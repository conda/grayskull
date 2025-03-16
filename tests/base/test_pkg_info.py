from unittest import mock

import pytest
import requests

from grayskull.base.pkg_info import (
    build_package_url,
    is_pkg_available,
    normalize_pkg_name,
)
from grayskull.cli import CLIConfig


@pytest.mark.parametrize(
    "channel_or_url,pkg_name,expected_url",
    [
        # Channel name tests
        ("conda-forge", "pytest", "https://anaconda.org/conda-forge/pytest/files"),
        ("test-channel", "numpy", "https://anaconda.org/test-channel/numpy/files"),
        # HTTPS URL tests
        (
            "https://internal-conda.example.com",
            "pytest",
            "https://internal-conda.example.com/pytest/files",
        ),
        (
            "https://internal-conda.example.com/",
            "pytest",
            "https://internal-conda.example.com/pytest/files",
        ),
        # HTTP URL tests
        (
            "http://internal-conda.example.com",
            "pytest",
            "http://internal-conda.example.com/pytest/files",
        ),
        (
            "http://internal-conda.example.com/",
            "pytest",
            "http://internal-conda.example.com/pytest/files",
        ),
        # URL with port
        (
            "https://internal-conda.example.com:8080",
            "pytest",
            "https://internal-conda.example.com:8080/pytest/files",
        ),
        # Edge cases
        ("", "pytest", "https://anaconda.org//pytest/files"),
        ("https://example.com///", "pytest", "https://example.com/pytest/files"),
        # URLs with query parameters and fragments - actual behavior
        (
            "https://example.com?param=value",
            "pytest",
            "https://example.com?param=value/pytest/files",
        ),
        (
            "https://example.com?param=value#fragment",
            "pytest",
            "https://example.com?param=value#fragment/pytest/files",
        ),
        (
            "https://example.com#fragment",
            "pytest",
            "https://example.com#fragment/pytest/files",
        ),
        # URLs with placeholders - actual behavior
        (
            "https://custom-conda.example.com/api/{pkg_name}",
            "pytest",
            "https://custom-conda.example.com/api/{pkg_name}/pytest/files",
        ),
        (
            "https://custom-conda.example.com/api/{pkg_name}?format=json",
            "numpy",
            "https://custom-conda.example.com/api/{pkg_name}?format=json/numpy/files",
        ),
        (
            "https://custom-conda.example.com/api/{pkg_name}#section",
            "pandas",
            "https://custom-conda.example.com/api/{pkg_name}#section/pandas/files",
        ),
        (
            "https://custom-conda.example.com/api/{pkg_name}/info",
            "scipy",
            "https://custom-conda.example.com/api/{pkg_name}/info/scipy/files",
        ),
    ],
)
def test_build_package_url(channel_or_url, pkg_name, expected_url):
    """Test that build_package_url correctly handles various input formats."""
    url = build_package_url(channel_or_url, pkg_name)
    assert url == expected_url


def test_pkg_available():
    assert is_pkg_available("pytest")


def test_pkg_not_available():
    assert not is_pkg_available("NOT_PACKAGE_654987321")


