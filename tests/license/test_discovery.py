import os
from typing import List
from unittest.mock import patch

import pytest
from pytest import fixture

from grayskull.license.discovery import (
    ShortLicense,
    _get_all_license_choice,
    _get_all_names_from_api,
    _get_api_github_url,
    _get_git_cmd,
    _get_license,
    get_all_licenses_from_opensource,
    get_license_type,
    get_short_license_id,
    match_license,
    search_license_file,
    search_license_folder,
    search_license_repo,
)


@fixture
def license_pytest_path(data_dir) -> str:
    return os.path.join(data_dir, "licenses", "pytest.txt")


@fixture
def opensource_license_mit() -> List:
    return [
        {
            "id": "MIT",
            "identifiers": [
                {"identifier": "MIT", "scheme": "DEP5"},
                {"identifier": "Expat", "scheme": "DEP5"},
                {"identifier": "MIT", "scheme": "SPDX"},
                {
                    "identifier": "License :: OSI Approved :: MIT License",
                    "scheme": "Trove",
                },
            ],
            "links": [
                {
                    "note": "tl;dr legal",
                    "url": "https://tldrlegal.com/license/mit-license",
                },
                {
                    "note": "Wikipedia page",
                    "url": "https://en.wikipedia.org/wiki/MIT_License",
                },
                {"note": "OSI Page", "url": "https://opensource.org/licenses/mit"},
            ],
            "name": "MIT/Expat License",
            "other_names": [
                {
                    "name": "MIT",
                    "note": "Because MIT has used many licenses for software, "
                    "the Free Software Foundation considers MIT License"
                    " ambiguous. The MIT License published on the OSI"
                    " site is the same as the Expat License.",
                },
                {
                    "name": "Expat",
                    "note": "Because MIT has used many licenses for software,"
                    " the Free Software Foundation considers MIT License"
                    " ambiguous. The MIT License published on the OSI site"
                    " is the same as the Expat License.",
                },
            ],
            "superseded_by": None,
            "keywords": ["osi-approved", "popular", "permissive"],
            "text": [
                {
                    "media_type": "text/html",
                    "title": "HTML",
                    "url": "https://opensource.org/licenses/mit",
                }
            ],
        }
    ]


def test_short_license():
    short_license = ShortLicense(name="name", path="path", is_packaged=True)
    assert short_license.is_packaged
    assert short_license.name == "name"
    assert short_license.path == "path"


def test_match_license():
    assert match_license("MIT License")["id"] == "MIT"
    assert match_license("Expat")["id"] == "MIT"


def test_get_all_licenses_from_opensource():
    assert len(get_all_licenses_from_opensource()) >= 88
    assert get_all_licenses_from_opensource()[0]["id"]


def test_short_license_id():
    assert get_short_license_id("MIT License") == "MIT"
    assert get_short_license_id("Expat") == "MIT"
    assert get_short_license_id("GPL 2.0") == "GPL-2.0"
    assert get_short_license_id("2-Clause BSD License") == "BSD-2-Clause"
    assert get_short_license_id("3-Clause BSD License") == "BSD-3-Clause"


def test_search_license_file(data_dir, tmpdir, monkeypatch):
    li_folder = os.path.join(data_dir, "licenses")
    short_license = search_license_file(
        folder_path=li_folder, license_name_metadata="GPL 2.0"
    )
    assert short_license == ShortLicense("GPL-2.0", "LICENSE", True)

    short_license = search_license_file(
        folder_path=str(tmpdir.mkdir("foo")), license_name_metadata="GPL 2.0"
    )
    assert short_license == ShortLicense("GPL-2.0", None, False)

    li_folder = tmpdir.mkdir("foobar")
    short_license = search_license_file(
        folder_path=str(li_folder),
        git_url="https://github.com/marcelotrevisani/grayskull",
    )
    assert short_license.name == "MIT"
    assert not short_license.is_packaged
    assert short_license.path.endswith("LICENSE")


@patch("grayskull.license.discovery.search_license_api_github")
def test_search_license_file_repo(mock_api, tmpdir):
    mock_api.return_value = None
    li_folder = tmpdir.mkdir("foobar")
    short_license = search_license_file(
        folder_path=str(li_folder),
        git_url="https://github.com/marcelotrevisani/grayskull",
    )
    assert short_license.name == "MIT"
    assert not short_license.is_packaged
    assert short_license.path.endswith("LICENSE")


@patch("grayskull.license.discovery.search_license_api_github")
@patch("grayskull.license.discovery.search_license_repo")
def test_search_license_file_default(mock_api, mock_repo, tmpdir):
    mock_api.return_value = None
    mock_repo.return_value = None
    li_folder = tmpdir.mkdir("foobar")
    short_license = search_license_file(
        folder_path=str(li_folder),
        git_url="https://github.com/marcelotrevisani/grayskull",
    )
    assert short_license.name is None
    assert not short_license.is_packaged
    assert short_license.path is None


def test_get_license(opensource_license_mit):
    assert _get_license("MIT", opensource_license_mit) == opensource_license_mit[0]


def test_get_all_names_from_api(opensource_license_mit):
    assert sorted(_get_all_names_from_api(opensource_license_mit[0])) == sorted(
        ["Expat", "MIT", "MIT/Expat License"]
    )


def test_get_all_license_choice(opensource_license_mit):
    assert sorted(_get_all_license_choice(opensource_license_mit)) == sorted(
        ["Expat", "MIT", "MIT/Expat License"]
    )


@fixture
def license_pytest_5_3_1(license_pytest_path) -> str:
    with open(license_pytest_path) as f:
        return f.read()


@pytest.mark.xfail(
    reason="This test may fail because github has limitation regarding the"
    " number of requisitions we can do to their api."
)
def test_search_license_api_github(license_pytest_5_3_1: str):
    from grayskull.license.discovery import search_license_api_github

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


def test_get_git_cmd():
    assert _get_git_cmd("GIT_URL", "version", "DEST") == [
        "git",
        "clone",
        "-b",
        "version",
        "GIT_URL",
        "DEST",
    ]
