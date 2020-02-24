from grayskull.license.discovery import get_short_license_id, match_license


def test_match_license():
    assert match_license("MIT License").id == "MIT"
    assert match_license("Expat").id == "MIT"


def test_short_license_id():
    assert get_short_license_id("MIT License") == "MIT"
    assert get_short_license_id("Expat") == "MIT"
