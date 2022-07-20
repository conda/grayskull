import base64
import json
import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from operator import itemgetter
from pathlib import Path
from subprocess import check_output
from tempfile import mkdtemp
from typing import List, Optional, Union

import requests
from colorama import Fore
from rapidfuzz import process
from rapidfuzz.fuzz import token_set_ratio, token_sort_ratio

from grayskull.cli.stdout import print_msg
from grayskull.license.data import get_all_licenses  # noqa

log = logging.getLogger(__name__)


@dataclass
class ShortLicense:
    name: str
    path: Union[str, Path, None]
    is_packaged: bool


@lru_cache(maxsize=10)
def get_all_licenses_from_spdx() -> List:
    """Get all licenses available on spdx.org

    :return: List with all licenses information on spdx.org
    """
    try:
        response = requests.get(
            url="https://spdx.org/licenses/licenses.json", timeout=5
        )
    except requests.exceptions.ConnectionError:
        log.info(
            "SPDX licence server didn't respond. Grayskull will continue without that."
        )
        return []
    log.debug(
        f"Response from spdx.org. Status code:{response.status_code},"
        f" response: {response}"
    )
    if response.status_code != 200:
        raise requests.HTTPError(
            f"It was not possible to communicate with spdx api.\n{response.text}"
        )
    print_msg("Recovering license info from spdx.org ...")
    return [
        lic
        for lic in response.json()["licenses"]
        if not lic.get("isDeprecatedLicenseId", False)
    ]


def match_license(name: str) -> dict:
    """Match if the given license name matches any license present on
    spdx.org

    :param name: License name
    :return: Information of the license matched
    """
    all_licenses = get_all_licenses_from_spdx()
    if not all_licenses:
        return {}
    name = re.sub(r"\s+license\s*", "", name.strip(), flags=re.IGNORECASE)

    best_matches = process.extract(name, _get_all_license_choice(all_licenses))
    spdx_license = best_matches[0]
    if spdx_license[1] != 100:
        best_matches = [lic[0] for lic in best_matches if not lic[0].endswith("-only")]

        if best_matches:
            best_matches = process.extract(name, best_matches, scorer=token_set_ratio)
            spdx_license = best_matches[0]
            best_matches = [lic[0] for lic in best_matches if lic[1] >= spdx_license[1]]
            if len(best_matches) > 1:
                spdx_license = process.extractOne(
                    name, best_matches, scorer=token_sort_ratio
                )

    log.info(
        f"Best match for license {name} was {spdx_license}.\n"
        f"Best matches: {best_matches}"
    )

    return _get_license(spdx_license[0], all_licenses)


def get_short_license_id(name: str) -> str:
    """Get the spdx identifier for the given license name

    :param name: License name
    :return: short identifier (spdx) for the given license name
    """
    recipe_license = match_license(name)
    if not recipe_license:
        return "IT-WAS-NOT-POSSIBLE-TO-RECOVER-LICENCE"
    return recipe_license["licenseId"]


def _get_license(license_id: str, all_licenses: List) -> dict:
    """Search for the license identification in all licenses received

    :param license_id: license identification
    :param all_licenses: List with all licenses
    :return: Dict with the information of the license desired
    """
    for one_license in all_licenses:
        if license_id in _get_all_names_from_api(one_license):
            return one_license


def _get_all_names_from_api(one_license: dict) -> List:
    """Get the names and other names which each license has.

    :param one_license: License name
    :return: List of all names which the given license is know of
    """
    result = set()
    if one_license["name"]:
        result.add(one_license["name"])
    if one_license["licenseId"]:
        result.add(one_license["licenseId"])
    other_names = get_other_names_from_opensource(one_license["licenseId"])
    result.update(other_names)
    return list(result)


def get_other_names_from_opensource(license_spdx: str) -> List:
    lic = get_opensource_license(license_spdx)
    return [_license["name"] for _license in lic.get("other_names", [])]


