import re

import semver

VERSION_REGEX = re.compile(
    r"""^[vV]?
        (?P<major>0|[1-9]\d*)
        (\.
        (?P<minor>0|[1-9]\d*)
        (\.
            (?P<patch>0|[1-9]\d*)
        )?
        )?$
    """,
    re.VERBOSE,
)


class InvalidVersion(BaseException):
    pass


def parse_version(version: str) -> dict[str, int | None]:
    """
    Parses a version string (not necessarily semver) to a dictionary with keys
    "major", "minor", and "patch". "minor" and "patch" are possibly None.

    >>> parse_version("0")
    {'major': 0, 'minor': None, 'patch': None}
    >>> parse_version("1")
    {'major': 1, 'minor': None, 'patch': None}
    >>> parse_version("1.2")
    {'major': 1, 'minor': 2, 'patch': None}
    >>> parse_version("1.2.3")
    {'major': 1, 'minor': 2, 'patch': 3}
    """
    match = VERSION_REGEX.search(version)
    if not match:
        raise InvalidVersion(f"Could not parse version {version}.")

    return {
        key: None if value is None else int(value)
        for key, value in match.groupdict().items()
    }


def vdict_to_vinfo(version_dict: dict[str, int | None]) -> semver.VersionInfo:
    """
    Coerces version dictionary to a semver.VersionInfo object. If minor or patch
    numbers are missing, 0 is substituted in their place.
    """
    ver = {key: 0 if value is None else value for key, value in version_dict.items()}
    return semver.VersionInfo(**ver)


def coerce_to_semver(version: str) -> str:
    """
    Coerces a version string to a semantic version.
    """
    if semver.VersionInfo.is_valid(version):
        return version

    parsed_version = parse_version(version)
    vinfo = vdict_to_vinfo(parsed_version)
    return str(vinfo)


def get_caret_ceiling(target: str) -> str:
    """
    Accepts a Poetry caret target and returns the exclusive version ceiling.

    Targets that are invalid semver strings (e.g. "1.2", "0") are handled
    according to the Poetry caret requirements specification, which is based on
    whether the major version is 0:

    - If the major version is 0, the ceiling is determined by bumping the
    rightmost specified digit and then coercing it to semver.
    Example: 0 => 1.0.0, 0.1 => 0.2.0, 0.1.2 => 0.1.3

    - If the major version is not 0, the ceiling is determined by
    coercing it to semver and then bumping the major version.
    Example: 1 => 2.0.0, 1.2 => 2.0.0, 1.2.3 => 2.0.0

    # Examples from Poetry docs
    >>> get_caret_ceiling("0")
    '1.0.0'
    >>> get_caret_ceiling("0.0")
    '0.1.0'
    >>> get_caret_ceiling("0.0.3")
    '0.0.4'
    >>> get_caret_ceiling("0.2.3")
    '0.3.0'
    >>> get_caret_ceiling("1")
    '2.0.0'
    >>> get_caret_ceiling("1.2")
    '2.0.0'
    >>> get_caret_ceiling("1.2.3")
    '2.0.0'
    """
    if not semver.VersionInfo.is_valid(target):
        target_dict = parse_version(target)

        if target_dict["major"] == 0:
            if target_dict["minor"] is None:
                target_dict["major"] += 1
            elif target_dict["patch"] is None:
                target_dict["minor"] += 1
            else:
                target_dict["patch"] += 1
            return str(vdict_to_vinfo(target_dict))

        vdict_to_vinfo(target_dict)
        return str(vdict_to_vinfo(target_dict).bump_major())

    target_vinfo = semver.VersionInfo.parse(target)

    if target_vinfo.major == 0:
        if target_vinfo.minor == 0:
            return str(target_vinfo.bump_patch())
        else:
            return str(target_vinfo.bump_minor())
    else:
        return str(target_vinfo.bump_major())


def get_tilde_ceiling(target: str) -> str:
    """
    Accepts a Poetry tilde target and returns the exclusive version ceiling.

    # Examples from Poetry docs
    >>> get_tilde_ceiling("1")
    '2.0.0'
    >>> get_tilde_ceiling("1.2")
    '1.3.0'
    >>> get_tilde_ceiling("1.2.3")
    '1.3.0'
    """
    target_dict = parse_version(target)
    if target_dict["minor"]:
        return str(vdict_to_vinfo(target_dict).bump_minor())

    return str(vdict_to_vinfo(target_dict).bump_major())


