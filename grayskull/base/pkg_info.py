from functools import lru_cache

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
