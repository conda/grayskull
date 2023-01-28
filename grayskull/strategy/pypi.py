import json
import logging
import os
import re
from pathlib import Path
from tempfile import mkdtemp
from typing import Dict, Iterable, List, Optional

import requests
from colorama import Fore
from souschef.jinja_expression import set_global_jinja_var
from souschef.recipe import Recipe

from grayskull.base.github import generate_git_archive_tarball_url, handle_gh_version
from grayskull.base.pkg_info import normalize_pkg_name
from grayskull.base.track_packages import _get_track_info_from_file, solve_list_pkg_name
from grayskull.cli.stdout import print_msg, print_requirements, progressbar_with_status
from grayskull.config import Configuration
from grayskull.strategy.abstract_strategy import AbstractStrategy
from grayskull.strategy.py_base import (
    RE_DEPS_NAME,
    clean_deps_for_conda_forge,
    discover_license,
    ensure_pep440,
    ensure_pep440_in_req_list,
    get_compilers,
    get_entry_points_from_sdist,
    get_extra_from_requires_dist,
    get_name_version_from_requires_dist,
    get_sdist_metadata,
    get_test_entry_points,
    get_test_imports,
    parse_extra_metadata_to_selector,
    py_version_to_limit_python,
    py_version_to_selector,
    update_requirements_with_pin,
)
from grayskull.utils import format_dependencies, origin_is_github, rm_duplicated_deps

log = logging.getLogger(__name__)

PYPI_CONFIG = Path(os.path.dirname(__file__)) / "config.yaml"

ALL_SECTIONS = (
    "package",
    "source",
    "build",
    "outputs",
    "requirements",
    "app",
    "test",
    "about",
    "extra",
)


class PypiStrategy(AbstractStrategy):
    @staticmethod
    def fetch_data(recipe, config, sections=None):
        update_recipe(recipe, config, sections or ALL_SECTIONS)
        if not (recipe["build"] and recipe["build"]["script"]):
            recipe["build"]["script"] = "<{ PYTHON }} -m pip install . -vv"


