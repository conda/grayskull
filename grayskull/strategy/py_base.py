from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from collections import defaultdict
from contextlib import AbstractContextManager, contextmanager
from copy import deepcopy
from distutils import core
from glob import glob
from pathlib import Path
from subprocess import check_output
from tempfile import mkdtemp
from urllib.parse import urlparse

import requests
from colorama import Fore, Style
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_version
from packaging.version import Version
from pkginfo import UnpackedSDist

from grayskull.cli.stdout import manage_progressbar, print_msg
from grayskull.config import Configuration
from grayskull.license.discovery import ShortLicense, search_license_file
from grayskull.strategy.py_toml import get_all_toml_info
from grayskull.utils import (
    RE_PEP725_PURL,
    PyVer,
    get_vendored_dependencies,
    merge_dict_of_lists_item,
    merge_list_item,
    origin_is_github,
    sha256_checksum,
)

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

log = logging.getLogger(__name__)
RE_DEPS_NAME = re.compile(r"^\s*([\.a-zA-Z0-9_-]+)", re.MULTILINE)
PIN_PKG_COMPILER = {"numpy": "<{ pin_compatible('numpy') }}"}


def search_setup_root(path_folder: Path | str) -> Path:
    if setup_py := list(Path(path_folder).rglob("setup.py")):
        return setup_py[0]
    if setup_cfg := list(Path(path_folder).rglob("setup.cfg")):
        return setup_cfg[0]
    if pyproject_toml := list(Path(path_folder).rglob("pyproject.toml")):
        return pyproject_toml[0]


def clean_deps_for_conda_forge(list_deps: list, py_ver_min: PyVer) -> list:
    """Remove dependencies which conda-forge is not supporting anymore.
    For example Python 2.7, Python version less than 3.6"""
    re_delimiter = re.compile(r"#\s+\[py\s*(?:([<>=!]+))?\s*(\d+)\]\s*$", re.DOTALL)
    result_deps = []
    for dependency in list_deps:
        match_del = re_delimiter.search(dependency)
        if match_del is None:
            result_deps.append(dependency)
            continue

        match_del = match_del.groups()
        if not match_del[0]:
            match_del = ("==", match_del[1])
        major = int(match_del[1][0])
        minor = int(match_del[1][1:].replace("k", "0") or 0)
        py_ver_min = Version(f"{py_ver_min.major}.{py_ver_min.minor}")
        current_py = SpecifierSet(f"{match_del[0]}{major}.{minor}")
        log.debug(f"Evaluating: {py_ver_min}{match_del}{current_py} -- {dependency}")
        if py_ver_min in current_py:
            if Version(f"{major}.{minor}") in SpecifierSet(
                f"<{py_ver_min.major}.{py_ver_min.minor}"
            ):
                result_deps.append(dependency.split("#")[0].strip())
            else:
                result_deps.append(dependency)
    return result_deps


def pkg_name_from_sdist_url(sdist_url: str):
    """This method extracts and returns the name of the package from the sdist
    url."""
    if origin_is_github(sdist_url):
        return sdist_url.split("/")[-3] + ".tar.gz"
    else:
        return sdist_url.split("/")[-1]


def parse_extra_metadata_to_selector(option: str, operation: str, value: str) -> str:
    """Method tries to convert the extra metadata received into selectors

    :param option: option (extra, python_version, sys_platform)
    :param operation: (>, >=, <, <=, ==, !=)
    :param value: value after the operation
    :return: selector
    """
    if option == "extra":
        return ""
    if option == "python_version":
        value = value.split(".")
        value = "".join(value[:2])
        return f"py{operation}{value}"
    if option == "sys_platform":
        value = re.sub(r"[^a-zA-Z]+", "", value)
        if operation == "!=":
            return f"not {value.lower()}"
        return value.lower()
    if option == "platform_system":
        replace_val = {"windows": "win", "linux": "linux", "darwin": "osx"}
        value_lower = value.lower().strip()
        if value_lower in replace_val:
            value_lower = replace_val[value_lower]
        if operation == "!=":
            return f"not {value_lower}"
        return value_lower


