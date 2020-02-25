import os
import shutil

from pytest import fixture

from grayskull.pypi import PyPi


@fixture(scope="session")
def data_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "data")


@fixture(scope="session")
def pkg_pytest(tmpdir_factory) -> str:
    folder = tmpdir_factory.mktemp("test-download-pkg")
    dest_pkg = str(folder / "PYTEST-PKG.tar.gz")
    PyPi._download_sdist_pkg(
        "https://pypi.io/packages/source/p/pytest/pytest-5.3.5.tar.gz", dest_pkg
    )
    shutil.unpack_archive(dest_pkg, str(folder))
    return dest_pkg
