from setuptools import setup

setup(
    name="grayskull",
    version="0.1.0",
    packages=["grayskull", "grayskull.base", "grayskull.pypi"],
    entry_points={"console_scripts": ["grayskull = grayskull.__main__:main"]},
    use_scm_version={"write_to": "grayskull/_version.py"},
    setup_requires=["setuptools-scm", "setuptools>=30.3.0"],
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
