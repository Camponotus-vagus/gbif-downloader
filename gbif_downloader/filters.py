"""
Filtering logic for GBIF occurrence records.

This module provides configurable filters for processing occurrence data,
including taxonomy, temporal, spatial, and data quality filters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from gbif_downloader.api import OccurrenceRecord
from gbif_downloader.utils import clean_string_list, validate_year, validate_positive_int


@dataclass
class FilterConfig:
    """
    Configuration for filtering GBIF occurrence records.

    Attributes:
        genus: Target genus name (required if no family specified)
        species_list: List of specific epithets to include (optional)
        family: Family name for broader searches (optional)
        year_start: First year to include (default: 1800)
        year_end: Last year to include (default: current year)
        uncertainty_max: Maximum coordinate uncertainty in meters (default: 1000)
        require_year: Exclude records without year (default: True)
        require_elevation: Exclude records without elevation (default: True)
        keep_unknown_uncertainty: Keep records with null uncertainty (default: True)
        countries: List of country codes to include (optional)
        institutions: List of institution codes to include (optional)
        basis_of_record: Record types to include (default: PRESERVED_SPECIMEN)
        deduplicate: Remove duplicate records (default: True)
    """

    genus: str | None = None
    species_list: list[str] = field(default_factory=list)
    family: str | None = None
    year_start: int = 1800
    year_end: int | None = None
    uncertainty_max: int = 1000
    require_year: bool = True
    require_elevation: bool = True
    keep_unknown_uncertainty: bool = True
    countries: list[str] = field(default_factory=list)
    institutions: list[str] = field(default_factory=list)
    basis_of_record: list[str] = field(
        default_factory=lambda: ["PRESERVED_SPECIMEN"]
    )
    deduplicate: bool = True

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Validate taxonomy
        if not self.genus and not self.family:
            raise ValueError("Either genus or family must be specified")

        # Validate years
        if self.year_start:
            self.year_start = validate_year(self.year_start, "year_start")

        if self.year_end:
            self.year_end = validate_year(self.year_end, "year_end")
        else:
            self.year_end = datetime.now().year

        if self.year_start > self.year_end:
            raise ValueError(
                f"year_start ({self.year_start}) cannot be after "
                f"year_end ({self.year_end})"
            )

        # Validate uncertainty
        self.uncertainty_max = validate_positive_int(
            self.uncertainty_max, "uncertainty_max", allow_zero=True
        )

        # Clean string lists
        self.species_list = clean_string_list(self.species_list)
        self.countries = [c.upper() for c in clean_string_list(self.countries)]
        self.institutions = clean_string_list(self.institutions)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterConfig:
        """
        Create FilterConfig from a dictionary (e.g., from YAML config).

        Args:
            data: Dictionary with configuration values

        Returns:
            FilterConfig instance
        """
        # Handle nested taxonomy section
        taxonomy = data.get("taxonomy", {})
        filters = data.get("filters", data)  # Support flat or nested

        return cls(
            genus=taxonomy.get("genus") or data.get("genus"),
            species_list=taxonomy.get("species") or data.get("species_list", []),
            family=taxonomy.get("family") or data.get("family"),
            year_start=filters.get("year_start", 1800),
            year_end=filters.get("year_end"),
            uncertainty_max=filters.get("uncertainty_max", 1000),
            require_year=filters.get("require_year", True),
            require_elevation=filters.get("require_elevation", True),
            keep_unknown_uncertainty=filters.get("keep_unknown_uncertainty", True),
            countries=filters.get("countries", []),
            institutions=filters.get("institutions", []),
            basis_of_record=filters.get(
                "basis_of_record", ["PRESERVED_SPECIMEN"]
            ),
            deduplicate=filters.get("deduplicate", True),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "taxonomy": {
                "genus": self.genus,
                "species": self.species_list,
                "family": self.family,
            },
            "filters": {
                "year_start": self.year_start,
                "year_end": self.year_end,
                "uncertainty_max": self.uncertainty_max,
                "require_year": self.require_year,
                "require_elevation": self.require_elevation,
                "keep_unknown_uncertainty": self.keep_unknown_uncertainty,
                "countries": self.countries,
                "institutions": self.institutions,
                "basis_of_record": self.basis_of_record,
                "deduplicate": self.deduplicate,
            },
        }


@dataclass
class FilterResult:
    """
    Result of filtering a record.

    Attributes:
        keep: Whether to keep the record
        reason: Why the record was filtered (if not kept)
        uncertainty_status: 'known', 'unknown', or 'exceeded'
    """

    keep: bool
    reason: str | None = None
    uncertainty_status: str = "known"


class RecordFilter:
    """
    Filter occurrence records based on configuration.

    This class applies the filtering logic from FilterConfig to individual
    OccurrenceRecord objects.

    Example:
        config = FilterConfig(genus="Nebria", year_start=1900)
        filter = RecordFilter(config)

        for record in records:
            result = filter.apply(record)
            if result.keep:
                filtered_records.append(record)
    """

    def __init__(self, config: FilterConfig):
        """
        Initialize filter with configuration.

        Args:
            config: FilterConfig instance
        """
        self.config = config
        self._seen_keys: set[int] = set()

        # Pre-process species list for faster matching
        self._species_set = set(self.config.species_list)

    def apply(self, record: OccurrenceRecord) -> FilterResult:
        """
        Apply all filters to a record.

        Args:
            record: OccurrenceRecord to filter

        Returns:
            FilterResult indicating whether to keep the record
        """
        # 1. Deduplication check
        if self.config.deduplicate:
            if record.key in self._seen_keys:
                return FilterResult(keep=False, reason="duplicate")
            self._seen_keys.add(record.key)

        # 2. Year filter
        if self.config.require_year and record.year is None:
            return FilterResult(keep=False, reason="missing_year")

        if record.year is not None:
            if record.year < self.config.year_start:
                return FilterResult(keep=False, reason="year_too_old")
            if self.config.year_end and record.year > self.config.year_end:
                return FilterResult(keep=False, reason="year_too_new")

        # 3. Elevation filter
        if self.config.require_elevation and record.elevation is None:
            return FilterResult(keep=False, reason="missing_elevation")

        # 4. Coordinate uncertainty filter
        uncertainty_status = self._check_uncertainty(record)
        if uncertainty_status == "exceeded":
            return FilterResult(
                keep=False,
                reason="uncertainty_exceeded",
                uncertainty_status=uncertainty_status,
            )
        if uncertainty_status == "unknown" and not self.config.keep_unknown_uncertainty:
            return FilterResult(
                keep=False,
                reason="uncertainty_unknown",
                uncertainty_status=uncertainty_status,
            )

        # 5. Species filter (if specified)
        if self._species_set:
            if not self._matches_species(record):
                return FilterResult(keep=False, reason="species_not_matched")

        # 6. Country filter (if specified)
        if self.config.countries:
            country = (record.country or "").upper()
            # Try to match country code from various fields
            if not any(c in country for c in self.config.countries):
                return FilterResult(keep=False, reason="country_not_matched")

        # 7. Institution filter (if specified)
        if self.config.institutions:
            inst = (record.institution_code or "").lower()
            if not any(i in inst for i in self.config.institutions):
                return FilterResult(keep=False, reason="institution_not_matched")

        return FilterResult(keep=True, uncertainty_status=uncertainty_status)

    def _check_uncertainty(self, record: OccurrenceRecord) -> str:
        """
        Check coordinate uncertainty status.

        Returns:
            'known' - uncertainty is within limit
            'unknown' - uncertainty is null/missing
            'exceeded' - uncertainty exceeds limit
        """
        unc = record.coordinate_uncertainty

        if unc is None:
            return "unknown"

        try:
            unc_value = float(unc)
            if unc_value <= self.config.uncertainty_max:
                return "known"
            else:
                return "exceeded"
        except (TypeError, ValueError):
            # Non-numeric uncertainty value
            return "unknown"

    def _matches_species(self, record: OccurrenceRecord) -> bool:
        """
        Check if record matches any target species.

        Matches against specificEpithet and scientificName.
        """
        # Check specific epithet (most reliable)
        epithet = (record.specific_epithet or "").lower()
        if epithet in self._species_set:
            return True

        # Check scientific name (fallback)
        sci_name = (record.scientific_name or "").lower()
        for species in self._species_set:
            if species in sci_name:
                return True

        return False

    def reset(self) -> None:
        """Reset the filter state (clears seen keys for deduplication)."""
        self._seen_keys.clear()

    @property
    def seen_count(self) -> int:
        """Number of unique records seen."""
        return len(self._seen_keys)


def filter_records(
    records: list[OccurrenceRecord],
    config: FilterConfig,
) -> tuple[list[OccurrenceRecord], dict[str, int]]:
    """
    Filter a list of records and return statistics.

    Args:
        records: List of OccurrenceRecord objects
        config: FilterConfig instance

    Returns:
        Tuple of (filtered records, statistics dict)
    """
    record_filter = RecordFilter(config)
    filtered = []
    stats = {
        "total": 0,
        "kept": 0,
        "duplicate": 0,
        "missing_year": 0,
        "year_too_old": 0,
        "year_too_new": 0,
        "missing_elevation": 0,
        "uncertainty_exceeded": 0,
        "uncertainty_unknown_kept": 0,
        "uncertainty_unknown_dropped": 0,
        "species_not_matched": 0,
        "country_not_matched": 0,
        "institution_not_matched": 0,
    }

    for record in records:
        stats["total"] += 1
        result = record_filter.apply(record)

        if result.keep:
            filtered.append(record)
            stats["kept"] += 1
            if result.uncertainty_status == "unknown":
                stats["uncertainty_unknown_kept"] += 1
        else:
            reason = result.reason or "other"
            if reason in stats:
                stats[reason] += 1
            if reason == "uncertainty_unknown":
                stats["uncertainty_unknown_dropped"] += 1

    return filtered, stats


def format_filter_stats(stats: dict[str, int]) -> str:
    """
    Format filter statistics as a human-readable string.

    Args:
        stats: Statistics dictionary from filter_records

    Returns:
        Formatted string
    """
    lines = [
        f"Total records processed: {stats['total']:,}",
        f"Records kept: {stats['kept']:,}",
        "",
        "Exclusion reasons:",
    ]

    exclusions = [
        ("Duplicates", "duplicate"),
        ("Missing year", "missing_year"),
        ("Year before range", "year_too_old"),
        ("Year after range", "year_too_new"),
        ("Missing elevation", "missing_elevation"),
        ("Uncertainty exceeded", "uncertainty_exceeded"),
        ("Unknown uncertainty (dropped)", "uncertainty_unknown_dropped"),
        ("Species not matched", "species_not_matched"),
        ("Country not matched", "country_not_matched"),
        ("Institution not matched", "institution_not_matched"),
    ]

    for label, key in exclusions:
        if stats.get(key, 0) > 0:
            lines.append(f"  - {label}: {stats[key]:,}")

    if stats.get("uncertainty_unknown_kept", 0) > 0:
        lines.append("")
        lines.append(
            f"Note: {stats['uncertainty_unknown_kept']:,} records with "
            "unknown uncertainty were kept (highlight in yellow)"
        )

    return "\n".join(lines)
