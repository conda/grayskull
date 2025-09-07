import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
import tarfile
from pathlib import Path

from grayskull.config import Configuration
from grayskull.strategy.cran import (
    get_github_r_metadata,
    download_github_r_pkg,
    get_github_archive_metadata,
    get_cran_metadata,
)


@pytest.fixture
def mock_github_r_description():
    """Mock DESCRIPTION file content for a GitHub R package"""
    return """Package: testpkg
Version: 1.0.0
Title: Test Package
Description: This is a test R package from GitHub
Authors@R: person("Test", "Author", email = "test@example.com", role = c("aut", "cre"))
License: MIT + file LICENSE
Encoding: UTF-8
Imports: 
    dplyr (>= 1.0.0),
    ggplot2
Suggests: 
    testthat
URL: https://github.com/testuser/testpkg
BugReports: https://github.com/testuser/testpkg/issues
NeedsCompilation: no
"""


@pytest.fixture
def mock_config():
    """Mock configuration for testing"""
    return Configuration(
        name="https://github.com/testuser/testpkg",
        version="1.0.0"
    )


@pytest.fixture
def mock_archive_file(mock_github_r_description):
    """Create a mock tarball with DESCRIPTION file"""
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create package directory structure
        pkg_dir = os.path.join(temp_dir, "testpkg-1.0.0")
        os.makedirs(pkg_dir)
        
        # Create DESCRIPTION file
        with open(os.path.join(pkg_dir, "DESCRIPTION"), "w") as f:
            f.write(mock_github_r_description)
        
        # Create tarball
        tarball_path = os.path.join(temp_dir, "testpkg-1.0.0.tar.gz")
        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(pkg_dir, arcname="testpkg-1.0.0")
        
        yield tarball_path


