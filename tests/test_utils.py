import os
from pathlib import Path

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


@pytest.mark.xfail(
    reason="Requires fix in conda-recipe-manager to use python_min for noarch recipes"
)
@pytest.mark.parametrize(
    "skip_selector,expected_match",
    [
        ("# [py<310]", 'match(python_min, "<3.10")'),
        ("# [py<39]", 'match(python_min, "<3.9")'),
        ("# [py<38]", 'match(python_min, "<3.8")'),
    ],
)
def test_upgrade_v0_recipe_to_v1_noarch_uses_python_min_in_skip(
    tmp_path, skip_selector, expected_match
):
    """Test that V1 noarch recipes use python_min instead of python in skip conditions.

    When a noarch recipe has a skip condition based on Python version, the V1 format
    should use match(python_min, ...) instead of match(python, ...) because:
    - CFEP-25 introduced python_min as the standard for minimum Python version
    - The variant config only defines python_min, not python, for noarch recipes
    - Using match(python, ...) causes rattler-build to skip all variants

    See: https://github.com/conda/grayskull/issues/644
    """
    pytest.importorskip("conda_recipe_manager")

    # Create a V0 recipe with both noarch: python AND a skip condition
    # This can happen when check_noarch_python_for_new_deps() changes is_arch
    # from True to False after skip was already set
    v0_recipe = f"""\
{{% set name = "test-pkg" %}}
{{% set version = "1.0.0" %}}

package:
  name: {{{{ name|lower }}}}
  version: {{{{ version }}}}

build:
  skip: True  {skip_selector}
  noarch: python
  number: 0

requirements:
  host:
    - python >=3.10
    - pip
  run:
    - python >=3.10
"""

    recipe_path = tmp_path / "meta.yaml"
    recipe_path.write_text(v0_recipe)

    upgrade_v0_recipe_to_v1(recipe_path)

    v1_content = recipe_path.read_text()

    # The V1 recipe should use python_min in the skip condition for noarch recipes
    assert expected_match in v1_content, (
        f"Expected '{expected_match}' in V1 recipe for noarch package, "
        f"but got:\n{v1_content}"
    )
    # It should NOT use match(python, ...) for noarch recipes
    assert 'match(python, "' not in v1_content, (
        f"V1 noarch recipe should use python_min, not python, in skip condition. "
        f"Got:\n{v1_content}"
    )