def encode_poetry_version(poetry_specifier: str) -> str:
    """
    Encodes Poetry version specifier as a Conda version specifier.

    Example: ^1 => >=1.0.0,<2.0.0

    # should be unchanged
    >>> encode_poetry_version("1.*")
    '1.*'
    >>> encode_poetry_version(">=1,<2")
    '>=1,<2'
    >>> encode_poetry_version("==1.2.3")
    '==1.2.3'
    >>> encode_poetry_version("!=1.2.3")
    '!=1.2.3'

    # strip spaces
    >>> encode_poetry_version(">= 1, < 2")
    '>=1,<2'

    # handle exact version specifiers correctly
    >>> encode_poetry_version("1.2.3")
    '1.2.3'
    >>> encode_poetry_version("==1.2.3")
    '==1.2.3'

    # handle caret operator correctly
    # examples from Poetry docs
    >>> encode_poetry_version("^0")
    '>=0.0.0,<1.0.0'
    >>> encode_poetry_version("^0.0")
    '>=0.0.0,<0.1.0'
    >>> encode_poetry_version("^0.0.3")
    '>=0.0.3,<0.0.4'
    >>> encode_poetry_version("^0.2.3")
    '>=0.2.3,<0.3.0'
    >>> encode_poetry_version("^1")
    '>=1.0.0,<2.0.0'
    >>> encode_poetry_version("^1.2")
    '>=1.2.0,<2.0.0'
    >>> encode_poetry_version("^1.2.3")
    '>=1.2.3,<2.0.0'

    # handle tilde operator correctly
    # examples from Poetry docs
    >>> encode_poetry_version("~1")
    '>=1.0.0,<2.0.0'
    >>> encode_poetry_version("~1.2")
    '>=1.2.0,<1.3.0'
    >>> encode_poetry_version("~1.2.3")
    '>=1.2.3,<1.3.0'

    # handle or operator correctly
    >>> encode_poetry_version("1.2.3|1.2.4")
    '1.2.3|1.2.4'
    >>> encode_poetry_version("^5|| ^6 | ^7")
    '>=5.0.0,<6.0.0|>=6.0.0,<7.0.0|>=7.0.0,<8.0.0'
    """
    if "|" in poetry_specifier:
        poetry_or_clauses = [clause.strip() for clause in poetry_specifier.split("|")]
        conda_or_clauses = [
            encode_poetry_version(clause)
            for clause in poetry_or_clauses
            if clause != ""
        ]
        return "|".join(conda_or_clauses)

    poetry_clauses = poetry_specifier.split(",")

    conda_clauses = []
    for poetry_clause in poetry_clauses:
        poetry_clause = poetry_clause.replace(" ", "")
        if poetry_clause.startswith("^"):
            # handle ^ operator
            target = poetry_clause[1:]
            floor = coerce_to_semver(target)
            ceiling = get_caret_ceiling(target)
            conda_clauses.append(">=" + floor)
            conda_clauses.append("<" + ceiling)
            continue

        if poetry_clause.startswith("~"):
            # handle ~ operator
            target = poetry_clause[1:]
            floor = coerce_to_semver(target)
            ceiling = get_tilde_ceiling(target)
            conda_clauses.append(">=" + floor)
            conda_clauses.append("<" + ceiling)
            continue

        # other poetry clauses should be conda-compatible
        conda_clauses.append(poetry_clause)

    return ",".join(conda_clauses)


def encode_poetry_platform_to_selector_item(poetry_platform: str) -> str:
    """
    Encodes Poetry Platform specifier as a Conda selector.

    Example: "darwin" => "osx"
    """

    platform_selectors = {"windows": "win", "linux": "linux", "darwin": "osx"}
    poetry_platform = poetry_platform.lower().strip()
    if poetry_platform in platform_selectors:
        return platform_selectors[poetry_platform]
    else:  # unknown
        return ""


