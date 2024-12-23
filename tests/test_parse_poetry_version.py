"""Unit tests for parsing Poetry versions."""

import pytest

from grayskull.strategy.parse_poetry_version import (
    InvalidVersion,
    combine_conda_selectors,
    encode_poetry_python_version_to_selector_item,
    parse_python_version_specifier_to_selector,
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
        ("3", "py==3"),
        (">3.12", "py>312"),
        ("!=3.7", "py!=37"),
        # multiple specifiers
        (">3.7,<3.12", "py>37 and py<312"),
        (">3.7,<3.12,!=3.9", "py>37 and py<312 and py!=39"),
        # version specifiers in "or" ("and" takes precedence)
        ("<3.7|>=3.10", "py<37 or py>=310"),
        ("<3.8|>=3.10,!=3.11", "py<38 or py>=310 and py!=311"),
        ("<3.8|>=3.10|=3.9", "py<38 or py>=310 or py==39"),
        # poetry specifiers
        ("^3.10", "py>=310 and py<4"),
        ("~3.10", "py>=310 and py<311"),
        # PEP 440 not common specifiers
        ("~=3.8", "py>=38 and py<4"),
        ("3.*", "py>=3 and py<4"),
        ("!=3.*", "py<3 or py>=4"),
    ],
)
def test_encode_poetry_python_version_to_selector_item(
    poetry_python_specifier, exp_selector_item
):
    assert exp_selector_item == encode_poetry_python_version_to_selector_item(
        poetry_python_specifier
    )


@pytest.mark.parametrize(
    "python_version, expected_conda_selector",
    [
        (">=3", "py>=3"),
        (">=3.8", "py>=38"),
        (">=3.8.0", "py>=38"),
        (">=3.8.0.1", "py>=38"),
        ("<4.0.0.0", "py<4"),
        ("<4.0.0", "py<4"),
        ("<4.0", "py<4"),
        ("3", "py==3"),
        ("3.12", "py==312"),
        ("3.12.1", "py==312"),
        ("3.12.1.1", "py==312"),
        ("=3", "py==3"),
        ("=3.8", "py==38"),
        ("=3.8.1", "py==38"),
        ("=3.8.1.1", "py==38"),
        ("===3", "py==3"),
        ("===3.8", "py==38"),
        ("===3.8.1", "py==38"),
        ("===3.8.1.1", "py==38"),
        ("!=3", "py!=3"),
        ("!=3.8", "py!=38"),
        ("!=3.8.1", "py!=38"),
        ("!=3.8.1.1", "py!=38"),
        ("~=3.8", "py>=38 and py<4"),
    ],
)
def test_parse_python_version_specifier_to_selector(
    python_version, expected_conda_selector
):
    conda_selector = parse_python_version_specifier_to_selector(python_version)
    assert conda_selector == expected_conda_selector


@pytest.mark.parametrize(
    "python_selector, platform_selector, expected_conda_selector",
    [
        ("", "", ""),
        ("py>=38 and py<312", "osx", "  # [py>=38 and py<312 and osx]"),
        ("py>=38 and py<312", "", "  # [py>=38 and py<312]"),
        ("", "osx", "  # [osx]"),
        ("py>=38", "", "  # [py>=38]"),
        ("py<310", "win", "  # [py<310 and win]"),
        (
            "py<38 or py>=310 and py!=311",
            "osx",
            "  # [(py<38 or py>=310 and py!=311) and osx]",
        ),
        ("py<38 or py>=310", "osx", "  # [(py<38 or py>=310) and osx]"),
    ],
)
def test_combine_conda_selectors(
    python_selector, platform_selector, expected_conda_selector
):
    conda_selector = combine_conda_selectors(python_selector, platform_selector)
    assert conda_selector == expected_conda_selector
