import re
import weakref
from typing import Optional, Union

from ruamel.yaml import CommentToken
from ruamel.yaml.comments import CommentedSeq


class RecipeItem:
    def __init__(self, position: int, yaml: CommentedSeq):
        self.__yaml = weakref.ref(yaml)
        self.__pos = position

    def __repr__(self) -> str:
        return f"RecipeItem(position={self.__pos}, yaml={self.__yaml()}"

    def __str__(self) -> str:
        val = f"{self.__yaml()[self.__pos]}"
        comment = self._get_comment_token()
        if comment:
            val += f"  {comment.value}"
        return val

    @staticmethod
    def _extract_selector(item: str) -> str:
        selector = re.search(r"\#\s+\[(.*)\]\s*$", item, re.DOTALL)
        if selector:
            return selector.groups()[0].strip()
        return ""

    @staticmethod
    def _remove_selector(item: str) -> str:
        return re.sub(r"\#\s+\[(.*)\]\s*$", "", item).strip()

    def _get_comment_token(self) -> Optional[CommentToken]:
        all_comment = self.__yaml().ca.items.get(self.__pos, None)
        return all_comment[0] if all_comment else None

    @property
    def value(self) -> Union[str, int, None]:
        return self.__yaml()[self.__pos]

    @value.setter
    def value(self, value: Union[str, int]):
        self.__yaml()[self.__pos] = self._remove_selector(value)
        selector = self._extract_selector(value)
        if selector:
            self.__yaml().yaml_add_eol_comment(selector, self.__pos, 0)

    @property
    def selector(self) -> Optional[str]:
        comment = self._get_comment_token()
        if comment:
            return self._extract_selector(self._get_comment_token().value)
        return ""

    @selector.setter
    def selector(self, value: str):
        comment = self._get_comment_token()
        sel = self._extract_selector(value)
        if not sel:
            sel = self._remove_selector(value)
        sel = f"[{sel}]"
        if comment:
            comment.value = f"# {sel}"
        else:
            self.__yaml().yaml_add_eol_comment(sel, self.__pos, 0)
