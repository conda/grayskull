from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple, Union

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap


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
        yml = YAML()
        yml.indent(mapping=2, sequence=4, offset=2)
        self._yaml = CommentedMap()
        self.refresh_all_recipe()
        super(Grayskull, self).__init__()

    def refresh_all_recipe(self):
        for section in self.ALL_SECTIONS:
            self.refresh_section(section)

    @abstractmethod
    def refresh_section(self, section: str = "", **kwargs):
        pass

    def __getitem__(self, item) -> Any:
        if item in self.ALL_SECTIONS:
            return getattr(self, item.lower())
        raise ValueError(f"Section {item} not found.")

    def __setitem__(self, item: str, value: Any):
        if item in self.ALL_SECTIONS:
            setattr(self, item, asdict(value))
        else:
            raise ValueError(f"Section {item} not found.")

    def __len__(self) -> int:
        return len(self.ALL_SECTIONS)

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        for section in self.ALL_SECTIONS:
            yield section, self[section]

    def as_dict(self, exclude_empty_values: bool = True) -> Dict[str, Any]:
        """Convert the recipe attributes to a dict to be able to dump it in a
        yaml file.

        :param exclude_empty_values: If True it will exclude the empty values
            in the recipe. Otherwise it will return everything
        :return dict:
        """
        if exclude_empty_values:
            result = self.clean_section(
                {
                    section: self.clean_section(value)
                    for section, value in self
                    if section != "extra"
                }
            )
        else:
            result = dict(self)
        result.update({"extra": {"recipe-maintainers": self.extra.recipe_maintainers}})
        return result

    @staticmethod
    def clean_section(section: Any) -> dict:
        """Create a new dictionary without None values.

        :param section: Receives a dict or a namedtuple
        :return dict: return a new dict without the None values
        """
        if not isinstance(section, dict):
            section = asdict(section)
        return {key: value for key, value in section.items() if value}

    def generate_recipe(self) -> str:
        """Generate the recipe in a string format.

        :return str:
        """
        body_dict = self.as_dict()
        body_dict["package"]["version"] = r"{{ version }}"
        body_dict["package"]["name"] = r"{{ name|lower }}"
        body = ""
        for section in self.ALL_SECTIONS:
            if section not in body_dict:
                continue
            yaml = YAML()
            yaml_value = yaml.dump({section: body_dict[section]},)
            body += f"{yaml_value}\n"
        return f"{self._get_jinja_declaration()}\n{body}"

    def _get_jinja_declaration(self) -> str:
        """Responsible to generate the jinja variable declaration.

        :return str: String with jinja variable declaration
        """
        extra_header = ""
        for name_jinja, jinja_value in self._extra_jinja_variables.items():
            extra_header += f'{{% set {name_jinja} = "{jinja_value}" %}}\n'
        return (
            f'{{% set name = "{self.package.name}" %}}\n'
            f'{{% set version = "{self.package.version}" %}}\n'
            f"{extra_header}\n"
        )

    def set_jinja_variable(self, name: str, value: Any):
        """Set new jinja variables to be add

        :param name: Variable name
        :param value: Value
        """
        self._extra_jinja_variables[name] = value

    def remove_jinja_variable(self, name: str):
        """Remove Jinja variable from the recipe

        :param name: Jinja variable name
        """
        if name in self._extra_jinja_variables:
            del self._extra_jinja_variables[name]

    def get_jinja_variable(self, name: str) -> Any:
        """Get the value of the Jinja variable

        :param name: Jinja variable name
        :return: Jinja variable value
        """
        return self._extra_jinja_variables.get(name, None)

    def to_file(self, folder_path: Union[str, Path] = "."):
        """Write the recipe in a location. It will create a folder with the
        package name and the recipe will be there.

        :param folder_path: Path to the folder
        """
        recipe_dir = Path(folder_path) / self.package.name.lower()
        if not recipe_dir.is_dir():
            recipe_dir.mkdir()
        recipe_path = recipe_dir / "meta.yaml"
        with recipe_path.open("w+") as recipe:
            recipe.write(self.generate_recipe())
