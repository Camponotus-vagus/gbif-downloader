"""
Export modules for GBIF occurrence data.

This package provides exporters for various file formats:
- Excel (.xlsx) with conditional formatting
- CSV (.csv) for universal compatibility
- GeoJSON (.geojson) for GIS applications
"""

from gbif_downloader.exporters.excel import ExcelExporter
from gbif_downloader.exporters.csv import CSVExporter
from gbif_downloader.exporters.geojson import GeoJSONExporter

__all__ = ["ExcelExporter", "CSVExporter", "GeoJSONExporter"]


def get_exporter(format_name: str):
    """
    Get the appropriate exporter for a format name.

    Args:
        format_name: Format name (excel, csv, geojson)

    Returns:
        Exporter class

    Raises:
        ValueError: If format is not supported
    """
    exporters = {
        "excel": ExcelExporter,
        "xlsx": ExcelExporter,
        "csv": CSVExporter,
        "geojson": GeoJSONExporter,
        "json": GeoJSONExporter,
    }

    format_lower = format_name.lower()
    if format_lower not in exporters:
        supported = ", ".join(sorted(set(exporters.keys())))
        raise ValueError(
            f"Unsupported format: {format_name}. Supported formats: {supported}"
        )

    return exporters[format_lower]
