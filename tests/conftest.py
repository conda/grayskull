import os
import shutil

import pytest
from pytest import fixture

from grayskull.strategy.py_base import download_sdist_pkg


@fixture(scope="session")
def data_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "data")


@fixture(scope="session")
def pkg_pytest(tmpdir_factory) -> str:
    folder = tmpdir_factory.mktemp("test-download-pkg")
    # Use different package name and version for the sdist archive on purpose
    # Correct info should be extracted from the metadata and not filename
    dest_pkg = str(folder / "PYTEST-PKG-1.0.0.tar.gz")
    download_sdist_pkg(
        "https://pypi.org/packages/source/p/pytest/pytest-5.3.5.tar.gz", dest_pkg
    )
    shutil.unpack_archive(dest_pkg, str(folder))
    return dest_pkg


def pytest_collection_modifyitems(config, items):
    github_mark = pytest.mark.xfail(
        reason="This test may fail because github has limitation regarding the"
        " number of requisitions we can do to their api."
    )
    for item in items:
        if "github" in item.keywords:
            item.add_marker(github_mark)
