import pytest

from grayskull.base import Extra, Package
from grayskull.base.base_recipe import Grayskull


class EmptyGray(Grayskull):
    def refresh_section(self, section="", **kwargs):
        if section == "package":
            self.package.name = "PkgName"
            self.package.version = "1.0.0"
        elif section == "source":
            self.source.sha256 = "sha256_foo"
            self.source.url = "URL"
        elif section == "build":
            self.build.number = 1


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


def test_base_recipe_as_dict(monkeypatch):
    monkeypatch.setattr(
        Extra,
        "_get_git_current_user_metadata",
        lambda: {"total_count": 1, "items": [{"login": "marcelotrevisani"}]},
    )
    assert EmptyGray().as_dict() == {
        "package": {"name": "PkgName", "version": "1.0.0"},
        "source": {"sha256": "sha256_foo", "url": "URL"},
        "build": {"number": 1},
        "extra": {"recipe-maintainers": ["marcelotrevisani"]},
    }


def test_clean_section():
    pkg = Package(name="pkg_name", version="1.1.1")
    assert EmptyGray.clean_section(pkg) == {
        "name": "pkg_name",
        "version": "1.1.1",
    }
    pkg = Package(name="new_pkg")
    assert EmptyGray.clean_section(pkg) == {"name": "new_pkg"}
    pkg = Package(name="new_pkg", version="")
    assert EmptyGray.clean_section(pkg) == {"name": "new_pkg"}


def test_magic_methods():
    recipe = EmptyGray()
    assert recipe["package"] == Package(name="PkgName", version="1.0.0")

    recipe["package"] = Package(name="PkgName2", version="1.1.0")
    assert recipe["package"] == Package(name="PkgName2", version="1.1.0")

    with pytest.raises(ValueError) as exec_info:
        recipe["KEY_FOO"]
    assert exec_info.match("Section KEY_FOO not found.")


def test_jinja_variables():
    pkg = EmptyGray(name="pkg_name", version="1.1.1")
    pkg.set_jinja_variable("foo_var", 10)
    assert pkg.get_jinja_variable("foo_var") == 10
    pkg.set_jinja_variable("foo_var", 20)
    assert pkg.get_jinja_variable("foo_var") == 20
    assert (
        pkg._get_jinja_declaration() == '{% set name = "PkgName" %}\n'
        '{% set version = "1.0.0" %}\n'
        '{% set foo_var = "20" %}\n\n'
    )
    pkg.remove_jinja_variable("foo_var")
    assert pkg.get_jinja_variable("foo_var") is None


def test_generate_yaml(tmpdir, monkeypatch):
    monkeypatch.setattr(
        Extra,
        "_get_git_current_user_metadata",
        lambda: {"total_count": 1, "items": [{"login": "marcelotrevisani"}]},
    )
    pkg = EmptyGray()
    pkg.set_jinja_variable("foo_jinja_var", 10)
    recipe_content = r"""{% set name = "PkgName" %}
{% set version = "1.0.0" %}
{% set foo_jinja_var = "10" %}


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
    assert pkg.generate_recipe() == recipe_content
    recipe_root = tmpdir.mkdir("recipe")
    pkg.to_file(str(recipe_root))
    with open(str(recipe_root / "pkgname" / "meta.yaml"), "r") as recipe:
        content = recipe.read()
        assert content == recipe_content
