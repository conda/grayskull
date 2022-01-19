import tarfile
import zipfile
from email import policy
from email.message import Message
from email.parser import BytesHeaderParser


class BadSdistError(Exception):
    pass


def parse_pkg_info(fp) -> Message:
    hp = BytesHeaderParser(policy=policy.compat32)
    message = hp.parse(fp)
    return message


def get_pkg_info_from_zip(sdist_file: str) -> Message:
    with zipfile.ZipFile(sdist_file) as myzip:
        for member in myzip.namelist():
            if member.endswith("PKG-INFO"):
                with myzip.open(member) as f:
                    return parse_pkg_info(f)
    raise BadSdistError(f"Invalid sdist: PKG-INFO not found in {sdist_file}")


def get_pkg_info_from_tar(sdist_file: str) -> Message:
    with tarfile.open(sdist_file, "r") as file:
        for member in file:
            if member.name.endswith("PKG-INFO"):
                f = file.extractfile(member.name)
                return parse_pkg_info(f)
    raise BadSdistError(f"Invalid sdist: PKG-INFO not found in {sdist_file}")


def get_pkg_info(sdist_file: str) -> Message:
    if tarfile.is_tarfile(sdist_file):
        return get_pkg_info_from_tar(sdist_file)
    if zipfile.is_zipfile(sdist_file):
        return get_pkg_info_from_zip(sdist_file)
    raise BadSdistError(f"Invalid sdist: {sdist_file} is not a tar or zip file")


class SdistContent:
    def __init__(self, sdist_file: str):
        self.sdist_file = sdist_file
        self.metadata = get_pkg_info(sdist_file)

    @property
    def name(self) -> str:
        return self.metadata.get("Name")

    @property
    def version(self) -> str:
        return self.metadata.get("Version")
