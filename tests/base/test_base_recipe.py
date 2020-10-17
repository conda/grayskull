import os

from pytest import fixture

from grayskull.base.base_recipe import AbstractRecipeModel


class EmptyGray(AbstractRecipeModel):
    def refresh_section(self, section="", **kwargs):
        if section == "source":
            self["source"]["sha256"] = "sha256_foo"
            self["source"]["url"] = "URL"
        elif section == "build":
            self["build"]["number"] = 1


@fixture
def data_recipes(data_dir: str) -> str:
    return os.path.join(data_dir, "recipes")


def test_update_all_recipe(data_recipes):
    recipe = EmptyGray(load_recipe=os.path.join(data_recipes, "simple_jinja_var.yaml"))
    recipe.update_all_recipe()
    assert recipe["build"]["number"] == 1
    assert recipe["source"]["sha256"] == "sha256_foo"
    assert recipe["source"]["url"] == "URL"


def test_refresh_section(data_recipes):
    recipe = EmptyGray(load_recipe=os.path.join(data_recipes, "simple_jinja_var.yaml"))
    assert "number" not in recipe["source"]

    recipe.refresh_section("build")
    assert recipe["build"]["number"].values[0] == 1
    assert "sha256" not in recipe["source"]
    assert "url" not in recipe["source"]

    recipe.refresh_section("source")
    assert recipe["build"]["number"] == 1
    assert recipe["source"]["sha256"] == "sha256_foo"
    assert recipe["source"]["url"] == "URL"


def test_generate_recipe(tmpdir, data_recipes):
    recipe = EmptyGray(name="pkg1", version="1.0.0")
    recipe.update_all_recipe()
    recipe.generate_recipe(tmpdir, mantainers=["marcelotrevisani"])

    with open(tmpdir / "pkg1" / "meta.yaml") as recipe_file:
        generated_recipe = recipe_file.read()
    with open(os.path.join(data_recipes, "empty_gray.yaml")) as recipe_file:
        exp_recipe = recipe_file.read()
    assert generated_recipe == exp_recipe


def test_jinja_var(data_recipes):
    recipe = EmptyGray(load_recipe=os.path.join(data_recipes, "simple_jinja_var.yaml"))
    assert recipe.get_jinja_var("name") == "foo_pkg-123.test"
    assert recipe.get_jinja_var("version") == "1.2.4"
    assert recipe["package"]["name"] == "<{ name|lower }}"
    assert recipe["package"]["version"] == "<{ version }}"

    recipe.set_jinja_var("version", "0.1.1")
    assert recipe.get_jinja_var("version") == "0.1.1"

    recipe.add_jinja_var("foo", "bar")
    assert recipe.get_jinja_var("foo") == "bar"

    recipe.set_jinja_var("bar", "foo")
    assert recipe.get_jinja_var("bar") == "foo"


def test_set_default_values():
    recipe = EmptyGray(name="PkgName", version="1.0.0")
    assert recipe.get_var_content(recipe["package"]["name"].values[0]) == "PkgName"
    assert recipe["package"]["name"].values[0] == "<{ name|lower }}"

    assert recipe["package"]["version"].values[0] == "<{ version }}"
    assert recipe.get_var_content(recipe["package"]["version"].values[0]) == "1.0.0"


def test_get_set_var_content():
    recipe = EmptyGray(name="PkgName", version="1.0.0")
    assert recipe.get_var_content(recipe["package"]["name"].values[0]) == "PkgName"
    assert recipe.get_var_content(recipe["package"]["version"].values[0]) == "1.0.0"

    recipe.set_var_content(recipe["package"]["version"].values[0], "2.1.3")
    assert recipe.get_var_content(recipe["package"]["version"].values[0]) == "2.1.3"
    assert recipe["package"]["version"].values[0] == "<{ version }}"


def test_getitem():
    pkg = EmptyGray("pytest", "5.0.0")
    assert pkg["build"].section_name == "build"
    assert pkg["build"]["number"].section_name == "number"
    assert pkg["build"]["number"][0] == 1
