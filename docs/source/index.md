% Grayskull documentation master file, created by
% sphinx-quickstart on Tue Feb 15 20:08:45 2022.
% You can adapt this file completely to your liking, but it should at least
% contain the root `toctree` directive.

# Grayskull Documentation

**Grayskull**

 is an automatic conda recipe generator.

The main goal of this project is to generate concise recipes for [conda-forge](https://github.com/conda-forge).

Presently Grayskull can generate recipes for Python packages available on PyPI and also those not published on PyPI but available as GitHub repositories. 
Grayskull can also generate recipes for R packages published on CRAN.

Future versions of Grayskull will support recipe generation for packages of other repositories such as Conan, CPAN etc..

Check out the {doc}`user_guide` section for further information, including how
to {ref}`install <installation>` Grayskull.

```{toctree}
:caption: 'Contents:'
:maxdepth: 1

user_guide
cli
developer_guide
```

```{note}
This project is under active development.
```

# Indices and tables

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