def merge_pypi_sdist_metadata(
    pypi_metadata: dict, sdist_metadata: dict, config: Configuration
) -> dict:
    """This method is responsible to merge two dictionaries and it will give
    priority to the pypi_metadata."""

    def get_val(key):
        return pypi_metadata.get(key) or sdist_metadata.get(key)

    requires_dist = merge_requires_dist(pypi_metadata, sdist_metadata)
    all_packages_names = get_val("packages")
    if not all_packages_names:
        all_packages_names = get_val("py_modules")

    source_section = get_val("source")
    if not config.from_local_sdist:
        source_section["url"] = adjust_source_url_to_include_placeholders(
            source_section["url"], get_val("version")
        )

    return {
        "author": get_val("author"),
        "name": get_val("name"),
        "version": get_val("version"),
        "source": source_section,
        "packages": all_packages_names,
        "url": get_val("url"),
        "classifiers": get_val("classifiers"),
        "compilers": get_compilers(requires_dist, sdist_metadata, config),
        "entry_points": get_entry_points_from_sdist(sdist_metadata),
        "scripts": get_val("scripts"),
        "summary": get_val("summary"),
        "requires_python": ensure_pep440(
            pypi_metadata.get("requires_python")
            or sdist_metadata.get("python_requires")
        ),
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


def adjust_source_url_to_include_placeholders(url, version):
    url_split = url.rsplit("/", 1)
    url_split[-1] = url_split[-1].replace(version, "{{ version }}")
    return "/".join(url_split)


def get_url_filename(metadata: dict, default: Optional[str] = None) -> str:
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

    for pkg_url in metadata["urls"]:
        if pkg_url["packagetype"] == "sdist":
            version = metadata["info"]["version"]
            return pkg_url["filename"].replace(version, "{{ version }}")
    return default


def get_sha256_from_pypi_metadata(pypi_metadata: dict) -> str:
    """Get the sha256 from pypi metadata

    :param pypi_metadata: pypi metadata
    :return: sha256 value for the sdist package
    """
    for pkg_info in pypi_metadata.get("urls"):
        if pkg_info.get("packagetype", "") == "sdist":
            return pkg_info["digests"]["sha256"]
    raise AttributeError("Hash information for sdist was not found on PyPi metadata.")


def get_sdist_url_from_pypi(metadata: dict) -> str:
    """Return the sdist url looking for the pypi metadata

    :param metadata: pypi metadata
    :return: sdist url
    """
    for sdist_url in metadata["urls"]:
        if sdist_url["packagetype"] == "sdist":
            return sdist_url["url"]


def skip_pypi_requirement(list_extra: List) -> bool:
    """Test if it should skip the requirement

    :param list_extra: list with all extra requirements
    :return: True if we should skip the requirement
    """
    return any(
        extra[1] == "extra" or extra[3] in ["testing", "test", "tests"]
        for extra in list_extra
    )


def merge_requires_dist(pypi_metadata: dict, sdist_metadata: dict) -> List:
    """Merge requirements metadata from pypi and sdist.

    :param pypi_metadata: pypi metadata
    :param sdist_metadata: sdist metadata
    :return: list with all requirements
    """
    all_deps = sdist_metadata.get("install_requires") or []
    all_deps += pypi_metadata.get("requires_dist") or []

    re_search = re.compile(r";\s*extra")
    all_deps = [pkg for pkg in all_deps if not re_search.search(pkg)]
    current_pkg = pypi_metadata.get("name", "")

    requires_dist = []
    pypi_deps_name = set()
    with progressbar_with_status(len(all_deps)) as bar:
        for pos, sdist_pkg in enumerate(all_deps, 1):
            match_deps = RE_DEPS_NAME.match(sdist_pkg)
            if not match_deps:
                bar.update(pos)
                continue
            match_deps = match_deps.group(0).strip()
            pkg_name = normalize_pkg_name(match_deps)
            bar.update(pos, pkg_name=pkg_name)
            if current_pkg and current_pkg == pkg_name:
                continue
            if pkg_name in pypi_deps_name:
                continue

            pypi_deps_name.add(pkg_name)
            requires_dist.append(sdist_pkg.replace(match_deps, pkg_name))
    return requires_dist


def get_origin_wise_metadata(config):
    """Method responsible for extracting metadata based on package origin."""
    if config.repo_github and origin_is_github(config.repo_github):
        url = config.repo_github
        name = config.name
        version, version_tag = handle_gh_version(
            name=name, version=config.version, url=url, tag=config.github_release_tag
        )
        archive_url = generate_git_archive_tarball_url(git_url=url, git_ref=version_tag)
        sdist_metadata = get_sdist_metadata(
            sdist_url=archive_url, config=config, with_source=True
        )
        sdist_metadata["version"] = version
        pypi_metadata = {}
    elif config.from_local_sdist:
        sdist_metadata = get_sdist_metadata(
            sdist_url="",
            config=config,
        )
        pypi_metadata = {}
    else:
        pypi_metadata = get_pypi_metadata(config)
        sdist_metadata = get_sdist_metadata(
            sdist_url=pypi_metadata["sdist_url"], config=config
        )
    return sdist_metadata, pypi_metadata


def get_pypi_metadata(config: Configuration) -> dict:
    """Method responsible to communicate with the pypi api endpoints and
    get the whole metadata available for the specified package and version.

    :return: Pypi metadata
    """
    print_msg("Recovering metadata from pypi...")
    if config.version:
        url_pypi = config.url_pypi_metadata.format(
            pkg_name=f"{config.name}/{config.version}"
        )
    else:
        log.info(f"Version for {config.name} not specified.\nGetting the latest one.")
        url_pypi = config.url_pypi_metadata.format(pkg_name=config.name)

    metadata = requests.get(url=url_pypi, timeout=5)
    if metadata.status_code != 200:
        raise requests.HTTPError(
            f"It was not possible to recover package metadata for {config.name}.\n"
            f"Error code: {metadata.status_code}"
        )

    metadata = metadata.json()
    if config.download:
        download_file = os.path.join(
            str(mkdtemp(f"grayskull-pypi-metadata-{config.name}-")), "pypi.json"
        )
        with open(download_file, "w") as f:
            json.dump(metadata, f, indent=4)
        config.files_to_copy.append(download_file)
    info = metadata["info"]
    project_urls = info.get("project_urls") or {}
    log.info(f"Package: {config.name}=={info['version']}")
    log.debug(f"Full PyPI metadata:\n{metadata}")
    sdist_url = get_sdist_url_from_pypi(metadata)
    if sdist_url is None:
        raise AttributeError(f"There is no sdist package on pypi for {config.name}.")
    return {
        "name": config.name,
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
            f"{get_url_filename(metadata)}",
            "sha256": get_sha256_from_pypi_metadata(metadata),
        },
        "sdist_url": sdist_url,
    }


