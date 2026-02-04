"""
CSV exporter for GBIF occurrence data.

Simple, universal export format compatible with any spreadsheet
software or data processing tool.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from gbif_downloader.api import OccurrenceRecord
from gbif_downloader.utils import get_logger


class CSVExporter:
    """
    Export occurrence records to CSV format.

    Features:
    - UTF-8 encoding
    - Standard comma delimiter
    - Quoted strings for safety

    Example:
        exporter = CSVExporter()
        exporter.export(records, "output.csv")
    """

    def __init__(self, delimiter: str = ",", encoding: str = "utf-8"):
        """
        Initialize the exporter.

        Args:
            delimiter: Field delimiter (default: comma)
            encoding: Output file encoding (default: utf-8)
        """
        self.delimiter = delimiter
        self.encoding = encoding
        self.logger = get_logger()

    def export(
        self,
        records: list[OccurrenceRecord],
        output_path: str | Path,
        **kwargs,  # Accept extra args for compatibility
    ) -> Path:
        """
        Export records to CSV file.

        Args:
            records: List of OccurrenceRecord objects
            output_path: Output file path

        Returns:
            Path to the created file
        """
        output_path = Path(output_path)

        # Ensure .csv extension
        if output_path.suffix.lower() != ".csv":
            output_path = output_path.with_suffix(".csv")

        self.logger.info(f"Exporting {len(records):,} records to CSV...")

        # Convert records to dictionaries
        data = [record.to_dict() for record in records]
        df = pd.DataFrame(data)

        # Export to CSV
        df.to_csv(
            output_path,
            index=False,
            encoding=self.encoding,
            sep=self.delimiter,
            quoting=csv.QUOTE_NONNUMERIC,
        )

        self.logger.info(f"CSV file saved: {output_path}")
        return output_path

    def export_streaming(
        self,
        records_iter,
        output_path: str | Path,
        fieldnames: list[str] | None = None,
    ) -> Path:
        """
        Export records in streaming mode (for large datasets).

        This method writes records one at a time, reducing memory usage
        for very large datasets.

        Args:
            records_iter: Iterator of OccurrenceRecord objects
            output_path: Output file path
            fieldnames: Column names (auto-detected from first record if None)

        Returns:
            Path to the created file
        """
        output_path = Path(output_path)

        if output_path.suffix.lower() != ".csv":
            output_path = output_path.with_suffix(".csv")

        self.logger.info("Starting streaming CSV export...")

        count = 0
        writer = None

        with open(output_path, "w", newline="", encoding=self.encoding) as f:
            for record in records_iter:
                data = record.to_dict()

                # Initialize writer with fieldnames from first record
                if writer is None:
                    if fieldnames is None:
                        fieldnames = list(data.keys())
                    writer = csv.DictWriter(
                        f,
                        fieldnames=fieldnames,
                        delimiter=self.delimiter,
                        quoting=csv.QUOTE_NONNUMERIC,
                    )
                    writer.writeheader()

                writer.writerow(data)
                count += 1

                if count % 10000 == 0:
                    self.logger.debug(f"Written {count:,} records...")

        self.logger.info(f"CSV file saved: {output_path} ({count:,} records)")
        return output_path

    @staticmethod
    def is_available() -> bool:
        """CSV export is always available."""
        return True
