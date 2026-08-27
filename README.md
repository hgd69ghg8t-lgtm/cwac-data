# cwac-data

Cleaning and visualisation pipeline for CWAC (accessibility) scan output of
New Zealand government websites.

## Layout

- `data/raw/<YYYY-MM-DD>/*` — raw scan files, one folder per scan date (source
  of truth). Large audits are stored zipped; the pipeline reads `.csv` and
  `.zip` transparently.
- `data/clean/` — cleaned, consolidated, date-stamped outputs (below).
- `scripts/clean.py` — the cleaning pipeline.
- `scripts/build.py` — one-command rebuild (clean → viz data → embed) with a
  change summary. See **Adding a scan** below.

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

## Adding a scan

Scan dates are auto-discovered from the `data/raw/<YYYY-MM-DD>/` folders — no
code edit is needed to add one.

1. Create `data/raw/<YYYY-MM-DD>/` and drop the scan CSVs in, named
   `<YYYY-MM-DD>_<audit>.csv` (or `.zip` for the large axe / language audits),
   matching the existing folders.
2. Optionally validate it: `python3 scripts/build.py --check <YYYY-MM-DD>`.
3. Rebuild everything: `python3 scripts/build.py`.

`build.py` runs `clean.py` → `build_viz_data.py` → `embed_data.py` and prints a
summary of new agencies / sites picked up. The **most recent** scan defines the
canonical (current) agency structure used for merger-aware attribution.

> `build_viz_data.py` needs pandas (`pip install pandas`); the other scripts are
> standard-library only.

## Adding a website you become responsible for

Attribution is derived from the data, not a hand-kept list. It comes from the
newest scan's `<date>_all_base_urls.csv` (columns `organisation,url,sector`).
List the new site's `url` there against the owning `organisation`, and it is
attributed automatically. Its trend line **starts at the first scan it appears
in** — earlier scans stay blank (not zero), so newly-acquired sites show up as
they appear.

## Publishing the dashboard

`viz/dashboard.html` is self-contained and can be opened directly. To publish it
as a Claude Artifact, embed a whitespace-spaced copy of the data first:

```
python3 scripts/embed_data.py --pretty --out /tmp/publish.html
```

then publish `/tmp/publish.html`. (The committed `dashboard.html` keeps the
minified data; the spaced copy only works around a publish-time validator that
false-positives on the dense minified JSON blob.)
