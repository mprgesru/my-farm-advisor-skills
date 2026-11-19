---
name: eda-field-sample
description: Build a reproducible, static field-level EDA for a multi-grower farm sample — boundary geometry, CDL crop sequences, and farm-level weather — producing PNG figures, CSV tables, and a manifest that a report can consume.
version: 1.0.0
author: mprgesru
tags: [eda, fields, boundaries, cdl, weather, maps, geopandas, matplotlib]
---

# Workflow: eda-field-sample

## Description

This workflow answers three questions about a set of farms:

1. **Boundaries** — how big, how compact, and how regular are the fields?
2. **CDL / cropland** — what is planted, how often, and what follows what?
3. **Weather** — how do temperature, growing degree days, and precipitation compare?

It is built for the Assignment 2 sample (ten fields each in Illinois, Iowa, and
Nebraska) but runs on any grower/farm directory that has boundaries, a CDL
composition table, and a weather table. It writes only static outputs — PNG
figures and CSV tables — plus a `manifest.json` of captions, sample sizes,
statistics, and input checksums. **Report generation is deliberately outside
this workflow**; a report assembles itself from the manifest later.

The workflow compares at three levels:

- **Within a field over time** — CDL is the only input here with field-level
  time, so the five-year sequences live in the CDL section.
- **Across fields within a grower** — every geometry and composition figure.
- **Across growers** — Illinois vs Iowa vs Nebraska at equal scale.

## When to use this workflow

- You need a repeatable, reviewable first look at a multi-farm field sample.
- You want figures that are safe to commit and re-read months later.
- You need the same numbers in a chart, a table, and a caption.
- You are preparing inputs for a separate report, not building a dashboard.

Do **not** use it for interactive exploration, soil analysis, or yield modeling;
those are different EDA workflows or out of scope.

## Prerequisites

