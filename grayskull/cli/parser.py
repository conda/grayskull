import re
from typing import Optional, Tuple


def parse_pkg_name_version(pkg_name: str) -> Tuple[str, Optional[str]]:
    if pkg_name.startswith(("http://", "https://")):
        origin, pkg_name = pkg_name.rsplit("/", 1)
        origin += "/"
    pkg = re.match(r"([a-zA-Z0-9\-_\.]+)=+([a-zA-Z0-9\-_\.]+)", pkg_name)
    if pkg:
        pkg_name = origin + pkg.group(1)
        version = pkg.group(2)
        return pkg_name, version
    return origin + pkg_name, None
