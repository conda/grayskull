import os
from typing import List

import pytest
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
    license_folder = search_license_folder(os.path.dirname(pkg_pytest))
    assert license_folder.path == os.path.join(
        os.path.dirname(pkg_pytest), "pytest-5.3.5", "LICENSE"
    )
    assert license_folder.name == "MIT"


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