Run inside the data-pipeline virtual environment, which already provides
`geopandas`, `pandas`, `scipy`, `matplotlib`, and `contextily`:

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
PY="$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python"
```

The runtime tree must contain, per farm:

```
growers/<grower>/farms/<farm>/
  farm.json                              # state + display_name
  boundary/field_boundaries.geojson      # CSB and/or OSM rows
  derived/tables/*_cdl_*_full_composition.csv
  derived/tables/*_crop_rotation.csv
  derived/tables/*_weather_*_*.csv
```

`farm.json` must carry `state` (e.g. `IL`) and `display_name`; the loader
refuses to guess either.

## Quick start

```bash
cd my-farm-advisor/eda/eda-field-sample

# Full run: boundaries + CDL + weather + 8 maps
"$PY" scripts/run_field_eda.py

# One section while iterating
"$PY" scripts/run_field_eda.py --only cdl

# Offline: draw plain backgrounds instead of fetching imagery
"$PY" scripts/run_field_eda.py --no-basemap

# Any farm set with the required files
"$PY" scripts/run_field_eda.py --all
"$PY" scripts/run_field_eda.py --growers il-dekalb-grower:dekalb-demo-farm
```

Outputs go to `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-sample/`:

```
output/   19 PNG figures
tables/   6 CSV tables
manifest.json
```

Use `--out DIR` to write somewhere else. Use `--no-strict` only when you
intentionally changed the sample shape; otherwise the loader raises before any
figure can silently change meaning.

## Figure inventory

### A — Boundary geometry (3 figures)

| ID | File | Question | Statistical view |
| --- | --- | --- | --- |
| A1 | `a1_field_size_distribution.png` | How big is a field? | Strip plot + ECDF, log acres |
| A2 | `a2_edge_density.png` | How much boundary per acre? | Box + jittered points, log scale |
| A3 | `a3_size_vs_compactness.png` | Does size predict shape? | Scatter + subgroup Spearman rho |

Every metric is measured in the field's **own UTM zone**. Degrees are not a
unit at field scale, and one national projection would distort compactness
ratios between Illinois and Nebraska. Compactness is Polsby-Popper,
`4π·area / perimeter²` (1 = circle).

A2 and A3 keep the one sub-acre Iowa parcel in the plot but annotate it. Because
a single 0.84-acre parcel needs ~330 m of boundary per acre against a 23 m
median for the other 29, any per-acre cost or sampling metric must exclude it
or report it separately. A3 reports the sensitivity directly: rho over all 30
fields, over CSB only, over OSM only, and per grower. None separates from zero,
and the relationship is negative-to-null — **size alone does not predict
shape**; the two least compact fields here are mid-sized strips, while the
single largest field is one of the roundest.

### B — CDL / cropland (5 figures)

| ID | File | Question | Statistical view |
| --- | --- | --- | --- |
| B1 | `b1_crop_composition.png` | What is planted each year? | Acreage-weighted stacked share |
| B2 | `b2_crop_sequence_grid.png` | What does each field do over time? | Dominant-class sequence grid |
| B3 | `b3_crop_transitions.png` | What follows what? | Row-normalized transition matrices |
| B4 | `b4_crop_class_counts.png` | How many field-years does each class win? | Counts by dominant class × grower |
| B5 | `b5_size_vs_diversity.png` | Do bigger fields carry more crop classes? | Scatter + Spearman rho, two definitions |

Shares are **acreage-weighted**, because the composition table counts equal-area
30 m pixels inside each boundary. Rows are **renormalized to 100% per
field-year before aggregating**: the source pipeline drops classes below a
rounding floor, so raw rows sum to 71–100% and a plain mean would inflate
whichever class happens to survive in more fields. B2 keeps a hatched "no data"
cell for the Iowa parcel that has no 2024 CDL row; nothing is imputed.

B4 counts **field-years**, not acres: one field in one year is one unit, so the
bar heights are directly comparable to B2's rows. B5 measures diversity as the
number of crop classes (corn, soybean, other crop) in a field-year and reports
both "every reported class" and "classes covering at least 5% of the field".
The two definitions disagree in sign, and the figure says so: a larger field
contains more 30 m pixels, so the raw count is partly a resolution artifact
rather than an agronomic signal.

### C — Weather (3 figures)

| ID | File | Question | Statistical view |
| --- | --- | --- | --- |
| C1 | `c1_monthly_temperature.png` | What is the monthly climate? | Mean line + year min–max band |
| C2 | `c2_season_precip.png` | How variable is the season? | Per-year season totals |
| C3 | `c3_gdd_vs_precip.png` | Heat vs water | Scatter + within-grower Spearman rho |

NASA POWER is a 0.5° product: all ten fields in a farm share one grid cell.
Every weather number is therefore **farm-level**, and the effective sample is
**3 locations × 5 years = 15 farm-years** — never 300 field-days. Figures and
captions say "farm-year" so the unit cannot be misread. With five seasons per
grower, a within-grower rho reports **direction, not a trend**.

This also means there is **no within-grower comparison across fields**: the ten
field records in a farm carry the same daily values on every date. The loader
measures that (`weather_max_distinct`) and records it as a manifest note; the
within-grower comparison the data supports is **across seasons** (C2, C3).

### Maps (8 figures)

| File | Extent | Field fill |
| --- | --- | --- |
| `map_boundaries_farm_{ia,il,ne}.png` | one farm each | boundary source (CSB / OSM) |
| `map_cdl_farm_{ia,il,ne}.png` | one farm each | years out of five corn-dominant |
| `map_boundaries_all.png` | three panels, one shared window | boundary source |
| `map_cdl_all.png` | three panels, one shared window | years out of five corn-dominant |

The all-farm maps are **three panels at one shared scale**, not one national
extent: at 750 km the 30 fields would be invisible specks, which hides the
comparison the map exists to make.

## Map frame contract

Every map follows `../../data-pipeline/references/field-map-frame.md`:

- **Farm maps** project to the farm's own UTM zone; **all-farm panels** use
  CONUS Albers (EPSG:5070).
- Geometry keeps true projected coordinates so the basemap lands correctly;
  only the **tick labels** are offset to read as distance from each panel's SW
  corner. Ticks sit on round offsets (0, 2 000, …), never on an arbitrary
  absolute coordinate.
- Farm-map viewports are padded 4% so boundaries never touch the frame, with
  extra room at the north-east corner for the arrow. All-farm panels share one
  window sized to the largest farm plus 1 km.
- A **boxed north arrow** sits top-right. There is **no scale bar**; the metre
  tick axes carry distance on every panel.
- Farm layouts are clusters of ten fields rather than one footprint, so no
  rotation is applied and north stays up.
- The CDL maps use a **discrete 6-bin legend** (`0/5` … `5/5`) with a
  `BoundaryNorm`, never a continuous colorbar.

Basemap is Esri World Imagery via `contextily`: greyscaled, `set_clim(35, 235)`
so dark imagery does not compete with the fills, alpha 0.5, no attribution
text in the figure. Tiles are cached under
`${DATA_PIPELINE_DATA_ROOT}/.cache/contextily`; the renderer retries two zoom
levels down before falling back to a plain background.

## Tables

| File | Grain | Contents |
| --- | --- | --- |
| `boundaries_field_metrics.csv` | one row per field | area, perimeter, edge/acre, compactness, source, boundary crop |
| `boundaries_compactness_rho.csv` | one row per subgroup | n, Spearman rho, p |
| `cdl_field_year.csv` | field × year | dominant class/share, corn %, soybean % |
| `cdl_area_share_by_year.csv` | grower × year | acreage-weighted class shares, corn transition rates |
| `cdl_diversity_by_field.csv` | one row per field | area, mean crop classes per field-year, same at the 5% threshold |
| `weather_farm_year.csv` | farm × year | season GDD, precipitation, mean temp, rain days, frost dates |

## Manifest

`manifest.json` is the handoff for report generation:

```json
{
  "skill": "eda-field-sample",
  "dataset": { "growers": [], "states": [], "farms": [], "fields": 30,
               "cdl_years": [2021, 2022, 2023, 2024, 2025],
               "weather_days": 1826, "weather_grain": "farm ..." },
  "figures": [ { "id", "path", "category", "title", "caption", "n", "stats" } ],
  "tables": [ "tables/....csv" ],
  "inputs":  [ { "path", "sha256", "bytes" } ],
  "notes":   [ "documented gaps, e.g. one farm-year with 9/10 fields" ]
}
```

`path` is relative to the output root. `stats` carries the exact numbers quoted
in the caption, so a report never has to re-derive them. `inputs` fingerprints
every source table used, so a reader can tell whether a figure is stale.

A full run rewrites the whole manifest. A `--only` run rewrites it with only
that section's figures — use `--only` for iteration and a full run for the
artifact you keep.

## Analysis rules worth keeping

- **Never multiply weather by fields.** One POWER cell per farm means 15
  farm-years, not 300 field-days.
- **Renormalize CDL composition per field-year** before any cross-field
  aggregate.
- **Measure geometry in local UTM.** Change the dataset, not the projection.
- **Keep outliers, annotate them.** Trimming the sub-acre parcel would hide the
  exact case a per-acre metric has to handle.
- **State the sample size in the figure.** Every subtitle carries n and units.
- **Sign is the finding at n = 5.** Do not fit or rank climates from five
  seasons.
- **No cross-skill duplication.** Weather reference logic lives in
  `weather/`; this workflow only summarizes what the pipeline already derived.

## Report handoff

This workflow stops at the manifest. A report generator should:

1. read `manifest.json`;
2. use each figure's `caption` and `stats` as the report text and inline numbers;
3. copy or embed `output/*.png` in manifest order;
4. surface `notes` as caveats.

Do not edit figures in the report; regenerate them here instead.

## Related docs

- [`examples/field-eda-30-fields/README.md`](examples/field-eda-30-fields/README.md) — the committed example run
- [`AGENTS.md`](AGENTS.md) — local editing and review rules
- [`../INDEX.md`](../INDEX.md) — EDA routing
- [`../../data-pipeline/references/field-map-frame.md`](../../data-pipeline/references/field-map-frame.md) — map frame contract
