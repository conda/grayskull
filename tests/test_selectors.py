from grayskull.base.selectors import Selectors


def test_selectors():
    sel = Selectors(" # [win and (py<36)]")
    assert sel[0].name == "win"
    assert sel[1].name == "and"
    assert sel[2].name == "("
    assert sel[3].name == "py"
    assert sel[3].operator == "<"
    assert sel[3].value == "36"
    assert sel[4].name == ")"


def test_parse_bracket():
    selectors = Selectors._parse_bracket("(py<36)")
    assert selectors[0].name == "("
    assert selectors[1].name == "py"
    assert selectors[1].operator == "<"
    assert selectors[1].value == "36"
    assert selectors[2].name == ")"
