# Grayskull
-------------
[![Tests](https://github.com/conda/grayskull/actions/workflows/tests.yml/badge.svg)](https://github.com/conda/grayskull/actions/workflows/tests.yml) [![Deployment (PyPI)](https://github.com/conda/grayskull/actions/workflows/publish_pypi.yml/badge.svg)](https://github.com/conda/grayskull/actions/workflows/publish_pypi.yml)

[![codecov](https://codecov.io/gh/conda/grayskull/branch/master/graph/badge.svg)](https://codecov.io/gh/conda/grayskull) [![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) ![](https://img.shields.io/badge/python-3.8+-blue.svg) ![](https://img.shields.io/github/license/conda/grayskull.svg) [![PyPI version](https://badge.fury.io/py/grayskull.svg)](https://badge.fury.io/py/grayskull) [![Conda Version](https://img.shields.io/conda/vn/conda-forge/grayskull.svg)](https://anaconda.org/conda-forge/grayskull) [![Gitter](https://badges.gitter.im/conda_grayskull/community.svg)](https://gitter.im/conda_grayskull/community?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge)

-------------
<span align="center">
    <br>
    <img src="https://static.wikia.nocookie.net/heman/images/3/33/Grayskull.jpg" align="center" />
    <br>
    <i>"Skeleto<strike>n</strike>r's main goal is to conquer the mysterious fortress of Castle Grayskull, from which He-Man draws his powers. If he succeeds, Skeletor would be able to conquer not only Eternia, but the whole universe."</i> </br>Adapted from <a href=https://en.wikipedia.org/wiki/Skeletor>Wikipedia</a>. Image credits: <a href=https://he-man.fandom.com>https://he-man.fandom.com</a>
</span>


-------------
## Introduction

Grayskull is an automatic conda recipe generator. <br>
The main goal of this project is to generate concise recipes
for [conda-forge](https://conda-forge.org/).
The Grayskull project was created with the intention to eventually replace `conda skeleton`. <br>
Presently Grayskull can generate recipes for Python packages available on PyPI and also those not published on PyPI but available as GitHub repositories.
Grayskull can also generate recipes for R packages published on CRAN.
Future versions of Grayskull will support recipe generation for packages of other repositories such as Conan and CPAN etc..

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
git clone https://github.com/conda/grayskull.git
cd grayskull
pip install -e .
```

## Usage

It is pretty simple to use `grayskull`. Just call it, pass the repository
 (`pypi` or `cran`) and the package name.

* Example:
```bash
grayskull pypi pytest
```

After that `grayskull` will create a folder with the same name as the package
and inside this folder the generated recipe will be present (`meta.yaml`).

* Example with `pytest` (`grayskull pypi pytest`):

![Grayskull CLI](https://github.com/conda/grayskull/raw/main/images/cli_example_grayskull.gif)

If your package is a GitHub repository just replace the package name with the GitHub repository URL. <br>
For example: <br>

```bash
grayskull pypi https://github.com/confluentinc/confluent-kafka-python
```

You can also generate a recipe from a local sdist archive:

```bash
grayskull pypi ./pytest-5.3.5.tar.gz
```

Note that such a recipe isn't really portable as it will depend on the local path of the
sdist file. It can be useful if you want to automatically generate a conda package.

### Use Grayskull with an internal package index

Grayskull can create recipes that point to any Python Package Index. Supply the `--pypi-mirror-url` keyword.

* Example:
```bash
grayskull pypi --pypi-mirror-url https://pypi.example.com pytest
```

The above will source packages from `https://pypi.example.com/packages/source/...`

This assumes that the mirror follows the same API as pypi _including_ hosting metadata at the `/pypi/{package_name}/json` endpoint.
To specify an alternate metadata location use the `--pypi-metadata-url` option.

* Example:
```bash
grayskull pypi --pypi-mirror-url https://pypi.example.com --pypi-metadata-url https://pypi_meta.example.com pytest
```

> *Note:* `--pypi-metadata-url` is a replacement for `--pypi-url`; `--pypi-url` is deprecated and will be removed in a future release.

### Checking package availability against custom indexes

By default, Grayskull checks if packages are available on conda-forge and highlights missing dependencies. You can specify custom package indexes to check against using the `--package-indexes` argument:

```bash
grayskull pypi --package-indexes my-channel company-channel conda-forge pytest
```

This will check if packages exist in `my-channel`, `company-channel`, or `conda-forge` (in that order) and mark them accordingly in the output.

You can also specify full URLs for internal package indexes that don't use anaconda.org:

```bash
grayskull pypi --package-indexes https://internal-conda.example.com http://another-conda.example.com conda-forge pytest
```

Both HTTP and HTTPS protocols are supported for custom package indexes. This is particularly useful for internal networks that don't have access to anaconda.org.

For internal package indexes with custom API structures, you can use the `{pkg_name}` placeholder in your URL:

```bash
grayskull pypi --package-indexes "https://internal-conda.example.com/api/{pkg_name}/available" conda-forge pytest
```

This allows you to specify exactly how your internal package index API works, rather than using the default `/pkg_name/files` path structure.

### Online Grayskull

It is also possible to use Grayskull without any installation. You can go to this website [marcelotrevisani.com/grayskull](https://www.marcelotrevisani.com/grayskull) and inform the name and the version (optional) of the package and it will create the recipe for you.


## License
Copyright Marcelo Duarte Trevisani and contributors, 2020-2023.

Distributed under the terms of the Apache 2.0 license, grayskull is free and open source software.
