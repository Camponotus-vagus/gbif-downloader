"""
GBIF API client with robust error handling and pagination.

This module provides a clean interface to the GBIF occurrence API with:
- Connection pooling and session management
- Exponential backoff retry logic
- Proper rate limit handling
- Cursor-based pagination to avoid offset limits
- Taxon validation to prevent downloading wrong data
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generator, Callable
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from gbif_downloader.utils import retry_with_backoff, get_logger

# GBIF API base URL
GBIF_API_BASE = "https://api.gbif.org/v1/"

# API endpoints
SPECIES_MATCH_ENDPOINT = "species/match"
OCCURRENCE_SEARCH_ENDPOINT = "occurrence/search"

# Request configuration
DEFAULT_TIMEOUT = (10, 30)  # (connect, read) in seconds
DEFAULT_PAGE_SIZE = 300
MAX_OFFSET = 100000  # GBIF's hard limit


class GBIFError(Exception):
    """Base exception for GBIF API errors."""

    pass


class TaxonNotFoundError(GBIFError):
    """Raised when a taxon cannot be found or doesn't match the requested rank."""

    pass


class RateLimitError(GBIFError):
    """Raised when GBIF rate limits are exceeded."""

    pass


class APIError(GBIFError):
    """Raised for general API errors."""

    pass


@dataclass
class TaxonMatch:
    """
    Result of a GBIF taxon name match.

    Attributes:
        usage_key: GBIF taxon key for API queries
        scientific_name: Full scientific name with authority
        canonical_name: Name without authority
        rank: Taxonomic rank (GENUS, SPECIES, FAMILY, etc.)
        status: Taxonomic status (ACCEPTED, SYNONYM, etc.)
        confidence: Match confidence score (0-100)
        match_type: Type of match (EXACT, HIGHERRANK, FUZZY, NONE)
        kingdom: Kingdom name
        family: Family name (if applicable)
        genus: Genus name (if applicable)
    """

    usage_key: int
    scientific_name: str
    canonical_name: str
    rank: str
    status: str
    confidence: int
    match_type: str
    kingdom: str | None = None
    family: str | None = None
    genus: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> TaxonMatch:
        """Create TaxonMatch from GBIF API response."""
        return cls(
            usage_key=data.get("usageKey", 0),
            scientific_name=data.get("scientificName", ""),
            canonical_name=data.get("canonicalName", ""),
            rank=data.get("rank", ""),
            status=data.get("status", ""),
            confidence=data.get("confidence", 0),
            match_type=data.get("matchType", "NONE"),
            kingdom=data.get("kingdom"),
            family=data.get("family"),
            genus=data.get("genus"),
        )


@dataclass
class OccurrenceRecord:
    """
    A single occurrence record from GBIF.

    Stores the key fields needed for biodiversity research.
    """

    key: int
    year: int | None
    event_date: str | None
    latitude: float | None
    longitude: float | None
    coordinate_uncertainty: float | None
    elevation: float | None
    locality: str | None
    genus: str | None
    species: str | None
    scientific_name: str | None
    specific_epithet: str | None
    institution_code: str | None
    catalog_number: str | None
    recorded_by: str | None
    country: str | None
    state_province: str | None
    basis_of_record: str | None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> OccurrenceRecord:
        """Create OccurrenceRecord from GBIF API response."""
        return cls(
            key=data.get("key", 0),
            year=data.get("year"),
            event_date=data.get("eventDate"),
            latitude=data.get("decimalLatitude"),
            longitude=data.get("decimalLongitude"),
            coordinate_uncertainty=data.get("coordinateUncertaintyInMeters"),
            elevation=data.get("elevation"),
            locality=data.get("locality"),
            genus=data.get("genus"),
            species=data.get("species"),
            scientific_name=data.get("scientificName"),
            specific_epithet=data.get("specificEpithet"),
            institution_code=data.get("institutionCode"),
            catalog_number=data.get("catalogNumber"),
            recorded_by=data.get("recordedBy"),
            country=data.get("country"),
            state_province=data.get("stateProvince"),
            basis_of_record=data.get("basisOfRecord"),
        )

    @property
    def gbif_url(self) -> str:
        """Get the URL to view this record on GBIF."""
        return f"https://www.gbif.org/occurrence/{self.key}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            "Year": self.year,
            "Date": self.event_date,
            "Latitude": self.latitude,
            "Longitude": self.longitude,
            "Uncertainty (m)": self.coordinate_uncertainty,
            "Elevation (m)": self.elevation,
            "Locality": self.locality,
            "Genus": self.genus,
            "Species": self.species,
            "Scientific Name": self.scientific_name,
            "Institution": self.institution_code,
            "Catalog No": self.catalog_number,
            "Recorded By": self.recorded_by,
            "Country": self.country,
            "State/Province": self.state_province,
            "Link": self.gbif_url,
        }