def get_opensource_license(license_spdx: str) -> dict:
    opensource = get_opensource_license_data()
    for lic in opensource:
        if lic["id"] == license_spdx:
            return lic
        for _id in lic["identifiers"]:
            if _id["scheme"].lower() == "spdx" and license_spdx == _id["identifier"]:
                return lic
    return {}


def read_licence_cache():
    with open(Path(__file__).parent / "licence_cache.json", "r") as licence_cache:
        return json.load(licence_cache)


@lru_cache(maxsize=10)
def get_opensource_license_data() -> List:
    try:
        response = requests.get(url="https://api.opensource.org/licenses/", timeout=5)
    except requests.exceptions.RequestException:
        return read_licence_cache()
    if response.status_code != 200:
        return read_licence_cache()
    return response.json()


def _get_all_license_choice(all_licenses: List) -> List:
    """Function responsible to get the whole licenses name

    :param all_licenses: list with all licenses
    :return: list with all names which each license may have
    """
    all_choices = []
    for api_license in all_licenses:
        all_choices += _get_all_names_from_api(api_license)
    return all_choices


def search_license_file(
    folder_path: str,
    git_url: Optional[str] = None,
    version: Optional[str] = None,
    license_name_metadata: Optional[str] = None,
) -> List[ShortLicense]:
    """Search for the license file. First it will try to find it in the given
    folder, after that it will search on the github api and for the last it will
    clone the repository and it will search for the license there.

    :param folder_path: Path where the sdist package was unpacked
    :param git_url: URL for the Github repository
    :param version: Package version
    :param license_name_metadata: Default value for the license type
    :return: ShortLicense with the information regarding the license
    """
    if license_name_metadata:
        license_name_metadata = get_short_license_id(license_name_metadata)

    all_license_sdist = search_license_folder(folder_path, license_name_metadata)
    for license_sdist in all_license_sdist:
        license_sdist.is_packaged = True
        license_sdist.path = os.path.relpath(license_sdist.path, folder_path)
        license_sdist.path = license_sdist.path.replace("\\", "/")

        splited = license_sdist.path.split("/")
        if len(splited) > 1:
            license_sdist.path = "/".join(splited[1:])
    if all_license_sdist:
        return all_license_sdist

    if not git_url:
        return [ShortLicense(license_name_metadata, None, False)]

    github_license = search_license_api_github(git_url, version, license_name_metadata)
    if github_license:
        return [github_license]

    repo_license = search_license_repo(git_url, version, license_name_metadata)
    if repo_license:
        return repo_license
    return [ShortLicense(license_name_metadata, None, False)]


@lru_cache(maxsize=13)
def search_license_api_github(
    github_url: str, version: Optional[str] = None, default: Optional[str] = "Other"
) -> Optional[ShortLicense]:
    """Search for the license asking in the github api

    :param github_url: GitHub URL
    :param version: Package version
    :param default: default license type
    :return: License information
    """
    if github_url.endswith("/"):
        github_url = github_url[:-1]
    github_url = _get_api_github_url(github_url, version)
    log.info(f"Github url: {github_url} - recovering license info")
    print_msg("Recovering license information from github...")

    response = requests.get(url=github_url, timeout=10)
    if response.status_code != 200:
        return None

    json_content = response.json()
    license_content = base64.b64decode(json_content["content"]).decode("utf-8")
    file_path = os.path.join(mkdtemp(prefix="github-license-"), json_content["name"])
    with open(file_path, "w") as f:
        f.write(license_content)
    return ShortLicense(
        json_content.get("license", {}).get("spdx_id", default), file_path, False
    )


def _get_api_github_url(github_url: str, version: Optional[str] = None) -> str:
    """Try to presume the github url

    :param github_url: GitHub URL
    :param version: package version
    :return: GitHub URL
    """
    github_url = re.sub(r"github.com", "api.github.com/repos", github_url)
    if github_url[-1] != "/":
        github_url += "/"

    github_url += "license"
    return f"{github_url}?ref={version}" if version else github_url