def get_run_req_from_requires_dist(requires_dist: List, config: Configuration) -> List:
    """Get the run requirements looking for the `requires_dist` key
    present in the metadata"""
    run_req = []
    for req in requires_dist:
        list_raw_requirements = req.split(";")
        selector = ""
        if len(list_raw_requirements) > 1:
            list_extra = get_extra_from_requires_dist(list_raw_requirements[1])
            if skip_pypi_requirement(list_extra):
                continue

            if result_selector := get_all_selectors_pypi(list_extra, config):
                selector = " ".join(result_selector)
                selector = f"  # [{selector}]"
            else:
                selector = ""
        pkg_name, version = get_name_version_from_requires_dist(
            list_raw_requirements[0]
        )
        run_req.append(f"{pkg_name} {version}{selector}".strip())
    return run_req


def get_all_selectors_pypi(list_extra: List, config: Configuration) -> List:
    """Get the selectors looking for the pypi data

    :param list_extra: List of extra requirements from pypi
    :param config: Configuration instructions for recipe
    :return: List of extra requirements with the selectors
    """
    result_selector = []
    for extra in list_extra:
        config.is_arch = True
        if selector := parse_extra_metadata_to_selector(extra[1], extra[2], extra[3]):
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


def get_metadata(recipe, config) -> dict:
    """Method responsible to get the whole metadata available. It will
    merge metadata from multiple sources (pypi, setup.py, setup.cfg)
    """
    name = config.name
    sdist_metadata, pypi_metadata = get_origin_wise_metadata(config)
    metadata = merge_pypi_sdist_metadata(pypi_metadata, sdist_metadata, config)
    log.debug(f"Data merged from pypi, setup.cfg and setup.py: {metadata}")
    if metadata.get("scripts") is not None:
        config.is_arch = True
        print_msg(f"{Fore.YELLOW}scripts detected. Package not eligible for noarch.")

    all_license_metadata = discover_license(metadata)
    license_file = []
    all_license_name = set()
    for license_metadata in all_license_metadata:
        all_license_name.add(license_metadata.name)
        if license_metadata.path:
            if license_metadata.is_packaged:
                license_file.append(license_metadata.path)
            else:
                license_file.append(os.path.basename(license_metadata.path))
                config.files_to_copy.append(license_metadata.path)

        print_msg(f"License type: {Fore.LIGHTMAGENTA_EX}{license_metadata.name}")
        print_msg(f"License file: {Fore.LIGHTMAGENTA_EX}{license_file}")
    if all_license_name:
        all_license_name = list(filter(None, all_license_name))
        license_name = " AND ".join(all_license_name)
        if len(all_license_name) > 1:
            print_msg(
                f"{Fore.RED}Multiple licenses detected!"
                f" {Fore.LIGHTYELLOW_EX}Please, be sure to check them."
            )
    else:
        license_name = "Other"
    if not license_file:
        license_file = "PLEASE_ADD_LICENSE_FILE"
    elif len(license_file) == 1:
        license_file = license_file[0]

    requirements_section = extract_requirements(metadata, config, recipe)
    optional_requirements = extract_optional_requirements(metadata, config)
    for key in requirements_section:
        requirements_section[key] = normalize_requirements_list(
            requirements_section[key], config
        )
    for key in optional_requirements:
        optional_requirements[key] = normalize_requirements_list(
            optional_requirements[key], config
        )

    all_missing_deps = print_requirements(requirements_section, optional_requirements)
    config.missing_deps = all_missing_deps

    test_requirements = optional_requirements.pop(config.extras_require_test, [])
    test_section = compose_test_section(metadata, test_requirements)

    about_section = {
        "home": metadata["url"] if metadata.get("url") else metadata.get("project_url"),
        "summary": metadata.get("summary"),
        "doc_url": metadata.get("doc_url"),
        "dev_url": metadata.get("dev_url"),
        "license": license_name,
        "license_file": license_file,
    }

    source_section = metadata.get("source", {})

    build_section = {"entry_points": metadata.get("entry_points")}

    outputs = []
    if optional_requirements:
        if config.extras_require_split:
            # First output is the package itself. Inherits all top-level
            # recipe sections like 'requirements', 'build', 'test'.
            outputs.append({"name": name})

            # Other outputs are empty and only add extra dependencies. Does
            # not inherit any top-level section.
            output_req_section = dict(requirements_section)
            output_req_section["run"] = [
                s for s in output_req_section.get("run", []) if "python" in s
            ]
            for option, req_list in optional_requirements.items():
                req_section = dict(output_req_section)
                req_section["run"] = list(req_section["run"])
                req_section["run"].append(
                    f"{{{{ pin_subpackage('{name}', exact=True) }}}}"
                )
                req_section["run"].extend(req_list)
                output = {
                    "name": f"{name}-{option}",
                    "requirements": req_section,
                }
                if test_section:
                    output["test"] = test_section
                outputs.append(output)
        else:
            # Sort options in terms of inclusion
            optional_requirements_items = list()
            for option, req_list in optional_requirements.items():
                for _idx, (_, req_list2) in enumerate(optional_requirements_items):
                    if set(req_list).issubset(req_list2):
                        break
                else:
                    _idx = len(optional_requirements_items)
                optional_requirements_items.insert(_idx, (option, req_list))

            # Add options to run requirements
            for option, req_list in optional_requirements_items:
                req_list = [s for s in req_list if s not in requirements_section["run"]]
                if not req_list:
                    continue
                requirements_section["run"] += [f"# Extra: {option}"] + req_list

    if outputs:
        package_section = {"name": name, "version": metadata["version"]}
        return {
            "package": package_section,
            "build": build_section,
            "requirements": requirements_section,
            "outputs": outputs,
            "test": test_section,
            "about": about_section,
            "source": source_section,
        }
    else:
        package_section = {"name": name, "version": metadata["version"]}
        return {
            "package": package_section,
            "build": build_section,
            "requirements": requirements_section,
            "test": test_section,
            "about": about_section,
            "source": source_section,
        }


