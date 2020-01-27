from grayskull.base.recipe_item import RecipeItem


def test_recipe_item():
    item = RecipeItem("importlib-metadata ", " >=0.12 ", "# [py<38]")
    assert item.name == "importlib-metadata"
    assert str(item.delimiter) == ">=0.12"
    assert str(item.selector) == "py<38"
    assert str(item) == "importlib-metadata >=0.12  # [py<38]"

    item.add_delimiter("<1.0")
    assert str(item.delimiter) == ">=0.12,<1.0"
    assert str(item) == "importlib-metadata >=0.12,<1.0  # [py<38]"

    item.add_selector("# [win]")
    assert str(item.selector) == "py<38 or win"
    assert str(item) == "importlib-metadata >=0.12,<1.0  # [py<38 or win]"

    item = RecipeItem("importlib-metadata >=0.12  # [py<38]")
    assert item.name == "importlib-metadata"
    assert str(item.delimiter) == ">=0.12"
    assert str(item.selector) == "py<38"
    assert str(item) == "importlib-metadata >=0.12  # [py<38]"
