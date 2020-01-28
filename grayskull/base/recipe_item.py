from typing import Union

from grayskull.base.delimiters import Delimiters
from grayskull.base.selectors import Selectors


class RecipeItem:
    def __init__(
        self,
        name: str,
        delimiter: Union[str, Delimiters] = "",
        selector: Union[str, Selectors] = "",
    ):
        self._delimiter: Delimiters = Delimiters()
        self._selector: Selectors = Selectors()
        self._name: str = name.strip().split()[0]
        self.add_delimiter(delimiter if delimiter else name)
        if self._has_selector(name):
            name = name.strip().split()[1:]
            name = name[name.index("#") :]
            self.add_selector(" ".join(name))
        self.add_selector(selector)

    def _has_selector(self, value: str) -> bool:
        return " # [" in value

    def __repr__(self) -> str:
        rep = f"{self.name}"
        if len(self.delimiter) > 0:
            rep += f" {self.delimiter}"
        if len(self.selector) > 0:
            rep += f"  # [{self.selector}]"
        return rep.strip()

    def __eq__(self, other) -> bool:
        return str(self) == other

    @property
    def name(self) -> str:
        return self._name

    def add_delimiter(self, value: Union[str, Delimiters]):
        self._delimiter += value

    def add_selector(self, value: Union[str, Delimiters]):
        self._selector += value

    @property
    def delimiter(self) -> Delimiters:
        return self._delimiter

    @delimiter.setter
    def delimiter(self, value: Union[str, Delimiters]):
        self._delimiter = Delimiters(value) if isinstance(value, str) else value

    @property
    def selector(self) -> Selectors:
        return self._selector

    @selector.setter
    def selector(self, value: Union[str, Selectors]):
        self._selector = Selectors(value) if isinstance(value, str) else value
