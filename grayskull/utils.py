import ast
import hashlib
import logging
import os
import re
from collections import namedtuple
from difflib import SequenceMatcher
from functools import lru_cache
from glob import glob
from pathlib import Path
from shutil import copyfile
from typing import Any, List, Optional, Union

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from souschef.ingredient import IngredientList
from souschef.section import Section

log = logging.getLogger(__name__)

PyVer = namedtuple("PyVer", ["major", "minor"])
yaml = YAML(typ="jinja2")
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.width = 600


@lru_cache(maxsize=10)
def get_std_modules() -> List:
    from stdlib_list import stdlib_list

    all_libs = set()
    for py_ver in ("2.7", "3.6", "3.7", "3.8"):
        all_libs.update(stdlib_list(py_ver))
    return list(all_libs)


def get_all_modules_imported_script(script_file: str) -> set:
    modules = set()

    def visit_Import(node):
        for name in node.names:
            if name.name:
                modules.add(name.name.split(".")[0])

    def visit_ImportFrom(node):
        # if node.module is missing it's a "from . import ..." statement
        # if level > 0 it's a "from .submodule import ..." statement
        if node.module is not None and node.level == 0:
            if node.module:
                modules.add(node.module.split(".")[0])

    node_iter = ast.NodeVisitor()
    node_iter.visit_Import = visit_Import
    node_iter.visit_ImportFrom = visit_ImportFrom
    with open(script_file, "r") as f:
        node_iter.visit(ast.parse(f.read()))
    return modules


def get_vendored_dependencies(script_file: str) -> List:
    """Get all third part dependencies which are being in use in the setup.py

    :param script_file: Path to the setup.py
    :return: List with all vendored dependencies
    """
    all_std_modules = get_std_modules()
    all_modules_used = get_all_modules_imported_script(script_file)
    local_modules = get_local_modules(os.path.dirname(script_file))
    return [
        dep.lower()
        for dep in all_modules_used
        if dep not in local_modules and dep not in all_std_modules
    ]


@lru_cache(maxsize=20)
def get_local_modules(sdist_folder: str) -> List:
    result = []
    for py_file in glob(f"{sdist_folder}/*.py"):
        py_file = os.path.basename(py_file)
        if py_file == "setup.py":
            continue
        result.append(os.path.splitext(py_file)[0])
    return result


def origin_is_github(name_or_url: str) -> bool:
    return (
        name_or_url.startswith(("http://", "https://")) and "github.com" in name_or_url
    )  # lgtm [py/incomplete-url-substring-sanitization]


def sha256_checksum(filename, block_size=65536):
    sha256 = hashlib.sha256()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            sha256.update(block)
    return sha256.hexdigest()


def string_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def rm_duplicated_deps(all_requirements: Union[list, set, None]) -> Optional[list]:
    if not all_requirements:
        return None
    new_value = []
    for dep in all_requirements:
        if (
            dep in new_value
            or dep.replace("-", "_") in new_value
            or dep.replace("_", "-") in new_value
        ):
            continue
        new_value.append(dep)
    return new_value


def format_dependencies(all_dependencies: List, name: str) -> List:
    """Just format the given dependency to a string which is valid for the
    recipe

    :param all_dependencies: list of dependencies
    :param name: package name
    :return: list of dependencies formatted
    """
    formatted_dependencies = []
    re_deps = re.compile(r"^\s*([\.a-zA-Z0-9_-]+)\s*(.*)\s*$", re.MULTILINE | re.DOTALL)
    re_remove_space = re.compile(r"([<>!=]+)\s+")
    re_remove_tags = re.compile(r"\s*(\[.*\])", re.DOTALL)
    re_remove_comments = re.compile(r"\s+#.*", re.DOTALL)
    for req in all_dependencies:
        match_req = re_deps.match(req)
        deps_name = req
        if deps_name.replace("-", "_") == name.replace("-", "_"):
            continue
        if match_req:
            match_req = match_req.groups()
            deps_name = match_req[0]
            if len(match_req) > 1:
                deps_name = " ".join(match_req)
        deps_name = re_remove_space.sub(r"\1", deps_name.strip())
        deps_name = re_remove_tags.sub(r" ", deps_name.strip())
        deps_name = re_remove_comments.sub("", deps_name)
        formatted_dependencies.append(deps_name.strip())
    return formatted_dependencies


def populate_metadata_from_dict(metadata: Any, section: Section) -> Section:
    if not isinstance(metadata, bool) and not metadata:
        return section
    if isinstance(metadata, list):
        section.value = IngredientList(section.yaml)
        return section
    if isinstance(metadata, dict):
        for name, value in metadata.items():
            if isinstance(value, bool) or value:
                section.add_section({name: value})
    else:
        section.value = metadata
    return section


def generate_recipe(
    recipe,
    config,
    folder_path: Union[str, Path] = ".",
):
    """Write the recipe in a location. It will create a folder with the
    package name and the recipe will be there.

    :param folder_path: Path to the folder
    """
    pkg_name = config.name
    if origin_is_github(pkg_name):
        pkg_name = pkg_name.split("/")[-1]
    if Path(folder_path).is_file():
        folder_path = Path(folder_path)
        recipe_path = folder_path
        recipe_folder = folder_path.parent
    else:
        recipe_dir = Path(folder_path) / pkg_name
        logging.debug(f"Generating recipe on: {recipe_dir}")
        if not recipe_dir.is_dir():
            recipe_dir.mkdir()
        recipe_path = recipe_dir / "meta.yaml"
        recipe_folder = recipe_dir
        add_new_lines_after_section(recipe.yaml)

    clean_yaml(recipe)
    recipe.save(recipe_path)
    for file_to_recipe in config.files_to_copy:
        name = file_to_recipe.split(os.path.sep)[-1]
        if os.path.isfile(file_to_recipe):
            copyfile(file_to_recipe, os.path.join(recipe_folder, name))


def get_clean_yaml(recipe_yaml: CommentedMap) -> CommentedMap:
    clean_yaml(recipe_yaml)
    return add_new_lines_after_section(recipe_yaml)


def add_new_lines_after_section(recipe_yaml: CommentedMap) -> CommentedMap:
    for section in recipe_yaml.keys():
        if section == "package":
            recipe_yaml.yaml_set_comment_before_after_key(section, "\n\n")
        else:
            recipe_yaml.yaml_set_comment_before_after_key(section, "\n")
    return recipe_yaml


def clean_yaml(recipe):
    for key, yaml_obj in _clean_yaml(recipe):
        del yaml_obj[key]


def _clean_yaml(recipe, all_obj_to_delete=None):
    all_obj_to_delete = all_obj_to_delete or []
    for key, value in recipe.items():
        value_to_delete = []
        if not isinstance(value, bool) and not value:
            value_to_delete = [(key, recipe)]
        elif isinstance(value, Section):
            value_to_delete = _clean_yaml(value)
        all_obj_to_delete.extend(value_to_delete)
    return all_obj_to_delete