def get_extra_from_requires_dist(string_parse: str) -> list:
    """Receives the extra metadata e parse it to get the option, operation
    and value.

    :param string_parse: metadata extra
    :return: return the option , operation and value of the extra metadata
    """
    return re.findall(
        r"(?:(\())?\s*([\.a-zA-Z0-9-_]+)\s*([=!<>]+)\s*[\'\"]*"
        r"([\.a-zA-Z0-9-_]+)[\'\"]*\s*(?:(\)))?\s*(?:(and|or))?",
        string_parse,
    )


def get_name_version_from_requires_dist(string_parse: str) -> tuple[str, str]:
    """Extract the name and the version from `requires_dist` present in
    PyPi`s metadata

    :param string_parse: requires_dist value from PyPi metadata
    :return: Name and version of a package
    """
    pkg = re.match(r"^\s*([^\s]+)\s*([\(]*.*[\)]*)?\s*", string_parse, re.DOTALL)
    pkg_name = pkg.group(1).strip()
    version = ""
    if len(pkg.groups()) > 1 and pkg.group(2):
        version = " " + pkg.group(2).strip()
    return pkg_name.strip(), re.sub(r"[\(\)]", "", version).strip()


def generic_py_ver_to(
    metadata: dict, config: Configuration, is_selector: bool = False
) -> str | None:  # sourcery no-metrics
    """Generic function which abstract the parse of the requires_python
    present in the PyPi metadata. Basically it can generate the selectors
    for Python or the constrained version if it is a `noarch: python` python package"""
    # TODO: Refactor the entire function to use LooseVersion instead of custom PyVer
    if not metadata.get("requires_python"):
        return None
    req_python = re.findall(
        r"([~><=!]+)\s*(\d+)(?:\.(\d+))?",
        metadata["requires_python"],
    )
    if not req_python:
        return None

    py_ver_enabled = config.get_py_version_available(req_python)
    small_py3_version = config.get_oldest_py3_version(
        [k for k, v in py_ver_enabled.items() if v]
    )
    all_py = list(py_ver_enabled.values())
    if all(all_py):
        return None
    if all(all_py if config.is_strict_cf else all_py[1:]):
        if is_selector:
            return None if config.is_strict_cf else "# [py2k]"
        else:
            return f">={small_py3_version.major}.{small_py3_version.minor}"
    if py_ver_enabled.get(PyVer(2, 7)) and any(all_py[1:]) is False:
        return "# [py3k]" if is_selector else "<3.0"

    for pos, py_ver in enumerate(py_ver_enabled):
        if py_ver == PyVer(2, 7):
            continue
        if all(all_py[pos:]) and any(all_py[:pos]) is False:
            if is_selector:
                minor = f"{py_ver.minor:02d}" if py_ver.major >= 4 else py_ver.minor
                return f"# [py<{py_ver.major}{minor}]"
            else:
                return f">={py_ver.major}.{py_ver.minor}"
        elif any(all_py[pos:]) is False:
            if is_selector:
                py2k = ""
                if not config.is_strict_cf and not all_py[0]:
                    py2k = " or py2k"
                minor = f"{py_ver.minor:02d}" if py_ver.major >= 4 else py_ver.minor
                return f"# [py>={py_ver.major}{minor}{py2k}]"
            else:
                py2 = ""
                if not all_py[0]:
                    py2 = f">={small_py3_version.major}.{small_py3_version.minor},"
                return f"{py2}<{py_ver.major}.{py_ver.minor}"

    all_selector = get_py_multiple_selectors(
        py_ver_enabled, is_selector=is_selector, config=config
    )
    if all_selector:
        return (
            "# [{}]".format(" or ".join(all_selector))
            if is_selector
            else ",".join(all_selector)
        )
    return None


def install_deps_if_necessary(setup_path: str, data_dist: dict, pip_dir: str):
    """Install missing dependencies to run the setup.py

    :param setup_path: path to the setup.py
    :param data_dist: metadata
    :param pip_dir: path where the missing packages will be downloaded
    """
    all_setup_deps = get_vendored_dependencies(setup_path)
    for dep in all_setup_deps:
        pip_install_dep(data_dist, dep, pip_dir)


