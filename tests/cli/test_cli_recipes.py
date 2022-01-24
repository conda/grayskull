from souschef.recipe import Recipe

from grayskull.__main__ import main


def test_loop_deps_nipy_and_maintainers(tmpdir, mocker):
    mocker.patch("grayskull.__main__.get_git_current_user", return_value="GIT_USER")
    out_folder = tmpdir.mkdir("out")
    main(["pypi", "nipy=0.4.2", "-o", str(out_folder), "--download"])
    nipy_folder = out_folder / "nipy"
    assert nipy_folder.isdir()

    recipe_file = nipy_folder / "meta.yaml"
    assert recipe_file.isfile()
    assert (nipy_folder / "pypi.json").isfile()
    assert (nipy_folder / "nipy-0.4.2.tar.gz").isfile()

    recipe = Recipe(load_file=recipe_file)
    assert recipe["extra"]["recipe-maintainers"][0] == "GIT_USER"
