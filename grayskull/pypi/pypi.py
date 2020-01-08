import logging
import re
from collections import namedtuple
from typing import Dict, List, Optional, Tuple

import requests
from requests import HTTPError

from grayskull.base import About, Package, Requirements, Source, Test
from grayskull.base.base_recipe import Grayskull

log = logging.getLogger(__name__)
PyVer = namedtuple("PyVer", ["major", "minor"])
SUPPORTED_PY = sorted([PyVer(2, 7), PyVer(3, 6), PyVer(3, 7), PyVer(3, 8)])


class PyPi(Grayskull):
    URL_PYPI_METADATA = "https://pypi.org/pypi/{pkg_name}/json"

    def __init__(self, name=None, version=None, force_setup=False):
        self._force_setup = force_setup
        self._pypi_metadata = None
        self._setup_metadata = None
        self._is_using_selectors = False
        self._is_no_arch = True
        super(PyPi, self).__init__(name=name, version=version)

    def _populate_fields_by_distutils(self):
        # TODO: Implement injection in distutils when there is no PyPi metadata
        pass

    def refresh_section(self, section: str = "", force_distutils: bool = False):
        if self._force_setup or force_distutils:
            self._populate_fields_by_distutils()
            return

        if self._get_pypi_metadata().get(section):
            self[section] = self._get_pypi_metadata().get(section)
        if not self.requirements.run or len(self.requirements.run) == 1:
            self._force_setup = True
            self.refresh_section(section, force_distutils=True)

    def _get_pypi_metadata(self) -> dict:
        if not self.package.version:
            log.info(
                f"Version for {self.package.name} not specified.\n"
                f"Getting the latest one."
            )
            url_pypi = self.URL_PYPI_METADATA.format(pkg_name=self.package.name)
        else:
            url_pypi = self.URL_PYPI_METADATA.format(
                pkg_name=f"{self.package.name}/{self.package.version}"
            )
        if self._pypi_metadata and self._pypi_metadata["package"] == self.package:
            return self._pypi_metadata

        metadata = requests.get(url=url_pypi)
        if metadata.status_code != 200:
            raise HTTPError(
                "It was not possible to recover PyPi metadata for"
                f" {self.package.name}."
            )
        metadata = metadata.json()
        info = metadata["info"]
        project_urls = info.get("project_urls", {})

        self._pypi_metadata = {
            "package": Package(name=self.package.name, version=info["version"]),
            "requirements": self._extract_pypi_requirements(metadata),
            "test": Test(imports=[self.package.name.lower()]),
            "about": About(
                home=info.get("project_url"),
                summary=info.get("summary"),
                doc_url=info.get("docs_url"),
                dev_url=project_urls.get("Source"),
                license=info.get("license"),
            ),
            "source": Source(
                url=r"https://pypi.io/packages/source/{{ name[0] }}/"
                r"{{ name }}/{{ name }}-{{ version }}.tar.gz",
                sha256=PyPi.get_sha256_from_pypi_metadata(metadata),
            ),
        }
        log.info(
            f"Extracting metadata for {self.package.name}" f" {self.package.version}."
        )
        return self._pypi_metadata

    @staticmethod
    def get_sha256_from_pypi_metadata(pypi_metadata: dict) -> str:
        for pkg_info in pypi_metadata.get("urls"):
            if pkg_info.get("packagetype", "") == "sdist":
                return pkg_info["digests"]["sha256"]
        raise ValueError("Hash information for sdist was not found on PyPi metadata.")

    def _extract_pypi_requirements(self, metadata: dict) -> Requirements:
        if not metadata["info"].get("requires_dist"):
            return Requirements(host=["python", "pip"], run=["python"])
        run_req = []

        for req in metadata["info"].get("requires_dist"):
            list_raw_requirements = req.split(";")

            selector = ""
            if len(list_raw_requirements) > 1:
                option, operation, value = PyPi._get_extra_from_requires_dist(
                    list_raw_requirements[1]
                )
                if option == "extra" or value == "testing":
                    continue
                self._is_using_selectors = True
                selector = PyPi._parse_extra_metadata_to_selector(
                    option, operation, value
                )
            pkg_name, version = PyPi._get_name_version_from_requires_dist(
                list_raw_requirements[0]
            )
            run_req.append(f"{pkg_name} {version}{selector}".strip())

        limit_python = metadata["info"].get("requires_python", "")
        if limit_python and self._is_using_selectors:
            self.build.skip = f"true  {PyPi.py_version_to_selector(metadata)}"
            limit_python = ""
        else:
            self.build.skip = None
            limit_python = PyPi.py_version_to_limit_python(metadata)

        host_req = [f"python{limit_python}", "pip"]
        run_req.insert(0, f"python{limit_python}")
        return Requirements(host=host_req, run=run_req)

    @staticmethod
    def _get_extra_from_requires_dist(string_parse: str) -> Tuple[str, str, str]:
        """Receives the extra metadata e parse it to get the option, operation
        and value.

        :param string_parse: metadata extra
        :return: return the option , operation and value of the extra metadata
        """
        option, operation, value = re.match(
            r"^\s*(\w+)\s+(\W*)\s+(.*)", string_parse, re.DOTALL
        ).groups()
        return option, operation, re.sub(r"['\"]", "", value)

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
        for Python or the delimiters if it is a `noarch: python` python package

        :param pypi_metadata: PyPi metadata
        :param is_selector:
        :return:
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
            return f"  # [py{operation}{value}]"
        if option == "sys_platform":
            value = re.sub(r"[^a-zA-Z]+", "", value)
            return f"  # [{value.lower()}]"
