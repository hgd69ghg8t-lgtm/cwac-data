#!/usr/bin/env python3
"""
Build viz/data.json — the compact, audit-presence-aware dataset the dashboard
reads. Run after scripts/clean.py.

Encoding notes
--------------
- Values are stored as metric -> array indexed by scan position (nulls omitted),
  which keeps the embedded payload small.
- Per-site keys store host+path with the URL scheme stripped, so the page embeds
  no full URLs (avoids a publish-size/validation issue seen with hundreds of
  https:// strings inline).
- Audit-absent points are gated to null (never zero) via audit presence per scan.
"""
import pandas as pd, json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")
OUT = os.path.join(ROOT, "viz", "data.json")
TOP_RULES = 10

org = pd.read_csv(f"{CLEAN}/summary_by_org.csv")
tot = pd.read_csv(f"{CLEAN}/summary_totals.csv")
sec = pd.read_csv(f"{CLEAN}/summary_by_sector.csv")
site = pd.read_csv(f"{CLEAN}/summary_by_site.csv")
impact = pd.read_csv(f"{CLEAN}/axe_impact_by_org.csv")
rules = pd.read_csv(f"{CLEAN}/axe_rules_by_org.csv")

scans = sorted(org.scan_date.unique())
sidx = {d: i for i, d in enumerate(scans)}


def present(d, base):
    return any(os.path.exists(f"{ROOT}/data/raw/{d}/{d}_{base}{e}")
               for e in (".csv", ".zip"))


ap = {d: {"axe": present(d, "axe_core_audit"),
          "focus": present(d, "focus_indicator_audit"),
          "reflow": present(d, "reflow_audit"),
          "response": present(d, "unexpected_response_codes"),
          "language": present(d, "language_audit"),
          "pages": present(d, "pages_scanned")} for d in scans}

gate = {"pages_scanned": "pages", "axe_issues": "axe", "axe_serious": "axe",
        "axe_critical": "axe", "focus_issues": "focus", "reflow_pages": "reflow",
        "reflow_issues": "reflow", "broken_urls": "response",
        "language_mean_fk": "language", "language_mean_smog": "language"}
allm = list(gate)
site_metrics = ["pages_scanned", "axe_issues", "axe_serious", "axe_critical",
                "focus_issues", "reflow_pages", "broken_urls", "language_mean_fk"]


def num(v, m):
    if pd.isna(v):
        return None
    if m in ("language_mean_fk", "language_mean_smog"):
        return round(float(v), 1)
    fv = float(v)
    return int(fv) if fv.is_integer() else round(fv, 2)


def arr_for(recs_by_date, m, gate_audit=True):
    arr = [None] * len(scans)
    any_v = False
    for d in scans:
        r = recs_by_date.get(d)
        if r is None:
            continue
        if gate_audit and not ap[d].get(gate[m], True):
            continue
        v = num(r[m], m)
        if v is not None:
            arr[sidx[d]] = v
            any_v = True
    return arr if any_v else None


def packA(df, key, metrics):
    out = {}
    for k, g in df.groupby(key):
        by = {d: r for d, r in zip(g["scan_date"], g.to_dict("records"))}
        rec = {}
        for m in metrics:
            if m not in df.columns:
                continue
            a = arr_for(by, m)
            if a is not None:
                rec[m] = a
        out[str(k)] = rec
    return out


tot_by = {d: r for d, r in zip(tot["scan_date"], tot.to_dict("records"))}
totals = {m: arr_for(tot_by, m) for m in allm
          if m in tot.columns and arr_for(tot_by, m) is not None}


def hostkey(u):
    return u.replace("https://", "").replace("http://", "").rstrip("/")


by_site = {}
for org_name, g in site.groupby("organisation"):
    d = {}
    for burl, gg in g.groupby("base_url"):
        by = {dd: r for dd, r in zip(gg["scan_date"], gg.to_dict("records"))}
        rec = {m: arr_for(by, m) for m in site_metrics
               if arr_for(by, m) is not None}
        d[hostkey(str(burl))] = rec
    by_site[str(org_name)] = d

# axe impact split per agency: org -> {impact: [array over scans]}
by_org_impact = {}
for org_name, g in impact.groupby("organisation"):
    d = {}
    for imp, gg in g.groupby("impact"):
        by = {row["scan_date"]: row["issues"] for _, row in gg.iterrows()}
        arr = [None] * len(scans)
        for dt, v in by.items():
            arr[sidx[dt]] = int(v)
        d[str(imp)] = arr
    by_org_impact[str(org_name)] = d

# top failing WCAG rules per agency: org -> [{r, c:[array over scans]}]
by_org_rules = {}
last = scans[-1]
for org_name, g in rules.groupby("organisation"):
    latest = (g[g.scan_date == last].groupby("rule_id")["issues"].sum()
              .sort_values(ascending=False))
    top = list(latest.head(TOP_RULES).index)
    # include any rule that was large historically even if 0 now? keep it simple: latest top-N
    lst = []
    for rid in top:
        gr = g[g.rule_id == rid]
        by = {row["scan_date"]: int(row["issues"]) for _, row in gr.iterrows()}
        arr = [by.get(d) for d in scans]
        lst.append({"r": str(rid), "c": arr})
    by_org_rules[str(org_name)] = lst

data = {
    "scans": scans,
    "metrics_order": allm,
    "audit_present": ap,
    "array": True,
    "totals": totals,
    "by_sector": packA(sec, "sector", allm),
    "by_org": packA(org, "organisation", allm),
    "by_site": by_site,
    "by_org_impact": by_org_impact,
    "by_org_rules": by_org_rules,
    "org_sector": {str(r["organisation"]): str(r["sector"])
                   for _, r in org.drop_duplicates("organisation").iterrows()},
}
with open(OUT, "w") as f:
    json.dump(data, f, separators=(",", ":"))
print(f"wrote viz/data.json {os.path.getsize(OUT):,} bytes")
