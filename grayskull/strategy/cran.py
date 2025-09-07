from __future__ import annotations

import logging
import os
import re
import shutil
import sys
import tarfile
import zipfile
from copy import deepcopy
from os.path import basename
from tempfile import mkdtemp
from urllib.request import Request, urlopen

import requests
from bs4 import BeautifulSoup
from souschef.jinja_expression import set_global_jinja_var

from grayskull.base.github import generate_git_archive_tarball_url, handle_gh_version
from grayskull.cli.stdout import print_msg
from grayskull.config import Configuration
from grayskull.license.discovery import match_license
from grayskull.strategy.abstract_strategy import AbstractStrategy
from grayskull.utils import origin_is_github, sha256_checksum

log = logging.getLogger(__name__)

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


class CranStrategy(AbstractStrategy):
    CRAN_URL = "https://cran.r-project.org"
    SET_POSIX = "{% set posix = 'm2-' if win else '' %}"
    SET_NATIVE = "{% set native = 'm2w64-' if win else '' %}"
    POSIX_NATIVE = f"\n{SET_POSIX}\n{SET_NATIVE}\n\n"

    @staticmethod
    def fetch_data(recipe, config, sections=None):
        metadata, r_recipe_end_comment = get_cran_metadata(
            config, CranStrategy.CRAN_URL
        )
        sections = sections or ALL_SECTIONS

        for sec in sections:
            metadata_section = metadata.get(sec)
            if metadata_section:
                recipe[sec] = metadata_section
                
        # Set Jinja2 global variables for the recipe
        set_global_jinja_var(recipe, "name", config.name)
        if config.version:
            set_global_jinja_var(recipe, "version", config.version)
            
        if metadata.get("need_compiler", False):
            set_global_jinja_var(recipe, "posix", 'm2-" if win else "')
            set_global_jinja_var(recipe, "native", 'm2w64-" if win else "')
        return recipe


def dict_from_cran_lines(lines):
    """Convert the data extracted from the description file into a dictionary"""
    d = {}
    for line in lines:
        if not line:
            continue
        try:
            (k, v) = line.split(": ", 1) if ": " in line else line.split(":", 1)
        except ValueError:
            sys.exit(f"Error: Could not parse metadata ({line})")
        d[k] = v
    d["orig_lines"] = lines
    return d


def remove_package_line_continuations(chunk):
    """
    >>> chunk = [
    ...     'Package: A3',
    ...     'Version: 0.9.2',
    ...     'Depends: R (>= 2.15.0), xtable, pbapply',
    ...     'Suggests: randomForest, e1071',
    ...     'Imports: MASS, R.methodsS3 (>= 1.5.2), R.oo (>= 1.15.8), R.utils (>=',
    ...     '        1.27.1), matrixStats (>= 0.8.12), R.filesets (>= 2.3.0), ',
    ...     '        sampleSelection, scatterplot3d, strucchange, systemfit',
    ...     'License: GPL (>= 2)',
    ...     'NeedsCompilation: no']
    >>> remove_package_line_continuations(chunk)  # doctest: +NORMALIZE_WHITESPACE
    ['Package: A3',
     'Version: 0.9.2',
     'Depends: R (>= 2.15.0), xtable, pbapply',
     'Suggests: randomForest, e1071',
     'Imports: MASS, R.methodsS3 (>= 1.5.2), R.oo (>= 1.15.8), R.utils (>= 1.27.1), matrixStats (>= 0.8.12), R.filesets (>= 2.3.0),  sampleSelection, scatterplot3d, strucchange, systemfit',
     'License: GPL (>= 2)',
     'NeedsCompilation: no',
     '']
    """  # NOQA
    continuation = (" ", "\t")
    continued_ix = None
    continued_line = None
    had_continuation = False
    accumulating_continuations = False

    chunk.append("")

    for i, line in enumerate(chunk):
        if line.startswith(continuation):
            line = f" {line.lstrip()}"
            if accumulating_continuations:
                assert had_continuation
                continued_line += line
            else:
                accumulating_continuations = True
                continued_ix = i - 1
                continued_line = chunk[continued_ix] + line
                had_continuation = True
            chunk[i] = None
        elif accumulating_continuations:
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


