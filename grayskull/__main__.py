import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Grayskull - Conda recipe generator")
    parser.add_argument(
        "repo_type",
        nargs=2,
        help="Specify the repository (PyPi, Cran) and the package name.",
    )
    parser.add_argument(
        "--heman", "--shera", default=False, action="store_true", dest="grayskull_power"
    )
    parser.add_argument(
        "--output", "-o", dest="output", help="Path to where the recipe will be created"
    )
    parser.add_argument("--version", "-v", dest="version", help="Package version ")

    args = parser.parse_args()

    if args.grayskull_power:
        print("By the power of Grayskull...\nI have the power!")
        sys.exit()

    print(args.repo_type)


if __name__ == "__main__":
    main()
