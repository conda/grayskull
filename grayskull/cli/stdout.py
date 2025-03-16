import re
from contextlib import contextmanager
from copy import deepcopy

import progressbar
from colorama import Fore, Style

from grayskull.base.pkg_info import is_pkg_available
from grayskull.cli import WIDGET_BAR_DOWNLOAD, CLIConfig
from grayskull.utils import RE_PEP725_PURL


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


def print_requirements(
    requirements: dict[str, list[str]], optional_requirements: dict[str, list[str]]
) -> set:
    all_missing_deps = set()
    re_search = re.compile(r"^\s*([a-z0-9\.\-\_]+)(.*)", re.IGNORECASE | re.DOTALL)

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
            elif RE_PEP725_PURL.match(pkg):
                pkg_name = pkg
                options = ""
                all_missing_deps.add(pkg)
                colour = Fore.YELLOW
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

    keys = ["build", "host", "run"]
    for key in keys:
        print_msg(f"{key.capitalize()} requirements:")
        req_list = requirements.get(key, [])
        if req_list:
            print_req(req_list)
        else:
            print_msg("  <none>")

    for key, req_list in optional_requirements.items():
        print_msg(f"{key.capitalize()} requirements (optional):")
        print_req(req_list)

    print_msg(
        f"\n{Fore.RED}RED{Style.RESET_ALL}: "
        "Package names not available on specified package indexes"
    )
    print_msg(
        f"{Fore.YELLOW}YELLOW{Style.RESET_ALL}: "
        "PEP-725 PURLs that did not map to known package"
    )
    print_msg(
        f"{Fore.GREEN}GREEN{Style.RESET_ALL}: "
        "Packages available on specified package indexes"
    )

    if CLIConfig().list_missing_deps:
        if all_missing_deps:
            indexes = ", ".join(f"'{idx}'" for idx in CLIConfig().package_indexes)
            print_msg(
                f"Missing dependencies (not found in {indexes}): "
                f"{', '.join(all_missing_deps)}"
            )
        else:
            indexes = ", ".join(f"'{idx}'" for idx in CLIConfig().package_indexes)
            print_msg(
                f"All dependencies are already available "
                f"in the specified package indexes ({indexes})."
            )
    return all_missing_deps
