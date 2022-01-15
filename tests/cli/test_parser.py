from grayskull.cli.parser import parse_pkg_name_version


def test_parse_pkg_name_version():
    origin, pkg_name, pkg_version = parse_pkg_name_version("pytest=5.3.5")
    assert pkg_name == "pytest"
    assert pkg_version == "5.3.5"

    origin, pkg_name, pkg_version = parse_pkg_name_version("pytest==5.3.5")
    assert pkg_name == "pytest"
    assert pkg_version == "5.3.5"

    origin, pkg_name, pkg_version = parse_pkg_name_version("pytest")
    assert pkg_name == "pytest"
    assert pkg_version is None


def test_parse_git_github_url():
    origin, pkg_name, version = parse_pkg_name_version(
        "https://github.com/pytest-dev/pytest.git"
    )
    assert origin == "https://github.com/pytest-dev/"
    assert pkg_name == "pytest"
    assert not version
