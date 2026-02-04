"""
Tkinter GUI for GBIF Downloader.

A user-friendly graphical interface for downloading and filtering
GBIF occurrence data.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from tkinter import (
    Tk,
    Label,
    StringVar,
    IntVar,
    BooleanVar,
    messagebox,
    filedialog,
)
from tkinter import ttk

from gbif_downloader import __version__
from gbif_downloader.api import GBIFClient, TaxonNotFoundError, GBIFError
from gbif_downloader.filters import FilterConfig, RecordFilter
from gbif_downloader.exporters import get_exporter
from gbif_downloader.utils import setup_logging, get_logger


class ToolTipButton(ttk.Button):
    """A small help button that shows an info dialog."""

    def __init__(self, parent, title: str, message: str):
        super().__init__(parent, text="?", width=2, command=self.show_message)
        self.title = title
        self.message = message

    def show_message(self):
        messagebox.showinfo(self.title, self.message)


class GBIFDownloaderGUI:
    """
    Main GUI application class.

    Provides a graphical interface for configuring and running
    GBIF occurrence downloads.
    """

    def __init__(self, root: Tk):
        """
        Initialize the GUI.

        Args:
            root: Tk root window
        """
        self.root = root
        self.root.title(f"GBIF Downloader v{__version__}")
        self.root.geometry("800x750")
        self.root.minsize(700, 600)

        # Setup logging
        setup_logging()
        self.logger = get_logger()

        # --- Configuration Variables ---
        # Taxonomy
        self.genus_var = StringVar(value="Nebria")
        self.species_var = StringVar(value="")
        self.family_var = StringVar(value="")

        # Numeric parameters
        self.year_start_var = IntVar(value=1800)
        self.year_end_var = IntVar(value=2024)
        self.uncertainty_var = IntVar(value=1000)

        # Filter options
        self.require_year_var = BooleanVar(value=True)
        self.require_elev_var = BooleanVar(value=True)
        self.keep_unknown_unc_var = BooleanVar(value=True)

        # Country filter
        self.countries_var = StringVar(value="")

        # Output format
        self.format_var = StringVar(value="excel")

        # Status
        self.status_var = StringVar(value="Ready")
        self.progress_var = StringVar(value="Waiting...")
        self.is_downloading = False
        self.stop_event = threading.Event()

        self._create_widgets()

    def _create_widgets(self):
        """Create all GUI widgets."""
        # --- Title ---
        title_frame = ttk.Frame(self.root, padding=10)
        title_frame.pack(fill="x")

        Label(
            title_frame,
            text="GBIF Downloader",
            font=("Segoe UI", 20, "bold"),
        ).pack()
        Label(
            title_frame,
            text="Download and filter biodiversity occurrence data",
            font=("Segoe UI", 10),
            fg="#666",
        ).pack()

        # --- Main Container with Scrollbar ---
        main_container = ttk.Frame(self.root, padding=10)
        main_container.pack(fill="both", expand=True, padx=20)

        # --- 1. Taxonomy Section ---
        tax_frame = ttk.LabelFrame(main_container, text="1. Taxonomy", padding=10)
        tax_frame.pack(fill="x", pady=5)

        self._add_entry_row(
            tax_frame, 0, "Genus:", self.genus_var,
            "The genus to search (e.g., Nebria, Carabus)"
        )
        self._add_entry_row(
            tax_frame, 1, "Species (optional):", self.species_var,
            "Comma-separated species epithets (e.g., germarii, castanea).\n"
            "Leave empty to download entire genus."
        )
        self._add_entry_row(
            tax_frame, 2, "Family (alternative):", self.family_var,
            "Search by family instead of genus.\n"
            "Leave empty if using genus search."
        )

        # --- 2. Temporal & Spatial Parameters ---
        params_frame = ttk.LabelFrame(
            main_container, text="2. Temporal & Spatial Parameters", padding=10
        )
        params_frame.pack(fill="x", pady=5)

        self._add_entry_row(
            params_frame, 0, "Year Start:", self.year_start_var,
            "First year to include (default: 1800)"
        )
        self._add_entry_row(
            params_frame, 1, "Year End:", self.year_end_var,
            "Last year to include (default: current year)"
        )
        self._add_entry_row(
            params_frame, 2, "Max Uncertainty (m):", self.uncertainty_var,
            "Maximum coordinate uncertainty in meters.\n"
            "Records above this value will be excluded.\n"
            "Default: 1000m"
        )
        self._add_entry_row(
            params_frame, 3, "Countries (optional):", self.countries_var,
            "Comma-separated ISO country codes (e.g., IT, CH, AT).\n"
            "Leave empty for all countries."
        )

        # --- 3. Filter Options ---
        filter_frame = ttk.LabelFrame(
            main_container, text="3. Filter Options", padding=10
        )
        filter_frame.pack(fill="x", pady=5)

        self._add_checkbox_row(
            filter_frame, 0, "Exclude records without YEAR", self.require_year_var,
            "If checked, records without collection year will be excluded."
        )
        self._add_checkbox_row(
            filter_frame, 1, "Exclude records without ELEVATION", self.require_elev_var,
            "If checked, records without elevation data will be excluded."
        )
        self._add_checkbox_row(
            filter_frame, 2,
            "Keep records with UNKNOWN uncertainty (highlight in yellow)",
            self.keep_unknown_unc_var,
            "Many museums don't report coordinate uncertainty.\n\n"
            "IF CHECKED: Keep these records and highlight in yellow.\n"
            "IF UNCHECKED: Exclude all records without precise uncertainty."
        )

        # --- 4. Output Format ---
        output_frame = ttk.LabelFrame(
            main_container, text="4. Output Format", padding=10
        )
        output_frame.pack(fill="x", pady=5)

        format_container = ttk.Frame(output_frame)
        format_container.pack(fill="x", padx=5)

        ttk.Radiobutton(
            format_container, text="Excel (.xlsx)", variable=self.format_var, value="excel"
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            format_container, text="CSV (.csv)", variable=self.format_var, value="csv"
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            format_container, text="GeoJSON (.geojson)", variable=self.format_var, value="geojson"
        ).pack(side="left", padx=10)

        # --- Progress Section ---
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(pady=10, padx=30, fill="x")

        self.status_label = Label(
            progress_frame,
            textvariable=self.status_var,
            fg="#0052cc",
            font=("Segoe UI", 9, "bold"),
        )
        self.status_label.pack(pady=2)

        self.progress_bar = ttk.Progressbar(
            progress_frame, orient="horizontal", mode="determinate"
        )
        self.progress_bar.pack(fill="x", ipady=2)

        self.progress_label = Label(
            progress_frame,
            textvariable=self.progress_var,
            font=("Consolas", 10),
        )
        self.progress_label.pack(pady=5)

        # --- Action Buttons ---
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=15, side="bottom")

        self.download_btn = ttk.Button(
            btn_frame,
            text="START DOWNLOAD",
            command=self._start_download,
        )
        self.download_btn.pack(side="left", padx=10, ipadx=15, ipady=5)

        self.stop_btn = ttk.Button(
            btn_frame,
            text="STOP",
            command=self._stop_download,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=10, ipadx=15, ipady=5)

    def _add_entry_row(
        self,
        parent,
        row: int,
        label: str,
        variable,
        help_text: str,
    ):
        """Add an entry row with label and help button."""
        ttk.Label(parent, text=label, width=22, anchor="w").grid(
            row=row, column=0, padx=5, pady=5
        )
        ttk.Entry(parent, textvariable=variable, width=30).grid(
            row=row, column=1, sticky="ew", padx=5, pady=5
        )
        ToolTipButton(parent, "Info", help_text).grid(row=row, column=2, padx=5)
        parent.columnconfigure(1, weight=1)

    def _add_checkbox_row(
        self,
        parent,
        row: int,
        label: str,
        variable: BooleanVar,
        help_text: str,
    ):
        """Add a checkbox row with help button."""
        ttk.Checkbutton(parent, text=label, variable=variable).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=5, pady=5
        )
        ToolTipButton(parent, "Info", help_text).grid(row=row, column=2, padx=5)

    def _start_download(self):
        """Start the download process in a background thread."""
        if self.is_downloading:
            return

        # Validate input
        genus = self.genus_var.get().strip()
        family = self.family_var.get().strip()

        if not genus and not family:
            messagebox.showerror("Error", "Please enter a genus or family name.")
            return

        try:
            year_start = self.year_start_var.get()
            year_end = self.year_end_var.get()
            uncertainty_max = self.uncertainty_var.get()
        except Exception:
            messagebox.showerror(
                "Error",
                "Year and uncertainty values must be valid integers."
            )
            return

        # Update UI state
        self.is_downloading = True
        self.stop_event.clear()
        self.download_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress_bar["value"] = 0
        self.progress_var.set("Initializing...")

        # Start background thread
        thread = threading.Thread(target=self._run_download)
        thread.daemon = True
        thread.start()

    def _stop_download(self):
        """Request download stop."""
        if self.is_downloading:
            self.stop_event.set()
            self.status_var.set("Stopping...")

    def _run_download(self):
        """Run the download process (called in background thread)."""
        try:
            # Build filter config
            genus = self.genus_var.get().strip() or None
            family = self.family_var.get().strip() or None
            species = self.species_var.get().strip()
            countries = self.countries_var.get().strip()

            config = FilterConfig(
                genus=genus,
                family=family,
                species_list=species.split(",") if species else [],
                year_start=self.year_start_var.get(),
                year_end=self.year_end_var.get(),
                uncertainty_max=self.uncertainty_var.get(),
                require_year=self.require_year_var.get(),
                require_elevation=self.require_elev_var.get(),
                keep_unknown_uncertainty=self.keep_unknown_unc_var.get(),
                countries=countries.split(",") if countries else [],
            )

            # Match taxon
            self.status_var.set(f"Matching taxon '{genus or family}'...")
            client = GBIFClient()

            try:
                taxon_name = genus or family
                rank = "GENUS" if genus else "FAMILY"
                taxon = client.match_taxon(taxon_name, rank=rank)
            except TaxonNotFoundError as e:
                self._show_error(str(e))
                return

            # Count records
            self.status_var.set("Counting records...")
            total_count = client.count_occurrences(taxon.usage_key)
            self.progress_bar["maximum"] = total_count
            self.status_var.set(f"Found {total_count:,} records. Downloading...")

            # Download and filter
            record_filter = RecordFilter(config)
            filtered_records = []
            processed = 0

            for record in client.iter_occurrences_by_year(
                taxon.usage_key,
                year_start=config.year_start,
                year_end=config.year_end,
                stop_check=self.stop_event.is_set,
            ):
                if self.stop_event.is_set():
                    break

                processed += 1
                result = record_filter.apply(record)

                if result.keep:
                    filtered_records.append(record)

                # Update progress
                self.progress_bar["value"] = processed
                if processed > total_count:
                    self.progress_bar["maximum"] = processed
                self.progress_var.set(
                    f"Valid: {len(filtered_records):,} | Processed: {processed:,}"
                )
                self.root.update_idletasks()

            client.close()

            # Handle cancellation
            if self.stop_event.is_set():
                messagebox.showinfo(
                    "Stopped",
                    f"Download stopped.\nRecords collected: {len(filtered_records):,}"
                )
                if not filtered_records:
                    return

            # Handle no results
            if not filtered_records:
                self.status_var.set("No valid records found.")
                messagebox.showwarning(
                    "No Data",
                    "No records passed the filter criteria."
                )
                return

            # Save file
            self._save_results(filtered_records, genus or family)

        except GBIFError as e:
            self._show_error(f"GBIF API Error: {e}")
        except Exception as e:
            self.logger.exception("Unexpected error during download")
            self._show_error(f"Error: {e}")
        finally:
            self.is_downloading = False
            self.download_btn.config(state="normal")
            self.stop_btn.config(state="disabled")

    def _save_results(self, records: list, taxon_name: str):
        """Prompt user to save results and export."""
        self.status_var.set("Preparing file...")

        format_name = self.format_var.get()
        extensions = {
            "excel": ("Excel Files", "*.xlsx"),
            "csv": ("CSV Files", "*.csv"),
            "geojson": ("GeoJSON Files", "*.geojson"),
        }
        ext = extensions[format_name]

        default_name = f"{taxon_name}_GBIF.{ext[1].replace('*.', '')}"

        path = filedialog.asksaveasfilename(
            defaultextension=ext[1].replace("*", ""),
            filetypes=[ext, ("All Files", "*.*")],
            initialfile=default_name,
            title="Save Results",
        )

        if not path:
            self.status_var.set("Save cancelled.")
            return

        # Export
        try:
            exporter_class = get_exporter(format_name)
            exporter = exporter_class()
            output_path = exporter.export(
                records,
                path,
                highlight_uncertain=self.keep_unknown_unc_var.get(),
            )

            self.status_var.set("Complete!")
            messagebox.showinfo(
                "Success",
                f"File saved successfully!\n\n"
                f"Records: {len(records):,}\n"
                f"File: {output_path}"
            )
        except Exception as e:
            self._show_error(f"Error saving file: {e}")

    def _show_error(self, message: str):
        """Show error message and reset UI state."""
        self.status_var.set("Error")
        self.root.after(0, lambda: messagebox.showerror("Error", message))


def main():
    """Main entry point for the GUI application."""
    root = Tk()

    # Cross-platform DPI handling
    try:
        # Windows
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    try:
        # macOS - Make text sharper
        root.tk.call("tk", "scaling", 2.0)
    except Exception:
        pass

    app = GBIFDownloaderGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
