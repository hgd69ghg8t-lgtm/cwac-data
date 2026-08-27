#!/usr/bin/env python3
"""
Embed viz/data.json into the <script id="DATA"> block of viz/dashboard.html.

This closes the manual "build step" the READMEs describe: after regenerating
viz/data.json (scripts/build_viz_data.py) run this to refresh the dashboard.

Usage
-----
    python3 scripts/embed_data.py                 # embed (minified) in place
    python3 scripts/embed_data.py --pretty --out FILE
                                                  # write a whitespace-spaced
                                                  # publish variant to FILE,
                                                  # leaving dashboard.html as-is

The --pretty variant exists only for publishing as a Claude Artifact: the
publish-time validator false-positives on the dense minified JSON blob, and
spacing the tokens clears it. The dashboard reads the block with JSON.parse,
so whitespace is functionally irrelevant.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASH = os.path.join(ROOT, "viz", "dashboard.html")
DATA = os.path.join(ROOT, "viz", "data.json")
OPEN_TAG = '<script id="DATA" type="application/json">'
CLOSE_TAG = "</script>"


def embed(html: str, payload: str) -> str:
    s = html.find(OPEN_TAG)
    if s == -1:
        sys.exit(f"error: {OPEN_TAG} not found in {DASH}")
    start = s + len(OPEN_TAG)
    end = html.find(CLOSE_TAG, start)
    if end == -1:
        sys.exit("error: closing </script> for the DATA block not found")
    return html[:start] + payload + html[end:]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pretty", action="store_true",
                    help="pretty-print the embedded JSON (for publishing)")
    ap.add_argument("--out", default=None,
                    help="write result here instead of editing dashboard.html")
    args = ap.parse_args()

    obj = json.load(open(DATA, encoding="utf-8"))
    payload = (json.dumps(obj, indent=1) if args.pretty
               else json.dumps(obj, separators=(",", ":")))

    html = open(DASH, encoding="utf-8").read()
    out_html = embed(html, payload)

    dest = args.out or DASH
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(out_html)
    print(f"embedded {len(payload):,} bytes of data.json -> {dest}"
          f"{' (pretty)' if args.pretty else ''}")


if __name__ == "__main__":
    main()
