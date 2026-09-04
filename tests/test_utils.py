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
    rm_duplicated_deps,
    upgrade_v0_recipe_to_v1,
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


def test_rm_duplicated_deps():
    assert rm_duplicated_deps([]) is None
    # my-crazy-pkg is preferred because "my-crazy-pkg" < "my_craZy-pkg":
    assert rm_duplicated_deps(["my_craZy-pkg", "my-crazy-pkg"]) == ["my-crazy-pkg"]


def test_rm_dupliate_deps_with_star():
    assert rm_duplicated_deps(["typing-extensions", "typing_extensions *"]) == [
        "typing_extensions"
    ]


def test_upgrade_v0_recipe_to_v1_python_version_noarch(tmp_path):
    """V1 conversion should expand `tests.python.python_version` for noarch.

    Regression test for conda/grayskull#667: a `noarch: python` package with a
    pinned test Python (e.g. `{{ python_min }}.*`) must produce a
    `python_version` list that also tests the latest Python (`*`).
    """
    pytest.importorskip(
        "conda_recipe_manager", reason="conda-recipe-manager is not installed"
    )
    v0 = tmp_path / "meta.yaml"
    v0.write_text(
        """\
package:
  name: mypkg
  version: 1.0.0

build:
  noarch: python

requirements:
  host:
    - python {{ python_min }}.*
    - pip
  run:
    - python >={{ python_min }}

test:
  imports:
    - mypkg
  commands:
    - pip check
  requires:
    - pip
    - python {{ python_min }}.*

about:
  home: https://example.com
  license: MIT
  summary: test package
"""
    )
    upgrade_v0_recipe_to_v1(v0)

    v1 = v0.read_text()
    assert "python_version:" in v1
    assert "{{ python_min }}.*" in v1
    assert '"*"' in v1 or "'*'" in v1
