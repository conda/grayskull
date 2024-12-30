import ast
import hashlib
import logging
import os
import re
from collections import defaultdict, namedtuple
from difflib import SequenceMatcher
from functools import lru_cache
from glob import glob
from pathlib import Path
from shutil import copyfile
from typing import Final

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from souschef.recipe import Recipe
from souschef.section import Section

log = logging.getLogger(__name__)

PyVer = namedtuple("PyVer", ["major", "minor"])
yaml = YAML(typ="jinja2")
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.width = 600


#  PURL fields               scheme      type           name
RE_PEP725_PURL = re.compile(r"[a-z]+\:[\.a-z0-9_-]+\/[\.a-z0-9_-]+", re.IGNORECASE)


@lru_cache(maxsize=10)
def get_std_modules() -> list:
    from stdlib_list import stdlib_list

    all_libs = set()
    for py_ver in (
        "2.7",
        "3.6",
        "3.7",
        "3.8",
    ):
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
        if node.module is not None and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])

    node_iter = ast.NodeVisitor()
    node_iter.visit_Import = visit_Import
    node_iter.visit_ImportFrom = visit_ImportFrom
    with open(script_file) as f:
        node_iter.visit(ast.parse(f.read()))
    return modules


def get_vendored_dependencies(script_file: str) -> list:
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
def get_local_modules(sdist_folder: str) -> list:
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
    )


def origin_is_local_sdist(name: str) -> bool:
    """Return True if the given local file can be a sdist"""
    # Available formats according to
    # https://docs.python.org/3/distutils/sourcedist.html#creating-a-source-distribution
    return (
        name.endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tar.Z", ".tar", ".zip"))
        and Path(name).is_file()
    )


def sha256_checksum(filename, block_size=65536):
    sha256 = hashlib.sha256()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(block_size), b""):
            sha256.update(block)
    return sha256.hexdigest()


def string_similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def rm_duplicated_deps(all_requirements: list | set | None) -> list | None:
    if not all_requirements:
        return None
    # Keep track of requirements which have already been added to the list.
    # The key is a canonicalized version of the requirement: lowercase,
    # and underscores converted to dashes. The value is the requirement itself,
    # as it should be added.
    # (This is order-preserving since dicts are ordered by first insertion.)
    new_reqs: dict[tuple[str, str], str] = {}
    re_split = re.compile(r"\s+(|>|=|<|~|!|#)+")
    for dep in all_requirements:
        if dep.strip().startswith(("{{", "<{")):
            new_reqs[dep] = dep
            continue
        dep_name, *constrains = re_split.split(dep.strip())
        dep_name = dep_name.strip()

        if "#" in dep:
            selector = dep.split("#")[-1]
        else:
            selector = ""

        constrains = [
            c.strip()
            for c in constrains
            if c.strip() not in {"=*", "==*", "*", "*.*", "*.*.*", ""}
        ]
        canonicalized = dep_name.replace("_", "-").lower()
        constrains.insert(0, dep_name)
        # a canonicalized dependency is only redundant if it also has the same
        # selector as a pervious dependency
        key = (canonicalized, selector)
        if key in new_reqs:
            # In order to break ties deterministically, we prioritize the requirement
            # which is alphanumerically lowest. This happens to prioritize the "-"
            # character over "_".
            # Example: given "importlib_metadata" and "importlib-metadata", we will
            # keep "importlib-metadata" because it is alphabetically lower.
            previous_req = new_reqs[key]
            if len(dep) > len(previous_req) or "-" in dep_name:
                new_reqs[key] = " ".join(constrains)
        else:
            new_reqs[key] = " ".join(constrains)
    return [re.sub(r"\s+(#)", "  \\1", v.strip()) for v in new_reqs.values()]


