import argparse
import logging
import os
import sys

import colorama
from colorama import Fore, Style
from colorama.ansi import clear_screen

import grayskull
from grayskull.base.base_recipe import Recipe
from grayskull.base.factory import GrayskullFactory
from grayskull.cli.parser import parse_pkg_name_version, parse_pkg_path_version

colorama.init(autoreset=True)
logging.basicConfig(format="%(levelname)s:%(message)s")


def main(args=None):
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description="Grayskull - Conda recipe generator")

    repo_parser = parser.add_subparsers(help="Options to generate recipes")
    pypi_cmds = repo_parser.add_parser("pypi", help="Generate recipes based on PyPI")

    load_cmds = repo_parser.add_parser("load", help="Load recipes")
    load_cmds.add_argument("recipes", help="Update sections", nargs="+", default=[])
    default_sections = tuple(
        section for section in Recipe.ALL_SECTIONS if section != "extra"
    )
    load_cmds.add_argument(
        "--update",
        "-u",
        help="Update sections",
        nargs="+",
        default=default_sections,
        dest="list_sections",
        choices=default_sections,
    )
    load_cmds.add_argument(
        "--repository",
        "--repo",
        help="Repository type",
        choices=("pypi",),
        default="",
        dest="repo_type",
    )

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

    args = parser.parse_args(args)

    if args.version:
        print(grayskull.__version__)
        return

    logging.debug(f"All arguments received: args: {args}")
    print(Style.RESET_ALL)
    print(clear_screen())
    if args.grayskull_power:
        print(
            f"{Fore.BLUE}By the power of Grayskull...\n"
            f"{Style.BRIGHT}I have the power!"
        )
        return

    if hasattr(args, "pypi_packages") and args.pypi_packages:
        for pkg_name in args.pypi_packages:
            logging.debug(f"Starting grayskull for pkg: {pkg_name}")
            print(
                f"{Fore.GREEN}\n\n"
                f"#### Initializing recipe for "
                f"{Fore.BLUE}{pkg_name} (pypi) {Fore.GREEN}####\n"
            )
            pkg_name, pkg_version = parse_pkg_name_version(pkg_name)
            recipe = GrayskullFactory.create_recipe(
                "pypi", pkg_name, pkg_version, download=args.download
            )
            recipe.generate_recipe(args.output, mantainers=args.maintainers)
            print(
                f"\n{Fore.GREEN}#### Recipe generated on "
                f"{os.path.realpath(args.output)} for {pkg_name} ####\n"
            )
        return

    sections_to_update = args.list_sections
    for recipe in args.recipes:
        print(
            f"{Fore.GREEN}\n\n"
            f"#### Loading recipe {Fore.BLUE}{recipe}{Fore.GREEN} ####"
        )
        pkg_name, pkg_version = parse_pkg_path_version(recipe)
        recipe_loaded = GrayskullFactory.load_recipe(pkg_name, args.repo_type)
        if isinstance(recipe_loaded, Recipe):
            print(
                f"{Fore.RED}It was not possible to guess the recipe type.\n"
                f"Please specify it using the proper options (--repo=pypi)."
            )
        if pkg_version:
            recipe_loaded.set_var_content(
                recipe_loaded["package"]["version"].values[0], pkg_version
            )
        else:
            recipe_loaded.set_var_content(
                recipe_loaded["package"]["version"].values[0], ""
            )
        if "package" not in sections_to_update:
            sections_to_update.insert(0, "source")
            sections_to_update.insert(0, "package")
        recipe_loaded.update(*sections_to_update)
        recipe_loaded.generate_recipe(pkg_name, disable_extra=True)
        print(f"\n{Fore.GREEN}#### Recipe sections were updated ####\n")


if __name__ == "__main__":
    main()
