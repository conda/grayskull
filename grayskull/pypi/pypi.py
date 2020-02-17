import logging
import os
import re
import shutil
import sys
from collections import namedtuple
from contextlib import contextmanager
from copy import deepcopy
from distutils import core
from functools import lru_cache
from pathlib import Path
from subprocess import check_output
from tempfile import mkdtemp
from typing import Dict, List, Optional, Tuple, Union

import requests
from requests import HTTPError

from grayskull.base.base_recipe import AbstractRecipeModel
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

    def __init__(self, name=None, version=None, force_setup=False):
        self._force_setup = force_setup
        self._setup_metadata = None
        self._is_arch = False
        super(PyPi, self).__init__(name=name, version=version)
        self["build"]["script"] = "<{ PYTHON }} -m pip install . -vv"

    @staticmethod
    def _download_sdist_pkg(sdist_url: str, dest: str):
        response = requests.get(sdist_url, allow_redirects=True, stream=True)
        with open(dest, "wb") as pkg_file:
            for chunk_data in response.iter_content(chunk_size=1024 ** 2):
                if chunk_data:
                    pkg_file.write(chunk_data)

    @lru_cache(maxsize=10)
    def _get_sdist_metadata(self, sdist_url: str) -> dict:
        name = self.get_var_content(self["package"]["name"].values[0])
        temp_folder = mkdtemp(prefix=f"grayskull-{name}-")

        pkg_name = sdist_url.split("/")[-1]
        path_pkg = os.path.join(temp_folder, pkg_name)

        self._download_sdist_pkg(sdist_url=sdist_url, dest=path_pkg)
        shutil.unpack_archive(path_pkg, temp_folder)
        with PyPi._injection_distutils(temp_folder) as metadata:
            return metadata

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
        from distutils.command import build_ext as dist_ext

        setup_core_original = core.setup
        old_dir = os.getcwd()
        path_setup = list(Path(folder).rglob("setup.py"))[0]
        os.chdir(os.path.dirname(str(path_setup)))

        original_build_ext_distutils = dist_ext.build_ext

        data_dist = {}

        # class _fake_build_ext_distutils(original_build_ext_distutils):
        #     def __init__(self, *args, **kwargs):
        #         global data_dist
        #         data_dist["compilers"] = ["c"]
        #         super(_fake_build_ext_distutils, self).__init__(*args, **kwargs)

        # from setuptools.command import build_ext as setup_ext
        #
        # original_build_ext_setuptools = setup_ext.build_ext
        #
        # class _fake_build_ext_setuptools(original_build_ext_setuptools):
        #     def __init__(self, *args, **kwargs):
        #         global data_dist
        #         data_dist["compilers"] = ["c"]
        #         super(_fake_build_ext_setuptools, self).__init__(*args, **kwargs)

        def __fake_distutils_setup(*args, **kwargs):
            print("------FAKE DISTUTILS -----------------")
            data_dist["tests_require"] = kwargs.get("tests_require", [])
            data_dist["install_requires"] = kwargs.get("install_requires", [])
            if not data_dist.get("setup_requires"):
                data_dist["setup_requires"] = []
            data_dist["setup_requires"] += (
                kwargs.get("setup_requires") if kwargs.get("setup_requires") else []
            )
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

            print("------EXT_MODULES---------")
            if kwargs.get("ext_modules", None):
                print(kwargs.get("ext_modules"))
                data_dist["compilers"] = ["c"]
                if len(kwargs["ext_modules"]) > 0:
                    for ext_mod in kwargs["ext_modules"]:
                        if ext_mod.has_f2py_sources():
                            data_dist["compilers"].append("fortran")
                            break
            if data_dist.get("run_py", False):
                del data_dist["run_py"]
                return
            setup_core_original(*args, **kwargs)

        try:
            core.setup = __fake_distutils_setup
            # dist_ext.build_ext = _fake_build_ext_distutils
            # setup_ext.build_ext = _fake_build_ext_setuptools
            path_setup = str(path_setup)
            PyPi.__run_setup_py(path_setup, data_dist)
            if not data_dist or data_dist.get("install_requires", None) is None:
                PyPi.__run_setup_py(path_setup, data_dist, run_py=True)
            yield data_dist
        except Exception as err:  # noqa
            print("---------- EXCEPTION INJECTION -----------")
            print(err)
            yield data_dist
        core.setup = setup_core_original
        dist_ext.build_ext = original_build_ext_distutils
        # setup_ext.build_ext = original_build_ext_setuptools
        os.chdir(old_dir)

    @staticmethod
    def __run_setup_py(path_setup: str, data_dist: dict, run_py=False):
        print("------------ RUN_SETUP_PY -----------------")
        original_path = deepcopy(sys.path)
        pip_dir = os.path.join(os.path.dirname(str(path_setup)), "pip-dir")
        if not os.path.exists(pip_dir):
            os.mkdir(pip_dir)
        if os.path.dirname(path_setup) not in sys.path:
            sys.path.append(os.path.dirname(path_setup))
            sys.path.append(pip_dir)
        PyPi._install_deps_if_necessary(path_setup, data_dist, pip_dir)
        try:
            if run_py:
                print("------------- RUN PY TRU RUNNING --------------")
                import runpy

                data_dist["run_py"] = True
                runpy.run_path(path_setup, run_name="__main__")
            else:
                print(f"------------ RUN SETUP --target={pip_dir} --------")
                core.run_setup(
                    path_setup, script_args=["install", f"--target={pip_dir}"]
                )
        except ModuleNotFoundError as err:
            PyPi._pip_install_dep(data_dist, err.name, pip_dir)
            PyPi.__run_setup_py(path_setup, data_dist, run_py)
        except Exception as err:  # noqa
            print("-------------- EXCEPTION RUN SETUP PY--------------------")
            print(err)
            pass
        if os.path.exists(pip_dir):
            shutil.rmtree(pip_dir)
        sys.path = original_path

    @staticmethod
    def _install_deps_if_necessary(setup_path: str, data_dist: dict, pip_dir: str):
        all_setup_deps = get_vendored_dependencies(setup_path)
        for dep in all_setup_deps:
            PyPi._pip_install_dep(data_dist, dep, pip_dir)

    @staticmethod
    def _pip_install_dep(data_dist: dict, dep_name: str, pip_dir: str):
        print("------------ PIP INSTALL -----------------")
        print(dep_name)
        if not data_dist.get("setup_requires"):
            data_dist["setup_requires"] = []
        if dep_name == "pkg_resources":
            dep_name = "setuptools"
        if (
            dep_name.lower() not in data_dist["setup_requires"]
            and dep_name.lower() != "setuptools"
        ):
            data_dist["setup_requires"].append(dep_name.lower())
        print(f"------------ PIP INSTALL {dep_name} -----------------")
        check_output(["pip", "install", dep_name, f"--target={pip_dir}"])

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
        return {
            "author": get_val("author"),
            "name": get_val("name"),
            "version": get_val("version"),
            "source": pypi_metadata.get("source"),
            "packages": get_val("packages"),
            "home": get_val("home"),
            "classifiers": get_val("classifiers"),
            "compilers": PyPi._get_compilers(requires_dist, sdist_metadata),
            "entry_points": PyPi._get_entry_points_from_sdist(sdist_metadata),
            "summary": get_val("summary"),
            "requires_python": get_val("requires_python"),
            "doc_url": get_val("doc_url"),
            "dev_url": get_val("dev_url"),
            "license": get_val("license"),
            "setup_requires": get_val("setup_requires"),
            "extra_requires": get_val("extra_requires"),
            "project_url": get_val("project_url"),
            "extras_require": get_val("extras_require"),
            "requires_dist": requires_dist,
        }

    @staticmethod
    def _get_compilers(requires_dist: List, sdist_metadata: dict) -> List:
        compilers = set(sdist_metadata.get("compilers", []))
        for pkg in requires_dist:
            pkg = PyPi.RE_DEPS_NAME.match(pkg).group(0)
            if pkg.strip() in PyPi.PKG_NEEDS_C_COMPILER:
                compilers.add("c")
            if pkg.strip() in PyPi.PKG_NEEDS_CXX_COMPILER:
                compilers.add("cxx")
        return list(compilers)

    @staticmethod
    def _get_entry_points_from_sdist(sdist_metadata: dict) -> List:
        all_entry_points = sdist_metadata.get("entry_points", None)
        if all_entry_points and (
            all_entry_points.get("console_scripts")
            or all_entry_points.get("gui_scripts")
        ):
            return all_entry_points.get("console_scripts", []) + all_entry_points.get(
                "gui_scripts", []
            )
        return []

    @staticmethod
    def _merge_requires_dist(pypi_metadata: dict, sdist_metadata: dict) -> List:
        pypi_deps_name = set()
        requires_dist = []
        all_deps = []
        if pypi_metadata.get("requires_dist"):
            all_deps = pypi_metadata.get("requires_dist", [])
        if sdist_metadata.get("install_requires"):
            all_deps += sdist_metadata.get("install_requires", [])

        for sdist_pkg in all_deps:
            match_deps = PyPi.RE_DEPS_NAME.match(sdist_pkg)
            if match_deps:
                match_deps = match_deps.group(0).strip()
                if match_deps not in pypi_deps_name:
                    pypi_deps_name.add(match_deps)
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
        if not self._is_arch:
            self["build"]["noarch"] = "python"

    @lru_cache(maxsize=10)
    def _get_metadata(self) -> dict:
        name = self.get_var_content(self["package"]["name"].values[0])
        pypi_metadata = self._get_pypi_metadata()
        sdist_metadata = self._get_sdist_metadata(sdist_url=pypi_metadata["sdist_url"])
        print("----------------- PYPI -----------")
        print(pypi_metadata)
        print("----------------- SDIST -----------")
        print(sdist_metadata)
        metadata = self._merge_pypi_sdist_metadata(pypi_metadata, sdist_metadata)
        print("----------------- MERGE METADATA -----------")
        print(metadata)
        return {
            "package": {"name": name, "version": metadata["version"]},
            "requirements": self._extract_requirements(metadata),
            "test": {"imports": pypi_metadata["name"]},
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
            url_pypi = PyPi.URL_PYPI_METADATA.format(pkg_name=f"{name}/{version}")
        else:
            log.info(f"Version for {name} not specified.\nGetting the latest one.")
            url_pypi = PyPi.URL_PYPI_METADATA.format(pkg_name=name)

        metadata = requests.get(url=url_pypi)
        if metadata.status_code != 200:
            raise HTTPError(
                f"It was not possible to recover PyPi metadata for {name}.\n"
                f"Error code: {metadata.status_code}"
            )

        metadata = metadata.json()
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
            "license": info.get("license"),
            "source": {
                "url": "https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/"
                "{{ name }}-{{ version }}.tar.gz",
                "sha256": PyPi.get_sha256_from_pypi_metadata(metadata),
            },
            "sdist_url": self._get_sdist_url_from_pypi(metadata),
        }

    def _get_sdist_url_from_pypi(self, metadata: dict) -> str:
        for sdist_url in metadata["urls"]:
            if sdist_url["packagetype"] == "sdist":
                return sdist_url["url"]

    @staticmethod
    def get_sha256_from_pypi_metadata(pypi_metadata: dict) -> str:
        for pkg_info in pypi_metadata.get("urls"):
            if pkg_info.get("packagetype", "") == "sdist":
                return pkg_info["digests"]["sha256"]
        raise AttributeError(
            "Hash information for sdist was not found on PyPi metadata."
        )

    @staticmethod
    def __skip_pypi_requirement(list_extra: List) -> bool:
        for extra in list_extra:
            if extra[0] == "extra" or extra[2] == "testing":
                return True
        return False

    def _extract_requirements(self, metadata: dict) -> dict:
        requires_dist = self._format_dependencies(metadata.get("requires_dist"))
        setup_requires = (
            metadata.get("setup_requires") if metadata.get("setup_requires") else []
        )
        host_req = self._format_dependencies(setup_requires)

        if not requires_dist and not host_req:
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
        result = (
            {"build": sorted(map(lambda x: x.lower(), build_req))} if build_req else {}
        )
        result.update(
            {
                "host": sorted(map(lambda x: x.lower(), host_req)),
                "run": sorted(map(lambda x: x.lower(), run_req)),
            }
        )
        self._update_requirements_with_pin(result)
        return result

    @staticmethod
    def _format_dependencies(all_dependencies: List) -> List:
        formated_dependencies = []
        re_deps = re.compile(
            r"^\s*([\.a-zA-Z0-9_-]+)\s*(.*)\s*$", re.MULTILINE | re.DOTALL
        )
        for req in all_dependencies:
            match_req = re_deps.match(req)
            deps_name = req
            if match_req:
                match_req = match_req.groups()
                deps_name = match_req[0]
                if len(match_req) > 1:
                    deps_name = " ".join(match_req)
            formated_dependencies.append(deps_name.strip())
        return formated_dependencies

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

    def _get_all_selectors_pypi(self, list_extra: List):
        result_selector = []
        for extra in list_extra:
            self._is_arch = True
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
