from __future__ import annotations

import re
from abc import ABC
from pathlib import Path

from souschef.ingredient import Ingredient
from souschef.jinja_expression import get_global_jinja_var
from souschef.recipe import Recipe

from grayskull.strategy.cran import CranStrategy
from grayskull.strategy.pypi import PypiStrategy


class GrayskullFactory(ABC):
    REGISTERED_STRATEGY = {
        "pypi": PypiStrategy,
        "cran": CranStrategy,
    }

    @staticmethod
    def create_recipe(repo_type: str, config, pkg_name=None, sections_populate=None):
        if repo_type.lower() not in GrayskullFactory.REGISTERED_STRATEGY:
            raise ValueError(
                f"Recipe generator {repo_type.lower()} does not exist.\n"
                f"Please inform a valid one."
                f"{', '.join(GrayskullFactory.REGISTERED_STRATEGY.keys())}"
            )
        if Path(config.name).is_file() and not config.from_local_sdist:
            recipe = Recipe(load_file=config.name)
            recipe_name = _get_name(recipe)
            recipe_version = _get_version(recipe)
            config.name = (
                recipe_name.value
                if isinstance(recipe_name, Ingredient)
                else recipe_name
            )
            config.version = (
                recipe_version.value
                if isinstance(recipe_version, Ingredient)
                else recipe_version
            )
        else:
            pkg_name = pkg_name or config.name
            recipe = Recipe(name=pkg_name, version=config.version)
        if config.name.startswith(("<{", "{{", "r-{{", "r-<{")):
            config.name = get_global_jinja_var(recipe, "name")
        GrayskullFactory.REGISTERED_STRATEGY[repo_type.lower()].fetch_data(
            recipe, config, sections=sections_populate
        )

        if "build" not in recipe:
            recipe.add_section({"build": {"number": 0}})
        else:
            recipe["build"]["number"] = 0

        return recipe


def _get_name(recipe):
    return __get_var(recipe, "name")


def __get_var(recipe, val):
    if recipe["package"][val].value.strip().startswith("<{"):
        re_jinja_var = re.match(r"\s*<{\s*(\w+)", recipe["package"][val].value)
        if re_jinja_var:
            jinja_var = re_jinja_var.groups()[0]
            try:
                return get_global_jinja_var(recipe, jinja_var)
            except ValueError:
                return None
    return recipe["package"][val]


def _get_version(recipe):
    return __get_var(recipe, "version")
