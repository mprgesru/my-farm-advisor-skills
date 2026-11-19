#!/usr/bin/env python3
"""Entry point for the field-sample EDA subskill.

    export DATA_PIPELINE_DATA_ROOT=$HOME/my-farm-advisor-runtime
    python scripts/run_field_eda.py --only boundaries
    python scripts/run_field_eda.py                 # all sections
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_SRC))

from cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
