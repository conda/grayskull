# Grayskull
-------------
[![Build Status](https://dev.azure.com/marceloduartetrevisani/Grayskull/_apis/build/status/Tests?branchName=master)](https://dev.azure.com/marceloduartetrevisani/Grayskull/_build/latest?definitionId=4&branchName=master) ![flake8](https://github.com/marcelotrevisani/grayskull/workflows/flake8/badge.svg?branch=master) ![Deployment (PyPI)](https://github.com/marcelotrevisani/grayskull/workflows/Upload%20Package%20to%20PyPI/badge.svg)

[![codecov](https://codecov.io/gh/marcelotrevisani/grayskull/branch/master/graph/badge.svg)](https://codecov.io/gh/marcelotrevisani/grayskull) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) ![](https://img.shields.io/badge/python-3.7+-blue.svg) ![](https://img.shields.io/github/license/marcelotrevisani/grayskull.svg) [![PyPI version](https://badge.fury.io/py/grayskull.svg)](https://badge.fury.io/py/grayskull) [![Conda Version](https://img.shields.io/conda/vn/conda-forge/grayskull.svg)](https://anaconda.org/conda-forge/grayskull) [![Gitter](https://badges.gitter.im/conda_grayskull/community.svg)](https://gitter.im/conda_grayskull/community?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge)

-------------
<span align="center">
    <br>
    <img src="https://comicvine1.cbsistatic.com/uploads/original/4/49448/2661756-castle_grayskull.jpg" align="center" />
    <br>
    <i>"Skeleto<strike>n</strike>r's main goal is to conquer the mysterious fortress of Castle Grayskull, from which He-Man draws his powers. If he succeeds, Skeletor would be able to conquer not only Eternia, but the whole universe."* Adapted from [Wikipedia](https://en.wikipedia.org/wiki/Skeletor)</i>
</span>


-------------
## Introduction

The Grayskull project was created with the intention to eventually replace the
`conda skeleton`. The main goal of this project is to generate concise recipes
 for [conda-forge](https://conda-forge.org/).

The current status of ``grayskull`` is generating recipes just looking for ``PyPI``,
 but in the future we will expand that to also support to load recipes and also
 generate recipes looking for other repositories, such as, CRAN, Conan, etc..

## Installation

It is possible to install this project using `pip`:
```bash
pip install grayskull
```

or `conda`, using the ``conda-forge`` channel:
```bash
conda install -c conda-forge grayskull
```

It is also possible to clone this repo and install it using `pip`:
```bash
git clone https://github.com/marcelotrevisani/grayskull.git
cd grayskull
pip install -e .
```

## Usage

It is pretty simple to use `grayskull`. Just call it, pass the repository
 (just `pypi` for now) and the package name.

* Example:
```bash
grayskull pypi pytest
```

After that `grayskull` will create a folder with the same name as the package
and inside of this folder it will generated the recipe (`meta.yaml`).

* Example with `pytest` (`grayskull pypi pytest`):

![Grayskull CLI](https://raw.githubusercontent.com/marcelotrevisani/grayskull/master/docs/images/cli_example_grayskull.gif)


## License
Copyright Marcelo Duarte Trevisani and others, 2020-2021.

Distributed under the terms of the MIT license, grayskull is free and open source software.