def encode_poetry_python_version_to_selector_item(poetry_specifier: str) -> str:
    """
    Encodes Poetry Python version specifier as a Conda selector.

    Example:
        ">=3.8,<3.12" => "py>=38 and py<312"
        ">=3.8,<3.12,!=3.11" => "py>=38 and py<312 and py!=311"
        "<3.8|>=3.10" => "py<38 or py>=310"
        "<3.8|>=3.10,!=3.11" => "py<38 or py>=310 and py!=311"

    # handle exact version specifiers correctly
    >>> encode_poetry_python_version_to_selector_item("3")
    'py==3'
    >>> encode_poetry_python_version_to_selector_item("3.8")
    'py==38'
    >>> encode_poetry_python_version_to_selector_item("==3.8")
    'py==38'
    >>> encode_poetry_python_version_to_selector_item("!=3.8")
    'py!=38'
    >>> encode_poetry_python_version_to_selector_item("!=3.8.1")
    'py!=38'

    # handle caret operator correctly
    >>> encode_poetry_python_version_to_selector_item("^3.10") # '>=3.10.0,<4.0.0'
    'py>=310 and py<4'

    # handle tilde operator correctly
    >>> encode_poetry_python_version_to_selector_item("~3.10") # '>=3.10.0,<3.11.0'
    'py>=310 and py<311'

    # handle multiple requirements correctly (in "and")
    >>> encode_poetry_python_version_to_selector_item(">=3.8,<3.12,!=3.11")
    'py>=38 and py<312 and py!=311'

    # handle multiple requirements in "or" correctly ("and" takes precendence)
    >>> encode_poetry_python_version_to_selector_item("<3.8|>=3.10,!=3.11")
    'py<38 or py>=310 and py!=311'
    """

    if not poetry_specifier:
        return ""

    version_specifier = encode_poetry_version(poetry_specifier)

    if "|" in version_specifier:
        poetry_or_clauses = [clause.strip() for clause in version_specifier.split("|")]
        conda_or_clauses = [
            encode_poetry_python_version_to_selector_item(clause)
            for clause in poetry_or_clauses
            if clause != ""
        ]
        conda_or_clauses = " or ".join(conda_or_clauses)
        return conda_or_clauses

    conda_clauses = version_specifier.split(",")

    conda_selectors = []
    for conda_clause in conda_clauses:
        operator, version = parse_python_version(conda_clause)
        version_selector = version.replace(".", "")
        conda_selectors.append(f"py{operator}{version_selector}")
    selectors = " and ".join(conda_selectors)
    return selectors


def parse_python_version(selector: str):
    """
    Return operator and normalized version from a version selector

    Examples:
        ">=3"   -> ">=", "3"
        ">=3.0"   -> ">=", "3"
        ">=3.8"   -> ">=", "3.8"
        ">=3.8.0" -> ">=", "3.8"
        "<4.0.0"  -> "<", "4"
        "3.12"    -> "==", 3.12"
        "=3.8"    -> "==", "3.8"
        ">=3.8.0.1" -> ">=", "3.8"

    >>> parse_python_version(">=3.8")
    ('>=', '3.8')
    >>> parse_python_version("3.12")
    ('==', '3.12')
    >>> parse_python_version("<4.0.0")
    ('<', '4')
    >>> parse_python_version(">=3")
    ('>=', '3')
    >>> parse_python_version(">=3.8.0")
    ('>=', '3.8')
    >>> parse_python_version(">=3.8.0.1")
    ('>=', '3.8')

    The version is normalized to "major.minor" (drop patch if present)
    or "major" if minor is 0
    """
    # Regex to split operator and version
    pattern = r"^(?P<operator>\^|~|>=|<=|!=|==|>|<|=)?(?P<version>\d+(\.\d+){0,3})$"
    match = re.match(pattern, selector)
    if not match:
        raise ValueError(f"Invalid version selector: {selector}")

    # Extract operator and version
    operator = match.group("operator")
    # Default to "==" if no operator is provided or "="
    operator = "==" if operator in {None, "="} else operator
    version = match.group("version")

    # Split into major, minor, and discard the rest (patch or additional parts)
    try:
        # Attempt to unpack major, minor, and ignore the rest
        major, minor, *_ = version.split(".")
    except ValueError:
        # If unpacking fails, assume only major is provided
        return operator, version

    # Return only major if minor is "0", otherwise return major.minor
    return operator, major if minor == "0" else f"{major}.{minor}"


def combine_conda_selectors(python_selector: str, platform_selector: str):
    """
    Combine selectors based on presence
    """
    if python_selector and platform_selector:
        if " or " in python_selector:
            python_selector = f"({python_selector})"
        selector = f"{python_selector} and {platform_selector}"
    elif python_selector:
        selector = f"{python_selector}"
    elif platform_selector:
        selector = f"{platform_selector}"
    else:
        selector = ""
    return f"  # [{selector}]" if selector else ""
