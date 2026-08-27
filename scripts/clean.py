#!/usr/bin/env python3
"""
CWAC scan cleaning + consolidation pipeline.

Reads the raw CWAC accessibility-scan CSVs (one folder per scan date under
data/raw/<YYYY-MM-DD>/) and produces cleaned, date-stamped datasets under
data/clean/.

Key design decision — merger-aware attribution
----------------------------------------------
New Zealand government agencies merge and rename over time (machinery-of-
government changes). To track a *current* agency's progress across scans, every
historical issue is attributed to the agency that owns its website **as of the
most recent scan (30 June 2026)**, by joining on ``base_url``. This means, e.g.,
the merged "Ministry of Cities, Environment, Regions and Transport" carries a
full trend line back through its predecessor agencies (Environment, Transport,
Housing & Urban Development). The mapping is derived from the data, not a hand-
maintained list.

Outputs
-------
- data/clean/agency_url_map.csv     canonical base_url -> current agency/sector
- data/clean/issues_long.csv.gz     every extracted issue, all audits & scans,
                                     attributed to the current agency
- data/clean/summary_by_org.csv     per current-agency x scan_date metrics (wide)
- data/clean/summary_by_sector.csv  per sector x scan_date metrics (wide)
- data/clean/summary_totals.csv     government-wide totals per scan_date
"""
from __future__ import annotations

import csv
import gzip
import io
import os
import re
import sys
import unicodedata
import zipfile
from collections import defaultdict

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "clean")

# Scan dates, auto-discovered from data/raw/<YYYY-MM-DD>/ folders in
# chronological order. Adding a new scan is therefore just: drop a new dated
# folder of CSVs into data/raw/ and re-run — no code edit needed. The LAST
# (most recent) scan defines the canonical (current) agency structure used for
# merger-aware attribution.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def discover_scans() -> list[str]:
    if not os.path.isdir(RAW):
        raise SystemExit(f"No raw data directory: {RAW}")
    dates = sorted(d for d in os.listdir(RAW)
                   if _DATE_RE.match(d) and os.path.isdir(os.path.join(RAW, d)))
    if not dates:
        raise SystemExit(f"No YYYY-MM-DD scan folders found under {RAW}")
    return dates


SCANS = discover_scans()
CANONICAL_SCAN = SCANS[-1]

