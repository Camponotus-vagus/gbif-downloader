"""
GeoJSON exporter for GBIF occurrence data.

Exports occurrence records as GeoJSON FeatureCollection, suitable for:
- QGIS
- ArcGIS
- Leaflet/Mapbox web maps
- Any GIS software
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gbif_downloader.api import OccurrenceRecord
from gbif_downloader.utils import get_logger

# Try to import geojson library for validation
try:
    import geojson
    from geojson import Feature, FeatureCollection, Point

    HAS_GEOJSON = True
except ImportError:
    HAS_GEOJSON = False


class GeoJSONExporter:
    """
    Export occurrence records to GeoJSON format.

    Creates a FeatureCollection with Point geometry for each record.
    Records without coordinates are skipped.

    Example:
        exporter = GeoJSONExporter()
        exporter.export(records, "output.geojson")

    The output can be directly loaded into QGIS, ArcGIS, or web mapping
    libraries like Leaflet.
    """

    def __init__(self, include_all_properties: bool = True):
        """
        Initialize the exporter.

        Args:
            include_all_properties: Include all record fields in properties
        """
        self.include_all_properties = include_all_properties
        self.logger = get_logger()

    def export(
        self,
        records: list[OccurrenceRecord],
        output_path: str | Path,
        **kwargs,  # Accept extra args for compatibility
    ) -> Path:
        """
        Export records to GeoJSON file.

        Args:
            records: List of OccurrenceRecord objects
            output_path: Output file path

        Returns:
            Path to the created file
        """
        output_path = Path(output_path)

        # Ensure .geojson extension
        if output_path.suffix.lower() not in (".geojson", ".json"):
            output_path = output_path.with_suffix(".geojson")

        self.logger.info(f"Exporting {len(records):,} records to GeoJSON...")

        if HAS_GEOJSON:
            feature_collection = self._create_feature_collection_geojson(records)
            geojson_str = geojson.dumps(feature_collection, indent=2)
        else:
            feature_collection = self._create_feature_collection_manual(records)
            geojson_str = json.dumps(feature_collection, indent=2)

        # Write to file
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(geojson_str)

        self.logger.info(f"GeoJSON file saved: {output_path}")
        return output_path

    def _create_feature_collection_geojson(
        self, records: list[OccurrenceRecord]
    ) -> "FeatureCollection":
        """
        Create FeatureCollection using geojson library.

        Args:
            records: List of OccurrenceRecord objects

        Returns:
            GeoJSON FeatureCollection
        """
        features = []
        skipped = 0

        for record in records:
            # Skip records without coordinates
            if record.latitude is None or record.longitude is None:
                skipped += 1
                continue

            # Create point geometry
            point = Point((record.longitude, record.latitude))

            # Create properties
            properties = self._get_properties(record)

            # Create feature
            feature = Feature(
                geometry=point,
                properties=properties,
                id=str(record.key),
            )
            features.append(feature)

        if skipped > 0:
            self.logger.warning(
                f"Skipped {skipped} records without coordinates"
            )

        return FeatureCollection(features)

    def _create_feature_collection_manual(
        self, records: list[OccurrenceRecord]
    ) -> dict[str, Any]:
        """
        Create FeatureCollection manually (without geojson library).

        Args:
            records: List of OccurrenceRecord objects

        Returns:
            GeoJSON FeatureCollection as dictionary
        """
        features = []
        skipped = 0

        for record in records:
            # Skip records without coordinates
            if record.latitude is None or record.longitude is None:
                skipped += 1
                continue

            # Create feature
            feature = {
                "type": "Feature",
                "id": str(record.key),
                "geometry": {
                    "type": "Point",
                    "coordinates": [record.longitude, record.latitude],
                },
                "properties": self._get_properties(record),
            }
            features.append(feature)

        if skipped > 0:
            self.logger.warning(
                f"Skipped {skipped} records without coordinates"
            )

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    def _get_properties(self, record: OccurrenceRecord) -> dict[str, Any]:
        """
        Get properties dictionary for a record.

        Args:
            record: OccurrenceRecord

        Returns:
            Properties dictionary
        """
        if self.include_all_properties:
            # Include all fields except coordinates (they're in geometry)
            props = record.to_dict()
            # Remove coordinate fields to avoid duplication
            props.pop("Latitude", None)
            props.pop("Longitude", None)
            return props
        else:
            # Minimal properties
            return {
                "scientific_name": record.scientific_name,
                "year": record.year,
                "institution": record.institution_code,
                "gbif_url": record.gbif_url,
            }

    @staticmethod
    def is_available() -> bool:
        """
        Check if GeoJSON export is available.

        Note: Even without the geojson library, we can still export
        using manual JSON construction.
        """
        return True  # Always available, just with/without validation
