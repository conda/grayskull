import base64
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
from fuzzywuzzy import process
from fuzzywuzzy.fuzz import token_sort_ratio
from requests import HTTPError

from grayskull.license.data import get_all_licenses  # noqa


@dataclass
class ShortLicense:
    name: str
    path: Union[str, Path]
    is_packaged: bool


@lru_cache(maxsize=10)
def get_all_licenses_from_opensource() -> List:
    response = requests.get(url="https://api.opensource.org/licenses", timeout=5)
    if response.status_code != 200:
        raise HTTPError(
            f"It was not possible to communicate with opensource api.\n{response.text}"
        )
    return response.json()


def match_license(name: str) -> dict:
    all_licenses = get_all_licenses_from_opensource()
    name = name.strip()
    name = re.sub(r"\s*License\s*", "", name, re.IGNORECASE)

    best_match = process.extractOne(
        name, _get_all_license_choice(all_licenses), scorer=token_sort_ratio
    )
    return _get_license(best_match[0], all_licenses)


def get_short_license_id(name: str) -> str:
    recipe_license = match_license(name)
    for identifier in recipe_license["identifiers"]:
        if identifier["scheme"].lower() == "spdx":
            return identifier["identifier"]
    return recipe_license["id"]


def _get_license(license_id: str, all_licenses: List) -> dict:
    for one_license in all_licenses:
        if license_id in _get_all_names_from_api(one_license):
            return one_license


def _get_all_names_from_api(one_license: dict) -> List:
    result = set()
    if one_license["name"]:
        result.add(one_license["name"])
    if one_license["id"]:
        result.add(one_license["id"])
    result = result.union({i["identifier"] for i in one_license["identifiers"]})
    result = result.union({l["name"] for l in one_license["other_names"]})
    return list(result)


def _get_all_license_choice(all_licenses: List) -> List:
    all_choices = []
    for api_license in all_licenses:
        all_choices += _get_all_names_from_api(api_license)
    return all_choices


def search_license_file(
    folder_path: str,
    git_url: Optional[str] = None,
    version: Optional[str] = None,
    license_name_metadata: Optional[str] = None,
) -> Optional[ShortLicense]:
    if license_name_metadata:
        license_name_metadata = get_short_license_id(license_name_metadata)

    license_sdist = search_license_folder(folder_path, license_name_metadata)
    if license_sdist:
        license_sdist.is_packaged = True
        license_sdist.path = os.path.relpath(license_sdist.path, folder_path)
        license_sdist.path = license_sdist.path.replace("\\", "/")

        splited = license_sdist.path.split("/")
        if len(splited) > 1:
            license_sdist.path = "/".join(splited[1:])
        return license_sdist

    if not git_url:
        return None

    github_license = search_license_api_github(git_url, version, license_name_metadata)
    if github_license:
        return github_license

    repo_license = search_license_repo(git_url, version, license_name_metadata)
    if repo_license:
        return repo_license
    return None


@lru_cache(maxsize=13)
def search_license_api_github(
    github_url: str, version: Optional[str] = None, default: Optional[str] = "Other"
) -> Optional[ShortLicense]:
    github_url = _get_api_github_url(github_url, version)

    response = requests.get(url=github_url, timeout=5)
    if response.status_code != 200:
        return None

    json_content = response.json()
    license_content = base64.b64decode(json_content["content"]).decode("utf-8")
    file_path = os.path.join(mkdtemp(prefix="github-license-"), "LICENSE")
    with open(file_path, "w") as f:
        f.write(license_content)
    return ShortLicense(
        json_content.get("license", {}).get("spdx_id", default), file_path, False
    )


def _get_api_github_url(github_url: str, version: Optional[str] = None) -> str:
    github_url = re.sub(r"github.com", "api.github.com/repos", github_url)
    if github_url[-1] != "/":
        github_url += "/"

    github_url += "license"
    return f"{github_url}?ref={version}" if version else github_url


def search_license_folder(
    path: Union[str, Path], default: Optional[str] = None
) -> Optional[ShortLicense]:
    re_search = re.compile(
        r"(\bcopyright\b|\blicense[s]*\b|\bcopying\b|\bcopyleft\b)", re.IGNORECASE
    )
    for folder_path, _, filenames in os.walk(str(path)):
        for one_file in filenames:
            if re_search.match(one_file):
                lc_path = os.path.join(folder_path, one_file)
                return ShortLicense(get_license_type(lc_path, default), lc_path, False)
    return None


def search_license_repo(
    git_url: str, version: Optional[str], default: Optional[str] = None
) -> Optional[ShortLicense]:
    git_url = re.sub(r"/$", ".git", git_url)
    git_url = git_url if git_url.endswith(".git") else f"{git_url}.git"

    tmp_dir = mkdtemp(prefix="gs-clone-repo-")
    try:
        check_output(_get_git_cmd(git_url, version, tmp_dir))
    except Exception as err:  # noqa
        return None
    return search_license_folder(str(tmp_dir), default)


def _get_git_cmd(git_url: str, version: str, dest) -> List[str]:
    git_cmd = ["git", "clone"]
    if version:
        git_cmd += ["-b", version]
    return git_cmd + [git_url, str(dest)]


def get_license_type(path_license: str, default: Optional[str] = None) -> Optional[str]:
    with open(path_license, "r") as license_file:
        license_content = license_file.read()

    all_licenses = get_all_licenses()
    licenses_text = list(map(itemgetter(1), all_licenses))
    best_match = process.extractOne(
        license_content, licenses_text, scorer=token_sort_ratio
    )
    if default and best_match[1] < 76:
        return default
    index_license = licenses_text.index(best_match[0])
    return all_licenses[index_license][0]
