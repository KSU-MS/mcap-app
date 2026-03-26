"""Compatibility shim for conversion module.

Use `api.conversion.telemetry_log` for new imports.
"""

from .conversion.telemetry_log import Channel, DataLog, Message

__all__ = ["Channel", "DataLog", "Message"]
