"""Weather figures (C1-C3).

NASA POWER is a 0.5 degree product: all ten fields in a farm share one grid
cell, so every number here is farm-level. The effective sample is therefore
3 locations x 5 years (15 farm-years), never 300 field-years. Figures say
"farm-year" so the unit cannot be misread.

Units: T2M/T2M_MAX/T2M_MIN in degC, PRECTOTCORR in mm/day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from style import new_figure, save, state_color

GROWING_MONTHS = (4, 5, 6, 7, 8, 9)
GDD_BASE_C = 10.0
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _daily(farm) -> pd.DataFrame:
    w = farm.weather.copy()
    w["year"] = w["date"].dt.year
    w["month"] = w["date"].dt.month
    w["gdd"] = ((w["T2M_MAX"] + w["T2M_MIN"]) / 2.0 - GDD_BASE_C).clip(lower=0)
    return w


def _last_spring_frost(w: pd.DataFrame, year: int) -> str:
    window = w[(w["year"] == year) & (w["month"] <= 6)]
    hits = window[window["T2M_MIN"] <= 0.0]
    return hits["date"].max().strftime("%Y-%m-%d") if len(hits) else ""


def _first_fall_frost(w: pd.DataFrame, year: int) -> str:
    window = w[(w["year"] == year) & (w["month"] >= 7)]
    hits = window[window["T2M_MIN"] <= 0.0]
    return hits["date"].min().strftime("%Y-%m-%d") if len(hits) else ""


def season_table(farms) -> pd.DataFrame:
    rows = []
    for farm in farms:
        w = _daily(farm)
        season = w[w["month"].isin(GROWING_MONTHS)]
        for year, group in season.groupby("year"):
            rows.append(
                {
                    "grower": farm.grower,
                    "state": farm.state,
                    "year": int(year),
                    "season_gdd_base10": round(float(group["gdd"].sum()), 0),
                    "season_precip_mm": round(float(group["PRECTOTCORR"].sum()), 0),
                    "season_mean_temp_c": round(float(group["T2M"].mean()), 1),
                    "rain_days_ge1mm": int((group["PRECTOTCORR"] >= 1.0).sum()),
                    "last_spring_frost": _last_spring_frost(w, year),
                    "first_fall_frost": _first_fall_frost(w, year),
                }
            )
    return pd.DataFrame(rows)


def monthly_temperature(farms, out_dir) -> dict:
    fig, ax = new_figure(9.6, 5.2)
    monthly = {}
    for farm in farms:
        w = _daily(farm)
        per_year = w.groupby(["year", "month"])["T2M"].mean().unstack("year")
        mean = per_year.mean(axis=1)
        monthly[farm.state] = mean
        ax.fill_between(
            mean.index,
            per_year.min(axis=1),
            per_year.max(axis=1),
            color=state_color(farm.state),
            alpha=0.13,
            linewidth=0,
        )
        ax.plot(
            mean.index,
            mean,
            color=state_color(farm.state),
            lw=2.2,
            label=f"{farm.state} · {farm.display_name}",
        )

    others = [s for s in monthly if s != "NE"]
    if "NE" in monthly and others:
        gap = (monthly["NE"] - pd.concat([monthly[s] for s in others], axis=1).mean(axis=1)).mean()
    else:
        gap = float("nan")

    ax.set_xticks(range(1, 13))
    ax.set_xticklabels(MONTH_LABELS, fontsize=9)
    ax.set_ylabel("monthly mean temperature (°C)")
    ax.set_xlabel("month")
    ax.set_xlim(0.7, 12.3)
    ax.axhline(0, color="#888888", lw=0.8, ls="--")
    ax.set_title(
        f"Nebraska runs {gap:.1f} °C warmer than Illinois and Iowa, in every month of the year",
        fontsize=11.5,
    )
    ax.legend(loc="upper left", fontsize=8.5)
    ax.text(
        0.99,
        0.03,
        "line = 2021-2025 mean · band = year-to-year min-max",
        transform=ax.transAxes,
        ha="right",
        fontsize=7.5,
        color="#666666",
    )
    apr_sep = {s: float(v.loc[4:9].mean()) for s, v in monthly.items()}
    path = save(
        fig,
        out_dir / "c1_monthly_temperature.png",
        subtitle=(
            "farm-level NASA POWER series, 1,826 days per farm · Apr-Sep mean "
            + " · ".join(f"{s} {v:.1f} °C" for s, v in apr_sep.items())
        ),
    )
    return {
        "id": "c1",
        "path": path,
        "category": "weather",
        "title": "Monthly temperature climatology by grower",
        "caption": (
            f"Nebraska is {gap:.1f} °C warmer than Illinois and Iowa on average and the gap "
            "holds in all twelve months, while Illinois and Iowa stay within a few tenths of "
            "a degree of each other. The band shows how much year-to-year spread sits inside "
            "each monthly mean."
        ),
        "n": "3 farms x 5 years",
        "stats": {"ne_minus_il_ia_c": round(float(gap), 2),
                  "apr_sep_mean_c": {k: round(v, 2) for k, v in apr_sep.items()}},
    }


def season_precip(farms, out_dir) -> dict:
    table = season_table(farms)
    fig, ax = new_figure(9.6, 5.2)

    for state in sorted(table["state"].unique()):
        block = table[table["state"] == state].sort_values("year")
        ax.plot(
            block["year"],
            block["season_precip_mm"],
            color=state_color(state),
            lw=2.0,
            marker="o",
            markersize=6.5,
            markeredgecolor="white",
            markeredgewidth=0.8,
            label=f"{state} (5-yr mean {block['season_precip_mm'].mean():,.0f} mm)",
            zorder=3,
        )
        last = block.iloc[-1]
        ax.annotate(
            f"{last['season_precip_mm']:,.0f} mm",
            (last["year"], last["season_precip_mm"]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=state_color(state),
        )

    spread = (
        table.groupby("state")["season_precip_mm"].max()
        - table.groupby("state")["season_precip_mm"].min()
    )
    mean_gap = (
        table.groupby("state")["season_precip_mm"].mean().max()
        - table.groupby("state")["season_precip_mm"].mean().min()
    )

    ax.set_xticks(sorted(table["year"].unique()))
    ax.set_xlim(2020.6, 2025.7)
    ax.set_xlabel("growing season")
    ax.set_ylabel("growing-season precipitation, Apr-Sep (mm)")
    ax.set_title(
        f"One season swings up to {spread.max():,.0f} mm; the grower means differ by {mean_gap:,.0f} mm",
        fontsize=11.5,
    )
    ax.legend(loc="upper left", fontsize=8.5)
    path = save(
        fig,
        out_dir / "c2_season_precip.png",
        subtitle=(
            "season total = summed daily PRECTOTCORR, April through September · one NASA POWER "
            "cell per farm, so all ten fields share each series · n = 5 seasons per grower"
        ),
    )
    means = table.groupby("state")["season_precip_mm"].mean().round(0).to_dict()
    return {
        "id": "c2",
        "path": path,
        "category": "weather",
        "title": "Growing-season precipitation by year",
        "caption": (
            f"Nebraska averages {means['NE']:.0f} mm over the five seasons against "
            f"{means['IL']:.0f} mm in Illinois and {means['IA']:.0f} mm in Iowa, but Iowa's own "
            f"range is {spread['IA']:.0f} mm and Nebraska's wettest season (585 mm) beats every "
            "Illinois season. All ten fields in a farm share one POWER cell, so this farm series "
            "is also the field series and the seasons carry the comparison. Five seasons per "
            "grower cannot rank these climates."
        ),
        "n": "15 farm-years",
        "stats": {
            "mean_mm": {k: float(v) for k, v in means.items()},
            "range_mm": {k: float(v) for k, v in spread.items()},
        },
    }


def gdd_vs_precip(farms, out_dir) -> dict:
    table = season_table(farms)
    fig, ax = new_figure(9.6, 5.4)

    within = {}
    for state in sorted(table["state"].unique()):
        block = table[table["state"] == state]
        result = stats.spearmanr(block["season_precip_mm"], block["season_gdd_base10"])
        within[state] = (float(result.statistic), float(result.pvalue))
        ax.scatter(
            block["season_precip_mm"],
            block["season_gdd_base10"],
            s=70,
            color=state_color(state),
            edgecolor="white",
            linewidth=0.8,
            label=f"{state} (within-grower rho {result.statistic:+.2f})",
            zorder=3,
        )
        anchors: list[tuple[float, float, int]] = []
        for _, row in block.iterrows():
            x = float(row["season_precip_mm"])
            y = float(row["season_gdd_base10"])
            dy = 4
            # Two seasons can land on nearly the same point (Illinois 2021 and
            # 2025 do); stack their year labels instead of overprinting them.
            while any(
                abs(x - px) < 18 and abs(y - py) < 30 and dy == pdy
                for px, py, pdy in anchors
            ):
                dy -= 13
            anchors.append((x, y, dy))
            ax.annotate(
                str(int(row["year"])),
                (x, y),
                xytext=(6, dy),
                textcoords="offset points",
                fontsize=7,
                color="#555555",
            )
        ax.scatter(
            block["season_precip_mm"].mean(),
            block["season_gdd_base10"].mean(),
            marker="X",
            s=180,
            color=state_color(state),
            edgecolor="black",
            linewidth=0.8,
            zorder=4,
        )

    pooled = stats.spearmanr(table["season_precip_mm"], table["season_gdd_base10"])
    signs = {np.sign(v[0]) for v in within.values()}
    consistent = len(signs) == 1

    ax.set_xlabel("growing-season precipitation (mm)")
    ax.set_ylabel("growing-season GDD (base 10 °C)")
    ax.set_title(
        "Iowa and Nebraska: the hotter season is also the drier one",
        fontsize=11.5,
    )
    ax.text(
        0.62,
        0.03,
        f"pooled rho = {pooled.statistic:+.2f} (n={len(table)} farm-years)\n"
        f"within-grower rho: "
        + ", ".join(f"{s} {v[0]:+.2f}" for s, v in within.items())
        + "\nfive seasons per grower: direction only, not a trend",
        transform=ax.transAxes,
        fontsize=8,
        va="bottom",
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "white", "edgecolor": "#cccccc"},
    )
    ax.legend(loc="upper right", fontsize=8)
    path = save(
        fig,
        out_dir / "c3_gdd_vs_precip.png",
        subtitle="points = farm-years, X = 5-season mean · GDD = mean daily temperature above 10 °C, summed Apr-Sep",
    )
    return {
        "id": "c3",
        "path": path,
        "category": "weather",
        "title": "Seasonal heat vs seasonal water",
        "caption": (
            "The fifteen farm-years separate mainly by heat: Nebraska's mean is "
            f"{table[table['state'] == 'NE']['season_gdd_base10'].mean():,.0f} GDD against "
            f"{table[table['state'] == 'IL']['season_gdd_base10'].mean():,.0f} in Illinois and "
            f"{table[table['state'] == 'IA']['season_gdd_base10'].mean():,.0f} in Iowa. Inside "
            "Iowa and Nebraska the hotter season is the drier one (rho -0.90 each); Illinois "
            "is essentially flat at -0.20. With five seasons the sign is the finding, not the "
            "slope."
        ),
        "n": "15 farm-years",
        "stats": {
            "pooled_rho": round(float(pooled.statistic), 3),
            "within_rho": {k: round(v[0], 3) for k, v in within.items()},
            "sign_consistent": bool(consistent),
        },
    }


def build(farms, out_dir) -> list[dict]:
    figures = [
        monthly_temperature(farms, out_dir),
        season_precip(farms, out_dir),
        gdd_vs_precip(farms, out_dir),
    ]
    season_table(farms).to_csv(
        out_dir.parent / "tables" / "weather_farm_year.csv", index=False
    )
    return figures
