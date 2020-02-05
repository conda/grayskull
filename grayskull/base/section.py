import weakref
from typing import Any, Iterator, Optional, Union

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
    def section_name(self) -> str:
        return self._section_name

    @property
    def yaml_obj(self) -> Union[CommentedMap, CommentedSeq]:
        """Get of the yaml object which is being handled for this section.
        """
        parent = (
            self.__parent
            if isinstance(self.__parent, CommentedMap)
            else self.__parent()
        )
        return parent[self.section_name]

    def __hash__(self) -> int:
        return hash(str(self))

    def __repr__(self) -> str:
        val = ""
        if isinstance(self.yaml_obj, CommentedSeq):
            val = f"items={self.yaml_obj}"
        elif isinstance(self.yaml_obj, CommentedMap):
            val = f"subsection={self.yaml_obj.keys()}"
        if val:
            val = f", {val}"
        return f"Section(section_name={self._section_name}{val})"

    def __len__(self) -> int:
        if self.yaml_obj:
            return len(self.yaml_obj)
        return 0

    def __iter__(self) -> Iterator:
        return iter(self.yaml_obj) if self.yaml_obj else iter([])

    def __getitem__(self, item: Union[str, int]) -> Union["Section", RecipeItem, None]:
        if isinstance(self.yaml_obj, CommentedMap):
            return self.yaml_obj.get(item, None)
        if isinstance(self.yaml_obj, CommentedSeq) and isinstance(item, int):
            return self.yaml_obj[item]
        return None

    def __setitem__(self, key: Union[str, int], value: Any):
        self.yaml_obj[key] = value

    def __getattr__(self, item: str) -> Union["Section", RecipeItem, None]:
        return self.__getitem__(item)

    def add_subsection(self, section: Union[str, "Section"]) -> "Section":
        """Add a subsection to the current Section. If the current section has a
        list of items or just an item, it will replace it by a subsection.

        :param section: Receives the name of a new subsection or a section object
        which will be populated as a child of the current section
        :return: Return the subsection added.
        """
        if not isinstance(self.yaml_obj, CommentedMap):
            self.__parent[self.section_name] = CommentedMap()
        if isinstance(section, Section):
            self.yaml_obj[section.section_name] = section.yaml_obj
        return Section(section, parent_yaml=self.yaml_obj)

    def add_item(self, item: Union[str, int]) -> RecipeItem:
        """Add a new item to the current section

        :param item: Receive the value for the current item
        :return: Return the item added to the current section
        """
        if not isinstance(self.yaml_obj, CommentedSeq):
            self.__parent[self.section_name] = CommentedSeq()
        self.__parent[self.section_name].append(item)
        return RecipeItem(len(self) - 1, self.yaml_obj)
