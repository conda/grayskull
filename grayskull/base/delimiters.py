import re
from dataclasses import dataclass
from typing import Iterator, List, Union


class Delimiters:
    @dataclass
    class SingleDelimiter:
        operator: str = ""
        version: str = ""

        def __str__(self) -> str:
            return f"{self.operator.strip()}{self.version.strip()}"

    def __init__(self, delimiter: str = ""):
        self._delimiters: List[Delimiters.SingleDelimiter] = self._parse(delimiter)

    def __len__(self) -> int:
        return len(self._delimiters)

    def __iter__(self) -> Iterator["Delimiters.SingleDelimiter"]:
        return iter(self._delimiters)

    def __repr__(self) -> str:
        return ",".join([str(d) for d in self._delimiters])

    def __add__(self, other: Union[str, "Delimiters"]) -> "Delimiters":
        if isinstance(other, str):
            return Delimiters(f"{self},{other}")
        elif isinstance(other, Delimiters):
            return Delimiters(f"{self},{other}")
        raise ValueError(
            f"Value received is not allowed to use the operator +. Received: {other}"
        )

    def __sub__(self, delimiter: Union[str, "Delimiters"]) -> "Delimiters":
        list_delimiters = self._parse(str(delimiter))
        result = []
        for d in self._delimiters:
            if d in list_delimiters:
                continue
            result.append(str(d))
        return Delimiters(",".join(result))

    @staticmethod
    def _parse(delimiter: str) -> List["Delimiters.SingleDelimiter"]:
        re_delimiter = re.findall(r"([<>!=]+)\s*([0-9a-zA-Z.\-_\*]+)", delimiter)
        return [
            Delimiters.SingleDelimiter(operator=val[0], version=val[1])
            for val in re_delimiter
        ]

    def add(self, delimiter: Union[str, "Delimiters"]):
        """Add a new delimiter

        :param delimiter: Delimiter to be added
        """
        if isinstance(delimiter, str):
            self._delimiters += self._parse(delimiter)
        elif isinstance(delimiter, Delimiters):
            for d in delimiter:
                if d in self._delimiters:
                    continue
                self._delimiters.append(d)
        else:
            raise ValueError(f"Value received is not allowed. Received: {delimiter}")

    def remove(self, delimiter: Union[str, "Delimiters"]):
        """Remove a specific delimiter, it is possible to pass a string with
        the delimiter to be removed or a Delimiter object

        :param delimiter: Delimiter to be removed
        """
        if not isinstance(delimiter, (str, Delimiters)):
            raise ValueError(f"Value received is not allowed. Received: {delimiter}")

        is_delimiters = isinstance(delimiter, Delimiters)
        for d in delimiter if is_delimiters else self._parse(delimiter):
            if d in self._delimiters:
                self._delimiters.remove(d)

    def remove_all(self):
        """Remove all delimiters"""
        self._delimiters = []
