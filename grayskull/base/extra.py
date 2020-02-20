import subprocess

import requests


def get_git_current_user_metadata() -> dict:
    git_out = subprocess.check_output(["git", "config", "user.name"])
    return requests.get(
        url="https://api.github.com/search/users", params={"q": git_out.strip()},
    ).json()


def get_git_current_user() -> str:
    try:
        github_search = get_git_current_user_metadata()
        if github_search["total_count"] == 1:
            return github_search["items"][0]["login"]
    except Exception as err:  # noqa
        pass
    return "AddYourGitHubIdHere"
