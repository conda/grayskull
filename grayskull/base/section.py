from abc import ABC
from typing import Dict, List, Union

from grayskull.base.recipe_item import RecipeItem


class Section(ABC):
    ALL_SUBSECTIONS_ALLOWED = tuple()

    def __init__(
        self,
        section_name: str,
        items: Union[
            List[str],
            str,
            "Section",
            List["Section"],
            RecipeItem,
            List[RecipeItem],
            None,
        ] = None,
        subsections: Union[List, Dict, None] = None,
    ):
        self._section_name = section_name.strip()
        self._value: Union[List["Section"], List[RecipeItem]] = []
        self.add_items(items)
        self._populate_subsections(subsections)

    def _populate_subsections(self, subsections: Union[List, Dict]):
        if not subsections:
            return
        if isinstance(subsections, list):
            for section in subsections:
                self.add_subsection(section)
        else:
            for key, value in subsections.items():
                self.add_subsection(key, value)

    # def __repr__(self) -> str:
    #     elements = ", ".join(str(v) for v in self._value)
    #     return f"{self._section_name}({elements})"

    @property
    def section_name(self) -> str:
        return f"{self._section_name}"

    def add_recipe_item(self, item: Union[str, RecipeItem]):
        if isinstance(item, str):
            item = RecipeItem(item)
        self._value.append(item)

    def __iter__(self):
        return iter(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __getitem__(self, item: str) -> "Section":
        for section in self._value:
            if isinstance(section, Section) and section.section_name == item:
                return section
        if item not in self.ALL_SUBSECTIONS_ALLOWED:
            raise ValueError(f"Item {item} does not exist.")
        self.add_subsection(item)
        return self.__getitem__(item)

    def __getattr__(self, item: str):
        return self[item]

    def __eq__(self, value):
        if len(self._value) == 1 and not isinstance(value, list):
            return str(self._value[0]) == str(value) or self._value[0] == value
        return self._value == value or value == [str(v) for v in self._value]

    @property
    def value(self,) -> Union[RecipeItem, List[RecipeItem], "Section", List["Section"]]:
        if len(self._value) == 1:
            return self._value[0]
        return self._value

    def add_subsection(
        self,
        section: Union[str, "Section"],
        item: Union[str, RecipeItem, List[str], List[RecipeItem]] = "",
    ):
        if isinstance(section, str):
            section = Section(section, item)
        else:
            section.add_items(item)
        self._value.append(section)

    def get_subsection(self, section: Union[str, "Section"]) -> "Section":
        if isinstance(section, str):
            section = Section(section)
        for sec in self._value:
            if isinstance(sec, Section) and sec.section_name == section.section_name:
                return sec
        raise ValueError(f"Subsection {section.section_name} does not exist.")

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

    def as_dict(self) -> dict:
        result = dict()
        items = []
        for value in self._value:
            if isinstance(value, Section):
                result.update(value.as_dict())
            else:
                items.append(str(value))
        if items and result:
            result = (items, result)
        elif items and not result:
            result = items
        return {self._section_name: result}


class Package(Section):
    ALL_SUBSECTIONS_ALLOWED = ("name", "version")

    def __init__(self, name: str, version: str):
        super(Package, self).__init__(
            section_name=Package.__name__.lower(),
            subsections={"name": name, "version": version},
        )

    def get_name_as_jinja(self) -> str:
        return r"{{ name|lower }}"

    def get_version_as_jinja(self) -> str:
        return r"{{ version }}"


class Source(Section):
    ALL_SUBSECTIONS_ALLOWED = (
        "fn",
        "url",
        "md5",
        "sha1",
        "sha256",
        "path",
        "path_via_symlink",
        "git_url",
        "git_tag",
        "git_branch",
        "git_rev",
        "git_depth",
        "hg_url",
        "hg_tag",
        "svn_url",
        "svn_rev",
        "svn_ignore_externals",
        "folder",
        "no_hoist",
        "patches",
    )

    def __init__(self, url: str, **kwargs):
        super(Source, self).__init__(
            section_name=__name__.lower(), subsections=kwargs.update({"url": url})
        )


class Build(Section):
    ALL_SUBSECTIONS_ALLOWED = (
        "number",
        "string",
        "entry_points",
        "osx_is_app",
        "disable_pip",
        "features",
        "track_features",
        "preserve_egg_dir",
        "no_link",
        "binary_relocation",
        "script",
        "noarch",
        "noarch_python",
        "has_prefix_files",
        "binary_has_prefix_files",
        "ignore_prefix_files",
        "detect_binary_files_with_prefix",
        "skip_compile_pyc",
        "rpaths",
        "rpaths_patcher",
        "script_env",
        "always_include_files",
        "skip",
        "msvc_compiler",
        "pin_depends",
        "include_recipe",  # pin_depends is experimental still
        "preferred_env",
        "preferred_env_executable_paths",
        "run_exports",
        "ignore_run_exports",
        "requires_features",
        "provides_features",
        "force_use_keys",
        "force_ignore_keys",
        "merge_build_host",
    )

    def __init__(self, number=0, **kwargs):
        super(Build, self).__init__(
            section_name=__name__.lower(), subsections=kwargs.update({"number": number})
        )
