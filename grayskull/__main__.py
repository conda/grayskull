import argparse

from grayskull.base.factory import GrayskullFactory


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

    if args.grayskull_power:
        print("By the power of Grayskull...\nI have the power!")

    for pkg_name in args.packages:
        recipe = GrayskullFactory.create_recipe(
            args.repo_type[0], pkg_name, args.version
        )
        recipe.generate_recipe(args.output)


if __name__ == "__main__":
    main()
