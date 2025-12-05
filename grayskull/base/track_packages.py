import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from packaging.utils import canonicalize_name
from packaging.version import Version  # noqa
from ruamel.yaml import YAML

log = logging.getLogger(__name__)


@dataclass
class ConfigPkg:
    """Configuration for mapping a PyPI package to its conda-forge equivalent."""

    pypi_name: str
    import_name: str = ""
    conda_forge: str = ""
    delimiter_min: str = ""
    delimiter_max: str = ""
    avoid_selector: bool = False

    def __post_init__(self):
        if not self.import_name:
            self.import_name = self.pypi_name
        if not self.conda_forge:
            self.conda_forge = self.pypi_name


def track_package(raw_pypi_name: str, config_file: Path | str) -> ConfigPkg:
    """Look up a PyPI package name in the config and return its mapping info."""
    pypi_to_conda_map = _get_track_info_from_file(config_file)
    normalized_pypi_name = canonicalize_name(raw_pypi_name)
    return ConfigPkg(raw_pypi_name, **(pypi_to_conda_map.get(normalized_pypi_name, {})))


def solve_list_pkg_name(pypi_reqs: list[str], config_file: Path | str) -> list[str]:
    """Convert a list of PyPI requirements to conda-forge package names."""
    re_norm = re.compile(r",\s+")
    return [
        re_norm.sub(",", solve_pkg_name(pypi_req, config_file))
        for pypi_req in pypi_reqs
    ]


def solve_pkg_name(pypi_req: str, config_file: Path | str) -> str:
    """Convert a single PyPI requirement (name + version spec) to conda-forge format."""
    parts = pypi_req.strip().split()
    raw_pypi_name = parts[0]
    version_spec = " ".join(parts[1:])
    pkg_config = track_package(raw_pypi_name, config_file)
    resolved_version_spec = solve_version_delimiter(version_spec, pkg_config)
    return " ".join([pkg_config.conda_forge, resolved_version_spec]).strip()


@lru_cache(maxsize=5)
def _get_track_info_from_file(config_file: Path | str) -> dict:
    yaml = YAML()
    with open(config_file, encoding="utf_8") as yaml_file:
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


def _version_solver(list_exp: list, pkg_cfg: ConfigPkg) -> list:
    result = []
    for op, version in list_exp:
        if op in ["==", ""]:
            return list_exp
        elif ">" in op and pkg_cfg.delimiter_min:
            if eval(f'Version("{pkg_cfg.delimiter_min}"){op}Version("{version}")'):
                result.append(f">={pkg_cfg.delimiter_min}")
            else:
                result.append(f"{op}{version}")
        elif "<" in op and pkg_cfg.delimiter_max:
            if eval(f'Version("{version}"){op}Version("{pkg_cfg.delimiter_max}")'):
                result.append(f"{op}{version}")
            else:
                result.append(f"<{pkg_cfg.delimiter_max}")
        else:
            result.append(f"{op}{version}")
    return result


def parse_delimiter(delimiter_exp: str) -> list[tuple[str, str] | None]:
    re_search = re.compile(r"([!=><]+)\s*([a-z0-9\-\.\_]+)", re.IGNORECASE)
    result = re_search.findall(delimiter_exp)
    if not result:
        return []
    return result
