"""Facade service for MCAP conversion workflows.

This service provides a stable API for callers while delegating actual
conversion logic to the existing converter implementation.
"""

from pathlib import Path

from ..conversion.mcap_converter import McapToCsvConverter
from .contracts import ConversionRequest, ConversionResult


class McapConversionService:
    """High-level conversion entrypoint for MCAP exports."""

    def __init__(self, converter: McapToCsvConverter | None = None):
        self.converter = converter or McapToCsvConverter()

    def convert(
        self,
        source_path: str | Path,
        output_path: str | Path,
        format_suffix: str,
        resample_hz: float,
    ) -> str:
        request = ConversionRequest(
            source_path=Path(source_path),
            output_path=Path(output_path),
            format_suffix=format_suffix,
            resample_hz=resample_hz,
        )
        result = self.convert_with_result(request)
        if not result.success:
            raise RuntimeError(result.error or "Conversion failed")
        return str(result.output_path)

    def convert_with_result(self, request: ConversionRequest) -> ConversionResult:
        try:
            output = self.converter.convert_to_csv(
                str(request.source_path),
                str(request.output_path),
                format=request.format_suffix,
                resample_hz=request.resample_hz,
            )
            return ConversionResult(success=True, output_path=Path(output))
        except Exception as exc:
            return ConversionResult(
                success=False,
                output_path=request.output_path,
                error=str(exc),
            )

    def convert_to_ld(
        self, source_path: str | Path, output_path: str | Path, resample_hz: float
    ) -> str:
        return self.convert(source_path, output_path, "ld", resample_hz)

    def convert_to_csv_omni(
        self, source_path: str | Path, output_path: str | Path, resample_hz: float
    ) -> str:
        return self.convert(source_path, output_path, "omni", resample_hz)

    def convert_to_csv_tvn(
        self, source_path: str | Path, output_path: str | Path, resample_hz: float
    ) -> str:
        return self.convert(source_path, output_path, "tvn", resample_hz)
