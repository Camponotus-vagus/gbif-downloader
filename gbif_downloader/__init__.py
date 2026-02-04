"""
GBIF Downloader - Download and filter biodiversity occurrence data from GBIF.

This package provides both CLI and GUI interfaces for downloading museum specimen
records from the Global Biodiversity Information Facility (GBIF) API.

Features:
- Filter by taxonomy (genus, species, family)
- Filter by year range, coordinate uncertainty, elevation
- Export to Excel, CSV, or GeoJSON formats
- Robust API handling with retry logic
- Progress tracking and resumable downloads

Example CLI usage:
    gbif-download --genus Nebria --output nebria_data.xlsx
    gbif-download --genus Nebria --species germarii,castanea --format geojson

Example Python usage:
    from gbif_downloader import GBIFClient, FilterConfig

    client = GBIFClient()
    config = FilterConfig(genus="Nebria", year_start=1900)
    records = client.download_occurrences(config)
"""

__version__ = "2.0.0"
__author__ = "Francesco Mensa"

from gbif_downloader.api import GBIFClient, GBIFError, TaxonNotFoundError
from gbif_downloader.filters import FilterConfig, RecordFilter
from gbif_downloader.config import Config

__all__ = [
    "GBIFClient",
    "GBIFError",
    "TaxonNotFoundError",
    "FilterConfig",
    "RecordFilter",
    "Config",
    "__version__",
]
