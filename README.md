# cwac-data

Cleaning and visualisation pipeline for CWAC (accessibility) scan output of
New Zealand government websites.

## Layout

- `data/raw/<YYYY-MM-DD>/*` — raw scan files, one folder per scan date (source
  of truth). Large audits are stored zipped; the pipeline reads `.csv` and
  `.zip` transparently.
- `data/clean/` — cleaned, consolidated, date-stamped outputs (below).
- `scripts/clean.py` — the cleaning pipeline.

## Merger-aware attribution

NZ government agencies merge and rename over time. Every historical issue is
attributed to the agency that owns its website **as of the most recent scan
(30 June 2026)**, by joining on `base_url`. So a merged agency (e.g. *Ministry
of Cities, Environment, Regions and Transport* = Environment + Transport +
Housing & Urban Development) carries one continuous trend line back through its
predecessors. The mapping is derived from the data, not hand-maintained.

## Cleaned outputs

Run `python3 scripts/clean.py` to regenerate:

| File | Grain | Use |
|---|---|---|
| `data/clean/issues_long.csv.gz` | one row per extracted issue (all audits, all scans) | full detail; attributed to current agency, `in_current_scope` flag |
| `data/clean/summary_by_org.csv` | agency × scan_date | trend charts per agency |
| `data/clean/summary_by_site.csv` | website × scan_date | per-site drill-down / agency report |
| `data/clean/axe_impact_by_org.csv` | agency × scan_date × impact | accessibility impact split |
| `data/clean/axe_rules_by_org.csv` | agency × scan_date × rule | top failing WCAG rules |
| `data/clean/summary_by_sector.csv` | sector × scan_date | cross-government sector trends |
| `data/clean/summary_totals.csv` | scan_date | headline government-wide trend |
| `data/clean/agency_url_map.csv` | base_url | reference: which agency owns each site + historical names |

### Metrics (in the summary files)

`pages_scanned`, `axe_issues` (serious+critical WCAG violations, split into
`axe_serious` / `axe_critical`), `axe_issue_rows`, `axe_template_rows`,
`focus_issues`, `reflow_pages`, `reflow_issues`, `broken_urls`,
`language_pages`, `language_mean_fk` (Flesch-Kincaid grade level),
`language_mean_smog`.

> **Important — normalise by coverage.** Scan breadth varies a lot between dates
> (the 2026-06-30 scan covered ~2× the pages of earlier scans). Compare
> **issues per page**, not absolute counts, to judge real progress.

## Audit coverage by scan

Not every audit ran every scan (e.g. `unexpected_response_codes` only
2026-03-31; `focus_indicator` / `language` missing 2025-08-12). Missing audits
are treated as "no data", never as zero.
