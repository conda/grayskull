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
    sec.add_item("pkg2  # [win]")
    sec.add_item("pkg3")
    assert "pkg1" in sec
    assert "pkg2" in sec
    assert "pkg3" in sec


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


def test_repr():
    commented_map = CommentedMap({"section1": {"subsection1": {"subsection2": "item"}}})
    sec = Section("section1", commented_map)
    assert repr(sec) == "Section(section_name=section1, subsection=['subsection1'])"


def test_str():
    commented_map = CommentedMap()
    sec = Section("section1", commented_map)
    assert str(sec) == "section1"


def test_reduce_section():
    commented_map = CommentedMap({})
    sec = Section("section", commented_map)
    sec.add_items(["item", None])
    sec.values[0].selector = "# [win]"
    assert sec.values == ["item", None]
    assert sec._get_parent()[sec.section_name] == ["item", None]

    sec.reduce_section()
    assert sec._get_parent()[sec.section_name] == "item"
    assert sec.values == ["item"]


def test_hash():
    commented_map = CommentedMap()
    sec = Section("section1", commented_map)
    assert hash(sec) == hash("section1-[]")
    sec.add_item("item")
    assert hash(sec) == hash("section1-['item']")
