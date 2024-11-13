import re
from pathlib import Path

from grayskull.utils import origin_is_github, origin_is_local_sdist


def parse_pkg_name_version(
    pkg_name: str,
) -> tuple[str, str, str | None]:
    origin = ""
    if origin_is_local_sdist(pkg_name):
        # Try to get package name and version from sdist archive
        # If the version is normalized, there should be no dash in it
        # Will get them from PKG-INFO later
        filename = Path(pkg_name).stem
        if filename.endswith(".tar"):
            filename = filename[:-4]
        name, _, version = filename.rpartition("-")
        if name == "":
            name = filename
            version = ""
        return "", name, version
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
