from abc import ABC
from typing import Union

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
