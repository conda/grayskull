import pytest

import grayskull
from grayskull.__main__ import main
from grayskull.base.base_recipe import Recipe


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


def test_load_recipe(tmpdir):
    main(["pypi", "pysal=2.0.0", "-o", str(tmpdir)])
    old_recipe_path = tmpdir / "pysal" / "meta.yaml"
    assert old_recipe_path.isfile()
    old_recipe = Recipe(load_recipe=str(old_recipe_path))
    assert (
        old_recipe.get_var_content(old_recipe["package"]["name"].values[0]) == "pysal"
    )
    assert (
        old_recipe.get_var_content(old_recipe["package"]["version"].values[0])
        == "2.0.0"
    )

    main(
        [
            "load",
            f"{old_recipe_path}=2.2.0",
            "--repo",
            "pypi",
            "--update",
            "requirements",
        ]
    )
    assert old_recipe_path.isfile()
    recipe = Recipe(load_recipe=str(old_recipe_path))
    assert recipe.get_var_content(recipe["package"]["name"].values[0]) == "pysal"
    assert recipe.get_var_content(recipe["package"]["version"].values[0]) == "2.2.0"


@pytest.mark.parametrize("option", ["--heman", "--shera"])
def test_easter(capsys, option):
    main([option])
    captured = capsys.readouterr()
    assert "By the power of Grayskull..." in captured.out.strip()
