from typing import Union

from grayskull.base.delimiters import Delimiters
from grayskull.base.selectors import Selectors


class RecipeItem:
    def __init__(
        self,
        value: str,
        delimiter: Union[str, Delimiters] = "",
        selector: Union[str, Selectors] = "",
    ):
        self._value: str = value.strip()
        self._delimiter: Delimiters = Delimiters()
        self._selector: Selectors = Selectors()
        self.add_delimiter(delimiter)
        self.add_selector(selector)

    def __repr__(self) -> str:
        rep = f"{self.value}"
        if len(self.delimiter) > 0:
            rep += f" {self.delimiter}"
        if len(self.selector) > 0:
            rep += f"  # [{self.selector}]"
        return rep.strip()

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, item: str):
        self._value = item.strip()

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
