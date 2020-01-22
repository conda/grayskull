import re
from dataclasses import dataclass
from typing import List

ALL_SELECTORS = (
    "x86",
    "x86_64",
    "linux",
    "linux32",
    "linux64",
    "armv6l",
    "armv7l",
    "ppc64le",
    "osx",
    "unix",
    "win",
    "win32",
    "win64",
    "py",
    "py3k",
    "py2k",
    "py27",
    "py34",
    "py35",
    "py36",
    "py37",
    "py38",
    "py39",
    "np",
    "vc",
)


class Selectors:
    @dataclass
    class SingleSelector:
        name: str
        operator: str = ""
        value: str = ""

        def __str__(self):
            return f"{self.name.strip()}{self.operator.strip()}{self.value.strip()}"

    def __init__(self, selectors: str):
        self._selectors = self._parser(selectors)

    def __getitem__(self, item: int) -> "SingleSelector":
        return self._selectors[item]

    @staticmethod
    def _parse_bracket(selector: str) -> List["SingleSelector"]:
        re_open_bracket = re.compile(r"(.*)([\(])(.*)", re.DOTALL)
        re_close_bracket = re.compile(r"(.*)([\)])(.*)", re.DOTALL)
        list_brackets = [("(", re_open_bracket), (")", re_close_bracket)]
        result = []
        for symbol, re_search in list_brackets:
            if symbol == selector:
                return [Selectors.SingleSelector(selector)]
            if symbol in selector:
                group_bracket = re_search.search(selector).groups()
                for bracket in group_bracket:
                    if not bracket:
                        continue
                    result += Selectors._parser(bracket)
        return result

    @staticmethod
    def _clean_selector(selector: str) -> str:
        selector = re.sub(r"\s*#\s*", "", selector)
        selector = re.sub(r"[\[\]]]*", "", selector)
        return selector.strip()

    @staticmethod
    def _parser(str_selector: str) -> List["SingleSelector"]:
        str_selector = Selectors._clean_selector(str_selector)
        selectors = str_selector.split()
        re_py_sel = re.compile(r"(\w+)\s*([<>!=]+)\s*(\d+)")
        result = []
        for sel in selectors:
            sel = sel.strip()
            if not sel:
                continue
            brackets = Selectors._parse_bracket(sel)
            if brackets:
                result += brackets
                continue

            py_sel = re_py_sel.findall(sel)
            if py_sel:
                sel = py_sel[0]
                result.append(Selectors.SingleSelector(*sel))
            else:
                result.append(Selectors.SingleSelector(sel))
        return result

    def remove_all(self):
        self._selectors = []
