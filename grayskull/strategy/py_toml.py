import re
from collections import defaultdict
from functools import singledispatch
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

import semver
import tomli

from grayskull.utils import nested_dict

VERSION_REGEX = re.compile(
    r"""[vV]?
        (?P<major>0|[1-9]\d*)
        (\.
        (?P<minor>0|[1-9]\d*)
        (\.
            (?P<patch>0|[1-9]\d*)
        )?
        )?
    """,
    re.VERBOSE,
)


class InvalidVersion(BaseException):
    pass


class InvalidPoetryDependency(BaseException):
    pass


def parse_version(version: str) -> Dict[str, Optional[str]]:
    """
    Parses a version string (not necessarily semver) to a dictionary with keys
    "major", "minor", and "patch". "minor" and "patch" are possibly None.
    """
    match = VERSION_REGEX.search(version)
    if not match:
        raise InvalidVersion(f"Could not parse version {version}.")

    return {
        key: None if value is None else int(value)
        for key, value in match.groupdict().items()
    }


def vdict_to_vinfo(version_dict: Dict[str, Optional[str]]) -> semver.VersionInfo:
    """
    Coerces version dictionary to a semver.VersionInfo object. If minor or patch
    numbers are missing, 0 is substituted in their place.
    """
    ver = {key: 0 if value is None else value for key, value in version_dict.items()}
    return semver.VersionInfo(**ver)


def coerce_to_semver(version: str) -> str:
    """
    Coerces a version string to a semantic version.
    """
    if semver.VersionInfo.is_valid(version):
        return version

    return str(vdict_to_vinfo(parse_version(version)))


def get_caret_ceiling(target: str) -> str:
    """
    Accepts a Poetry caret target and returns the exclusive version ceiling.

    Targets that are invalid semver strings (e.g. "1.2", "0") are handled
    according to the Poetry caret requirements specification, which is based on
    whether the major version is 0:

    - If the major version is 0, the ceiling is determined by bumping the
    rightmost specified digit and then coercing it to semver.
    Example: 0 => 1.0.0, 0.1 => 0.2.0, 0.1.2 => 0.1.3

    - If the major version is not 0, the ceiling is determined by
    coercing it to semver and then bumping the major version.
    Example: 1 => 2.0.0, 1.2 => 2.0.0, 1.2.3 => 2.0.0
    """
    if not semver.VersionInfo.is_valid(target):
        target_dict = parse_version(target)

        if target_dict["major"] == 0:
            if target_dict["minor"] is None:
                target_dict["major"] += 1
            elif target_dict["patch"] is None:
                target_dict["minor"] += 1
            else:
                target_dict["patch"] += 1
            return str(vdict_to_vinfo(target_dict))

        vdict_to_vinfo(target_dict)
        return str(vdict_to_vinfo(target_dict).bump_major())

    target_vinfo = semver.VersionInfo.parse(target)

    if target_vinfo.major == 0:
        if target_vinfo.minor == 0:
            return str(target_vinfo.bump_patch())
        else:
            return str(target_vinfo.bump_minor())
    else:
        return str(target_vinfo.bump_major())


def get_tilde_ceiling(target: str) -> str:
    """
    Accepts a Poetry tilde target and returns the exclusive version ceiling.
    """
    target_dict = parse_version(target)
    if target_dict["minor"]:
        return str(vdict_to_vinfo(target_dict).bump_minor())

    return str(vdict_to_vinfo(target_dict).bump_major())


def encode_poetry_version(poetry_specifier: str) -> str:
    """
    Encodes Poetry version specifier as a Conda version specifier.

    Example: ^1 => >=1.0.0,<2.0.0
    """
    poetry_clauses = poetry_specifier.split(",")

    conda_clauses = []
    for poetry_clause in poetry_clauses:
        poetry_clause = poetry_clause.replace(" ", "")
        if poetry_clause.startswith("^"):
            # handle ^ operator
            target = poetry_clause[1:]
            floor = coerce_to_semver(target)
            ceiling = get_caret_ceiling(target)
            conda_clauses.append(">=" + floor)
            conda_clauses.append("<" + ceiling)
            continue

        if poetry_clause.startswith("~"):
            # handle ~ operator
            target = poetry_clause[1:]
            floor = coerce_to_semver(target)
            ceiling = get_tilde_ceiling(target)
            conda_clauses.append(">=" + floor)
            conda_clauses.append("<" + ceiling)
            continue

        # other poetry clauses should be conda-compatible
        conda_clauses.append(poetry_clause)

    return ",".join(conda_clauses)


@singledispatch
def get_constrained_dep(dep_spec, dep_name):
    raise InvalidPoetryDependency(
        "Expected Poetry dependency specification to be of type str or dict, "
        f"received {type(dep_spec).__name__}"
    )


