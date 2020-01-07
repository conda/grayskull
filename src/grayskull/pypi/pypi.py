import logging
import re
from collections import OrderedDict, namedtuple

import requests
from requests import HTTPError

from grayskull import About, Package, Requirements, Source, Test
from grayskull.base_recipe import Grayskull

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
        pass

    def refresh_section(self, section="", force_distutils=False):
        if self._force_setup or force_distutils:
            self._populate_fields_by_distutils()
            return

        if self._get_pypi_metadata().get(section):
            self[section] = self._get_pypi_metadata().get(section)
        if not self.requirements.run or len(self.requirements.run) == 1:
            self._force_setup = True
            self.refresh_section(section, force_distutils=True)

    def _get_pypi_metadata(self):
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
    def get_sha256_from_pypi_metadata(pypi_metadata):
        for pkg_info in pypi_metadata.get("urls"):
            if pkg_info.get("packagetype", "") == "sdist":
                return pkg_info["digests"]["sha256"]
        raise ValueError("Hash information for sdist was not found on PyPi metadata.")

    def _extract_pypi_requirements(self, metadata):
        if not metadata["info"].get("requires_dist"):
            return Requirements(host=["python", "pip"], run=["python"])
        limit_python = metadata["info"].get("requires_python", "")
        if limit_python is None:
            limit_python = ""
        run_req = []

        for req in metadata["info"].get("requires_dist"):
            list_raw_requirements = req.split(";")

            selector = ""
            if len(list_raw_requirements) > 1:
                self._is_using_selectors = True
                if limit_python:
                    self.build.skip = f"true  {PyPi.py_version_to_selector(metadata)}"
                else:
                    self.build.skip = None
                limit_python = ""
                option, operation, value = PyPi._get_extra_from_requires_dist(
                    list_raw_requirements[1]
                )
                if value == "testing":
                    continue
                selector = PyPi._parse_extra_metadata_to_selector(
                    option, operation, value
                )
            pkg_name, version = PyPi._get_name_version_from_requires_dist(
                list_raw_requirements[0]
            )
            run_req.append(f"{pkg_name} {version}{selector}".strip())

        host_req = [f"python{limit_python}", "pip"]
        run_req.insert(0, f"python{limit_python}")
        return Requirements(host=host_req, run=run_req)

    @staticmethod
    def _get_extra_from_requires_dist(string_parse):
        option, operation, value = re.match(
            r"^\s*(\w+)\s+(\W*)\s+(.*)", string_parse, re.DOTALL
        ).groups()
        return option, operation, re.sub(r"['\"]", "", value)

    @staticmethod
    def _get_name_version_from_requires_dist(string_parse):
        pkg = re.match(r"^\s*([^\s]+)\s*(\(.*\))?\s*", string_parse, re.DOTALL)
        pkg_name = pkg.group(1).strip()
        version = ""
        if len(pkg.groups()) > 1 and pkg.group(2):
            version = " " + pkg.group(2).strip()
        return pkg_name.strip(), re.sub(r"[\(\)]", "", version).strip()

    @staticmethod
    def py_version_to_selector(pypi_metadata):
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
            return "# [py2k]"
        if py_ver_enabled.get(PyVer(2, 7)) and any(all_py[1:]) is False:
            return "# [py3k]"

        for pos, py_ver in enumerate(SUPPORTED_PY[1:], 1):
            if all(all_py[pos:]) and any(all_py[:pos]) is False:
                return f"# [py<{py_ver.major}{py_ver.minor}]"
            elif any(all_py[pos:]) is False:
                return f"# [py>={py_ver.major}{py_ver.minor}]"

        all_selector = PyPi._get_multiple_selectors(py_ver_enabled)
        if all_selector:
            return "# [{}]".format(" or ".join(all_selector))
        return None

    @staticmethod
    def _get_py_version_available(req_python):
        py_ver_enabled = OrderedDict([(py_ver, True) for py_ver in SUPPORTED_PY])
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
    def _get_multiple_selectors(result):
        all_selector = []
        if result[PyVer(2, 7)] is False:
            all_selector.append("py2k")
        for py_ver, is_enabled in result.items():
            if py_ver == PyVer(2, 7) or is_enabled:
                continue
            all_selector.append(f"py=={py_ver.major}{py_ver.minor}")
        return all_selector

    @staticmethod
    def _parse_extra_metadata_to_selector(option, operation, value):
        if option == "extra":
            return ""
        if option == "python_version":
            value = value.split(".")
            value = "".join(value[:2])
            return f"  # [py{operation}{value}]"
        if option == "sys_platform":
            value = re.sub(r"[^a-zA-Z]+", "", value)
            return f"  # [{value.lower()}]"
