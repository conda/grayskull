import sys
from copy import deepcopy

import pytest
from souschef.recipe import Recipe

import grayskull
import grayskull.main as cli
from grayskull.base.factory import GrayskullFactory
from grayskull.config import Configuration


def test_version(capsys):
    cli.main(["--version"])
    captured = capsys.readouterr()
    assert captured.out.strip() == grayskull.__version__


def test_pypi_cmd(tmpdir):
    out_folder = tmpdir.mkdir("out")
    cli.main(
        ["pypi", "pytest=5.3.2", "-o", str(out_folder), "-m", "m1", "m2", "--download"]
    )
    pytest_folder = out_folder / "pytest"
    assert pytest_folder.isdir()

    recipe_file = pytest_folder / "meta.yaml"
    assert recipe_file.isfile()
    assert (pytest_folder / "pypi.json").isfile()
    assert (pytest_folder / "pytest-5.3.2.tar.gz").isfile()


@pytest.mark.parametrize("option", ["--heman", "--shera"])
def test_easter(capsys, option):
    cli.main([option])
    captured = capsys.readouterr()
    assert "By the power of Grayskull..." in captured.out.strip()


def test_grayskull_without_options(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["foo"])
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        cli.main([])
    assert pytest_wrapped_e.type is SystemExit
    captured = capsys.readouterr()
    assert "Grayskull - Conda recipe generator" in captured.out


def test_msg_missing_pkg_pypi(capsys):
    cli.main(["pypi", "NOT_A_PACKAGE_123123123"])
    captured = capsys.readouterr()
    assert (
        "Package seems to be missing."
        "\nException: It was not possible to recover package metadata"
        " for NOT_A_PACKAGE_123123123.\n"
        "Error code: 404" in captured.out
    )


def test_license_discovery(tmpdir):
    out_folder = tmpdir.mkdir("out-license")
    cli.main(["pypi", "httplib2shim=0.0.3", "-o", str(out_folder)])
    assert (out_folder / "httplib2shim" / "LICENSE").exists()


def test_change_pypi_url(mocker):
    mocker.patch("grayskull.main.generate_recipe", return_value=None)
    mocker.patch(
        "grayskull.main.create_python_recipe", return_value=({"extra": {}}, None)
    )
    mocker.patch("grayskull.main.add_extra_section", return_value=None)
    spy = mocker.spy(cli, "create_python_recipe")

    cli.main(["pypi", "pytest=5.3.2", "--pypi-url=http://url_pypi.com/abc"])
    spy.assert_called_once_with(
        "pytest=5.3.2",
        is_strict_cf=False,
        download=False,
        url_pypi="https://pypi.org",
        url_pypi_metadata="http://url_pypi.com/abc",
        sections_populate=None,
        from_local_sdist=False,
        extras_require_test=None,
        github_release_tag=None,
        extras_require_include=tuple(),
        extras_require_exclude=tuple(),
        extras_require_all=False,
        extras_require_split=False,
        licence_exclude_folders=tuple(),
    )


def test_config_url_pypi_metadata():
    config = Configuration("pytest", url_pypi_metadata="http://url_pypi.com/abc")
    assert config.url_pypi_metadata == "http://url_pypi.com/abc/{pkg_name}/json"


@pytest.mark.parametrize("option", ["-r", "--recursive"])
def test_recursive_option(mocker, option, tmpdir):
    folder = tmpdir.mkdir(f"recursive_pkg{option}")

    def mock_is_pkg_available(pkg):
        return pkg != "colorama"

    mocker.patch("grayskull.cli.stdout.is_pkg_available", new=mock_is_pkg_available)
    spy = mocker.spy(cli, "generate_recipes_from_list")
    cli.main(["pypi", "pytest=5.3.2", option, "-o", str(folder)])
    assert spy.call_count == 2
    assert spy.call_args_list[0].args[0] == ["pytest=5.3.2"]
    assert spy.call_args_list[1].args[0] == {"colorama"}


# The CRAN test is not passing. I don't understand why!
@pytest.mark.parametrize(
    "index, name, version",
    [("pypi", "pytest", "5.3.2"), ("cran", "future", "1.26.1")],
)
def test_part_reload_recipe(tmpdir, index, name, version):
    recipe = GrayskullFactory.create_recipe(index, Configuration(name, version))
    host = deepcopy([str(i) for i in recipe["requirements"]["host"]])
    run = deepcopy([str(i) for i in recipe["requirements"]["run"]])
    recipe["requirements"] = {}
    recipe["foo"] = "bar"
    assert not recipe["requirements"].value
    assert host
    assert run
    assert recipe["foo"] == "bar"

    folder = tmpdir.mkdir("reload_recipe")
    recipe_path = folder / "recipe.yaml"
    recipe.save(str(recipe_path))
    cli.main([index, str(recipe_path), "--sections", "requirements"])

    recipe = Recipe(load_file=str(recipe_path))
    assert host == [str(v) for v in recipe["requirements"]["host"] if v]
    assert run == [str(v) for v in recipe["requirements"]["run"] if v]
    assert recipe["foo"] == "bar"


def test_package_indexes_option(mocker, tmpdir):
    folder = tmpdir.mkdir("package_indexes_test")

    # Mock CLIConfig to capture the package_indexes value
    mock_cli_config = mocker.patch("grayskull.main.CLIConfig")
    mock_cli_config_instance = mocker.MagicMock()
    mock_cli_config.return_value = mock_cli_config_instance

    # Mock is_pkg_available to prevent actual network calls
    mocker.patch("grayskull.cli.stdout.is_pkg_available", return_value=True)

    # Mock generate_recipe to prevent actual recipe generation
    mocker.patch("grayskull.main.generate_recipe")

    # Run with custom package indexes including both HTTP and HTTPS URLs
    cli.main(
        [
            "pypi",
            "pytest",
            "--package-indexes",
            "custom-channel",
            "https://internal-conda.example.com",
            "http://another-conda.example.com",
            "-o",
            str(folder),
        ]
    )

    # Verify that package_indexes was set correctly in CLIConfig
    assert mock_cli_config_instance.package_indexes == [
        "custom-channel",
        "https://internal-conda.example.com",
        "http://another-conda.example.com",
    ]
