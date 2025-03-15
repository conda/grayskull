from grayskull.base.pkg_info import is_pkg_available, normalize_pkg_name
import pytest
from unittest import mock
from grayskull.cli import CLIConfig
import requests


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
    result = is_pkg_available("pytest", "https://internal-conda.example.com")
    
    # Verify the function called requests.get with the correct URL
    mock_get.assert_called_once_with(
        url="https://internal-conda.example.com/pytest/files",
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
    result = is_pkg_available("pytest", "test-channel")
    
    # Verify the function called requests.get with the correct URL
    mock_get.assert_called_once_with(
        url="https://anaconda.org/test-channel/pytest/files",
        allow_redirects=False,
    )
    assert result is True


@mock.patch("requests.get")
@mock.patch("grayskull.base.pkg_info.CLIConfig")
def test_is_pkg_available_with_multiple_indexes(mock_cli_config, mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()
    
    # Setup mock CLIConfig to return our custom package indexes
    mock_cli_config_instance = mock.MagicMock()
    mock_cli_config_instance.package_indexes = ["test-channel", "https://internal-conda.example.com"]
    mock_cli_config.return_value = mock_cli_config_instance
    
    # Setup mock responses
    mock_response1 = mock.Mock()
    mock_response1.status_code = 404  # First index doesn't have the package
    
    mock_response2 = mock.Mock()
    mock_response2.status_code = 200  # Second index has the package
    
    mock_get.side_effect = [mock_response1, mock_response2]

    # Test with multiple indexes
    result = is_pkg_available("pytest")
    
    # Verify the function called requests.get with the correct URLs
    assert mock_get.call_count == 2
    mock_get.assert_has_calls([
        mock.call(url="https://anaconda.org/test-channel/pytest/files", allow_redirects=False),
        mock.call(url="https://internal-conda.example.com/pytest/files", allow_redirects=False),
    ])
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


@mock.patch("requests.get")
def test_is_pkg_available_with_url_pattern_matching(mock_get):
    # Clear the cache to ensure the function is actually called
    is_pkg_available.cache_clear()
    
    # Setup mock responses
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    
    # Test with different URL formats
    urls_to_test = [
        "https://example.com",
        "http://example.com",
        "https://example.com/",
        "http://example.com/",
        "https://internal-conda.example.com:8080",
    ]
    
    for url in urls_to_test:
        is_pkg_available.cache_clear()
        result = is_pkg_available("pytest", url)
        assert result is True
        expected_url = f"{url.rstrip('/')}/pytest/files"
        mock_get.assert_called_with(url=expected_url, allow_redirects=False)
        mock_get.reset_mock()