def clear_whitespace(string):
    """Due to how the metadata is rendered there can be
    significant areas of repeated newlines.
    This collapses them and also strips any trailing spaces.
    """
    lines = []
    last_line = ""
    for line in string.splitlines():
        line = line.rstrip()
        if line or last_line:
            lines.append(line)
        last_line = line
    return "\n".join(lines)


def read_description_contents(fp):
    """Reads the description file contents and formats them by
    running other functions on the content and returns the dictionary.
    """
    bytes_ = fp.read()
    text = bytes_.decode("utf-8", errors="replace")
    text = clear_whitespace(text)
    lines = remove_package_line_continuations(text.splitlines())
    return dict_from_cran_lines(lines)


def get_archive_metadata(path):
    """Extracting the DESCRIPTION file from the downloaded package."""
    print_msg(f"Reading package metadata from {path}")
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
        sys.exit(f"Cannot extract a DESCRIPTION from file {path}")
    sys.exit(f"{path} does not seem to be a CRAN package (no DESCRIPTION) file")


def scrap_main_page_cran_find_latest_package(
    cran_url: str, pkg_name: str, pkg_version: str | None
):
    pkg_name = pkg_name.strip().lower()
    pkg_version = pkg_version.strip().lower() if pkg_version else None
    for url_a in get_webpage(f"{cran_url}/src/contrib/").findAll("a"):
        url_text = url_a.get_text()
        if url_text.endswith(".tar.gz") and "_" in url_text:
            name, version = url_text.rsplit(".", 2)[0].rsplit("_", 1)
            version = version.strip().lower()
            name = name.strip().lower()
            if name == pkg_name:
                pkg_url = f"{cran_url}/src/contrib/Archive"
                if pkg_version is None or pkg_version == version:
                    pkg_version = version
                    pkg_url = f"{cran_url}/src/contrib/{url_a.get('href')}"
                return pkg_name, pkg_version, pkg_url
    raise ValueError(
        f"It was not possible to find the package requested. pkg: {pkg_name}"
    )


def scrap_cran_archive_page_for_package_folder_url(cran_url: str, pkg_name: str):
    for url_a in get_webpage(cran_url).findAll("a"):
        if url_a.get_text().strip().lower() == f"{pkg_name.strip().lower()}/":
            return f"{cran_url}/{url_a.get('href')}"
    raise ValueError(
        f"It was not possible to find the package requested. pkg: {pkg_name}"
    )


def scrap_cran_pkg_folder_page_for_full_url(
    cran_url: str, pkg_name: str, pkg_version: str
):
    for url_a in get_webpage(cran_url).findAll("a"):
        try:
            url_name, url_pkg_version = (
                url_a.get_text().rsplit(".", 2)[0].rsplit("_", 1)
            )
        except ValueError:
            continue
        url_name = url_name.strip().lower()
        url_pkg_version = url_pkg_version.strip().lower()
        if pkg_name.strip().lower() == url_name and pkg_version == url_pkg_version:
            return (
                f"{cran_url}{'' if cran_url.endswith('/') else '/'}{url_a.get('href')}"
            )
    raise ValueError("It was not possible to find the package requested")


def get_webpage(cran_url):
    req = Request(cran_url)
    html_page = urlopen(req)
    return BeautifulSoup(html_page, features="html.parser")


def get_cran_index(cran_url: str, pkg_name: str, pkg_version: str | None = None):
    """Fetch the entire CRAN index and store it."""
    print_msg(f"Fetching main index from {cran_url}")

    name, version, url_page = scrap_main_page_cran_find_latest_package(
        cran_url, pkg_name, pkg_version
    )
    if url_page.endswith(".tar.gz"):
        return name, version, url_page

    url_page = scrap_cran_archive_page_for_package_folder_url(url_page, pkg_name)
    return (
        name,
        version,
        scrap_cran_pkg_folder_page_for_full_url(url_page, pkg_name, pkg_version),
    )


