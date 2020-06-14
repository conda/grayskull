from ruamel.yaml.comments import CommentedSeq

from grayskull.base.recipe_item import RecipeItem


def test_recipe():
    seq = CommentedSeq(["importlib-metadata >=0.12", "pytest"])
    seq.yaml_add_eol_comment("[py<38]", 0)
    item = RecipeItem(0, seq)
    assert item.value == "importlib-metadata >=0.12"
    assert item.selector == "py<38"
    assert str(item) == "importlib-metadata >=0.12   # [py<38]"

    item.value = "importlib-metadata"
    item.selector = "py35"
    assert item.value == "importlib-metadata"
    assert item.selector == "py35"
    assert seq.ca.items[0][0].value == " # [py35]"
    assert seq[0] == "importlib-metadata"
    assert str(item) == "importlib-metadata   # [py35]"


def test_recipe_item_extract_selector():
    assert RecipeItem._extract_selector("# [win or osx]") == "win or osx"
    assert RecipeItem._extract_selector("deps1 >=0.12") == ""
    assert RecipeItem._extract_selector("pytest  # [unix]") == "unix"


def test_recipe_item_remove_selector():
    assert RecipeItem._remove_selector("# [win or osx]") == ""
    assert RecipeItem._remove_selector("deps1 >=0.12") == "deps1 >=0.12"
    assert RecipeItem._remove_selector("pytest  # [unix]") == "pytest"
