import pytest

import grayskull
from grayskull.__main__ import main


def test_version(capsys):
    main(["--version"])
    captured = capsys.readouterr()
    assert captured.out.strip() == grayskull.__version__


def test_pypi_cmd(tmpdir):
    out_folder = tmpdir.mkdir("out")
    main(["pypi", "pytest=5.3.2", "-o", str(out_folder), "-m", "m1", "m2"])
    pytest_folder = out_folder / "pytest"
    assert pytest_folder.isdir()

    recipe_file = pytest_folder / "meta.yaml"
    assert recipe_file.isfile()


@pytest.mark.parametrize("option", ["--heman", "--shera"])
def test_easter(capsys, option):
    main([option])
    captured = capsys.readouterr()
    assert "By the power of Grayskull..." in captured.out.strip()
