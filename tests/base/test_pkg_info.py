from grayskull.base.pkg_info import check_pkgs_availability, is_pkg_available


def test_pkg_available():
    assert is_pkg_available("pytest")


def test_pkg_not_available():
    assert not is_pkg_available("NOT_PACKAGE_654987321")


def test_check_pkgs_availability(capsys):
    all_pkgs = check_pkgs_availability(
        [
            "pytest >=4.0.0,<5.0.0  # [win]",
            "requests",
            "pandas[test]",
            "NOT_PACKAGE_13248743",
        ]
    )

    assert sorted(all_pkgs) == sorted(
        [
            ("pytest >=4.0.0,<5.0.0  # [win]", True),
            ("requests", True),
            ("pandas[test]", True),
            ("NOT_PACKAGE_13248743", False),
        ]
    )