@get_constrained_dep.register
def __get_constrained_dep_dict(dep_spec: dict, dep_name: str):
    conda_version = encode_poetry_version(dep_spec.get("version", ""))
    return f"{dep_name} {conda_version}".strip()


@get_constrained_dep.register
def __get_constrained_dep_str(dep_spec: str, dep_name: str):
    conda_version = encode_poetry_version(dep_spec)
    return f"{dep_name} {conda_version}"


def encode_poetry_deps(poetry_deps: dict) -> Tuple[list, list]:
    run = []
    run_constrained = []
    for dep_name, dep_spec in poetry_deps.items():
        constrained_dep = get_constrained_dep(dep_spec, dep_name)
        try:
            assert dep_spec.get("optional", False)
            run_constrained.append(constrained_dep)
        except (AttributeError, AssertionError):
            run.append(constrained_dep)
    return run, run_constrained


def add_poetry_metadata(metadata: dict, toml_metadata: dict) -> dict:
    if not is_poetry_present(toml_metadata):
        return metadata

    poetry_metadata = toml_metadata["tool"]["poetry"]
    poetry_deps = poetry_metadata.get("dependencies", {})
    req_run, req_run_constrained = encode_poetry_deps(poetry_deps)

    # add dependencies
    metadata["requirements"].setdefault("run", [])
    metadata["requirements"]["run"].extend(req_run)

    # add optional dependencies
    if len(req_run_constrained):
        metadata["requirements"].setdefault("run_constrained", [])
        metadata["requirements"]["run_constrained"].extend(req_run_constrained)

    host_metadata = metadata["requirements"].get("host", [])
    if toml_metadata["tool"].get("poetry", {}).get("scripts"):
        metadata["build"]["entry_points"] = []
        for entry_name, entry_path in toml_metadata["tool"]["poetry"][
            "scripts"
        ].items():
            metadata["build"]["entry_points"].append(f"{entry_name} = {entry_path}")
    if "poetry" not in host_metadata and "poetry-core" not in host_metadata:
        metadata["requirements"]["host"] = host_metadata + ["poetry-core"]

    poetry_test_deps = (
        poetry_metadata.get("group", {}).get("test", {}).get("dependencies", {})
    )
    # add required test dependencies and ignore optional test dependencies, as
    # there doesn't appear to be a way to specify them in Conda recipe metadata.
    test_reqs, _ = encode_poetry_deps(poetry_test_deps)
    metadata["test"].get("requires", []).extend(test_reqs)
    return metadata


def is_poetry_present(toml_metadata: dict) -> bool:
    return "poetry" in toml_metadata.get("tool", {})


def is_flit_present(toml_metadata: dict) -> bool:
    return "flit" in toml_metadata.get("tool", {})


def add_flit_metadata(metadata: dict, toml_metadata: dict) -> dict:
    if not is_flit_present(toml_metadata):
        return metadata

    flit_metadata = toml_metadata["tool"]["flit"]
    flit_scripts = flit_metadata.get("scripts", {})
    for entry_name, entry_path in flit_scripts.items():
        if "build" not in metadata:
            metadata["build"] = {}
        if "entry_points" not in metadata["build"]:
            metadata["build"]["entry_points"] = []
        metadata["build"]["entry_points"].append(f"{entry_name} = {entry_path}")
    return metadata


def is_pep725_present(toml_metadata: dict):
    return "external" in toml_metadata