def pip_install_dep(data_dist: dict, dep_name: str, pip_dir: str):
    """Install dependency using `pip`

    :param data_dist: sdist metadata
    :param dep_name: Package name which will be installed
    :param pip_dir: Path to the folder where `pip` will let the packages
    """
    if not data_dist.get("setup_requires"):
        data_dist["setup_requires"] = []
    if dep_name == "pkg_resources":
        dep_name = "setuptools"
    try:
        check_output(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                dep_name,
                f"--target={pip_dir}",
            ]
        )
    except Exception as err:
        log.error(
            f"It was not possible to install {dep_name}.\n"
            f"Command: pip install {dep_name} --target={pip_dir}.\n"
            f"Error: {err}"
        )
    else:
        if (
            dep_name.lower() not in data_dist["setup_requires"]
            and dep_name.lower() != "setuptools"
        ):
            data_dist["setup_requires"].append(dep_name.lower())


def merge_sdist_metadata(setup_py: dict, setup_cfg: dict) -> dict:
    """This method will merge the metadata present in the setup.py and
    setup.cfg. It is an auxiliary method.

    :param setup_py: Metadata from setup.py
    :param setup_cfg: Metadata from setup.cfg
    :return: Return the merged data from setup.py and setup.cfg
    """
    result = deepcopy(setup_py)
    for key, value in setup_cfg.items():
        if key not in result:
            result[key] = value

    merge_list_item(result, setup_cfg, "install_requires")
    merge_list_item(result, setup_cfg, "setup_requires")
    merge_list_item(result, setup_cfg, "compilers")
    merge_dict_of_lists_item(result, setup_cfg, "extras_require")

    if "setuptools-scm" in result.get("setup_requires", []):
        result["setup_requires"].remove("setuptools-scm")

    return result


def get_setup_cfg(source_path: str) -> dict:
    """Method responsible to extract the setup.cfg metadata

    :param source_path: Path to the folder where is located the sdist
     files unpacked
    :return: Metadata of setup.cfg
    """
    try:
        from setuptools.config.setupcfg import read_configuration
    except ImportError:
        from setuptools.config import read_configuration

    log.debug(f"Started setup.cfg from {source_path}")
    print_msg("Recovering metadata from setup.cfg")
    path_setup_cfg = list(Path(source_path).rglob("setup.cfg"))
    if not path_setup_cfg:
        return {}
    path_setup_cfg = path_setup_cfg[0]

    setup_cfg = read_configuration(str(path_setup_cfg))
    setup_cfg = dict(setup_cfg)
    if setup_cfg.get("options", {}).get("python_requires"):
        setup_cfg["options"]["python_requires"] = ensure_pep440(
            str(setup_cfg["options"]["python_requires"])
        )
    result = {}
    result.update(setup_cfg.get("options", {}))
    result.update(setup_cfg.get("metadata", {}))
    if result.get("build_ext"):
        result["compilers"] = ["c"]
    log.debug(f"Data recovered from setup.cfg: {result}")
    return result


