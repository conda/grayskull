from setuptools import find_packages, setup

setup(
    name="grayskull",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    use_scm_version={"write_to": "src/grayskull/_version.py"},
    setup_requires=["setuptools-scm>=3.4", "setuptools>=42.0"],
    install_requires=["requests", "pyyaml"],
    extras_require={"testing": ["pytest"]},
    url="https://github.com/marcelotrevisani/grayskull",
    license="MIT",
    author="Marcelo Duarte Trevisani",
    author_email="marceloduartetrevisani@gmail.com",
    description="Skeletor's main goal is to conquer the mysterious fortress of"
    " Castle Grayskull. If he succeeds, Skeletor would be able to conquer not"
    " only Eternia, but the whole universe.",
)
