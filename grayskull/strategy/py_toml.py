from collections import defaultdict
from pathlib import Path
from typing import Union

import tomli

from grayskull.utils import nested_dict


def add_poetry_metadata(metadata: dict, toml_metadata: dict) -> dict:
    if not is_poetry_present(toml_metadata):
        return metadata

    def flat_deps(dict_deps: dict) -> list:
        result = []
        for pkg_name, version in dict_deps.items():
            if isinstance(version, dict):
                version_spec = version["version"].strip()
                del version["version"]
                version = (
                    f"{version_spec}{' ; '.join(f'{k} {v}' for k,v in version.items())}"
                )
            version = f"=={version}" if version and version[0].isdigit() else version
            result.append(f"{pkg_name} {version}".strip())
        return result

    poetry_metadata = toml_metadata["tool"]["poetry"]
    if poetry_run := flat_deps(poetry_metadata.get("dependencies", {})):
        if not metadata["requirements"]["run"]:
            metadata["requirements"]["run"] = []
        metadata["requirements"]["run"].extend(poetry_run)

    host_metadata = metadata["requirements"].get("host", [])
    if "poetry" not in host_metadata and "poetry-core" not in host_metadata:
        metadata["requirements"]["host"] = host_metadata + ["poetry-core"]

    test_metadata = metadata["test"].get("requires", []) or []
    if (
        test_deps := poetry_metadata.get("group", {})
        .get("test", {})
        .get("dependencies", {})
    ):
        test_deps = flat_deps(test_deps)
        metadata["test"]["requires"] = test_metadata + test_deps
    return metadata


def is_poetry_present(toml_metadata: dict) -> bool:
    return "poetry" in toml_metadata.get("tool", {})


def get_all_toml_info(path_toml: Union[Path, str]) -> dict:
    with open(path_toml, "rb") as f:
        toml_metadata = tomli.load(f)
    toml_metadata = defaultdict(dict, toml_metadata)
    metadata = nested_dict()

    metadata["requirements"]["host"] = toml_metadata["build-system"].get("requires", [])
    metadata["requirements"]["run"] = toml_metadata["project"].get("dependencies", [])
    license = toml_metadata["project"].get("license")
    if isinstance(license, dict):
        license = license.get("text", "")
    metadata["about"]["license"] = license
    optional_deps = toml_metadata["project"].get("optional-dependencies", {})
    metadata["test"]["requires"] = (
        optional_deps.get("testing", [])
        or optional_deps.get("test", [])
        or optional_deps.get("tests", [])
    )

    if toml_metadata["project"].get("requires-python"):
        py_constrain = f"python {toml_metadata['project']['requires-python']}"
        metadata["requirements"]["host"].append(py_constrain)
        metadata["requirements"]["run"].append(py_constrain)

    if toml_metadata["project"].get("scripts"):
        metadata["build"]["entry_points"] = []
        for entry_name, entry_path in (
            toml_metadata["project"].get("scripts", {}).items()
        ):
            metadata["build"]["entry_points"].append(f"{entry_name} = {entry_path}")
    if all_urls := toml_metadata["project"].get("urls"):
        metadata["about"]["dev_url"] = all_urls.get("Source", None)
        metadata["about"]["home"] = all_urls.get("Homepage", None)
    metadata["about"]["summary"] = toml_metadata["project"].get("description")

    add_poetry_metadata(metadata, toml_metadata)

    return metadata