@contextmanager
def injection_distutils(folder: str) -> AbstractContextManager[dict]:
    """This is a bit of "dark magic", please don't do it at home.
    It is injecting code in the distutils.core.setup and replacing the
    setup function by the inner function __fake_distutils_setup.
    This method is a contextmanager, after leaving the context it will return
    with the normal implementation of the distutils.core.setup.
    This method is necessary for two reasons:
    -pypi metadata for some packages might be absent from the pypi API.
    -pypi metadata, when present, might be missing some information.

    :param folder: Path to the folder where the sdist package was extracted
    :yield: return the metadata from sdist
    """
    from distutils import core

    setup_core_original = core.setup
    old_dir = os.getcwd()
    path_setup = search_setup_root(folder)
    os.chdir(os.path.dirname(str(path_setup)))

    data_dist = {}

    def __fake_distutils_setup(*args, **kwargs):
        if not isinstance(kwargs, dict) or not kwargs:
            return

        def _fix_list_requirements(key_deps: str) -> list:
            """Fix when dependencies have lists inside of another sequence"""
            val_deps = kwargs.get(key_deps)
            if not val_deps:
                return val_deps
            list_req = []
            if isinstance(val_deps, str):
                val_deps = [val_deps]
            for val in val_deps:
                if isinstance(val, tuple | list):
                    list_req.extend(list(map(str, val)))
                else:
                    list_req.append(str(val))
            return list_req

        if "setup_requires" in kwargs:
            kwargs["setup_requires"] = _fix_list_requirements("setup_requires")
        if "install_requires" in kwargs:
            kwargs["install_requires"] = _fix_list_requirements("install_requires")

        data_dist.update(kwargs)
        if not data_dist.get("setup_requires"):
            data_dist["setup_requires"] = []
        data_dist["setup_requires"] += (
            kwargs.get("setup_requires") if kwargs.get("setup_requires") else []
        )

        if "use_scm_version" in data_dist and kwargs["use_scm_version"]:
            log.debug("setuptools_scm found on setup.py")
            if "setuptools_scm" not in data_dist["setup_requires"]:
                data_dist["setup_requires"] += ["setuptools_scm"]
            if "setuptools-scm" in data_dist["setup_requires"]:
                data_dist["setup_requires"].remove("setuptools-scm")

        if kwargs.get("ext_modules", None):
            compilers = {"c"}
            for module in kwargs.get("ext_modules", []):
                if (getattr(module, "language", "") or "").lower() in {"c++", "cpp"}:
                    compilers.add("cxx")
                elif (
                    hasattr(module, "has_f2py_sources") and module.has_f2py_sources()
                ) or (getattr(module, "language", "") or "").lower() in (
                    "fortran",
                    "f77",
                    "f90",
                ):
                    compilers.add("fortran")
            data_dist["compilers"] = list(compilers)
        log.debug(f"Injection distutils all arguments: {kwargs}")
        if data_dist.get("run_py", False):
            del data_dist["run_py"]
            return
        setup_core_original(*args, **kwargs)

    try:
        core.setup = __fake_distutils_setup
        path_setup = str(path_setup)
        print_msg("Executing injected distutils...")
        __run_setup_py(path_setup, data_dist)
        if not data_dist or not data_dist.get("install_requires", None):
            print_msg(
                "No data was recovered from setup.py."
                " Forcing to execute the setup.py as script"
            )
            __run_setup_py(path_setup, data_dist, run_py=True)
        yield data_dist
    except BaseException as err:
        log.debug(f"Exception occurred when executing sdist injection: {err}")
        yield data_dist
    finally:
        core.setup = setup_core_original
        os.chdir(old_dir)


def __run_setup_py(path_setup: str, data_dist: dict, run_py=False, deps_installed=None):
    """Method responsible to run the setup.py

    :param path_setup: full path to the setup.py
    :param data_dist: metadata
    :param run_py: If it should run the setup.py with run_py, otherwise it will run
    invoking the distutils directly
    """
    deps_installed = deps_installed or []
    original_path = deepcopy(sys.path)
    pip_dir = mkdtemp(prefix="pip-dir-")
    if not os.path.exists(pip_dir):
        os.mkdir(pip_dir)
    if os.path.dirname(path_setup) not in sys.path:
        sys.path.append(os.path.dirname(path_setup))
        sys.path.append(pip_dir)
    install_deps_if_necessary(path_setup, data_dist, pip_dir)
    try:
        if run_py:
            import runpy

            data_dist["run_py"] = True
            runpy.run_path(path_setup, run_name="__main__")
        else:
            core.run_setup(path_setup, script_args=["install", f"--target={pip_dir}"])
    except ModuleNotFoundError as err:
        log.debug(
            f"When executing setup.py did not find the module: {err.name}."
            f" Exception: {err}"
        )
        dep_install = err.name
        if dep_install in deps_installed:
            dep_install = dep_install.split(".")[0]
        if dep_install not in deps_installed:
            deps_installed.append(dep_install)
            pip_install_dep(data_dist, dep_install, pip_dir)
            __run_setup_py(path_setup, data_dist, run_py, deps_installed=deps_installed)
    except Exception as err:
        log.debug(f"Exception when executing setup.py as script: {err}")
    data_dist.update(
        merge_sdist_metadata(data_dist, get_setup_cfg(os.path.dirname(str(path_setup))))
    )
    log.debug(f"Data recovered from setup.py: {data_dist}")
    if os.path.exists(pip_dir):
        shutil.rmtree(pip_dir)
    sys.path = original_path


