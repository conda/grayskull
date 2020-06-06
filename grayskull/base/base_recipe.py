import logging
import os
import re
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from shutil import copyfile
from typing import Any, List, Optional, Union

from colorama import Fore
from ruamel.yaml import YAML, CommentToken
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import CommentMark

from grayskull.base.extra import get_git_current_user
from grayskull.base.recipe_item import RecipeItem
from grayskull.base.section import Section
from grayskull.cli.stdout import print_msg

yaml = YAML(typ="jinja2")
yaml.indent(mapping=2, sequence=4, offset=2)
yaml.width = 600


class AbstractRecipeModel(ABC):
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
    re_jinja_var = re.compile(
        r"^[{#]%\s*set\s+([a-zA-Z\._0-9\-]+)\s*=\s*(.*)\s*%}[\\n]*$",
        re.IGNORECASE | re.MULTILINE,
    )

    def __init__(self, name=None, version=None, load_recipe: str = ""):
        if load_recipe:
            with open(load_recipe, "r") as yaml_file:
                self._yaml = yaml.load(yaml_file)
        else:
            self._yaml = yaml.load(
                f'{{% set name = "{name}" %}}\n'
                "package:\n    name: {{ name|lower }}\n"
            )
            for section in self.ALL_SECTIONS[1:]:
                Section(section, self._yaml)
            if version:
                self.add_jinja_var("version", version)
                self["package"]["version"] = "<{ version }}"
            self["build"]["number"] = 0
            self.__files_copy: List = []
            self.update_all_recipe()
        super(AbstractRecipeModel, self).__init__()

    def __repr__(self) -> str:
        name = self.get_var_content(self["package"]["name"].values[0])
        version = self.get_var_content(self["package"]["version"].values[0])
        return f"{self.__class__.__name__}(name={name}, version={version})"

    @property
    def files_to_copy(self) -> List:
        return self.__files_copy

    @files_to_copy.setter
    def files_to_copy(self, path: str):
        self.__files_copy.append(path)

    def get_var_content(self, item: RecipeItem) -> str:
        re_var = re.match(
            r"^\s*[?:'\"]?\s*[{<]{\s*(\w+).*}}\s*[?:'\"]?\s*$",
            item.value,
            re.DOTALL | re.MULTILINE,
        )
        return self.get_jinja_var(re_var.groups()[0]) if re_var else item.value

    def set_var_content(self, item: RecipeItem, value: Any):
        re_var = re.match(
            r"^\s*[?:'\"]?\s*[{<]{\s*(\w+).*}}\s*[?:'\"]?\s*$",
            item.value,
            re.DOTALL | re.MULTILINE,
        )
        if re_var:
            self.set_jinja_var(re_var.groups()[0], value)
        else:
            item.value = value

    def add_jinja_var(self, name: str, value: Any):
        if self._yaml.ca.comment:
            if self._yaml.ca.comment[1]:
                self._yaml.ca.comment[1][-1].value = re.sub(
                    r"[\n]+$", "\n", self._yaml.ca.comment[1][-1].value, re.MULTILINE
                )
        else:
            self._yaml.ca.comment = [None, []]

        self._yaml.ca.comment[1].append(
            CommentToken(
                f'#% set {name} = "{value}" %}}',
                start_mark=CommentMark(0),
                end_mark=CommentMark(0),
            )
        )

    def update_all_recipe(self):
        for section in self.ALL_SECTIONS:
            self.refresh_section(section)

    def get_jinja_var(self, key: str) -> str:
        if not self._yaml.ca.comment and not self._yaml.ca.comment[1]:
            raise ValueError(f"Key {key} does not exist")

        comment = self.__find_commented_token_jinja_var(key)
        if comment.value:
            value = self.re_jinja_var.match(comment.value)
            value = re.sub(r"^\s*[\'\"]", "", value.groups()[1].strip())
            return re.sub(r"[\'\"]\s*$", "", value)
        raise ValueError(f"Key {key} does not exist")

    def __find_commented_token_jinja_var(self, key: str) -> Optional[CommentToken]:
        for comment in self._yaml.ca.comment[1]:
            match_jinja = AbstractRecipeModel.re_jinja_var.match(comment.value)
            if match_jinja and match_jinja.groups()[0] == key:
                return comment
        return None

    def set_jinja_var(self, key: str, value: Any):
        if not self._yaml.ca.comment and not self._yaml.ca.comment[1]:
            self.add_jinja_var(key, value)
            return
        comment = self.__find_commented_token_jinja_var(key)
        if comment:
            comment.value = f"#% set {key} = {value} %}}"
        else:
            self.add_jinja_var(key, value)

    @abstractmethod
    def refresh_section(self, section: str = "", **kwargs):
        pass

    @property
    def yaml_obj(self) -> CommentedMap:
        return self._yaml

    def __getitem__(self, item: str) -> Any:
        if item in self.ALL_SECTIONS:
            if self._yaml.get(item) is None:
                self._yaml[item] = CommentedMap()
            return Section(item, parent_yaml=self._yaml)
        else:
            raise KeyError(f"Section {item} not found.")

    def __setitem__(self, item: str, value: Any):
        if item in self.ALL_SECTIONS:
            self._yaml[item] = value
        else:
            raise KeyError(f"Section {item} not found.")

    def __iter__(self) -> Section:
        for section in self.ALL_SECTIONS:
            yield self[section]

    def generate_recipe(
        self,
        folder_path: Union[str, Path] = ".",
        mantainers: Optional[List] = None,
        disable_extra: bool = False,
    ):
        """Write the recipe in a location. It will create a folder with the
        package name and the recipe will be there.

        :param folder_path: Path to the folder
        """
        recipe_dir = Path(folder_path) / self.get_var_content(
            self["package"]["name"].values[0]
        )
        logging.debug(f"Generating recipe on folder: {recipe_dir}")
        if not recipe_dir.is_dir():
            recipe_dir.mkdir()
        recipe_path = recipe_dir / "meta.yaml"

        if not disable_extra:
            self._add_extra_section(mantainers)

        with recipe_path.open("w") as recipe:
            yaml.dump(self.get_clean_yaml(self._yaml), recipe)

        for file_to_recipe in self.files_to_copy:
            name = file_to_recipe.split(os.path.sep)[-1]
            if os.path.isfile(file_to_recipe):
                copyfile(file_to_recipe, os.path.join(recipe_dir, name))

    def _add_extra_section(self, maintainers: Optional[List] = None):
        if not self["extra"]:
            maintainers = maintainers if maintainers else [get_git_current_user()]
            self["extra"]["recipe-maintainers"].add_items(maintainers)
        prefix = f"\n   - {Fore.LIGHTMAGENTA_EX}"
        print_msg(f"Maintainers:{prefix}{prefix.join(maintainers)}")

    def get_clean_yaml(self, recipe_yaml: CommentedMap) -> CommentedMap:
        result = self._clean_yaml(recipe_yaml)
        return self._add_new_lines_after_section(result)

    def _add_new_lines_after_section(self, recipe_yaml: CommentedMap) -> CommentedMap:
        for section in recipe_yaml.keys():
            if section == "package":
                recipe_yaml.yaml_set_comment_before_after_key(section, "\n\n\n")
            else:
                recipe_yaml.yaml_set_comment_before_after_key(section, "\n")
        return recipe_yaml

    def _clean_yaml(self, recipe_yaml: CommentedMap):
        recipe = deepcopy(recipe_yaml)
        for key, value in recipe_yaml.items():
            if key == "extra" or (key == "test" and value):
                continue
            if not isinstance(value, bool) and not value:
                del recipe[key]
            elif isinstance(value, (CommentedMap, dict)):
                if key != "requirements":
                    self.__reduce_list(key, recipe)
        return recipe

    def __reduce_list(self, name, recipe: CommentedMap):
        for section in Section(name, recipe):
            if section == "entry_points":
                continue
            section.reduce_section()

    def populate_metadata_from_dict(self, metadata: Any, section: Section) -> Section:
        if not isinstance(metadata, bool) and not metadata:
            return section
        if isinstance(metadata, list):
            section.add_items(metadata)
            return section
        if isinstance(metadata, dict):
            for name, value in metadata.items():
                if isinstance(value, bool) or value:
                    self.populate_metadata_from_dict(
                        value, Section(name, section.yaml_obj)
                    )
        else:
            section.add_item(metadata)
        return section
