from unittest.mock import MagicMock, patch

import pytest

from grayskull.config import Configuration
from grayskull.strategy.cran import (
    get_cran_metadata,
    get_github_r_metadata,
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


@patch("grayskull.strategy.cran.origin_is_github")
@patch("grayskull.strategy.cran.get_github_r_metadata")
def test_get_cran_metadata_github_url_detection(mock_github_metadata, mock_is_github):
    """Test that get_cran_metadata detects GitHub URLs and uses GitHub strategy"""
    # Setup
    mock_is_github.return_value = True
    mock_github_metadata.return_value = ({"package": "test"}, "# comment")
    
    config = Configuration(name="https://github.com/user/repo")
    
    # Call
    result, comment = get_cran_metadata(config, "https://cran.r-project.org")
    
    # Verify GitHub path was taken
    mock_is_github.assert_called_once_with("https://github.com/user/repo")
    mock_github_metadata.assert_called_once_with(config)
    
    assert result == {"package": "test"}
    assert comment == "# comment"


@patch("grayskull.strategy.cran.origin_is_github")
@patch("grayskull.strategy.cran.get_cran_index")
@patch("grayskull.strategy.cran.download_cran_pkg")
@patch("grayskull.strategy.cran.get_archive_metadata")
@patch("grayskull.strategy.cran.sha256_checksum")
def test_get_cran_metadata_regular_cran_package(
    mock_sha256, mock_get_archive, mock_download, mock_get_index, mock_is_github
):
    """Test that get_cran_metadata handles regular CRAN packages correctly"""
    # Setup
    mock_is_github.return_value = False
    mock_get_index.return_value = ("testpkg", "1.0.0", "http://cran.../testpkg_1.0.0.tar.gz")
    mock_download.return_value = "/tmp/testpkg_1.0.0.tar.gz"
    mock_sha256.return_value = "fake_sha256_hash"
    mock_get_archive.return_value = {
        "Package": "testpkg",
        "Version": "1.0.0",
        "orig_lines": ["Package: testpkg"],
        "URL": "http://example.com"
    }
    
    config = Configuration(name="testpkg")
    
    # Call
    result, comment = get_cran_metadata(config, "https://cran.r-project.org")
    
    # Verify CRAN path was taken
    # Note: origin_is_github is not called for regular CRAN packages anymore
    # as the logic now checks for config.repo_github attribute first
    mock_get_index.assert_called_once()
    assert "package" in result
    assert result["package"]["name"] == "r-{{ name }}"


@patch("grayskull.strategy.cran.handle_gh_version")
@patch("grayskull.strategy.cran.generate_git_archive_tarball_url")
@patch("grayskull.strategy.cran.download_github_r_pkg")
@patch("grayskull.strategy.cran.get_github_archive_metadata")
@patch("grayskull.strategy.cran.sha256_checksum")
def test_get_github_r_metadata_basic_flow(
    mock_sha256, mock_get_metadata, mock_download, mock_gen_url, mock_handle_version
):
    """Test basic flow of get_github_r_metadata"""
    # Setup
    config = Configuration(name="https://github.com/user/testpkg", version="1.0.0")
    
    mock_handle_version.return_value = ("1.0.0", "v1.0.0")
    mock_gen_url.return_value = "https://github.com/user/testpkg/archive/v1.0.0.tar.gz"
    mock_download.return_value = "/tmp/testpkg-1.0.0.tar.gz"
    mock_sha256.return_value = "fake_sha256_hash"
    mock_get_metadata.return_value = {
        "Package": "testpkg",
        "Version": "1.0.0",
        "Description": "Test package",
        "License": "MIT",
        "Imports": "dplyr",
        "NeedsCompilation": "no",
        "orig_lines": ["Package: testpkg", "Version: 1.0.0"]
    }
    
    # Call
    result, comment = get_github_r_metadata(config)
    
    # Verify structure
    assert "package" in result
    assert "source" in result
    assert "requirements" in result
    assert "about" in result
    
    # Verify GitHub-specific fields
    assert result["about"]["home"] == "https://github.com/user/testpkg"
    assert result["about"]["dev_url"] == "https://github.com/user/testpkg"
    assert "v{{ version }}" in result["source"]["url"]
    
    # Verify dependencies
    assert "r-dplyr" in result["requirements"]["host"]
    assert "r-base" in result["requirements"]["host"]
