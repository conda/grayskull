from collections import defaultdict
from pathlib import Path
from typing import Union

import tomli

from grayskull.utils import nested_dict


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
    metadata["test"]["requires"] = (
        toml_metadata["project"].get("optional-dependencies", {}).get("testing", [])
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
    all_urls = toml_metadata["project"].get("urls")
    if all_urls:
        metadata["about"]["dev_url"] = all_urls.get("Source", None)
        metadata["about"]["home"] = all_urls.get("Homepage", None)
    metadata["about"]["summary"] = toml_metadata["project"].get("description")
    return metadata
