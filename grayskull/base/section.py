import weakref
from typing import Any, Iterator, List, Optional, Union

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from grayskull.base.recipe_item import RecipeItem


class Section:
    def __init__(self, section_name: str, parent_yaml: Optional[CommentedMap] = None):
        self._section_name = section_name.strip()
        if parent_yaml is None:
            self.__parent = CommentedMap()
            if section_name not in self.__parent:
                self.__parent[section_name] = None
        else:
            if section_name not in parent_yaml:
                parent_yaml[section_name] = None
            self.__parent = weakref.ref(parent_yaml)

    @property
    def values(self) -> List:
        parent = self._get_parent()
        result = []
        if isinstance(self.yaml_obj, CommentedMap):
            result = [Section(name, self.yaml_obj) for name in self.yaml_obj.keys()]
        elif isinstance(self.yaml_obj, dict):
            parent[self.section_name] = CommentedMap(self.yaml_obj)
            result = [Section(name, self.yaml_obj) for name in self.yaml_obj.keys()]
        elif isinstance(self.yaml_obj, CommentedSeq):
            result = [
                RecipeItem(pos, self.yaml_obj) for pos in range(len(self.yaml_obj))
            ]
        elif self.yaml_obj is not None:
            parent[self.section_name] = CommentedSeq([self.yaml_obj])
            result = [RecipeItem(0, parent[self.section_name])]
        return result

    @property
    def section_name(self) -> str:
        return self._section_name

    def _get_parent(self):
        if isinstance(self.__parent, CommentedMap):
            return self.__parent
        return self.__parent()

    @property
    def yaml_obj(self) -> Union[CommentedMap, CommentedSeq]:
        """Get of the yaml object which is being handled for this section.
        Please do not modify this object directly unless you know what you are
        doing.
        """
        parent = self._get_parent()
        if self.section_name not in parent:
            self.add_subsection(self.section_name)
        return parent[self.section_name]

    def reduce_section(self):
        if not self.values:
            return
        if isinstance(self.values[0], Section):
            for section in self.values:
                section.reduce_section()
        elif isinstance(self.values[0], RecipeItem):
            for recipe_item in self.values:
                if recipe_item.value is None:
                    self.yaml_obj.pop(self.yaml_obj.index(recipe_item.value))
            if len(self.yaml_obj) == 1:
                val = self._get_parent()[self.section_name][0]
                if self._get_parent()[self.section_name].ca.items:
                    comment_token = self.yaml_obj.ca.items.get(0)
                    if comment_token:
                        comment_token[0].value = f" {comment_token[0].value}"
                        self._get_parent().ca.items[self.section_name] = [
                            None,
                            None,
                            comment_token[0],
                            None,
                        ]
                self._get_parent()[self.section_name] = val

    def __hash__(self) -> int:
        return hash(f"{self}-{[str(v) for v in self.values]}")

    def __str__(self) -> str:
        return self.section_name

    def __repr__(self) -> str:
        val = ""
        if isinstance(self.yaml_obj, (CommentedMap, dict)):
            val = f"subsection={list(self.yaml_obj.keys())}"
        elif self.yaml_obj is not None:
            val = f"items={self.yaml_obj}"
        if val:
            val = f", {val}"
        return f"Section(section_name={self._section_name}{val})"

    def __len__(self) -> int:
        if self.yaml_obj:
            return len(self.yaml_obj)
        return 0

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, Section):
            return other.yaml_obj == self.yaml_obj
        if len(self.values) == 1:
            return self.values[0] == other or str(self.section_name) == str(other)
        if isinstance(other, str):
            return str(self.section_name) == str(other)
        if isinstance(other, list) and isinstance(other[0], str):
            for pos, item in enumerate(self.values):
                if item.value != other[pos] and str(item.value) != other[pos]:
                    return False
            return True
        return other == self.values

    def __iter__(self) -> Iterator:
        if not self.yaml_obj:
            return iter([])
        return iter(self.values)

    def __getitem__(self, item: Union[str, int]) -> Union["Section", RecipeItem, None]:
        if isinstance(item, str):
            for child in self.values:
                if child.section_name == item:
                    return child
            return Section(item, parent_yaml=self.yaml_obj)
        return self.values[item]

    def __setitem__(self, key: str, value: Any):
        if key not in self.yaml_obj:
            self.add_subsection(key)
        if isinstance(value, (str, int)):
            self.yaml_obj[key] = CommentedSeq()
            self[key].add_item(value)
        elif isinstance(value, dict):
            Section(key, self.yaml_obj)

    def add_subsection(self, section: Union[str, "Section"]):
        """Add a subsection to the current Section. If the current section has a
        list of items or just an item, it will replace it by a subsection.

        :param section: Receives the name of a new subsection or a section object
        which will be populated as a child of the current section
        """
        if not isinstance(self.yaml_obj, CommentedMap):
            self._get_parent()[self.section_name] = CommentedMap()
        if isinstance(section, Section):
            self._get_parent()[section.section_name] = section.yaml_obj
        return Section(section, parent_yaml=self.yaml_obj)

    def add_item(self, item: Union[str, int]):
        """Add a new item to the current section

        :param item: Receive the value for the current item
        """
        if not isinstance(self.yaml_obj, CommentedSeq):
            self._get_parent()[self.section_name] = CommentedSeq()
        RecipeItem(len(self.yaml_obj), self.yaml_obj, item)

    def add_items(self, items: List):
        for item in items:
            self.add_item(item)
