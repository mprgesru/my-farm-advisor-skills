"""Data access for the field-sample EDA.

Reads only canonical runtime paths:

    ${DATA_PIPELINE_DATA_ROOT}/data-pipeline/growers/<grower>/farms/<farm>/

The loader deliberately normalises the two boundary schemas (USDA CSB rows
carry ``crop``; OpenStreetMap rows carry ``crop_name``) and computes geometry
metrics in each field's own UTM zone, because degrees are not a unit at field
scale and a single national projection distorts compactness ratios.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

# Farms that make up the Assignment 2 sample. Kept explicit so the example run
# is reproducible; ``discover=False`` callers can pass their own list.
ASSIGNMENT_FARMS: tuple[tuple[str, str], ...] = (
    ("il-dekalb-grower", "dekalb-demo-farm"),
    ("ia-story-grower", "story-demo-farm"),
    ("ne-york-grower", "york-demo-farm"),
)
EXPECTED_FIELDS = 10
EXPECTED_CDL_YEARS = (2021, 2022, 2023, 2024, 2025)
EXPECTED_WEATHER_DAYS = 1826


class DatasetShapeError(RuntimeError):
    """Raised when the runtime data no longer matches the published sample."""


@dataclass
class FarmData:
    grower: str
    farm: str
    state: str
    display_name: str
    fields: gpd.GeoDataFrame
    cdl_long: pd.DataFrame
    cdl_dominant: pd.DataFrame
    rotation: pd.DataFrame
    weather: pd.DataFrame
    metrics: pd.DataFrame = field(default_factory=pd.DataFrame)
    weather_fields: int = 1
    weather_max_distinct: int = 1

    @property
    def label(self) -> str:
        return self.state


def data_root() -> Path:
    raw = os.environ.get("DATA_PIPELINE_DATA_ROOT")
    if not raw:
        raise RuntimeError(
            "DATA_PIPELINE_DATA_ROOT is not set. Export it, e.g.\n"
            "  export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime"
        )
    return Path(raw).expanduser().resolve() / "data-pipeline"


def _utm_epsg(lon: float, lat: float) -> int:
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    return (32600 if lat >= 0 else 32700) + zone


def _first_match(directory: Path, pattern: str) -> Path | None:
    hits = sorted(directory.glob(pattern))
    return hits[-1] if hits else None


def _read_farm_meta(farm_dir: Path) -> dict:
    path = farm_dir / "farm.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _normalise_boundaries(fields: gpd.GeoDataFrame, state: str) -> gpd.GeoDataFrame:
    out = fields.copy()
    source = out.get("source", pd.Series("", index=out.index)).astype(str)
    out["source_label"] = source.str.contains("csb", case=False).map(
        {True: "CSB", False: "OSM"}
    )

    crop = out.get("crop", pd.Series(pd.NA, index=out.index, dtype="object"))
    crop_name = out.get(
        "crop_name", pd.Series(pd.NA, index=out.index, dtype="object")
    )
    out["boundary_crop"] = crop.where(crop.notna(), crop_name)
    out["state"] = state
    return out


def _geometry_metrics(fields: gpd.GeoDataFrame, grower: str) -> pd.DataFrame:
    """Per-field geometry metrics measured in the field's own UTM zone."""
    rows = []
    for row in fields.itertuples(index=False):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        centroid = geom.centroid
        local = gpd.GeoSeries([geom], crs=fields.crs).to_crs(
            _utm_epsg(centroid.x, centroid.y)
        )
        area_m2 = float(local.area.iloc[0])
        perimeter_m = float(local.length.iloc[0])
        acres = area_m2 / 4046.8564224
        rows.append(
            {
                "field_id": row.field_id,
                "grower": grower,
                "state": row.state,
                "source": row.source_label,
                "boundary_crop": row.boundary_crop,
                "area_acres": acres,
                "perimeter_m": perimeter_m,
                "edge_m_per_acre": perimeter_m / acres if acres else None,
                "polsby_popper": (
                    4.0 * math.pi * area_m2 / (perimeter_m**2)
                    if perimeter_m
                    else None
                ),
            }
        )
    return pd.DataFrame(rows)


