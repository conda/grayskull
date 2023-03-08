from grayskull.base.pkg_info import is_pkg_available


def test_pkg_available():
    assert is_pkg_available("pytest")


def test_pkg_not_available():
    assert not is_pkg_available("NOT_PACKAGE_654987321")
