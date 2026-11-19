"""CLI for the field-sample EDA.

    export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
    python scripts/run_field_eda.py                 # all four sections
    python scripts/run_field_eda.py --only boundaries,cdl
    python scripts/run_field_eda.py --no-basemap    # offline maps

Outputs land under ``${DATA_PIPELINE_DATA_ROOT}/data-pipeline/eda/field-sample``:
``output/*.png``, ``tables/*.csv`` and ``manifest.json`` (figure captions plus
input checksums) for a downstream report to consume.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import boundaries
import cdl
import maps
import style
import weather
from loaders import (
    ASSIGNMENT_FARMS,
    EXPECTED_CDL_YEARS,
    data_root,
    discover_farms,
    load_dataset,
    validate_dataset,
)

SECTIONS = ("boundaries", "cdl", "weather", "maps")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_pairs(raw: str | None) -> list[tuple[str, str]]:
    if not raw:
        return list(ASSIGNMENT_FARMS)
    pairs = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise SystemExit(
                f"--growers expects grower:farm pairs, e.g. il-dekalb-grower:dekalb-demo-farm (got {item!r})"
            )
        grower, farm = item.split(":", 1)
        pairs.append((grower.strip(), farm.strip()))
    return pairs


def _inputs_for(farms) -> list[dict]:
    entries = []
    for farm in farms:
        root = data_root() / "growers" / farm.grower / "farms" / farm.farm
        candidates = [
            root / "boundary" / "field_boundaries.geojson",
            *sorted((root / "derived" / "tables").glob("*_cdl_*_full_composition.csv")),
            *sorted((root / "derived" / "tables").glob("*_crop_rotation.csv")),
            *sorted((root / "derived" / "tables").glob("*_weather_*_*.csv")),
        ]
        for path in candidates:
            if path.exists():
                entries.append(
                    {
                        "path": str(path.relative_to(data_root())),
                        "sha256": _sha256(path),
                        "bytes": path.stat().st_size,
                    }
                )
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Field-sample EDA (static PNG + CSV outputs)")
    parser.add_argument(
        "--growers",
        default="",
        help="comma-separated grower:farm pairs; defaults to the Assignment 2 sample",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="every grower/farm that has boundaries and a CDL composition table",
    )
    parser.add_argument(
        "--only",
        default=",".join(SECTIONS),
        help=f"comma-separated subset of {','.join(SECTIONS)}",
    )
    parser.add_argument("--out", default="", help="output root (default: $DATA_PIPELINE_DATA_ROOT/data-pipeline/eda/field-sample)")
    parser.add_argument("--no-basemap", action="store_true", help="skip the Esri imagery basemap")
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="do not raise when the dataset shape differs from the published sample",
    )
    args = parser.parse_args(argv)

    requested = [s.strip() for s in args.only.split(",") if s.strip()]
    unknown = [s for s in requested if s not in SECTIONS]
    if unknown:
        raise SystemExit(f"unknown section(s): {', '.join(unknown)} (choose from {', '.join(SECTIONS)})")

    pairs = discover_farms() if args.all else _parse_pairs(args.growers)
    style.apply_style()
    farms = load_dataset(pairs)
    notes = validate_dataset(farms, strict=not args.no_strict)

    out_root = Path(args.out).expanduser().resolve() if args.out else data_root() / "eda" / "field-sample"
    out_dir = out_root / "output"
    table_dir = out_root / "tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)

    print(f"dataset: {len(farms)} growers")
    for farm in farms:
        print(
            f"  {farm.state}  {farm.grower}/{farm.farm}  "
            f"fields={len(farm.metrics)}  cdl_years={farm.cdl_long['year'].nunique()}  "
            f"weather_days={len(farm.weather)}"
        )
    for note in notes:
        print(f"  note: {note}")

    figures: list[dict] = []
    if "boundaries" in requested:
        print("\n[boundaries]")
        figures += boundaries.build(farms, out_dir)
    if "cdl" in requested:
        print("\n[cdl]")
        figures += cdl.build(farms, out_dir)
    if "weather" in requested:
        print("\n[weather]")
        figures += weather.build(farms, out_dir)
    if "maps" in requested:
        print("\n[maps]")
        figures += maps.build(farms, out_dir, basemap=not args.no_basemap)

    for figure in figures:
        rel = figure["path"].relative_to(out_root).as_posix()
        figure["path"] = rel
        print(f"  {rel}")

    manifest = {
        "skill": "eda-field-sample",
        "dataset": {
            "growers": [f.grower for f in farms],
            "states": [f.state for f in farms],
            "farms": [f.farm for f in farms],
            "fields": int(sum(len(f.metrics) for f in farms)),
            "cdl_years": list(EXPECTED_CDL_YEARS),
            "weather_days": int(max(len(f.weather) for f in farms)),
            "weather_grain": "farm (NASA POWER 0.5 deg grid cell)",
        },
        "figures": figures,
        "tables": sorted(
            p.relative_to(out_root).as_posix() for p in table_dir.glob("*.csv")
        ),
        "inputs": _inputs_for(farms),
        "notes": notes,
    }
    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"\nfigures: {len(figures)}")
    print(f"manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
