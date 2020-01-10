import pytest

from grayskull.base.delimiters import Delimiters


def test_delimiters():
    delimiter = Delimiters(">=3.6")
    assert str(delimiter) == ">=3.6"
    assert str(delimiter + "<3.9") == ">=3.6,<3.9"
    assert str(delimiter + Delimiters("<3.9")) == ">=3.6,<3.9"

    delimiter.add("!=3.8.0")
    delimiter.add(Delimiters("!=3.8.1"))
    assert str(delimiter) == ">=3.6,!=3.8.0,!=3.8.1"

    delimiter.remove("!=3.8.0")
    assert str(delimiter) == ">=3.6,!=3.8.1"
    assert str(delimiter - "!=3.8.1") == ">=3.6"
    assert str(delimiter - Delimiters("!=3.8.1")) == ">=3.6"
    delimiter.remove(Delimiters("!=3.8.1"))
    assert str(delimiter) == ">=3.6"


@pytest.mark.parametrize(
    "raw_str, exp_result",
    [
        ("pluggy (<1.0,>=0.12)", "<1.0,>=0.12"),
        ("more-itertools (>=4.0.0)", ">=4.0.0"),
        ("attrs (>= 17.4.0)", ">=17.4.0"),
        ("py ( >=1.5.0)", ">=1.5.0"),
        ("hypothesis (>=3.56 )", ">=3.56"),
        ("atomicwrites >=1.0  # [win]", ">=1.0"),
        ("attrs >=17.4.0", ">=17.4.0"),
    ],
)
def test_delimiters_parse(raw_str, exp_result):
    assert str(Delimiters(raw_str)) == exp_result
