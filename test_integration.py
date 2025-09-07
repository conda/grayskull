#!/usr/bin/env python3
"""
Integration test for GitHub R package functionality.
This script tests the complete workflow of generating a recipe for an R package from GitHub.
"""

import tempfile
import os
import sys
from pathlib import Path

# Add the grayskull module to path
sys.path.insert(0, '/data02/work/guozhonghao/grayskull')

from grayskull.main import create_r_recipe


def test_github_r_package_integration():
    """Test creating a recipe for a real GitHub R package"""
    
    # Use a simple, small R package from GitHub for testing
    # This package should have a proper DESCRIPTION file
    github_url = "https://github.com/tidyverse/stringr"
    
    print(f"Testing recipe generation for: {github_url}")
    
    try:
        # Create recipe
        recipe, config = create_r_recipe(github_url)
        
        # Verify basic structure
        assert "package" in recipe
        assert "source" in recipe
        assert "build" in recipe
        assert "requirements" in recipe
        assert "test" in recipe
        assert "about" in recipe
        
        # Verify package information
        assert recipe["package"]["name"] == "r-{{ name }}"
        assert recipe["package"]["version"] == "{{ version }}"
        
        # Verify source points to GitHub
        assert "github.com" in recipe["source"]["url"]
        assert "archive" in recipe["source"]["url"]
        assert "{{ version }}" in recipe["source"]["url"]
        
        # Verify requirements include r-base
        assert "r-base" in recipe["requirements"]["host"]
        assert "r-base" in recipe["requirements"]["run"]
        
        # Verify about section
        assert "github.com" in recipe["about"]["home"]
        assert recipe["about"]["dev_url"] == recipe["about"]["home"]
        
        print("✅ Recipe structure looks good!")
        print(f"Package name: {config.name}")
        print(f"Package version: {config.version}")
        print(f"Source URL: {recipe['source']['url']}")
        print(f"Home URL: {recipe['about']['home']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_github_r_package_detection():
    """Test that GitHub R packages are properly detected"""
    from grayskull.config import Configuration
    from grayskull.strategy.cran import get_cran_metadata
    from grayskull.utils import origin_is_github
    
    # Test URL detection
    github_url = "https://github.com/tidyverse/stringr"
    assert origin_is_github(github_url), "GitHub URL should be detected"
    
    # Test configuration parsing
    config = Configuration(name=github_url)
    assert hasattr(config, 'repo_github'), "repo_github should be set"
    assert config.repo_github == github_url, "repo_github should match input URL"
    assert config.name == "stringr", "name should be extracted from URL"
    
    print("✅ GitHub R package detection works correctly!")
    return True


if __name__ == "__main__":
    print("Running GitHub R package integration tests...")
    print("=" * 50)
    
    # Test 1: Basic detection
    print("Test 1: GitHub package detection")
    if not test_github_r_package_detection():
        sys.exit(1)
    
    print("\n" + "=" * 50)
    
    # Test 2: Full integration (requires network access)
    print("Test 2: Full recipe generation (requires network)")
    response = input("Run integration test with real GitHub package? (y/N): ")
    
    if response.lower() in ['y', 'yes']:
        if not test_github_r_package_integration():
            sys.exit(1)
    else:
        print("Skipping integration test")
    
    print("\n✅ All tests completed successfully!")
