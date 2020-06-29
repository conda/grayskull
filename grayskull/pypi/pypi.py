import json
import logging
import os
import re
import shutil
import sys
import traceback
from collections import namedtuple
from contextlib import contextmanager
from copy import deepcopy
from distutils import core
from functools import lru_cache
from pathlib import Path
from subprocess import check_output
from tempfile import mkdtemp
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

import requests
from colorama import Fore, Style

from grayskull.base.base_recipe import AbstractRecipeModel
from grayskull.base.pkg_info import is_pkg_available
from grayskull.base.track_packages import solve_list_pkg_name
from grayskull.cli.stdout import (
    manage_progressbar,
    print_msg,
    print_requirements,
    progressbar_with_status,
)
from grayskull.license.discovery import ShortLicense, search_license_file
from grayskull.utils import get_vendored_dependencies

log = logging.getLogger(__name__)
PyVer = namedtuple("PyVer", ["major", "minor"])
SUPPORTED_PY = sorted([PyVer(2, 7), PyVer(3, 6), PyVer(3, 7), PyVer(3, 8)])


class PyPi(AbstractRecipeModel):
    URL_PYPI_METADATA = "https://pypi.org/pypi/{pkg_name}/json"
    PKG_NEEDS_C_COMPILER = ("cython",)
    PKG_NEEDS_CXX_COMPILER = ("pybind11",)
    RE_DEPS_NAME = re.compile(r"^\s*([\.a-zA-Z0-9_-]+)", re.MULTILINE)
    PIN_PKG_COMPILER = {"numpy": "<{ pin_compatible('numpy') }}"}
    PYPI_CONFIG = Path(os.path.dirname(__file__)) / "config.yaml"

    def __init__(
        self,
        name: Optional[str] = None,
        version: Optional[str] = None,
        download: bool = False,
    ):
        self._download = download
        self._setup_metadata = None
        self._is_arch = False
        super(PyPi, self).__init__(name=name, version=version)
        self["build"]["script"] = "<{ PYTHON }} -m pip install . -vv"

    @staticmethod
    def _download_sdist_pkg(sdist_url: str, dest: str):
        """Download the sdist package

        :param sdist_url: sdist url
        :param dest: Folder were the method will download the sdist
        """
        name = sdist_url.split("/")[-1]
        print_msg(
            f"{Fore.GREEN}Starting the download of the sdist package"
            f" {Fore.BLUE}{Style.BRIGHT}{name}"
        )
        log.debug(f"Downloading {name} sdist - {sdist_url}")
        response = requests.get(sdist_url, allow_redirects=True, stream=True, timeout=5)
        total_size = int(response.headers["Content-length"])

        with manage_progressbar(max_value=total_size, prefix=f"{name} ") as bar, open(
            dest, "wb"
        ) as pkg_file:
            progress_val = 0
            chunk_size = 512
            for chunk_data in response.iter_content(chunk_size=chunk_size):
                if chunk_data:
                    pkg_file.write(chunk_data)
                    progress_val += chunk_size
                    bar.update(min(progress_val, total_size))

    @lru_cache(maxsize=10)
    def _get_sdist_metadata(self, sdist_url: str, name: str) -> dict:
        """Method responsible to return the sdist metadata which is basically
        the metadata present in setup.py and setup.cfg

        :param sdist_url: URL to the sdist package
        :param name: name of the package
        :return: sdist metadata
        """
        temp_folder = mkdtemp(prefix=f"grayskull-{name}-")
        pkg_name = sdist_url.split("/")[-1]
        path_pkg = os.path.join(temp_folder, pkg_name)

        PyPi._download_sdist_pkg(sdist_url=sdist_url, dest=path_pkg)
        if self._download:
            self.files_to_copy.append(path_pkg)
        log.debug(f"Unpacking {path_pkg} to {temp_folder}")
        shutil.unpack_archive(path_pkg, temp_folder)
        print_msg("Recovering information from setup.py")
        with PyPi._injection_distutils(temp_folder) as metadata:
            metadata["sdist_path"] = temp_folder
            return metadata

    @staticmethod
    def _merge_sdist_metadata(setup_py: dict, setup_cfg: dict) -> dict:
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

        def get_full_list(key: str) -> List:
            if key not in setup_py:
                return setup_cfg.get(key, [])
            cfg_val = set(setup_cfg.get(key, []))
            result_val = set(result.get(key, []))
            return list(cfg_val.union(result_val))

        if "install_requires" in result:
            result["install_requires"] = get_full_list("install_requires")
        if "extras_require" in result:
            result["extras_require"] = get_full_list("extras_require")
        if "setup_requires" in result:
            result["setup_requires"] = get_full_list("setup_requires")
            if "setuptools-scm" in result["setup_requires"]:
                result["setup_requires"].remove("setuptools-scm")
        if "compilers" in result:
            result["compilers"] = get_full_list("compilers")
        return result

    @staticmethod
    def __rm_duplicated_deps(
        all_requirements: Union[list, set, None]
    ) -> Optional[list]:
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

    @staticmethod
    def _get_setup_cfg(source_path: str) -> dict:
        """Method responsible to extract the setup.cfg metadata

        :param source_path: Path to the folder where is located the sdist
         files unpacked
        :return: Metadata of setup.cfg
        """
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
            setup_cfg["options"]["python_requires"] = str(
                setup_cfg["options"]["python_requires"]
            )
        result = {}
        result.update(setup_cfg.get("options", {}))
        result.update(setup_cfg.get("metadata", {}))
        if result.get("build_ext"):
            result["compilers"] = ["c"]
        log.debug(f"Data recovered from setup.cfg: {result}")
        return result

    @staticmethod
    @contextmanager
    def _injection_distutils(folder: str) -> dict:
        """This is a bit of "dark magic", please don't do it at home.
        It is injecting code in the distutils.core.setup and replacing the
        setup function by the inner function __fake_distutils_setup.
        This method is a contextmanager, after leaving the context it will return
        with the normal implementation of the distutils.core.setup.
        This method is necessary because some information are missing from the
        pypi metadata and also for those packages which the pypi metadata is missing.

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

            def _fix_list_requirements(key_deps: str) -> List:
                """Fix when dependencies have lists inside of another sequence"""
                if not kwargs.get(key_deps):
                    return kwargs.get(key_deps)
                list_req = []
                for val in kwargs.get(key_deps):
                    if isinstance(val, (tuple, list)):
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
                data_dist["compilers"] = ["c"]
                if len(kwargs["ext_modules"]) > 0:
                    for ext_mod in kwargs["ext_modules"]:
                        if (
                            hasattr(ext_mod, "has_f2py_sources")
                            and ext_mod.has_f2py_sources()
                        ):
                            data_dist["compilers"].append("fortran")
                            break
            log.debug(f"Injection distutils all arguments: {kwargs}")
            if data_dist.get("run_py", False):
                del data_dist["run_py"]
                return
            setup_core_original(*args, **kwargs)

        try:
            core.setup = __fake_distutils_setup
            path_setup = str(path_setup)
            print_msg("Executing injected distutils...")
            PyPi.__run_setup_py(path_setup, data_dist)
            if not data_dist or not data_dist.get("install_requires", None):
                print_msg(
                    "No data was recovered from setup.py."
                    " Forcing to execute the setup.py as script"
                )
                PyPi.__run_setup_py(path_setup, data_dist, run_py=True)
            yield data_dist
        except:  # noqa
            log.debug(
                "Exception occurred when executing sdist injection:"
                f" {traceback.format_exc()}"
            )
            yield data_dist
        finally:
            core.setup = setup_core_original
            os.chdir(old_dir)

    @staticmethod
    def __run_setup_py(
        path_setup: str, data_dist: dict, run_py=False, deps_installed=None
    ):
        """Method responsible to run the setup.py

        :param path_setup: full path to the setup.py
        :param data_dist: metadata
        :param run_py: If it should run the setup.py with run_py, otherwise it will run
        invoking the distutils directly
        """
        deps_installed = deps_installed if deps_installed else []
        original_path = deepcopy(sys.path)
        pip_dir = mkdtemp(prefix="pip-dir-")
        if not os.path.exists(pip_dir):
            os.mkdir(pip_dir)
        if os.path.dirname(path_setup) not in sys.path:
            sys.path.append(os.path.dirname(path_setup))
            sys.path.append(pip_dir)
        PyPi._install_deps_if_necessary(path_setup, data_dist, pip_dir)
        try:
            if run_py:
                import runpy

                data_dist["run_py"] = True
                runpy.run_path(path_setup, run_name="__main__")
            else:
                core.run_setup(
                    path_setup, script_args=["install", f"--target={pip_dir}"]
                )
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
                PyPi._pip_install_dep(data_dist, dep_install, pip_dir)
                PyPi.__run_setup_py(
                    path_setup, data_dist, run_py, deps_installed=deps_installed
                )
        except Exception as err:
            log.debug(f"Exception when executing setup.py as script: {err}")
        data_dist.update(
            PyPi._merge_sdist_metadata(
                data_dist, PyPi._get_setup_cfg(os.path.dirname(str(path_setup)))
            )
        )
        log.debug(f"Data recovered from setup.py: {data_dist}")
        if os.path.exists(pip_dir):
            shutil.rmtree(pip_dir)
        sys.path = original_path

    @staticmethod
    def _install_deps_if_necessary(setup_path: str, data_dist: dict, pip_dir: str):
        """Install missing dependencies to run the setup.py

        :param setup_path: path to the setup.py
        :param data_dist: metadata
        :param pip_dir: path where the missing packages will be downloaded
        """
        all_setup_deps = get_vendored_dependencies(setup_path)
        for dep in all_setup_deps:
            PyPi._pip_install_dep(data_dist, dep, pip_dir)

    @staticmethod
    def _pip_install_dep(data_dist: dict, dep_name: str, pip_dir: str):
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
            check_output(["pip", "install", dep_name, f"--target={pip_dir}"])
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

    @staticmethod
    def _merge_pypi_sdist_metadata(pypi_metadata: dict, sdist_metadata: dict) -> dict:
        """This method is responsible to merge two dictionaries and it will give
        priority to the pypi_metadata.

        :param pypi_metadata: PyPI metadata
        :param sdist_metadata: Metadata which comes from the ``setup.py``
        :return: A new dict with the result of the merge
        """

        def get_val(key):
            return pypi_metadata.get(key) or sdist_metadata.get(key)

        requires_dist = PyPi._merge_requires_dist(pypi_metadata, sdist_metadata)
        all_packages_names = get_val("packages")
        if not all_packages_names:
            all_packages_names = get_val("py_modules")
        return {
            "author": get_val("author"),
            "name": get_val("name"),
            "version": get_val("version"),
            "source": pypi_metadata.get("source"),
            "packages": all_packages_names,
            "url": get_val("url"),
            "classifiers": get_val("classifiers"),
            "compilers": PyPi._get_compilers(requires_dist, sdist_metadata),
            "entry_points": PyPi._get_entry_points_from_sdist(sdist_metadata),
            "summary": get_val("summary"),
            "requires_python": pypi_metadata.get("requires_python")
            or sdist_metadata.get("python_requires"),
            "doc_url": get_val("doc_url"),
            "dev_url": get_val("dev_url"),
            "license": get_val("license"),
            "setup_requires": get_val("setup_requires"),
            "extra_requires": get_val("extra_requires"),
            "project_url": get_val("project_url"),
            "extras_require": get_val("extras_require"),
            "requires_dist": requires_dist,
            "sdist_path": get_val("sdist_path"),
        }

    @staticmethod
    def _get_compilers(requires_dist: List, sdist_metadata: dict) -> List:
        """Return which compilers are necessary

        :param requires_dist: Package requirements
        :param sdist_metadata: sdist metadata
        :return: List with all compilers found.
        """
        compilers = set(sdist_metadata.get("compilers", []))
        for pkg in requires_dist:
            pkg = PyPi.RE_DEPS_NAME.match(pkg).group(0)
            pkg = pkg.lower().strip()
            if pkg.strip() in PyPi.PKG_NEEDS_C_COMPILER:
                compilers.add("c")
            if pkg.strip() in PyPi.PKG_NEEDS_CXX_COMPILER:
                compilers.add("cxx")
        return list(compilers)

    @staticmethod
    def _get_entry_points_from_sdist(sdist_metadata: dict) -> List:
        """Extract entry points from sdist metadata

        :param sdist_metadata: sdist metadata
        :return: list with all entry points
        """
        all_entry_points = sdist_metadata.get("entry_points", {})
        if isinstance(all_entry_points, str) or not all_entry_points:
            return []
        if all_entry_points.get("console_scripts") or all_entry_points.get(
            "gui_scripts"
        ):
            console_scripts = all_entry_points.get("console_scripts", [])
            gui_scripts = all_entry_points.get("gui_scripts", [])
            entry_points_result = []
            if console_scripts:
                if isinstance(console_scripts, str):
                    console_scripts = [console_scripts]
                entry_points_result += console_scripts
            if gui_scripts:
                if isinstance(gui_scripts, str):
                    gui_scripts = [gui_scripts]
                entry_points_result += gui_scripts
            return entry_points_result
        return []

    @staticmethod
    def _merge_requires_dist(pypi_metadata: dict, sdist_metadata: dict) -> List:
        """Merge requirements metadata from pypi and sdist.

        :param pypi_metadata: pypi metadata
        :param sdist_metadata: sdist metadata
        :return: list with all requirements
        """
        all_deps = []
        if sdist_metadata.get("install_requires"):
            all_deps += sdist_metadata.get("install_requires", [])
        if pypi_metadata.get("requires_dist"):
            all_deps += pypi_metadata.get("requires_dist", [])

        re_search = re.compile(r";\s*extra")
        all_deps = [pkg for pkg in all_deps if not re_search.search(pkg)]
        current_pkg = pypi_metadata.get("name", "")

        requires_dist = []
        pypi_deps_name = set()
        with progressbar_with_status(len(all_deps)) as bar:
            for pos, sdist_pkg in enumerate(all_deps, 1):
                match_deps = PyPi.RE_DEPS_NAME.match(sdist_pkg)
                if not match_deps:
                    bar.update(pos)
                    continue
                match_deps = match_deps.group(0).strip()
                pkg_name = PyPi._normalize_pkg_name(match_deps)
                bar.update(pos, pkg_name=pkg_name)
                if current_pkg and current_pkg == pkg_name:
                    continue
                if pkg_name in pypi_deps_name:
                    continue

                pypi_deps_name.add(pkg_name)
                requires_dist.append(sdist_pkg.replace(match_deps, pkg_name))
        return requires_dist

    @staticmethod
    def _normalize_pkg_name(pkg_name: str) -> str:
        if is_pkg_available(pkg_name):
            return pkg_name
        if is_pkg_available(pkg_name.replace("-", "_")):
            return pkg_name.replace("-", "_")
        elif is_pkg_available(pkg_name.replace("_", "-")):
            return pkg_name.replace("_", "-")
        return pkg_name

    def refresh_section(self, section: str = ""):
        """Update one specific section.

        :param section: Section name
        """
        metadata = self._get_metadata()
        if metadata.get(section):
            if section == "package":
                self.set_jinja_var("version", metadata["package"]["version"])
                self["package"]["version"] = "<{ version }}"
            else:
                self.populate_metadata_from_dict(metadata.get(section), self[section])
        if not self._is_arch:
            self["build"]["noarch"] = "python"

    @lru_cache(maxsize=10)
    def _get_metadata(self) -> dict:
        """Method responsible to get the whole metadata available. It will
        merge metadata from multiple sources (pypi, setup.py, setup.cfg)
        """
        name = self.get_var_content(self["package"]["name"].values[0])
        version = ""
        if self["package"]["version"].values:
            version = self.get_var_content(self["package"]["version"].values[0])
        pypi_metadata = self._get_pypi_metadata(name, version)
        sdist_metadata = self._get_sdist_metadata(
            sdist_url=pypi_metadata["sdist_url"], name=name
        )
        metadata = PyPi._merge_pypi_sdist_metadata(pypi_metadata, sdist_metadata)
        log.debug(f"Data merged from pypi, setup.cfg and setup.py: {metadata}")
        license_metadata = PyPi._discover_license(metadata)

        license_file = "PLEASE_ADD_LICENSE_FILE"
        license_name = "Other"
        if license_metadata:
            license_name = license_metadata.name
            if license_metadata.path:
                if license_metadata.is_packaged:
                    license_file = license_metadata.path
                else:
                    license_file = os.path.basename(license_metadata.path)
                    self.files_to_copy.append(license_metadata.path)

        print_msg(f"License type: {Fore.LIGHTMAGENTA_EX}{license_name}")
        print_msg(f"License file: {Fore.LIGHTMAGENTA_EX}{license_file}")

        all_requirements = self._extract_requirements(metadata)
        all_requirements["host"] = solve_list_pkg_name(
            all_requirements["host"], self.PYPI_CONFIG
        )
        all_requirements["run"] = solve_list_pkg_name(
            all_requirements["run"], self.PYPI_CONFIG
        )
        print_requirements(all_requirements)

        test_entry_points = PyPi._get_test_entry_points(metadata.get("entry_points"))
        test_imports = PyPi._get_test_imports(metadata, pypi_metadata["name"])
        return {
            "package": {"name": name, "version": metadata["version"]},
            "build": {"entry_points": metadata.get("entry_points")},
            "requirements": all_requirements,
            "test": {
                "imports": test_imports,
                "commands": ["pip check"] + test_entry_points,
                "requires": "pip",
            },
            "about": {
                "home": metadata["url"]
                if metadata.get("url")
                else metadata.get("project_url"),
                "summary": metadata.get("summary"),
                "doc_url": metadata.get("doc_url"),
                "dev_url": metadata.get("dev_url"),
                "license": license_name,
                "license_file": license_file,
            },
            "source": metadata.get("source", {}),
        }

    @staticmethod
    def _get_test_imports(metadata: dict, default: Optional[str] = None) -> List:
        if default:
            default = default.replace("-", "_")
        if "packages" not in metadata or not metadata["packages"]:
            return [default]
        meta_pkg = metadata["packages"]
        if isinstance(meta_pkg, str):
            meta_pkg = [metadata["packages"]]
        return sorted(meta_pkg)[:2]

    @staticmethod
    def _get_test_entry_points(entry_points: Union[List, str]) -> List:
        if entry_points:
            if isinstance(entry_points, str):
                entry_points = [entry_points]
        test_entry_points = [
            f"{ep.split('=')[0].strip()} --help" for ep in entry_points
        ]
        return test_entry_points

    @staticmethod
    def _discover_license(metadata: dict) -> Optional[ShortLicense]:
        """Based on the metadata this method will try to discover what is the
        right license for the package

        :param metadata: metadata
        :return: Return an object which contains relevant informations regarding
        the license.
        """
        git_url = metadata.get("dev_url", None)
        if (
            not git_url
            and "github.com" == urlparse(metadata.get("project_url", "")).netloc
        ):
            git_url = metadata.get("project_url")
        # "url" is always present but sometimes set to None
        if not git_url and "github.com" == urlparse((metadata.get("url") or "")).netloc:
            git_url = metadata.get("url")

        short_license = search_license_file(
            metadata.get("sdist_path"),
            git_url,
            metadata.get("version"),
            license_name_metadata=metadata.get("license"),
        )
        if short_license:
            return short_license

    @lru_cache(maxsize=10)
    def _get_pypi_metadata(self, name, version: Optional[str] = None) -> dict:
        """Method responsible to communicate with the pypi api endpoints and
        get the whole metadata available for the specified package and version.

        :param name: Package name
        :param version: Package version
        :return: Pypi metadata
        """
        print_msg("Recovering metadata from pypi...")
        if version:
            url_pypi = PyPi.URL_PYPI_METADATA.format(pkg_name=f"{name}/{version}")
        else:
            log.info(f"Version for {name} not specified.\nGetting the latest one.")
            url_pypi = PyPi.URL_PYPI_METADATA.format(pkg_name=name)

        metadata = requests.get(url=url_pypi, timeout=5)
        if metadata.status_code != 200:
            raise requests.HTTPError(
                f"It was not possible to recover PyPi metadata for {name}.\n"
                f"Error code: {metadata.status_code}"
            )

        metadata = metadata.json()
        if self._download:
            download_file = os.path.join(
                str(mkdtemp(f"grayskull-pypi-metadata-{name}-")), "pypi.json"
            )
            with open(download_file, "w") as f:
                json.dump(metadata, f, indent=4)
            self.files_to_copy.append(download_file)
        info = metadata["info"]
        project_urls = info.get("project_urls") if info.get("project_urls") else {}
        log.info(f"Package: {name}=={info['version']}")
        log.debug(f"Full PyPI metadata:\n{metadata}")
        return {
            "name": name,
            "version": info["version"],
            "requires_dist": info.get("requires_dist", []),
            "requires_python": info.get("requires_python", None),
            "summary": info.get("summary"),
            "project_url": info.get("project_url"),
            "doc_url": info.get("docs_url"),
            "dev_url": project_urls.get("Source"),
            "url": info.get("home_page"),
            "license": info.get("license"),
            "source": {
                "url": "https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/"
                "{{ name }}-{{ version }}.tar.gz",
                "sha256": PyPi.get_sha256_from_pypi_metadata(metadata),
            },
            "sdist_url": PyPi._get_sdist_url_from_pypi(metadata),
        }

    @staticmethod
    def _get_sdist_url_from_pypi(metadata: dict) -> str:
        """Return the sdist url looking for the pypi metadata

        :param metadata: pypi metadata
        :return: sdist url
        """
        for sdist_url in metadata["urls"]:
            if sdist_url["packagetype"] == "sdist":
                return sdist_url["url"]

    @staticmethod
    def get_sha256_from_pypi_metadata(pypi_metadata: dict) -> str:
        """Get the sha256 from pypi metadata

        :param pypi_metadata: pypi metadata
        :return: sha256 value for the sdist package
        """
        for pkg_info in pypi_metadata.get("urls"):
            if pkg_info.get("packagetype", "") == "sdist":
                return pkg_info["digests"]["sha256"]
        raise AttributeError(
            "Hash information for sdist was not found on PyPi metadata."
        )

    @staticmethod
    def __skip_pypi_requirement(list_extra: List) -> bool:
        """Test if it should skip the requirement

        :param list_extra: list with all extra requirements
        :return: True if we should skip the requirement
        """
        for extra in list_extra:
            if extra[1] == "extra" or extra[3] == "testing":
                return True
        return False

    def _extract_requirements(self, metadata: dict) -> dict:
        """Extract the requirements for `build`, `host` and `run`

        :param metadata: all metadata
        :return: all requirement section
        """
        name = metadata["name"]
        requires_dist = PyPi._format_dependencies(metadata.get("requires_dist"), name)
        setup_requires = (
            metadata.get("setup_requires") if metadata.get("setup_requires") else []
        )
        host_req = PyPi._format_dependencies(setup_requires, name)

        if not requires_dist and not host_req and not metadata.get("requires_python"):
            return {"host": sorted(["python", "pip"]), "run": ["python"]}

        run_req = self._get_run_req_from_requires_dist(requires_dist)

        build_req = [f"<{{ compiler('{c}') }}}}" for c in metadata.get("compilers", [])]
        if build_req:
            self._is_arch = True

        if self._is_arch:
            version_to_selector = PyPi.py_version_to_selector(metadata)
            if version_to_selector:
                self["build"]["skip"] = True
                self["build"]["skip"].values[0].selector = version_to_selector
            limit_python = ""
        else:
            limit_python = PyPi.py_version_to_limit_python(metadata)

        limit_python = f" {limit_python}" if limit_python else ""

        if "pip" not in host_req:
            host_req += [f"python{limit_python}", "pip"]

        run_req.insert(0, f"python{limit_python}")
        result = {}
        if build_req:
            result = {
                "build": PyPi.__rm_duplicated_deps(
                    sorted(map(lambda x: x.lower(), build_req))
                )
            }

        result.update(
            {
                "host": PyPi.__rm_duplicated_deps(
                    sorted(map(lambda x: x.lower(), host_req))
                ),
                "run": PyPi.__rm_duplicated_deps(
                    sorted(map(lambda x: x.lower(), run_req))
                ),
            }
        )
        self._update_requirements_with_pin(result)
        return result

    @staticmethod
    def _format_dependencies(all_dependencies: List, name: str) -> List:
        """Just format the given dependency to a string which is valid for the
        recipe

        :param all_dependencies: list of dependencies
        :param name: package name
        :return: list of dependencies formatted
        """
        formatted_dependencies = []
        re_deps = re.compile(
            r"^\s*([\.a-zA-Z0-9_-]+)\s*(.*)\s*$", re.MULTILINE | re.DOTALL
        )
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
            deps_name = re_remove_tags.sub(r"", deps_name.strip())
            deps_name = re_remove_comments.sub("", deps_name)
            formatted_dependencies.append(deps_name.strip())
        return formatted_dependencies

    @staticmethod
    def _update_requirements_with_pin(requirements: dict):
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
            for build in requirements["build"]:
                if re_compiler.match(build):
                    return True
            return False

        if not is_compiler_present():
            return
        for pkg in requirements["host"]:
            pkg_name = PyPi.RE_DEPS_NAME.match(pkg).group(0)
            if pkg_name in PyPi.PIN_PKG_COMPILER.keys():
                if pkg_name in requirements["run"]:
                    requirements["run"].remove(pkg_name)
                requirements["run"].append(PyPi.PIN_PKG_COMPILER[pkg_name])

    def _get_run_req_from_requires_dist(self, requires_dist: List) -> List:
        """Get the run requirements looking for the `requires_dist` key
        present in the metadata

        :param requires_dist: List of requirements
        :return:
        """
        run_req = []
        for req in requires_dist:
            list_raw_requirements = req.split(";")
            selector = ""
            if len(list_raw_requirements) > 1:
                list_extra = PyPi._get_extra_from_requires_dist(
                    list_raw_requirements[1]
                )
                if PyPi.__skip_pypi_requirement(list_extra):
                    continue

                result_selector = self._get_all_selectors_pypi(list_extra)

                if result_selector:
                    selector = " ".join(result_selector)
                    selector = f"  # [{selector}]"
                else:
                    selector = ""
            pkg_name, version = PyPi._get_name_version_from_requires_dist(
                list_raw_requirements[0]
            )
            run_req.append(f"{pkg_name} {version}{selector}".strip())
        return run_req

    def _get_all_selectors_pypi(self, list_extra: List) -> List:
        """Get the selectors looking for the pypi data

        :param list_extra: List of extra requirements from pypi
        :return: List of extra requirements with the selectors
        """
        result_selector = []
        for extra in list_extra:
            self._is_arch = True
            selector = PyPi._parse_extra_metadata_to_selector(
                extra[1], extra[2], extra[3]
            )
            if selector:
                if extra[0]:
                    result_selector.append(extra[0])
                result_selector.append(selector)
                if extra[4]:
                    result_selector.append(extra[4])
                if extra[5]:
                    result_selector.append(extra[5])
        if result_selector and result_selector[-1] in ["and", "or"]:
            del result_selector[-1]
        return result_selector

    @staticmethod
    def _get_extra_from_requires_dist(string_parse: str) -> Union[List]:
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

    @staticmethod
    def _get_name_version_from_requires_dist(string_parse: str) -> Tuple[str, str]:
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

    @staticmethod
    def _generic_py_ver_to(
        pypi_metadata: dict, is_selector: bool = False
    ) -> Optional[str]:
        """Generic function which abstract the parse of the requires_python
        present in the PyPi metadata. Basically it can generate the selectors
        for Python or the constrained version if it is a `noarch: python` python package

        :param pypi_metadata: PyPi metadata
        :param is_selector:
        :return: return the constrained versions or the selectors
        """
        if not pypi_metadata["requires_python"]:
            return None
        req_python = re.findall(
            r"([><=!]+)\s*(\d+)(?:\.(\d+))?", pypi_metadata["requires_python"],
        )
        if not req_python:
            return None

        py_ver_enabled = PyPi._get_py_version_available(req_python)
        small_py3_version = get_small_py3_version(list(py_ver_enabled.keys()))
        all_py = list(py_ver_enabled.values())
        if all(all_py):
            return None
        if all(all_py[1:]):
            return (
                "# [py2k]"
                if is_selector
                else f">={small_py3_version.major}.{small_py3_version.minor}"
            )
        if py_ver_enabled.get(PyVer(2, 7)) and any(all_py[1:]) is False:
            return "# [py3k]" if is_selector else "<3.0"

        for pos, py_ver in enumerate(py_ver_enabled):
            if py_ver == PyVer(2, 7):
                continue
            if all(all_py[pos:]) and any(all_py[:pos]) is False:
                return (
                    f"# [py<{py_ver.major}{py_ver.minor}]"
                    if is_selector
                    else f">={py_ver.major}.{py_ver.minor}"
                )
            elif any(all_py[pos:]) is False:
                if is_selector:
                    py2k = ""
                    if not all_py[0]:
                        py2k = " or py2k"
                    return f"# [py>={py_ver.major}{py_ver.minor}{py2k}]"
                else:
                    py2 = ""
                    if not all_py[0]:
                        py2 = f">={small_py3_version.major}.{small_py3_version.minor},"
                    return f"{py2}<{py_ver.major}.{py_ver.minor}"

        all_selector = PyPi._get_py_multiple_selectors(
            py_ver_enabled, is_selector=is_selector
        )
        if all_selector:
            return (
                "# [{}]".format(" or ".join(all_selector))
                if is_selector
                else ",".join(all_selector)
            )
        return None

    @staticmethod
    def py_version_to_limit_python(pypi_metadata: dict) -> Optional[str]:
        return PyPi._generic_py_ver_to(pypi_metadata, is_selector=False)

    @staticmethod
    def py_version_to_selector(pypi_metadata: dict) -> Optional[str]:
        return PyPi._generic_py_ver_to(pypi_metadata, is_selector=True)

    @staticmethod
    def _get_py_version_available(
        req_python: List[Tuple[str, str, str]]
    ) -> Dict[PyVer, bool]:
        """Get the python version available given the requires python received

        :param req_python: Requires python
        :return: Dict of Python versions if it is enabled or disabled
        """
        sup_python_ver = deepcopy(SUPPORTED_PY)
        for _, major, minor in req_python:
            if not minor:
                minor = 0
            new_py_ver = PyVer(int(major), int(minor))
            if new_py_ver in sup_python_ver:
                continue
            sup_python_ver.append(new_py_ver)
        sup_python_ver.sort()
        py_ver_enabled = {py_ver: True for py_ver in sup_python_ver}
        for op, major, minor in req_python:
            if not minor:
                minor = 0
            for sup_py, is_enabled in py_ver_enabled.items():
                if is_enabled is False:
                    continue
                py_ver_enabled[sup_py] = eval(
                    f"sup_py {op} PyVer(int({major}), int({minor}))"
                )
        return py_ver_enabled

    @staticmethod
    def _get_py_multiple_selectors(
        selectors: Dict[PyVer, bool], is_selector=False
    ) -> List:
        """Get python selectors available.

        :param selectors: Dict with the Python version and if it is selected
        :param is_selector: if it needs to convert to selector or constrain python
        :return: list with all selectors or constrained python
        """
        all_selector = []
        if selectors[PyVer(2, 7)] is False:
            all_selector += (
                ["py2k"]
                if is_selector
                else get_small_py3_version(list(selectors.keys()))
            )
        for py_ver, is_enabled in selectors.items():
            if py_ver == PyVer(2, 7) or is_enabled:
                continue
            all_selector += (
                [f"py=={py_ver.major}{py_ver.minor}"]
                if is_selector
                else [f"!={py_ver.major}.{py_ver.minor}"]
            )
        return all_selector

    @staticmethod
    def _parse_extra_metadata_to_selector(
        option: str, operation: str, value: str
    ) -> str:
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


def get_small_py3_version(list_py_ver: List[PyVer]) -> PyVer:
    list_py_ver = sorted(list_py_ver)
    for py_ver in list_py_ver:
        if py_ver >= PyVer(3, 0):
            return py_ver


def search_setup_root(path_folder: Union[Path, str]) -> Path:
    setup_py = list(Path(path_folder).rglob("setup.py"))
    if setup_py:
        return setup_py[0]
    setup_cfg = list(Path(path_folder).rglob("setup.cfg"))
    if setup_cfg:
        return setup_cfg[0]
    pyproject_toml = list(Path(path_folder).rglob("pyproject.toml"))
    if pyproject_toml:
        return pyproject_toml[0]
