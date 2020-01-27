from typing import List, Union

from grayskull.base.recipe_item import RecipeItem


class Section:
    def __init__(
        self,
        name: str,
        items: Union[
            List[str],
            str,
            "Section",
            List["Section"],
            RecipeItem,
            List[RecipeItem],
            None,
        ] = None,
    ):
        self._name = name.strip()
        self._value: Union[List["Section"], List[RecipeItem]] = []
        self.add_items(items)

    def __repr__(self) -> str:
        return f"Section(name={self._name})"

    @property
    def name(self) -> str:
        return f"{self._name}"

    def add_recipe_item(self, item: Union[str, RecipeItem]):
        if isinstance(item, str):
            item = RecipeItem(item)
        self._value.append(item)

    def get_values(
        self,
    ) -> Union[RecipeItem, List[RecipeItem], "Section", List["Section"]]:
        if len(self._value) == 1:
            return self._value[0]
        return self._value

    def add_subsection(self, section: Union[str, "Section"]):
        if isinstance(section, str):
            section = Section(section)
        self._value.append(section)

    def get_subsection(self, section: Union[str, "Section"]) -> "Section":
        if isinstance(section, str):
            section = Section(section)
        for sec in self._value:
            if isinstance(sec, Section) and sec.name == section.name:
                return sec
        raise ValueError(f"Subsection {section.name} does not exist.")

    def add_single_item(self, item: Union[str, RecipeItem, "Section"]):
        if isinstance(item, str):
            self._value.append(RecipeItem(item))
        else:
            self._value.append(item)

    def add_items(self, items: Union[List[str], List["Section"], List[RecipeItem]]):
        if not items:
            return
        if not isinstance(items, list):
            items = [items]
        for item in items:
            self.add_single_item(item)
