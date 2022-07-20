import logging
import os
import re
import sys
import tarfile
import zipfile
from os.path import basename
from pathlib import Path
from tempfile import mkdtemp
from typing import List

import requests
import yaml
from souschef.jinja_expression import set_global_jinja_var
from souschef.recipe import Recipe
from yaml import SafeDumper

from grayskull.config import Configuration
from grayskull.strategy.abstract_strategy import AbstractStrategy
from grayskull.utils import sha256_checksum

log = logging.getLogger(__name__)
CRAN_CONFIG = Path(os.path.dirname(__file__)) / "config.yaml"

ALL_SECTIONS = (
    "package",
    "source",
    "build",
    "outputs",
    "requirements",
    "app",
    "test",
    "about",
    "extra",
)

cran_url = "https://cran.r-project.org"


class CranStrategy(AbstractStrategy):
    @staticmethod
    def fetch_data(recipe, config, sections=None):
        return update_recipe(recipe, config, sections or ALL_SECTIONS)


# Convert the data extracted from the description file into a dictionary
def dict_from_cran_lines(lines):
    d = {}
    for line in lines:
        if not line:
            continue
        try:
            if ": " in line:
                (k, v) = line.split(": ", 1)
            else:
                # Sometimes fields are included but left blank, e.g.:
                #   - Enhances in data.tree
                #   - Suggests in corpcor
                (k, v) = line.split(":", 1)
        except ValueError:
            sys.exit("Error: Could not parse metadata (%s)" % line)
        d[k] = v
    d["orig_lines"] = lines
    return d


def remove_package_line_continuations(chunk):
    """
    >>> chunk = [
        'Package: A3',
        'Version: 0.9.2',
        'Depends: R (>= 2.15.0), xtable, pbapply',
        'Suggests: randomForest, e1071',
        'Imports: MASS, R.methodsS3 (>= 1.5.2), R.oo (>= 1.15.8), R.utils (>=',
        '        1.27.1), matrixStats (>= 0.8.12), R.filesets (>= 2.3.0), ',
        '        sampleSelection, scatterplot3d, strucchange, systemfit',
        'License: GPL (>= 2)',
        'NeedsCompilation: no']
    >>> remove_package_line_continuations(chunk)
    ['Package: A3',
     'Version: 0.9.2',
     'Depends: R (>= 2.15.0), xtable, pbapply',
     'Suggests: randomForest, e1071',
     'Imports: MASS, R.methodsS3 (>= 1.5.2), R.oo (>= 1.15.8), R.utils (>= 1.27.1), matrixStats (>= 0.8.12), R.filesets (>= 2.3.0), sampleSelection, scatterplot3d, strucchange, systemfit, rgl,'
     'License: GPL (>= 2)',
     'NeedsCompilation: no']
    """  # NOQA
    continuation = (" ", "\t")
    continued_ix = None
    continued_line = None
    had_continuation = False
    accumulating_continuations = False

    chunk.append("")

    for (i, line) in enumerate(chunk):
        if line.startswith(continuation):
            line = " " + line.lstrip()
            if accumulating_continuations:
                assert had_continuation
                continued_line += line
                chunk[i] = None
            else:
                accumulating_continuations = True
                continued_ix = i - 1
                continued_line = chunk[continued_ix] + line
                had_continuation = True
                chunk[i] = None
        else:
            if accumulating_continuations:
                assert had_continuation
                chunk[continued_ix] = continued_line
                accumulating_continuations = False
                continued_line = None
                continued_ix = None

    if had_continuation:
        # Remove the None(s).
        chunk = [c for c in chunk if c]

    chunk.append("")

    return chunk


def yaml_quote_string(string):
    """
    Quote a string for use in YAML.

    We can't just use yaml.dump because it adds ellipses to the end of the
    string, and it in general doesn't handle being placed inside an existing
    document very well.

    Note that this function is NOT general.
    """
    return (
        yaml.dump(string, Dumper=SafeDumper)
        .replace("\n...\n", "")
        .replace("\n", "\n  ")
        .rstrip("\n ")
    )


# Due to how the metadata is rendered there can be
# significant areas of repeated newlines.
# This collapses them and also strips any trailing spaces.
def clear_whitespace(string):
    lines = []
    last_line = ""
    for line in string.splitlines():
        line = line.rstrip()
        if not (line == "" and last_line == ""):
            lines.append(line)
        last_line = line
    return "\n".join(lines)


# Reads the description file contents and formats them by
# running other functions on the content and returns the dictionary.
def read_description_contents(fp):
    bytes_ = fp.read()
    text = bytes_.decode("utf-8", errors="replace")
    text = clear_whitespace(text)
    lines = remove_package_line_continuations(text.splitlines())
    return dict_from_cran_lines(lines)


# Extracting the DESCRIPTION file from the downloaded package.
def get_archive_metadata(path, verbose=True):
    if verbose:
        print("Reading package metadata from %s" % path)
    if basename(path) == "DESCRIPTION":
        with open(path, "rb") as fp:
            return read_description_contents(fp)
    elif tarfile.is_tarfile(path):
        with tarfile.open(path, "r") as tf:
            for member in tf:
                if re.match(r"^[^/]+/DESCRIPTION$", member.name):
                    fp = tf.extractfile(member)
                    return read_description_contents(fp)
    elif path.endswith(".zip"):
        with zipfile.ZipFile(path, "r") as zf:
            for member in zf.infolist():
                if re.match(r"^[^/]+/DESCRIPTION$", member.filename):
                    fp = zf.open(member, "r")
                    return read_description_contents(fp)
    else:
        sys.exit("Cannot extract a DESCRIPTION from file %s" % path)
    sys.exit("%s does not seem to be a CRAN package (no DESCRIPTION) file" % path)


