from dataclasses import dataclass, field
from subprocess import check_output
from typing import List

import requests


@dataclass
class Extra:
    recipe_maintainers: List[str] = field(default_factory=list)

    def add_maintainer(self, name: str):
        self.recipe_maintainers.append(name)

    def add_r_group(self):
        self.recipe_maintainers.append(r"conda-forge/r")

    @staticmethod
    def _get_git_current_user_metadata() -> dict:
        git_out = check_output(["git", "config", "user.name"])
        return requests.get(
            url="https://api.github.com/search/users", params={"q": git_out.strip()},
        ).json()

    def add_git_current_user(self) -> str:
        try:
            github_search = Extra._get_git_current_user_metadata()
            if github_search["total_count"] == 1:
                github_login = github_search["items"][0]["login"]
                self.recipe_maintainers.append(github_login)
                return github_login
        except Exception:
            pass
        self.recipe_maintainers.append("AddYourGitHubIdHere")
        return "AddYourGitHubIdHere"
