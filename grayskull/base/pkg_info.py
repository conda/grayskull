import re
from functools import lru_cache
from typing import List, Optional, Tuple

import requests


@lru_cache(maxsize=35)
def is_pkg_available(pkg_name: str, channel: str = "conda-forge") -> bool:
    """Verify if the package is available on Anaconda for a specific channel.

    :param pkg_name: Package name
    :param channel: Anaconda channel
    :return: Return True if the package is present on the given channel
    """
    response = requests.get(
        url=f"https://anaconda.org/{channel}/{pkg_name}/files", allow_redirects=False
    )
    return response.status_code == 200


def normalize_pkg_name(pkg_name: str) -> str:
    if is_pkg_available(pkg_name):
        return pkg_name
    if is_pkg_available(pkg_name.replace("-", "_")):
        return pkg_name.replace("-", "_")
    elif is_pkg_available(pkg_name.replace("_", "-")):
        return pkg_name.replace("_", "-")
    return pkg_name


def check_pkgs_availability(
    list_pkgs: List[str], channel: Optional[str] = None
) -> List[Tuple[str, bool]]:
    """Check if the list is

    :param list_pkgs: List with packages name
    :return:
    """
    list_pkgs.sort()
    re_search = re.compile(r"^\s*[a-z0-9\.\-\_]+", re.IGNORECASE)

    result_list = []
    all_pkg = set()
    for pkg in list_pkgs:
        if not pkg:
            continue
        search_result = re_search.search(pkg)
        if not search_result:
            continue

        pkg_name = search_result.group()
        if pkg_name in all_pkg:
            continue

        all_pkg.add(pkg_name)
        if channel:
            result_list.append((pkg, is_pkg_available(pkg_name, channel)))
        else:
            result_list.append((pkg, is_pkg_available(pkg_name)))
    return result_list
