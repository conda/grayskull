import os
from functools import lru_cache


@lru_cache(maxsize=2)
def get_all_licenses() -> list:
    data_folder = os.path.dirname(__file__)
    all_licenses = []
    for license_file in os.listdir(data_folder):
        full_path = os.path.join(data_folder, license_file)
        if not os.path.isfile(full_path) or license_file.endswith(".py"):
            continue
        with open(full_path) as f:
            all_licenses.append((license_file, f.read()))
    return all_licenses
