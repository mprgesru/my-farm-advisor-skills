"""Shared plotting style for the field-sample EDA figures.

One colour per grower and one marker per boundary source are used across all
figures so a reader can carry a visual key from plot to plot.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

# Colour-blind safe, consistent across every figure in this subskill.
STATE_COLORS = {
    "IL": "#1f6fb2",  # blue
    "IA": "#2e8b57",  # green
    "NE": "#d97706",  # orange
}
# Non-crop classes get neutral greys so crop fills stay the focus.
CROP_COLORS = {
    "Corn": "#f2c14e",
    "Soybeans": "#4f7942",
    "Other crop": "#8fb8de",
    "Non-crop": "#b8b8b8",
    "Missing": "#e6e6e6",
}
SOURCE_COLORS = {"CSB": "#3b3b3b", "OSM": "#c0392b"}
SOURCE_MARKERS = {"CSB": "o", "OSM": "^"}

FIG_DPI = 200
FIG_SIZE = (9.0, 5.4)


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 110,
            "savefig.dpi": FIG_DPI,
            "font.size": 10,
            "axes.titlesize": 11.5,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.alpha": 0.25,
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def new_figure(
    width: float = FIG_SIZE[0],
    height: float = FIG_SIZE[1],
    nrows: int = 1,
    ncols: int = 1,
    **kwargs,
):
    """Figure with one axes, or a flat array of axes when a grid is requested."""
    fig, axes = plt.subplots(
        nrows, ncols, figsize=(width, height), squeeze=False, **kwargs
    )
    if nrows == 1 and ncols == 1:
        return fig, axes[0, 0]
    return fig, axes.ravel()


def save(fig, path: Path, *, subtitle: str | None = None, layout: bool = True) -> Path:
    """Save and close *fig*, stamping an n/units subtitle when given.

    ``layout=False`` is for figures that position axes with ``subplots_adjust``
    themselves because a figure-level legend or colourbar sits outside the
    axes; ``tight_layout`` would otherwise shrink the axes into that space.
    """
    if subtitle:
        fig.text(0.01, 0.005, subtitle, fontsize=7.5, color="#555555", ha="left")
    if layout:
        fig.tight_layout(rect=(0, 0.03, 1, 1) if subtitle else None)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(
        path,
        bbox_inches="tight" if layout else None,
        facecolor="white",
        pil_kwargs={"optimize": True, "compress_level": 9},
    )
    plt.close(fig)
    return path


def state_color(state: str) -> str:
    return STATE_COLORS.get(state, "#666666")
