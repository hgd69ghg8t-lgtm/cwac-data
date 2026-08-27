# viz

`dashboard.html` — self-contained interactive dashboard of accessibility
progress over time (built from `data/clean/`). Open directly in a browser.

The headline stats at the top are **dynamic**: focusing an agency recomputes
them for that agency, and a snapshot date selector shows the overall figures as
at any scan.

Selecting a single agency opens an **Agency report** that opens with a
plain-language **narrative** — how issues/page changed, which predecessor
agencies it was formed from (merger-aware), the most improved and
worst-regressed sites, and any sites added since tracking began — followed by a
site × audit overview table and a detailed section for every audit
(accessibility with impact split and top WCAG rules, reading level, reflow,
focus, broken links).

`data.json` — the compact, audit-presence-aware dataset the dashboard reads
(embedded into dashboard.html by `scripts/embed_data.py`). Includes
`by_org_predecessors` (predecessor agency → site count) that powers the merger
narrative.

Regenerate everything with one command:

```
python3 scripts/build.py           # clean → viz data → embed, with a summary
```

or step by step:

```
python3 scripts/clean.py           # rebuild data/clean/
python3 scripts/build_viz_data.py  # rebuild viz/data.json
python3 scripts/embed_data.py      # embed data.json into dashboard.html
```
