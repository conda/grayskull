from grayskull.license.discovery import get_short_license_id, match_license


def test_match_license():
    assert match_license("MIT License").id == "MIT"
    assert match_license("Expat").id == "MIT"


def test_short_license_id():
    assert get_short_license_id("MIT License") == "MIT"
    assert get_short_license_id("Expat") == "MIT"
    assert get_short_license_id("GPL 2.0") == "GPL-2.0"
    assert get_short_license_id("2-Clause BSD License") == "BSD-2-Clause"
    assert get_short_license_id("3-Clause BSD License") == "BSD-3-Clause"
