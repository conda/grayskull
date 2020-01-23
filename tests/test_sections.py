from grayskull.base.section import Section


def test_section():
    sec = Section("run", "pytest")
    assert str(sec) == "Section(name=run)"
