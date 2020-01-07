from dataclasses import dataclass, field, make_dataclass
from subprocess import check_output
from typing import List

import requests
import yaml


def get_valid_fields(fields):
    return [
        (name.replace("-", "_"), "typing.Any", field(default=None)) for name in fields
    ]


FIELDS = {
    "package": {"name", "version"},
    "source": {
        "fn",
        "url",
        "md5",
        "sha1",
        "sha256",
        "path",
        "path_via_symlink",
        "git_url",
        "git_tag",
        "git_branch",
        "git_rev",
        "git_depth",
        "hg_url",
        "hg_tag",
        "svn_url",
        "svn_rev",
        "svn_ignore_externals",
        "folder",
        "no_hoist",
        "patches",
    },
    "build": {
        "number",
        "string",
        "entry_points",
        "osx_is_app",
        "disable_pip",
        "features",
        "track_features",
        "preserve_egg_dir",
        "no_link",
        "binary_relocation",
        "script",
        "noarch",
        "noarch_python",
        "has_prefix_files",
        "binary_has_prefix_files",
        "ignore_prefix_files",
        "detect_binary_files_with_prefix",
        "skip_compile_pyc",
        "rpaths",
        "rpaths_patcher",
        "script_env",
        "always_include_files",
        "skip",
        "msvc_compiler",
        "pin_depends",
        "include_recipe",  # pin_depends is experimental still
        "preferred_env",
        "preferred_env_executable_paths",
        "run_exports",
        "ignore_run_exports",
        "requires_features",
        "provides_features",
        "force_use_keys",
        "force_ignore_keys",
        "merge_build_host",
    },
    "outputs": {
        "name",
        "version",
        "number",
        "script",
        "script_interpreter",
        "build",
        "requirements",
        "test",
        "about",
        "extra",
        "files",
        "type",
        "run_exports",
    },
    "requirements": {"build", "host", "run", "conflicts", "run_constrained"},
    "app": {"entry", "icon", "summary", "type", "cli_opts", "own_environment"},
    "test": {
        "requires",
        "commands",
        "files",
        "imports",
        "source_files",
        "downstreams",
    },
    "about": {
        "home",
        "dev_url",
        "doc_url",
        "doc_source_url",
        "license_url",  # these are URLs
        "license",
        "summary",
        "description",
        "license_family",  # text
        "identifiers",
        "tags",
        "keywords",  # lists
        "license_file",
        "readme",  # paths in source tree
    },
}


Package = make_dataclass("Package", get_valid_fields(FIELDS["package"]))
Source = make_dataclass("Source", get_valid_fields(FIELDS["source"]))
Build = make_dataclass("Build", get_valid_fields(FIELDS["build"]))
Outputs = make_dataclass("Outputs", get_valid_fields(FIELDS["outputs"]))
Requirements = make_dataclass("Requirements", get_valid_fields(FIELDS["requirements"]))
App = make_dataclass("App", get_valid_fields(FIELDS["app"]))
Test = make_dataclass("Test", get_valid_fields(FIELDS["test"]))
About = make_dataclass("About", get_valid_fields(FIELDS["about"]))


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


class GrayDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super(GrayDumper, self).increase_indent(flow, False)
