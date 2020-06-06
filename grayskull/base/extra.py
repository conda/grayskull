import logging
import subprocess

import requests
from colorama import Fore

from grayskull.cli.stdout import print_msg

log = logging.getLogger(__name__)


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
