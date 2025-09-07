"""
Integration tests for GitHub R packages.
These tests require internet access and use real GitHub repositories.
"""
import pytest
from grayskull.main import create_r_recipe
from souschef.jinja_expression import get_global_jinja_var


@pytest.mark.github
def test_github_r_package_integration():
    """Test creating a recipe from a real GitHub R package"""
    # Use a small, stable R package for testing
    # Using the 'praise' package which is simple and stable
    github_url = "https://github.com/rladies/praise"
    
    # Create recipe 
    recipe, config = create_r_recipe(github_url, version="1.0.0")
    
    # Basic structure checks
    assert "package" in recipe
    assert "source" in recipe
    assert "build" in recipe
    assert "requirements" in recipe
    assert "test" in recipe
    assert "about" in recipe
    
    # Package info
    assert recipe["package"]["name"] == "r-{{ name }}"
    assert recipe["package"]["version"] == "{{ version }}"
    assert get_global_jinja_var(recipe, "name") == "praise"
    assert get_global_jinja_var(recipe, "version") == "1.0.0"
    
    # Source info - should use GitHub archive with version placeholder
    assert "github.com" in recipe["source"]["url"]
    assert "{{ version }}" in recipe["source"]["url"] or "v{{ version }}" in recipe["source"]["url"]
    assert "sha256" in recipe["source"]
    
    # Requirements - should have r-base at minimum
    assert "r-base" in recipe["requirements"]["host"]
    assert "r-base" in recipe["requirements"]["run"]
    
    # About section - should have GitHub info
    assert recipe["about"]["home"] == "https://github.com/rladies/praise"
    assert recipe["about"]["dev_url"] == "https://github.com/rladies/praise"
    
    # Test commands should be present
    assert any("library('praise')" in cmd for cmd in recipe["test"]["commands"])


@pytest.mark.github
def test_github_r_package_with_dependencies():
    """Test GitHub R package with dependencies"""
    # Using a package that has some dependencies
    github_url = "https://github.com/hadley/stringr"
    
    # Create recipe without specifying version (should get latest)
    recipe, config = create_r_recipe(github_url)
    
    # Should have dependencies
    host_deps = recipe["requirements"]["host"]
    run_deps = recipe["requirements"]["run"]
    
    # Should have r-base
    assert "r-base" in host_deps
    assert "r-base" in run_deps
    
    # Should have additional R dependencies
    assert len(host_deps) > 1  # More than just r-base
    assert len(run_deps) > 1   # More than just r-base
    
    # All dependencies should be prefixed with 'r-'
    for dep in host_deps:
        assert dep.startswith("r-") or dep.startswith("cross-r-base")
    for dep in run_deps:
        assert dep.startswith("r-")


@pytest.mark.github  
def test_github_r_package_version_placeholder():
    """Test that GitHub R package URLs get proper version placeholders"""
    github_url = "https://github.com/rladies/praise"
    
    recipe, config = create_r_recipe(github_url, version="1.0.0")
    
    # The source URL should have version placeholder
    source_url = recipe["source"]["url"]
    assert "{{ version }}" in source_url or "v{{ version }}" in source_url
    
    # Should not contain the actual version string
    assert "1.0.0" not in source_url


@pytest.mark.github
def test_github_r_package_needs_compilation():
    """Test GitHub R package that needs compilation"""
    # This would test a package that has NeedsCompilation: yes
    # For now, we'll skip this as it requires finding a suitable test package
    pytest.skip("Need to identify a suitable R package that requires compilation")


@pytest.mark.github
def test_github_r_package_url_variations():
    """Test different GitHub URL formats"""
    test_urls = [
        "https://github.com/rladies/praise",
        "https://github.com/rladies/praise/",  # with trailing slash
        "http://github.com/rladies/praise",    # http instead of https
    ]
    
    for url in test_urls:
        recipe, config = create_r_recipe(url, version="1.0.0")
        
        # Should all produce valid recipes
        assert "package" in recipe
        assert recipe["package"]["name"] == "r-{{ name }}"
        assert get_global_jinja_var(recipe, "name") == "praise"
        
        # About section should normalize to https
        assert recipe["about"]["home"] == "https://github.com/rladies/praise"
        assert recipe["about"]["dev_url"] == "https://github.com/rladies/praise"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "github"])
