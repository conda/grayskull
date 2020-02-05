from ruamel.yaml.comments import CommentedMap

from grayskull.base.section import Section


def test_section():
    commented_map = CommentedMap({"section1": {"subsection1": {"subsection2": "item"}}})
    sec = Section("MAIN_SECTION", parent_yaml=commented_map)
    assert sec.yaml_obj == commented_map.update({"MAIN_SECTION": None})


def test_add_subsection():
    sec = Section("MAIN_SEC")
    sec.add_subsection("SUBSECTION")
    assert "SUBSECTION" in sec
    assert sec.section_name == "MAIN_SEC"


def test_add_item():
    sec = Section("MAIN_SEC")
    sec.add_item("pkg1")
    item2 = sec.add_item("pkg2  # [win]")
    item3 = sec.add_item("pkg3")
    assert "pkg1" in sec
    assert "pkg2" in sec
    assert "pkg3" in sec

    assert item2.value == "pkg2"
    assert item2.selector == "win"
    assert str(item2) == "pkg2  # [win]"
    assert item3.value == "pkg3"
    assert item3.selector == ""
    assert str(item3) == "pkg3"