def get_pep725_mapping(purl: str):
    """This function maps a PURL to the name in the conda ecosystem. It is expected
    that this will be provided on a per-ecosystem basis (such as by conda-forge)"""

    package_mapping = {
        "virtual:compiler/c": "{{ compiler('c') }}",
        "virtual:compiler/cpp": "{{ compiler('cxx') }}",
        "virtual:compiler/fortran": "{{ compiler('fortran') }}",
        "virtual:compiler/rust": "{{ compiler('rust') }}",
        "virtual:interface/blas": "{{ blas }}",
        "pkg:generic/boost": "boost-cpp",
        "pkg:generic/brial": "brial",
        "pkg:generic/cddlib": "cddlib",
        "pkg:generic/cliquer": "cliquer",
        "pkg:generic/ecl": "ecl",
        "pkg:generic/eclib": "eclib",
        "pkg:generic/ecm": "ecm",
        "pkg:generic/fflas-ffpack": "fflas-ffpack",
        "pkg:generic/fplll": "fplll",
        "pkg:generic/flint": "libflint",
        "pkg:generic/libgd": "libgd",
        "pkg:generic/gap": "gap-defaults",
        "pkg:generic/gfan": "gfan",
        "pkg:generic/gmp": "gmp",
        "pkg:generic/giac": "giac",
        "pkg:generic/givaro": "givaro",
        "pkg:generic/pkg-config": "pkg-config",
        "pkg:generic/glpk": "glpk",
        "pkg:generic/gsl": "gsl",
        "pkg:generic/iml": "iml",
        "pkg:generic/lcalc": "lcalc",
        "pkg:generic/libbraiding": "libbraiding",
        "pkg:generic/libhomfly": "libhomfly",
        "pkg:generic/lrcalc": "lrcalc",
        "pkg:generic/libpng": "libpng",
        "pkg:generic/linbox": "linbox",
        "pkg:generic/m4ri": "m4ri",
        "pkg:generic/m4rie": "m4rie",
        "pkg:generic/mpc": "mpc",
        "pkg:generic/mpfi": "mpfi",
        "pkg:generic/mpfr": "mpfr",
        "pkg:generic/maxima": "maxima",
        "pkg:generic/nauty": "nauty",
        "pkg:generic/ntl": "ntl",
        "pkg:generic/pari": "pari",
        "pkg:generic/pari-elldata": "pari-elldata",
        "pkg:generic/pari-galdata": "pari-galdata",
        "pkg:generic/pari-seadata": "pari-seadata",
        "pkg:generic/palp": "palp",
        "pkg:generic/planarity": "planarity",
        "pkg:generic/ppl": "ppl",
        "pkg:generic/primesieve": "primesieve",
        "pkg:generic/primecount": "primecount",
        "pkg:generic/qhull": "qhull",
        "pkg:generic/rw": "rw",
        "pkg:generic/singular": "singular",
        "pkg:generic/symmetrica": "symmetrica",
        "pkg:generic/sympow": "sympow",
    }
    return package_mapping.get(purl, purl)


def add_pep725_metadata(metadata: dict, toml_metadata: dict):
    if not is_pep725_present(toml_metadata):
        return metadata

    externals = toml_metadata["external"]
    # each of these is a list of PURLs. For each one we find,
    # we need to map it to the the conda ecosystem
    requirements = metadata.get("requirements", {})
    section_map = (
        ("build", "build-requires"),
        ("host", "host-requires"),
        ("run", "dependencies"),
    )
    for conda_section, pep725_section in section_map:
        requirements.setdefault(conda_section, [])
        requirements[conda_section].extend(
            [get_pep725_mapping(purl) for purl in externals.get(pep725_section, [])]
        )
        # TODO: handle optional dependencies properly
        optional_features = toml_metadata.get(f"optional-{pep725_section}", {})
        for feature_name, feature_deps in optional_features.items():
            requirements[conda_section].append(
                f'# OPTIONAL dependencies from feature "{feature_name}"'
            )
            requirements[conda_section].extend(feature_deps)
        if not requirements[conda_section]:
            del requirements[conda_section]

    if requirements:
        metadata["requirements"] = requirements
    return metadata


def get_all_toml_info(path_toml: Union[Path, str]) -> dict:
    with open(path_toml, "rb") as f:
        toml_metadata = tomli.load(f)
    toml_metadata = defaultdict(dict, toml_metadata)
    metadata = nested_dict()
    toml_project = toml_metadata.get("project", {}) or {}
    metadata["requirements"]["host"] = toml_metadata["build-system"].get("requires", [])
    metadata["requirements"]["run"] = toml_project.get("dependencies", [])
    license = toml_project.get("license")
    if isinstance(license, dict):
        license = license.get("text", "")
    metadata["about"]["license"] = license
    optional_deps = toml_project.get("optional-dependencies", {})
    metadata["test"]["requires"] = (
        optional_deps.get("testing", [])
        or optional_deps.get("test", [])
        or optional_deps.get("tests", [])
    )

    tom_urls = toml_project.get("urls", {})
    if homepage := tom_urls.get("Homepage"):
        metadata["about"]["home"] = homepage
    if dev_url := tom_urls.get("Source"):
        metadata["about"]["dev_url"] = dev_url

    if toml_project.get("requires-python"):
        py_constrain = f"python {toml_project['requires-python']}"
        metadata["requirements"]["host"].append(py_constrain)
        metadata["requirements"]["run"].append(py_constrain)

    if toml_project.get("scripts"):
        metadata["build"]["entry_points"] = []
        for entry_name, entry_path in toml_project.get("scripts", {}).items():
            metadata["build"]["entry_points"].append(f"{entry_name} = {entry_path}")
    if all_urls := toml_project.get("urls"):
        metadata["about"]["dev_url"] = all_urls.get("Source", None)
        metadata["about"]["home"] = all_urls.get("Homepage", None)
    metadata["about"]["summary"] = toml_project.get("description")
    metadata["name"] = metadata.get("name") or toml_project.get("name")

    add_poetry_metadata(metadata, toml_metadata)
    add_flit_metadata(metadata, toml_metadata)
    add_pep725_metadata(metadata, toml_metadata)

    return metadata
