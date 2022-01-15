from abc import ABC

from souschef.recipe import Recipe

from grayskull.strategy.pypi import PypiStrategy


class GrayskullFactory(ABC):
    REGISTERED_STRATEGY = {
        "pypi": PypiStrategy,
    }

    @staticmethod
    def create_recipe(repo_type: str, config, pkg_name=None):
        pkg_name = pkg_name or config.name
        if repo_type.lower() not in GrayskullFactory.REGISTERED_STRATEGY:
            raise ValueError(
                f"Recipe generator {repo_type.lower()} does not exist.\n"
                f"Please inform a valid one."
                f"{', '.join(GrayskullFactory.REGISTERED_STRATEGY.keys())}"
            )
        recipe = Recipe(name=pkg_name, version=config.version)
        GrayskullFactory.REGISTERED_STRATEGY[repo_type.lower()].fetch_data(
            recipe, config
        )
        return recipe