def update_recipe(recipe: Recipe, config: Configuration, all_sections: List[str]):
    """Update one specific section."""
    from souschef.section import Section

    metadata = get_metadata(recipe, config)
    for section in all_sections:
        if metadata.get(section):
            if section == "package":
                package_metadata = dict(metadata[section])
                if package_metadata["name"].lower() == config.name.lower():
                    package_metadata.pop("name")
                else:
                    package_metadata["name"] = package_metadata["name"].replace(
                        config.name, "<{ name|lower }}"
                    )

                set_global_jinja_var(recipe, "version", package_metadata["version"])
                config.version = package_metadata["version"]
                package_metadata["version"] = "<{ version }}"

                recipe[section].update(package_metadata)
            elif section in recipe and isinstance(recipe[section], Section):
                recipe[section].update(metadata[section])
            else:
                recipe.add_section({section: metadata[section]})

    if not config.is_arch:
        recipe["build"]["noarch"] = "python"
        if "outputs" in recipe:
            for output in recipe["outputs"]:
                if output["name"].lower() == config.name.lower():
                    continue  # inherits top-level sections
                if "build" not in output:
                    output["build"] = dict()
                output["build"]["noarch"] = "python"


def extract_requirements(metadata: dict, config, recipe) -> Dict[str, List[str]]:
    """Extract the requirements for `build`, `host` and `run`"""
    name = metadata["name"]
    requires_dist = format_dependencies(metadata.get("requires_dist", []), name)
    setup_requires = metadata.get("setup_requires", [])
    host_req = format_dependencies(setup_requires or [], config.name)
    if not requires_dist and not host_req and not metadata.get("requires_python"):
        if config.is_strict_cf:
            py_constrain = (
                f" >={config.py_cf_supported[0].major}"
                f".{config.py_cf_supported[0].minor}"
            )
            return {
                "host": [f"python {py_constrain}", "pip"],
                "run": [f"python {py_constrain}"],
            }
        else:
            return {"host": ["python", "pip"], "run": ["python"]}

    run_req = get_run_req_from_requires_dist(requires_dist, config)
    host_req = get_run_req_from_requires_dist(host_req, config)
    build_req = [f"<{{ compiler('{c}') }}}}" for c in metadata.get("compilers", [])]
    if build_req:
        config.is_arch = True

    if config.is_arch:
        if version_to_selector := py_version_to_selector(metadata, config):
            try:
                recipe["build"]["skip"] = True
            except (TypeError, KeyError):
                recipe.add_section({"build": {"skip": True}})
            recipe["build"]["skip"].inline_comment = version_to_selector
        limit_python = ""
    else:
        limit_python = py_version_to_limit_python(metadata, config)

    limit_python = f" {limit_python}" if limit_python else ""

    if "pip" not in host_req:
        host_req += [f"python{limit_python}", "pip"]
    run_req.insert(0, f"python{limit_python}")

    if config.is_strict_cf:
        host_req = remove_selectors_pkgs_if_needed(host_req)
        run_req = remove_selectors_pkgs_if_needed(run_req)
    result = {}
    if build_req:
        result = {
            "build": rm_duplicated_deps(sort_reqs(map(lambda x: x.lower(), build_req)))
        }

    result.update(
        {
            "host": rm_duplicated_deps(sort_reqs(map(lambda x: x.lower(), host_req))),
            "run": rm_duplicated_deps(sort_reqs(map(lambda x: x.lower(), run_req))),
        }
    )
    update_requirements_with_pin(result)
    return result


