try:
    from typing import Self
except ImportError:
    from typing import TypeVar

    Self = TypeVar("Self", bound="CLIConfig")

import progressbar

WIDGET_BAR_DOWNLOAD = [
    progressbar.Percentage(),
    " ",
    progressbar.ETA(format="%(eta)8s"),
    " ",
    progressbar.AdaptiveTransferSpeed(),
    progressbar.Bar(),
]


class CLIConfig:
    __instance: Self | None = None

    def __new__(cls, stdout: bool = False, list_missing_deps: bool = False):
        if CLIConfig.__instance is None:
            CLIConfig.__instance = object.__new__(cls)
            CLIConfig.__instance.stdout = stdout
            CLIConfig.__instance.list_missing_deps = list_missing_deps
        return CLIConfig.__instance
