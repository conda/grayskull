import argparse
import logging
import os
import sys

from colorama import Fore, Style, init
from colorama.ansi import clear_screen

import grayskull
from grayskull.base.factory import GrayskullFactory
from grayskull.cli import CLIConfig
from grayskull.cli.parser import parse_pkg_name_version
from grayskull.cli.stdout import print_msg

init(autoreset=True)
logging.basicConfig(format="%(levelname)s:%(message)s")


def main(args=None):
    if not args:
        args = sys.argv[1:] if sys.argv[1:] else ["--help"]

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
        print_msg(
            f"{Fore.GREEN}\n\n"
            f"#### Initializing recipe for "
            f"{Fore.BLUE}{pkg_name} (pypi) {Fore.GREEN}####\n"
        )
        pkg_name, pkg_version = parse_pkg_name_version(pkg_name)
        recipe = GrayskullFactory.create_recipe(
            "pypi", pkg_name, pkg_version, download=args.download
        )
        recipe.generate_recipe(args.output, mantainers=args.maintainers)
        print_msg(
            f"\n{Fore.GREEN}#### Recipe generated on "
            f"{os.path.realpath(args.output)} for {pkg_name} ####\n"
        )


if __name__ == "__main__":
    main(sys.argv[1:])
