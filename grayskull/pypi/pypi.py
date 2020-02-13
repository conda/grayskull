import logging
import os
import re
import shutil
import sys
from collections import namedtuple
from contextlib import contextmanager
from distutils import core
from functools import lru_cache
from pathlib import Path
from subprocess import check_output
from tempfile import mktemp
from typing import Dict, List, Optional, Tuple, Union

import requests
from requests import HTTPError

from grayskull.base.base_recipe import AbstractRecipeModel

log = logging.getLogger(__name__)
PyVer = namedtuple("PyVer", ["major", "minor"])
SUPPORTED_PY = sorted([PyVer(2, 7), PyVer(3, 6), PyVer(3, 7), PyVer(3, 8)])


class PyPi(AbstractRecipeModel):
    URL_PYPI_METADATA = "https://pypi.org/pypi/{pkg_name}/json"

    def __init__(self, name=None, version=None, force_setup=False):
        self._force_setup = force_setup
        self._setup_metadata = None
        self._is_using_selectors = False
        self._is_no_arch = True
        super(PyPi, self).__init__(name=name, version=version)
        self["build"]["script"] = "<{ PYTHON }} -m pip install . -vv"

    @lru_cache(maxsize=10)
    def _get_sdist_metadata(self, version: Optional[str] = None) -> dict:
        name = self.get_var_content(self["package"]["name"].values[0])
        if not version and self["package"]["version"].values:
            version = self.get_var_content(self["package"]["version"].values[0])
        pkg = f"{name}=={version}" if version else name
        temp_folder = mktemp(prefix=f"grayskull-{name}-")
        check_output(
            [
                "pip",
                "download",
                pkg,
                "--no-binary",
                ":all:",
                "--no-deps",
                "-d",
                str(temp_folder),
            ]
        )
        shutil.unpack_archive(
            os.path.join(temp_folder, os.listdir(temp_folder)[0]), temp_folder
        )
        with self._injection_distutils(temp_folder) as metadata:
            return metadata

    @contextmanager
    def _injection_distutils(self, folder: str) -> dict:
        """This is a bit of "dark magic", please don't do it at home.
        It is injecting code in the distutils.core.setup and replacing the
        setup function by the inner function __fake_distutils_setup.
        This method is a contextmanager, after leaving the context it will return
        with the normal implementation of the distutils.core.setup.
        This method is necessary because some information are missing from the
        pypi metadata and also for those packages which the pypi metadata is missing.

        :pram folder: Path to the folder where the sdist package was extracted
        :yield: return the metadata from sdist
        """
        from distutils import core
        from distutils.command import build_ext as dist_ext

        setup_core_original = core.setup
        old_dir = os.getcwd()
        path_setup = list(Path(folder).rglob("setup.py"))[0]
        os.chdir(os.path.dirname(str(path_setup)))

        original_build_ext_distutils = dist_ext.build_ext

        data_dist = {}

        class _fake_build_ext_distutils(original_build_ext_distutils):
            def __init__(self, *args, **kwargs):
                global data_dist
                data_dist["c_compiler"] = True
                super(_fake_build_ext_distutils, self).__init__(*args, **kwargs)

        from setuptools.command import build_ext as setup_ext

        original_build_ext_setuptools = setup_ext.build_ext

        class _fake_build_ext_setuptools(original_build_ext_setuptools):
            def __init__(self, *args, **kwargs):
                global data_dist
                data_dist["c_compiler"] = True
                super(_fake_build_ext_setuptools, self).__init__(*args, **kwargs)

        def __fake_distutils_setup(*args, **kwargs):
            data_dist["tests_require"] = kwargs.get("tests_require", [])
            data_dist["install_requires"] = kwargs.get("install_requires", [])
            if not data_dist.get("setup_requires"):
                data_dist["setup_requires"] = []
            data_dist["setup_requires"] += kwargs.get("setup_requires", [])
            data_dist["extras_require"] = kwargs.get("extras_require", [])
            data_dist["requires_python"] = kwargs.get("requires_python", None)
            data_dist["entry_points"] = kwargs.get("entry_points", None)
            data_dist["packages"] = kwargs.get("packages", [])
            data_dist["summary"] = kwargs.get("description", None)
            data_dist["home"] = kwargs.get("url", None)
            data_dist["license"] = kwargs.get("license", None)
            data_dist["name"] = kwargs.get("name", None)
            data_dist["classifiers"] = kwargs.get("classifiers", None)
            data_dist["version"] = kwargs.get("version", None)
            data_dist["author"] = kwargs.get("author", None)

            if "use_scm_version" in kwargs:
                if "setuptools_scm" not in data_dist["setup_requires"]:
                    data_dist["setup_requires"] += ["setuptools_scm"]
                if "setuptools-scm" in data_dist["setup_requires"]:
                    data_dist["setup_requires"].remove("setuptools-scm")

            if kwargs.get("ext_modules", None):
                data_dist["c_compiler"] = True
            else:
                data_dist["c_compiler"] = data_dist.get("c_compiler", False)
            if data_dist.get("run_py", False):
                del data_dist["run_py"]
                return
            setup_core_original(*args, **kwargs)

        try:
            core.setup = __fake_distutils_setup
            dist_ext.build_ext = _fake_build_ext_distutils
            setup_ext.build_ext = _fake_build_ext_setuptools
            path_setup = str(path_setup)
            self.__run_setup_py(path_setup, data_dist)
            if not data_dist:
                self.__run_setup_py(path_setup, data_dist, run_py=True)
            yield data_dist
        except Exception:
            yield data_dist
        core.setup = setup_core_original
        dist_ext.build_ext = original_build_ext_distutils
        setup_ext.build_ext = original_build_ext_setuptools
        os.chdir(old_dir)

    def __run_setup_py(self, path_setup: str, data_dist: dict, run_py=False):
        original_path = sys.path
        pip_dir = os.path.join(os.path.dirname(str(path_setup)), "pip-dir")
        if not os.path.exists(pip_dir):
            os.mkdir(pip_dir)
        if os.path.dirname(path_setup) not in sys.path:
            sys.path.append(os.path.dirname(path_setup))
            sys.path.append(pip_dir)
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
            if not data_dist.get("setup_requires"):
                data_dist["setup_requires"] = []
            data_dist["setup_requires"].append(err.name)
            check_output(["pip", "install", err.name, f"--target={pip_dir}"])
            self.__run_setup_py(path_setup, data_dist, run_py)
        except Exception:
            pass
        if os.path.exists(pip_dir):
            os.rmdir(pip_dir)
        sys.path = original_path

    def _merge_pypi_sdist_metadata(
        self, pypi_metadata: dict, sdist_metadata: dict
    ) -> dict:
        """This method is responsible to merge two dictionaries and it will give
        priority to the pypi_metadata.

        :param pypi_metadata: PyPI metadata
        :param sdist_metadata: Metadata which comes from the ``setup.py``
        :return: A new dict with the result of the merge
        """

        def get_val(key):
            return pypi_metadata.get(key) or sdist_metadata.get(key)

        return {
            "author": sdist_metadata["author"],
            "name": get_val("name"),
            "version": get_val("version"),
            "source": pypi_metadata["source"],
            "packages": sdist_metadata["packages"],
            "home": sdist_metadata["home"],
            "classifiers": sdist_metadata["classifiers"],
            "c_compiler": sdist_metadata.get("c_compiler", False),
            "entry_points": self._get_entry_points_from_sdist(sdist_metadata),
            "summary": get_val("summary"),
            "requires_python": get_val("requires_python"),
            "doc_url": get_val("doc_url"),
            "dev_url": get_val("dev_url"),
            "license": get_val("license"),
            "setup_requires": get_val("setup_requires"),
            "extra_requires": get_val("extra_requires"),
            "project_url": get_val("project_url"),
            "extras_require": get_val("extras_require"),
            "requires_dist": self._merge_requires_dist(pypi_metadata, sdist_metadata),
        }

    def _get_entry_points_from_sdist(self, sdist_metadata: dict) -> List:
        all_entry_points = sdist_metadata.get("entry_points", None)
        if all_entry_points and (
            all_entry_points.get("console_scripts")
            or all_entry_points.get("gui_scripts")
        ):
            return all_entry_points.get("console_scripts", []) + all_entry_points.get(
                "gui_scripts", []
            )
        return []

    def _merge_requires_dist(self, pypi_metadata: dict, sdist_metadata: dict) -> List:
        re_deps_name = re.compile(r"^\s*([\.a-zA-Z0-9_-]+)", re.MULTILINE)
        if pypi_metadata.get("requires_dist"):
            pypi_deps_name = [
                re_deps_name.match(s).group(0).strip()
                for s in pypi_metadata.get("requires_dist", [])
                if re_deps_name.match(s)
            ]
        else:
            pypi_deps_name = []

        requires_dist = []
        if pypi_metadata.get("requires_dist"):
            requires_dist = pypi_metadata.get("requires_dist", [])
        for sdist_pkg in sdist_metadata.get("install_requires", []):
            match_deps = re_deps_name.match(sdist_pkg)
            if match_deps and match_deps.group(0).strip() not in pypi_deps_name:
                requires_dist.append(sdist_pkg)
        return requires_dist

    def refresh_section(self, section: str = ""):
        metadata = self._get_metadata()
        if metadata.get(section):
            if section == "package":
                self.set_jinja_var("version", metadata["package"]["version"])
                self["package"]["version"] = "<{ version }}"
            else:
                self.populate_metadata_from_dict(metadata.get(section), self[section])
        if not self._is_using_selectors:
            self["build"]["noarch"] = "python"

    def _get_metadata(self) -> dict:
        name = self.get_var_content(self["package"]["name"].values[0])
        pypi_metada = self._get_pypi_metadata()
        sdist_metada = self._get_sdist_metadata()
        metadata = self._merge_pypi_sdist_metadata(pypi_metada, sdist_metada)
        test_imports = (
            metadata.get("packages") if metadata.get("packages") else [name.lower()]
        )
        return {
            "package": {"name": name, "version": metadata["version"]},
            "requirements": self._extract_requirements(metadata),
            "test": {"imports": test_imports},
            "about": {
                "home": metadata.get("project_url"),
                "summary": metadata.get("summary"),
                "doc_url": metadata.get("doc_url"),
                "dev_url": metadata.get("dev_url"),
                "license": metadata.get("license"),
            },
            "source": metadata.get("source", {}),
        }

    @lru_cache(maxsize=10)
    def _get_pypi_metadata(self, version: Optional[str] = None) -> dict:
        name = self.get_var_content(self["package"]["name"].values[0])

        if not version and self["package"]["version"].values:
            version = self.get_var_content(self["package"]["version"].values[0])

        if version:
            url_pypi = self.URL_PYPI_METADATA.format(pkg_name=f"{name}/{version}")
        else:
            log.info(f"Version for {name} not specified.\nGetting the latest one.")
            url_pypi = self.URL_PYPI_METADATA.format(pkg_name=name)

        metadata = requests.get(url=url_pypi)
        if metadata.status_code != 200:
            raise HTTPError(
                f"It was not possible to recover PyPi metadata for {name}.\n"
                f"Error code: {metadata.status_code}"
            )

        metadata = metadata.json()
        info = metadata["info"]
        project_urls = info.get("project_urls", {})
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
            "license": info.get("license"),
            "source": {
                "url": "https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/"
                "{{ name }}-{{ version }}.tar.gz",
                "sha256": PyPi.get_sha256_from_pypi_metadata(metadata),
            },
        }

    @staticmethod
    def get_sha256_from_pypi_metadata(pypi_metadata: dict) -> str:
        for pkg_info in pypi_metadata.get("urls"):
            if pkg_info.get("packagetype", "") == "sdist":
                return pkg_info["digests"]["sha256"]
        raise AttributeError(
            "Hash information for sdist was not found on PyPi metadata."
        )

    def __skip_pypi_requirement(self, list_extra: List) -> bool:
        for extra in list_extra:
            if extra[0] == "extra" or extra[2] == "testing":
                return True
        return False

    def _extract_requirements(self, metadata: dict) -> dict:
        requires_dist = metadata.get("requires_dist")
        host_req = (
            metadata.get("setup_requires") if metadata.get("setup_requires") else []
        )
        if not requires_dist and not host_req:
            return {"host": sorted(["python", "pip"]), "run": ["python"]}
        run_req = []
        for req in metadata.get("requires_dist", []):
            list_raw_requirements = req.split(";")
            selector = ""
            if len(list_raw_requirements) > 1:
                list_extra = PyPi._get_extra_from_requires_dist(
                    list_raw_requirements[1]
                )
                if self.__skip_pypi_requirement(list_extra):
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

        limit_python = metadata.get("requires_python", "")
        if limit_python and (self._is_using_selectors or metadata.get("compiler", [])):
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
        return {"host": sorted(host_req), "run": sorted(run_req)}

    def _get_all_selectors_pypi(self, list_extra):
        result_selector = []
        for extra in list_extra:
            self._is_using_selectors = True
            selector = PyPi._parse_extra_metadata_to_selector(
                extra[0], extra[1], extra[2]
            )
            if selector:
                result_selector.append(selector)
                if len(result_selector) < len(list_extra):
                    if extra[3]:
                        result_selector.append(extra[3])
                    elif extra[4]:
                        result_selector.append(extra[4])
        return result_selector

    @staticmethod
    def _get_extra_from_requires_dist(string_parse: str) -> Union[List]:
        """Receives the extra metadata e parse it to get the option, operation
        and value.

        :param string_parse: metadata extra
        :return: return the option , operation and value of the extra metadata
        """
        return re.findall(
            r"\s*(\w+)\s+(\W*)\s+[?:'\"]?([.a-zA-Z0-9_-]+)"
            r"[?:'\"]?\s*\W*\s*(?:(and))?(?:(or))?\s*",
            string_parse,
            re.DOTALL,
        )

    @staticmethod
    def _get_name_version_from_requires_dist(string_parse: str) -> Tuple[str, str]:
        """Extract the name and the version from `requires_dist` present in
        PyPi`s metadata

        :param string_parse: requires_dist value from PyPi metadata
        :return: Name and version of a package
        """
        pkg = re.match(r"^\s*([^\s]+)\s*(\(.*\))?\s*", string_parse, re.DOTALL)
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
        all_py = list(py_ver_enabled.values())
        if all(all_py):
            return None
        if all(all_py[1:]):
            return (
                "# [py2k]"
                if is_selector
                else f">={SUPPORTED_PY[1].major}.{SUPPORTED_PY[1].minor}"
            )
        if py_ver_enabled.get(PyVer(2, 7)) and any(all_py[1:]) is False:
            return "# [py3k]" if is_selector else "<3.0"

        for pos, py_ver in enumerate(SUPPORTED_PY[1:], 1):
            if all(all_py[pos:]) and any(all_py[:pos]) is False:
                return (
                    f"# [py<{py_ver.major}{py_ver.minor}]"
                    if is_selector
                    else f">={py_ver.major}.{py_ver.minor}"
                )
            elif any(all_py[pos:]) is False:
                return (
                    f"# [py>={py_ver.major}{py_ver.minor}]"
                    if is_selector
                    else f"<{py_ver.major}.{py_ver.minor}"
                )

        all_selector = PyPi._get_multiple_selectors(
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
        py_ver_enabled = {py_ver: True for py_ver in SUPPORTED_PY}
        for op, major, minor in req_python:
            if not minor:
                minor = 0
            for sup_py in SUPPORTED_PY:
                if py_ver_enabled[sup_py] is False:
                    continue
                py_ver_enabled[sup_py] = eval(
                    f"sup_py {op} PyVer(int({major}), int({minor}))"
                )
        return py_ver_enabled

    @staticmethod
    def _get_multiple_selectors(selectors: Dict[PyVer, bool], is_selector=False):
        all_selector = []
        if selectors[PyVer(2, 7)] is False:
            all_selector += ["py2k"] if is_selector else [">3.0"]
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
        if option == "extra":
            return ""
        if option == "python_version":
            value = value.split(".")
            value = "".join(value[:2])
            return f"py{operation}{value}"
        if option == "sys_platform":
            value = re.sub(r"[^a-zA-Z]+", "", value)
            return value.lower()
