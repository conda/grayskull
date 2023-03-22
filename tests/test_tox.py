"""Unit and integration tests for recipifying Tox projects."""

from pathlib import Path

from grayskull.strategy.py_toml import get_all_toml_info


def test_get_all_toml_info():
    toml_path = Path(__file__).parent / "data" / "tox" / "tox.toml"

    result = get_all_toml_info(toml_path)
    assert result["build"]["entry_points"] == ["tox = tox.run:run"]
    assert result["about"] == {
        "license": "MIT",
        "dev_url": "https://github.com/tox-dev/tox",
        "home": "http://tox.readthedocs.org",
        "summary": "tox is a generic virtualenv management and test command line tool",
    }
    assert result["test"]["requires"] == [
        "build[virtualenv]>=0.9",
        "covdefaults>=2.2.2",
        "devpi-process>=0.3",
        "diff-cover>=7.3",
        "distlib>=0.3.6",
        "flaky>=3.7",
        "hatch-vcs>=0.3",
        "hatchling>=1.12.2",
        "psutil>=5.9.4",
        "pytest>=7.2",
        "pytest-cov>=4",
        "pytest-mock>=3.10",
        "pytest-xdist>=3.1",
        "re-assert>=1.1",
        "wheel>=0.38.4",
        'time-machine>=2.8.2; implementation_name != "pypy"',
    ]
    assert result["requirements"]["host"] == [
        "hatchling>=1.12.2",
        "hatch-vcs>=0.3",
        "python >=3.7",
    ]
    assert result["requirements"]["run"] == [
        "cachetools>=5.2.1",
        "chardet>=5.1",
        "colorama>=0.4.6",
        "packaging>=23",
        "platformdirs>=2.6.2",
        "pluggy>=1",
        "pyproject-api>=1.5",
        'tomli>=2.0.1; python_version < "3.11"',
        "virtualenv>=20.17.1",
        "filelock>=3.9",
        'importlib-metadata>=6; python_version < "3.8"',
        'typing-extensions>=4.4; python_version < "3.8"',
        "python >=3.7",
    ]
