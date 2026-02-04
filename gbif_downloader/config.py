"""
Configuration management for GBIF Downloader.

Supports loading and saving filter presets from YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from gbif_downloader.filters import FilterConfig
from gbif_downloader.utils import get_logger


class Config:
    """
    Configuration manager for GBIF Downloader.

    Handles loading and saving filter configurations from YAML files.

    Example:
        # Load from file
        config = Config.load("my_search.yaml")
        filter_config = config.get_filter_config()

        # Save to file
        config = Config(filter_config=filter_config, output_format="excel")
        config.save("my_search.yaml")
    """

    def __init__(
        self,
        filter_config: FilterConfig | None = None,
        output_format: str = "excel",
        output_path: str | None = None,
        highlight_uncertain: bool = True,
    ):
        """
        Initialize configuration.

        Args:
            filter_config: FilterConfig instance
            output_format: Output format (excel, csv, geojson)
            output_path: Default output file path
            highlight_uncertain: Highlight uncertain records in Excel
        """
        self.filter_config = filter_config
        self.output_format = output_format
        self.output_path = output_path
        self.highlight_uncertain = highlight_uncertain
        self.logger = get_logger()

    @classmethod
    def load(cls, path: str | Path) -> Config:
        """
        Load configuration from a YAML file.

        Args:
            path: Path to YAML file

        Returns:
            Config instance

        Raises:
            FileNotFoundError: If file doesn't exist
            yaml.YAMLError: If file is invalid YAML
        """
        path = Path(path)

        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty config file: {path}")

        # Parse filter config
        filter_config = FilterConfig.from_dict(data)

        # Parse output settings
        output = data.get("output", {})

        return cls(
            filter_config=filter_config,
            output_format=output.get("format", "excel"),
            output_path=output.get("filename"),
            highlight_uncertain=output.get("highlight_uncertain", True),
        )

    def save(self, path: str | Path) -> None:
        """
        Save configuration to a YAML file.

        Args:
            path: Path to save to
        """
        path = Path(path)

        if self.filter_config is None:
            raise ValueError("No filter configuration to save")

        data = self.filter_config.to_dict()

        # Add output settings
        data["output"] = {
            "format": self.output_format,
            "highlight_uncertain": self.highlight_uncertain,
        }

        if self.output_path:
            data["output"]["filename"] = self.output_path

        # Ensure directory exists
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        self.logger.info(f"Configuration saved to: {path}")

    def get_filter_config(self) -> FilterConfig:
        """
        Get the filter configuration.

        Returns:
            FilterConfig instance

        Raises:
            ValueError: If no filter config is set
        """
        if self.filter_config is None:
            raise ValueError("No filter configuration set")
        return self.filter_config

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {}

        if self.filter_config:
            result.update(self.filter_config.to_dict())

        result["output"] = {
            "format": self.output_format,
            "highlight_uncertain": self.highlight_uncertain,
        }

        if self.output_path:
            result["output"]["filename"] = self.output_path

        return result


# Default config directory
DEFAULT_CONFIG_DIR = Path.home() / ".gbif_downloader"


def get_config_dir() -> Path:
    """
    Get the configuration directory, creating it if needed.

    Returns:
        Path to config directory
    """
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return DEFAULT_CONFIG_DIR


def list_presets() -> list[str]:
    """
    List available preset configurations.

    Returns:
        List of preset names (without .yaml extension)
    """
    config_dir = get_config_dir()
    presets = []

    for path in config_dir.glob("*.yaml"):
        presets.append(path.stem)

    return sorted(presets)


def load_preset(name: str) -> Config:
    """
    Load a preset configuration by name.

    Args:
        name: Preset name (without .yaml extension)

    Returns:
        Config instance

    Raises:
        FileNotFoundError: If preset doesn't exist
    """
    config_dir = get_config_dir()
    path = config_dir / f"{name}.yaml"
    return Config.load(path)


def save_preset(name: str, config: Config) -> Path:
    """
    Save a configuration as a preset.

    Args:
        name: Preset name (without .yaml extension)
        config: Config instance to save

    Returns:
        Path to saved file
    """
    config_dir = get_config_dir()
    path = config_dir / f"{name}.yaml"
    config.save(path)
    return path


def delete_preset(name: str) -> bool:
    """
    Delete a preset configuration.

    Args:
        name: Preset name (without .yaml extension)

    Returns:
        True if deleted, False if not found
    """
    config_dir = get_config_dir()
    path = config_dir / f"{name}.yaml"

    if path.exists():
        path.unlink()
        return True

    return False


# Example configuration template
EXAMPLE_CONFIG = """# GBIF Downloader Configuration
# Save this file and use with: gbif-download --config my_search.yaml

taxonomy:
  genus: Nebria
  # Uncomment to filter specific species:
  # species:
  #   - germarii
  #   - castanea
  # Or search by family instead:
  # family: Carabidae

filters:
  year_start: 1900
  year_end: 2024
  uncertainty_max: 1000
  require_year: true
  require_elevation: false
  keep_unknown_uncertainty: true
  # Uncomment to filter by country (ISO codes):
  # countries:
  #   - IT
  #   - CH
  #   - AT
  # Uncomment to filter by institution:
  # institutions:
  #   - MZUF
  #   - NHMW

output:
  format: excel  # excel, csv, or geojson
  filename: nebria_data.xlsx
  highlight_uncertain: true
"""


def create_example_config(path: str | Path | None = None) -> Path:
    """
    Create an example configuration file.

    Args:
        path: Where to save (default: config_dir/example.yaml)

    Returns:
        Path to created file
    """
    if path is None:
        path = get_config_dir() / "example.yaml"
    else:
        path = Path(path)

    with open(path, "w", encoding="utf-8") as f:
        f.write(EXAMPLE_CONFIG)

    return path
