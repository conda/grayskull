from setuptools import setup

setup(
    name="grayskull",
    packages=["grayskull", "grayskull.base", "grayskull.pypi"],
    entry_points={
        "console_scripts": [
            "grayskull = grayskull.__main__:main",
            "gs = grayskull.__main__:main",
        ]
    },
    use_scm_version={"write_to": "grayskull/_version.py"},
    setup_requires=["setuptools-scm", "setuptools>=30.3.0"],
    install_requires=[
        "requests",
        "ruamel.yaml >=0.15.3",
        "ruamel.yaml.jinja2",
        "stdlib-list",
        "pip",
        "setuptools>=30.3.0",
        "fuzzywuzzy",
        "python-Levenshtein",
        "progressbar2",
        "colorama",
    ],
    extras_require={"testing": ["pytest"]},
    url="https://github.com/marcelotrevisani/grayskull",
    license="MIT",
    author="Marcelo Duarte Trevisani",
    author_email="marceloduartetrevisani@gmail.com",
    description="Project to generate recipes for conda packages. "
    "Skeletor's main goal is to conquer the mysterious fortress of"
    " Castle Grayskull. If he succeeds, Skeletor would be able to conquer not"
    " only Eternia, but the whole universe.",
)
