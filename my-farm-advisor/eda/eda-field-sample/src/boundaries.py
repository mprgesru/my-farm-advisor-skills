"""Field-boundary figures (A1-A3).

All three figures answer structural questions about the sample's geometry.
Boundaries are a single snapshot, so there is no within-field time axis here;
the temporal story belongs to the CDL module.

Every metric is measured in each field's own UTM zone. Degrees are not a unit
at field scale, and one national projection would distort compactness ratios
between Illinois and Nebraska.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from style import STATE_COLORS, SOURCE_MARKERS, new_figure, save, state_color


def _metrics(farms) -> pd.DataFrame:
    return pd.concat([farm.metrics for farm in farms], ignore_index=True)


def _ecdf(values: np.ndarray):
    xs = np.sort(values)
    ys = np.arange(1, xs.size + 1) / xs.size
    return xs, ys


def field_size_distribution(farms, out_dir) -> dict:
    metrics = _metrics(farms)
    states = sorted(metrics["state"].unique())
    fig, (ax_l, ax_r) = new_figure(10.4, 5.2, nrows=1, ncols=2)

    rng = np.random.default_rng(0)
    for i, state in enumerate(states):
        group = metrics[metrics["state"] == state]
        jitter = rng.uniform(-0.16, 0.16, len(group))
        ax_l.scatter(
            group["area_acres"],
            i + jitter,
            s=42,
            color=state_color(state),
            alpha=0.85,
            edgecolor="white",
            linewidth=0.6,
            zorder=3,
        )
        median = group["area_acres"].median()
        ax_l.plot(
            [median, median], [i - 0.28, i + 0.28], color="black", lw=2, zorder=4
        )
        ax_l.annotate(
            f"median {median:,.0f} ac",
            (median, i + 0.34),
            ha="center",
            va="bottom",
            fontsize=8,
            color="black",
        )
    ax_l.set_yticks(range(len(states)))
    ax_l.set_yticklabels(states)
    ax_l.set_xscale("log")
    ax_l.set_xlabel("field area (acres, log scale)")
    ax_l.set_title("Every field, one dot")
    ax_l.set_ylim(-0.6, len(states) - 0.2)

    for state in states:
        group = metrics[metrics["state"] == state]
        xs, ys = _ecdf(group["area_acres"].to_numpy())
        ax_r.step(xs, ys, where="post", color=state_color(state), lw=2, label=state)
        ax_r.scatter(xs, ys, s=14, color=state_color(state), zorder=3)
    ax_r.set_xscale("log")
    ax_r.set_xlabel("field area (acres, log scale)")
    ax_r.set_ylabel("share of fields at or below")
    ax_r.set_title("Cumulative distribution")
    ax_r.set_ylim(0, 1.05)
    ax_r.legend(title="grower", loc="lower right")

    fig.suptitle(
        "Nebraska's fields are one narrow band; Illinois and Iowa run 0.8 to 619 acres",
        fontsize=12.5,
        fontweight="bold",
        y=1.02,
    )
    ax_l.text(
        0.99,
        0.02,
        "note: both tails are real geometry, not parsing errors",
        transform=ax_l.transAxes,
        ha="right",
        va="bottom",
        fontsize=7.5,
        color="#666666",
    )
    counts = " · ".join(f"{s} {int((metrics['state'] == s).sum())}" for s in states)
    path = save(
        fig,
        out_dir / "a1_field_size_distribution.png",
        subtitle=f"n = {len(metrics)} fields ({counts}) · area measured in each field's own UTM zone",
    )
    return {
        "id": "a1",
        "path": path,
        "category": "boundaries",
        "title": "Field size distribution by grower",
        "caption": (
            "Nebraska's ten fields sit in a 208-458 acre band, while Illinois runs 18-619 "
            "acres and Iowa 0.84-326. The sub-acre and sub-20-acre ends are OpenStreetMap "
            "parcels, including a 0.84-acre Iowa sliver, and are kept rather than trimmed."
        ),
        "n": "30 fields",
    }


def edge_density(farms, out_dir) -> dict:
    metrics = _metrics(farms)
    order = sorted(metrics["state"].unique())
    fig, ax = new_figure()
    ax.set_axisbelow(True)

    data = [
        metrics.loc[metrics["state"] == s, "edge_m_per_acre"].to_numpy() for s in order
    ]
    bp = ax.boxplot(
        data,
        positions=range(len(order)),
        widths=0.45,
        patch_artist=True,
        showfliers=False,
        medianprops={"color": "black", "lw": 1.6},
        whiskerprops={"color": "#555555"},
        capprops={"color": "#555555"},
    )
    for patch, state in zip(bp["boxes"], order):
        patch.set_facecolor(STATE_COLORS.get(state, "#999999"))
        patch.set_alpha(0.28)
        patch.set_edgecolor(STATE_COLORS.get(state, "#999999"))

    rng = np.random.default_rng(0)
    for i, state in enumerate(order):
        group = metrics[metrics["state"] == state]
        jitter = rng.uniform(-0.13, 0.13, len(group))
        ax.scatter(
            i + jitter,
            group["edge_m_per_acre"],
            s=38,
            color=state_color(state),
            alpha=0.9,
            edgecolor="white",
            linewidth=0.6,
            zorder=3,
        )

    worst = metrics.loc[metrics["edge_m_per_acre"].idxmax()]
    rest = metrics.drop(worst.name)
    ratio = worst["edge_m_per_acre"] / rest["edge_m_per_acre"].median()
    ax.annotate(
        f"{worst['field_id']}\n{worst['area_acres']:.2f} ac · {worst['edge_m_per_acre']:.0f} m/ac",
        (order.index(worst["state"]), worst["edge_m_per_acre"]),
        xytext=(20, -30),
        textcoords="offset points",
        fontsize=8,
        arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 0.8},
    )

    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(order)
    ax.set_yscale("log")
    ax.set_ylabel("boundary metres per acre (log scale)")
    ax.set_xlabel("grower")
    ax.set_title(
        f"The sub-acre parcel needs {ratio:.0f}x the boundary per acre of a typical field",
        fontsize=12,
    )
    path = save(
        fig,
        out_dir / "a2_edge_density.png",
        subtitle=(
            f"n = {len(metrics)} fields · box = IQR, dots = fields · "
            f"median of the other {len(rest)} fields = {rest['edge_m_per_acre'].median():.0f} m/ac"
        ),
    )
    return {
        "id": "a2",
        "path": path,
        "category": "boundaries",
        "title": "Edge density (perimeter per acre) by grower",
        "caption": (
            f"Typical fields need {rest['edge_m_per_acre'].median():.0f} m of boundary per "
            f"acre; the 0.84-acre Iowa parcel needs {worst['edge_m_per_acre']:.0f} m, about "
            f"{ratio:.0f} times more. Any per-acre cost or sampling metric has to exclude that "
            "parcel or report it separately."
        ),
        "n": "30 fields",
    }


def _rho_table(metrics: pd.DataFrame) -> pd.DataFrame:
    groups = [("all fields", metrics)]
    groups += [(f"only {s}", metrics[metrics["source"] == s]) for s in ("CSB", "OSM")]
    groups += [(s, metrics[metrics["state"] == s]) for s in sorted(metrics["state"].unique())]
    rows = []
    for label, block in groups:
        if len(block) < 3:
            continue
        result = stats.spearmanr(block["area_acres"], block["polsby_popper"])
        rows.append(
            {
                "group": label,
                "n": len(block),
                "rho": float(result.statistic),
                "p": float(result.pvalue),
            }
        )
    return pd.DataFrame(rows)


def size_vs_compactness(farms, out_dir) -> dict:
    metrics = _metrics(farms)
    rhos = _rho_table(metrics)
    fig, (ax_l, ax_r) = new_figure(11.4, 5.2, nrows=1, ncols=2, gridspec_kw={"width_ratios": [1.45, 1]})

    for state, group in metrics.groupby("state"):
        for source, marker in SOURCE_MARKERS.items():
            subset = group[group["source"] == source]
            if subset.empty:
                continue
            ax_l.scatter(
                subset["area_acres"],
                subset["polsby_popper"],
                s=58,
                marker=marker,
                color=state_color(state),
                alpha=0.85,
                edgecolor="white",
                linewidth=0.7,
                label=f"{state} · {source}",
                zorder=3,
            )

    small = metrics[metrics["area_acres"] < 5]
    for row in small.itertuples(index=False):
        ax_l.annotate(
            f"{row.field_id}\n{row.area_acres:.2f} ac",
            (row.area_acres, row.polsby_popper),
            xytext=(12, 6),
            textcoords="offset points",
            fontsize=7.5,
            color="#444444",
        )

    ax_l.set_xscale("log")
    ax_l.set_xlabel("field area (acres, log scale)")
    ax_l.set_ylabel("Polsby-Popper compactness (1 = circle)")
    ax_l.set_title("Compactness vs area", fontsize=10.5)
    ax_l.set_ylim(0.15, 0.80)
    ax_l.legend(fontsize=7.5, ncol=2, loc="lower left")

    order = rhos.sort_values("rho")
    colors = ["#9e9e9e" if g == "all fields" else
              STATE_COLORS.get(g, "#9e9e9e") if g in STATE_COLORS else "#7a7a7a"
              for g in order["group"]]
    ax_r.axvline(0, color="#333333", lw=1)
    ax_r.barh(range(len(order)), order["rho"], color=colors, alpha=0.75, height=0.6)
    ax_r.set_yticks(range(len(order)))
    ax_r.set_yticklabels([f"{g} (n={n})" for g, n in zip(order["group"], order["n"])], fontsize=8.5)
    ax_r.set_xlim(-1, 1)
    ax_r.set_xlabel("Spearman rho: area vs compactness")
    ax_r.set_title("No subgroup clears the noise floor", fontsize=10.5)
    for i, (_, row) in enumerate(order.iterrows()):
        offset = 0.04 if row["rho"] >= 0 else -0.04
        ax_r.text(
            row["rho"] + offset,
            i,
            f"{row['rho']:+.2f}  p={row['p']:.2f}",
            va="center",
            ha="left" if row["rho"] >= 0 else "right",
            fontsize=7.5,
            color="#333333",
        )

    fig.suptitle(
        "Field size barely predicts compactness — and the largest field is one of the roundest",
        fontsize=12,
        fontweight="bold",
        y=1.02,
    )
    path = save(
        fig,
        out_dir / "a3_size_vs_compactness.png",
        subtitle="Polsby-Popper = 4*pi*area / perimeter^2 in each field's UTM zone · rho over all 30 fields = "
        f"{rhos.loc[rhos['group'] == 'all fields', 'rho'].iloc[0]:+.2f}",
    )
    pooled = rhos[rhos["group"] == "all fields"].iloc[0]
    return {
        "id": "a3",
        "path": path,
        "category": "boundaries",
        "title": "Field size vs compactness, with subgroup correlations",
        "caption": (
            f"Across all 30 fields the rank correlation between area and compactness is "
            f"{pooled['rho']:+.2f} (p={pooled['p']:.2f}), and no subgroup - CSB only, OSM only, "
            "or any single grower - separates from zero. The two least compact fields are "
            "mid-sized Illinois CSB strips, while the single largest field is one of the "
            "roundest; size alone does not predict shape."
        ),
        "n": "30 fields",
        "stats": {row["group"]: {"rho": round(row["rho"], 3), "p": round(row["p"], 3)} for _, row in rhos.iterrows()},
    }


def build(farms, out_dir) -> list[dict]:
    figures = [
        field_size_distribution(farms, out_dir),
        edge_density(farms, out_dir),
        size_vs_compactness(farms, out_dir),
    ]
    _metrics(farms).to_csv(
        out_dir.parent / "tables" / "boundaries_field_metrics.csv", index=False
    )
    _rho_table(_metrics(farms)).to_csv(
        out_dir.parent / "tables" / "boundaries_compactness_rho.csv", index=False
    )
    return figures