def get_compilers(
    requires_dist: list, sdist_metadata: dict, config: Configuration
) -> list:
    """Return which compilers are necessary"""
    compilers = set(sdist_metadata.get("compilers", []))
    for pkg in requires_dist:
        pkg = RE_DEPS_NAME.match(pkg).group(0)
        pkg = pkg.lower().strip()
        if pkg.startswith("cython-") or pkg in config.pkg_need_c_compiler:
            compilers.add("c")
        if pkg in config.pkg_need_cxx_compiler:
            compilers.add("cxx")
    return list(compilers)


def get_py_multiple_selectors(
    selectors: dict[PyVer, bool],
    config: Configuration,
    is_selector: bool = False,
) -> list:
    """Get python selectors available.

    :param selectors: Dict with the Python version and if it is selected
    :param is_selector: if it needs to convert to selector or constrain python
    :param config: Configuration object
    :return: list with all selectors or constrained python
    """
    all_selector = []
    if not config.is_strict_cf and selectors[PyVer(2, 7)] is False:
        all_selector += (
            ["py2k"]
            if is_selector
            else config.get_oldest_py3_version(list(selectors.keys()))
        )
    for py_ver, is_enabled in selectors.items():
        if (not config.is_strict_cf and py_ver == PyVer(2, 7)) or is_enabled:
            continue
        all_selector += (
            [f"py=={py_ver.major}{py_ver.minor}"]
            if is_selector
            else [f"!={py_ver.major}.{py_ver.minor}"]
        )
    return all_selector


def py_version_to_selector(pypi_metadata: dict, config) -> str | None:
    return generic_py_ver_to(pypi_metadata, is_selector=True, config=config)


def py_version_to_limit_python(pypi_metadata: dict, config=None) -> str | None:
    config = config or Configuration(pypi_metadata["name"])
    result = generic_py_ver_to(pypi_metadata, is_selector=False, config=config)
    if not result and config.is_strict_cf:
        result = (
            f">={config.py_cf_supported[0].major}.{config.py_cf_supported[0].minor}"
        )
    return result


def update_requirements_with_pin(requirements: dict):
    """Get a dict with the `host`, `run` and `build` in it and replace
    if necessary the run requirements with the appropriated pin.

    :param requirements: Dict with the requirements in it
    """

    def is_compiler_present() -> bool:
        if "build" not in requirements:
            return False
        re_compiler = re.compile(
            r"^\s*[<{]\{\s*compiler\(['\"]\w+['\"]\)\s*\}\}\s*$", re.MULTILINE
        )
        return any(re_compiler.match(build) for build in requirements["build"])

    if not is_compiler_present():
        return

    def clean_list_pkg(pkg, list_pkgs):
        return [p for p in list_pkgs if pkg != p.strip().split(" ", 1)[0]]

    for pkg in requirements["host"]:
        pkg_name_match = RE_DEPS_NAME.match(pkg)
        if pkg_name_match:
            pkg_name = pkg_name_match.group(0)
            if pkg_name in PIN_PKG_COMPILER.keys():
                requirements["run"] = clean_list_pkg(pkg_name, requirements["run"])
                requirements["run"].append(PIN_PKG_COMPILER[pkg_name])


def discover_license(metadata: dict) -> list[ShortLicense]:
    """Based on the metadata this method will try to discover what is the
    right license for the package

    :param metadata: metadata
    :return: Return an object which contains relevant information regarding
    the license.
    """
    git_url = metadata.get("dev_url")
    project_url = metadata.get("project_urls", "") or metadata.get("project_url", "")
    if not git_url and urlparse(project_url).netloc == "github.com":
        git_url = project_url
    # "url" is always present but sometimes set to None
    if not git_url and urlparse(metadata.get("url") or "").netloc == "github.com":
        git_url = metadata.get("url")

    return search_license_file(
        metadata.get("sdist_path"),
        git_url,
        metadata.get("version"),
        license_name_metadata=metadata.get("license"),
    )


