# Grower Web Map Local Instructions

## Purpose

This folder documents the grower-level interactive web map workflow. The
runnable generator lives in `../src/scripts/reporting/generate_grower_webmap.py`
so it is copied into the runtime by the normal installer.

## Safe edit scope

Edits should stay in this folder, the reporting generator, and the shared path
helpers used by the generator. Do not change farm-pipeline orchestration or
ingest behavior for a web-map-only task.

## Runtime contract

- `DATA_PIPELINE_DATA_ROOT` is required and must be absolute.
- Read boundaries from `growers/<grower>/farms/<farm>/boundary/field_boundaries.geojson`.
- Never regenerate, approximate, or synthesize field boundaries for this map.
- Write HTML to `growers/<grower>/derived/webmaps/<grower>_webmap.html`.
- Write the manifest to `growers/<grower>/manifests/grower_webmap.json`.
- Keep generated HTML under the runtime root and out of Git.
- Do not embed raster imagery, full data bundles, or base64 payloads in the HTML.
- The Esri World Imagery basemap is loaded by the browser from the internet.

## Command runbook

Install the generator into the runtime source copy:

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

Render named growers:

```bash
cd "${DATA_PIPELINE_DATA_ROOT}/data-pipeline/src"
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug il-dekalb-grower \
  --grower-slug ia-story-grower
```

Render all growers with fields:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py --all-growers
```

Preview planned outputs:

```bash
"${DATA_PIPELINE_DATA_ROOT}/data-pipeline/.venv/bin/python" \
  scripts/reporting/generate_grower_webmap.py \
  --grower-slug il-dekalb-grower \
  --dry-run
```

## Validation

For each generated map:

- Confirm the HTML exists and is below 200 KB.
- Confirm the embedded GeoJSON feature count matches the inventory field count.
- Confirm the page contains the Esri World Imagery tile URL, Leaflet map setup,
  zoom controls, `fitBounds`, popups, and the field-list controls.
- Confirm grower, farm, and field metadata are present.
- Confirm no base64 or raster payload is embedded.
- Confirm generated files remain outside the Git worktree.

Run repository validation after documentation or path-helper changes:

```bash
cd ..
./scripts/validate.sh
```

## Structure note

Do not add a nested `SKILL.md` here. OpenCode treats a nested `SKILL.md` as a
separate skill; this repository routes nested workflows through `README.md`,
`AGENTS.md`, and `GUIDE.md` files instead.
