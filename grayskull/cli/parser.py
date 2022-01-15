import re
from typing import Optional, Tuple

from grayskull.utils import origin_is_github


def parse_pkg_name_version(pkg_name: str) -> Tuple[str, str, Optional[str]]:
    origin = ""
    if origin_is_github(pkg_name):
        origin, pkg_name = pkg_name.rsplit("/", 1)
        origin += "/"
        if pkg_name.endswith(".git"):
            pkg_name = pkg_name[:-4]
    pkg = re.match(r"([a-zA-Z0-9\-_\.]+)=+([a-zA-Z0-9\-_\.]+)", pkg_name)
    if pkg:
        pkg_name = origin + pkg.group(1)
        version = pkg.group(2)
        return "", pkg_name, version
    return origin, pkg_name, None
