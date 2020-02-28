import argparse
import logging
import os
import sys

import colorama
from colorama import Fore, Style
from colorama.ansi import clear_screen

import grayskull
from grayskull.base.factory import GrayskullFactory
from grayskull.cli.parser import parse_pkg_name_version

colorama.init(autoreset=True)
logging.basicConfig(format="%(levelname)s:%(message)s")


def main():
    parser = argparse.ArgumentParser(description="Grayskull - Conda recipe generator")
    sub_parser = parser.add_subparsers(help="Options to generate PyPI recipes")
    pypi_cmds = sub_parser.add_parser("pypi", help="Generate recipes based on PyPI")
    pypi_cmds.add_argument(
        "pypi_packages", nargs="+", help="Specify the PyPI packages name.", default=""
    )
    parser.add_argument(
        "--version",
        "-v",
        default=False,
        action="store_true",
        dest="version",
        help="Grayskull version",
    )
    parser.add_argument(
        "--heman", "--shera", default=False, action="store_true", dest="grayskull_power"
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output",
        default=".",
        help="Path to where the recipe will be created",
    )
    args = parser.parse_args()

    if args.version:
        print(grayskull.__version__)
        sys.exit()

    logging.debug(f"All arguments received: args: {args}")
    print(Style.RESET_ALL)
    print(clear_screen())
    if args.grayskull_power:
        print(
            f"{Fore.BLUE}By the power of Grayskull...\n"
            f"{Style.BRIGHT}I have the power!"
        )

    for pkg_name in args.pypi_packages:
        logging.debug(f"Starting grayskull for pkg: {pkg_name}")
        print(
            f"{Fore.GREEN}\n\n"
            f"#### Initializing recipe for "
            f"{Fore.BLUE}{pkg_name} (pypi) {Fore.GREEN}####\n"
        )
        pkg_name, pkg_version = parse_pkg_name_version(pkg_name)
        recipe = GrayskullFactory.create_recipe("pypi", pkg_name, pkg_version)
        recipe.generate_recipe(args.output)
        print(
            f"\n{Fore.GREEN}#### Recipe generated on "
            f"{os.path.realpath(args.output)} for {pkg_name} ####\n"
        )


if __name__ == "__main__":
    main()