def get_cran_metadata(config: Configuration, cran_url: str):
    """Method responsible for getting CRAN metadata.
    Look for the package in the stored CRAN index.
    :return: CRAN metadata"""
    if config.name.startswith("r-"):
        config.name = config.name[2:]
    
    # Check if this is a GitHub repository
    # Use repo_github if it exists (set by Configuration when parsing GitHub URLs)
    if hasattr(config, 'repo_github') and config.repo_github and origin_is_github(config.repo_github):
        return get_github_r_metadata(config)
    
    pkg_name = config.name
    pkg_version = str(config.version) if config.version else None
    _, pkg_version, pkg_url = get_cran_index(cran_url, pkg_name, pkg_version)
    
    # Set version as global jinja variable for consistent recipe generation
    config.version = pkg_version
    
    print_msg(pkg_name)
    print_msg(pkg_version)
    download_file = download_cran_pkg(config, pkg_url)
    metadata = get_archive_metadata(download_file)
    r_recipe_end_comment = "\n".join(
        [f"# {line}" for line in metadata["orig_lines"] if line]
    )

    print_msg(r_recipe_end_comment)

    imports = []
    r_base_version = None
    
    # Extract dependencies from both 'Depends' and 'Imports' fields
    # Process 'Depends' first to extract R version requirements
    for s in metadata.get("Depends", "").split(","):
        if not s.strip():
            continue
        s = s.strip()
        if s.startswith("R "):
            # Extract R version constraint
            r_parts = s.split("(")
            if len(r_parts) > 1:
                r_version_constraint = r_parts[1].strip().replace(")", "").replace(" ", "")
                r_base_version = r_version_constraint
        else:
            # Regular package dependency
            r = s.split("(")
            if len(r) == 1:
                imports.append(f"r-{r[0].strip()}")
            else:
                constrain = r[1].strip().replace(")", "").replace(" ", "")
                imports.append(f"r-{r[0].strip()} {constrain.strip()}")
    
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
    # Hence, the 'r-base' package is always present
    # in the host and run requirements.
    # Add version constraint if found in Depends field
    if r_base_version:
        imports.append(f"r-base {r_base_version}")
    else:
        imports.append("r-base")
    imports.sort()  # this is not a requirement in conda but good for readability

    dict_metadata = {
        "package": {
            "name": "r-{{ name }}",
            "version": "{{ version }}",
        },
        "source": {
            "url": pkg_url.replace(pkg_version, "{{ version }}"),
            "sha256": sha256_checksum(download_file),
        },
        "build": {
            "number": 0,
            "merge_build_host": True,
            "script": "R CMD INSTALL --build .",
            "entry_points": metadata.get("entry_points"),
            "rpaths": ["lib/R/lib/", "lib/"],
        },
        "requirements": {
            "build": [],
            "host": deepcopy(imports),
            "run": deepcopy(imports),
        },
        "test": {
            "imports": metadata.get("tests"),
            "commands": [
                f"$R -e \"library('{config.name}')\"  # [not win]",
                f'"%R%" -e "library(\'{config.name}\')"  # [win]',
            ],
        },
        "about": {
            "home": metadata["URL"],
            "summary": metadata.get("Description"),
            "doc_url": metadata.get("doc_url"),
            "dev_url": metadata.get("dev_url"),
            "license": match_license(metadata.get("License", "")).get("licenseId")
            or metadata.get("License", ""),
        },
    }
    if metadata.get("NeedsCompilation", "no").lower() == "yes":
        dict_metadata["need_compiler"] = True
        dict_metadata["requirements"]["build"].extend(
            [
                "cross-r-base {{ r_base }}  # [build_platform != target_platform]",
                "autoconf  # [unix]",
                "{{ compiler('c') }}  # [unix]",
                "{{ compiler('m2w64_c') }}  # [win]",
                "{{ compiler('cxx') }}  # [unix]",
                "{{ compiler('m2w64_cxx') }}  # [win]",
                "posix  # [win]",
            ]
        )
    if not dict_metadata["requirements"]["build"]:
        del dict_metadata["requirements"]["build"]
    return dict_metadata, r_recipe_end_comment


