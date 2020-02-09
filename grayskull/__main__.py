import argparse

from grayskull.base.factory import GrayskullFactory


def main():
    parser = argparse.ArgumentParser(description="Grayskull - Conda recipe generator")
    parser.add_argument(
        "repo_type",
        nargs=2,
        help="Specify the repository (pypi, cran) and the package name.",
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

    recipe = GrayskullFactory.create_recipe(
        args.repo_type[0], args.repo_type[1], args.version
    )
    recipe.generate_recipe(args.output)


if __name__ == "__main__":
    main()
