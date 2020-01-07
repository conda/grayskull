from setuptools import setup

setup(
    name="grayskull",
    version="0.1.0",
    packages=["grayskull", "grayskull.pypi"],
    package_dir={"": "src"},
    install_requires=["requests", "pyyaml"],
    extras_require={"testing": ["pytest"]},
    url="https://github.com/marcelotrevisani/grayskull",
    license="MIT",
    author="Marcelo Duarte Trevisani",
    author_email="marceloduartetrevisani@gmail.com",
    description="Skeletonr's main goal is to conquer the mysterious fortress of"
    " Castle Grayskull. If he succeeds, Skeletor would be able to conquer not"
    " only Eternia, but the whole universe.",
)
