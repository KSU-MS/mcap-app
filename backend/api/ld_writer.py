"""Compatibility shim for conversion module.

Use `api.conversion.ld_writer` for new imports.
"""

from .conversion.ld_writer import write_ld_file
from .conversion.motec_ld_native import write_ld_native

__all__ = ["write_ld_file", "write_ld_native"]
