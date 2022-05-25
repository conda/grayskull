import os

import pytest

from grayskull.utils import (
    format_dependencies,
    get_all_modules_imported_script,
    get_std_modules,
    get_vendored_dependencies,
    merge_dict_of_lists_item,
    merge_list_item,
    origin_is_local_sdist,
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


@pytest.mark.parametrize(
    "filename", ["mypkg.zip", "mypkg.tar", "mypkg.tar.gz", "mypkg.tar.bz2"]
)
def test_origin_is_local_sdist(filename, tmp_path):
    p = tmp_path / filename
    p.write_text("foo")
    assert origin_is_local_sdist(str(p))


def test_origin_is_not_local_sdist_file(tmp_path):
    p = tmp_path / "mypgk"
    p.write_text("foo")
    assert not origin_is_local_sdist(str(p))


@pytest.mark.parametrize(
    "filename", ["mypkg", "mypkg=1.0.0", "https://github.com/foo/bar"]
)
def test_origin_is_not_local_sdist_filename(filename):
    assert not origin_is_local_sdist(filename)


def test_merge_lists_item():
    destination = {}
    add = {}
    merge_list_item(destination, add, "name")
    assert destination == {}

    destination = {"name": [1]}
    add = {}
    merge_list_item(destination, add, "name")
    destination = {key: set(lst) for key, lst in destination.items()}
    assert destination == {"name": {1}}

    destination = {}
    add = {"name": [2]}
    merge_list_item(destination, add, "name")
    destination = {key: set(lst) for key, lst in destination.items()}
    assert destination == {"name": {2}}

    destination = {"name": [1]}
    add = {"name": [2]}
    merge_list_item(destination, add, "name")
    destination = {key: set(lst) for key, lst in destination.items()}
    assert destination == {"name": {1, 2}}


def test_merge_dict_of_lists_item():
    destination = {}
    add = {}
    merge_dict_of_lists_item(destination, add, "name")
    assert destination == {}

    destination = {"name": {"sub_name": [1]}}
    add = {}
    merge_dict_of_lists_item(destination, add, "name")
    for key in destination:
        destination[key] = {
            sub_key: set(lst) for sub_key, lst in destination[key].items()
        }
    assert destination == {"name": {"sub_name": {1}}}

    destination = {}
    add = {"name": {"sub_name": [2]}}
    merge_dict_of_lists_item(destination, add, "name")
    for key in destination:
        destination[key] = {
            sub_key: set(lst) for sub_key, lst in destination[key].items()
        }
    assert destination == {"name": {"sub_name": {2}}}

    destination = {"name": {"sub_name": [1]}}
    add = {"name": {"sub_name": [2]}}
    merge_dict_of_lists_item(destination, add, "name")
    for key in destination:
        destination[key] = {
            sub_key: set(lst) for sub_key, lst in destination[key].items()
        }
    assert destination == {"name": {"sub_name": {1, 2}}}
