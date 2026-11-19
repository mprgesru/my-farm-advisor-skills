# Local Instructions

## Purpose

This folder owns the **field-sample EDA** workflow: static, reproducible
figures and tables comparing field boundaries, CDL crop history, and farm-level
weather across a multi-grower sample. Report assembly is out of scope and lives
in a separate report step that consumes `manifest.json`.

## Safe edit scope

Edits should stay in this folder and its children unless the user explicitly
asks for a broader skill change. Do not change parent `SKILL.md`, sibling EDA
workflows, or root policy from a subskill task unless explicitly requested.

## Layout

```
eda-field-sample/
  GUIDE.md                  # workflow, figure inventory, analysis rules
  AGENTS.md                 # this file
  scripts/run_field_eda.py  # thin entrypoint into src/cli.py
  src/
    style.py                # shared palette, figure/save helpers
    loaders.py              # runtime data access, dataset validation
    boundaries.py           # A1-A3
    cdl.py                  # B1-B5
    weather.py              # C1-C3
    maps.py                 # 8 geospatial maps
    cli.py                  # arguments, manifest writing
  examples/field-eda-30-fields/
    README.md
    output/                 # 19 committed PNGs
    tables/                 # 6 committed CSVs
```

Do **not** add a nested `SKILL.md` or a top-level Skill heading here; the EDA
index routes to `GUIDE.md`.

## Read nearby docs first

Read `GUIDE.md` first. If routing context is needed, read `../INDEX.md` and
`../../SKILL.md`. For map work, read
`../../data-pipeline/references/field-map-frame.md` before changing a renderer.

## Data contract

- Read only canonical runtime paths:
  `${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/`.
- Weather is farm-level (NASA POWER 0.5° grid). Never multiply by field count.
- CDL composition rows are renormalized per field-year before aggregation.
- Geometry metrics use each field's own UTM zone.
- Keep the documented gaps (e.g. one Iowa field-year with no 2024 CDL row) as
  notes, never impute them silently.

## Local validation

Run the workflow against the runtime sample before committing:

```bash
export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
cd my-farm-advisor/eda/eda-field-sample
"$DATA_PIPELINE_DATA_ROOT/data-pipeline/.venv/bin/python" scripts/run_field_eda.py
```

Then run `./scripts/validate.sh` from the repository root.

## Figure review gate

Every committed PNG is a gallery figure under `examples/**/output/` and must
pass the five-point review in `../../../CONTRIBUTING.md` before it is committed:

1. no empty or under-covered panels;
2. field-map frame contract (local-metre axes, north arrow, no scale bar);
3. halo clip where raster is involved (not applicable to this workflow);
4. colorbar semantics — discrete legend for categorical corn years;
5. legible labels at README size.

A change to `src/style.py` or `src/maps.py` re-triggers review of **every**
figure those modules draw. Record the verdict in the commit message.

## Local-delta-only reminder

This nested AGENTS.md only records instructions that differ from the parent or
root files. Do not duplicate root-wide asset, vendor, or validation policy here
except this pointer to `../../../AGENTS.md`.