def get_test_entry_points(entry_points: list | str) -> list:
    if entry_points and isinstance(entry_points, str):
        entry_points = [entry_points]
    return [f"{ep.split('=')[0].strip()} --help" for ep in entry_points]


def get_test_imports(metadata: dict, default: str | None = None) -> list:
    if default:
        default = default.replace("-", "_")
    if "packages" not in metadata or not metadata["packages"]:
        return [default]
    meta_pkg = metadata["packages"]
    if isinstance(meta_pkg, str):
        meta_pkg = [metadata["packages"]]
    result = []
    for module in sorted(meta_pkg):
        if "/" in module or "." in module or module.startswith("_"):
            continue
        if module in ["test", "tests"]:
            log.warning(
                f"The package wrongfully added the test folder as a module ({module}),"
                f" as a result that might result in conda clobber warnings."
            )
            continue
        result.append(module)
    if not result:
        return [impt.replace("/", ".") for impt in sorted(meta_pkg)[:2]]
    return result


def get_entry_points_from_sdist(sdist_metadata: dict) -> list:
    """Extract entry points from sdist metadata

    :param sdist_metadata: sdist metadata
    :return: list with all entry points
    """
    all_entry_points = sdist_metadata.get("entry_points", {})
    if not all_entry_points:
        return []
    if isinstance(all_entry_points, str):
        all_lines = []
        for line in all_entry_points.splitlines():
            if "=" not in line:
                all_lines.append(line)
                continue
            all_parts = [line_col.strip() for line_col in line.split("=")]
            if not all_parts[-1].startswith(("'", '"')):
                all_parts[-1] = f"'{all_parts[-1]}'"
            all_lines.append("=".join(all_parts))
        try:
            all_entry_points = tomllib.loads("\n".join(all_lines))
        except tomllib.TOMLDecoderError:
            return []

    if all_entry_points.get("console_scripts") or all_entry_points.get("gui_scripts"):
        console_scripts = all_entry_points.get("console_scripts", [])
        if isinstance(console_scripts, dict):
            console_scripts = [
                f"{k} = {v}" for k, v in all_entry_points["console_scripts"].items()
            ]

        gui_scripts = all_entry_points.get("gui_scripts", [])
        if isinstance(gui_scripts, dict):
            gui_scripts = [
                f"{k} = {v}" for k, v in all_entry_points["gui_scripts"].items()
            ]

        entry_points_result = []
        if console_scripts:
            if isinstance(console_scripts, str):
                console_scripts = [console_scripts]
            entry_points_result += console_scripts
        if gui_scripts:
            if isinstance(gui_scripts, str):
                gui_scripts = [gui_scripts]
            entry_points_result += gui_scripts
        return_entry_point = []
        for entry_point in entry_points_result:
            if isinstance(entry_point, str):
                entry_point = entry_point.split("\n")
            return_entry_point.extend(entry_point)
        return [ep for ep in return_entry_point if ep.strip()]
    return []


def download_sdist_pkg(sdist_url: str, dest: str, name: str | None = None):
    """Download the sdist package

    :param sdist_url: sdist url
    :param dest: Folder were the method will download the sdist
    """
    print_msg(
        f"{Fore.GREEN}Starting the download of the sdist package"
        f" {Fore.BLUE}{Style.BRIGHT}{name}"
    )
    log.debug(f"Downloading {name} sdist - {sdist_url}")
    response = requests.get(sdist_url, allow_redirects=True, stream=True, timeout=5)
    response.raise_for_status()
    total_size = int(response.headers.get("Content-length", 0))
    with manage_progressbar(max_value=total_size, prefix=f"{name} ") as bar:
        with open(dest, "wb") as pkg_file:
            progress_val = 0
            chunk_size = 512
            for chunk_data in response.iter_content(chunk_size=chunk_size):
                if chunk_data:
                    pkg_file.write(chunk_data)
                    progress_val += chunk_size
                    bar.update(min(progress_val, total_size))


