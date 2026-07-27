# %%
"""
1b (shared paths) — Path shim for the Orbis CbCR-universe passes.

Resolves the repo-root-relative data directories shared by the step-1b passes.
Their nexus-matrix output stays under data/intermediate/extractive/ for backward
compatibility, even though it is a destination-sales product, not an extractive one.

Author: Alison Schultz (based on Javier Garcia-Bernardo's work).
Last updated: 2026-07-25.
"""
# %% MARK: 1. Shared paths
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent.parent
RAW = BASE / "data" / "raw"
INTERMEDIATE = BASE / "data" / "intermediate"
EXT_INT = INTERMEDIATE / "extractive"
EXT_INT.mkdir(parents=True, exist_ok=True)
