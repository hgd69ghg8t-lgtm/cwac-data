# cwac-data

Cleaning and visualisation pipeline for CWAC accessibility scan output.

## Layout

- `data/raw/<YYYY-MM-DD>/*.csv` — raw scan CSVs, one folder per scan date (source of truth).
- `data/clean/combined.csv` — consolidated long-format dataset; every row carries a `scan_date` column so progress over time is preserved.
- `scripts/` — the cleaning pipeline.

## Status

Awaiting first real scan CSVs to finalise column extraction.
