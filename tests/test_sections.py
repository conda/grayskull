from grayskull.base.section import Section


def test_section():
    sec = Section("run", "pytest")
    assert str(sec) == "Section(name=run)"


def test_add_subsection_items():
    sec = Section("requirements")
    sec.add_subsection("run")
    assert sec.get_subsection("run").name == "run"

    run_sec = sec.get_subsection("run")
    run_sec.add_items(["pytest", "python <3.8", "pkg3 <1.0  # [win]"])
    assert run_sec.get_values()[0].name == "pytest"
    assert run_sec.get_values()[1].name == "python"
    assert str(run_sec.get_values()[1].delimiter) == "<3.8"
    assert str(run_sec.get_values()[1]) == "python <3.8"
    assert run_sec.get_values()[2].name == "pkg3"
    assert str(run_sec.get_values()[2].delimiter) == "<1.0"
    assert str(run_sec.get_values()[2].selector) == "win"
    assert str(run_sec.get_values()[2]) == "pkg3 <1.0  # [win]"
