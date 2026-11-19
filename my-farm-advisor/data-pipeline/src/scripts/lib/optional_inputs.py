"""Optional-input helpers for upstream data outages.

Reporting steps must degrade per panel, not fail wholesale, when an upstream
source is unavailable. A missing table is treated as an empty frame so the
dependent panel is skipped while everything else still renders.
"""

from pathlib import Path

import pandas as pd


def read_optional_csv(path: Path | str) -> pd.DataFrame:
    """Return the CSV at *path*, or an empty frame when it does not exist."""
    target = Path(path)
    if not target.exists():
        return pd.DataFrame()
    return pd.read_csv(target)
