import sys

import pytest

import grayskull
from grayskull import __main__ as cli
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
    assert pytest_wrapped_e.type == SystemExit
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
    mocker.patch("grayskull.__main__.generate_recipe", return_value=None)
    mocker.patch(
        "grayskull.__main__.create_python_recipe", return_value=({"extra": {}}, None)
    )
    spy = mocker.spy(cli, "create_python_recipe")

    cli.main(["pypi", "pytest=5.3.2", "--pypi-url=http://url_pypi.com/abc"])
    spy.assert_called_once_with(
        "pytest=5.3.2",
        is_strict_cf=False,
        download=False,
        url_pypi_metadata="http://url_pypi.com/abc",
    )


def test_config_url_pypi_metadata():
    config = Configuration("pytest", url_pypi_metadata="http://url_pypi.com/abc")
    assert config.url_pypi_metadata == "http://url_pypi.com/abc/{pkg_name}/json"
