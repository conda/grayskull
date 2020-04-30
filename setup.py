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
    entry_points={"console_scripts": ["grayskull = grayskull.__main__:main"]},
    use_scm_version={"write_to": "grayskull/_version.py"},
    setup_requires=["setuptools-scm", "setuptools>=30.3.0"],
    package_data={"": ["LICENSE", "license/data/*", "license/data/*.*"]},
    include_package_data=True,
    python_requires=">=3.7",
    install_requires=[
        "requests",
        "ruamel.yaml >=0.15.3",
        "ruamel.yaml.jinja2",
        "stdlib-list",
        "pip",
        "setuptools >=30.3.0",
        "rapidfuzz >=0.7.6",
        "progressbar2",
        "colorama",
    ],
    extras_require={
        "testing": ["pytest", "mock", "pytest-cov", "pytest-console-scripts"]
    },
    url="https://github.com/marcelotrevisani/grayskull",
    license="MIT",
    author="Marcelo Duarte Trevisani",
    author_email="marceloduartetrevisani@gmail.com",
    description="Project to generate recipes for conda packages.",
    long_description_content_type="text/markdown",
    long_description=readme,
    project_urls={"Source": "https://github.com/marcelotrevisani/grayskull"},
)
