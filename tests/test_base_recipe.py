from grayskull.base.base_recipe import Grayskull
from grayskull.base.extra import Extra


class EmptyGray(Grayskull):
    def refresh_section(self, section="", **kwargs):
        if section == "package":
            self._name = "PkgName"
            self._version = "1.0.0"
        elif section == "source":
            self["source"].add_subsection("sha256")
            self["source"].add_subsection("url")
            self["source"]["sha256"].add_item("sha256_foo")
            self["source"]["url"].add_item("URL")
        elif section == "build":
            self["build"].add_subsection("number")
            self["build"]["number"].add_item(1)


def test_getitem():
    pkg = EmptyGray("pytest", "5.0.0")
    assert pkg["build"].section_name == "build"
    assert pkg["build"]["number"].section_name == "number"
    assert pkg["build"]["number"][0] == 1


def test_extra_dataclass(monkeypatch):
    extra = Extra()
    extra.add_r_group()
    assert extra.recipe_maintainers == ["conda-forge/r"]
    extra.add_maintainer(name="foo")
    assert extra.recipe_maintainers == ["conda-forge/r", "foo"]
    monkeypatch.setattr(
        Extra,
        "_get_git_current_user_metadata",
        lambda: {"total_count": 1, "items": [{"login": "marcelotrevisani"}]},
    )
    extra.add_git_current_user()
    assert extra.recipe_maintainers == [
        "conda-forge/r",
        "foo",
        "marcelotrevisani",
    ]


def test_generate_yaml(tmpdir, monkeypatch):
    monkeypatch.setattr(
        Extra,
        "_get_git_current_user_metadata",
        lambda: {"total_count": 1, "items": [{"login": "marcelotrevisani"}]},
    )
    pkg = EmptyGray()
    recipe_content = r"""{% set name = "PkgName" %}
{% set version = "1.0.0" %}


package:
  name: '{{ name|lower }}'
  version: '{{ version }}'

source:
  sha256: sha256_foo
  url: URL

build:
  number: 1

extra:
  recipe-maintainers:
    - marcelotrevisani

"""
    assert pkg.create_recipe_from_scratch() == recipe_content
    recipe_root = tmpdir.mkdir("recipe")
    pkg.to_file(str(recipe_root))
    with open(str(recipe_root / "pkgname" / "meta.yaml"), "r") as recipe:
        content = recipe.read()
        assert content == recipe_content
