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

    def _parser(self, str_selector: str) -> List["SingleSelector"]:
        str_selector = re.sub(r"\s*#\s*", "", str_selector)
        str_selector = re.sub(r"[\[\]]]*", "", str_selector)
        selectors = str_selector.split()
        re_py_sel = re.compile(r"(\w+)\s*([<>!=]+)\s*(\d+)")
        re_open_bracket = re.compile(r"(.*)([\(])(.*)", re.DOTALL)
        re_close_bracket = re.compile(r"(.*)([\)])(.*)", re.DOTALL)
        result = []
        if isinstance(selectors, str):
            selectors = [selectors]
        for sel in selectors:
            sel = sel.strip()
            if not sel:
                continue
            if "(" == sel:
                result.append(self.SingleSelector(sel))
                continue
            if "(" in sel:
                open_bracket = re_open_bracket.search(sel).groups()
                for bracket in open_bracket:
                    if not bracket:
                        continue
                    result += self._parser(bracket)
            if ")" == sel:
                result.append(self.SingleSelector(sel))
                continue
            if ")" in sel:
                close_bracket = re_close_bracket.search(sel).groups()
                for bracket in close_bracket:
                    if not bracket:
                        continue
                    result += self._parser(bracket)

            py_sel = re_py_sel.findall(sel)
            if py_sel:
                sel = py_sel[0]
                result.append(self.SingleSelector(*sel))
            else:
                result.append(self.SingleSelector(sel))
        return result

    def remove_all(self):
        self._selectors = []
