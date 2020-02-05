from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Iterator, List, Tuple, Union

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from grayskull.base.section import Section


class Grayskull(ABC):
    ALL_SECTIONS = (
        "package",
        "source",
        "build",
        "outputs",
        "requirements",
        "app",
        "test",
        "about",
        "extra",
    )

    def __init__(self, name=None, version=None):
        self._yml_config = YAML()
        self._name = name
        self._version = version
        self._extra_jinja_variables = []
        self._yml_config.indent(mapping=2, sequence=4, offset=2)
        self._yaml = CommentedMap()
        for section in self.ALL_SECTIONS:
            Section(section, self._yaml)
        self.refresh_all_recipe()
        super(Grayskull, self).__init__()

    def refresh_all_recipe(self):
        for section in self.ALL_SECTIONS:
            self.refresh_section(section)

    @property
    def jinja_header(self) -> List:
        return self._extra_jinja_variables

    @jinja_header.setter
    def jinja_header(self, jinja_list: List[str]):
        self._extra_jinja_variables = jinja_list

    @abstractmethod
    def refresh_section(self, section: str = "", **kwargs):
        pass

    @property
    def yaml_obj(self) -> CommentedMap:
        return self._yaml

    def __getitem__(self, item) -> Any:
        if item in self.ALL_SECTIONS:
            if self._yaml.get(item) is None:
                self._yaml[item] = CommentedMap()
            return Section(item, self._yaml[item])
        else:
            raise ValueError(f"Section {item} not found.")

    def __setitem__(self, item: str, value: Any):
        if item in self.ALL_SECTIONS:
            self._yaml[item] = value
        else:
            raise ValueError(f"Section {item} not found.")

    def __len__(self) -> int:
        return len(self.ALL_SECTIONS)

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        for section in self.ALL_SECTIONS:
            yield section, self[section]

    def create_recipe_from_scratch(self) -> str:
        """Generate the recipe in a string format.

        :return str:
        """
        self["package"]["version"].value = r"{{ version }}"
        self["package"]["name"].value = r"{{ name|lower }}"
        body = ""
        for section in self.ALL_SECTIONS:
            if not section or section not in self:
                continue
            yaml_value = self._yml_config.dump({section: self[section]},)
            body += f"{yaml_value}\n"
        return f"{self._get_jinja_declaration()}\n{body}"

    def _get_jinja_declaration(self) -> str:
        """Responsible to generate the jinja variable declaration.

        :return str: String with jinja variable declaration
        """
        extra_header = ""
        for jinja_value in self._extra_jinja_variables:
            extra_header += f'{{% {jinja_value}" %}}\n'
        return (
            f'{{% set name = "{self._name}" %}}\n'
            f'{{% set version = "{self._version}" %}}\n'
            f"{extra_header}\n"
        )

    def to_file(self, folder_path: Union[str, Path] = "."):
        """Write the recipe in a location. It will create a folder with the
        package name and the recipe will be there.

        :param folder_path: Path to the folder
        """
        recipe_dir = Path(folder_path) / self._name.lower()
        if not recipe_dir.is_dir():
            recipe_dir.mkdir()
        recipe_path = recipe_dir / "meta.yaml"
        with recipe_path.open("w+") as recipe:
            recipe.write(self.create_recipe_from_scratch())