def get_cran_archive_versions(cran_url, session, package, verbose=True):
    if verbose:
        print(f"Fetching archived versions for package {package} from {cran_url}")
    r = session.get(cran_url + "/src/contrib/Archive/" + package + "/")
    try:
        r.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print("No archive directory for package %s" % package)
            return []
        raise
    versions = []
    for p, dt in re.findall(
        r'<td><a href="([^"]+)">\1</a></td>\s*<td[^>]*>([^<]*)</td>', r.text
    ):
        if p.endswith(".tar.gz") and "_" in p:
            name, version = p.rsplit(".", 2)[0].split("_", 1)
            versions.append((dt.strip(), version))
    return [v for dt, v in sorted(versions, reverse=True)]


# Fetch the entire CRAN index and store it.
def get_cran_index(cran_url, verbose=True):
    if verbose:
        print("Fetching main index from %s" % cran_url)
    r = requests.get(cran_url + "/src/contrib/")
    r.raise_for_status()
    records = {}
    for p in re.findall(r'<td><a href="([^"]+)">\1</a></td>', r.text):
        if p.endswith(".tar.gz") and "_" in p:
            name, version = p.rsplit(".", 2)[0].split("_", 1)
            records[name.lower()] = (name, version)
    r = requests.get(cran_url + "/src/contrib/Archive/")
    r.raise_for_status()
    for p in re.findall(r'<td><a href="([^"]+)/">\1/</a></td>', r.text):
        if re.match(r"^[A-Za-z]", p):
            records.setdefault(p.lower(), (p, None))
    return records


def get_available_binaries(cran_url, details):
    url = cran_url + "/" + details["dir"]
    response = requests.get(url)
    response.raise_for_status()
    ext = details["ext"]
    for filename in re.findall(r'<a href="([^"]*)">\1</a>', response.text):
        if filename.endswith(ext):
            pkg, _, ver = filename.rpartition("_")
            ver, _, _ = ver.rpartition(ext)
            details["binaries"].setdefault(pkg, []).append((ver, url + filename))


# Look for the package in the stored CRAN index.
def get_cran_metadata(recipe, config: Configuration) -> dict:
    """Method responsible for getting CRAN metadata.
    :return: CRAN metadata"""
    # get_archive_metadata(path, verbose=True)
    cran_index = get_cran_index(cran_url)
    if config.name.lower() not in cran_index:
        sys.exit("Package %s not found" % config.name)
    package, cran_version = cran_index[config.name.lower()]
    print(package)
    print(cran_version)
    tarball_name = package + "_" + cran_version + ".tar.gz"
    download_url = cran_url + "/src/contrib/" + tarball_name
    print(download_url)
    response = requests.get(download_url)
    response.raise_for_status()
    download_file = os.path.join(
        str(mkdtemp(f"grayskull-cran-metadata-{config.name}-")), tarball_name
    )
    with open(download_file, "wb") as f:
        f.write(response.content)
    metadata = get_archive_metadata(download_file)
    global r_recipe_end_comment
    r_recipe_end_comment = "\n".join(
        ["# %s" % line for line in metadata["orig_lines"] if line]
    )
    print(r_recipe_end_comment)

    imports = []
    # Extract 'imports' from metadata.
    # Imports is equivalent to run and host dependencies.
    # Add 'r-' suffix to all packages listed in imports.
    for s in metadata.get("Imports", "").split(","):
        if not s.strip():
            continue
        r = s.split("(")
        if len(r) == 1:
            imports.append(f"r-{r[0].strip()}")
        else:
            constrain = r[1].strip().replace(")", "").replace(" ", "")
            imports.append(f"r-{r[0].strip()} {constrain.strip()}")

    # Every CRAN package will always depend on the R base package.
    # Hence the 'r-base' package is always present
    # in the host and run requirements.
    imports.append("r-base")
    imports.sort()  # this is not a requirement in conda but good for readability

    d = {
        "package": {
            "name": "r-" + metadata.get("Package"),
            "version": metadata.get("Version"),
        },
        "source": {
            "sha256": sha256_checksum(download_file),
            "url": "{{ cran_mirror }}/src/contrib/"
            + "{{ package }}_{{ cran_version }}.tar.gz",
        },
        "build": {
            "entry_points": metadata.get("entry_points"),
            "rpaths": ["lib/R/lib/", "lib/"],
        },
        "requirements": {
            "build": "",
            "run": imports,
            "host": imports,
        },
        "test": {
            "imports": metadata.get("tests"),
        },
        "about": {
            "home": metadata["URL"],
            "summary": metadata.get("Description"),
            "doc_url": metadata.get("doc_url"),
            "dev_url": metadata.get("dev_url"),
            "license": metadata.get("License"),
        },
    }
    return d


# add posix and native at the top
set_posix = "{{% set posix = 'm2-' if win else '' %}}"
set_native = "{{% set native = 'm2w64-' if win else '' %}}"
posix_native = "\n" + set_posix + "\n" + set_native


def update_recipe(recipe: Recipe, config: Configuration, all_sections: List[str]):
    """Update one specific section."""
    metadata = get_cran_metadata(recipe, config)
    recipe.add_section(metadata)
    set_global_jinja_var(recipe, "version", metadata["package"]["version"])
    config.version = metadata["package"]["version"]
    recipe["package"]["version"] = "<{ version }}"
    recipe["test"]["commands"] = [
        f"$R -e \"library('{config.name}')\"  # [not win]",
        f'"%R%" -e "library(\'{config.name}\')"  # [win]',
    ]
    recipe.inline_comment = posix_native
    recipe.inline_comment = r_recipe_end_comment
