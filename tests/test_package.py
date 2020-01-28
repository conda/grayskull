from grayskull.base.section import Package


def test_package():
    pkg = Package(name="pkg1", version="1.0.0")
    assert pkg.section_name == "package"
    assert pkg.version == "1.0.0"
    assert pkg.name == "pkg1"
