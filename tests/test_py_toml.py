"""Unit and integration tests for recipifying Poetry projects."""

import filecmp
from pathlib import Path

import pytest

from grayskull.main import generate_recipes_from_list, init_parser
from grayskull.strategy.py_toml import (
    add_flit_metadata,
    add_pep725_metadata,
    add_poetry_metadata,
    get_all_toml_info,
    get_constrained_dep,
)


def test_add_flit_metadata():
    metadata = {"build": {"entry_points": []}}
    toml_metadata = {"tool": {"flit": {"scripts": {"key": "value"}}}}
    result = add_flit_metadata(metadata, toml_metadata)
    assert result == {"build": {"entry_points": ["key = value"]}}


def test_add_poetry_metadata():
    toml_metadata = {
        "tool": {
            "poetry": {
                "dependencies": {"tomli": ">=1.0.0", "requests": ">=1.0.0"},
                "group": {
                    "test": {"dependencies": {"tox": ">=1.0.0", "pytest": ">=1.0.0"}}
                },
            }
        }
    }
    metadata = {
        "requirements": {
            "host": ["pkg_host1 >=1.0.0", "pkg_host2"],
            "run": ["pkg_run1", "pkg_run2 >=2.0.0"],
        },
        "test": {"requires": ["mock", "pkg_test >=1.0.0"]},
    }
    assert add_poetry_metadata(metadata, toml_metadata) == {
        "requirements": {
            "host": ["pkg_host1 >=1.0.0", "pkg_host2", "poetry-core"],
            "run": [
                "pkg_run1",
                "pkg_run2 >=2.0.0",
                "tomli >=1.0.0",
                "requests >=1.0.0",
            ],
        },
        "test": {
            "requires": ["mock", "pkg_test >=1.0.0", "tox >=1.0.0", "pytest >=1.0.0"]
        },
    }


def test_poetry_dependencies():
    toml_path = Path(__file__).parent / "data" / "poetry" / "poetry.toml"
    result = get_all_toml_info(toml_path)

    assert result["test"]["requires"] == ["cachy 0.3.0", "deepdiff >=6.2.0,<7.0.0"]
    assert result["requirements"]["host"] == ["setuptools>=1.1.0", "poetry-core"]
    assert result["requirements"]["run"] == [
        "python >=3.7.0,<4.0.0",
        "cleo >=2.0.0,<3.0.0",
        "html5lib >=1.0.0,<2.0.0",
        "urllib3 >=1.26.0,<2.0.0",
    ]


def test_poetry_langchain_snapshot(tmpdir):
    """Snapshot test that asserts correct recipifying of an example Poetry project."""
    snapshot_path = (
        Path(__file__).parent / "data" / "poetry" / "langchain-expected.yaml"
    )
    output_path = tmpdir / "langchain" / "meta.yaml"

    parser = init_parser()
    # Check pyproject.toml for version 0.0.119
    # https://inspector.pypi.io/project/langchain/0.0.119
    args = parser.parse_args(
        ["pypi", "langchain==0.0.119", "-o", str(tmpdir), "-m", "AddYourGitHubIdHere"]
    )

    generate_recipes_from_list(args.pypi_packages, args)
    assert filecmp.cmp(snapshot_path, output_path, shallow=False)


def test_poetry_get_constrained_dep_version_not_present():
    assert (
        next(
            get_constrained_dep(
                {"git": "https://codeberg.org/hjacobs/pytest-kind.git"}, "pytest-kind"
            )
        )
        == "pytest-kind"
    )


def test_poetry_get_constrained_dep_version_string():
    assert next(get_constrained_dep(">=2022.8.2", "s3fs")) == "s3fs >=2022.8.2"


def test_poetry_get_constrained_dep_tilde_version_string():
    assert next(get_constrained_dep("~0.21.0", "s3fs")) == "s3fs >=0.21.0,<0.22.0"


def test_poetry_get_constrained_dep_caret_version_string():
    assert next(get_constrained_dep("^1.24.0", "numpy")) == "numpy >=1.24.0,<2.0.0"


def test_poetry_get_constrained_dep_caret_PEP440_version_string():
    assert (
        next(get_constrained_dep("^0.8.post1", "pyfiglet"))
        == "pyfiglet >=0.8.0.post1,<0.9.0"
    )


def test_poetry_get_constrained_dep_caret_PEP440_version_regression_534():
    # Regression test for #534
    # https://github.com/conda/grayskull/issues/534
    assert (
        next(get_constrained_dep("^0.10.11.post1", "llama-index-core"))
        == "llama-index-core >=0.10.11.post1,<0.11.0"
    )


def test_poetry_get_constrained_dep_no_version_only_python():
    assert (
        next(
            get_constrained_dep(
                {"python": ">=3.8"},
                "validators",
            )
        )
        == "validators  # [py>=38]"
    )


def test_poetry_get_constrained_dep_no_version_only_python_version_and_platform():
    assert (
        next(
            get_constrained_dep(
                {"python": ">=3.8", "platform": "darwin"},
                "validators",
            )
        )
        == "validators  # [py>=38 and osx]"
    )


def test_poetry_get_constrained_dep_caret_version_python_version_min_max_and_platform():
    assert (
        next(
            get_constrained_dep(
                {"version": "^1.5", "python": ">=3.8,<3.12", "platform": "darwin"},
                "pandas",
            )
        )
        == "pandas >=1.5.0,<2.0.0  # [py>=38 and py<312 and osx]"
    )


def test_poetry_get_constrained_dep_caret_version_python_version_in_or_and_platform():
    assert next(
        get_constrained_dep(
            {
                "version": "^1.5",
                "python": "<=3.7,!=3.4|>=3.10,!=3.12",
                "platform": "darwin",
            },
            "pandas",
        )
    ) == (
        "pandas >=1.5.0,<2.0.0  # [(py<=37 and py!=34 or py>=310 and py!=312) and osx]"
    )


