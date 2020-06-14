import grayskull
from grayskull.base.extra import get_git_current_user, get_git_current_user_metadata


def test_get_git_current_user_metadata(monkeypatch):
    monkeypatch.setattr("subprocess.check_output", lambda x: "Marcelo Duarte Trevisani")
    json_git = get_git_current_user_metadata()
    assert json_git["items"][0]["login"] == "marcelotrevisani"
    assert json_git["items"][0]["type"] == "User"


def test_get_git_current_with_multiple_users(monkeypatch):
    monkeypatch.setattr(
        grayskull.base.extra,
        "get_git_current_user_metadata",
        lambda: {"items": [{"login": "user1"}, {"login": "user2"}], "total_count": 2},
    )
    assert get_git_current_user() == "user1"


def test_get_git_current_user(monkeypatch):
    monkeypatch.setattr(
        grayskull.base.extra,
        "get_git_current_user_metadata",
        lambda: {"items": [{"login": "marcelotrevisani"}], "total_count": 1},
    )
    assert get_git_current_user() == "marcelotrevisani"

    def _fake_exception():
        raise Exception("fake exception")

    monkeypatch.setattr(
        grayskull.base.extra, "get_git_current_user_metadata", _fake_exception
    )
    assert get_git_current_user() == "AddYourGitHubIdHere"
