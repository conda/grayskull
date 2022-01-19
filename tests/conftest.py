import os
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest
from pytest import fixture

from grayskull.strategy.py_base import download_sdist_pkg


@fixture(scope="session")
def data_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "data")


@fixture(scope="session")
def pkg_pytest(tmpdir_factory) -> str:
    folder = tmpdir_factory.mktemp("test-download-pkg")
    dest_pkg = str(folder / "PYTEST-PKG.tar.gz")
    download_sdist_pkg(
        "https://pypi.io/packages/source/p/pytest/pytest-5.3.5.tar.gz", dest_pkg
    )
    shutil.unpack_archive(dest_pkg, str(folder))
    return dest_pkg


@fixture(scope="session")
def sdist_pkg_info(data_dir) -> Path:
    return Path(data_dir) / "local-sdist" / "PKG-INFO-TEST"


@fixture
def local_tar_sdist(tmp_path, sdist_pkg_info) -> str:
    mypkg = tmp_path / "mypkg.tar.gz"
    with tarfile.open(mypkg, "w") as tar:
        tar.add(sdist_pkg_info, arcname="mypkg-1.0.0/PKG-INFO")
    return str(mypkg)


@fixture
def local_tar_not_sdist(tmp_path, sdist_pkg_info) -> str:
    mypkg = tmp_path / "mypkg.tar.gz"
    with tarfile.open(mypkg, "w") as tar:
        tar.add(sdist_pkg_info, arcname="mypkg-1.0.0/README")
    return str(mypkg)


@fixture
def local_zip_sdist(tmp_path, sdist_pkg_info) -> str:
    mypkg = tmp_path / "mypkg.zip"
    with zipfile.ZipFile(mypkg, "w") as myzip:
        myzip.write(sdist_pkg_info, arcname="mypkg-1.0.0/PKG-INFO")
    return str(mypkg)


def pytest_collection_modifyitems(config, items):
    github_mark = pytest.mark.xfail(
        reason="This test may fail because github has limitation regarding the"
        " number of requisitions we can do to their api."
    )
    for item in items:
        if "github" in item.keywords:
            item.add_marker(github_mark)
