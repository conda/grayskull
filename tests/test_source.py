from grayskull.base.source import Source


def test_source():
    source = Source(url="foo.com", sha256="1234567984635asdasf")
    assert source