@mock.patch("requests.get")
def test_is_pkg_available_with_full_url(mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()

    # Setup mock response
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    # Test with a full URL
    url = "https://internal-conda.example.com"
    result = is_pkg_available("pytest", url)

    # Verify the function called requests.get with the correct URL
    mock_get.assert_called_once_with(
        url=build_package_url(url, "pytest"),
        allow_redirects=False,
    )
    assert result is True


@mock.patch("requests.get")
def test_is_pkg_available_with_channel_name(mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()

    # Setup mock response
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    # Test with a channel name
    channel = "test-channel"
    result = is_pkg_available("pytest", channel)

    # Verify the function called requests.get with the correct URL
    mock_get.assert_called_once_with(
        url=build_package_url(channel, "pytest"),
        allow_redirects=False,
    )
    assert result is True


@mock.patch("requests.get")
@mock.patch("grayskull.base.pkg_info.CLIConfig")
def test_is_pkg_available_with_multiple_indexes(mock_cli_config, mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()

    # Setup mock CLIConfig to return our custom package indexes
    channels = [
        "test-channel",
        "https://internal-conda.example.com",
        "http://another-conda.example.com",
    ]
    mock_cli_config_instance = mock.MagicMock()
    mock_cli_config_instance.package_indexes = channels
    mock_cli_config.return_value = mock_cli_config_instance

    # Setup mock responses
    mock_response1 = mock.Mock()
    mock_response1.status_code = 404  # First index doesn't have the package

    mock_response2 = mock.Mock()
    mock_response2.status_code = 404  # Second index doesn't have the package

    mock_response3 = mock.Mock()
    mock_response3.status_code = 200  # Third index has the package

    mock_get.side_effect = [mock_response1, mock_response2, mock_response3]

    # Test with multiple indexes
    result = is_pkg_available("pytest")

    # Verify the function called requests.get with the correct URLs
    assert mock_get.call_count == 3
    mock_get.assert_has_calls(
        [
            mock.call(
                url=build_package_url(channels[0], "pytest"), allow_redirects=False
            ),
            mock.call(
                url=build_package_url(channels[1], "pytest"), allow_redirects=False
            ),
            mock.call(
                url=build_package_url(channels[2], "pytest"), allow_redirects=False
            ),
        ]
    )
    assert result is True


@mock.patch("requests.get")
def test_is_pkg_available_with_request_exception(mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()

    # Setup mock to raise an exception
    mock_get.side_effect = requests.exceptions.RequestException("Connection error")

    # Test with an exception
    result = is_pkg_available("pytest", "test-channel")

    # Verify the function handled the exception gracefully
    assert result is False


@mock.patch("requests.get")
def test_is_pkg_available_not_found(mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()

    # Setup mock response for package not found
    mock_response = mock.Mock()
    mock_response.status_code = 404
    mock_get.return_value = mock_response

    # Test with a package that doesn't exist
    result = is_pkg_available("NOT_PACKAGE_654987321", "test-channel")

    # Verify the function returns False for non-200 status codes
    assert result is False


@mock.patch("grayskull.base.pkg_info.is_pkg_available")
def test_normalize_pkg_name_with_custom_indexes(mock_is_pkg_available):
    # Setup mock to simulate different package name formats
    def side_effect(pkg_name):
        if pkg_name == "package-name":
            return False
        elif pkg_name == "package_name":
            return True
        return False

    mock_is_pkg_available.side_effect = side_effect

    # Test normalize_pkg_name with custom indexes
    CLIConfig(package_indexes=["custom-channel", "https://internal-conda.example.com"])
    result = normalize_pkg_name("package-name")

    # Verify the function returns the correct normalized name
    assert result == "package_name"
    assert mock_is_pkg_available.call_count == 2


# Reset CLIConfig after tests
@pytest.fixture(autouse=True)
def reset_cli_config():
    yield
    # Reset CLIConfig after each test
    CLIConfig(stdout=False, list_missing_deps=False, package_indexes=["conda-forge"])
    # Clear the cache after each test
    is_pkg_available.cache_clear()


@pytest.mark.parametrize(
    "url,expected_status,expected_result",
    [
        ("https://example.com", 200, True),
        ("http://example.com", 200, True),
        ("https://example.com/", 200, True),
        ("http://example.com/", 200, True),
        ("https://internal-conda.example.com:8080", 200, True),
    ],
)
@mock.patch("requests.get")
def test_is_pkg_available_with_url_pattern_matching(
    mock_get, url, expected_status, expected_result
):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()

    # Setup mock response
    mock_response = mock.Mock()
    mock_response.status_code = expected_status
    mock_get.return_value = mock_response

    # Test with the URL
    result = is_pkg_available("pytest", url)
    assert result is expected_result
    mock_get.assert_called_with(
        url=build_package_url(url, "pytest"),
        allow_redirects=False,
    )


@mock.patch("requests.get")
def test_is_pkg_available_with_http_url(mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()

    # Setup mock response
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    # Test with an HTTP URL
    url = "http://internal-conda.example.com"
    result = is_pkg_available("pytest", url)

    # Verify the function called requests.get with the correct URL
    mock_get.assert_called_once_with(
        url=build_package_url(url, "pytest"),
        allow_redirects=False,
    )
    assert result is True
