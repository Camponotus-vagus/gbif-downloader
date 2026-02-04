"""
Command-line interface for GBIF Downloader.

Usage:
    gbif-download --genus Nebria --output nebria_data.xlsx
    gbif-download --genus Nebria --species germarii,castanea --format geojson
    gbif-download --config my_search.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from gbif_downloader import __version__
from gbif_downloader.api import GBIFClient, GBIFError, TaxonNotFoundError
from gbif_downloader.filters import FilterConfig, RecordFilter, format_filter_stats
from gbif_downloader.config import Config, create_example_config, list_presets
from gbif_downloader.exporters import get_exporter
from gbif_downloader.utils import setup_logging, sanitize_filename

console = Console()


def print_banner():
    """Print the application banner."""
    console.print(
        "\n[bold blue]GBIF Downloader[/bold blue] "
        f"[dim]v{__version__}[/dim]",
    )
    console.print(
        "[dim]Download biodiversity occurrence data from GBIF[/dim]\n"
    )


@click.group(invoke_without_command=True)
@click.option(
    "--genus", "-g",
    help="Genus name to search (e.g., Nebria)",
)
@click.option(
    "--species", "-s",
    help="Species epithets, comma-separated (e.g., germarii,castanea)",
)
@click.option(
    "--family", "-f",
    help="Family name for broader search (e.g., Carabidae)",
)
@click.option(
    "--year-start", "-y",
    type=int,
    default=1800,
    help="Start year for records (default: 1800)",
)
@click.option(
    "--year-end",
    type=int,
    help="End year for records (default: current year)",
)
@click.option(
    "--uncertainty-max", "-u",
    type=int,
    default=1000,
    help="Maximum coordinate uncertainty in meters (default: 1000)",
)
@click.option(
    "--country", "-c",
    help="Country codes, comma-separated (e.g., IT,CH,AT)",
)
@click.option(
    "--require-year/--no-require-year",
    default=True,
    help="Require year field (default: yes)",
)
@click.option(
    "--require-elevation/--no-require-elevation",
    default=True,
    help="Require elevation field (default: yes)",
)
@click.option(
    "--keep-unknown-uncertainty/--drop-unknown-uncertainty",
    default=True,
    help="Keep records with unknown uncertainty (default: yes)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["excel", "csv", "geojson"]),
    default="excel",
    help="Output format (default: excel)",
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Output file path",
)
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True),
    help="Load settings from YAML config file",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--version",
    is_flag=True,
    help="Show version and exit",
)
@click.pass_context
def main(
    ctx,
    genus,
    species,
    family,
    year_start,
    year_end,
    uncertainty_max,
    country,
    require_year,
    require_elevation,
    keep_unknown_uncertainty,
    output_format,
    output,
    config_file,
    verbose,
    version,
):
    """
    Download and filter GBIF biodiversity occurrence data.

    Examples:

    \b
    # Download all Nebria specimens
    gbif-download --genus Nebria --output nebria_data.xlsx

    \b
    # Download specific species as GeoJSON
    gbif-download --genus Nebria --species germarii,castanea --format geojson -o nebria.geojson

    \b
    # Use a config file
    gbif-download --config my_search.yaml

    \b
    # Filter by country and year
    gbif-download --genus Nebria --country IT,CH --year-start 1900 -o alpine_nebria.xlsx
    """
    if version:
        console.print(f"gbif-downloader version {__version__}")
        sys.exit(0)

    # If no subcommand and no genus/family/config, show help
    if ctx.invoked_subcommand is None:
        if not genus and not family and not config_file:
            click.echo(ctx.get_help())
            sys.exit(0)

    # Setup logging
    setup_logging(verbose=verbose)

    print_banner()

    # Load config from file if provided
    if config_file:
        try:
            config = Config.load(config_file)
            filter_config = config.get_filter_config()
            output_format = config.output_format
            if not output and config.output_path:
                output = config.output_path
            console.print(f"[green]Loaded config from: {config_file}[/green]\n")
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            sys.exit(1)
    else:
        # Build filter config from CLI options
        if not genus and not family:
            console.print("[red]Error: Either --genus or --family is required[/red]")
            sys.exit(1)

        try:
            filter_config = FilterConfig(
                genus=genus,
                species_list=species.split(",") if species else [],
                family=family,
                year_start=year_start,
                year_end=year_end,
                uncertainty_max=uncertainty_max,
                require_year=require_year,
                require_elevation=require_elevation,
                keep_unknown_uncertainty=keep_unknown_uncertainty,
                countries=country.split(",") if country else [],
            )
        except ValueError as e:
            console.print(f"[red]Configuration error: {e}[/red]")
            sys.exit(1)

    # Determine output path
    if not output:
        taxon_name = filter_config.genus or filter_config.family
        safe_name = sanitize_filename(taxon_name)
        ext = {"excel": ".xlsx", "csv": ".csv", "geojson": ".geojson"}[output_format]
        output = f"{safe_name}_GBIF{ext}"

    # Run the download
    run_download(filter_config, output_format, output, verbose)


def run_download(
    filter_config: FilterConfig,
    output_format: str,
    output_path: str,
    verbose: bool = False,
):
    """
    Run the download process.

    Args:
        filter_config: Filter configuration
        output_format: Output format
        output_path: Output file path
        verbose: Enable verbose output
    """
    # Show configuration
    show_config(filter_config)

    # Initialize client and filter
    client = GBIFClient()
    record_filter = RecordFilter(filter_config)

    try:
        # Match taxon
        with console.status("[bold blue]Matching taxon..."):
            taxon_name = filter_config.genus or filter_config.family
            rank = "GENUS" if filter_config.genus else "FAMILY"

            try:
                taxon = client.match_taxon(taxon_name, rank=rank)
            except TaxonNotFoundError as e:
                console.print(f"\n[red]Error: {e}[/red]")
                sys.exit(1)

        console.print(
            f"[green]Matched:[/green] {taxon.canonical_name} "
            f"({taxon.rank}, key={taxon.usage_key})\n"
        )

        # Count total records
        with console.status("[bold blue]Counting records..."):
            total_count = client.count_occurrences(taxon.usage_key)

        console.print(f"[blue]Total records on GBIF:[/blue] {total_count:,}\n")

        if total_count == 0:
            console.print("[yellow]No records found matching the criteria.[/yellow]")
            sys.exit(0)

        # Download with progress
        filtered_records = []
        stats = {
            "total": 0,
            "kept": 0,
            "filtered": 0,
        }

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "[cyan]Downloading...",
                total=total_count,
            )

            def progress_callback(current: int, total: int, year: int):
                progress.update(
                    task,
                    completed=current,
                    description=f"[cyan]Year {year}...",
                )

            for record in client.iter_occurrences_by_year(
                taxon.usage_key,
                year_start=filter_config.year_start,
                year_end=filter_config.year_end,
                progress_callback=progress_callback,
            ):
                stats["total"] += 1
                result = record_filter.apply(record)

                if result.keep:
                    filtered_records.append(record)
                    stats["kept"] += 1
                else:
                    stats["filtered"] += 1

        console.print()

        # Show results
        console.print(f"[green]Records downloaded:[/green] {stats['total']:,}")
        console.print(f"[green]Records kept after filtering:[/green] {stats['kept']:,}")
        console.print(f"[dim]Records filtered out:[/dim] {stats['filtered']:,}\n")

        if not filtered_records:
            console.print("[yellow]No records passed the filters.[/yellow]")
            sys.exit(0)

        # Export
        with console.status(f"[bold blue]Exporting to {output_format}..."):
            exporter_class = get_exporter(output_format)
            exporter = exporter_class()
            output_file = exporter.export(filtered_records, output_path)

        console.print(f"\n[bold green]Success![/bold green] Saved to: {output_file}")
        console.print(f"[dim]Total records: {len(filtered_records):,}[/dim]")

    except GBIFError as e:
        console.print(f"\n[red]GBIF API error: {e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Download interrupted by user.[/yellow]")
        sys.exit(130)
    finally:
        client.close()


def show_config(config: FilterConfig):
    """Display the current configuration."""
    table = Table(title="Search Configuration", show_header=False)
    table.add_column("Setting", style="cyan")
    table.add_column("Value")

    if config.genus:
        table.add_row("Genus", config.genus)
    if config.family:
        table.add_row("Family", config.family)
    if config.species_list:
        table.add_row("Species", ", ".join(config.species_list))
    table.add_row("Year range", f"{config.year_start} - {config.year_end}")
    table.add_row("Max uncertainty", f"{config.uncertainty_max}m")
    table.add_row("Require year", "Yes" if config.require_year else "No")
    table.add_row("Require elevation", "Yes" if config.require_elevation else "No")
    table.add_row(
        "Keep unknown uncertainty",
        "Yes" if config.keep_unknown_uncertainty else "No",
    )
    if config.countries:
        table.add_row("Countries", ", ".join(config.countries))

    console.print(table)
    console.print()


@main.command()
@click.argument("path", type=click.Path(), default="example_config.yaml")
def init(path):
    """Create an example configuration file."""
    print_banner()

    output_path = create_example_config(path)
    console.print(f"[green]Created example config:[/green] {output_path}")
    console.print("[dim]Edit this file and use with: gbif-download --config example_config.yaml[/dim]")


@main.command()
def presets():
    """List available preset configurations."""
    print_banner()

    preset_list = list_presets()

    if not preset_list:
        console.print("[yellow]No presets found.[/yellow]")
        console.print("[dim]Create one with: gbif-download init my_preset.yaml[/dim]")
        return

    console.print("[bold]Available presets:[/bold]\n")
    for preset in preset_list:
        console.print(f"  - {preset}")

    console.print("\n[dim]Use with: gbif-download --config ~/.gbif_downloader/PRESET.yaml[/dim]")


if __name__ == "__main__":
    main()
