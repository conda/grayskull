__all__ = ["__version__"]

try:
    from .version import version as __version__
except ImportError:
    __version__ = "unknown"
