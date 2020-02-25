import os
import sys

import pytest
from pytest import fixture

from grayskull.license.discovery import (
    _get_api_github_url,
    get_license_type,
    get_short_license_id,
    match_license,
    search_license_api_github,
    search_license_folder,
    search_license_repo,
)


@fixture
def license_pytest_path(data_dir) -> str:
    return os.path.join(data_dir, "licenses", "pytest.txt")


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Failing to retrieve information on windows"
)
def test_match_license():
    assert match_license("MIT License").id == "MIT"
    assert match_license("Expat").id == "MIT"


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="Failing to retrieve information on windows"
)
def test_short_license_id():
    assert get_short_license_id("MIT License") == "MIT"
    assert get_short_license_id("Expat") == "MIT"
    assert get_short_license_id("GPL 2.0") == "GPL-2.0"
    assert get_short_license_id("2-Clause BSD License") == "BSD-2-Clause"
    assert get_short_license_id("3-Clause BSD License") == "BSD-3-Clause"


@fixture
def license_pytest_5_3_1(license_pytest_path) -> str:
    with open(license_pytest_path) as f:
        return f.read()


@pytest.mark.xfail(
    reason="It may fail because there's a limit of requests which can be made to github"
)
def test_search_license_api_github(license_pytest_5_3_1: str):
    license_api = search_license_api_github(
        "https://github.com/pytest-dev/pytest", "5.3.1"
    )
    assert license_api.name == "MIT"
    assert license_api.path.endswith("LICENSE")

    with open(license_api.path, "r") as f:
        assert f.read() == license_pytest_5_3_1


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


def test_search_license_repository(pkg_pytest):
    license_repo = search_license_repo("https://github.com/pytest-dev/pytest", "5.3.5")
    assert license_repo.path.endswith("LICENSE")
    assert license_repo.name == "MIT"


def test_predict_license_type(license_pytest_path):
    assert get_license_type(license_pytest_path) == "MIT"