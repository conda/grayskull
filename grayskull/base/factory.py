from abc import ABC
from typing import Optional, Union

from grayskull.base.base_recipe import Recipe
from grayskull.pypi import PyPi


class GrayskullFactory(ABC):
    REGISTERED_CLASS = {
        "pypi": PyPi,
    }

    @staticmethod
    def create_recipe(
        repo_type: str, name: str, version: str = "", **kwargs
    ) -> Union[PyPi]:
        if repo_type.lower() not in GrayskullFactory.REGISTERED_CLASS:
            raise ValueError(
                f"Recipe generator {repo_type.lower()} does not exist.\n"
                f"Please inform a valid one."
                f"{', '.join(GrayskullFactory.REGISTERED_CLASS.keys())}"
            )
        return GrayskullFactory.REGISTERED_CLASS[repo_type.lower()](
            name, version, **kwargs
        )

    @staticmethod
    def guess_recipe_type(recipe: Recipe) -> Optional[str]:
        if (
            "noarch" in recipe["build"]
            and recipe["build"]["noarch"].values[0].value == "python"
        ):
            return "pypi"
        for url in recipe["source"]["url"].values:
            if "pypi." in url:
                return "pypi"
        if (
            "python" in recipe["requirements"]["host"]
            or "pip" in recipe["requirements"]["host"]
        ):
            return "pypi"
        return None

    @staticmethod
    def load_recipe(
        recipe_path: str, recipe_type: Optional[str] = None
    ) -> Union[Recipe, PyPi]:
        recipe = Recipe(load_recipe=recipe_path)
        if recipe_type is None:
            recipe_type = GrayskullFactory.guess_recipe_type(recipe)
        if recipe_type:
            return GrayskullFactory.REGISTERED_CLASS[recipe_type.lower()](
                load_recipe=recipe
            )
        return recipe
