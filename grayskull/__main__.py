import argparse
import logging
import os

import colorama
from colorama import Fore, Style
from colorama.ansi import clear_screen

from grayskull.base.factory import GrayskullFactory

colorama.init(autoreset=True)
logging.basicConfig(format="%(levelname)s:%(message)s")


def main():
    parser = argparse.ArgumentParser(description="Grayskull - Conda recipe generator")
    parser.add_argument(
        "repo_type", nargs=1, help="Specify the repository (pypi, cran).",
    )
    parser.add_argument(
        "packages", nargs="+", help="Specify the packages name.",
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
    parser.add_argument(
        "--version", "-v", default="", dest="version", help="Package version "
    )

    args = parser.parse_args()
    logging.debug(f"All arguments received: args: {args}")
    print(Style.RESET_ALL)
    print(clear_screen())
    if args.grayskull_power:
        print(
            f"{Fore.BLUE}By the power of Grayskull...\n"
            f"{Style.BRIGHT}I have the power!"
        )

    for pkg_name in args.packages:
        logging.debug(f"Starting grayskull for pkg: {pkg_name}")
        print(
            f"{Fore.GREEN}\n\n"
            f"#### Initializing recipe for "
            f"{Fore.BLUE}{pkg_name} ({args.repo_type[0]}) {Fore.GREEN}####\n"
        )
        recipe = GrayskullFactory.create_recipe(
            args.repo_type[0], pkg_name, args.version
        )
        recipe.generate_recipe(args.output)
        print(
            f"\n{Fore.GREEN}#### Recipe generated on "
            f"{os.path.realpath(args.output)} for {pkg_name} ####\n"
        )


if __name__ == "__main__":
    main()
