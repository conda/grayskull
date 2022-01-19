import pytest

from grayskull.sdist import BadSdistError, SdistContent


def test_sdist_content_from_zip(local_zip_sdist):
    sd = SdistContent(local_zip_sdist)
    assert sd.name == "test-package"
    assert sd.version == "1.2.0"
    assert sd.metadata.get("Requires-Python") == ">=3.8"
    assert "Programming Language :: Python :: 3.8" in sd.metadata.get_all("Classifier")


def test_sdist_content_from_tar(pkg_pytest):
    sd = SdistContent(pkg_pytest)
    assert sd.name == "pytest"
    assert sd.version == "5.3.5"
    assert sd.metadata.get("Home-Page") == "https://docs.pytest.org/en/latest/"
    assert sd.metadata.get("Summary") == "pytest: simple powerful testing with Python"
    assert sd.metadata.get("License") == "MIT license"


def test_sdist_bad_tar(local_tar_not_sdist):
    with pytest.raises(BadSdistError) as excinfo:
        _ = SdistContent(local_tar_not_sdist)
    assert f"Invalid sdist: PKG-INFO not found in {local_tar_not_sdist}" in str(excinfo)


def test_sdist_bad_archive(tmp_path):
    myfile = tmp_path / "README.md"
    myfile.write_text("Hello")
    with pytest.raises(BadSdistError) as excinfo:
        _ = SdistContent(str(myfile))
    assert f"Invalid sdist: {myfile} is not a tar or zip file" in str(excinfo)
