import os

from grayskull.utils import (
    format_dependencies,
    get_all_modules_imported_script,
    get_std_modules,
    get_vendored_dependencies,
)


def test_get_std_modules():
    std_modules = get_std_modules()
    assert "sys" in std_modules
    assert "os" in std_modules
    assert "ast" in std_modules
    assert "typing" in std_modules


def test_get_all_modules_imported_script(data_dir):
    all_imports = get_all_modules_imported_script(
        os.path.join(data_dir, "foo_imports.py")
    )
    assert sorted(all_imports) == sorted(["numpy", "pandas", "requests", "os", "sys"])


def test_get_vendored_dependencies(data_dir):
    all_deps = get_vendored_dependencies(os.path.join(data_dir, "foo_imports.py"))
    assert sorted(all_deps) == sorted(["numpy", "pandas", "requests"])


def test_format_dependencies_optional_double_equal():
    assert format_dependencies(
        ["dask[dataframe,distributed]==2021.10.0"], "dask-sql"
    ) == ["dask ==2021.10.0"]
