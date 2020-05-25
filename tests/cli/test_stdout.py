from progressbar import ProgressBar

from grayskull.cli import CLIConfig
from grayskull.cli.stdout import manage_progressbar, print_msg


def test_print_stdout(capsys):
    CLIConfig().stdout = True
    print_msg("TEST-OUTPUT")
    captured_out = capsys.readouterr()
    assert captured_out.out == "TEST-OUTPUT\n"


def test_disabled_print(capsys):
    CLIConfig().stdout = False
    print_msg("TEST-OUTPUT")
    captured_out = capsys.readouterr()
    assert captured_out.out == ""


def test_progressbar_enable():
    CLIConfig().stdout = True
    with manage_progressbar(max_value=100, prefix="prefix-") as bar:
        assert isinstance(bar, ProgressBar)


def test_progressbar_disable():
    CLIConfig().stdout = False
    with manage_progressbar(max_value=100, prefix="prefix-") as bar:
        assert not isinstance(bar, ProgressBar)
