"""CDL / cropland figures (B1-B5).

CDL is the only input in this sample with field-level time, so it carries the
"within a field over five years" comparisons. Shares are area shares: the
composition table counts equal-area 30 m pixels inside each boundary, so a
field's share is weighted by its acreage before the grower total is formed.

Composition rows are renormalised to 100% per field-year. The source pipeline
drops classes below its rounding floor, so raw rows sum to 96-100% and a plain
mean would inflate whichever class happens to survive in more fields.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter
from scipy import stats

from style import CROP_COLORS, new_figure, save, state_color

CROP_ORDER = ["Corn", "Soybeans", "Other crop", "Non-crop"]
# Crop classes only (no non-crop), used by the diversity analysis.
CROP_CLASSES = ["Corn", "Soybeans", "Other crop"]
YEARS = [2021, 2022, 2023, 2024, 2025]
NON_CROP = {
    "Forest",
    "Grass/Pasture",
    "Fallow/Idle",
    "Water",
    "Developed",
    "Wetlands",
    "Shrubland",
    "Barren",
}


def crop_class(name: str) -> str:
    if name == "Corn":
        return "Corn"
    if name == "Soybeans":
        return "Soybeans"
    if name in NON_CROP:
        return "Non-crop"
    if isinstance(name, str) and name.strip():
        return "Other crop"
    return "Non-crop"


def _with_class(cdl: pd.DataFrame) -> pd.DataFrame:
    out = cdl.copy()
    out["crop_class"] = out["crop_name"].map(crop_class)
    return out


def _dominant_class(dominant: pd.DataFrame) -> pd.DataFrame:
    """``cdl_dominant`` carries ``dominant_crop`` rather than ``crop_name``."""
    out = dominant.copy()
    out["crop_class"] = out["dominant_crop"].map(crop_class)
    return out


def area_share(farm) -> pd.DataFrame:
    """Acreage-weighted class shares (%), one row per year, summing to 100."""
    cdl = _with_class(farm.cdl_long)
    per_field = (
        cdl.groupby(["field_id", "year", "crop_class"])["pct"]
        .sum()
        .unstack("crop_class", fill_value=0.0)
        .reindex(columns=CROP_ORDER, fill_value=0.0)
    )
    totals = per_field.sum(axis=1).replace(0, np.nan)
    per_field = per_field.div(totals, axis=0) * 100.0

    weights = farm.metrics.set_index("field_id")["area_acres"]
    per_field["__weight"] = per_field.index.get_level_values("field_id").map(weights)
    per_field = per_field.dropna(subset=["__weight"])

    weighted = per_field[CROP_ORDER].mul(per_field["__weight"], axis=0)
    share = weighted.groupby(level="year").sum().div(
        per_field["__weight"].groupby(level="year").sum(), axis=0
    )
    return share.reindex(sorted(share.index)).round(3)


def _legend_handles():
    return [
        Rectangle((0, 0), 1, 1, facecolor=CROP_COLORS[cls], edgecolor="white")
        for cls in CROP_ORDER
    ]


def composition(farms, out_dir) -> dict:
    comp = pd.concat(
        [area_share(farm).assign(state=farm.state, grower=farm.grower) for farm in farms],
        ignore_index=False,
    ).reset_index()

    fig, ax = new_figure(10.6, 5.4)
    ax.set_axisbelow(True)
    positions, labels, block_centres = [], [], {}
    cursor = 0.0
    for state in sorted(comp["state"].unique()):
        block = comp[comp["state"] == state].sort_values("year")
        start = cursor
        for _, row in block.iterrows():
            bottom = 0.0
            for cls in CROP_ORDER:
                value = float(row[cls])
                ax.bar(
                    cursor,
                    value,
                    bottom=bottom,
                    width=0.74,
                    color=CROP_COLORS[cls],
                    edgecolor="white",
                    linewidth=0.8,
                    zorder=3,
                )
                bottom += value
            positions.append(cursor)
            labels.append(str(int(row["year"])))
            cursor += 1.0
        block_centres[state] = (start + cursor - 1.0) / 2.0
        cursor += 0.6

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(0, 100)
    ax.set_ylabel("share of field area (%)")
    ax.set_title(
        "Corn carries every grower in every year except Nebraska in 2022",
        fontsize=12,
    )

    for state, centre in block_centres.items():
        ax.annotate(
            state,
            (centre, -0.085),
            xycoords=("data", "axes fraction"),
            ha="center",
            va="top",
            fontsize=10.5,
            fontweight="bold",
            color=state_color(state),
        )

    ax.legend(
        handles=_legend_handles(),
        labels=CROP_ORDER,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=4,
        fontsize=8.5,
    )
    path = save(
        fig,
        out_dir / "b1_crop_composition.png",
        subtitle="acreage-weighted share of CDL pixels inside each grower's ten boundaries · rows renormalised to 100%",
    )
    return {
        "id": "b1",
        "path": path,
        "category": "cdl",
        "title": "Crop composition by grower and year",
        "caption": (
            "Corn holds 50-68% of Illinois area and 47-59% of Iowa area in every year, "
            "while Nebraska sits at 89-99% except 2022, when soybeans take 60% of its "
            "area. That single year is the only break in a corn-dominated sample."
        ),
        "n": "3 growers x 5 years",
    }


def sequence_grid(farms, out_dir) -> dict:
    rows = []
    for farm in farms:
        dom = _dominant_class(farm.cdl_dominant)
        for field_id, group in dom.groupby("field_id", sort=True):
            rows.append((farm.state, field_id, group.set_index("year")["crop_class"]))

    fig, ax = new_figure(9.6, 8.8)
    for y, (state, field_id, series) in enumerate(rows):
        for x, year in enumerate(YEARS):
            cls = series.get(year, "Missing")
            if not isinstance(cls, str):
                cls = "Missing"
            ax.add_patch(
                Rectangle(
                    (x, y),
                    1,
                    1,
                    facecolor=CROP_COLORS.get(cls, CROP_COLORS["Missing"]),
                    edgecolor="white",
                    linewidth=1.1,
                    hatch="///" if cls == "Missing" else None,
                )
            )
            if cls == "Missing":
                ax.text(
                    x + 0.5,
                    y + 0.5,
                    "no data",
                    ha="center",
                    va="center",
                    fontsize=6.2,
                    color="#555555",
                )

    ax.set_yticks([y + 0.5 for y in range(len(rows))])
    ax.set_yticklabels([r[1] for r in rows], fontsize=6.2)

    start = 0
    for state in sorted({r[0] for r in rows}):
        count = sum(1 for r in rows if r[0] == state)
        if start:
            ax.axhline(start, color="#333333", lw=1.2)
        ax.annotate(
            state,
            (-0.02, start + count / 2),
            xycoords=("axes fraction", "data"),
            xytext=(-62, 0),
            textcoords="offset points",
            ha="right",
            va="center",
            fontsize=10.5,
            fontweight="bold",
            color=state_color(state),
        )
        start += count

    ax.set_xlim(0, len(YEARS))
    ax.set_ylim(0, len(rows))
    ax.set_xticks([x + 0.5 for x in range(len(YEARS))])
    ax.set_xticklabels(YEARS)
    ax.set_xlabel("year")
    ax.invert_yaxis()
    ax.grid(False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title(
        "Within-field sequences: Nebraska holds corn four years in five",
        fontsize=12,
    )
    ax.legend(
        handles=_legend_handles(),
        labels=CROP_ORDER,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.055),
        ncol=4,
        fontsize=8.5,
    )
    path = save(
        fig,
        out_dir / "b2_crop_sequence_grid.png",
        subtitle="cell = dominant CDL class by area for that field-year; one field per row; hatched = no CDL row",
    )
    return {
        "id": "b2",
        "path": path,
        "category": "cdl",
        "title": "Dominant crop per field, 2021-2025",
        "caption": (
            "Field-by-field sequences show Illinois and Iowa alternating on a two-year "
            "rhythm while Nebraska's ten fields are corn in 41 of 50 field-years. The "
            "hatched cell is the 0.84-acre Iowa parcel, which covers too few 30 m pixels "
            "to resolve a 2024 class."
        ),
        "n": "30 fields x 5 years",
    }


def transition_matrix(farm) -> pd.DataFrame:
    """Counts of consecutive-year class pairs (any year t -> t+1)."""
    dom = _dominant_class(farm.cdl_dominant)
    wide = dom.pivot(index="field_id", columns="year", values="crop_class")
    pairs = []
    for year in YEARS[:-1]:
        if year not in wide.columns or year + 1 not in wide.columns:
            continue
        pair = wide[[year, year + 1]].dropna()
        pair.columns = ["from", "to"]
        pairs.append(pair)
    stacked = (
        pd.concat(pairs, ignore_index=True)
        if pairs
        else pd.DataFrame(columns=["from", "to"])
    )
    matrix = pd.DataFrame(0, index=CROP_ORDER, columns=CROP_ORDER, dtype=int)
    for _, row in stacked.iterrows():
        matrix.loc[row["from"], row["to"]] += 1
    return matrix


def transitions(farms, out_dir) -> dict:
    matrices = {farm.state: transition_matrix(farm) for farm in farms}
    # Drop classes that are never the dominant class, so empty rows do not
    # consume a quarter of each panel.
    used = [c for c in CROP_ORDER if any(m[c].sum() or m.loc[c].sum() for m in matrices.values())]
    dropped = [c for c in CROP_ORDER if c not in used]

    fig, axes = plt.subplots(1, len(farms), figsize=(12.2, 4.4), sharey=True)
    axes = np.atleast_1d(axes)
    summary = {}

    for i, (ax, farm) in enumerate(zip(axes, farms)):
        matrix = matrices[farm.state].loc[used, used]
        share = matrix.div(matrix.sum(axis=1).replace(0, np.nan), axis=0)
        ax.imshow(share.fillna(0).to_numpy(), cmap="Blues", vmin=0, vmax=1)
        ax.set_xticks(range(len(used)))
        ax.set_xticklabels(used, rotation=30, ha="right", fontsize=8)
        ax.set_yticks(range(len(used)))
        ax.set_yticklabels(used if i == 0 else [], fontsize=8)
        ax.set_title(
            f"{farm.state}  ({int(matrix.to_numpy().sum())} year pairs)",
            fontsize=10,
        )
        ax.grid(False)
        for r in range(len(used)):
            for c in range(len(used)):
                value = share.iloc[r, c]
                if pd.isna(value) or matrix.iloc[r, c] == 0:
                    continue
                ax.text(
                    c,
                    r,
                    f"{value:.2f}\n{int(matrix.iloc[r, c])}",
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color="white" if value > 0.55 else "#333333",
                )
        cc = share.loc["Corn", "Corn"] if "Corn" in used else float("nan")
        cs = share.loc["Corn", "Soybeans"] if "Soybeans" in used else float("nan")
        summary[farm.state] = {
            "corn_to_corn": None if pd.isna(cc) else round(float(cc), 3),
            "corn_to_soy": None if pd.isna(cs) else round(float(cs), 3),
        }

    fig.suptitle(
        "Corn flips to soybean 76-81% of the time in Illinois and Iowa, 26% in Nebraska",
        fontsize=12,
        fontweight="bold",
        y=1.02,
    )
    note = "rows = class in year t · columns = class in year t+1 · cell = row share / count"
    if dropped:
        note += f" · no field is ever dominant {' or '.join(dropped)}"
    fig.text(0.5, -0.08, note, ha="center", fontsize=8, color="#555555")
    path = save(fig, out_dir / "b3_crop_transitions.png")
    return {
        "id": "b3",
        "path": path,
        "category": "cdl",
        "title": "Year-to-year crop transitions by grower",
        "caption": (
            "Row-normalised transition matrices make the rotation gap a rate: after a corn "
            "year, Illinois and Iowa plant soybean 81% and 76% of the time, Nebraska only "
            "26%. Corn-to-corn is 0.74 in Nebraska against 0.19 and 0.24 in Illinois and "
            "Iowa."
        ),
        "n": "118 within-grower year pairs",
        "stats": summary,
    }


def dominant_class_counts(farms) -> pd.DataFrame:
    """Field-years per dominant CDL class, stacked by grower (long form)."""
    rows = []
    for farm in farms:
        dom = _dominant_class(farm.cdl_dominant)
        counts = dom["crop_class"].value_counts()
        for cls in CROP_ORDER:
            rows.append(
                {
                    "state": farm.state,
                    "grower": farm.grower,
                    "crop_class": cls,
                    "field_years": int(counts.get(cls, 0)),
                }
            )
    return pd.DataFrame(rows)


def crop_class_counts(farms, out_dir) -> dict:
    """B4: how many field-years each class dominates, by grower."""
    table = dominant_class_counts(farms)
    states = sorted(table["state"].unique())
    classes = [
        cls
        for cls in CROP_ORDER
        if table.loc[table["crop_class"] == cls, "field_years"].sum() > 0
    ]
    totals = table.groupby("state")["field_years"].sum().to_dict()

    fig, ax = new_figure(9.4, 5.0)
    width = 0.78 / len(classes)
    positions = np.arange(len(states))
    stats_out: dict[str, dict[str, int]] = {}

    drawn: set[str] = set()
    for i, cls in enumerate(classes):
        values = [
            int(
                table.loc[
                    (table["state"] == state) & (table["crop_class"] == cls),
                    "field_years",
                ].sum()
            )
            for state in states
        ]
        for j, value in enumerate(values):
            if not value:
                continue
            bar = ax.bar(
                positions[j] - 0.39 + width * (i + 0.5),
                value,
                width=width * 0.9,
                color=CROP_COLORS[cls],
                edgecolor="white",
                linewidth=0.8,
                label=cls if cls not in drawn else None,
                zorder=3,
            )
            drawn.add(cls)
            ax.text(
                bar[0].get_x() + bar[0].get_width() / 2,
                value + 0.7,
                str(value),
                ha="center",
                va="bottom",
                fontsize=8.5,
                color="#333333",
            )

    ax.set_xticks(positions)
    ax.set_xticklabels([f"{state}\n({totals[state]} field-years)" for state in states])
    for label, state in zip(ax.get_xticklabels(), states):
        label.set_color(state_color(state))
    ax.set_ylim(0, max(int(table["field_years"].max()) + 7, 10))
    ax.set_ylabel("field-years (one field in one year)")
    ax.set_title(
        f"Nebraska stays in corn {int(table.loc[(table['state'] == 'NE') & (table['crop_class'] == 'Corn'), 'field_years'].sum())} "
        "of 50 field-years; Illinois and Iowa split corn with soybean",
        fontsize=11.5,
    )
    ax.legend(loc="upper right", fontsize=8.5, title=None)

    for state in states:
        block = table[table["state"] == state]
        stats_out[state] = {
            row.crop_class: int(row.field_years) for row in block.itertuples()
        }

    path = save(
        fig,
        out_dir / "b4_crop_class_counts.png",
        subtitle="bar = field-years where that class is the largest CDL share · counts, not acreage; acreage shares are in B1",
    )

    ia_noncrop = stats_out.get("IA", {}).get("Non-crop", 0)
    ia_fields = (
        _dominant_class(
            next(f for f in farms if f.state == "IA").cdl_dominant
        )
        .loc[lambda d: d["crop_class"] == "Non-crop", "field_id"]
        .nunique()
    )
    caption = (
        f"Nebraska is corn-dominant in {stats_out['NE']['Corn']} of {totals['NE']} field-years, "
        f"against {stats_out['IL']['Corn']} of {totals['IL']} in Illinois and "
        f"{stats_out['IA']['Corn']} of {totals['IA']} in Iowa, where soybean accounts for most of "
        "the remainder. "
    )
    if ia_noncrop:
        caption += (
            f"Iowa's {ia_noncrop} non-crop field-years all belong to {ia_fields} small parcels, "
            "not to a broader shift out of crops."
        )
    return {
        "id": "b4",
        "path": path,
        "category": "cdl",
        "title": "Dominant CDL class counts by grower",
        "caption": caption,
        "n": f"{int(table['field_years'].sum())} field-years",
        "stats": {"class_counts": stats_out, "field_years": totals},
    }


def diversity_table(farms) -> pd.DataFrame:
    """Per-field mean count of crop classes dominating at least a share.

    Two definitions are kept because they disagree: every class the pipeline
    reports, and classes covering at least 5% of the field. The first is
    sensitive to how many 30 m pixels a field contains, so it is not a pure
    agronomic measure. Shares are renormalised per field-year first.
    """
    frames = []
    for farm in farms:
        cdl = _with_class(farm.cdl_long)
        cdl = cdl[cdl["year"].isin(YEARS)].copy()
        row_total = cdl.groupby(["field_id", "year"])["pct"].transform("sum")
        cdl["pct_n"] = cdl["pct"].div(row_total.replace(0, np.nan)).mul(100.0)
        crop = cdl[cdl["crop_class"].isin(CROP_CLASSES)]

        any_n = crop.groupby(["field_id", "year"])["crop_class"].nunique()
        ge5_n = (
            crop[crop["pct_n"] >= 5.0]
            .groupby(["field_id", "year"])["crop_class"]
            .nunique()
        )
        # A field-year with no crop class at all (the smallest Iowa parcel in
        # 2022 reports only grass) has zero crop classes, not a missing value.
        observed = pd.MultiIndex.from_frame(
            cdl[["field_id", "year"]].drop_duplicates()
        )
        any_n = any_n.reindex(observed, fill_value=0)
        ge5_n = ge5_n.reindex(observed, fill_value=0)
        frame = (
            pd.concat(
                [any_n.rename("classes_all"), ge5_n.rename("classes_ge5")], axis=1
            )
            .reset_index()
            .merge(
                farm.metrics[["field_id", "area_acres"]],
                on="field_id",
                how="right",
            )
        )
        frame["grower"] = farm.grower
        frame["state"] = farm.state
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    return (
        combined.groupby(["grower", "state", "field_id"], as_index=False)
        .agg(
            area_acres=("area_acres", "first"),
            mean_classes=("classes_all", "mean"),
            mean_classes_ge5=("classes_ge5", "mean"),
            field_years=("classes_all", "size"),
        )
        .sort_values(["state", "area_acres"])
        .reset_index(drop=True)
    )


def size_vs_diversity(farms, out_dir) -> dict:
    """B5: does a bigger field carry more crop classes?"""
    table = diversity_table(farms)
    fig, axes = new_figure(11.6, 5.2, ncols=2, sharey=True)
    panels = [
        ("mean_classes", "every reported crop class", axes[0]),
        ("mean_classes_ge5", "crop classes covering at least 5%", axes[1]),
    ]
    stats_out: dict[str, dict] = {}

    for col, (column, label, ax) in enumerate(panels):
        pooled = stats.spearmanr(table["area_acres"], table[column])
        within = {}
        for state in sorted(table["state"].unique()):
            block = table[table["state"] == state]
            result = stats.spearmanr(block["area_acres"], block[column])
            within[state] = {
                "rho": round(float(result.statistic), 3),
                "p": round(float(result.pvalue), 3),
            }
            ax.scatter(
                block["area_acres"],
                block[column],
                s=64,
                color=state_color(state),
                edgecolor="white",
                linewidth=0.8,
                label=f"{state}  rho {result.statistic:+.2f}",
                zorder=3,
            )
        stats_out[column] = {
            "pooled": {
                "rho": round(float(pooled.statistic), 3),
                "p": round(float(pooled.pvalue), 3),
            },
            "within": within,
        }

        ax.set_xscale("log")
        ax.set_xticks([1, 3, 10, 30, 100, 300, 700])
        ax.get_xaxis().set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.set_xlim(0.65, 900)
        ytop = float(table[["mean_classes", "mean_classes_ge5"]].max().max())
        ax.set_ylim(0.7, ytop + 0.4)
        ax.set_yticks([0, 1, 2, 3])
        ax.set_xlabel("field area (acres, log scale)")
        ax.set_title(f"{label}\npooled rho {pooled.statistic:+.2f} (p={pooled.pvalue:.3f})")
        if col == 0:
            ax.set_ylabel("mean crop classes per field-year")
            ax.legend(loc="upper left", fontsize=8.2)

    smallest = table.nsmallest(1, "area_acres").iloc[0]
    axes[0].annotate(
        f"{smallest['area_acres']:.2f} ac",
        (smallest["area_acres"], smallest["mean_classes"]),
        xytext=(8, -3),
        textcoords="offset points",
        fontsize=7.2,
        color="#555555",
    )

    fig.suptitle(
        "The size-diversity link depends on how a class is counted",
        fontsize=12,
        fontweight="bold",
        y=1.02,
    )
    path = save(
        fig,
        out_dir / "b5_size_vs_diversity.png",
        subtitle=(
            "point = one field, mean over its CDL years · crop classes = corn, soybean, other crop "
            f"· {int(table['field_years'].sum())} field-years"
        ),
    )

    pooled_all = stats_out["mean_classes"]["pooled"]
    pooled_ge5 = stats_out["mean_classes_ge5"]["pooled"]
    within_all = stats_out["mean_classes"]["within"]
    within_ge5 = stats_out["mean_classes_ge5"]["within"]
    caption = (
        f"Counting every reported crop class, larger fields look richer: pooled rho "
        f"{pooled_all['rho']:+.2f} (p={pooled_all['p']:.3f}), positive in all three growers "
        f"({within_all['IL']['rho']:+.2f} IL, {within_all['IA']['rho']:+.2f} IA, "
        f"{within_all['NE']['rho']:+.2f} NE, n=10 each). Requiring a class to cover at least 5% "
        f"of the field flips the pooled sign to {pooled_ge5['rho']:+.2f} "
        f"(p={pooled_ge5['p']:.2f}), with Iowa at {within_ge5['IA']['rho']:+.2f}. A larger field "
        "resolves more 30 m classes, so the raw count is partly a resolution artifact; this "
        "sample does not establish an agronomic size-diversity effect."
    )
    return {
        "id": "b5",
        "path": path,
        "category": "cdl",
        "title": "Field size vs crop-class diversity, two definitions",
        "caption": caption,
        "n": "30 fields, 149 field-years",
        "stats": stats_out,
    }


def build(farms, out_dir) -> list[dict]:
    figures = [
        composition(farms, out_dir),
        sequence_grid(farms, out_dir),
        transitions(farms, out_dir),
        crop_class_counts(farms, out_dir),
        size_vs_diversity(farms, out_dir),
    ]

    rows = []
    for farm in farms:
        dom = _dominant_class(farm.cdl_dominant)
        wide = (
            _with_class(farm.cdl_long)
            .pivot_table(
                index=["field_id", "year"],
                columns="crop_class",
                values="pct",
                aggfunc="sum",
                fill_value=0.0,
            )
            .reindex(columns=CROP_ORDER, fill_value=0.0)
        )
        for row in dom.itertuples(index=False):
            key = (row.field_id, row.year)
            values = wide.loc[key] if key in wide.index else None
            total = float(values.sum()) if values is not None else 0.0
            rows.append(
                {
                    "grower": farm.grower,
                    "state": farm.state,
                    "field_id": row.field_id,
                    "year": int(row.year),
                    "dominant_crop": row.dominant_crop,
                    "dominant_pct": float(row.dominant_pct),
                    "corn_pct": round(
                        float(values.get("Corn", 0.0)) / total * 100 if total else 0.0, 2
                    ),
                    "soybean_pct": round(
                        float(values.get("Soybeans", 0.0)) / total * 100 if total else 0.0,
                        2,
                    ),
                }
            )
    pd.DataFrame(rows).to_csv(
        out_dir.parent / "tables" / "cdl_field_year.csv", index=False
    )

    share_rows = []
    for farm in farms:
        share = area_share(farm)
        for year, row in share.iterrows():
            share_rows.append(
                {
                    "grower": farm.grower,
                    "state": farm.state,
                    "year": int(year),
                    **{cls.lower().replace(" ", "_") + "_pct": round(float(row[cls]), 2) for cls in CROP_ORDER},
                    "corn_to_corn": transitions_summary(farm)["corn_to_corn"],
                    "corn_to_soy": transitions_summary(farm)["corn_to_soy"],
                }
            )
    pd.DataFrame(share_rows).to_csv(
        out_dir.parent / "tables" / "cdl_area_share_by_year.csv", index=False
    )

    diversity_table(farms).to_csv(
        out_dir.parent / "tables" / "cdl_diversity_by_field.csv", index=False
    )
    return figures


def transitions_summary(farm) -> dict:
    matrix = transition_matrix(farm)
    share = matrix.div(matrix.sum(axis=1).replace(0, np.nan), axis=0)
    out = {}
    for a, b, label in (("Corn", "Corn", "corn_to_corn"), ("Corn", "Soybeans", "corn_to_soy")):
        value = share.loc[a, b]
        out[label] = None if pd.isna(value) else round(float(value), 3)
    return out