class TestGitHubRPackages:
    """Test suite for GitHub R package functionality"""

    @patch('grayskull.strategy.cran.sha256_checksum')
    @patch('grayskull.strategy.cran.handle_gh_version')
    @patch('grayskull.strategy.cran.generate_git_archive_tarball_url')
    @patch('grayskull.strategy.cran.download_github_r_pkg')
    @patch('grayskull.strategy.cran.get_github_archive_metadata')
    def test_get_github_r_metadata_basic(
        self, 
        mock_get_metadata, 
        mock_download, 
        mock_gen_url, 
        mock_handle_version,
        mock_sha256,
        mock_config
    ):
        """Test basic GitHub R metadata extraction"""
        
        # Setup mocks
        mock_handle_version.return_value = ("1.0.0", "v1.0.0")
        mock_gen_url.return_value = "https://github.com/testuser/testpkg/archive/v1.0.0.tar.gz"
        mock_download.return_value = "/tmp/testpkg-1.0.0.tar.gz"
        mock_sha256.return_value = "abcd1234567890"
        mock_get_metadata.return_value = {
            "Package": "testpkg",
            "Version": "1.0.0",
            "Description": "Test package",
            "License": "MIT + file LICENSE",
            "Imports": "dplyr (>= 1.0.0), ggplot2",
            "NeedsCompilation": "no",
            "orig_lines": ["Package: testpkg", "Version: 1.0.0"]
        }
        
        # Test the function
        metadata, comment = get_github_r_metadata(mock_config)
        
        # Verify the structure
        assert "package" in metadata
        assert "source" in metadata
        assert "build" in metadata
        assert "requirements" in metadata
        assert "test" in metadata
        assert "about" in metadata
        
        # Verify package information
        assert metadata["package"]["name"] == "r-{{ name }}"
        assert metadata["package"]["version"] == "{{ version }}"
        
        # Verify source information
        assert "github.com" in metadata["source"]["url"]
        assert "{{ version }}" in metadata["source"]["url"]
        
        # Verify requirements
        host_requirements = metadata["requirements"]["host"]
        assert any("r-dplyr" in req for req in host_requirements)
        assert "r-ggplot2" in host_requirements
        assert "r-base" in host_requirements
        
        # Verify about section
        assert metadata["about"]["home"] == "https://github.com/testuser/testpkg"
        assert metadata["about"]["dev_url"] == "https://github.com/testuser/testpkg"

    @patch('requests.get')
    def test_download_github_r_pkg(self, mock_get, mock_config):
        """Test downloading GitHub R package archive"""
        
        # Mock the response
        mock_response = Mock()
        mock_response.content = b"fake tarball content"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        # Test download
        result = download_github_r_pkg(
            mock_config, 
            "https://github.com/testuser/testpkg/archive/v1.0.0.tar.gz",
            "testpkg",
            "1.0.0"
        )
        
        # Verify the file was created
        assert os.path.exists(result)
        assert result.endswith("testpkg-1.0.0.tar.gz")
        
        # Clean up
        os.unlink(result)

    def test_get_github_archive_metadata(self, mock_archive_file):
        """Test extracting metadata from GitHub archive"""
        
        metadata = get_github_archive_metadata(mock_archive_file)
        
        # Verify extracted metadata
        assert metadata["Package"] == "testpkg"
        assert metadata["Version"] == "1.0.0"
        assert metadata["License"] == "MIT + file LICENSE"
        assert "dplyr" in metadata["Imports"]
        assert "ggplot2" in metadata["Imports"]
        assert metadata["NeedsCompilation"] == "no"

    @patch('grayskull.strategy.cran.origin_is_github')
    @patch('grayskull.strategy.cran.get_github_r_metadata')
    @patch('grayskull.strategy.cran.get_cran_index')
    def test_get_cran_metadata_github_detection(
        self, 
        mock_cran_index, 
        mock_github_metadata, 
        mock_is_github,
        mock_config
    ):
        """Test that get_cran_metadata properly detects and handles GitHub URLs"""
        
        # Setup mocks
        mock_is_github.return_value = True
        mock_github_metadata.return_value = ({}, "# comment")
        
        # Call with GitHub URL
        config = Configuration(name="https://github.com/testuser/testpkg")
        get_cran_metadata(config, "https://cran.r-project.org")
        
        # Verify GitHub path was taken
        mock_github_metadata.assert_called_once()
        mock_cran_index.assert_not_called()

    @patch('grayskull.strategy.cran.origin_is_github')
    @patch('grayskull.strategy.cran.get_github_r_metadata')
    @patch('grayskull.strategy.cran.get_cran_index')
    def test_get_cran_metadata_cran_path(
        self, 
        mock_cran_index, 
        mock_github_metadata, 
        mock_is_github
    ):
        """Test that get_cran_metadata properly handles CRAN packages"""
        
        # Setup mocks
        mock_is_github.return_value = False
        mock_cran_index.return_value = ("testpkg", "1.0.0", "http://cran.r-project.org/...")
        
        # Mock other required functions
        with patch('grayskull.strategy.cran.download_cran_pkg') as mock_download, \
             patch('grayskull.strategy.cran.get_archive_metadata') as mock_metadata, \
             patch('grayskull.strategy.cran.sha256_checksum') as mock_sha256:
            
            mock_download.return_value = "/tmp/file.tar.gz"
            mock_sha256.return_value = "abcd1234567890"
            mock_metadata.return_value = {
                "Package": "testpkg",
                "Version": "1.0.0",
                "orig_lines": [],
                "URL": "http://example.com"
            }
            
            # Call with regular package name
            config = Configuration(name="testpkg")
            get_cran_metadata(config, "https://cran.r-project.org")
            
            # Verify CRAN path was taken
            mock_cran_index.assert_called_once()
            mock_github_metadata.assert_not_called()

    @pytest.mark.github 
    def test_github_url_version_placeholder_r_package(self):
        """Test that GitHub R package URLs get proper version placeholders"""
        
        # This would be an integration test that requires actual GitHub access
        # For now, we'll skip it but it's here for future implementation
        pytest.skip("Integration test - requires actual GitHub access")

    def test_version_tag_handling(self):
        """Test proper handling of version tags (v1.0.0 vs 1.0.0)"""
        
        config = Configuration(name="https://github.com/testuser/testpkg", version="1.0.0")
        
        with patch('grayskull.strategy.cran.handle_gh_version') as mock_handle, \
             patch('grayskull.strategy.cran.generate_git_archive_tarball_url') as mock_gen_url, \
             patch('grayskull.strategy.cran.download_github_r_pkg') as mock_download, \
             patch('grayskull.strategy.cran.get_github_archive_metadata') as mock_metadata, \
             patch('grayskull.strategy.cran.sha256_checksum') as mock_sha256:
            
            # Test with v-prefixed tag
            mock_handle.return_value = ("1.0.0", "v1.0.0")
            mock_gen_url.return_value = "https://github.com/testuser/testpkg/archive/v1.0.0.tar.gz"
            mock_download.return_value = "/tmp/test.tar.gz"
            mock_sha256.return_value = "abcd1234567890"
            mock_metadata.return_value = {
                "Package": "testpkg",
                "orig_lines": []
            }
            
            metadata, _ = get_github_r_metadata(config)
            
            # Should use v{{ version }} in URL for v-prefixed tags
            assert "v{{ version }}" in metadata["source"]["url"]

    def test_needs_compilation_handling(self):
        """Test that NeedsCompilation: yes adds proper build requirements"""
        
        config = Configuration(name="https://github.com/testuser/testpkg")
        
        with patch('grayskull.strategy.cran.handle_gh_version') as mock_handle, \
             patch('grayskull.strategy.cran.generate_git_archive_tarball_url') as mock_gen_url, \
             patch('grayskull.strategy.cran.download_github_r_pkg') as mock_download, \
             patch('grayskull.strategy.cran.get_github_archive_metadata') as mock_metadata, \
             patch('grayskull.strategy.cran.sha256_checksum') as mock_sha256:
            
            mock_handle.return_value = ("1.0.0", "1.0.0")
            mock_gen_url.return_value = "https://github.com/testuser/testpkg/archive/1.0.0.tar.gz"
            mock_download.return_value = "/tmp/test.tar.gz"
            mock_sha256.return_value = "abcd1234567890"
            mock_metadata.return_value = {
                "Package": "testpkg",
                "NeedsCompilation": "yes",
                "orig_lines": []
            }
            
            metadata, _ = get_github_r_metadata(config)
            
            # Should have compilation requirements
            assert metadata.get("need_compiler") is True
            build_requirements = metadata["requirements"]["build"]
            assert any("{{ compiler('c') }}" in req for req in build_requirements)
            assert any("autoconf" in req for req in build_requirements)

    def test_imports_parsing(self):
        """Test proper parsing of Imports field with version constraints"""
        
        config = Configuration(name="https://github.com/testuser/testpkg")
        
        with patch('grayskull.strategy.cran.handle_gh_version') as mock_handle, \
             patch('grayskull.strategy.cran.generate_git_archive_tarball_url') as mock_gen_url, \
             patch('grayskull.strategy.cran.download_github_r_pkg') as mock_download, \
             patch('grayskull.strategy.cran.get_github_archive_metadata') as mock_metadata, \
             patch('grayskull.strategy.cran.sha256_checksum') as mock_sha256:
            
            mock_handle.return_value = ("1.0.0", "1.0.0")
            mock_gen_url.return_value = "https://github.com/testuser/testpkg/archive/1.0.0.tar.gz"
            mock_download.return_value = "/tmp/test.tar.gz"
            mock_sha256.return_value = "abcd1234567890"
            mock_metadata.return_value = {
                "Package": "testpkg",
                "Imports": "dplyr (>= 1.0.0), ggplot2, stringr (>= 1.4.0)",
                "orig_lines": []
            }
            
            metadata, _ = get_github_r_metadata(config)
            
            # Should parse imports with version constraints
            requirements = metadata["requirements"]["host"]
            assert any("r-dplyr" in req and ">=1.0.0" in req for req in requirements)
            assert "r-ggplot2" in requirements
            assert any("r-stringr" in req and ">=1.4.0" in req for req in requirements)
            assert "r-base" in requirements


if __name__ == "__main__":
    pytest.main([__file__])