def get_github_r_metadata(config: Configuration):
    """Method responsible for getting R metadata from GitHub repositories.
    
    :param config: Configuration object containing package information
    :return: R metadata dictionary and recipe comment
    """
    print_msg("Fetching R package metadata from GitHub repository...")
    
    # Extract GitHub URL and package name
    # Use repo_github if available (set by Configuration.__post_init__), otherwise use config.name
    github_url = getattr(config, 'repo_github', None) or config.name
    if github_url.endswith('/'):
        github_url = github_url.rstrip('/')
    
    # Extract package name from URL (last part) or use config.name if it's already parsed
    if hasattr(config, 'repo_github') and config.repo_github:
        pkg_name = config.name  # Already parsed by Configuration
    else:
        pkg_name = github_url.split('/')[-1]
    
    # Handle version and get the appropriate Git reference
    version, version_tag = handle_gh_version(
        name=pkg_name,
        version=config.version,
        url=github_url,
        tag=None
    )
    
    # Generate archive URL for the specific version/tag
    archive_url = generate_git_archive_tarball_url(git_url=github_url, git_ref=version_tag)
    
    print_msg(f"Package: {pkg_name}")
    print_msg(f"Version: {version}")
    print_msg(f"Archive URL: {archive_url}")
    
    # Download and extract the GitHub archive
    download_file = download_github_r_pkg(config, archive_url, pkg_name, version)
    
    # Extract metadata from the DESCRIPTION file
    metadata = get_github_archive_metadata(download_file)
    
    r_recipe_end_comment = "\n".join(
        [f"# {line}" for line in metadata["orig_lines"] if line]
    )

    print_msg(r_recipe_end_comment)

    imports = []
    r_base_version = None
    
    # Extract dependencies from both 'Depends' and 'Imports' fields
    # Process 'Depends' first to extract R version requirements
    for s in metadata.get("Depends", "").split(","):
        if not s.strip():
            continue
        s = s.strip()
        if s.startswith("R "):
            # Extract R version constraint
            r_parts = s.split("(")
            if len(r_parts) > 1:
                r_version_constraint = r_parts[1].strip().replace(")", "").replace(" ", "")
                r_base_version = r_version_constraint
        else:
            # Regular package dependency
            r = s.split("(")
            if len(r) == 1:
                imports.append(f"r-{r[0].strip()}")
            else:
                constrain = r[1].strip().replace(")", "").replace(" ", "")
                imports.append(f"r-{r[0].strip()} {constrain.strip()}")
    
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
    # Add version constraint if found in Depends field
    if r_base_version:
        imports.append(f"r-base {r_base_version}")
    else:
        imports.append("r-base")
    imports.sort()  # this is not a requirement in conda but good for readability

    # Create source URL with placeholders for templating
    source_url = archive_url.replace(version_tag, "{{ version }}")
    if version_tag.startswith('v') and not version.startswith('v'):
        source_url = archive_url.replace(version_tag, "v{{ version }}")

    dict_metadata = {
        "package": {
            "name": "r-{{ name }}",
            "version": "{{ version }}",
        },
        "source": {
            "url": source_url,
            "sha256": sha256_checksum(download_file),
        },
        "build": {
            "number": 0,
            "merge_build_host": True,
            "script": "R CMD INSTALL --build .",
            "entry_points": metadata.get("entry_points"),
            "rpaths": ["lib/R/lib/", "lib/"],
        },
        "requirements": {
            "build": [],
            "host": deepcopy(imports),
            "run": deepcopy(imports),
        },
        "test": {
            "imports": metadata.get("tests"),
            "commands": [
                f"$R -e \"library('{pkg_name}')\"  # [not win]",
                f'"%R%" -e "library(\'{pkg_name}\')"  # [win]',
            ],
        },
        "about": {
            "home": github_url,
            "summary": metadata.get("Description"),
            "doc_url": metadata.get("URL"),
            "dev_url": github_url,
            "license": match_license(metadata.get("License", "")).get("licenseId")
            or metadata.get("License", ""),
        },
    }
    
    if metadata.get("NeedsCompilation", "no").lower() == "yes":
        dict_metadata["need_compiler"] = True
        dict_metadata["requirements"]["build"].extend(
            [
                "cross-r-base {{ r_base }}  # [build_platform != target_platform]",
                "autoconf  # [unix]",
                "{{ compiler('c') }}  # [unix]",
                "{{ compiler('m2w64_c') }}  # [win]",
                "{{ compiler('cxx') }}  # [unix]",
                "{{ compiler('m2w64_cxx') }}  # [win]",
                "posix  # [win]",
            ]
        )
    if not dict_metadata["requirements"]["build"]:
        del dict_metadata["requirements"]["build"]
        
    # Set the package name and version in config for recipe generation
    config.name = pkg_name
    config.version = version
        
    return dict_metadata, r_recipe_end_comment