def test_poetry_get_constrained_dep_compatible_rel_op_python_version_and_platform():
    assert next(
        get_constrained_dep(
            {
                "version": "^1.5",
                "python": "~=3.8",
                "platform": "darwin",
            },
            "pandas",
        )
    ) == ("pandas >=1.5.0,<2.0.0  # [py>=38 and py<4 and osx]")


def test_poetry_get_constrained_dep_wildvard_python_version_and_platform():
    assert next(
        get_constrained_dep(
            {
                "version": "^1.5",
                "python": "3.*",
                "platform": "darwin",
            },
            "pandas",
        )
    ) == ("pandas >=1.5.0,<2.0.0  # [py>=3 and py<4 and osx]")


def test_poetry_get_constrained_dep_no_version_only_platform():
    assert (
        next(
            get_constrained_dep(
                {"platform": "darwin"},
                "validators",
            )
        )
        == "validators  # [osx]"
    )


def test_poetry_get_constrained_dep_caret_version_python_minimum_version():
    assert (
        next(
            get_constrained_dep(
                {"version": "~0.21.0", "python": ">=3.8"},
                "validators",
            )
        )
        == "validators >=0.21.0,<0.22.0  # [py>=38]"
    )


def test_poetry_get_constrained_dep_caret_version_python_maximum_version():
    assert (
        next(
            get_constrained_dep(
                [{"version": "^1.24.0", "python": "<3.10"}],
                "numpy",
            )
        )
        == "numpy >=1.24.0,<2.0.0  # [py<310]"
    )


def test_poetry_get_constrained_dep_multiple_constraints_dependencies_with_platform():
    assert list(
        get_constrained_dep(
            [
                {"version": "^1.24.0", "python": "<3.10"},
                {"version": "^1.26.0", "python": ">=3.10"},
                {"version": "^1.26.0", "python": ">=3.8,<3.10", "platform": "darwin"},
            ],
            "numpy",
        )
    ) == [
        "numpy >=1.24.0,<2.0.0  # [py<310]",
        "numpy >=1.26.0,<2.0.0  # [py>=310]",
        "numpy >=1.26.0,<2.0.0  # [py>=38 and py<310 and osx]",
    ]


def test_poetry_get_constrained_dep_multiple_constraints_dependencies_ersilia():
    assert (
        next(
            get_constrained_dep(
                [{"version": "~0.21.0", "python": ">=3.8"}],
                "validators",
            )
        )
        == "validators >=0.21.0,<0.22.0  # [py>=38]"
    )


def test_poetry_get_constrained_dep_multiple_constraints_dependencies_xypattern():
    assert list(
        get_constrained_dep(
            [
                {"version": "^1.24.0", "python": "<3.10"},
                {"version": "^1.26.0", "python": ">=3.10"},
            ],
            "numpy",
        )
    ) == ["numpy >=1.24.0,<2.0.0  # [py<310]", "numpy >=1.26.0,<2.0.0  # [py>=310]"]


def test_poetry_get_constrained_dep_multiple_constraints_dependencies_nannyml():
    assert (
        next(
            get_constrained_dep(
                [{"version": "^1.5", "python": ">=3.8,<3.12"}],
                "pandas",
            )
        )
        == "pandas >=1.5.0,<2.0.0  # [py>=38 and py<312]"
    )


def test_poetry_get_constrained_dep_mult_constraints_deps_databricks_sql_connector():
    assert list(
        get_constrained_dep(
            [
                {"version": ">=6.0.0", "python": ">=3.7,<3.11"},
                {"version": ">=10.0.1", "python": ">=3.11"},
            ],
            "pyarrow",
        )
    ) == [
        "pyarrow >=6.0.0  # [py>=37 and py<311]",
        "pyarrow >=10.0.1  # [py>=311]",
    ]


def test_poetry_get_constrained_dep_mult_constraints_deps_langchain_0_0_119():
    assert (
        next(
            get_constrained_dep(
                {"version": "^2.11.0", "optional": True, "python": "^3.10, <3.12"},
                "tensorflow-text",
            )
        )
        == "tensorflow-text >=2.11.0,<3.0.0  # [py>=310 and py<4 and py<312]"
    )


def test_poetry_entrypoints():
    poetry = {
        "requirements": {"host": ["setuptools"], "run": ["python"]},
        "build": {},
        "test": {},
    }
    toml_metadata = {
        "tool": {
            "poetry": {
                "scripts": {
                    "grayskull": "grayskull.main:main",
                    "grayskull-recipe": "grayskull.main:recipe",
                }
            }
        }
    }
    assert add_poetry_metadata(poetry, toml_metadata) == {
        "requirements": {
            "host": ["setuptools", "poetry-core"],
            "run": ["python"],
        },
        "build": {
            "entry_points": [
                "grayskull = grayskull.main:main",
                "grayskull-recipe = grayskull.main:recipe",
            ]
        },
        "test": {},
    }


@pytest.mark.parametrize(
    "conda_section, pep725_section",
    [("build", "build-requires"), ("host", "host-requires"), ("run", "dependencies")],
)
@pytest.mark.parametrize(
    "purl, purl_translated",
    [
        ("virtual:compiler/c", "{{ compiler('c') }}"),
        ("pkg:alice/bob", "pkg:alice/bob"),
    ],
)
def test_pep725_section_lookup(conda_section, pep725_section, purl, purl_translated):
    toml_metadata = {
        "external": {
            pep725_section: [purl],
        }
    }
    assert add_pep725_metadata({}, toml_metadata) == {
        "requirements": {conda_section: [purl_translated]}
    }
