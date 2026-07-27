"""Compute the (documented, NOT adopted) ETR-based tax-haven candidate list.

An outcome-based haven definition — pooled period-average ETR below a threshold —
was explored but deliberately NOT adopted (it drops marquee havens and adds
loss-year / tiny-profit non-havens), so there is no `TAX_HAVENS_REPRESENTATION_ETR`
constant in config.py. The candidate jurisdictions are documented in
`docs/tax_haven_lists.md` ("Explored but not adopted"); this script reproduces
them from the cleaned CbCR data and prints a set literal for that doc.

Definition (matches the comment in config.py):
  pooled period-average ETR = Σ income_tax_paid_on_cash_basis
                              ÷ Σ profit_loss_before_income_tax_corrected
  over the whole period, clipped to [0, 1] (the etr_average_corrected
  construction with window = entire period). A jurisdiction is a haven if that
  ETR is < THRESHOLD. Pure threshold: no profit floor, no union with the other
  lists. Jurisdictions with non-positive pooled profit are excluded.

Usage:
  python src/_build_etr_haven_list.py            # default threshold 0.10
  python src/_build_etr_haven_list.py 0.05       # custom threshold
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DATA = _PROJECT_ROOT / "data" / "final" / "cbcr_main_allsubgroupsonly.csv"

PROFIT_COL = "profit_loss_before_income_tax_corrected"
TAX_COL = "income_tax_paid_on_cash_basis"


def compute_period_etr(path=_DATA):
    """Return a DataFrame (iso_partner, etr_pooled, profit) for positive-profit jurisdictions."""
    df = pd.read_csv(path)
    g = df.groupby("iso_partner").agg(
        tax=(TAX_COL, "sum"), profit=(PROFIT_COL, "sum")
    )
    g["etr_pooled"] = (
        (g["tax"] / g["profit"]).replace([np.inf, -np.inf], np.nan).clip(0, 1)
    )
    return g[g["profit"] > 0].reset_index()


def build_list(threshold, path=_DATA):
    g = compute_period_etr(path)
    sel = g[g["etr_pooled"] < threshold].sort_values("etr_pooled")
    return sel


if __name__ == "__main__":
    threshold = float(sys.argv[1]) if len(sys.argv) > 1 else 0.10
    sel = build_list(threshold)
    print(f"# pooled ETR < {threshold:.2f}  ->  {len(sel)} jurisdictions")
    print("TAX_HAVENS_REPRESENTATION_ETR = {")
    for _, r in sel.iterrows():
        print(f'    "{r.iso_partner}",  # {r.etr_pooled * 100:.1f}%')
    print("}")
