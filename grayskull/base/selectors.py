import re
from dataclasses import dataclass


class Selectors:
    @dataclass
    class SingleSelector:
        name: str = ""
        operator: str = ""
        value: str = ""

        def __str__(self):
            return f"{self.name.strip()}{self.operator.strip()}{self.value.strip()}"

    def __init__(self, selectors: str):
        self._selectors = []

    def _parser(self):
        re.compile(r"\s+")

    def __and__(self, other):
        return

    def __or__(self, other):
        pass
