import logging
import os
import re
import shutil
import sys
from collections import namedtuple
from contextlib import contextmanager
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
        self._pypi_metadata = {}
        self._setup_metadata = None
        self._is_using_selectors = False
        self._is_no_arch = True
        super(PyPi, self).__init__(name=name, version=version)
        self["build"]["script"] = "<{ PYTHON }} -m pip install . -vv"

    def _extract_fields_by_distutils(self) -> dict:
        name = self.get_var_content(self["package"]["name"].values[0])
        version = self.get_var_content(self["package"]["version"].values[0])
        pkg = f"{name}=={version}"
        temp_folder = mktemp(prefix=f"grayskull-{name}-{version}-")
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
        :yield: return the
        """
        from distutils import core

        setup_core_original = core.setup
        old_dir = os.getcwd()
        path_setup = list(Path(folder).rglob("setup.py"))[0]
        os.chdir(os.path.dirname(str(path_setup)))

        data = {}

        def __fake_distutils_setup(*args, **kwargs):
            data["tests_require"] = kwargs.get("tests_require", None)
            data["install_requires"] = kwargs.get("install_requires", None)
            data["extras_require"] = kwargs.get("extras_require", None)
            data["entry_points"] = kwargs.get("entry_points", None)
            data["packages"] = kwargs.get("packages", None)
            data["setuptools"] = "setuptools" in sys.modules
            data["summary"] = kwargs.get("description", None)
            data["home"] = kwargs.get("url", None)
            data["license"] = kwargs.get("license", None)
            data["name"] = kwargs.get("name", None)
            data["classifiers"] = kwargs.get("classifiers", None)
            data["version"] = kwargs.get("version", None)
            return

        try:
            core.setup = __fake_distutils_setup
            try:
                core.run_setup(str(path_setup), script_args=["install"])
            except RuntimeError:
                pass
            yield data
        except Exception:
            yield {}
        finally:
            core.setup = setup_core_original
            os.chdir(old_dir)

    def refresh_section(self, section: str = "", force_distutils: bool = False):
        pypi_metadata = self._get_pypi_metadata()
        if pypi_metadata.get(section):
            if section == "package":
                self.add_jinja_var("version", pypi_metadata["package"]["version"])
                self["package"]["version"] = "<{ version }}"
            else:
                self.populate_metadata_from_dict(
                    pypi_metadata.get(section), self[section]
                )
        if not self._is_using_selectors:
            self["build"]["noarch"] = "python"

    def _get_pypi_metadata(self) -> dict:
        name = self.get_var_content(self["package"]["name"].values[0])
        if self["package"]["version"].values:
            version = self.get_var_content(self["package"]["version"].values[0])
            url_pypi = self.URL_PYPI_METADATA.format(pkg_name=f"{name}/{version}")
        else:
            version = None
            log.info(f"Version for {name} not specified.\nGetting the latest one.")
            url_pypi = self.URL_PYPI_METADATA.format(pkg_name=name)

        if (
            self._pypi_metadata
            and version
            and self._pypi_metadata["package"]["version"] == version
        ):
            return self._pypi_metadata

        metadata = requests.get(url=url_pypi)
        if metadata.status_code != 200:
            raise HTTPError(f"It was not possible to recover PyPi metadata for {name}.")

        metadata = metadata.json()
        info = metadata["info"]
        project_urls = info.get("project_urls", {})

        self._pypi_metadata = {
            "package": {"name": name, "version": info["version"]},
            "requirements": self._extract_pypi_requirements(metadata),
            "test": {"imports": [name.lower()]},
            "about": {
                "home": info.get("project_url"),
                "summary": info.get("summary"),
                "doc_url": info.get("docs_url"),
                "dev_url": project_urls.get("Source"),
                "license": info.get("license"),
            },
            "source": {
                "url": "https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/"
                "{{ name }}-{{ version }}.tar.gz",
                "sha256": PyPi.get_sha256_from_pypi_metadata(metadata),
            },
        }
        return self._pypi_metadata

    @staticmethod
    def get_sha256_from_pypi_metadata(pypi_metadata: dict) -> str:
        for pkg_info in pypi_metadata.get("urls"):
            if pkg_info.get("packagetype", "") == "sdist":
                return pkg_info["digests"]["sha256"]
        raise ValueError("Hash information for sdist was not found on PyPi metadata.")

    def __skip_pypi_requirement(self, list_extra: List) -> bool:
        for extra in list_extra:
            if extra[0] == "extra" or extra[2] == "testing":
                return True
        return False

    def _extract_pypi_requirements(self, metadata: dict) -> dict:
        if not metadata["info"].get("requires_dist"):
            return {"host": sorted(["python", "pip"]), "run": ["python"]}
        run_req = []
        for req in metadata["info"].get("requires_dist"):
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

        limit_python = metadata["info"].get("requires_python", "")
        if limit_python and self._is_using_selectors:
            version_to_selector = PyPi.py_version_to_selector(metadata)
            if version_to_selector:
                self["build"]["skip"] = True
                self["build"]["skip"].values[0].selector = version_to_selector
            limit_python = ""
        else:
            limit_python = PyPi.py_version_to_limit_python(metadata)
        limit_python = f" {limit_python}" if limit_python else ""
        host_req = [f"python{limit_python}", "pip"]
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
        req_python = re.findall(
            r"([><=!]+)\s*(\d+)(?:\.(\d+))?", pypi_metadata["info"]["requires_python"],
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
