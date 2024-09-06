"""Unit tests for parsing Poetry versions."""

import pytest

from grayskull.strategy.parse_poetry_version import (
    InvalidVersion,
    encode_poetry_version,
    get_caret_ceiling,
    get_tilde_ceiling,
    parse_version,
)


@pytest.mark.parametrize(
    "version, major, minor, patch",
    [
        ("0", 0, None, None),
        ("1", 1, None, None),
        ("1.2", 1, 2, None),
        ("1.2.3", 1, 2, 3),
    ],
)
def test_parse_version_success(version, major, minor, patch):
    assert parse_version(version) == {"major": major, "minor": minor, "patch": patch}


@pytest.mark.parametrize(
    "invalid_version", ["asdf", "", ".", "x.2.3", "1.x.3", "1.2.x"]
)
def test_parse_version_failure(invalid_version):
    with pytest.raises(InvalidVersion):
        parse_version(invalid_version)


@pytest.mark.parametrize(
    "version, ceiling_version",
    [
        ("0", "1.0.0"),
        ("0.0", "0.1.0"),
        ("0.0.3", "0.0.4"),
        ("0.2.3", "0.3.0"),
        ("1", "2.0.0"),
        ("1.2", "2.0.0"),
        ("1.2.3", "2.0.0"),
    ],
)
def test_get_caret_ceiling(version, ceiling_version):
    # examples from Poetry docs
    assert get_caret_ceiling(version) == ceiling_version


@pytest.mark.parametrize(
    "version, ceiling_version",
    [("1", "2.0.0"), ("1.2", "1.3.0"), ("1.2.3", "1.3.0")],
)
def test_get_tilde_ceiling(version, ceiling_version):
    # examples from Poetry docs
    assert get_tilde_ceiling(version) == ceiling_version


@pytest.mark.parametrize(
    "version, encoded_version",
    [
        # should be unchanged
        ("1.*", "1.*"),
        (">=1,<2", ">=1,<2"),
        ("==1.2.3", "==1.2.3"),
        ("!=1.2.3", "!=1.2.3"),
        # strip spaces
        (">= 1, < 2", ">=1,<2"),
        # handle exact version specifiers correctly
        ("1.2.3", "1.2.3"),
        ("==1.2.3", "==1.2.3"),
        # handle caret operator correctly
        # examples from Poetry docs
        ("^0", ">=0.0.0,<1.0.0"),
        ("^0.0", ">=0.0.0,<0.1.0"),
        ("^0.0.3", ">=0.0.3,<0.0.4"),
        ("^0.2.3", ">=0.2.3,<0.3.0"),
        ("^1", ">=1.0.0,<2.0.0"),
        ("^1.2", ">=1.2.0,<2.0.0"),
        ("^1.2.3", ">=1.2.3,<2.0.0"),
        # handle tilde operator correctly
        # examples from Poetry docs
        ("~1", ">=1.0.0,<2.0.0"),
        ("~1.2", ">=1.2.0,<1.3.0"),
        ("~1.2.3", ">=1.2.3,<1.3.0"),
    ],
)
def test_encode_poetry_version(version, encoded_version):
    assert encode_poetry_version(version) == encoded_version
