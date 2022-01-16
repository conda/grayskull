import argparse
import logging
import os
import sys
from typing import List, Optional

import requests
from colorama import Fore, Style, init
from colorama.ansi import clear_screen

import grayskull
from grayskull.base.factory import GrayskullFactory
from grayskull.base.github import get_git_current_user
from grayskull.cli import CLIConfig
from grayskull.cli.stdout import print_msg
from grayskull.config import Configuration
from grayskull.utils import generate_recipe, origin_is_github

init(autoreset=True)
logging.basicConfig(format="%(levelname)s:%(message)s")


def main(args=None):
    if not args:
        args = sys.argv[1:] or ["--help"]

    parser = argparse.ArgumentParser(description="Grayskull - Conda recipe generator")
    pypi_parser = parser.add_subparsers(help="Options to generate PyPI recipes")
    pypi_cmds = pypi_parser.add_parser("pypi", help="Generate recipes based on PyPI")
    pypi_cmds.add_argument(
        "pypi_packages", nargs="+", help="Specify the PyPI packages name.", default=[]
    )
    pypi_cmds.add_argument(
        "--download",
        "-d",
        dest="download",
        action="store_true",
        default=False,
        help="Download the sdist package and PyPI information in the same folder"
        " the recipe is located.",
    )
    pypi_cmds.add_argument(
        "--maintainers",
        "-m",
        dest="maintainers",
        nargs="+",
        help="List of maintainers which will be added to the recipe.",
    )
    parser.add_argument(
        "--version",
        "-v",
        default=False,
        action="store_true",
        dest="version",
        help="Print Grayskull version and exit",
    )
    parser.add_argument(
        "--heman",
        "--shera",
        default=False,
        action="store_true",
        dest="grayskull_power",
        help=argparse.SUPPRESS,
    )
    pypi_cmds.add_argument(
        "--output",
        "-o",
        dest="output",
        default=".",
        help="Path to where the recipe will be created",
    )
    pypi_cmds.add_argument(
        "--stdout",
        dest="stdout",
        default=True,
        help="Disable or enable stdout, if it is False, Grayskull"
        " will disable the prints. Default is True",
    )
    pypi_cmds.add_argument(
        "--list-missing-deps",
        default=False,
        action="store_true",
        dest="list_missing_deps",
        help="After the execution Grayskull will print all the missing dependencies.",
    )
    pypi_cmds.add_argument(
        "--strict-conda-forge",
        default=False,
        action="store_true",
        dest="is_strict_conda_forge",
        help="It will generate the recipes strict for the conda-forge channel.",
    )
    pypi_cmds.add_argument(
        "--pypi-url",
        default="https://pypi.org/pypi/",
        dest="url_pypi_metadata",
        help="Pypi url server",
    )

    args = parser.parse_args(args)

    if args.version:
        print(grayskull.__version__)
        return

    logging.debug(f"All arguments received: args: {args}")

    if args.grayskull_power:
        print(
            f"{Fore.BLUE}By the power of Grayskull...\n"
            f"{Style.BRIGHT}I have the power!"
        )
        return

    CLIConfig().stdout = args.stdout
    CLIConfig().list_missing_deps = args.list_missing_deps

    print_msg(Style.RESET_ALL)
    print_msg(clear_screen())

    for pkg_name in args.pypi_packages:
        logging.debug(f"Starting grayskull for pkg: {pkg_name}")
        pypi_label = "" if origin_is_github(pkg_name) else " (pypi)"
        print_msg(
            f"{Fore.GREEN}\n\n"
            f"#### Initializing recipe for "
            f"{Fore.BLUE}{pkg_name}{pypi_label} {Fore.GREEN}####\n"
        )
        try:
            recipe, config = create_python_recipe(
                pkg_name,
                is_strict_cf=args.is_strict_conda_forge,
                download=args.download,
                url_pypi_metadata=args.url_pypi_metadata,
            )
        except requests.exceptions.HTTPError as err:
            print_msg(f"{Fore.RED}Package seems to be missing.\nException: {err}\n\n")
            continue

        add_extra_section(recipe, args.maintainers)

        generate_recipe(recipe, config, args.output)
        print_msg(
            f"\n{Fore.GREEN}#### Recipe generated on "
            f"{os.path.realpath(args.output)} for {pkg_name} ####\n"
        )


def create_python_recipe(pkg_name, **kwargs):
    config = Configuration(name=pkg_name, **kwargs)
    return GrayskullFactory.create_recipe("pypi", config, pkg_name), config


def add_extra_section(recipe, maintainers: Optional[List] = None):
    maintainers = maintainers or [get_git_current_user()]
    if "extra" in recipe:
        recipe["extra"]["recipe-maintainers"] = maintainers
    else:
        recipe.add_section({"extra": {"recipe-maintainers": maintainers}})
    prefix = f"\n   - {Fore.LIGHTMAGENTA_EX}"
    print_msg(f"\nMaintainers:{prefix}{prefix.join(maintainers)}")


if __name__ == "__main__":
    main(sys.argv[1:])