def _load_cdl(tables: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    composition_path = _first_match(tables, "*_cdl_*_full_composition.csv")
    if composition_path is None:
        raise FileNotFoundError(f"no CDL composition table under {tables}")
    cdl = pd.read_csv(composition_path)

    # Dominant class per field-year: the single largest share.
    dominant = (
        cdl.sort_values(["field_id", "year", "pct"])
        .groupby(["field_id", "year"], as_index=False)
        .last()
        .loc[:, ["field_id", "year", "crop_name", "pct"]]
        .rename(columns={"crop_name": "dominant_crop", "pct": "dominant_pct"})
    )

    rotation_path = _first_match(tables, "*_crop_rotation.csv")
    rotation = pd.read_csv(rotation_path) if rotation_path else pd.DataFrame()
    return cdl, dominant, rotation


def _load_weather(tables: Path) -> tuple[pd.DataFrame, int, int]:
    path = _first_match(tables, "*_weather_*_*.csv")
    if path is None:
        raise FileNotFoundError(f"no weather table under {tables}")
    weather = pd.read_csv(path, parse_dates=["date"])
    # NASA POWER is a 0.5 deg grid: every field in a farm shares one cell.
    # Confirm that before collapsing, so the note we publish is measured, not
    # assumed. ``weather_max_distinct == 1`` means all field rows carry the
    # same daily value and a within-grower across-fields comparison has no
    # variance to analyse.
    value_cols = [c for c in ("T2M", "PRECTOTCORR") if c in weather.columns]
    n_fields = int(weather["field_id"].nunique()) if "field_id" in weather else 1
    max_distinct = (
        int(weather.groupby("date")[value_cols].nunique().to_numpy().max())
        if value_cols
        else 1
    )
    weather = (
        weather.sort_values("date")
        .drop_duplicates(subset=["date"])
        .reset_index(drop=True)
    )
    return weather, n_fields, max_distinct


def load_farm(grower: str, farm: str) -> FarmData:
    root = data_root() / "growers" / grower / "farms" / farm
    if not root.exists():
        raise FileNotFoundError(f"farm directory not found: {root}")

    meta = _read_farm_meta(root)
    state = str(meta.get("state") or "").strip().upper()
    if not state:
        raise ValueError(f"{root}/farm.json has no state; cannot label the grower")

    boundaries = gpd.read_file(root / "boundary" / "field_boundaries.geojson")
    fields = _normalise_boundaries(boundaries, state)
    fields.attrs["grower"] = grower

    tables = root / "derived" / "tables"
    cdl, dominant, rotation = _load_cdl(tables)
    weather, weather_fields, weather_max_distinct = _load_weather(tables)
    metrics = _geometry_metrics(fields, grower)

    return FarmData(
        grower=grower,
        farm=farm,
        state=state,
        display_name=str(meta.get("display_name") or farm),
        fields=fields,
        cdl_long=cdl,
        cdl_dominant=dominant,
        rotation=rotation,
        weather=weather,
        metrics=metrics,
        weather_fields=weather_fields,
        weather_max_distinct=weather_max_distinct,
    )


def discover_farms() -> list[tuple[str, str]]:
    """Every grower/farm pair that has boundaries and a CDL composition table."""
    root = data_root() / "growers"
    found: list[tuple[str, str]] = []
    for grower_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        farms_dir = grower_dir / "farms"
        if not farms_dir.exists():
            continue
        for farm_dir in sorted(p for p in farms_dir.iterdir() if p.is_dir()):
            has_boundary = (farm_dir / "boundary" / "field_boundaries.geojson").exists()
            has_cdl = bool(
                list((farm_dir / "derived" / "tables").glob("*_cdl_*_composition.csv"))
            )
            if has_boundary and has_cdl:
                found.append((grower_dir.name, farm_dir.name))
    return found


def load_dataset(pairs: list[tuple[str, str]] | None = None) -> list[FarmData]:
    pairs = list(pairs or ASSIGNMENT_FARMS)
    farms = [load_farm(grower, farm) for grower, farm in pairs]
    return sorted(farms, key=lambda f: f.state)


def validate_dataset(farms: list[FarmData], *, strict: bool = True) -> list[str]:
    """Check the sample still has the shape the published figures claim.

    Returns human-readable notes (known gaps). Raises ``DatasetShapeError`` for
    anything that would silently change a figure's meaning.
    """
    notes: list[str] = []
    problems: list[str] = []

    if len(farms) != 3:
        problems.append(f"expected 3 growers, found {len(farms)}")
    for farm in farms:
        n = len(farm.metrics)
        if n != EXPECTED_FIELDS:
            problems.append(f"{farm.grower}: {n} fields (expected {EXPECTED_FIELDS})")

        years = tuple(sorted(farm.cdl_long["year"].unique().tolist()))
        if years != EXPECTED_CDL_YEARS:
            problems.append(f"{farm.grower}: CDL years {years}")

        days = len(farm.weather)
        if days != EXPECTED_WEATHER_DAYS:
            problems.append(f"{farm.grower}: {days} weather days")

        # The loader keeps one series per farm because NASA POWER resolves a
        # single 0.5 deg cell. If fields ever carry different values, that
        # assumption is wrong and every weather figure must be revisited.
        if farm.weather_max_distinct > 1:
            problems.append(
                f"{farm.grower}: weather varies across fields; the farm-level "
                "loader would discard real variation"
            )

        # Known, documented gap: the sub-acre Iowa sliver has no 2024 pixel.
        per_year = farm.cdl_dominant.groupby("year")["field_id"].nunique().to_dict()
        for year, count in sorted(per_year.items()):
            if count < EXPECTED_FIELDS:
                notes.append(
                    f"{farm.grower}: {year} CDL covers {count}/{EXPECTED_FIELDS} fields"
                )

    if problems and strict:
        raise DatasetShapeError(
            "runtime data no longer matches the published sample:\n  - "
            + "\n  - ".join(problems)
        )

    shared = [
        farm
        for farm in farms
        if farm.weather_fields > 1 and farm.weather_max_distinct == 1
    ]
    if len(shared) == len(farms) and farms:
        notes.append(
            "weather: all field locations in a farm resolve to one NASA POWER series, "
            "so a within-grower across-fields comparison has no variance; seasons are "
            "the within-grower comparison"
        )
    return notes
