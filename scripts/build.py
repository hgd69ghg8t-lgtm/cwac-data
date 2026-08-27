#!/usr/bin/env python3
"""
One-command rebuild of the CWAC dashboard from raw scans.

Runs the whole pipeline end to end:

    clean.py  ->  build_viz_data.py  ->  embed_data.py

and prints a summary of what changed (scans, agencies, sites) so that after
dropping a new dated scan folder into data/raw/ you can see exactly which new
websites / agencies you picked up.

Usage
-----
    python3 scripts/build.py                 # full rebuild + change summary
    python3 scripts/build.py --check DATE     # validate a raw scan folder only
                                              # (e.g. --check 2026-09-30)

Adding a new scan
-----------------
1. Create data/raw/<YYYY-MM-DD>/ and drop the scan CSVs in, named
   <YYYY-MM-DD>_<audit>.csv (or .zip for the large axe/language audits), exactly
   like the existing folders.
2. (Optional) `python3 scripts/build.py --check <YYYY-MM-DD>` to sanity-check it.
3. `python3 scripts/build.py`.

Adding a website you have become responsible for
------------------------------------------------
Attribution is derived from the data, not a hand-kept list: it comes from the
NEWEST scan's <date>_all_base_urls.csv (columns: organisation,url,sector). List
the new site's url there against the owning organisation and it is attributed
automatically. Its trend line starts at the first scan it appears in (shown as
it appears — earlier scans stay blank, not zero).

Note: build_viz_data.py requires pandas. If it is not installed, this script
reports that clearly and stops after clean.py.
"""
import argparse
import csv
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
RAW = os.path.join(ROOT, "data", "raw")
CLEAN = os.path.join(ROOT, "data", "clean")
MAP = os.path.join(CLEAN, "agency_url_map.csv")

# Files a scan folder should contain. axe/language may be zipped.
REQUIRED = [("all_base_urls.csv", ["organisation", "url", "sector"]),
            ("pages_scanned.csv", ["base_url"])]
EXPECTED_AUDITS = ["axe_core_audit", "pages_scanned", "all_base_urls"]


def read_map():
    """Return (scans_seen_max, {base_url}, {organisation}) from agency_url_map."""
    urls, orgs = set(), set()
    if not os.path.exists(MAP):
        return urls, orgs
    with open(MAP, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            urls.add(r["base_url"])
            if r.get("current_organisation"):
                orgs.add(r["current_organisation"])
    return urls, orgs


def scan_dirs():
    import re
    rx = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    return sorted(d for d in os.listdir(RAW)
                  if rx.match(d) and os.path.isdir(os.path.join(RAW, d)))


def check(date):
    folder = os.path.join(RAW, date)
    if not os.path.isdir(folder):
        sys.exit(f"error: no scan folder {folder}")
    problems = []
    for base, cols in REQUIRED:
        p = os.path.join(folder, f"{date}_{base}")
        if not os.path.exists(p):
            problems.append(f"missing {date}_{base}")
            continue
        with open(p, encoding="utf-8-sig", newline="") as fh:
            header = next(csv.reader(fh), [])
        for c in cols:
            if c not in header:
                problems.append(f"{date}_{base}: column '{c}' not found "
                                f"(has: {', '.join(header)})")
    # axe present as csv or zip?
    if not any(os.path.exists(os.path.join(folder, f"{date}_axe_core_audit{e}"))
               for e in (".csv", ".zip")):
        problems.append(f"missing {date}_axe_core_audit(.csv|.zip)")
    if problems:
        print(f"✗ {date}: not ready")
        for p in problems:
            print(f"    - {p}")
        return False
    print(f"✓ {date}: looks good")
    return True


def run(script, *args):
    print(f"\n$ python3 scripts/{script} {' '.join(args)}".rstrip())
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args])
    return r.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", metavar="DATE",
                    help="validate a raw scan folder (YYYY-MM-DD) and exit")
    args = ap.parse_args()

    if args.check:
        sys.exit(0 if check(args.check) else 1)

    print(f"Scans found: {', '.join(scan_dirs())}")
    urls_before, orgs_before = read_map()

    if run("clean.py") != 0:
        sys.exit("clean.py failed")

    urls_after, orgs_after = read_map()
    new_urls = sorted(urls_after - urls_before)
    new_orgs = sorted(orgs_after - orgs_before)

    # Print the attribution summary now — it comes from clean.py, so it is
    # useful even if the viz step below can't run (e.g. pandas missing).
    print("\n── Change summary ─────────────────────────────")
    print(f"  scans:      {len(scan_dirs())}")
    print(f"  agencies:   {len(orgs_after)}"
          + (f"  (+{len(new_orgs)} new)" if new_orgs else ""))
    print(f"  sites:      {len(urls_after)}"
          + (f"  (+{len(new_urls)} new)" if new_urls else ""))
    for o in new_orgs:
        print(f"    + agency: {o}")
    for u in new_urls[:20]:
        print(f"    + site:   {u}")
    if len(new_urls) > 20:
        print(f"    … and {len(new_urls) - 20} more sites")

    rc = run("build_viz_data.py")
    if rc != 0:
        print("\n⚠ build_viz_data.py failed. It requires pandas — install with:")
        print("    pip install pandas")
        print("clean.py outputs are up to date; re-run build after installing.")
        sys.exit(rc)

    if run("embed_data.py") != 0:
        sys.exit("embed_data.py failed")

    print("\nDone. viz/dashboard.html refreshed. To publish, run:")
    print("  python3 scripts/embed_data.py --pretty --out /tmp/publish.html")
    print("  then publish /tmp/publish.html as the Artifact.")


if __name__ == "__main__":
    main()
