from grayskull.base.section import Build, Package, Source


def test_package():
    pkg = Package(name="pkg1", version="1.0.0")
    assert pkg.section_name == "package"
    assert pkg.version == "1.0.0"
    assert pkg.name == "pkg1"


def test_source():
    source = Source(url="url.com", sha256="1234abcd")
    assert source.url == "url.com"
    assert source["url"] == "url.com"
    assert source.sha256 == "1234abcd"
    assert source["sha256"] == "1234abcd"


def test_build():
    build = Build(number=1, skip="true  # [win]")
    assert build.number == 1
    build.bump_build_number()
    assert build.number == 2
