import hashlib
import os

from grayskull.base.utils import (
    get_all_modules_imported_script,
    get_std_modules,
    get_vendored_dependencies,
)
from grayskull.pypi import PyPi


def test_get_std_modules():
    std_modules = get_std_modules()
    assert "sys" in std_modules
    assert "os" in std_modules
    assert "ast" in std_modules
    assert "typing" in std_modules


def test_get_all_modules_imported_script(data_dir):
    all_imports = get_all_modules_imported_script(
        os.path.join(data_dir, "foo_imports.py")
    )
    assert sorted(all_imports) == sorted(["numpy", "pandas", "requests", "os", "sys"])


def test_get_vendored_dependencies(data_dir):
    all_deps = get_vendored_dependencies(os.path.join(data_dir, "foo_imports.py"))
    assert sorted(all_deps) == sorted(["numpy", "pandas", "requests"])


def test_download_pkg(pkg_pytest):
    with open(pkg_pytest, "rb") as pkg_file:
        content = pkg_file.read()
        pkg_sha256 = hashlib.sha256(content).hexdigest()
    assert (
        pkg_sha256 == "0d5fe9189a148acc3c3eb2ac8e1ac0742cb7618c084f3d228baaec0c254b318d"
    )
    setup_cfg = PyPi._get_setup_cfg(os.path.dirname(pkg_pytest))
    assert setup_cfg["name"] == "pytest"
    assert setup_cfg["python_requires"] == ">=3.5"
    assert setup_cfg["entry_points"] == {
        "console_scripts": ["pytest=pytest:main", "py.test=pytest:main"]
    }
