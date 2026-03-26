"""Compatibility shim for conversion module.

Use `api.conversion.mcap_converter` for new imports.
"""

from .conversion.mcap_converter import McapToCsvConverter

__all__ = ["McapToCsvConverter"]
