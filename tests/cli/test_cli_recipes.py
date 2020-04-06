from grayskull.__main__ import main


def test_loop_deps_nipy(tmpdir):
    out_folder = tmpdir.mkdir("out")
    main(["pypi", "nipy=0.4.2", "-o", str(out_folder), "--download"])
    nipy_folder = out_folder / "nipy"
    assert nipy_folder.isdir()

    recipe_file = nipy_folder / "meta.yaml"
    assert recipe_file.isfile()
    assert (nipy_folder / "pypi.json").isfile()
    assert (nipy_folder / "nipy-0.4.2.tar.gz").isfile()
