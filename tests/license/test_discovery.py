import os
from typing import List
from unittest.mock import patch

import pytest
import requests
from pytest import fixture

from grayskull.license.discovery import (
    _get_all_license_choice,
    _get_all_names_from_api,
    _get_api_github_url,
    _get_license,
    get_all_licenses_from_spdx,
    get_license_type,
    get_opensource_license_data,
    get_other_names_from_opensource,
    get_short_license_id,
    match_license,
    search_license_api_github,
    search_license_folder,
    search_license_repo,
)


@fixture
def license_pytest_path(data_dir) -> str:
    return os.path.join(data_dir, "licenses", "pytest.txt")


@fixture
def spdx_org_license_mit() -> List:
    return [
        {
            "reference": "./MIT.html",
            "isDeprecatedLicenseId": False,
            "isFsfLibre": True,
            "detailsUrl": "http://spdx.org/licenses/MIT.json",
            "referenceNumber": "256",
            "name": "MIT License",
            "licenseId": "MIT",
            "seeAlso": ["https://opensource.org/licenses/MIT"],
            "isOsiApproved": True,
        }
    ]


def test_match_license():
    assert match_license("MIT License")["licenseId"] == "MIT"
    assert match_license("Expat")["licenseId"] == "MIT"


def test_get_all_licenses_from_spdx():
    assert len(get_all_licenses_from_spdx()) > 300


def test_get_opensource_license_data():
    assert len(get_opensource_license_data()) >= 50


def test_short_license_id():
    assert get_short_license_id("MIT License") == "MIT"
    assert get_short_license_id("Expat") == "MIT"
    assert get_short_license_id("GPL 2.0") == "GPL-2.0-or-later"
    assert get_short_license_id("2-Clause BSD License") == "BSD-2-Clause"
    assert get_short_license_id("3-Clause BSD License") == "BSD-3-Clause"


def test_get_other_names_from_opensource():
    assert sorted(get_other_names_from_opensource("MIT")) == sorted(["MIT", "Expat"])


def test_get_license(spdx_org_license_mit):
    assert _get_license("MIT", spdx_org_license_mit) == spdx_org_license_mit[0]


def test_get_all_names_from_api(spdx_org_license_mit):
    assert sorted(_get_all_names_from_api(spdx_org_license_mit[0])) == sorted(
        ["Expat", "MIT", "MIT License"]
    )


def test_get_all_license_choice(spdx_org_license_mit):
    assert sorted(_get_all_license_choice(spdx_org_license_mit)) == sorted(
        ["Expat", "MIT", "MIT License"]
    )


@fixture
def license_pytest_5_3_1(license_pytest_path) -> str:
    with open(license_pytest_path) as f:
        return f.read()


@pytest.mark.github
def test_search_license_api_github(license_pytest_5_3_1: str):
    license_api = search_license_api_github(
        "https://github.com/pytest-dev/pytest", "5.3.1"
    )
    assert license_api.name == "MIT"
    assert license_api.path.endswith("LICENSE")

    with open(license_api.path, "r") as f:
        assert f.read() == license_pytest_5_3_1


@pytest.mark.github
def test_get_api_github_url():
    assert (
        _get_api_github_url("https://github.com/pytest-dev/pytest", "5.3.1")
        == "https://api.github.com/repos/pytest-dev/pytest/license?ref=5.3.1"
    )
    assert (
        _get_api_github_url("https://github.com/pytest-dev/pytest")
        == "https://api.github.com/repos/pytest-dev/pytest/license"
    )


def test_search_license_folder(pkg_pytest):
    license_folder = search_license_folder(os.path.dirname(pkg_pytest))[0]
    assert license_folder.path == os.path.join(
        os.path.dirname(pkg_pytest), "pytest-5.3.5", "LICENSE"
    )
    assert license_folder.name == "MIT"


def test_search_license_folder_hidden_folder(tmp_path, license_pytest_5_3_1):
    d = tmp_path / "mypackage"
    d.mkdir()
    license_path = d / "LICENSE"
    license_path.write_text(license_pytest_5_3_1)
    # Following licences under hidden directory should be ignored
    egg_info = d / ".eggs" / "setuptools_scm-7.0.5-py3.10.egg" / "EGG-INFO"
    egg_info.mkdir(parents=True)
    for lic in (d / ".eggs" / "LICENSE", egg_info / "LICENSE"):
        lic.write_text(license_pytest_5_3_1)
    all_licenses = search_license_folder(tmp_path)
    assert len(all_licenses) == 1
    assert all_licenses[0].path == str(license_path)


def test_search_licence_exclude_folders(tmp_path, license_pytest_5_3_1):
    folder = tmp_path / "location-exclude-folder"
    folder.mkdir()
    folder_exclude = folder / "folder_exclude"
    folder_exclude.mkdir()
    (folder_exclude / "LICENSE").write_text("LICENCE TO EXCLUDE")
    folder_search = folder / "folder_search"
    folder_search.mkdir()
    (folder_search / "LICENSE").write_text("LICENCE TO BE FOUND")
    all_licences = search_license_folder(str(folder))
    assert len(all_licences) == 2
    all_licences = search_license_folder(
        str(folder), folders_exclude_search=("folder_exclude",)
    )
    assert len(all_licences) == 1
    assert all_licences[0].path == str(folder_search / "LICENSE")


@pytest.mark.xfail(
    reason="This test may fail because github has limitation regarding the"
    " number of requisitions we can do to their api."
)
def test_search_license_repository(pkg_pytest):
    license_repo = search_license_repo("https://github.com/pytest-dev/pytest", "5.3.5")
    assert license_repo.path.endswith("LICENSE")
    assert license_repo.name == "MIT"


def test_predict_license_type(license_pytest_path):
    assert get_license_type(license_pytest_path) == "MIT"


def test_fallback_cache_licence():
    with patch("requests.get", side_effect=requests.exceptions.RequestException):
        assert get_opensource_license_data()
