from collections.abc import Iterable
from dataclasses import dataclass, field

from grayskull.cli.parser import parse_pkg_name_version
from grayskull.utils import PyVer

DEFAULT_PYPI_URL = "https://pypi.org"
DEFAULT_PYPI_META_URL = "https://pypi.org/pypi"


@dataclass
class Configuration:
    name: str
    version: str = ""
    files_to_copy: list = field(default_factory=list)
    supported_py: list[PyVer] = field(
        default_factory=lambda: [
            PyVer(2, 7),
            PyVer(3, 6),
            PyVer(3, 7),
            PyVer(3, 8),
            PyVer(3, 9),
            PyVer(3, 10),
            PyVer(3, 11),
            PyVer(3, 12),
        ]
    )
    py_cf_supported: list[PyVer] = field(
        default_factory=lambda: [
            PyVer(3, 7),
            PyVer(3, 8),
            PyVer(3, 9),
            PyVer(3, 10),
            PyVer(3, 11),
            PyVer(3, 12),
        ]
    )
    is_strict_cf: bool = False
    pkg_need_c_compiler: tuple = field(
        default_factory=lambda: ("cython", "cython-blis", "blis")
    )
    pkg_need_cxx_compiler: tuple = field(default_factory=lambda: ("pybind11",))
    url_pypi: str = DEFAULT_PYPI_URL
    url_pypi_metadata: str = DEFAULT_PYPI_META_URL
    download: bool = False
    is_arch: bool = False
    repo_github: str | None = None
    from_local_sdist: bool = False
    local_sdist: str | None = None
    missing_deps: set = field(default_factory=set)
    extras_require_test: str | None = None
    github_release_tag: str | None = None
    extras_require_include: Iterable[str] = tuple()
    extras_require_exclude: Iterable[str] = tuple()
    extras_require_all: bool = False
    extras_require_split: bool = False
    licence_exclude_folders: Iterable[str] = tuple()

    def get_oldest_py3_version(self, list_py_ver: list[PyVer]) -> PyVer:
        list_py_ver = sorted(list_py_ver)
        min_python_version = (
            self.py_cf_supported[0] if self.is_strict_cf else PyVer(3, 0)
        )
        for py_ver in list_py_ver:
            if py_ver >= min_python_version:
                return py_ver
        return min_python_version

    def get_py_version_available(
        self, req_python: list[tuple[str, str, str]]
    ) -> dict[PyVer, bool]:
        """Get the python version available given the requires python received

        :param req_python: Requires python
        :return: Dict of Python versions if it is enabled or disabled
        """
        sup_python_ver = set(
            self.py_cf_supported if self.is_strict_cf else self.supported_py
        )
        sup_python_ver.update(
            {
                PyVer(int(major), int(minor or 0))
                for _, major, minor in req_python
                if major
            }
        )
        sup_python_ver = sorted(list(sup_python_ver))
        if self.is_strict_cf:
            py_ver_enabled = {
                py_ver: py_ver in self.py_cf_supported for py_ver in sup_python_ver
            }
        else:
            py_ver_enabled = {py_ver: True for py_ver in sup_python_ver}
        for op, major, minor in req_python:
            if op == "=":
                op = "=="
            elif op == "~=":
                op = ">="
            if not minor:
                minor = 0
            for sup_py, is_enabled in py_ver_enabled.items():
                if is_enabled is False:
                    continue
                py_ver_enabled[sup_py] = eval(
                    f"sup_py {op} PyVer(int({major}), int({minor}))"
                )
        return py_ver_enabled

    def __post_init__(self):
        if not self.url_pypi_metadata.endswith("/{pkg_name}/json"):
            self.url_pypi_metadata = (
                self.url_pypi_metadata.rstrip("/") + "/{pkg_name}/json"
            )
        if self.from_local_sdist:
            self.local_sdist = self.local_sdist or self.name
        pkg_repo, pkg_name, pkg_version = parse_pkg_name_version(self.name)
        if pkg_repo:
            prefix = "" if pkg_repo.endswith("/") else "/"
            self.repo_github = f"{pkg_repo}{prefix}{pkg_name}"

        self.name = pkg_name

        if pkg_version:
            self.version = pkg_version
