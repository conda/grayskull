import re
from contextlib import contextmanager
from copy import deepcopy
from typing import Dict

import progressbar
from colorama import Fore, Style

from grayskull.base.pkg_info import is_pkg_available
from grayskull.cli import WIDGET_BAR_DOWNLOAD, CLIConfig


def print_msg(msg: str):
    if CLIConfig().stdout:
        print(msg)


@contextmanager
def manage_progressbar(*, max_value: int, prefix: str):
    if CLIConfig().stdout:
        with progressbar.ProgressBar(
            widgets=deepcopy(WIDGET_BAR_DOWNLOAD),
            max_value=max_value,
            prefix=prefix,
        ) as bar:
            yield bar
    else:

        class DisabledBar:
            def update(self, *args, **kargs):
                pass

        yield DisabledBar()


@contextmanager
def progressbar_with_status(max_value: int):
    if CLIConfig().stdout:
        with progressbar.ProgressBar(
            widgets=[
                " ",
                progressbar.Percentage(),
                " ",
                progressbar.Bar(),
                "[",
                progressbar.Timer(),
                "]",
            ],
            prefix="Checking >> {variables.pkg_name}",
            variables={"pkg_name": "--"},
            max_value=max_value,
        ) as bar:
            yield bar
    else:

        class DisabledBar:
            def update(self, *args, **kargs):
                pass

        yield DisabledBar()


def print_requirements(all_requirements: Dict):
    if not CLIConfig().stdout:
        return

    re_search = re.compile(r"^\s*([a-z0-9\.\-\_]+)(.*)", re.IGNORECASE | re.DOTALL)
    all_missing_deps = set()

    def print_req(list_pkg):
        if isinstance(list_pkg, str):
            list_pkg = [list_pkg]
        for pkg in list_pkg:
            if not pkg:
                continue

            search_result = re_search.search(pkg)
            if pkg.strip().startswith("{{") or pkg.strip().startswith("<{"):
                pkg_name = pkg.replace("<{", "{{")
                options = ""
                colour = Fore.GREEN
            elif search_result:
                pkg_name, options = search_result.groups()
                if is_pkg_available(pkg_name):
                    colour = Fore.GREEN
                else:
                    all_missing_deps.add(pkg_name)
                    colour = Fore.RED
            else:
                continue
            print_msg(f"  - {colour}{Style.BRIGHT}{pkg_name}{Style.RESET_ALL}{options}")

    if all_requirements.get("build"):
        print_msg("Build requirements:")
        print_req(sorted(all_requirements.get("build", [])))
    print_msg("Host requirements:")
    print_req(sorted(all_requirements.get("host", [])))
    print_msg("\nRun requirements:")
    print_req(sorted(all_requirements.get("run", [])))
    print_msg(f"\n{Fore.RED}RED{Style.RESET_ALL}: Missing packages")
    print_msg(f"{Fore.GREEN}GREEN{Style.RESET_ALL}: Packages available on conda-forge")
    if CLIConfig().list_missing_deps:
        if all_missing_deps:
            print_msg(f"Missing dependencies: {', '.join(all_missing_deps)}")
        else:
            print_msg("All dependencies are already on conda-forge.")
    return all_missing_deps
