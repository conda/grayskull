import re
from dataclasses import astuple, dataclass
from typing import List, Union

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

        def __post_init__(self):
            py_sel = re.search(r"(\w+)\s*([<>!=]+)\s*(\d+)", self.name)
            if py_sel:
                self.name, self.operator, self.value = py_sel.groups()

        def __str__(self):
            return f"{self.name.strip()}{self.operator.strip()}{self.value.strip()}"

        def __eq__(self, other: Union[str, "SingleSelector"]) -> bool:
            if isinstance(other, str):
                return str(self) == other
            return astuple(self) == astuple(other)

    def __init__(self, selectors: str):
        self._selectors = self._parse(selectors)

    def __getitem__(self, item: int) -> "SingleSelector":
        return self._selectors[item]

    def __repr__(self) -> str:
        all_sel = " ".join([str(sel) for sel in self])
        return f"[{all_sel}]"

    @staticmethod
    def _parse_bracket(selector: str) -> List["SingleSelector"]:
        list_brackets = [
            ("(", re.compile(r"(.*)(\()(.*)", re.DOTALL)),
            (")", re.compile(r"(.*)(\))(.*)", re.DOTALL)),
        ]
        result = []
        for symbol, re_search in list_brackets:
            if symbol == selector:
                return [Selectors.SingleSelector(selector)]
            if symbol in selector:
                group_bracket = re_search.search(selector).groups()
                for bracket in group_bracket:
                    if not bracket:
                        continue
                    result += Selectors._parse(bracket)
                selector = re_search.sub(selector, "")
        return result

    @staticmethod
    def _clean_selector(selector: str) -> str:
        selector = re.sub(r"\s*#\s*", "", selector)
        selector = re.sub(r"[\[\]]]*", "", selector)
        return selector.strip()

    @staticmethod
    def _parse(str_selector: str) -> List["SingleSelector"]:
        str_selector = Selectors._clean_selector(str_selector)
        selectors = str_selector.split()
        result = []
        for sel in selectors:
            sel = sel.strip()
            if not sel:
                continue
            brackets = Selectors._parse_bracket(sel)
            if brackets:
                result += brackets
                continue

            result.append(Selectors.SingleSelector(sel))
        return result

    def remove_all(self):
        self._selectors = []
