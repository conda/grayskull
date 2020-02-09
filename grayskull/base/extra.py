from subprocess import check_output

import requests


def _get_git_current_user_metadata() -> dict:
    git_out = check_output(["git", "config", "user.name"])
    return requests.get(
        url="https://api.github.com/search/users", params={"q": git_out.strip()},
    ).json()


def get_git_current_user() -> str:
    try:
        github_search = _get_git_current_user_metadata()
        if github_search["total_count"] == 1:
            github_login = github_search["items"][0]["login"]
            return github_login
    except Exception:
        pass
    return "AddYourGitHubIdHere"
