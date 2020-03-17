from grayskull.cli.parser import parse_pkg_name_version, parse_pkg_path_version


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


def test_parse_pkg_path_version(tmpdir):
    path_recipe = str(tmpdir / "test-foo" / "meta.yaml")
    assert parse_pkg_path_version(f"{path_recipe}=1.2.3") == (path_recipe, "1.2.3")

    assert parse_pkg_path_version(f"{path_recipe}") == (path_recipe, None)
