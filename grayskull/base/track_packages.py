import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from pkg_resources import parse_version  # noqa
from ruamel.yaml import YAML

log = logging.getLogger(__name__)


@dataclass
class ConfigPkg:
    name: str
    import_name: str = ""
    conda_forge: str = ""
    delimiter_min: str = ""
    delimiter_max: str = ""

    def __post_init__(self):
        if not self.import_name:
            self.import_name = self.name
        if not self.conda_forge:
            self.conda_forge = self.name


def track_package(pkg_name: str, config_file: Union[Path, str]) -> ConfigPkg:
    all_pkg = _get_track_info_from_file(config_file)
    return ConfigPkg(pkg_name, **(all_pkg.get(pkg_name, {})))


def solve_list_pkg_name(
    list_pkg: List[str], config_file: Union[Path, str]
) -> List[str]:
    re_norm = re.compile(r",\s+")
    return [re_norm.sub(",", solve_pkg_name(pkg, config_file)) for pkg in list_pkg]


def solve_pkg_name(pkg: str, config_file: Union[Path, str]) -> str:
    pkg_name_sep = pkg.strip().split()
    config_pkg = track_package(pkg_name_sep[0], config_file)
    all_delimiter = " ".join(pkg_name_sep[1:])
    return (
        " ".join(
            [config_pkg.conda_forge, solve_version_delimiter(all_delimiter, config_pkg)]
        )
    ).strip()


@lru_cache(maxsize=5)
def _get_track_info_from_file(config_file: Union[Path, str]) -> Dict:
    yaml = YAML()
    with open(config_file, "r", encoding="utf_8") as yaml_file:
        return yaml.load(yaml_file)


def solve_version_delimiter(delimiter_exp: str, pkg_cfg: ConfigPkg) -> str:
    if not pkg_cfg.delimiter_max and not pkg_cfg.delimiter_min:
        return delimiter_exp
    list_exp = parse_delimiter(delimiter_exp)
    if not list_exp:
        return delimiter_exp
    try:
        result = _version_solver(list_exp, pkg_cfg)
    except Exception as err_msg:
        log.debug(f"Version solver exception: {err_msg}")
        return delimiter_exp
    else:
        return ",".join(result)


def _version_solver(list_exp: List, pkg_cfg: ConfigPkg) -> List:
    result = []
    for op, version in list_exp:
        if op in ["==", ""]:
            return list_exp
        elif ">" in op and pkg_cfg.delimiter_min:
            if eval(
                f'parse_version("{pkg_cfg.delimiter_min}")'
                f'{op}parse_version("{version}")'
            ):
                result.append(f">={pkg_cfg.delimiter_min}")
            else:
                result.append(f"{op}{version}")
        elif "<" in op and pkg_cfg.delimiter_max:
            if eval(
                f'parse_version("{version}")'
                f'{op}parse_version("{pkg_cfg.delimiter_max}")'
            ):
                result.append(f"{op}{version}")
            else:
                result.append(f"<{pkg_cfg.delimiter_max}")
        else:
            result.append(f"{op}{version}")
    return result


def parse_delimiter(delimiter_exp: str) -> List[Optional[Tuple[str, str]]]:
    re_search = re.compile(r"([!=><]+)\s*([a-z0-9\-\.\_]+)", re.IGNORECASE)
    result = re_search.findall(delimiter_exp)
    if not result:
        return []
    return result
