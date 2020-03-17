import os

from pytest import fixture

from grayskull.base.base_recipe import MetaRecipeModel, update


class EmptyGray(metaclass=MetaRecipeModel):
    @update("source")
    def update_source(self):
        self["source"]["sha256"] = "sha256_foo"
        self.recipe["source"]["url"] = "URL"

    @update("build")
    def update_build(self):
        self.recipe["build"]["number"] = 1


@fixture
def data_recipes(data_dir: str) -> str:
    return os.path.join(data_dir, "recipes")


def test_update_all_recipe(data_recipes):
    recipe = EmptyGray(load_recipe=os.path.join(data_recipes, "simple_jinja_var.yaml"))
    recipe.update_all()
    assert recipe.recipe["build"]["number"] == 1
    assert recipe.recipe["source"]["sha256"] == "sha256_foo"
    assert recipe["source"]["url"] == "URL"


def test_refresh_section(data_recipes):
    recipe = EmptyGray(load_recipe=os.path.join(data_recipes, "simple_jinja_var.yaml"))
    assert "number" not in recipe.recipe["source"]

    recipe.update("build")
    assert recipe.recipe["build"]["number"].values[0] == 1
    assert "sha256" not in recipe.recipe["source"]
    assert "url" not in recipe.recipe["source"]

    recipe.update("source")
    assert recipe.recipe["build"]["number"] == 1
    assert recipe.recipe["source"]["sha256"] == "sha256_foo"
    assert recipe.recipe["source"]["url"] == "URL"


def test_generate_recipe(tmpdir, data_recipes):
    recipe = EmptyGray(name="pkg1", version="1.0.0")
    recipe.update_all()
    recipe.recipe.generate_recipe(tmpdir, mantainers=["marcelotrevisani"])

    with open(tmpdir / "pkg1" / "meta.yaml") as recipe_file:
        generated_recipe = recipe_file.read()
    with open(os.path.join(data_recipes, "empty_gray.yaml")) as recipe_file:
        exp_recipe = recipe_file.read()
    assert generated_recipe == exp_recipe


def test_jinja_var(data_recipes):
    recipe = EmptyGray(load_recipe=os.path.join(data_recipes, "simple_jinja_var.yaml"))
    assert recipe.recipe.get_jinja_var("name") == "foo_pkg-123.test"
    assert recipe.recipe.get_jinja_var("version") == "1.2.4"
    assert recipe.recipe["package"]["name"] == "<{ name|lower }}"
    assert recipe.recipe["package"]["version"] == "<{ version }}"

    recipe.recipe.set_jinja_var("version", "0.1.1")
    assert recipe.recipe.get_jinja_var("version") == "0.1.1"

    recipe.recipe.add_jinja_var("foo", "bar")
    assert recipe.recipe.get_jinja_var("foo") == "bar"

    recipe.recipe.set_jinja_var("bar", "foo")
    assert recipe.recipe.get_jinja_var("bar") == "foo"


def test_set_default_values():
    recipe = EmptyGray(name="PkgName", version="1.0.0")
    assert (
        recipe.recipe.get_var_content(recipe.recipe["package"]["name"].values[0])
        == "PkgName"
    )
    assert recipe.recipe["package"]["name"].values[0] == "<{ name|lower }}"

    assert recipe.recipe["package"]["version"].values[0] == "<{ version }}"
    assert (
        recipe.recipe.get_var_content(recipe.recipe["package"]["version"].values[0])
        == "1.0.0"
    )


def test_get_set_var_content():
    recipe = EmptyGray(name="PkgName", version="1.0.0")
    assert (
        recipe.recipe.get_var_content(recipe.recipe["package"]["name"].values[0])
        == "PkgName"
    )
    assert (
        recipe.recipe.get_var_content(recipe.recipe["package"]["version"].values[0])
        == "1.0.0"
    )

    recipe.recipe.set_var_content(
        recipe.recipe["package"]["version"].values[0], "2.1.3"
    )
    assert (
        recipe.recipe.get_var_content(recipe.recipe["package"]["version"].values[0])
        == "2.1.3"
    )
    assert recipe.recipe["package"]["version"].values[0] == "<{ version }}"


def test_getitem():
    pkg = EmptyGray("pytest", "5.0.0")
    pkg.update_all()
    assert pkg.recipe["build"].section_name == "build"
    assert pkg.recipe["build"]["number"].section_name == "number"
    assert pkg.recipe["build"]["number"][0] == 1


class MetaFoo(metaclass=MetaRecipeModel):
    def __init__(self, name, version, load_recipe):
        self.update_req = []

    @update("requirements", "build")
    def update_requirements(self, section):
        self.update_req.append(section)


def test_meta_recipe_register():
    meta_obj = MetaFoo()
    assert meta_obj.update_req == ["requirements", "build"]
    meta_obj.update("build")
    assert meta_obj.update_req == ["requirements", "build", "build"]

    meta_obj = MetaFoo()
    assert sorted(meta_obj.update_req) == ["build", "requirements"]
    meta_obj.update_all()
    assert sorted(meta_obj.update_req) == sorted(["build", "requirements"] * 2)


def test_has_selectors():
    recipe = EmptyGray(name="PkgName", version="1.0.0")
    recipe["package"].add_item("foo  # [win]")
    assert recipe.recipe.has_selectors()

    recipe = EmptyGray(name="PkgName", version="1.0.0")
    recipe["package"].add_item("foo")
    assert not recipe.recipe.has_selectors()

    recipe["outputs"].add_subsection("sec2")
    recipe["outputs"]["sec2"].add_item("bar")
    assert not recipe.recipe.has_selectors()
    recipe["outputs"]["sec2"].add_item("foobar  # [unix]")
