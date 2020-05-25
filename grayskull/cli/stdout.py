from contextlib import contextmanager
from copy import deepcopy

from progressbar import ProgressBar

from grayskull.cli import WIDGET_BAR_DOWNLOAD, CLIConfig


def print_msg(msg: str):
    if CLIConfig().stdout:
        print(msg)


@contextmanager
def manage_progressbar(*, max_value: int, prefix: str):
    if CLIConfig().stdout:
        with ProgressBar(
            widgets=deepcopy(WIDGET_BAR_DOWNLOAD), max_value=max_value, prefix=prefix,
        ) as bar:
            yield bar
    else:

        class DisabledBar:
            def update(self, *args, **kargs):
                pass

        yield DisabledBar()
