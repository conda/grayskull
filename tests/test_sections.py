from ruamel.yaml.comments import CommentedMap

from grayskull.base.section import Section


def test_section_yaml_obj():
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


def test_section_children():
    commented_map = CommentedMap(
        {
            "section1": CommentedMap(
                {"subsection1": CommentedMap({"subsection2": "item"})}
            )
        }
    )
    sec = Section("section1", parent_yaml=commented_map)
    assert sec.section_name == "section1"
    assert sec.values[0].section_name == "subsection1"


def test_section_load():
    commented_map = CommentedMap({"section1": {"subsection1": {"subsection2": "item"}}})
    sec = Section("section1", commented_map)
    assert sec.section_name == "section1"
    assert sec["subsection1"].section_name == "subsection1"
    assert sec["subsection1"]["subsection2"].section_name == "subsection2"
    assert sec["subsection1"]["subsection2"][0].value == "item"
