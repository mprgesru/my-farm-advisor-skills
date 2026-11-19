#!/usr/bin/env python3
"""Generate a lightweight, grower-level interactive field web map.

The map reads the canonical field boundaries produced by the data pipeline and
embeds only the polygon geometry and a small metadata payload. Satellite tiles
are loaded from Esri at view time; no imagery or raster data is embedded.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.paths import (  # noqa: E402
    DATA_ROOT,
    GROWERS_ROOT,
    SHARED_ROOT,
    ensure_data_root_path,
    farm_boundary_path,
    grower_dir,
    grower_manifest_path,
    grower_webmap_path,
    validate_path_slug,
)

_STATE_FALLBACK = {
    "17": "IL",
    "19": "IA",
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _relative(path: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(DATA_ROOT))
    except ValueError:
        return str(path)


def _state_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    path = SHARED_ROOT / "geoadmin" / "l1_states" / "states_usa.geojson"
    payload = _load_json(path, {})
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        fips = str(props.get("state_fips") or "").zfill(2)
        if not fips:
            continue
        labels[fips] = str(props.get("state_code") or props.get("state_name") or fips)
    labels.update({key: value for key, value in _STATE_FALLBACK.items() if key not in labels})
    return labels


def _pretty_slug(value: str) -> str:
    parts = [part for part in value.replace("_", "-").split("-") if part]
    if not parts:
        return value
    if parts[0].lower() in {"il", "ia", "in", "mn", "mo", "ne", "wi"}:
        parts[0] = parts[0].upper()
    return " ".join(part.capitalize() if part.islower() else part for part in parts)


def _display_name(payload: dict[str, Any], slug: str) -> str:
    name = str(payload.get("display_name") or "").strip()
    if name and name != slug:
        return name
    return _pretty_slug(slug)


def _field_display_name(payload: dict[str, Any], slug: str) -> str:
    name = str(payload.get("display_name") or "").strip()
    if name and name != slug:
        return name
    return slug


def _load_inventory(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {
            str(row.get("field_id", "")).strip(): str(row.get("field_slug", "")).strip()
            for row in csv.DictReader(handle)
            if row.get("field_id")
        }


def _load_crop_lookup(farm_path: Path) -> dict[str, str]:
    tables = sorted((farm_path / "derived" / "tables").glob("*_2025_cdl.csv"))
    if not tables:
        tables = sorted((farm_path / "derived" / "tables").glob("*_cdl.csv"), reverse=True)
    if not tables:
        return {}

    best: dict[str, tuple[float, str]] = {}
    with tables[0].open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            field_id = str(row.get("field_id", "")).strip()
            crop_name = str(row.get("crop_name", "")).strip()
            if not field_id or not crop_name:
                continue
            try:
                pct = float(row.get("pct") or 0)
            except ValueError:
                pct = 0.0
            previous = best.get(field_id)
            if previous is None or pct > previous[0]:
                best[field_id] = (pct, crop_name)
    return {field_id: crop for field_id, (_, crop) in best.items()}


def _round_coordinates(value: Any) -> Any:
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    if isinstance(value, list):
        return [_round_coordinates(item) for item in value]
    return value


def _iter_positions(coordinates: Any):
    if (
        isinstance(coordinates, list)
        and len(coordinates) >= 2
        and all(isinstance(value, (int, float)) for value in coordinates[:2])
    ):
        yield float(coordinates[0]), float(coordinates[1])
        return
    if isinstance(coordinates, list):
        for item in coordinates:
            yield from _iter_positions(item)


def _load_field_metadata(farm_path: Path, field_slug: str) -> dict[str, Any]:
    return _load_json(farm_path / "fields" / field_slug / "field.json", {})


def _build_grower_payload(
    grower_slug: str,
    *,
    state_labels: dict[str, str],
) -> dict[str, Any] | None:
    grower_path = grower_dir(grower_slug)
    grower_meta = _load_json(grower_path / "grower.json", {})
    grower_label = _display_name(grower_meta, grower_slug)

    features: list[dict[str, Any]] = []
    farms: list[dict[str, Any]] = []
    source_boundaries: list[str] = []

    for farm_path in sorted((grower_path / "farms").glob("*")):
        if not farm_path.is_dir():
            continue
        farm_slug = farm_path.name
        boundary_path = farm_boundary_path(grower_slug, farm_slug)
        if not boundary_path.exists():
            print(f"warn  {grower_slug}/{farm_slug}: missing {boundary_path}", file=sys.stderr)
            continue

        farm_meta = _load_json(farm_path / "farm.json", {})
        farm_label = _display_name(farm_meta, farm_slug)
        inventory = _load_inventory(farm_path / "manifests" / "field-inventory.csv")
        crop_lookup = _load_crop_lookup(farm_path)
        boundary = _load_json(boundary_path, {"type": "FeatureCollection", "features": []})
        farm_features = boundary.get("features") or []

        seen_ids: set[str] = set()
        for index, feature in enumerate(farm_features):
            props = feature.get("properties") or {}
            field_id = str(props.get("field_id") or "").strip()
            if not field_id:
                continue
            seen_ids.add(field_id)
            field_slug = inventory.get(field_id) or str(props.get("field_slug") or field_id)
            field_meta = _load_field_metadata(farm_path, field_slug)
            field_name = _field_display_name(field_meta, field_slug)
            state_fips = str(props.get("state_fips") or "").zfill(2)
            state_code = state_labels.get(state_fips, state_fips or "")
            try:
                area_acres = round(float(props.get("area_acres") or 0), 1)
            except (TypeError, ValueError):
                area_acres = 0.0

            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": feature.get("geometry", {}).get("type"),
                        "coordinates": _round_coordinates(
                            feature.get("geometry", {}).get("coordinates")
                        ),
                    },
                    "properties": {
                        "field_id": field_id,
                        "field_slug": field_slug,
                        "field_name": field_name,
                        "grower": grower_label,
                        "grower_slug": grower_slug,
                        "farm": farm_label,
                        "farm_slug": farm_slug,
                        "area_acres": area_acres,
                        "crop": crop_lookup.get(field_id) or str(props.get("crop_name") or ""),
                        "county": str(props.get("county_name") or ""),
                        "county_fips": str(props.get("county_fips") or "").zfill(3),
                        "state": state_code,
                        "state_fips": state_fips,
                    },
                }
            )

        missing = sorted(set(inventory) - seen_ids)
        if missing:
            print(
                f"warn  {grower_slug}/{farm_slug}: inventory field(s) without polygons: "
                + ", ".join(missing),
                file=sys.stderr,
            )
        farms.append(
            {
                "farm_slug": farm_slug,
                "farm_name": farm_label,
                "field_count": len([f for f in features if f["properties"]["farm_slug"] == farm_slug]),
                "boundary": _relative(boundary_path),
            }
        )
        source_boundaries.append(_relative(boundary_path))

    if not features:
        return None

    features.sort(
        key=lambda feature: (
            feature["properties"]["farm"],
            feature["properties"]["field_name"],
            feature["properties"]["field_id"],
        )
    )
    positions = [
        position
        for feature in features
        for position in _iter_positions(feature["geometry"]["coordinates"])
    ]
    if not positions:
        return None
    lons = [lon for lon, _ in positions]
    lats = [lat for _, lat in positions]

    return {
        "grower_slug": grower_slug,
        "grower_name": grower_label,
        "farms": farms,
        "source_boundaries": sorted(set(source_boundaries)),
        "center": [sum(lats) / len(lats), sum(lons) / len(lons)],
        "fields": {"type": "FeatureCollection", "features": features},
        "field_count": len(features),
        "state_summary": ", ".join(
            sorted({str(feature["properties"]["state"]) for feature in features if feature["properties"]["state"]})
        ),
    }


def _field_items_html(features: list[dict[str, Any]]) -> str:
    items: list[str] = []
    for feature in features:
        props = feature["properties"]
        meta_parts = [html.escape(str(props["farm"]))]
        if props.get("crop"):
            meta_parts.append(html.escape(str(props["crop"])))
        if props.get("area_acres"):
            meta_parts.append(f"{float(props['area_acres']):.1f} ac")
        items.append(
            '<button class="field-item" type="button" data-field-id="{field_id}">'
            '<span class="field-name">{field_name}</span>'
            '<span class="field-meta">{meta}</span>'
            "</button>".format(
                field_id=html.escape(str(props["field_id"])),
                field_name=html.escape(str(props["field_name"])),
                meta=" · ".join(meta_parts),
            )
        )
    return "\n".join(items)


def _render_html(payload: dict[str, Any]) -> str:
    features = payload["fields"]["features"]
    map_data = json.dumps(payload["fields"], separators=(",", ":"), ensure_ascii=False)
    map_data = map_data.replace("</", "<\\/")
    title = f"{payload['grower_name']} — Grower Field Map"
    subtitle = (
        f"{payload['field_count']} fields · {len(payload['farms'])} farm"
        f"{'s' if len(payload['farms']) != 1 else ''} · {payload['state_summary']}"
    )
    field_items = _field_items_html(features)
    center = payload["center"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {{
    --panel: #111827;
    --panel-2: #1f2937;
    --line: #334155;
    --text: #e5e7eb;
    --muted: #94a3b8;
    --accent: #2dd4bf;
    --accent-2: #f59e0b;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{ height: 100%; margin: 0; }}
  body {{
    display: flex;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0b1220;
    color: var(--text);
  }}
  #sidebar {{
    width: 340px;
    min-width: 300px;
    max-width: 380px;
    display: flex;
    flex-direction: column;
    background: var(--panel);
    border-right: 1px solid var(--line);
    z-index: 10;
  }}
  #sidebar header {{
    padding: 20px 20px 16px;
    border-bottom: 1px solid var(--line);
  }}
  #sidebar h1 {{
    margin: 0 0 6px;
    font-size: 1.25rem;
    line-height: 1.25;
  }}
  .subtitle {{
    margin: 0 0 14px;
    color: var(--muted);
    font-size: 0.85rem;
  }}
  #fit-all {{
    width: 100%;
    padding: 10px 12px;
    border: 1px solid #0f766e;
    border-radius: 8px;
    background: #0f766e;
    color: white;
    font-weight: 650;
    cursor: pointer;
  }}
  #fit-all:hover {{ background: #115e59; }}
  #fields {{
    overflow-y: auto;
    padding: 12px;
  }}
  .field-item {{
    display: block;
    width: 100%;
    margin: 0 0 8px;
    padding: 10px 12px;
    text-align: left;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: var(--panel-2);
    color: var(--text);
    cursor: pointer;
  }}
  .field-item:hover {{
    border-color: var(--accent);
    background: #243447;
  }}
  .field-name {{
    display: block;
    font-weight: 650;
    font-size: 0.9rem;
    margin-bottom: 3px;
    overflow-wrap: anywhere;
  }}
  .field-meta {{
    display: block;
    color: var(--muted);
    font-size: 0.76rem;
    line-height: 1.3;
  }}
  #map {{ flex: 1; min-height: 100vh; }}
  .popup h3 {{
    margin: 0 0 8px;
    font-size: 1rem;
  }}
  .popup-row {{
    display: flex;
    justify-content: space-between;
    gap: 16px;
    padding: 3px 0;
    border-top: 1px solid #e5e7eb;
    font-size: 0.82rem;
  }}
  .popup-row span {{ color: #475569; }}
  .popup-row strong {{ text-align: right; }}
  .leaflet-popup-content {{ margin: 14px 16px; }}
  @media (max-width: 800px) {{
    body {{ flex-direction: column; }}
    #sidebar {{
      width: 100%;
      max-width: none;
      max-height: 45vh;
      min-width: 0;
      border-right: 0;
      border-bottom: 1px solid var(--line);
    }}
    #map {{ min-height: 55vh; }}
  }}
</style>
</head>
<body>
  <aside id="sidebar">
    <header>
      <h1>{html.escape(payload["grower_name"])}</h1>
      <p class="subtitle">{html.escape(subtitle)}</p>
      <button id="fit-all" type="button">Fit all fields</button>
    </header>
    <div id="fields">
      {field_items}
    </div>
  </aside>
  <div id="map"></div>
  <script>
    const mapData = {map_data};
    const map = L.map('map', {{ zoomControl: true, preferCanvas: true }})
      .setView([{center[0]:.6f}, {center[1]:.6f}], 12);

    const satellite = L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{
        maxZoom: 19,
        attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'
      }}
    ).addTo(map);

    const streets = L.tileLayer(
      'https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
      {{
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
      }}
    );

    L.control.layers({{ 'Satellite': satellite, 'Streets': streets }}, null, {{ collapsed: true }}).addTo(map);
    const fieldLayers = {{}};

    function esc(value) {{
      return String(value ?? '').replace(/[&<>"']/g, function (char) {{
        return {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }}[char];
      }});
    }}

    function popupHtml(props) {{
      const area = Number(props.area_acres || 0).toFixed(1);
      const county = props.county ? esc(props.county) + ' County' : '—';
      const state = props.state ? ' ' + esc(props.state) : '';
      return '<div class="popup">' +
        '<h3>' + esc(props.field_name) + '</h3>' +
        '<div class="popup-row"><span>Grower</span><strong>' + esc(props.grower) + '</strong></div>' +
        '<div class="popup-row"><span>Farm</span><strong>' + esc(props.farm) + '</strong></div>' +
        '<div class="popup-row"><span>Field ID</span><strong>' + esc(props.field_id) + '</strong></div>' +
        '<div class="popup-row"><span>Area</span><strong>' + area + ' acres</strong></div>' +
        '<div class="popup-row"><span>2025 crop</span><strong>' + esc(props.crop || '—') + '</strong></div>' +
        '<div class="popup-row"><span>Location</span><strong>' + county + state + '</strong></div>' +
        '</div>';
    }}

    function baseStyle() {{
      return {{ color: '#fbbf24', weight: 2, opacity: 0.95, fillColor: '#2dd4bf', fillOpacity: 0.22 }};
    }}

    function selectedStyle() {{
      return {{ color: '#ffffff', weight: 3, opacity: 1, fillColor: '#f97316', fillOpacity: 0.45 }};
    }}

    const geoLayer = L.geoJSON(mapData, {{
      style: baseStyle,
      onEachFeature: function (feature, layer) {{
        const props = feature.properties || {{}};
        fieldLayers[props.field_id] = layer;
        layer.bindTooltip(props.field_name, {{ sticky: true }});
        layer.bindPopup(popupHtml(props), {{ maxWidth: 340 }});
        layer.on('mouseover', function () {{ layer.setStyle({{ weight: 3, fillOpacity: 0.34 }}); }});
        layer.on('mouseout', function () {{
          if (!layer._selected) {{ geoLayer.resetStyle(layer); }}
        }});
        layer.on('click', function () {{ selectLayer(layer); }});
      }}
    }}).addTo(map);

    function selectLayer(layer) {{
      geoLayer.eachLayer(function (item) {{
        item._selected = false;
        geoLayer.resetStyle(item);
      }});
      layer._selected = true;
      layer.setStyle(selectedStyle());
      layer.bringToFront();
      layer.openPopup();
    }}

    function fitAll() {{
      if (geoLayer.getLayers().length) {{
        map.fitBounds(geoLayer.getBounds(), {{ padding: [24, 24] }});
      }}
    }}

    document.querySelectorAll('.field-item').forEach(function (button) {{
      button.addEventListener('click', function () {{
        const layer = fieldLayers[button.dataset.fieldId];
        if (!layer) return;
        map.fitBounds(layer.getBounds(), {{ padding: [24, 24], maxZoom: 17 }});
        selectLayer(layer);
      }});
    }});

    document.getElementById('fit-all').addEventListener('click', fitAll);
    if (geoLayer.getLayers().length) {{
      map.fitBounds(geoLayer.getBounds(), {{ padding: [24, 24] }});
    }}
  </script>
</body>
</html>
"""


