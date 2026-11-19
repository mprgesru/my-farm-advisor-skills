"""Geospatial figures (8 maps).

Two map families, each rendered per farm and once for the whole sample:

* boundaries - where the ten fields sit and which source produced them
* cdl        - five-year corn frequency per field

House map frame (``data-pipeline/references/field-map-frame.md``): each farm is
projected to its own UTM zone, the origin is pinned at the SW corner of the
field bounding box, axes stay in metres with a 4% viewport margin, and a boxed
true-north arrow sits top-right. There is no scale bar - the metre tick axes
carry distance on every panel. Farm layouts are clusters of ten fields rather
than one footprint, so no rotation is applied and north stays up.

The all-farm maps put the three farms side by side at one shared window size
instead of one national extent: at 750 km the 30 fields would be a handful of
invisible specks, which hides the very comparison the map is for.

Basemaps are Esri World Imagery via contextily, desaturated so parcel fills
stay readable; pass ``--no-basemap`` for an offline run.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import contextily as ctx
import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from loaders import _utm_epsg, data_root
from style import SOURCE_COLORS, new_figure, save, state_color

VIEW_PAD_FRAC = 0.04  # house 4% margin so boundaries never touch the frame
PANEL_PAD_KM = 1.0  # extra room on the shared all-farm window
LABEL_MIN_ACRES = 20.0  # below this a field is smaller than its own label

CORN_YEARS = list(range(6))  # 0/5 .. 5/5
CORN_CMAP = ListedColormap(plt.cm.YlOrBr(np.linspace(0.10, 0.95, len(CORN_YEARS))))
CORN_NORM = BoundaryNorm(np.arange(-0.5, 6.5, 1.0), CORN_CMAP.N)


# --------------------------------------------------------------------------- #
# shared frame helpers
# --------------------------------------------------------------------------- #
def _corn_frequency(farm) -> dict[str, float]:
    """Share of available years where corn is the dominant CDL class."""
    dom = farm.cdl_dominant.copy()
    return {
        field_id: float((group["dominant_crop"] == "Corn").mean())
        for field_id, group in dom.groupby("field_id")
    }


def _count_phrase(count: int, noun: str) -> str:
    """'no X parcels' for zero, otherwise 'N X parcels'."""
    if count == 0:
        return f"no {noun}s"
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _north_arrow(ax) -> None:
    ax.annotate(
        "N",
        xy=(0.955, 0.925),
        xytext=(0.955, 0.80),
        xycoords="axes fraction",
        textcoords="axes fraction",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.26", "facecolor": "white", "edgecolor": "#333333"},
        arrowprops={"arrowstyle": "-|>", "lw": 1.8, "color": "#333333"},
        zorder=20,
    )


def _desaturate(ax) -> None:
    """Turn the contextily raster grey so parcel fills stay legible on top."""
    for image in ax.images:
        array = np.asarray(image.get_array())
        if array.ndim != 3 or array.shape[-1] < 3:
            continue
        lum = array[..., :3].astype(float) @ np.array([0.299, 0.587, 0.114])
        image.set_data(lum)
        image.set_cmap("gray")
        # Lift the black point so dark imagery does not compete with the
        # dark boundary fills sitting on top of it.
        image.set_clim(35, 235)


def _tile_cache() -> None:
    """Cache imagery under the runtime root so re-runs do not refetch tiles."""
    try:
        cache = data_root().parent / ".cache" / "contextily"
        cache.mkdir(parents=True, exist_ok=True)
        ctx.set_cache_dir(str(cache))
    except OSError:
        pass


def _add_basemap(ax, crs, enabled: bool, *, zoom: int | None = None) -> bool:
    """Add the Esri imagery basemap, stepping down a zoom level on failure."""
    if not enabled:
        return False
    zooms: list[int | None] = [zoom] if zoom is None else [zoom, zoom - 1, zoom - 2]
    last: Exception | None = None
    for attempt, level in enumerate(zooms):
        kwargs = {} if level is None else {"zoom": level}
        try:
            ctx.add_basemap(
                ax,
                source=ctx.providers.Esri.WorldImagery,
                crs=crs,
                alpha=0.5,
                attribution=False,
                **kwargs,
            )
            _desaturate(ax)
            return True
        except Exception as exc:  # noqa: BLE001 - basemap is optional
            last = exc
            if attempt + 1 < len(zooms):
                time.sleep(1.0)
    print(f"    basemap unavailable ({type(last).__name__}: {last}); drawing plain background")
    return False


def _farm_frame(farm):
    fields = farm.fields.to_crs(4326)
    centroid = fields.union_all().centroid
    epsg = _utm_epsg(centroid.x, centroid.y)
    return fields.to_crs(epsg), epsg


def _local_limits(
    gdf: gpd.GeoDataFrame,
    pad_frac: float = VIEW_PAD_FRAC,
    *,
    corner_frac: tuple[float, float] = (0.0, 0.0),
):
    """Viewport and SW-origin for the field-local frame.

    The geometry keeps its true UTM coordinates so the basemap lands in the
    right place; only the tick *labels* are offset to read from the SW corner.
    ``corner_frac`` grows the east/north limits, which keeps the boxed north
    arrow out of the fields when a farm fills the whole frame.
    """
    xmin, ymin, xmax, ymax = gdf.total_bounds
    width, height = xmax - xmin, ymax - ymin
    pad = pad_frac * max(width, height)
    right = corner_frac[0] * width
    top = corner_frac[1] * height
    xlim = (xmin - pad, xmax + pad + right)
    ylim = (ymin - pad, ymax + pad + top)
    return xlim, ylim, (xmin, ymin)


def _nice_step(span: float, target: int = 4) -> float:
    raw = span / max(target, 1)
    for step in (250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 50000):
        if raw <= step:
            return float(step)
    return 100000.0


def _metre_axes(
    ax,
    epsg: int,
    origin: tuple[float, float],
    *,
    crs_label: str | None = None,
    show: bool = True,
) -> None:
    """Local-metre tick axes; labels read as distance from the SW corner.

    Ticks are placed on round offsets from the origin (0, 2000, ...) rather
    than on matplotlib's absolute positions, so a reader never sees "1,931".
    """
    ax.set_aspect("equal")
    ax.grid(False)
    if not show:
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_xlabel("")
        ax.set_ylabel("")
        return

    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    step = _nice_step(max(xlim[1] - xlim[0], ylim[1] - ylim[0]))

    def offsets(lo: float, hi: float, base: float) -> list[float]:
        start = math.ceil((lo - base) / step) * step
        values = []
        value = start
        while value <= hi - base:
            values.append(base + value)
            value += step
        return values

    ax.set_xticks(offsets(*xlim, origin[0]))
    ax.set_yticks(offsets(*ylim, origin[1]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value - origin[0]:,.0f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value - origin[1]:,.0f}"))
    ax.tick_params(labelsize=7.5)
    ax.set_xlabel(crs_label or f"m E from SW corner (UTM {epsg % 100})", fontsize=8)
    ax.set_ylabel("m N", fontsize=8)


def _field_labels(ax, fields, text_for, *, fontsize=7.2) -> None:
    """Label each field, nudging labels apart when fields sit shoulder to shoulder."""
    xlim, ylim = ax.get_xlim(), ax.get_ylim()
    sep_x = 0.080 * (xlim[1] - xlim[0])
    sep_y = 0.050 * (ylim[1] - ylim[0])
    placed: list[tuple[float, float]] = []
    anchors: list[tuple[float, float]] = []
    texts: list[str] = []
    moves: list[tuple[float, float]] = []

    for row in fields.itertuples(index=False):
        point = row.geometry.representative_point()
        x, y = point.x, point.y
        for _ in range(6):
            clash = next(
                (
                    (px, py)
                    for px, py in placed
                    if abs(px - x) < sep_x and abs(py - y) < sep_y
                ),
                None,
            )
            if clash is None:
                break
            direction = 1.0 if len(placed) % 2 == 0 else -1.0
            y = clash[1] + direction * 1.6 * sep_y
        placed.append((x, y))
        anchors.append((point.x, point.y))
        texts.append(text_for(row))
        moves.append((x - point.x, y - point.y))

    for (x, y), (ax0, ay0), text, (dx, dy) in zip(placed, anchors, texts, moves):
        if math.hypot(dx, dy) > 0:
            ax.plot(
                [ax0, x],
                [ay0, y],
                color="#333333",
                lw=0.6,
                zorder=8,
            )
        ax.annotate(
            text,
            (x, y),
            ha="center",
            va="center",
            fontsize=fontsize,
            fontweight="bold",
            color="#111111",
            bbox={
                "boxstyle": "round,pad=0.16",
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.82,
            },
            zorder=10,
        )


def _small_field_labels(ax, block, text_for, *, fontsize: float) -> None:
    """Label only fields big enough to hold the text at this scale."""
    _field_labels(ax, block[block["area_acres"] >= LABEL_MIN_ACRES], text_for, fontsize=fontsize)


def _corn_legend(fig, *, title="years with corn dominant", y: float = 0.075) -> None:
    handles = [
        Patch(
            facecolor=CORN_CMAP(CORN_NORM(k)),
            edgecolor="#333333",
            linewidth=0.5,
            label=f"{k}/5",
        )
        for k in CORN_YEARS
    ]
    fig.legend(
        handles=handles,
        title=title,
        loc="lower center",
        bbox_to_anchor=(0.5, y),
        ncol=len(handles),
        fontsize=8,
        title_fontsize=8,
        frameon=False,
        handlelength=1.1,
        handleheight=1.2,
        columnspacing=1.0,
    )


def _corn_years(fields: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return fields.assign(corn_years=(fields["corn_frequency"] * 5).round().clip(0, 5))


# --------------------------------------------------------------------------- #
# per-farm maps
# --------------------------------------------------------------------------- #
def boundaries_farm(farm, out_dir, basemap: bool) -> dict:
    fields, epsg = _farm_frame(farm)
    areas = farm.metrics.set_index("field_id")["area_acres"]
    fields = fields.assign(area_acres=fields["field_id"].map(areas))
    xlim, ylim, origin = _local_limits(fields, corner_frac=(0.07, 0.10))

    fig, ax = new_figure(7.4, 6.0)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    had_basemap = _add_basemap(ax, epsg, basemap, zoom=14)

    for source, color in SOURCE_COLORS.items():
        subset = fields[fields["source_label"] == source]
        if subset.empty:
            continue
        subset.plot(
            ax=ax,
            facecolor=color,
            alpha=0.32,
            edgecolor=color,
            linewidth=1.6,
            zorder=5,
        )

    _field_labels(ax, fields, lambda row: f"{row.area_acres:,.0f} ac")

    counts = fields["source_label"].value_counts().to_dict()
    total = float(fields["area_acres"].sum())
    handles = [
        Patch(
            facecolor=SOURCE_COLORS[s],
            alpha=0.38,
            edgecolor=SOURCE_COLORS[s],
            label=f"{s} ({counts.get(s, 0)} fields)",
        )
        for s in SOURCE_COLORS
        if counts.get(s)
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.025),
        ncol=len(handles),
        fontsize=8.5,
        title="boundary source",
        title_fontsize=8.5,
        frameon=False,
    )
    _metre_axes(ax, epsg, origin)
    _north_arrow(ax)
    ax.set_title(
        f"{farm.state} · {farm.display_name}: {total:,.0f} acres in {len(fields)} fields",
        fontsize=11,
    )
    fig.subplots_adjust(left=0.11, right=0.98, top=0.93, bottom=0.16)
    path = save(
        fig,
        out_dir / f"map_boundaries_farm_{farm.state.lower()}.png",
        subtitle="label = field area in acres"
        + (" · imagery: Esri World Imagery, greyscaled" if had_basemap else " · basemap unavailable"),
        layout=False,
    )
    return {
        "id": f"map_boundaries_{farm.state.lower()}",
        "path": path,
        "category": "boundaries",
        "title": f"{farm.state} field layout by boundary source",
        "caption": (
            f"{farm.display_name} holds "
            f"{_count_phrase(counts.get('CSB', 0), 'USDA CSB field')} and "
            f"{_count_phrase(counts.get('OSM', 0), 'OpenStreetMap parcel')} across "
            f"{total:,.0f} acres; the map shows layout and adjacency, which the size "
            "figures cannot."
        ),
        "n": f"{len(fields)} fields",
    }


def cdl_farm(farm, out_dir, basemap: bool) -> dict:
    fields, epsg = _farm_frame(farm)
    freq = _corn_frequency(farm)
    fields = _corn_years(fields.assign(corn_frequency=fields["field_id"].map(freq)))
    xlim, ylim, origin = _local_limits(fields, corner_frac=(0.07, 0.10))

    fig, ax = new_figure(7.4, 6.0)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    had_basemap = _add_basemap(ax, epsg, basemap, zoom=14)
    fields.plot(
        ax=ax,
        column="corn_years",
        cmap=CORN_CMAP,
        norm=CORN_NORM,
        edgecolor="#333333",
        linewidth=1.1,
        alpha=0.9,
        zorder=5,
    )
    _field_labels(ax, fields, lambda row: f"{row.corn_frequency*5:.0f}/5", fontsize=8)

    _metre_axes(ax, epsg, origin)
    _north_arrow(ax)
    mean = float(np.mean(list(freq.values()))) if freq else 0.0
    ax.set_title(f"{farm.state} · corn dominant {mean*5:.1f} of 5 years on average", fontsize=11)
    _corn_legend(fig, y=0.02)
    fig.subplots_adjust(left=0.11, right=0.98, top=0.94, bottom=0.17)
    path = save(
        fig,
        out_dir / f"map_cdl_farm_{farm.state.lower()}.png",
        subtitle="label = years out of five with corn as the dominant CDL class"
        + (" · imagery: Esri World Imagery, greyscaled" if had_basemap else " · basemap unavailable"),
        layout=False,
    )
    return {
        "id": f"map_cdl_{farm.state.lower()}",
        "path": path,
        "category": "cdl",
        "title": f"{farm.state} five-year corn frequency",
        "caption": (
            f"Corn is dominant in {mean*5:.1f} of five years for the average {farm.state} field; "
            "the map shows whether that intensity is uniform across the farm or concentrated "
            "in particular blocks."
        ),
        "n": f"{len(fields)} fields x 5 years",
        "stats": {"mean_corn_years": round(mean * 5, 2)},
    }


# --------------------------------------------------------------------------- #
# all-farm maps: three panels, one shared window
# --------------------------------------------------------------------------- #
def _all_fields(farms) -> gpd.GeoDataFrame:
    frames = []
    for farm in farms:
        gdf = farm.fields.to_crs(5070).copy()
        gdf["state"] = farm.state
        gdf["grower"] = farm.grower
        gdf["corn_frequency"] = gdf["field_id"].map(_corn_frequency(farm))
        # Areas come from the canonical per-field UTM metric, not from the
        # Albers display geometry, so panel titles match the tables exactly.
        gdf["area_acres"] = gdf["field_id"].map(
            farm.metrics.set_index("field_id")["area_acres"]
        )
        frames.append(gdf)
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=5070)


def _panel_window(farms, fields) -> tuple[float, float]:
    """One window big enough for every farm, so all panels share a scale."""
    half_x = half_y = 0.0
    for farm in farms:
        xmin, ymin, xmax, ymax = fields[fields["state"] == farm.state].total_bounds
        half_x = max(half_x, (xmax - xmin) / 2)
        half_y = max(half_y, (ymax - ymin) / 2)
    pad = PANEL_PAD_KM * 1000
    return half_x + pad, half_y + pad


def _setup_panels(farms, fields, figsize):
    fig, axes = new_figure(*figsize, nrows=1, ncols=len(farms))
    axes = np.atleast_1d(axes)
    half_x, half_y = _panel_window(farms, fields)
    layout = []
    for ax, farm in zip(axes, farms):
        block = fields[fields["state"] == farm.state]
        xmin, ymin, xmax, ymax = block.total_bounds
        cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
        ax.set_xlim(cx - half_x, cx + half_x)
        ax.set_ylim(cy - half_y, cy + half_y)
        layout.append((ax, block, (cx - half_x, cy - half_y)))
    return fig, layout


def _panel_title(ax, farm, block) -> None:
    ax.set_title(
        f"{farm.state} · {len(block)} fields · {block['area_acres'].sum():,.0f} ac",
        fontsize=10,
        color=state_color(farm.state),
    )


def boundaries_all(farms, out_dir, basemap: bool) -> dict:
    fields = _all_fields(farms)
    fig, layout = _setup_panels(farms, fields, (13.2, 4.4))
    any_basemap = False

    for ax, moved, origin in layout:
        farm = next(f for f in farms if f.state == moved["state"].iloc[0])
        any_basemap |= _add_basemap(ax, 5070, basemap, zoom=14)
        for source, color in SOURCE_COLORS.items():
            subset = moved[moved["source_label"] == source]
            if subset.empty:
                continue
            subset.plot(
                ax=ax,
                facecolor=color,
                alpha=0.35,
                edgecolor=color,
                linewidth=1.1,
                zorder=5,
            )
        _small_field_labels(ax, moved, lambda row: f"{row.area_acres:,.0f}", fontsize=6.0)
        _metre_axes(
            ax, 5070, origin, crs_label="m E from SW corner (Albers, EPSG:5070)"
        )
        _panel_title(ax, farm, moved)

    _north_arrow(layout[0][0])
    handles = [
        Patch(facecolor=SOURCE_COLORS[s], alpha=0.4, edgecolor=SOURCE_COLORS[s], label=s)
        for s in SOURCE_COLORS
    ]
    fig.legend(
        handles=handles,
        labels=list(SOURCE_COLORS),
        loc="lower center",
        ncol=2,
        fontsize=8.5,
        title="boundary source",
        title_fontsize=8.5,
        frameon=False,
        bbox_to_anchor=(0.5, 0.05),
    )
    fig.suptitle(
        "Ten fields per grower, drawn at one shared scale",
        fontsize=12,
        fontweight="bold",
        y=0.99,
    )
    fig.subplots_adjust(left=0.062, right=0.985, top=0.855, bottom=0.235, wspace=0.22)
    path = save(
        fig,
        out_dir / "map_boundaries_all.png",
        subtitle=(
            "tick labels count from each panel's own SW corner; grid spacing is identical across panels · "
            f"label = field area in acres, omitted below {LABEL_MIN_ACRES:.0f} ac · "
            "Illinois and Nebraska sit 745 km apart"
            + (" · imagery: Esri World Imagery" if any_basemap else " · basemap unavailable")
        ),
        layout=False,
    )
    return {
        "id": "map_boundaries_all",
        "path": path,
        "category": "boundaries",
        "title": "All 30 fields, one panel per grower at equal scale",
        "caption": (
            "The three farms share one sampling design, and drawing them at the same scale "
            "makes the geometry comparable: Illinois mixes six blocky CSB fields with four "
            "OSM parcels of very different sizes, Iowa carries one sub-acre sliver too small "
            "to label at this scale, and Nebraska's ten fields are regular rectangular blocks."
        ),
        "n": "30 fields",
    }


def cdl_all(farms, out_dir, basemap: bool) -> dict:
    fields = _all_fields(farms)
    fig, layout = _setup_panels(farms, fields, (13.2, 4.6))
    any_basemap = False

    for ax, moved, origin in layout:
        farm = next(f for f in farms if f.state == moved["state"].iloc[0])
        any_basemap |= _add_basemap(ax, 5070, basemap, zoom=14)
        _corn_years(moved).plot(
            ax=ax,
            column="corn_years",
            cmap=CORN_CMAP,
            norm=CORN_NORM,
            edgecolor="#333333",
            linewidth=0.9,
            alpha=0.9,
            zorder=5,
        )
        _small_field_labels(ax, moved, lambda row: f"{row.corn_frequency*5:.0f}/5", fontsize=7.0)
        _metre_axes(
            ax, 5070, origin, crs_label="m E from SW corner (Albers, EPSG:5070)"
        )
        _panel_title(ax, farm, moved)

    _north_arrow(layout[0][0])
    _corn_legend(fig, y=0.03)
    fig.suptitle(
        "Continuous corn is a Nebraska signature, not a farm quirk",
        fontsize=12,
        fontweight="bold",
        y=0.99,
    )
    fig.subplots_adjust(left=0.062, right=0.985, top=0.845, bottom=0.245, wspace=0.22)
    path = save(
        fig,
        out_dir / "map_cdl_all.png",
        subtitle="label = years out of five with corn as the dominant CDL class · each panel pinned to its own SW corner"
        + (" · imagery: Esri World Imagery" if any_basemap else " · basemap unavailable"),
        layout=False,
    )
    return {
        "id": "map_cdl_all",
        "path": path,
        "category": "cdl",
        "title": "Five-year corn frequency across all 30 fields",
        "caption": (
            "Eight of ten Nebraska fields are corn in at least four of five years, while "
            "Illinois and Iowa fields scatter across the range and none repeats corn five "
            "times; the pattern that looked farm-wide in one panel holds across the sample."
        ),
        "n": "30 fields x 5 years",
    }


def build(farms, out_dir, *, basemap: bool = True) -> list[dict]:
    if basemap:
        _tile_cache()
    figures = []
    for farm in farms:
        figures.append(boundaries_farm(farm, out_dir, basemap))
        figures.append(cdl_farm(farm, out_dir, basemap))
    figures.append(boundaries_all(farms, out_dir, basemap))
    figures.append(cdl_all(farms, out_dir, basemap))
    return figures
