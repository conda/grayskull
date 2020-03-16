import re
from typing import Optional, Tuple


def parse_pkg_name_version(pkg_name: str) -> Tuple[str, Optional[str]]:
    pkg = re.match(r"([a-zA-Z0-9\-_\.]+)=+([a-zA-Z0-9\-_\.]+)", pkg_name)
    return pkg.groups() if pkg else (pkg_name, None)


def parse_pkg_path_version(pkg_path: str) -> Tuple[str, Optional[str]]:
    pkg = re.match(r"(.*)=+([a-zA-Z0-9\-_\.]+)\s*$", pkg_path, re.DOTALL)
    return pkg.groups() if pkg else (pkg_path, None)
