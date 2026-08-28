# viz

`dashboard.html` — self-contained interactive dashboard of accessibility
progress over time (built from `data/clean/`). Open directly in a browser.
No external requests (no web fonts, no CDNs): it uses the system font stack and
a calm monochrome + teal light theme, and is responsive down to phone widths.

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

## Publishing (GitHub Pages)

`dashboard.html` is the single source of truth. `.github/workflows/pages.yml`
builds the published site from it in CI (copies it to `index.html`) and deploys
to GitHub Pages on every push that changes `viz/dashboard.html` — **no manual
copy step.** Pages must be enabled once (Settings → Pages → Source: *GitHub
Actions*); after that it is automatic. The workflow can also be run on demand
from **Actions → Deploy dashboard to GitHub Pages → Run workflow**.

Live at https://hgd69ghg8t-lgtm.github.io/cwac-data/
