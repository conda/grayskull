import pytest

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


@pytest.mark.parametrize("extension", [".zip", ".tar", ".tar.gz", ".tar.bz2"])
@pytest.mark.parametrize(
    "filepath, expected_name, expected_version",
    [
        ("mypkg-1.2.0", "mypkg", "1.2.0"),
        ("mypkg-with-dash-1.2.0", "mypkg-with-dash", "1.2.0"),
        ("mypkg-1.0rc1", "mypkg", "1.0rc1"),
        ("mypkg", "mypkg", ""),
    ],
)
def test_parse_local_sdist(
    extension, filepath, expected_name, expected_version, tmp_path
):
    p = tmp_path / f"{filepath}{extension}"
    p.write_text("foo")
    origin, name, version = parse_pkg_name_version(str(p))
    assert origin == ""
    assert name == expected_name
    assert version == expected_version
