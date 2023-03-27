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
    if semver.VersionInfo.isvalid(version):
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
    if not semver.VersionInfo.isvalid(target):
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
    conda_version = encode_poetry_version(dep_spec["version"])
    return f"{dep_name} {conda_version}"


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

    add_poetry_metadata(metadata, toml_metadata)

    return metadata
