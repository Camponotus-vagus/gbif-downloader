# GBIF Downloader

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Download and filter biodiversity occurrence data from [GBIF](https://www.gbif.org/) (Global Biodiversity Information Facility) with both CLI and GUI interfaces.

## Features

- **Smart Filtering**: Filter by taxonomy, year range, coordinate uncertainty, elevation, country
- **Multiple Export Formats**: Excel (with highlighting), CSV, GeoJSON (for GIS software)
- **Robust API Handling**: Automatic retries, rate limit handling, pagination
- **Dual Interface**: Command-line for scripting, GUI for interactive use
- **Configuration Files**: Save and reuse your filter settings
- **Cross-Platform**: Works on Windows, macOS (Intel & Apple Silicon), and Linux
- **No Python Required**: Standalone executables available for all platforms

## Installation

### Option 1: Download Standalone Executable (No Python Required)

Download the latest release for your platform from the [Releases page](https://github.com/Camponotus-vagus/gbif-downloader/releases):

| Platform | CLI | GUI |
|----------|-----|-----|
| **Windows** | `gbif-download-windows.exe` | `gbif-gui-windows.exe` |
| **Linux** | `gbif-download-linux` | `gbif-gui-linux` |
| **macOS Intel** | `gbif-download-macos-intel` | `gbif-gui-macos-intel` |
| **macOS Apple Silicon (M1/M2/M3)** | `gbif-download-macos-arm64` | `gbif-gui-macos-arm64` |

#### Windows
Just download and double-click the `.exe` file, or run from Command Prompt:
```cmd
gbif-download-windows.exe --genus Nebria --output nebria.xlsx
```

#### macOS
After downloading, you may need to allow the app to run:
```bash
# Remove quarantine attribute
xattr -d com.apple.quarantine ./gbif-download-macos-*

# Make executable
chmod +x ./gbif-download-macos-*

# Run
./gbif-download-macos-arm64 --genus Nebria --output nebria.xlsx
```

Or go to **System Preferences → Security & Privacy → General** and click **"Open Anyway"**.

#### Linux
```bash
chmod +x ./gbif-download-linux
./gbif-download-linux --genus Nebria --output nebria.xlsx
```

### Option 2: Install with pip

```bash
pip install gbif-downloader
```

### Option 3: Install from Source

```bash
git clone https://github.com/Camponotus-vagus/gbif-downloader.git
cd gbif-downloader
pip install -e .
```

### Dependencies (only for pip install)

- Python 3.9+
- requests
- pandas
- openpyxl (for Excel export)
- click (for CLI)
- rich (for CLI progress bars)
- PyYAML (for config files)
- geojson (for GeoJSON export)

## Quick Start

### Command Line

```bash
# Download all Nebria specimens to Excel
gbif-download --genus Nebria --output nebria_data.xlsx

# Download specific species as GeoJSON (for QGIS)
gbif-download --genus Nebria --species germarii,castanea --format geojson -o nebria.geojson

# Filter by country and year range
gbif-download --genus Nebria --country IT,CH,AT --year-start 1900 -o alpine_nebria.xlsx

# Use a configuration file
gbif-download --config my_search.yaml
```

### Graphical Interface

```bash
gbif-gui
```

Or launch from Python:

```python
from gbif_downloader.gui import main
main()
```

### Python API

```python
from gbif_downloader import GBIFClient, FilterConfig, RecordFilter
from gbif_downloader.exporters import ExcelExporter

# Configure the search
config = FilterConfig(
    genus="Nebria",
    species_list=["germarii", "castanea"],
    year_start=1900,
    uncertainty_max=1000,
    require_elevation=True,
)

# Download data
client = GBIFClient()
taxon = client.match_taxon("Nebria", rank="GENUS")

# Filter and collect records
record_filter = RecordFilter(config)
filtered_records = []

for record in client.iter_occurrences_by_year(taxon.usage_key, year_start=1900):
    result = record_filter.apply(record)
    if result.keep:
        filtered_records.append(record)

# Export to Excel
exporter = ExcelExporter()
exporter.export(filtered_records, "nebria_data.xlsx")

client.close()
```

## CLI Reference

```
Usage: gbif-download [OPTIONS]

Options:
  -g, --genus TEXT              Genus name to search
  -s, --species TEXT            Species epithets, comma-separated
  -f, --family TEXT             Family name for broader search
  -y, --year-start INTEGER      Start year (default: 1800)
  --year-end INTEGER            End year (default: current year)
  -u, --uncertainty-max INTEGER Max coordinate uncertainty in meters (default: 1000)
  -c, --country TEXT            Country codes, comma-separated (e.g., IT,CH,AT)
  --require-year / --no-require-year
                                Require year field (default: yes)
  --require-elevation / --no-require-elevation
                                Require elevation field (default: yes)
  --keep-unknown-uncertainty / --drop-unknown-uncertainty
                                Keep records with unknown uncertainty (default: yes)
  --format [excel|csv|geojson]  Output format (default: excel)
  -o, --output PATH             Output file path
  --config PATH                 Load settings from YAML config file
  -v, --verbose                 Enable verbose output
  --version                     Show version and exit
  --help                        Show this message and exit

Commands:
  init     Create an example configuration file
  presets  List available preset configurations
```

## Configuration File

Create a YAML configuration file for reusable searches:

```yaml
# my_search.yaml
taxonomy:
  genus: Nebria
  species:
    - germarii
    - castanea

filters:
  year_start: 1900
  year_end: 2024
  uncertainty_max: 1000
  require_year: true
  require_elevation: false
  keep_unknown_uncertainty: true
  countries:
    - IT
    - CH
    - AT

output:
  format: excel
  filename: alpine_nebria.xlsx
  highlight_uncertain: true
```

Then use it:

```bash
gbif-download --config my_search.yaml
```

## Export Formats

### Excel (.xlsx)

- Conditional formatting: yellow highlighting for records with unknown coordinate uncertainty
- Auto-adjusted column widths
- Frozen header row
- Clickable GBIF links

### CSV (.csv)

- Standard comma-separated format
- UTF-8 encoding
- Compatible with any spreadsheet software

### GeoJSON (.geojson)

- Point geometry for each record
- All record attributes as properties
- Direct import into QGIS, ArcGIS, Leaflet, Mapbox

## Filter Options Explained

| Option | Description |
|--------|-------------|
| `require_year` | Exclude records without collection year |
| `require_elevation` | Exclude records without elevation data |
| `uncertainty_max` | Maximum acceptable coordinate uncertainty in meters |
| `keep_unknown_uncertainty` | Keep records where uncertainty is not reported (common in museum data) |
| `countries` | ISO country codes to filter by (e.g., IT, CH, AT) |

## Why Use This Instead of GBIF.org?

| Aspect | GBIF Website | GBIF Downloader |
|--------|--------------|-----------------|
| **Speed** | Slow web interface, page reloads | Fast local filtering |
| **Batch Processing** | One search at a time | Script multiple taxa |
| **Unknown Uncertainty** | Can't highlight or handle specially | Yellow highlighting in Excel |
| **GIS Integration** | Must convert manually | Direct GeoJSON export |
| **Reproducibility** | Remember settings manually | Save configs as YAML |
| **Large Downloads** | Timeout issues, email delays | Robust retry logic |
| **No Python Needed** | N/A | Standalone executables! |

### Key Benefits

- **Faster filtering**: Apply complex filters without waiting for GBIF's web interface
- **Batch processing**: Download multiple taxa or run scheduled downloads
- **Custom output**: Get exactly the columns and format you need
- **Scriptable**: Integrate into your research pipeline
- **Offline analysis**: Work with your data locally
- **Uncertainty handling**: The "killer feature" - GBIF has millions of records where uncertainty is NULL. This tool lets you keep them but flag them visually (yellow in Excel)

## Troubleshooting

### "Taxon not found"

- Check spelling of the genus/family name
- Verify the taxon exists on [GBIF](https://www.gbif.org/species/search)
- Try searching at a different taxonomic level

### Rate limiting

The GBIF API may rate limit requests. The tool automatically retries with exponential backoff, but for very large downloads, consider:

- Using year-by-year download (default for large datasets)
- Running during off-peak hours
- Splitting your search into smaller batches

### Missing data

Museum specimens on GBIF vary in data quality. Common issues:

- **No coordinates**: Many historical specimens lack georeferencing
- **No uncertainty**: Coordinate uncertainty often not reported
- **No elevation**: Elevation frequently missing from older records

Use the `keep_unknown_uncertainty` option to include records without uncertainty data (highlighted in yellow in Excel output).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Run tests (`pytest`)
4. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
5. Push to the branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [GBIF](https://www.gbif.org/) for providing free access to biodiversity data
- All the museums and researchers who contribute occurrence data to GBIF

## Citation

If you use this tool in your research, please cite:

```
GBIF Downloader (2024). https://github.com/Camponotus-vagus/gbif-downloader
```

And don't forget to cite GBIF and the data providers for any data you download!
