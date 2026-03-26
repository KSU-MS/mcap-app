"""Shared status constants used across backend workflows."""

MCAP_TERMINAL_STATUSES = {
    "completed",
    "success",
    "failed",
    "skipped",
}

EXPORT_ACTIVE_STATUSES = {
    "pending",
    "processing",
}

EXPORT_TERMINAL_STATUSES = {
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
}


def is_mcap_terminal(status_value: str | None) -> bool:
    if not status_value:
        return False
    value = status_value.lower()
    return value in MCAP_TERMINAL_STATUSES or value.startswith("error")


def is_export_terminal(status_value: str | None) -> bool:
    if not status_value:
        return False
    return status_value.lower() in EXPORT_TERMINAL_STATUSES