def sort_reqs(reqs: Iterable[str], alphabetize: bool = False) -> List[str]:
    """Sort requirements. Put python first, then optionally sort alphabetically."""
    reqs_list = list(reqs)

    def is_python(req: str) -> bool:
        return req == "python" or req.startswith("python ")

    python_reqs = [req for req in reqs_list if is_python(req)]
    non_python_reqs = [req for req in reqs_list if not is_python(req)]
    if alphabetize:
        non_python_reqs.sort()
    result = python_reqs + non_python_reqs
    return result


def remove_selectors_pkgs_if_needed(
    list_req: List, config_file: Optional[Path] = None
) -> List:
    info_pkgs = _get_track_info_from_file(config_file or PYPI_CONFIG)
    re_selector = re.compile(r"\s+#\s+\[.*", re.DOTALL)
    result = []
    for pkg in list_req:
        pkg_cfg_info = info_pkgs.get(pkg.strip().split()[0], {})
        if pkg_cfg_info.get("avoid_selector", False):
            pkg = re_selector.sub("", pkg)
        result.append(pkg)
    return result


def extract_optional_requirements(metadata: dict, config) -> Dict[str, List[str]]:
    """Extract all optional requirements that are specified in the configuration"""
    keys = set()
    if config.extras_require_all:
        extras_require = metadata.get("extras_require")
        if extras_require:
            keys.update(extras_require.keys())
    if config.extras_require_include:
        keys.update(config.extras_require_include)
    if config.extras_require_exclude:
        keys -= set(config.extras_require_exclude)
    if config.extras_require_test:
        keys.add(config.extras_require_test)
    result = dict()
    for key in sorted(keys):
        requirements = metadata["extras_require"].get(key)
        if requirements:
            result[key] = format_dependencies(requirements, metadata["name"])
    return result


def normalize_requirements_list(requirements: List[str], config) -> List[str]:
    """Adapt requirements to PEP440, Conda and Conda-Forge"""
    requirements = solve_list_pkg_name(requirements, PYPI_CONFIG)
    requirements = ensure_pep440_in_req_list(requirements)
    if config.is_strict_cf:
        requirements = clean_deps_for_conda_forge(
            requirements, config.py_cf_supported[0]
        )
    return requirements


def compose_test_section(metadata: dict, test_requirements: List[str]) -> dict:
    test_imports = get_test_imports(metadata, metadata["name"])
    test_requirements = ["pip"] + test_requirements
    test_commands = ["pip check"]
    if any("pytest" in req for req in test_requirements):
        test_commands.extend(f"pytest --pyargs {module}" for module in test_imports)
    test_commands.extend(get_test_entry_points(metadata.get("entry_points", [])))
    return {
        "imports": test_imports,
        "commands": test_commands,
        "requires": test_requirements,
    }
