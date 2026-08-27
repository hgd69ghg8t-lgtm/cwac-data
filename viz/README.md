# viz

`dashboard.html` — self-contained interactive dashboard of accessibility
progress over time (built from `data/clean/`). Open directly in a browser.

Selecting a single agency opens an **Agency report**: a site × audit overview
table plus a detailed section for every audit (accessibility with impact split
and top WCAG rules, reading level, reflow, focus, broken links), showing each
owned site's progress over time.

`data.json` — the compact, audit-presence-aware dataset the dashboard reads
(embedded into dashboard.html at build time).

Regenerate after re-running `scripts/clean.py`:

```
python3 scripts/clean.py           # rebuild data/clean/
python3 scripts/build_viz_data.py  # rebuild viz/data.json
# then re-embed data.json into dashboard.html (build step)
```