def merge_deps_toml_setup(setup_deps: list, toml_deps: list) -> list:
    re_split = re.compile(r"\s+|>|=|<|~|!")
    # drop any empty deps
    setup_deps = [dep for dep in setup_deps if dep.strip()]
    toml_deps = [dep for dep in toml_deps if dep.strip()]

    # get dep names
    toml_dep_names = [re_split.split(dep)[0] for dep in toml_deps]
    setup_dep_names = [re_split.split(dep)[0] for dep in setup_deps]

    # prefer toml over setup; only add setup deps if not found in toml
    merged_deps = toml_deps
    for dep_name, dep in zip(setup_dep_names, setup_deps):
        if not dep_name.strip():
            continue
        alternatives = [
            dep_name,
            dep_name.replace("_", "-"),
            dep_name.replace("-", "_"),
        ]
        found = any([alternative in toml_dep_names for alternative in alternatives])
        # only add the setup dep if no alternative name was found
        if not found:
            merged_deps.append(dep)

    return merged_deps


def merge_setup_toml_metadata(setup_metadata: dict, pyproject_metadata: dict) -> dict:
    setup_metadata = defaultdict(dict, setup_metadata)
    if not pyproject_metadata:
        return setup_metadata
    setup_metadata["name"] = setup_metadata.get("name") or pyproject_metadata["name"]
    if pyproject_metadata["about"]["license"]:
        setup_metadata["license"] = pyproject_metadata["about"]["license"]
    if pyproject_metadata["about"]["summary"]:
        setup_metadata["summary"] = pyproject_metadata["about"]["summary"]
    if pyproject_metadata["about"]["home"]:
        setup_metadata["projects_url"]["Homepage"] = pyproject_metadata["about"]["home"]
    if pyproject_metadata["build"]["entry_points"]:
        setup_metadata["entry_points"]["console_scripts"] = pyproject_metadata["build"][
            "entry_points"
        ]
    if pyproject_metadata["requirements"]["host"]:
        setup_metadata["setup_requires"] = merge_deps_toml_setup(
            setup_metadata.get("setup_requires", []),
            pyproject_metadata["requirements"]["host"],
        )
    if pyproject_metadata["requirements"]["run"]:
        setup_metadata["install_requires"] = merge_deps_toml_setup(
            setup_metadata.get("install_requires", []),
            pyproject_metadata["requirements"]["run"],
        )
    for extra_name, extra_requirements in pyproject_metadata["requirements"][
        "extra"
    ].items():
        setup_metadata["extras_require"][extra_name] = merge_deps_toml_setup(
            setup_metadata["extras_require"].get(extra_name, []),
            extra_requirements,
        )
    # this is not a valid setup_metadata field, but we abuse it to pass it
    # through to the conda recipe generator downstream. It's because setup.py
    # does not have a notion of build vs. host requirements. It only has
    # equivalents to host and run.
    if pyproject_metadata["requirements"]["build"]:
        setup_metadata["__build_requirements_placeholder"] = pyproject_metadata[
            "requirements"
        ]["build"]
    if pyproject_metadata["requirements"]["run_constrained"]:
        setup_metadata["requirements_run_constrained"] = pyproject_metadata[
            "requirements"
        ]["run_constrained"]
    return setup_metadata


