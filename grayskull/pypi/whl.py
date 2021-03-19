import os
import re
import logging
import requests
import shutil
from pathlib import Path
from functools import lru_cache
from typing import Optional, List, Union, Tuple, Dict

from tempfile import mkdtemp
from colorama import Fore, Style
from grayskull.cli.stdout import print_msg, manage_progressbar, print_requirements

from grayskull.base.track_packages import solve_list_pkg_name

from .pypi import clean_deps_for_conda_forge, PyPi
from grayskull.base.base_recipe import AbstractRecipeModel

log = logging.getLogger(__name__)

class Whl(AbstractRecipeModel):
    URL_PYPI_METADATA = "https://pypi.org/pypi/{pkg_name}/json"
    PKG_NEEDS_C_COMPILER = ("cython",)
    PKG_NEEDS_CXX_COMPILER = ("pybind11",)
    PIN_PKG_COMPILER = {"numpy": "<{ pin_compatible('numpy') }}"}
    RE_DEPS_NAME = re.compile(r"^\s*([\.a-zA-Z0-9_-]+)", re.MULTILINE)
    PYPI_CONFIG = Path(os.path.dirname(__file__)) / "config.yaml"

    def __init__(
        self,
        name: Optional[str] = None,
        version: Optional[str] = None,
        is_strict_cf: bool = False,
    ):
        self._is_strict_cf = is_strict_cf
        self._is_arch = True
        super(Whl, self).__init__(name=name, version=str(version) if version else None)
        self["build"]["script"] = "<{ PYTHON }} -m pip install *.whl -vv"

    @lru_cache(maxsize=10)
    def _get_bdist_metadata(self, bdist_url: str, name: str) -> dict:
        """Method responsible to return the bdist metadata which is basically
        the metadata present in setup.py and setup.cfg

        :param bdist_url: URL to the bdist package
        :param name: name of the package
        :return: bdist metadata
        """
        temp_folder = mkdtemp(prefix=f"grayskull-{name}-")
        pkg_name = bdist_url.split("/")[-1]
        path_pkg = os.path.join(temp_folder, pkg_name)

        PyPi._download_sdist_pkg(sdist_url=bdist_url, dest=path_pkg)
        log.debug(f"Unpacking {path_pkg} to {temp_folder}")
        if 'wheel' not in shutil._UNPACK_FORMATS:
            shutil.register_unpack_format(
                name='wheel',
                extensions=['.whl'],
                function=shutil._unpack_zipfile,
            )
        shutil.unpack_archive(path_pkg, temp_folder)
        print_msg("Recovering information from METADATA and entry_points.txt")
        return Whl._extract_metadata_and_entrypoints(temp_folder)

    @staticmethod
    def _extract_metadata_and_entrypoints(folder: str) -> dict:
        bdist_metadata = {}
        metadata_file = list(Path(folder).rglob("METADATA"))
        entrypoints_file = list(Path(folder).rglob("entry_points.txt"))
        
        metadata_props = {
            'Author: ': 'author',
            'Name: ': 'name',
            'Version: ': 'version',
            'Classifier: ': 'classifiers',
            'Summary: ': 'summary',
            'Requires-Python: ': 'requires_python',
            'License: ': 'license',
            'Requires-Dist: ': 'requires_dist',
        }

        if metadata_file and metadata_file[0]:
            f = open(metadata_file[0], 'r')
            for each_line in f.readlines():
                for (k, v) in metadata_props.items():
                    if each_line.startswith(k):
                        entry = each_line.split(k)[1].strip()
                        if k in ['Classifier: ', 'Requires-Dist: ']:
                            if v not in bdist_metadata:
                                bdist_metadata[v] = [entry]
                            else:
                                bdist_metadata[v].append(entry)
                        else:
                            bdist_metadata[v] = entry
        
        if entrypoints_file and entrypoints_file[0]:
            f = open(entrypoints_file[0], 'r')
            bdist_metadata['entry_points'] = []
            for each_line in f.readlines():
                if each_line.startswith('[console_scripts]') or each_line.startswith('[gui_scripts]'):
                    continue
                else:
                    if each_line.strip('\n'):
                        bdist_metadata['entry_points'].append(each_line.strip('\n'))

        bdist_metadata['sdist_path'] = folder

        return bdist_metadata

    @staticmethod
    def _merge_pypi_bdist_metadata(pypi_metadata: dict, bdist_metadata: dict) -> dict:
        def get_val(key):
            return pypi_metadata.get(key) or bdist_metadata.get(key)

        requires_dist = PyPi._merge_requires_dist(pypi_metadata, bdist_metadata)
        
        return {
            "author": get_val("author"),
            "name": get_val("name"),
            "version": get_val("version"),
            "source": pypi_metadata.get("source"),
            "packages": get_val("packages") if get_val("packages") else get_val("py_modules"),
            "url": get_val("url"),
            "classifiers": get_val("classifiers"),
            "compilers": PyPi._get_compilers(requires_dist, bdist_metadata),
            "entry_points": get_val("entry_points"),
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
            "sdist_path": get_val("sdist_path"),
        }

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
        version = ""
        if self["package"]["version"].values:
            version = self.get_var_content(self["package"]["version"].values[0])
        pypi_metadata = self._get_pypi_metadata(name, version)

        all_bdist_metadata = []
        for each_bdist_url in pypi_metadata["bdist_url"]:
            each_bdist_metadata = self._get_bdist_metadata(
                bdist_url=each_bdist_url, name=name
            )
            all_bdist_metadata.append(each_bdist_metadata)

        final_bdist_metadata = Whl.combine_bdist_metadata(all_bdist_metadata, pypi_metadata["filenames"])

        metadata = Whl._merge_pypi_bdist_metadata(pypi_metadata, final_bdist_metadata)

        log.debug(f"Data merged from pypi, METADATA and entry_points.txt: {metadata}")
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
        if self._is_strict_cf:
            all_requirements["host"] = clean_deps_for_conda_forge(
                all_requirements["host"]
            )
            all_requirements["run"] = clean_deps_for_conda_forge(
                all_requirements["run"]
            )
        print_requirements(all_requirements)

        test_entry_points = PyPi._get_test_entry_points(metadata.get("entry_points") if metadata.get("entry_points") is not None else [])
        test_imports = PyPi._get_test_imports(metadata, pypi_metadata["name"])
        return {
            "package": {"name": name, "version": metadata["version"]},
            "build": {"entry_points": metadata.get("entry_points")},
            "requirements": all_requirements,
            "test": {
                "imports": [], # test_imports
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

    @lru_cache(maxsize=10)
    def _get_pypi_metadata(self, name, version: Optional[str] = None) -> dict:
        print_msg("Recovering metadata from pypi...")
        if version:
            url_pypi = Whl.URL_PYPI_METADATA.format(pkg_name=f"{name}/{version}")
        else:
            log.info(f"Version for {name} not specified.\nGetting the latest one.")
            url_pypi = Whl.URL_PYPI_METADATA.format(pkg_name=name)

        metadata = requests.get(url=url_pypi, timeout=5)
        if metadata.status_code != 200:
            raise requests.HTTPError(
                f"It was not possible to recover PyPi metadata for {name}.\n"
                f"Error code: {metadata.status_code}"
            )

        metadata = metadata.json()
        info = metadata["info"]
        project_urls = info.get("project_urls") if info.get("project_urls") else {}

        all_urls, all_filenames, all_shas = Whl._get_url_filename(metadata)

        all_bdist_urls, all_bdist_filenames = Whl._get_bdist_url_from_pypi(metadata)

        log.info(f"Package: {name}=={info['version']}")
        log.debug(f"Full PyPI metadata:\n{metadata}")

        pypi_metadata = {
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
            "bdist_url": all_bdist_urls,
            "filenames": all_bdist_filenames,
        }

        pypi_metadata["source"] = []
        for url, fn, sha in zip(all_urls, all_filenames, all_shas):
            pypi_metadata["source"].append({
                "url": url,
                "fn": fn,
                "sha256": sha
            })
        return pypi_metadata

    @staticmethod
    def _get_url_filename(metadata: dict, default: Optional[str] = None) -> str:
        """Method responsible to get the filename and right extension to add
        to the pypi url

        :param metadata: Dictionary with the all package metadata filled
        :param default: default value for the package filename
        :return: filename and extension to download the file on pypi
        """
        if default is None:
            default = "{{ name }}-{{ version }}.tar.gz"
        if "urls" not in metadata:
            return default

        url_template = "https://pypi.org/packages/source/{{ name[0] }}/{{ name }}/filename"
        all_urls = []
        all_filenames = []
        all_shas = []
        for pkg_url in metadata["urls"]:
            if pkg_url["packagetype"] == "bdist_wheel":
                version = metadata["info"]["version"]
                python_version = pkg_url["python_version"]
                filename = pkg_url["filename"].replace(version, "{{ version }}")
                each_url = url_template.replace("source", python_version).replace("filename", filename)
                each_sha = pkg_url["digests"]["sha256"]
                selector = Whl.determine_preprocessor_selectors(filename)
                all_urls.append(each_url+f'  # [{selector}]')
                all_filenames.append(filename+f'  # [{selector}]')
                all_shas.append(each_sha+f'  # [{selector}]')
        if all_urls and all_filenames and all_shas:
            return all_urls, all_filenames, all_shas
        return default

    @staticmethod
    def _get_bdist_url_from_pypi(metadata: dict) -> str:
        """Return the bdist url looking for the pypi metadata

        :param metadata: pypi metadata
        :return: bdist url
        """
        all_bdist_urls = []
        all_bdist_filenames = []
        for bdist_url in metadata["urls"]:
            if bdist_url["packagetype"] == "bdist_wheel":
                all_bdist_urls.append(bdist_url["url"])
                all_bdist_filenames.append(bdist_url["filename"])
        
        return all_bdist_urls, all_bdist_filenames

    @staticmethod
    def get_sha256_from_pypi_metadata(pypi_metadata: dict) -> str:
        """Get the sha256 from pypi metadata

        :param pypi_metadata: pypi metadata
        :return: sha256 value for the bdist package
        """
        for pkg_info in pypi_metadata.get("urls"):
            if pkg_info.get("packagetype", "") == "bdist_wheel":
                return pkg_info["digests"]["sha256"]
        raise AttributeError(
            "Hash information for bdist was not found on PyPi metadata."
        )

    @staticmethod
    def determine_preprocessor_selectors(filename):
        wheel_file_re = re.compile(
            r"""^(?P<namever>(?P<name>.+?)-(?P<ver>.*?))
            ((-(?P<build>\d[^-]*?))?-(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)
            \.whl|\.dist-info)$""",
            re.VERBOSE
        )
        wheel_info = wheel_file_re.match(filename)
        build_tag = wheel_info.group('build')
        pyversions = wheel_info.group('pyver').split('.')
        abis = wheel_info.group('abi').split('.')
        plats = wheel_info.group('plat').split('.')
        
        tags = []
        all_versions = re.findall('[0-9]+', pyversions[0])
        if all_versions:
            tags.append(f"py=={all_versions[0]}")

        platform = plats[0]
        if 'macosx' in platform: tags.append('osx')
        if 'win32' in platform: tags.append('win32')
        if 'win64' in platform: tags.append('win64')
        if 'win32' not in platform and 'win64' not in platform and 'win' in platform:
            tags.append('win')
        if 'linux32' in platform: tags.append('linux32')
        if 'linux64' in platform: tags.append('linux64')
        if 'linux32' not in platform and 'linux64' not in platform and 'linux' in platform:
            tags.append('linux')
        if 'x86_64' in platform: tags.append('x86_64')
        if 'x86_64' not in platform and 'x86' in platform:
            tags.append('x86')
        selector = " and ".join(tags)
        return f"({selector})"

    @staticmethod
    def combine_bdist_metadata(all_bdist_metadata, all_filenames):
        meta_dict = {}
        all_fields = ['author', 'name', 'version', 'summary', 'requires_python', 'license']
        for each_field in all_fields:
            meta_dict[each_field] = {}

        list_fields = ['classifiers', 'requires_dist', 'entry_points']
        for each_field in list_fields:
            meta_dict[each_field] = {}

        for each_bdist_metadata, each_filename in zip(all_bdist_metadata, all_filenames):
            tags = Whl.determine_preprocessor_selectors(each_filename)
            for each_field in all_fields:
                if each_field in each_bdist_metadata:
                    if each_bdist_metadata[each_field] not in meta_dict[each_field]:
                        meta_dict[each_field][each_bdist_metadata[each_field]] = [tags]
                    else:
                        meta_dict[each_field][each_bdist_metadata[each_field]].append(tags)
            for each_field in list_fields:
                if each_field in each_bdist_metadata:
                    for each_entry in each_bdist_metadata[each_field]:
                        if each_entry not in meta_dict[each_field]:
                            meta_dict[each_field][each_entry] = [tags]
                        else:
                            meta_dict[each_field][each_entry].append(tags)

        final_bdist_metadata = {}
        for each_field in all_fields:
            for each_entry in meta_dict[each_field]:
                if len(meta_dict[each_field][each_entry]) == len(all_filenames):
                    final_bdist_metadata[each_field] = each_entry
                else:
                    selector_for_entry = " or ".join(meta_dict[each_field][each_entry])
                    if each_field not in final_bdist_metadata:
                        final_bdist_metadata[each_field] = [each_entry+f'  # [{selector_for_entry}]']
                    else:
                        final_bdist_metadata[each_field].append(each_entry+f'  # [{selector_for_entry}]')

        for each_field in list_fields:
            for each_entry in meta_dict[each_field]:
                if len(meta_dict[each_field][each_entry]) != len(all_filenames):
                    selector_for_entry = " or ".join(meta_dict[each_field][each_entry])
                    each_entry+=f'  # [{selector_for_entry}]'
                if each_field not in final_bdist_metadata:
                    final_bdist_metadata[each_field] = [each_entry]
                else:
                    final_bdist_metadata[each_field].append(each_entry)
        
        final_bdist_metadata['sdist_path'] = all_bdist_metadata[0]['sdist_path']
        return final_bdist_metadata

    def _extract_requirements(self, metadata: dict) -> dict:
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
            version_to_selector = PyPi.py_version_to_selector(
                metadata, is_strict_cf=self._is_strict_cf
            )
            if version_to_selector:
                self["build"]["skip"] = True
                self["build"]["skip"].values[0].selector = version_to_selector
            limit_python = ""
        else:
            limit_python = PyPi.py_version_to_limit_python(
                metadata, is_strict_cf=self._is_strict_cf
            )

        limit_python = f" {limit_python}" if limit_python else ""

        if "pip" not in host_req:
            host_req += [f"python{limit_python}", "pip"]

        run_req.insert(0, f"python{limit_python}")
        result = {}
        if build_req:
            result = {
                "build": Whl.__rm_duplicated_deps(
                    sorted(map(lambda x: x.lower(), build_req))
                )
            }

        result.update(
            {
                "host": Whl.__rm_duplicated_deps(
                    sorted(map(lambda x: x.lower(), host_req))
                ),
                "run": Whl.__rm_duplicated_deps(
                    sorted(map(lambda x: x.lower(), run_req))
                ),
            }
        )
        PyPi._update_requirements_with_pin(result)
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