from unittest.mock import MagicMock, patch

import pytest

from grayskull.config import Configuration
from grayskull.strategy.cran import (
    get_cran_metadata,
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
    mock_url_bar.get_text.return_value = "PKG_NAME/"
    mock_url_bar.get.return_value = "PKG_NAME_URL_BAR/"
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
        == "CRAN_URL/PKG_NAME_URL_BAR/"
    )


@patch("grayskull.strategy.cran.get_webpage")
def test_scrap_cran_pkg_folder_page_for_full_url(mock_get_webpage, webpage_magic_mock):
    mock_get_webpage.return_value = webpage_magic_mock
    assert (
        scrap_cran_pkg_folder_page_for_full_url("CRAN_URL", "PKG_NAME", "1.0.0")
        == "CRAN_URL/PKG_NAME_URL"
    )


@patch("grayskull.strategy.cran.get_archive_metadata")
@patch("grayskull.strategy.cran.sha256_checksum")
@patch("grayskull.strategy.cran.download_cran_pkg")
@patch("grayskull.strategy.cran.get_cran_index")
def test_get_cran_metadata_need_compilation(
    mock_get_cran_index,
    mock_download_cran_pkg,
    mock_sha256,
    mock_get_archive_metadata,
    tmp_path,
):
    mock_get_cran_index.return_value = ("rpkg", "1.0.0", "http://foobar")
    mock_sha256.return_value = 123456
    mock_download_cran_pkg.return_value = str(tmp_path / "rpkg-1.0.0.tar.gz")
    mock_get_archive_metadata.return_value = {
        "orig_lines": ["foo", "bar"],
        "License": "MIT",
        "NeedsCompilation": "yes",
        "URL": "PKG-URL",
    }
    cfg = Configuration(name="rpkg", version="1.0.0")
    result_metadata, r_recipe_comment = get_cran_metadata(
        cfg, "https://cran.r-project.org"
    )
    assert r_recipe_comment == "# foo\n# bar"
    assert result_metadata["requirements"]["build"] == [
        "cross-r-base {{ r_base }}  # [build_platform != target_platform]",
        "autoconf  # [unix]",
        "{{ compiler('c') }}  # [unix]",
        "{{ compiler('m2w64_c') }}  # [win]",
        "{{ compiler('cxx') }}  # [unix]",
        "{{ compiler('m2w64_cxx') }}  # [win]",
        "posix  # [win]",
    ]
