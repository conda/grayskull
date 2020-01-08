from abc import ABC
from typing import Union

from grayskull.pypi import PyPi


class GrayskullFactory(ABC):
    REGISTERED_CLASS = {
        "pypi": PyPi,
    }

    @staticmethod
    def create_recipe(repo_type: str, name: str, version: str = "") -> Union[PyPi]:
        return GrayskullFactory.REGISTERED_CLASS[repo_type.lower()](name, version)
