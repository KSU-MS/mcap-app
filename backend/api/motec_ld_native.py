"""Compatibility shim for conversion module.

Use `api.conversion.motec_ld_native` for new imports.
"""

from .conversion.motec_ld_native import MotecLogNative, write_ld_native

__all__ = ["MotecLogNative", "write_ld_native"]
