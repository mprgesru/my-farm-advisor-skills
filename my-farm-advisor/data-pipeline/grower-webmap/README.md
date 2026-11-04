# Grower Web Map

Generate one lightweight, interactive HTML map for each data-pipeline grower.
The map shows every field across every farm owned by the grower, using the
actual boundary polygons written by the farm pipeline.

This is the Assignment 1 grower-level web map workflow. It is intentionally a
separate reporting command rather than a farm-pipeline step because one map can
span multiple farms.

## What the map includes

- Leaflet from CDN.
- Esri World Imagery satellite basemap by default, with an optional
  OpenStreetMap streets layer.
- All field polygons for the selected grower.
- Automatic fit-to-fields, zoom in/out controls, pan, and field hover states.
- Clickable field popups showing:
  - grower
  - farm
  - field name
  - field ID
  - area in acres
  - dominant 2025 CDL crop
  - county and state
- A sidebar field list that zooms to a field and opens its popup.
- A **Fit all fields** control.

The HTML does not embed satellite imagery, rasters, or base64 data. Only
simplified polygon geometry and a small metadata payload are embedded.

## Inputs

The generator reads the canonical runtime tree:

```text
growers/<grower>/grower.json
growers/<grower>/farms/*/farm.json
growers/<grower>/farms/*/boundary/field_boundaries.geojson
growers/<grower>/farms/*/manifests/field-inventory.csv
growers/<grower>/farms/*/fields/<field>/field.json
growers/<grower>/farms/*/derived/tables/*_2025_cdl.csv
```

Location labels come from the field-boundary attributes (`state_fips` and
`county_name`), not from `farm.json`. This avoids stale state metadata in
existing runtime data.

## Outputs

For each grower:

```text
growers/<grower>/derived/webmaps/<grower>_webmap.html
growers/<grower>/manifests/grower_webmap.json
```

The manifest records the source boundaries, field count, output size, farms,
and field metadata used for the map.

## Usage

Run from the runtime source copy:

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug il-dekalb-grower \
  --grower-slug ia-story-grower
```

Render every grower with fields:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py --all-growers
```

Preview without writing:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug il-dekalb-grower \
  --dry-run
```

### Options

| Option | Behavior |
| --- | --- |
| `--grower-slug <slug>` | Render one grower; repeat for multiple growers. |
| `--all-growers` | Render every grower that has at least one polygon. |
| `--output-dir <path>` | Override the output directory. Relative paths resolve under the runtime data root. |
| `--dry-run` | Discover farms/fields and print planned outputs without writing files. |

With no selector, the command renders all growers.

## Install into the runtime

The installer copies the baseline `src/` tree into the runtime, including the
new generator. It does not copy this documentation directory and does not touch
grower data.

```bash
export DATA_PIPELINE_DATA_ROOT=/absolute/path/to/my-farm-advisor-runtime
cd my-farm-advisor/data-pipeline
./scripts/install.sh \
  --data-root "$DATA_PIPELINE_DATA_ROOT" \
  --persist user \
  --non-interactive \
  --force-refresh \
  --no-install-deps
```

No new Python dependencies are required.

## Determinism

The map is derived only from the current runtime boundary files, inventory, and
CDL tables. Re-running the command against unchanged runtime data produces the
same field set and metadata. Tile imagery is fetched by the browser at view
time, so the basemap appearance depends on the online Esri service and the
viewer's network access.
