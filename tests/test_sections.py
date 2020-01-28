from grayskull.base.section import Section


def test_section():
    sec = Section("run", ["pytest", "pkg2"])
    assert str(sec) == "run(pytest, pkg2)"
    assert sec.as_dict() == {"run": ["pytest", "pkg2"]}
    assert sec == ["pytest", "pkg2"]

    sec = Section("requirements")
    sec.add_subsection("run", ["pytest <5.2.0", "pkg2"])
    sec.add_subsection("host", ["pkg2"])
    assert str(sec) == "requirements(run(pytest <5.2.0, pkg2), host(pkg2))"
    assert sec.run == ["pytest <5.2.0", "pkg2"]
    assert sec.host == ["pkg2"]

    assert sec.as_dict() == {
        "requirements": {"run": ["pytest <5.2.0", "pkg2"], "host": ["pkg2"]}
    }


def test_add_subsection_items():
    sec = Section("requirements")
    sec.add_subsection("run")
    assert sec.get_subsection("run").section_name == "run"

    run_sec = sec.get_subsection("run")
    run_sec.add_items(["pytest", "python <3.8", "pkg3 <1.0  # [win]"])
    assert run_sec.value[0].section_name == "pytest"
    assert run_sec.value[1].section_name == "python"
    assert str(run_sec.value[1].delimiter) == "<3.8"
    assert str(run_sec.value[1]) == "python <3.8"

    assert run_sec.value[2].section_name == "pkg3"
    assert str(run_sec.value[2].delimiter) == "<1.0"
    assert str(run_sec.value[2].selector) == "win"
    assert str(run_sec.value[2]) == "pkg3 <1.0  # [win]"
