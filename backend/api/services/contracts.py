"""Typed service contracts for conversion and export status."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ConversionRequest:
    source_path: Path
    output_path: Path
    format_suffix: str
    resample_hz: float


@dataclass(frozen=True)
class ConversionResult:
    success: bool
    output_path: Path
    error: str | None = None


@dataclass(frozen=True)
class ExportProgressSnapshot:
    id: int
    status: str
    format: str
    resample_hz: float
    error_message: str | None
    total_items: int
    completed_items: int
    failed_items: int
    progress_percent: int

    def to_payload(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "format": self.format,
            "resample_hz": self.resample_hz,
            "error_message": self.error_message,
            "total_items": self.total_items,
            "completed_items": self.completed_items,
            "failed_items": self.failed_items,
            "progress_percent": self.progress_percent,
        }
