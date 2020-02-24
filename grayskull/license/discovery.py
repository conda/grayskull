import re
from typing import List

from fuzzywuzzy import process
from opensource import OpenSourceAPI
from opensource.licenses.wrapper import License


def match_license(name: str) -> License:
    os_api = OpenSourceAPI()
    name = name.strip()
    name = re.sub(r"\s*License\s*", "", name, re.IGNORECASE)
    try:
        return os_api.get(name)
    except ValueError:
        pass
    best_match = process.extractOne(name, _get_all_license_choice(os_api))
    return _get_license(best_match[0], os_api)


def get_short_license_id(name: str) -> str:
    return match_license(name).id


def _get_license(name: str, os_api: OpenSourceAPI) -> License:
    try:
        return os_api.get(name)
    except ValueError:
        pass

    for api_license in os_api.all():
        if name in _get_all_names_from_api(api_license):
            return api_license


def _get_all_names_from_api(api_license: License) -> list:
    result = []
    if api_license.name:
        result.append(api_license.name)
    if api_license.id:
        result.append(api_license.id)
    return result + [l["name"] for l in api_license.other_names]


def _get_all_license_choice(os_api: OpenSourceAPI) -> List:
    all_choices = []
    for api_license in os_api.all():
        all_choices += _get_all_license_choice(api_license)
    return all_choices
