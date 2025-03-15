import re
from functools import lru_cache

import requests

from grayskull.cli import CLIConfig


@lru_cache(maxsize=35)
def is_pkg_available(pkg_name: str, channel: str = None) -> bool:
    """Verify if the package is available on Anaconda or custom package indexes.

    :param pkg_name: Package name
    :param channel: Anaconda channel or full URL (if None, will use channels from CLIConfig)
    :return: Return True if the package is present on any of the given channels or URLs
    """
    channels_to_check = [channel] if channel else CLIConfig().package_indexes

    for channel_to_check in channels_to_check:
        try:
            # Check if the channel is a full URL
            if re.match(r"^https?://", channel_to_check):
                url = f"{channel_to_check.rstrip('/')}/{pkg_name}/files"
            else:
                # Default to anaconda.org if not a full URL
                url = f"https://anaconda.org/{channel_to_check}/{pkg_name}/files"

            response = requests.get(
                url=url,
                allow_redirects=False,
            )
            if response.status_code == 200:
                return True
        except requests.exceptions.RequestException:
            continue
    return False


def normalize_pkg_name(pkg_name: str) -> str:
    if is_pkg_available(pkg_name):
        return pkg_name
    if is_pkg_available(pkg_name.replace("-", "_")):
        return pkg_name.replace("-", "_")
    elif is_pkg_available(pkg_name.replace("_", "-")):
        return pkg_name.replace("_", "-")
    return pkg_name
