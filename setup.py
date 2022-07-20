import os

from setuptools import find_packages, setup

if os.path.exists("README.md"):
    with open("README.md", "r") as f:
        readme = f.read()
else:
    readme = ""


setup(
    name="grayskull",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "grayskull = grayskull.__main__:main",
            "greyskull = grayskull.__main__:main",
            "conda-grayskull = grayskull.__main__:main",
            "conda-greyskull = grayskull.__main__:main",
        ]
    },
    use_scm_version={"write_to": "grayskull/_version.py"},
    setup_requires=["setuptools-scm", "setuptools>=30.3.0"],
    package_data={
        "": [
            "LICENSE",
            "license/data/*",
            "license/data/*.*",
            "licence/licence_cache.json",
        ]
    },
    include_package_data=True,
    python_requires=">=3.8",
    install_requires=[
        "requests",
        "ruamel.yaml >=0.16.10",
        "ruamel.yaml.jinja2",
        "stdlib-list",
        "pip",
        "setuptools >=30.3.0",
        "rapidfuzz >=1.7.1",
        "progressbar2 >=3.53.0",
        "colorama",
        "conda-souschef >=2.1.2",
        "pkginfo",
    ],
    extras_require={
        "testing": [
            "pytest",
            "mock",
            "pytest-cov",
            "pytest-console-scripts",
            "pytest-mock",
        ]
    },
    url="https://github.com/conda-incubator/grayskull",
    license="MIT",
    author="Marcelo Duarte Trevisani",
    author_email="marceloduartetrevisani@gmail.com",
    description="Project to generate recipes for conda packages.",
    long_description_content_type="text/markdown",
    long_description=readme,
    project_urls={"Source": "https://github.com/conda-incubator/grayskull"},
)
