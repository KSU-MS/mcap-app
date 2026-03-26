from pathlib import Path

from django.conf import settings

from ..models import McapLog


def resolve_source_file_for_log(
    mcap_log: McapLog, file_path: str | None = None
) -> Path:
    original_file_path = None
    original_uri = str(mcap_log.original_uri or "")
    recovered_uri = str(mcap_log.recovered_uri or "")
    if file_path:
        p = Path(file_path)
        if not p.is_absolute():
            p = (Path(settings.MEDIA_ROOT) / p).resolve()
        original_file_path = p

    if not original_file_path and original_uri:
        if original_uri.startswith(settings.MEDIA_URL):
            rel = original_uri.replace(settings.MEDIA_URL, "", 1)
            original_file_path = Path(settings.MEDIA_ROOT) / rel
        elif original_uri.startswith("/"):
            original_file_path = Path(original_uri)
        else:
            original_file_path = Path(settings.MEDIA_ROOT) / original_uri

    if recovered_uri and recovered_uri != "pending":
        if recovered_uri.startswith(settings.MEDIA_URL):
            rel = recovered_uri.replace(settings.MEDIA_URL, "", 1)
            recovered_path = Path(settings.MEDIA_ROOT) / rel
        elif recovered_uri.startswith("/"):
            recovered_path = Path(recovered_uri)
        else:
            recovered_path = Path(settings.MEDIA_ROOT) / recovered_uri
        if recovered_path.exists():
            return recovered_path

    return original_file_path or Path("")


def resolve_original_file_for_log(mcap_log: McapLog) -> Path:
    original_uri = str(mcap_log.original_uri or "")
    if not original_uri:
        return Path("")

    if original_uri.startswith(settings.MEDIA_URL):
        rel = original_uri.replace(settings.MEDIA_URL, "", 1)
        return Path(settings.MEDIA_ROOT) / rel
    if original_uri.startswith("/"):
        return Path(original_uri)
    return Path(settings.MEDIA_ROOT) / original_uri


def task_path_value(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(settings.MEDIA_ROOT))
    except Exception:
        return str(path)


def is_non_retryable_recover_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "invalid zero opcode" in message