def get_sdist_metadata(
    sdist_url: str, config: Configuration, with_source: bool = False
) -> dict:
    """Method responsible to return the sdist metadata which is basically
    the metadata present in setup.py and setup.cfg or PKG-INFO
    :param sdist_url: URL to the sdist package
    :param config: package configuration
    :param with_source: a boolean value to indicate Github packages
    :return: sdist metadata
    """
    temp_folder = mkdtemp(prefix=f"grayskull-{config.name}-")
    if config.from_local_sdist:
        path_pkg = Path(config.local_sdist).resolve()
    else:
        pkg_name = pkg_name_from_sdist_url(sdist_url)
        path_pkg = os.path.join(temp_folder, pkg_name)

        download_sdist_pkg(sdist_url=sdist_url, dest=path_pkg, name=config.name)
        if config.download:
            config.files_to_copy.append(path_pkg)
    log.debug(f"Unpacking {path_pkg} to {temp_folder}")
    shutil.unpack_archive(path_pkg, temp_folder)

    print_msg("Checking for pyproject.toml")
    pyproject_toml = glob(f"{temp_folder}/**/pyproject.toml", recursive=True)
    pyproject_metadata = {}
    if pyproject_toml:
        pyproject_toml = Path(pyproject_toml[0])
        print_msg(f"pyproject.toml found in {pyproject_toml}")
        pyproject_metadata = get_all_toml_info(pyproject_toml)
    else:
        print_msg("pyproject.toml not found.")

    print_msg("Recovering information from setup.py")
    with injection_distutils(temp_folder) as metadata:
        metadata["sdist_path"] = temp_folder

    # At this point the tarball was successfully extracted
    # so we can assume the sha256 can be computed reliably
    if with_source:
        metadata["source"] = {"url": sdist_url, "sha256": sha256_checksum(path_pkg)}
    if config.from_local_sdist:
        metadata["source"] = {
            "url": Path(path_pkg).as_uri(),
            "sha256": sha256_checksum(path_pkg),
        }

    # Get some keys from PKG-INFO
    path_pkg_info = list(Path(temp_folder).rglob("PKG-INFO"))
    if path_pkg_info:
        dist = UnpackedSDist(path_pkg_info[0].parent)
        for key in ("name", "version", "summary", "author"):
            metadata[key] = getattr(dist, key, None)

    # "packages" refer to the modules you can import
    # That might be different from the distribution name (PKG-INFO name)
    # packages can be retrieved from setup.py but is usually not defined
    # in pyproject.toml
    # For setuptools, it is possible to get it from top_level.txt
    if "packages" not in metadata or not metadata["packages"]:
        top_level = list(Path(temp_folder).rglob("*.egg-info/top_level.txt"))
        if top_level:
            metadata["packages"] = top_level[0].read_text().split()

    return merge_setup_toml_metadata(metadata, pyproject_metadata)


def ensure_pep440_in_req_list(list_req: list[str]) -> list[str]:
    return [ensure_pep440(pkg) for pkg in list_req]


def split_deps(deps: str) -> list[str]:
    result = []
    for d in deps.split(","):
        constrain = ""
        for val in re.split(r"([><!=~^]+)", d):
            if not val:
                continue
            if {">", "<", "=", "!", "~", "^"} & set(val):
                constrain = val.strip()
            else:
                result.append(f"{constrain}{val.strip()}")
    return result


def ensure_pep440(pkg: str | None) -> str | None:
    if not pkg or RE_PEP725_PURL.match(pkg):
        return pkg
    pkg = pkg.strip()
    if any([pkg.startswith(pattern) for pattern in ("<{", "{{")]):
        return pkg
    split_pkg = pkg.strip().split(" ")
    if len(split_pkg) <= 1:
        return pkg
    selector = ""
    if "#" in split_pkg:
        hash_index = split_pkg.index("#")
        selector = f"  {' '.join(split_pkg[hash_index:])}"
        split_pkg = split_pkg[:hash_index]
    constrain_pkg = "".join(split_pkg[1:])
    list_constrains = split_deps(constrain_pkg)
    full_constrain = []
    for constrain in list_constrains:
        if "~=" in constrain:
            version = constrain.strip().replace("~=", "").strip()
            version_upper = next_incompatible_version(version)
            full_constrain.append(f">={version},<{version_upper}")
        else:
            full_constrain.append(constrain.strip())
    all_constrains = ",".join(full_constrain)
    return f"{split_pkg[0]} {all_constrains}{selector}"


def next_incompatible_version(version: str) -> str:
    """Return the next incompatible version for the given version."""
    comments_removed = version.split("#")[0]
    version_ = Version(comments_removed)
    epoch = version_.epoch
    previous_release = version_.release
    if len(previous_release) < 2:
        raise ValueError(
            f"~= operator requires at least two version numbers, but given only "
            f"'{version}'"
        )
    release = previous_release[:-2] + (previous_release[-2] + 1,)
    release_str = ".".join(str(r) for r in release)
    return canonicalize_version(f"{epoch}!{release_str}dev")
