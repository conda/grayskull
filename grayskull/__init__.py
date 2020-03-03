__all__ = ["__version__"]

try:
    from ._version import version as __version__  # lgtm [py/import-own-module]
except ImportError:
    __version__ = "unknown"