def _write_manifest(payload: dict[str, Any], output_path: Path) -> Path:
    manifest = {
        "dataset_name": "grower_webmap",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "grower_slug": payload["grower_slug"],
        "grower_name": payload["grower_name"],
        "output_html": _relative(output_path),
        "html_bytes": output_path.stat().st_size,
        "field_count": payload["field_count"],
        "farms": payload["farms"],
        "fields": [
            {
                "field_id": feature["properties"]["field_id"],
                "field_slug": feature["properties"]["field_slug"],
                "field_name": feature["properties"]["field_name"],
                "farm_slug": feature["properties"]["farm_slug"],
                "area_acres": feature["properties"]["area_acres"],
                "crop": feature["properties"]["crop"],
            }
            for feature in payload["fields"]["features"]
        ],
        "basemap": "Esri World Imagery",
        "source_boundaries": payload["source_boundaries"],
    }
    path = grower_manifest_path(payload["grower_slug"], "grower_webmap.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def _discover_growers(requested: list[str]) -> list[str]:
    if requested:
        return [validate_path_slug(slug, "grower_slug") for slug in requested]
    return sorted(path.name for path in GROWERS_ROOT.glob("*") if path.is_dir())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grower-slug",
        action="append",
        default=[],
        help="Grower slug to render; repeat for multiple growers (default: all growers)",
    )
    parser.add_argument(
        "--all-growers",
        action="store_true",
        help="Render every grower under the runtime grower root",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Optional output directory, absolute or relative to the runtime data root",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover fields and print planned outputs without writing files",
    )
    args = parser.parse_args()

    if args.all_growers:
        growers = _discover_growers([])
    else:
        growers = _discover_growers(args.grower_slug)

    output_root = None
    if args.output_dir:
        candidate = Path(args.output_dir)
        output_root = candidate if candidate.is_absolute() else DATA_ROOT / candidate
        output_root = ensure_data_root_path(output_root)

    state_labels = _state_labels()
    written: list[dict[str, Any]] = []
    for grower_slug in growers:
        output_path = (
            output_root / f"{grower_slug}_webmap.html"
            if output_root is not None
            else grower_webmap_path(grower_slug)
        )
        payload = _build_grower_payload(
            grower_slug,
            state_labels=state_labels,
        )
        if payload is None:
            print(f"skip  {grower_slug}: no field polygons found")
            continue

        if args.dry_run:
            written.append(
                {
                    "grower_slug": grower_slug,
                    "output": _relative(output_path),
                    "field_count": payload["field_count"],
                    "farms": payload["farms"],
                }
            )
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(_render_html(payload), encoding="utf-8")
        manifest_path = _write_manifest(payload, output_path)
        written.append(
            {
                "grower_slug": grower_slug,
                "output": _relative(output_path),
                "manifest": _relative(manifest_path),
                "field_count": payload["field_count"],
                "bytes": output_path.stat().st_size,
            }
        )

    print(json.dumps({"growers": written, "dry_run": args.dry_run}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
