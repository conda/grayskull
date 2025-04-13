import sys
from collections import defaultdict
from collections.abc import Iterator
from functools import singledispatch
from pathlib import Path

from grayskull.strategy.parse_poetry_version import (
    combine_conda_selectors,
    encode_poetry_platform_to_selector_item,
    encode_poetry_python_version_to_selector_item,
    encode_poetry_version,
)
from grayskull.utils import nested_dict

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class InvalidPoetryDependency(BaseException):
    pass


@singledispatch
def get_constrained_dep(dep_spec: list | str | dict, dep_name: str) -> str:
    raise InvalidPoetryDependency(
        "Expected Poetry dependency specification to be of type list, str or dict, "
        f"received {type(dep_spec).__name__}"
    )


@get_constrained_dep.register
def __get_constrained_dep_dict(
    dep_spec: dict, dep_name: str
) -> Iterator[str, None, None]:
    """
    Yield a dependency entry in conda format from a Poetry entry
    with version, python version, and platform

    Example:
        dep_spec:
            {"version": "^1.5", "python": ">=3.8,<3.12", "platform": "darwin"},
        dep_name:
            "pandas",
        result yield:
            "pandas >=1.5.0,<2.0.0  # [py>=38 and py<312 and osx]"
    """
    conda_version = encode_poetry_version(dep_spec.get("version", ""))
    if conda_version:
        conda_version = f" {conda_version}"
    python_selector = encode_poetry_python_version_to_selector_item(
        dep_spec.get("python", "")
    )
    platform_selector = encode_poetry_platform_to_selector_item(
        dep_spec.get("platform", "")
    )
    conda_selector = combine_conda_selectors(python_selector, platform_selector)
    yield f"{dep_name}{conda_version}{conda_selector}".strip()


@get_constrained_dep.register
def __get_constrained_dep_str(
    dep_spec: str, dep_name: str
) -> Iterator[str, None, None]:
    conda_version = encode_poetry_version(dep_spec)
    yield f"{dep_name} {conda_version}"


@get_constrained_dep.register
def __get_constrained_dep_list(
    dep_spec_list: list, dep_name: str
) -> Iterator[str, None, None]:
    for dep_spec in dep_spec_list:
        yield from get_constrained_dep(dep_spec, dep_name)


def encode_poetry_deps(poetry_deps: dict) -> tuple[list, list]:
    run = []
    run_constrained = []
    for dep_name, dep_spec in poetry_deps.items():
        for constrained_dep in get_constrained_dep(dep_spec, dep_name):
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
    if test_reqs:
        extra_metadata = metadata["requirements"].setdefault("extra", {})
        for name in ("test", "tests", "testing"):
            if name in extra_metadata:
                extra_metadata[name] += test_reqs
                break
        else:
            extra_metadata["test"] = test_reqs
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


def get_all_toml_info(path_toml: Path | str) -> dict:
    with open(path_toml, "rb") as f:
        toml_metadata = tomllib.load(f)
    toml_metadata = defaultdict(dict, toml_metadata)
    metadata = nested_dict()
    toml_project = toml_metadata.get("project", {}) or {}
    metadata["requirements"]["host"] = toml_metadata["build-system"].get("requires", [])
    metadata["requirements"]["run"] = toml_project.get("dependencies", [])
    metadata["requirements"]["extra"] = toml_project.get("optional-dependencies", {})
    license = toml_project.get("license")
    if isinstance(license, dict):
        license = license.get("text", "")
    metadata["about"]["license"] = license

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
