from grayskull.cli.parser import parse_pkg_name_version


def test_parse_pkg_name_version():
    pkg_name, pkg_version = parse_pkg_name_version("pytest=5.3.5")
    assert pkg_name == "pytest"
    assert pkg_version == "5.3.5"

    pkg_name, pkg_version = parse_pkg_name_version("pytest==5.3.5")
    assert pkg_name == "pytest"
    assert pkg_version == "5.3.5"

    pkg_name, pkg_version = parse_pkg_name_version("pytest")
    assert pkg_name == "pytest"
    assert pkg_version is None


def test_parse_git_github_url():
    pkg_name, _ = parse_pkg_name_version("https://github.com/pytest-dev/pytest.git")
    assert pkg_name == "https://github.com/pytest-dev/pytest"
