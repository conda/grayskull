from unittest.mock import MagicMock, patch

import pytest

from grayskull.strategy.cran import (
    scrap_cran_archive_page_for_package_folder_url,
    scrap_cran_pkg_folder_page_for_full_url,
    scrap_main_page_cran_find_latest_package,
)


@pytest.fixture
def webpage_magic_mock():
    mock_webpage = MagicMock()
    mock_url = MagicMock()
    mock_url.get_text.return_value = "PKG_NAME_1.0.0.tar.gz"
    mock_url.get.return_value = "PKG_NAME_URL"
    mock_url_foo = MagicMock()
    mock_url_foo.get_text.return_value = "OTHER_PACKAGE_2.0.1.tar.gz"
    mock_url_bar = MagicMock()
    mock_url_bar.get_text.return_value = "PKG_NAME"
    mock_url_bar.get.return_value = "PKG_NAME_URL_BAR"
    mock_webpage.findAll.return_value = [mock_url_foo, mock_url_bar, mock_url]
    return mock_webpage


@patch("grayskull.strategy.cran.get_webpage")
def test_scrap_main_page_cran_find_latest_package(mock_get_webpage, webpage_magic_mock):
    mock_get_webpage.return_value = webpage_magic_mock
    assert scrap_main_page_cran_find_latest_package(
        "CRAN_URL", "PKG_NAME", "1.0.0"
    ) == ("pkg_name", "1.0.0", "CRAN_URL/src/contrib/PKG_NAME_URL")
    assert scrap_main_page_cran_find_latest_package("CRAN_URL", "PKG_NAME", None) == (
        "pkg_name",
        "1.0.0",
        "CRAN_URL/src/contrib/PKG_NAME_URL",
    )


@patch("grayskull.strategy.cran.get_webpage")
def test_scrap_main_page_cran_find_latest_package_not_latest(
    mock_get_webpage, webpage_magic_mock
):
    mock_get_webpage.return_value = webpage_magic_mock
    assert scrap_main_page_cran_find_latest_package(
        "CRAN_URL", "PKG_NAME", "0.1.0"
    ) == ("pkg_name", "0.1.0", "CRAN_URL/src/contrib/Archive")


@patch("grayskull.strategy.cran.get_webpage")
def test_scrap_cran_archive_page_for_package_folder_url(
    mock_get_webpage, webpage_magic_mock
):
    mock_get_webpage.return_value = webpage_magic_mock
    assert (
        scrap_cran_archive_page_for_package_folder_url("CRAN_URL", "PKG_NAME")
        == "CRAN_URL/PKG_NAME_URL_BAR"
    )


@patch("grayskull.strategy.cran.get_webpage")
def test_scrap_cran_pkg_folder_page_for_full_url(mock_get_webpage, webpage_magic_mock):
    mock_get_webpage.return_value = webpage_magic_mock
    assert (
        scrap_cran_pkg_folder_page_for_full_url("CRAN_URL", "PKG_NAME", "1.0.0")
        == "CRAN_URL/PKG_NAME_URL"
    )
