import ast
import logging
import os
from copy import deepcopy
from functools import lru_cache
from glob import glob
from typing import List

import requests
from colorama import Fore, Style
from progressbar import ProgressBar

from grayskull.cli import WIDGET_BAR_DOWNLOAD

log = logging.getLogger(__name__)


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
    vendored_modules = []
    for dep in all_modules_used:
        if dep in local_modules or dep in all_std_modules:
            continue
        vendored_modules.append(dep.lower())
    return vendored_modules


def download_pkg(pkg_url: str, dest: str):
    """Download the given url and add a progressbar for it.

    :param pkg_url: package url
    :param dest: Folder were the function will download the package
    """
    name = pkg_url.split("/")[-1]
    print(
        f"{Fore.GREEN}Starting the download of the sdist package"
        f" {Fore.BLUE}{Style.BRIGHT}{name}"
    )
    log.debug(f"Downloading {name} sdist - {pkg_url}")
    response = requests.get(pkg_url, allow_redirects=True, stream=True, timeout=5)
    total_size = int(response.headers["Content-length"])

    with ProgressBar(
        widgets=deepcopy(WIDGET_BAR_DOWNLOAD), max_value=total_size, prefix=f"{name} ",
    ) as bar, open(dest, "wb") as pkg_file:
        progress_val = 0
        chunk_size = 512
        for chunk_data in response.iter_content(chunk_size=chunk_size):
            if chunk_data:
                pkg_file.write(chunk_data)
                progress_val += chunk_size
                bar.update(min(progress_val, total_size))


@lru_cache(maxsize=20)
def get_local_modules(sdist_folder: str) -> List:
    result = []
    for py_file in glob(f"{sdist_folder}/*.py"):
        py_file = os.path.basename(py_file)
        if py_file == "setup.py":
            continue
        result.append(os.path.splitext(py_file)[0])
    return result