def download_github_r_pkg(config: Configuration, archive_url: str, pkg_name: str, version: str):
    """Download R package archive from GitHub.
    
    :param config: Configuration object
    :param archive_url: GitHub archive URL  
    :param pkg_name: Package name
    :param version: Package version
    :return: Path to downloaded file
    """
    tarball_name = f"{pkg_name}-{version}.tar.gz"
    print_msg(f"Downloading from: {archive_url}")
    
    response = requests.get(archive_url, timeout=30)
    response.raise_for_status()
    
    download_file = os.path.join(
        str(mkdtemp(f"grayskull-github-r-{pkg_name}-")), tarball_name
    )
    
    with open(download_file, "wb") as f:
        f.write(response.content)
    
    return download_file


def get_github_archive_metadata(archive_path: str):
    """Extract metadata from GitHub R package archive.
    
    :param archive_path: Path to the downloaded archive
    :return: Metadata dictionary
    """
    print_msg("Extracting metadata from GitHub R package...")
    
    # Create temporary directory for extraction
    temp_dir = mkdtemp(prefix="grayskull-github-r-extract-")
    
    try:
        # Extract the archive
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(temp_dir, filter='data')
        
        # Find the DESCRIPTION file
        # GitHub archives typically have a top-level directory
        extracted_dirs = [d for d in os.listdir(temp_dir) 
                         if os.path.isdir(os.path.join(temp_dir, d))]
        
        if not extracted_dirs:
            raise ValueError("No directories found in the archive")
        
        # Use the first directory (there should be only one)
        package_dir = os.path.join(temp_dir, extracted_dirs[0])
        description_path = os.path.join(package_dir, "DESCRIPTION")
        
        if not os.path.exists(description_path):
            raise ValueError("DESCRIPTION file not found in the R package")
        
        # Read and parse the DESCRIPTION file
        with open(description_path, "r", encoding="utf-8") as f:
            description_content = f.read()
        
        # Parse the DESCRIPTION file content
        lines = description_content.strip().split("\n")
        lines = remove_package_line_continuations(lines)
        metadata = dict_from_cran_lines(lines)
        
        return metadata
        
    finally:
        # Clean up temporary directory
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def download_cran_pkg(config, pkg_url):
    tarball_name = pkg_url.rsplit("/", 1)[-1]
    print_msg(pkg_url)
    response = requests.get(pkg_url)
    response.raise_for_status()
    download_file = os.path.join(
        str(mkdtemp(f"grayskull-cran-metadata-{config.name}-")), tarball_name
    )
    with open(download_file, "wb") as f:
        f.write(response.content)
    return download_file
