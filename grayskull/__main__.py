import argparse
import logging
import os
import sys
from pathlib import Path
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
from grayskull.utils import generate_recipe, origin_is_github, origin_is_local_sdist

init(autoreset=True)
logging.basicConfig(format="%(levelname)s:%(message)s")


def main(args=None):
    if not args:
        args = sys.argv[1:] or ["--help"]

    # create the top-level parser
    parser = argparse.ArgumentParser(description="Grayskull - Conda recipe generator")
    subparsers = parser.add_subparsers(help="sub-command help")
    # create parser for cran
    cran_parser = subparsers.add_parser("cran", help="Options to generate CRAN recipes")
    cran_parser.add_argument(
        "cran_packages", nargs="+", help="Specify the CRAN packages name.", default=[]
    )
    cran_parser.add_argument(
        "--stdout",
        dest="stdout",
        default=True,
        help="Disable or enable stdout, if it is False, Grayskull"
        " will disable the prints. Default is True",
    )
    cran_parser.add_argument(
        "--list-missing-deps",
        default=False,
        action="store_true",
        dest="list_missing_deps",
        help="After the execution Grayskull will print all the missing dependencies.",
    )
    cran_parser.add_argument(
        "--download",
        "-d",
        dest="download",
        action="store_true",
        default=False,
        help="Download the sdist package and PyPI information in the same folder"
        " the recipe is located.",
    )
    cran_parser.add_argument(
        "--maintainers",
        "-m",
        dest="maintainers",
        nargs="+",
        help="List of maintainers which will be added to the recipe.",
    )
    cran_parser.add_argument(
        "--output",
        "-o",
        dest="output",
        default=".",
        help="Path to where the recipe will be created",
    )
    cran_parser.add_argument(
        "--strict-conda-forge",
        default=False,
        action="store_true",
        dest="is_strict_conda_forge",
        help="It will generate the recipes strict for the conda-forge channel.",
    )
    cran_parser.add_argument(
        "--sections",
        "-s",
        default=None,
        required=False,
        choices=(
            "package",
            "source",
            "build",
            "requirements",
            "test",
            "about",
            "extra",
        ),
        nargs="+",
        dest="sections_populate",
        help="If sections are specified, grayskull will populate just the sections "
        "informed.",
    )
    # create parser for pypi
    pypi_parser = subparsers.add_parser("pypi", help="Options to generate PyPI recipes")
    pypi_parser.add_argument(
        "pypi_packages", nargs="+", help="Specify the PyPI packages name.", default=[]
    )
    pypi_parser.add_argument(
        "--download",
        "-d",
        dest="download",
        action="store_true",
        default=False,
        help="Download the sdist package and PyPI information in the same folder"
        " the recipe is located.",
    )
    pypi_parser.add_argument(
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
    pypi_parser.add_argument(
        "--output",
        "-o",
        dest="output",
        default=".",
        help="Path to where the recipe will be created",
    )
    pypi_parser.add_argument(
        "--stdout",
        dest="stdout",
        default=True,
        help="Disable or enable stdout, if it is False, Grayskull"
        " will disable the prints. Default is True",
    )
    pypi_parser.add_argument(
        "--list-missing-deps",
        default=False,
        action="store_true",
        dest="list_missing_deps",
        help="After the execution Grayskull will print all the missing dependencies.",
    )
    pypi_parser.add_argument(
        "--strict-conda-forge",
        default=False,
        action="store_true",
        dest="is_strict_conda_forge",
        help="It will generate the recipes strict for the conda-forge channel.",
    )
    pypi_parser.add_argument(
        "--pypi-url",
        default="https://pypi.org/pypi/",
        dest="url_pypi_metadata",
        help="Pypi url server",
    )
    pypi_parser.add_argument(
        "--recursive",
        "-r",
        default=False,
        action="store_true",
        dest="is_recursive",
        help="Recursively run grayskull on missing dependencies.",
    )
    pypi_parser.add_argument(
        "--sections",
        "-s",
        default=None,
        required=False,
        choices=(
            "package",
            "source",
            "build",
            "requirements",
            "test",
            "about",
            "extra",
        ),
        nargs="+",
        dest="sections_populate",
        help="If sections are specified, grayskull will populate just the sections "
        "informed.",
    )
    pypi_parser.add_argument(
        "--extras-require-test",
        default=None,
        dest="extras_require_test",
        help="Extra requirements to run tests.",
    )
    pypi_parser.add_argument(
        "--tag",
        "-t",
        default=None,
        dest="github_release_tag",
        help="If tag is specified, grayskull will build from release tag",
    )
    pypi_parser.add_argument(
        "--extras-require-all",
        default=False,
        action="store_true",
        dest="extras_require_all",
        help="Include all extra requirements.",
    )
    pypi_parser.add_argument(
        "--extras-require-include",
        default=tuple(),
        type=str,
        nargs="*",
        dest="extras_require_include",
        help="Include these extra requirements.",
    )
    pypi_parser.add_argument(
        "--extras-require-exclude",
        default=tuple(),
        type=str,
        nargs="*",
        dest="extras_require_exclude",
        help="Exclude these extra requirements (overrides include).",
    )
    pypi_parser.add_argument(
        "--extras-require-split",
        default=False,
        action="store_true",
        dest="extras_require_split",
        help="Create a separate conda package for each extra requirements."
        " Ignored when no extra requirements are selected.",
    )
    pypi_parser.add_argument(
        "--licence-exclude-folders",
        default=tuple(),
        nargs="*",
        dest="licence_exclude_folders",
        help="Exclude folders when searching for licence.",
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

    if getattr(args, "pypi_packages", None):
        generate_recipes_from_list(args.pypi_packages, args)
    elif getattr(args, "cran_packages", None):
        generate_r_recipes_from_list(args.cran_packages, args)


def generate_recipes_from_list(list_pkgs, args):
    for pkg_name in list_pkgs:
        logging.debug(f"Starting grayskull for pkg: {pkg_name}")
        from_local_sdist = origin_is_local_sdist(pkg_name)
        if origin_is_github(pkg_name):
            pypi_label = ""
        elif from_local_sdist:
            pypi_label = " (local)"
        else:
            pypi_label = " (pypi)"
        print_msg(
            f"{Fore.GREEN}\n\n"
            f"#### Initializing recipe for "
            f"{Fore.BLUE}{pkg_name}{pypi_label} {Fore.GREEN}####\n"
        )
        if Path(pkg_name).is_file() and (not from_local_sdist):
            args.output = pkg_name
        try:
            recipe, config = create_python_recipe(
                pkg_name,
                is_strict_cf=args.is_strict_conda_forge,
                download=args.download,
                url_pypi_metadata=args.url_pypi_metadata,
                sections_populate=args.sections_populate,
                from_local_sdist=from_local_sdist,
                extras_require_test=args.extras_require_test,
                github_release_tag=args.github_release_tag,
                extras_require_include=tuple(args.extras_require_include),
                extras_require_exclude=tuple(args.extras_require_exclude),
                extras_require_all=args.extras_require_all,
                extras_require_split=args.extras_require_split,
                licence_exclude_folders=args.licence_exclude_folders,
            )
        except requests.exceptions.HTTPError as err:
            print_msg(f"{Fore.RED}Package seems to be missing.\nException: {err}\n\n")
            continue

        if args.sections_populate is None or "extra" in args.sections_populate:
            add_extra_section(recipe, args.maintainers)

        generate_recipe(recipe, config, args.output)
        print_msg(
            f"\n{Fore.GREEN}#### Recipe generated on "
            f"{os.path.realpath(args.output)} for {pkg_name} ####\n\n"
        )

        if args.is_recursive and config.missing_deps:
            generate_recipes_from_list(config.missing_deps, args)


def create_python_recipe(pkg_name, sections_populate=None, **kwargs):
    config = Configuration(name=pkg_name, **kwargs)
    return (
        GrayskullFactory.create_recipe(
            "pypi", config, sections_populate=sections_populate
        ),
        config,
    )


def generate_r_recipes_from_list(list_pkgs, args):
    cran_label = " (cran)"
    for pkg_name in list_pkgs:
        logging.debug(f"Starting grayskull for pkg: {pkg_name}")
        from_local_sdist = origin_is_local_sdist(pkg_name)
        print_msg(
            f"{Fore.GREEN}\n\n"
            f"#### Initializing recipe for "
            f"{Fore.BLUE}{pkg_name}{cran_label} {Fore.GREEN}####\n"
        )
        if Path(pkg_name).is_file() and (not from_local_sdist):
            args.output = pkg_name
        try:
            recipe, config = create_r_recipe(
                pkg_name,
                is_strict_cf=args.is_strict_conda_forge,
                download=args.download,
                sections_populate=args.sections_populate,
            )
        except requests.exceptions.HTTPError as err:
            print_msg(f"{Fore.RED}Package seems to be missing.\nException: {err}\n\n")
            continue

        if args.sections_populate is None or "extra" in args.sections_populate:
            add_extra_section(recipe, args.maintainers)

        generate_recipe(recipe, config, args.output)
        print_msg(
            f"\n{Fore.GREEN}#### Recipe generated on "
            f"{os.path.realpath(args.output)} for {pkg_name} ####\n\n"
        )


def create_r_recipe(pkg_name, sections_populate=None, **kwargs):
    config = Configuration(name=pkg_name, **kwargs)
    return (
        GrayskullFactory.create_recipe(
            "cran", config, sections_populate=sections_populate
        ),
        config,
    )


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