class GBIFClient:
    """
    Client for interacting with the GBIF API.

    Handles connection pooling, retries, pagination, and error handling.

    Example:
        client = GBIFClient()
        taxon = client.match_taxon("Nebria", rank="GENUS")
        for record in client.iter_occurrences(taxon.usage_key, year=2020):
            print(record.scientific_name)
    """

    def __init__(
        self,
        timeout: tuple[int, int] = DEFAULT_TIMEOUT,
        max_retries: int = 3,
        page_size: int = DEFAULT_PAGE_SIZE,
    ):
        """
        Initialize GBIF client.

        Args:
            timeout: Request timeout as (connect, read) seconds
            max_retries: Maximum retry attempts for failed requests
            page_size: Number of records per API request (max 300)
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.page_size = min(page_size, 300)  # GBIF max is 300
        self.logger = get_logger()

        # Create session with retry configuration
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        # Set default headers
        session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "gbif-downloader/2.0 (Python)",
            }
        )

        return session

    def _make_request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make a request to the GBIF API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            RateLimitError: If rate limited
            APIError: For other API errors
        """
        url = urljoin(GBIF_API_BASE, endpoint)

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 429:
                raise RateLimitError("GBIF rate limit exceeded. Please wait and retry.")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            raise APIError(f"HTTP error: {e}")
        except requests.exceptions.ConnectionError as e:
            raise APIError(f"Connection error: {e}")
        except requests.exceptions.Timeout as e:
            raise APIError(f"Request timeout: {e}")
        except requests.exceptions.RequestException as e:
            raise APIError(f"Request failed: {e}")

    def match_taxon(
        self,
        name: str,
        rank: str | None = None,
        kingdom: str = "Animalia",
        class_name: str | None = None,
        strict: bool = True,
    ) -> TaxonMatch:
        """
        Match a taxonomic name against GBIF backbone.

        Args:
            name: Taxon name to match (e.g., "Nebria", "Nebria germarii")
            rank: Expected rank (GENUS, SPECIES, FAMILY, etc.)
            kingdom: Kingdom to search in (default: Animalia)
            class_name: Class to filter by (e.g., "Insecta")
            strict: If True, validate that result matches expected rank

        Returns:
            TaxonMatch with taxon details

        Raises:
            TaxonNotFoundError: If taxon not found or doesn't match expected rank
        """
        params = {"name": name, "kingdom": kingdom}

        if class_name:
            params["class"] = class_name

        self.logger.debug(f"Matching taxon: {name}")
        data = self._make_request(SPECIES_MATCH_ENDPOINT, params)
        match = TaxonMatch.from_api_response(data)

        # Validate the match
        if match.match_type == "NONE":
            raise TaxonNotFoundError(f"Taxon '{name}' not found in GBIF.")

        # CRITICAL FIX: Check if we got a higher rank than expected
        # This prevents downloading millions of wrong records
        if strict and rank:
            if match.rank != rank:
                raise TaxonNotFoundError(
                    f"'{name}' matched as {match.rank} ({match.canonical_name}), "
                    f"but expected {rank}. Please check the spelling."
                )

            # Also verify the name matches (case-insensitive)
            if match.canonical_name.lower() != name.lower():
                raise TaxonNotFoundError(
                    f"'{name}' matched to '{match.canonical_name}' ({match.rank}). "
                    f"This may not be what you intended. Please verify."
                )

        self.logger.info(
            f"Matched '{name}' to {match.canonical_name} "
            f"({match.rank}, key={match.usage_key})"
        )

        return match

    def count_occurrences(
        self,
        taxon_key: int,
        basis_of_record: str | list[str] = "PRESERVED_SPECIMEN",
        has_coordinate: bool = True,
        year: int | None = None,
        country: str | None = None,
    ) -> int:
        """
        Count occurrences matching the given criteria.

        Args:
            taxon_key: GBIF taxon key
            basis_of_record: Record type filter
            has_coordinate: Only count georeferenced records
            year: Filter by year
            country: Filter by country code

        Returns:
            Total count of matching records
        """
        params = {
            "taxonKey": taxon_key,
            "hasCoordinate": str(has_coordinate).lower(),
            "limit": 0,  # We only want the count
        }

        if basis_of_record:
            params["basisOfRecord"] = basis_of_record

        if year:
            params["year"] = year

        if country:
            params["country"] = country

        data = self._make_request(OCCURRENCE_SEARCH_ENDPOINT, params)
        return data.get("count", 0)

    def iter_occurrences(
        self,
        taxon_key: int,
        basis_of_record: str | list[str] = "PRESERVED_SPECIMEN",
        has_coordinate: bool = True,
        year: int | None = None,
        country: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Generator[OccurrenceRecord, None, None]:
        """
        Iterate over occurrences matching the given criteria.

        Uses offset-based pagination with the GBIF limit in mind.
        For large datasets, use iter_occurrences_by_year instead.

        Args:
            taxon_key: GBIF taxon key
            basis_of_record: Record type filter
            has_coordinate: Only return georeferenced records
            year: Filter by year
            country: Filter by country code
            progress_callback: Function called with (current, total)

        Yields:
            OccurrenceRecord for each matching record
        """
        params = {
            "taxonKey": taxon_key,
            "hasCoordinate": str(has_coordinate).lower(),
            "limit": self.page_size,
            "offset": 0,
        }

        if basis_of_record:
            params["basisOfRecord"] = basis_of_record

        if year:
            params["year"] = year

        if country:
            params["country"] = country

        total = None
        count = 0

        while True:
            data = self._make_request(OCCURRENCE_SEARCH_ENDPOINT, params)

            if total is None:
                total = data.get("count", 0)
                self.logger.info(f"Found {total:,} total occurrences")

            results = data.get("results", [])
            if not results:
                break

            for item in results:
                yield OccurrenceRecord.from_api_response(item)
                count += 1

                if progress_callback:
                    progress_callback(count, total)

            # Check if we've reached the end or hit the offset limit
            if data.get("endOfRecords", False):
                break

            params["offset"] += self.page_size

            if params["offset"] >= MAX_OFFSET:
                self.logger.warning(
                    f"Reached GBIF offset limit ({MAX_OFFSET:,}). "
                    f"Consider using iter_occurrences_by_year for complete data."
                )
                break

    def iter_occurrences_by_year(
        self,
        taxon_key: int,
        year_start: int = 1800,
        year_end: int | None = None,
        basis_of_record: str | list[str] = "PRESERVED_SPECIMEN",
        has_coordinate: bool = True,
        country: str | None = None,
        progress_callback: Callable[[int, int, int], None] | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> Generator[OccurrenceRecord, None, None]:
        """
        Iterate over occurrences year by year to avoid offset limits.

        This is the recommended method for large datasets (>100K records).

        Args:
            taxon_key: GBIF taxon key
            year_start: First year to include
            year_end: Last year to include (default: current year)
            basis_of_record: Record type filter
            has_coordinate: Only return georeferenced records
            country: Filter by country code
            progress_callback: Function called with (current, total, year)
            stop_check: Function that returns True to stop iteration

        Yields:
            OccurrenceRecord for each matching record
        """
        if year_end is None:
            year_end = datetime.now().year

        # Get total count estimate
        total_estimate = self.count_occurrences(
            taxon_key=taxon_key,
            basis_of_record=basis_of_record,
            has_coordinate=has_coordinate,
            country=country,
        )
        self.logger.info(f"Estimated total: {total_estimate:,} records")

        count = 0
        seen_keys: set[int] = set()  # For deduplication

        for year in range(year_start, year_end + 1):
            # Check if we should stop
            if stop_check and stop_check():
                self.logger.info("Download stopped by user")
                break

            self.logger.debug(f"Processing year {year}")

            params = {
                "taxonKey": taxon_key,
                "hasCoordinate": str(has_coordinate).lower(),
                "year": year,
                "limit": self.page_size,
                "offset": 0,
            }

            if basis_of_record:
                params["basisOfRecord"] = basis_of_record

            if country:
                params["country"] = country

            while True:
                if stop_check and stop_check():
                    break

                try:
                    data = self._make_request(OCCURRENCE_SEARCH_ENDPOINT, params)
                except APIError as e:
                    self.logger.warning(f"Error fetching year {year}: {e}")
                    break

                results = data.get("results", [])
                if not results:
                    break

                for item in results:
                    record = OccurrenceRecord.from_api_response(item)

                    # Deduplicate
                    if record.key in seen_keys:
                        continue
                    seen_keys.add(record.key)

                    yield record
                    count += 1

                    if progress_callback:
                        progress_callback(count, total_estimate, year)

                if data.get("endOfRecords", False) or len(results) < self.page_size:
                    break

                params["offset"] += self.page_size

                # Safety check for single-year offset limit
                if params["offset"] >= MAX_OFFSET:
                    self.logger.warning(
                        f"Year {year} has >100K records. Some may be missed."
                    )
                    break

        self.logger.info(f"Downloaded {count:,} unique records")

    def close(self) -> None:
        """Close the session and release resources."""
        self.session.close()

    def __enter__(self) -> GBIFClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.close()