def format_dependencies(all_dependencies: list, name: str) -> list:
    """Just format the given dependency to a string which is valid for the
    recipe

    :param all_dependencies: list of dependencies
    :param name: package name
    :return: list of dependencies formatted
    """
    formatted_dependencies = []
    re_deps = re.compile(r"^\s*([\.a-zA-Z0-9_-]+)\s*(.*)\s*$", re.MULTILINE | re.DOTALL)
    re_remove_space = re.compile(r"([<>!=]+)\s+")
    re_selector = re.compile(r"\s+#\s+\[.*\]", re.DOTALL)
    re_remove_tags = re.compile(r"\s*(\[.*\])", re.DOTALL)
    re_remove_comments = re.compile(r"\s+#.*", re.DOTALL)
    for req in all_dependencies:
        if RE_PEP725_PURL.match(req):
            formatted_dependencies.append(req)
            continue
        match_req = re_deps.match(req)
        deps_name = req
        if name is not None and deps_name.replace("-", "_") == name.replace("-", "_"):
            continue
        if match_req:
            match_req = match_req.groups()
            deps_name = match_req[0]
            if len(match_req) > 1:
                deps_name = " ".join(match_req)
        deps_name = re_remove_space.sub(r"\1", deps_name.strip())
        if re_selector.search(deps_name):
            # don't want to remove selectors
            formatted_dependencies.append(deps_name)
            continue
        deps_name = re_remove_tags.sub(r" ", deps_name.strip())
        deps_name = re_remove_comments.sub("", deps_name)
        formatted_dependencies.append(deps_name.strip())
    return formatted_dependencies


def generate_recipe(
    recipe: Recipe,
    config,
    folder_path: str | Path = ".",
    use_v1_format: bool = False,
):
    """Write the recipe in a location. It will create a folder with the
    package name and the recipe will be there.

    :param folder_path: Path to the folder
    :param use_v1_format: If set to True, return a recipe in the V1 format
    """
    if recipe["package"]["name"].value.startswith("r-{{"):
        pkg_name = f"r-{config.name}"
    else:
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
        recipe_path = (
            recipe_dir / "recipe.yaml" if use_v1_format else recipe_dir / "meta.yaml"
        )
        recipe_folder = recipe_dir
        add_new_lines_after_section(recipe.yaml)

    clean_yaml(recipe)
    recipe.save(recipe_path)
    if use_v1_format:
        upgrade_v0_recipe_to_v1(recipe_path)
    for file_to_recipe in config.files_to_copy:
        name = file_to_recipe.split(os.path.sep)[-1]
        if os.path.isfile(file_to_recipe):
            copyfile(file_to_recipe, os.path.join(recipe_folder, name))


def upgrade_v0_recipe_to_v1(recipe_path: Path) -> None:
    """
    Takes a V0 (pre CEP-13) recipe and converts it to a V1 (post CEP-13) recipe file.
    Upgraded recipes are saved to the provided file path.

    NOTE: As of writing, we need ruamel to dump the text to a file first so we can
          get the original recipe file as a string. This is a workaround until we
          can get ruamel to dump to a string stream without blowing up on the
          JINJA plugin.
    :param recipe_path: Path to that contains the original recipe file to modify.
    """
    try:
        from conda_recipe_manager.parser.recipe_parser_convert import (
            RecipeParserConvert,
        )
    except ImportError as e:
        raise ImportError(
            "Please install conda-recipe-manager from conda-forge to enable "
            "support for the V1 format. (Note that Python >=3.11 is required.)"
        ) from e

    recipe_content: Final[str] = RecipeParserConvert.pre_process_recipe_text(
        recipe_path.read_text()
    )
    recipe_converter = RecipeParserConvert(recipe_content)
    v1_content, _, _ = recipe_converter.render_to_v1_recipe_format()
    recipe_path.write_text(v1_content, encoding="utf-8")


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


def merge_list_item(destination: dict, add: dict, key: str) -> None:
    """Modify the list 'destination[key]' to include missing elements from 'add[key]'.

    Duplicated elements are removed. The order of the elements is preserved.
    In case 'key' is undefined or empty in both lists, 'destination' is unmodified.
    """
    result = []
    destination_list = destination.get(key, [])
    add_list = add.get(key, [])
    for item in destination_list + add_list:
        if item not in result:
            result.append(item)
    if len(result) > 0:
        destination[key] = result


def merge_dict_of_lists_item(destination: dict, add: dict, key: str) -> None:
    sub_destination = destination.get(key, {})
    sub_add = add.get(key, {})
    for sub_key in set(sub_destination) | set(sub_add):
        merge_list_item(sub_destination, sub_add, sub_key)
    if sub_destination:
        destination[key] = sub_destination


def nested_dict():
    return defaultdict(nested_dict)
