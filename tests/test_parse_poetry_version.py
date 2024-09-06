"""Unit tests for parsing Poetry versions."""

import pytest

from grayskull.strategy.parse_poetry_version import InvalidVersion, parse_version


@pytest.mark.parametrize(
    "invalid_version", ["asdf", "", ".", "x.2.3", "1.x.3", "1.2.x"]
)
def test_parse_version_failure(invalid_version):
    with pytest.raises(InvalidVersion):
        parse_version(invalid_version)
