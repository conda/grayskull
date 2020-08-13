import sys

import pytest

import grayskull
from grayskull.__main__ import main


def test_version(capsys):
    main(["--version"])
    captured = capsys.readouterr()
    assert captured.out.strip() == grayskull.__version__


def test_pypi_cmd(tmpdir):
    out_folder = tmpdir.mkdir("out")
    main(
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
    main([option])
    captured = capsys.readouterr()
    assert "By the power of Grayskull..." in captured.out.strip()


def test_grayskull_without_options(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["foo"])
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        main([])
    assert pytest_wrapped_e.type == SystemExit
    captured = capsys.readouterr()
    assert "Grayskull - Conda recipe generator" in captured.out


def test_msg_missing_pkg_pypi(capsys):
    main(["pypi", "NOT_A_PACKAGE_123123123"])
    captured = capsys.readouterr()
    assert (
        "Package seems to be missing on pypi."
        "\nException: It was not possible to recover PyPi metadata"
        " for NOT_A_PACKAGE_123123123.\n"
        "Error code: 404" in captured.out
    )


def test_license_discovery(tmpdir):
    out_folder = tmpdir.mkdir("out-license")
    main(["pypi", "httplib2shim=0.0.3", "-o", str(out_folder)])
    assert (out_folder / "httplib2shim" / "LICENSE").exists()
