import re
import weakref
from typing import Any, Optional, Union

from ruamel.yaml import CommentToken
from ruamel.yaml.comments import CommentedSeq


class RecipeItem:
    def __init__(self, position: int, yaml: CommentedSeq, item: Any = None):
        self.__yaml = weakref.ref(yaml)
        self.__pos = position
        if position >= len(yaml):
            yaml.append(None)
            self.value = item

    def __repr__(self) -> str:
        return (
            f"RecipeItem(position={self.__pos},"
            f" value={self.value}, selector={self.selector})"
        )

    def __str__(self) -> str:
        val = f"{self.__yaml()[self.__pos]}"
        comment = self._get_comment_token()
        if comment:
            val += f"  {comment.value}"
        return val

    def __lt__(self, other: "RecipeItem") -> bool:
        return self.value < other.value

    def __le__(self, other: "RecipeItem") -> bool:
        return self.value <= other.value

    def __gt__(self, other: "RecipeItem") -> bool:
        return self.value > other.value

    def __ge__(self, other: "RecipeItem") -> bool:
        return self.value >= other.value

    def __eq__(self, other: Union[str, int, "RecipeItem"]) -> bool:
        if isinstance(other, RecipeItem):
            return self.value == other.value and self.selector == other.selector
        return str(self) == str(other) or str(self.value) == str(other)

    @staticmethod
    def _extract_selector(item: str) -> str:
        """Extract the selectors from the string received.

        :param item: String to be parsed
        :return: It will return just the content of the selector
        """
        selector = re.search(r"\#\s+\[(.*)\]\s*$", item, re.DOTALL)
        if selector:
            return selector.groups()[0].strip()
        return ""

    @staticmethod
    def _remove_selector(item: str) -> str:
        """Remove the special characters which identifies the selector, if they
        are not present it will just return the same string as received.

        :param item: String to be removed the selector
        :return: New string without the selectors representation
        """
        return re.sub(r"\#\s+\[(.*)\]\s*$", "", item).strip()

    def _get_comment_token(self) -> Optional[CommentToken]:
        all_comment = self.__yaml().ca.items.get(self.__pos, None)
        return all_comment[0] if all_comment else None

    @property
    def value(self) -> Union[str, int, None]:
        return self.__yaml()[self.__pos]

    @value.setter
    def value(self, value: Union[str, int]):
        column = 8
        if isinstance(value, int):
            column += len(str(value))
            self.__yaml()[self.__pos] = value
        elif value:
            self.__yaml()[self.__pos] = self._remove_selector(value)
            column += len(str(self.__yaml()[self.__pos]))
        else:
            column += len(str(value))
            self.__yaml()[self.__pos] = value
        selector = self._extract_selector(str(value))
        if selector:
            sel = f"[{selector}]"
            self.__yaml().yaml_add_eol_comment(sel, self.__pos, column=column)

    @property
    def selector(self) -> Optional[str]:
        """Return just the content of the selector, without the special characters
        such as # and [ ]

        :return: Return the selector
        """
        comment = self._get_comment_token()
        if comment:
            return self._extract_selector(self._get_comment_token().value)
        return ""

    @selector.setter
    def selector(self, value: str):
        """Set the selector for this specific item. It is not necessary to
        add the # and [ or ]. Please add just the values.

        :param value: string values which represent the content of the selector
        """
        comment = self._get_comment_token()
        sel = self._extract_selector(value)
        if not sel:
            sel = self._remove_selector(value)
        sel = f"[{sel}]"
        if comment:
            comment.value = f" # {sel}"
        else:
            self.__yaml().yaml_add_eol_comment(sel, self.__pos)