def search_license_folder(
    path: Union[str, Path], default: Optional[str] = None
) -> Optional[ShortLicense]:
    """Search for the license in the given folder

    :param path: Sdist folder
    :param default: Default value for the license type
    :return: License information
    """
    re_search = re.compile(
        r"(\bcopyright\b|\bnotice\b|\blicense[s]*\b|\bcopying\b|\bcopyleft\b)",
        re.IGNORECASE,
    )
    all_licences = []
    for folder_path, dirnames, filenames in os.walk(str(path)):
        if os.path.basename(folder_path).startswith("."):
            continue
        dirnames[:] = [
            folder
            for folder in dirnames
            if folder not in ("doc", "theme", "themes", "docs")
        ]
        for one_file in filenames:
            if re_search.match(one_file):
                lc_path = os.path.join(folder_path, one_file)
                all_licences.append(
                    ShortLicense(get_license_type(lc_path, default), lc_path, False)
                )
    return all_licences


def search_license_repo(
    git_url: str, version: Optional[str], default: Optional[str] = None
) -> Optional[List[ShortLicense]]:
    """Search for the license file in the given github repository

    :param git_url: GitHub URL
    :param version: Package version
    :param default: Default value for the license type
    :return: License information
    """
    git_url = re.sub(r"/$", ".git", git_url)
    git_url = git_url if git_url.endswith(".git") else f"{git_url}.git"
    print_msg("Recovering license info from repository...")
    tmp_dir = mkdtemp(prefix="gs-clone-repo-")
    try:
        check_output(_get_git_cmd(git_url, version, tmp_dir))
    except Exception as err:
        log.debug(
            f"Exception occurred when gs was trying to clone the repository."
            f" url: {git_url}, version: {version}. Exception: {err}"
        )
        if not version.startswith("v"):
            return search_license_repo(git_url, f"v{version}", default)
        return None
    return search_license_folder(str(tmp_dir), default)


def _get_git_cmd(git_url: str, version: str, dest) -> List[str]:
    """Return the full git command to clone the repository

    :param git_url: GitHub URL
    :param version: Package version
    :param dest: Folder destination
    :return: git command to clone the repository
    """
    git_cmd = ["git", "clone"]
    if version:
        git_cmd += ["-b", version]
    return git_cmd + [git_url, str(dest)]


def get_license_type(path_license: str, default: Optional[str] = None) -> Optional[str]:
    """Function tries to match the license with one of the models present in
    grayskull/license/data

    :param path_license: Path to the license file
    :param default: Default value for the license type
    :return: License type
    """
    with open(path_license, "r") as license_file:
        license_content = license_file.read()
    find_apache = re.findall(
        r"apache\.org\/licenses\/LICENSE\-([0-9])\.([0-9])",
        license_content,
        re.IGNORECASE,
    )
    if find_apache:
        lic_type = find_apache[0]
        return f"Apache-{lic_type[0]}.{lic_type[1]}"
    print_msg("Matching license file with database from Grayskull...")
    all_licenses = get_all_licenses()
    licenses_text = list(map(itemgetter(1), all_licenses))
    best_match = process.extract(
        license_content, licenses_text, scorer=token_sort_ratio
    )
    print_msg(
        f"{Fore.YELLOW}Match percentage of the license is {int(best_match[0][1])}%. "
        + "Low match percentage could mean that the license was modified."
    )

    if default and best_match[0][1] < 51:
        log.info(f"Match too low for recipe {best_match}, using the default {default}")
        return default

    higher_match = best_match[0]
    equal_values = [val[0] for val in best_match if val[1] > (higher_match[1] - 3)]
    if len(equal_values) > 1:
        higher_match = process.extractOne(
            license_content, equal_values, scorer=token_set_ratio
        )
    index_license = licenses_text.index(higher_match[0])
    return all_licenses[index_license][0]