DESC_MAXLEN = 200  # truncate long descriptions to keep issues_long compact


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def norm_text(s: str | None) -> str:
    """Normalise a text value: NFC unicode, strip, collapse inner whitespace."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", s)
    return " ".join(s.split())


def norm_url_key(u: str | None) -> str:
    """Normalise a URL for join matching (not for display)."""
    u = norm_text(u)
    if not u:
        return ""
    return u.rstrip("/").lower()


def to_int(v, default=0) -> int:
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return default


def to_float(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


def scan_path(date: str, suffix: str) -> str | None:
    """Path to a raw file for a scan, or None if absent."""
    p = os.path.join(RAW, date, f"{date}_{suffix}")
    return p if os.path.exists(p) else None


def open_rows(date: str, base_suffix: str):
    """
    Yield dict rows from a raw audit that may be stored as .csv or zipped .zip.
    Uses utf-8-sig to strip the BOM, and tolerates embedded NULs.
    Returns (columns, generator) or (None, None) if the file is absent.
    """
    csv_p = scan_path(date, base_suffix + ".csv")
    zip_p = scan_path(date, base_suffix + ".zip")
    if csv_p:
        fh = open(csv_p, "r", encoding="utf-8-sig", newline="")
        reader = csv.DictReader(_denul(fh))
        return reader.fieldnames, _iter_close(reader, fh)
    if zip_p:
        zf = zipfile.ZipFile(zip_p)
        name = zf.namelist()[0]
        raw = zf.open(name, "r")
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(_denul(text))
        return reader.fieldnames, _iter_close(reader, zf)
    return None, None


def _denul(fh):
    for line in fh:
        yield line.replace("\x00", "")


def _iter_close(reader, closable):
    try:
        for row in reader:
            yield row
    finally:
        closable.close()


# --------------------------------------------------------------------------- #
# 1. Canonical URL -> current agency map
# --------------------------------------------------------------------------- #
def build_canonical_map():
    """base_url_key -> (current_organisation, current_sector) from newest scan."""
    p = scan_path(CANONICAL_SCAN, "all_base_urls.csv")
    if not p:
        raise SystemExit(f"Canonical all_base_urls.csv missing for {CANONICAL_SCAN}")
    cmap = {}
    display = {}
    with open(p, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            key = norm_url_key(row.get("url"))
            if not key:
                continue
            cmap[key] = (norm_text(row.get("organisation")), norm_text(row.get("sector")))
            display[key] = norm_text(row.get("url"))
    return cmap, display


# --------------------------------------------------------------------------- #
# 2. Audit extractors -> normalised issue records
# --------------------------------------------------------------------------- #
def issue_base(row):
    """Common identifying fields present on most audit rows."""
    return (
        norm_text(row.get("base_url")),
        norm_text(row.get("url")),
        norm_text(row.get("organisation")),
        norm_text(row.get("sector")),
    )


def extract_axe(row, template=False):
    desc = norm_text(row.get("description"))
    if not desc or desc == "No issues found":
        return None
    base_url, url, org, sector = issue_base(row)
    count = to_int(row.get("num_pages") if template else row.get("num_issues"), 1) or 1
    return dict(
        audit="axe_core_template" if template else "axe_core",
        base_url=base_url, url=url, own_org=org, own_sector=sector,
        rule_id=norm_text(row.get("id")),
        impact=norm_text(row.get("impact")),
        description=desc[:DESC_MAXLEN],
        count=count,
    )


def extract_focus(row):
    if to_int(row.get("num_issues")) <= 0:
        return None
    base_url, url, org, sector = issue_base(row)
    return dict(
        audit="focus_indicator",
        base_url=base_url, url=url, own_org=org, own_sector=sector,
        rule_id="focus-visible",
        impact="",
        description=norm_text(row.get("description"))[:DESC_MAXLEN],
        count=to_int(row.get("num_issues"), 1) or 1,
    )


def extract_reflow(row):
    overflow = norm_text(row.get("overflows")).upper() == "TRUE"
    if not overflow and to_int(row.get("num_issues")) <= 0:
        return None
    base_url, url, org, sector = issue_base(row)
    px = to_int(row.get("overflow_amount_px"))
    return dict(
        audit="reflow",
        base_url=base_url, url=url, own_org=org, own_sector=sector,
        rule_id="reflow",
        impact="",
        description=f"Content overflow at 320px ({px}px)",
        count=to_int(row.get("num_issues"), 1) or 1,
    )


def extract_response_code(row):
    # No org/sector columns; attributed purely via base_url.
    base_url = norm_text(row.get("base_url"))
    url = norm_text(row.get("url"))
    code = norm_text(row.get("status_code"))
    return dict(
        audit="response_code",
        base_url=base_url, url=url, own_org="", own_sector="",
        rule_id=code,
        impact="",
        description=f"Unexpected HTTP {code}",
        count=1,
    )


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    os.makedirs(OUT, exist_ok=True)
    cmap, cdisplay = build_canonical_map()
    print(f"Canonical map ({CANONICAL_SCAN}): {len(cmap)} base URLs, "
          f"{len({v[0] for v in cmap.values()})} current agencies")

    # per (scan, current_org) accumulators for the summary
    summ = defaultdict(lambda: defaultdict(float))
    sector_of = {}                 # current_org -> current_sector
    url_seen = defaultdict(set)    # base_url_key -> set(scan dates seen)
    url_histnames = defaultdict(set)

    # per (scan, base_url) accumulators for the per-site drill-down
    # (in-current-scope sites only, so every site rolls up under a current agency)
    site_summ = defaultdict(lambda: defaultdict(float))
    site_org = {}                  # base_url_key -> (current_org, current_sector)

    # agency-level axe breakdowns for the per-agency report
    axe_impact = defaultdict(float)          # (date, org, impact) -> issues
    axe_rule = defaultdict(float)            # (date, org, rule_id) -> issues
    axe_rule_sites = defaultdict(set)        # (date, org, rule_id) -> {base_url_key}

    issues_path = os.path.join(OUT, "issues_long.csv.gz")
    issues_cols = ["scan_date", "audit", "organisation", "sector",
                   "base_url", "url", "rule_id", "impact", "description",
                   "count", "in_current_scope"]
    n_issues = 0

    with gzip.open(issues_path, "wt", encoding="utf-8", newline="") as gz:
        w = csv.writer(gz)
        w.writerow(issues_cols)

        for date in SCANS:
            audits = {
                "axe_core_audit": lambda r: extract_axe(r, template=False),
                "axe_core_audit_template_aware": lambda r: extract_axe(r, template=True),
                "focus_indicator_audit": extract_focus,
                "reflow_audit": extract_reflow,
                "unexpected_response_codes": extract_response_code,
            }
            present = []
            for suffix, fn in audits.items():
                cols, rows = open_rows(date, suffix)
                if rows is None:
                    continue
                present.append(suffix)
                for row in rows:
                    rec = fn(row)
                    if rec is None:
                        continue
                    key = norm_url_key(rec["base_url"])
                    url_seen[key].add(date)
                    if rec["own_org"]:
                        url_histnames[key].add(rec["own_org"])
                    in_scope = key in cmap
                    if in_scope:
                        org, sector = cmap[key]
                    else:
                        org, sector = (rec["own_org"], rec["own_sector"])
                    w.writerow([
                        date, rec["audit"], org, sector,
                        rec["base_url"], rec["url"], rec["rule_id"],
                        rec["impact"], rec["description"], rec["count"],
                        "true" if in_scope else "false",
                    ])
                    n_issues += 1

                    # summary only counts current-scope agencies
                    if in_scope:
                        sector_of[org] = sector
                        site_org[key] = (org, sector)
                        a = rec["audit"]
                        if a == "axe_core":
                            imp = rec["impact"] or "unknown"
                            axe_impact[(date, org, imp)] += rec["count"]
                            rid = rec["rule_id"] or "(unlabelled)"
                            axe_rule[(date, org, rid)] += rec["count"]
                            axe_rule_sites[(date, org, rid)].add(key)
                        for s in (summ[(date, org)], site_summ[(date, key)]):
                            if a == "axe_core":
                                s["axe_issue_rows"] += 1
                                s["axe_issues"] += rec["count"]
                                if rec["impact"] == "serious":
                                    s["axe_serious"] += rec["count"]
                                elif rec["impact"] == "critical":
                                    s["axe_critical"] += rec["count"]
                            elif a == "axe_core_template":
                                s["axe_template_rows"] += 1
                            elif a == "focus_indicator":
                                s["focus_issues"] += rec["count"]
                            elif a == "reflow":
                                s["reflow_pages"] += 1
                                s["reflow_issues"] += rec["count"]
                            elif a == "response_code":
                                s["broken_urls"] += 1

            # coverage: pages_scanned (org/sector present in file)
            cols, rows = open_rows(date, "pages_scanned")
            if rows is not None:
                present.append("pages_scanned")
                for row in rows:
                    key = norm_url_key(row.get("base_url"))
                    if key in cmap:
                        org, sector = cmap[key]
                        sector_of[org] = sector
                        site_org[key] = (org, sector)
                        n_pages = to_int(row.get("number_of_pages"))
                        summ[(date, org)]["pages_scanned"] += n_pages
                        site_summ[(date, key)]["pages_scanned"] += n_pages

            # language_audit: reading-level metrics (not issues)
            cols, rows = open_rows(date, "language_audit")
            if rows is not None:
                present.append("language_audit")
                lang_acc = defaultdict(lambda: [0, 0.0, 0.0])  # org -> [n, sum_fk, sum_smog]
                for row in rows:
                    key = norm_url_key(row.get("base_url"))
                    if key not in cmap:
                        continue
                    fk = to_float(row.get("flesch_kincaid_gl"))
                    smog = to_float(row.get("smog_gl"))
                    if fk is None:
                        continue
                    org = cmap[key][0]
                    acc = lang_acc[org]
                    acc[0] += 1
                    acc[1] += fk
                    acc[2] += (smog or 0.0)
                    site_org[key] = cmap[key]
                    ss = site_summ[(date, key)]
                    ss["language_pages"] += 1
                    ss["_lang_fk_sum"] += fk
                    ss["_lang_smog_sum"] += (smog or 0.0)
                for org, (n, sfk, ssmog) in lang_acc.items():
                    if n:
                        summ[(date, org)]["language_pages"] += n
                        summ[(date, org)]["_lang_fk_sum"] += sfk
                        summ[(date, org)]["_lang_smog_sum"] += ssmog

            print(f"  {date}: audits present = {', '.join(present) or 'NONE'}")

    print(f"issues_long.csv.gz: {n_issues:,} issue records")

    # ----------------------------------------------------------------- #
    # summary_by_org (wide)
    # ----------------------------------------------------------------- #
    metric_cols = [
        "pages_scanned", "axe_issues", "axe_serious", "axe_critical",
        "axe_issue_rows", "axe_template_rows", "focus_issues",
        "reflow_pages", "reflow_issues", "broken_urls",
        "language_pages", "language_mean_fk", "language_mean_smog",
    ]
    org_rows = []
    for (date, org), s in sorted(summ.items()):
        lp = s.get("language_pages", 0)
        rec = {
            "scan_date": date,
            "organisation": org,
            "sector": sector_of.get(org, ""),
        }
        for m in metric_cols:
            if m == "language_mean_fk":
                rec[m] = round(s["_lang_fk_sum"] / lp, 3) if lp else ""
            elif m == "language_mean_smog":
                rec[m] = round(s["_lang_smog_sum"] / lp, 3) if lp else ""
            else:
                v = s.get(m, 0)
                rec[m] = int(v) if float(v).is_integer() else v
        org_rows.append(rec)

    _write_csv(os.path.join(OUT, "summary_by_org.csv"),
               ["scan_date", "organisation", "sector"] + metric_cols, org_rows)

    # ----------------------------------------------------------------- #
    # summary_by_site (wide) — per website x scan_date, for the agency
    # drill-down. base_url shown in its canonical (30 June 2026) form.
    # ----------------------------------------------------------------- #
    site_rows = []
    for (date, key), s in sorted(site_summ.items()):
        org, sector = site_org.get(key, ("", ""))
        lp = s.get("language_pages", 0)
        rec = {
            "scan_date": date,
            "base_url": cdisplay.get(key, key),
            "organisation": org,
            "sector": sector,
        }
        for m in metric_cols:
            if m == "language_mean_fk":
                rec[m] = round(s["_lang_fk_sum"] / lp, 3) if lp else ""
            elif m == "language_mean_smog":
                rec[m] = round(s["_lang_smog_sum"] / lp, 3) if lp else ""
            else:
                v = s.get(m, 0)
                rec[m] = int(v) if float(v).is_integer() else v
        site_rows.append(rec)
    _write_csv(os.path.join(OUT, "summary_by_site.csv"),
               ["scan_date", "base_url", "organisation", "sector"] + metric_cols,
               site_rows)

    # ----------------------------------------------------------------- #
    # axe_impact_by_org / axe_rules_by_org — agency-level axe breakdowns
    # for the per-agency report (impact split + top failing WCAG rules).
    # ----------------------------------------------------------------- #
    impact_rows = [
        {"scan_date": d, "organisation": o, "impact": imp, "issues": int(v)}
        for (d, o, imp), v in sorted(axe_impact.items())
    ]
    _write_csv(os.path.join(OUT, "axe_impact_by_org.csv"),
               ["scan_date", "organisation", "impact", "issues"], impact_rows)

    rule_rows = [
        {"scan_date": d, "organisation": o, "rule_id": r, "issues": int(v),
         "sites_affected": len(axe_rule_sites[(d, o, r)])}
        for (d, o, r), v in sorted(axe_rule.items())
    ]
    _write_csv(os.path.join(OUT, "axe_rules_by_org.csv"),
               ["scan_date", "organisation", "rule_id", "issues", "sites_affected"],
               rule_rows)

    # ----------------------------------------------------------------- #
    # summary_by_sector (wide) — roll up agencies within a sector
    # ----------------------------------------------------------------- #
    sec = defaultdict(lambda: defaultdict(float))
    for rec in org_rows:
        key = (rec["scan_date"], rec["sector"])
        for m in metric_cols:
            if m.startswith("language_mean"):
                continue
            v = rec[m]
            if isinstance(v, (int, float)):
                sec[key][m] += v
    # weighted language means from raw sums
    lang_sums = defaultdict(lambda: [0.0, 0.0, 0.0])  # (date,sector)->[pages,fk,smog]
    for (date, org), s in summ.items():
        key = (date, sector_of.get(org, ""))
        lp = s.get("language_pages", 0)
        lang_sums[key][0] += lp
        lang_sums[key][1] += s.get("_lang_fk_sum", 0.0)
        lang_sums[key][2] += s.get("_lang_smog_sum", 0.0)
    sector_rows = []
    for (date, sector_name), s in sorted(sec.items()):
        rec = {"scan_date": date, "sector": sector_name}
        for m in metric_cols:
            if m == "language_mean_fk":
                lp, fk, _ = lang_sums[(date, sector_name)]
                rec[m] = round(fk / lp, 3) if lp else ""
            elif m == "language_mean_smog":
                lp, _, sm = lang_sums[(date, sector_name)]
                rec[m] = round(sm / lp, 3) if lp else ""
            else:
                v = s.get(m, 0)
                rec[m] = int(v) if float(v).is_integer() else v
        sector_rows.append(rec)
    _write_csv(os.path.join(OUT, "summary_by_sector.csv"),
               ["scan_date", "sector"] + metric_cols, sector_rows)

    # ----------------------------------------------------------------- #
    # summary_totals (government-wide) per scan_date
    # ----------------------------------------------------------------- #
    tot = defaultdict(lambda: defaultdict(float))
    lang_tot = defaultdict(lambda: [0.0, 0.0, 0.0])
    for rec in org_rows:
        d = rec["scan_date"]
        for m in metric_cols:
            if m.startswith("language_mean"):
                continue
            v = rec[m]
            if isinstance(v, (int, float)):
                tot[d][m] += v
    for (date, org), s in summ.items():
        lang_tot[date][0] += s.get("language_pages", 0)
        lang_tot[date][1] += s.get("_lang_fk_sum", 0.0)
        lang_tot[date][2] += s.get("_lang_smog_sum", 0.0)
    total_rows = []
    for date in SCANS:
        if date not in tot:
            continue
        rec = {"scan_date": date, "agencies_with_data":
               sum(1 for (d, _o) in summ if d == date)}
        for m in metric_cols:
            if m == "language_mean_fk":
                lp, fk, _ = lang_tot[date]
                rec[m] = round(fk / lp, 3) if lp else ""
            elif m == "language_mean_smog":
                lp, _, sm = lang_tot[date]
                rec[m] = round(sm / lp, 3) if lp else ""
            else:
                v = tot[date].get(m, 0)
                rec[m] = int(v) if float(v).is_integer() else v
        total_rows.append(rec)
    _write_csv(os.path.join(OUT, "summary_totals.csv"),
               ["scan_date", "agencies_with_data"] + metric_cols, total_rows)

    # ----------------------------------------------------------------- #
    # agency_url_map.csv — reference of the merger-aware mapping
    # ----------------------------------------------------------------- #
    map_rows = []
    all_keys = set(cmap) | set(url_seen)
    for key in sorted(all_keys):
        org, sector = cmap.get(key, ("", ""))
        map_rows.append({
            "base_url": cdisplay.get(key, key),
            "current_organisation": org,
            "current_sector": sector,
            "in_2026_06_30": "true" if key in cmap else "false",
            "scans_seen": len(url_seen.get(key, ())),
            "historical_names": "; ".join(sorted(url_histnames.get(key, ()))),
        })
    _write_csv(os.path.join(OUT, "agency_url_map.csv"),
               ["base_url", "current_organisation", "current_sector",
                "in_2026_06_30", "scans_seen", "historical_names"], map_rows)

    print("Wrote:")
    for f in ["issues_long.csv.gz", "summary_by_org.csv", "summary_by_site.csv",
              "axe_impact_by_org.csv", "axe_rules_by_org.csv",
              "summary_by_sector.csv", "summary_totals.csv", "agency_url_map.csv"]:
        p = os.path.join(OUT, f)
        print(f"  data/clean/{f:28s} {os.path.getsize(p):>12,} bytes")


def _write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    main()
