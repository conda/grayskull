import logging
import subprocess
from typing import Any, Tuple, Union
from urllib.parse import urlparse, urlunparse

import requests
from colorama import Fore

from grayskull.cli.stdout import print_msg
from grayskull.utils import string_similarity

log = logging.getLogger(__name__)


def fetch_latest_metadata_from_github_repo(git_url):
    url_parts = urlparse(git_url)
    netloc = "api.github.com"
    path = f"/repos{url_parts.path}/releases/latest"
    api_parts = url_parts.scheme, netloc, path, *url_parts[3:]
    api_url = urlunparse(api_parts)
    response = requests.get(api_url)
    response.raise_for_status()
    return response.json()


def get_latest_version_of_github_repo(git_url: str) -> str:
    """get the latest version of the github repository using github api"""
    return fetch_latest_metadata_from_github_repo(git_url)["tag_name"]


def get_most_similar_tag_in_repo(git_url: str, query: str) -> str:
    """get the most similar tag in the given repository"""
    data = fetch_latest_metadata_from_github_repo(git_url)

    def closest_match(tag):
        return string_similarity(query, tag)

    if isinstance(data, dict):
        most_similar = data["tag_name"]
    else:
        most_similar = max([tag["name"] for tag in data], key=closest_match)
    log.debug(
        f"Most similar git reference found for query `{query}` is `{most_similar}`"
    )
    return most_similar


def handle_gh_version(name: str, version: str, url: str) -> Tuple[Union[str, Any], Any]:
    """Method responsible for handling the version of the GitHub package.
    If version is specified, gets the closest tag in the repo.
    If not, gets the latest version.
    Also trims off 'v'prefix from version names if present.
    """
    if version:
        # try get the tag with the most similar name to the requested version
        version_tag = get_most_similar_tag_in_repo(url, version)
        log.info(f"Closest git reference to `{version}` is `{version_tag}`.")
    else:
        version_tag = get_latest_version_of_github_repo(url)
        log.info(
            f"Version for {name} not specified."
            "\nGetting the latest one, which is {version_tag}."
        )
        version = version_tag
    if version.startswith("v"):
        version = version[1:]
    return version, version_tag


def generate_git_archive_tarball_url(git_url: str, git_ref: str) -> str:
    """This method takes a github repository url and returns the archive
    tarball url for that repository.
    :param git_url: github repository url
    :param git_ref: github repository reference (version, name...)
    :return: github repository archive tarball url
    """
    return f"{git_url}/archive/{git_ref}.tar.gz"


def get_git_current_user_metadata() -> dict:
    git_out = subprocess.check_output(["git", "config", "user.name"])
    return requests.get(
        url="https://api.github.com/search/users",
        params={"q": git_out.strip()},
        timeout=5,
    ).json()


def get_git_current_user() -> str:
    try:
        github_search = get_git_current_user_metadata()
        if github_search["total_count"] >= 1:
            return github_search["items"][0]["login"]
    except Exception as err:
        log.debug(
            f"Exception occurred when trying to recover user information from github."
            f" Exception: {err}"
        )
    print_msg(
        f"Using default recipe maintainer:"
        f" {Fore.LIGHTMAGENTA_EX}AddYourGitHubIdHere"
    )
    return "AddYourGitHubIdHere"
