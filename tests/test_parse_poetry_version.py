"""Unit tests for parsing Poetry versions."""

import pytest

from grayskull.strategy.parse_poetry_version import (
    InvalidVersion,
    combine_conda_selectors,
    encode_poetry_python_version_to_selector_item,
    parse_version,
)


@pytest.mark.parametrize(
    "invalid_version", ["asdf", "", ".", "x.2.3", "1.x.3", "1.2.x"]
)
def test_parse_version_failure(invalid_version):
    with pytest.raises(InvalidVersion):
        parse_version(invalid_version)


@pytest.mark.parametrize(
    "poetry_python_specifier, exp_selector_item",
    [
        ("", ""),
        (">=3.5", "py>=35"),
        (">=3.6", "py>=36"),
        (">3.7", "py>37"),
        ("<=3.7", "py<=37"),
        ("<3.7", "py<37"),
        ("3.10", "py==310"),
        ("=3.10", "py==310"),
        ("==3.10", "py==310"),
        ("==3", "py==3"),
        (">3.12", "py>312"),
        ("!=3.7", "py!=37"),
        # multiple specifiers
        (">3.7,<3.12", "py>37 or py<312"),
        # poetry specifiers
        ("^3.10", "py>=310 or py<4"),
        ("~3.10", "py>=310 or py<311"),
        # PEP 440 not common specifiers
        # ("~=3.7", "<37", "<37"),
        # ("3.*", "<37", "<37"),
        # ("!=3.*", "<37", "<37"),
    ],
)
def test_encode_poetry_python_version_to_selector_item(
    poetry_python_specifier, exp_selector_item
):
    assert exp_selector_item == encode_poetry_python_version_to_selector_item(
        poetry_python_specifier
    )


@pytest.mark.parametrize(
    "python_selector, platform_selector, exp_conda_selector_content",
    [
        ("py>=38 or py<312", "osx", "(py>=38 or py<312) and osx"),
        ("py>=38 or py<312", "", "py>=38 or py<312"),
        ("", "osx", "osx"),
        ("py>=38", "", "py>=38"),
        ("py<310", "win", "py<310 and win"),
    ],
)
def test_combine_conda_selectors(
    python_selector, platform_selector, exp_conda_selector_content
):
    conda_selector = combine_conda_selectors(python_selector, platform_selector)
    expected = (
        f"  # [{exp_conda_selector_content}]" if exp_conda_selector_content else ""
    )
    assert conda_selector == expected
