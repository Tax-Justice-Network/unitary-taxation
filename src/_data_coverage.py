"""Per-partner CbCR data-coverage metrics + the thin-coverage flag.

A country's UT estimate rests on the reported (parent, partner, year) cells
that mention it. Where those are very few, the estimate is data-thin and the
paper tables flag it (footnote [2]). Rule calibrated with the user 2026-07-22
(≤40 countries flagged; 37 under this rule):

    thin  <=>  n_cells < 10  OR  n_parents < 3  OR  n_years < 4

computed on REPORTED foreign cells (is_distributed == 0, iso_parent !=
iso_partner) over the paper window 2016-2022 excl 2020. Flags are always
computed from reported cells — also for gravity-sample tables (imputed rows
add no evidence; the gravity_imputation_inflated flag is a separate concern).

Usage:
    from _data_coverage import coverage_table, thin_iso_set
    cov = coverage_table()          # DataFrame indexed by iso_partner
    thin = thin_iso_set(cov)        # set of flagged ISO3
`coverage_table` also writes data_coverage_by_partner.csv to the
across-samples country_overview folder so every generator shares one file.
"""
import os
import sys

import pandas as pd

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SRC_DIR)
import config  # noqa: E402
from config import data_final  # noqa: E402

AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
CELLS_MIN, PARENTS_MIN, YEARS_MIN = 10, 3, 4

FOOTNOTE_TEXT = (
    "[2] Thin CbCR coverage: fewer than 10 reported country-cells, fewer than 3 "
    "reporting parent countries, or fewer than 4 of the 6 sample years underlie "
    "this country's estimate (reported foreign cells, 2016-2022 excl. 2020) — "
    "interpret with caution."
)


def coverage_table(write=True):
    cb = pd.read_csv(
        f"{data_final}cbcr_main_disaggregated.csv",
        usecols=["iso_parent", "iso_partner", "year", "is_distributed",
                 "profit_loss_before_income_tax_corrected", "n_cbcr"],
        low_memory=False)
    r = cb[(cb["is_distributed"] == 0) & cb["year"].isin(AVG_YEARS)
           & (cb["iso_parent"] != cb["iso_partner"])].copy()
    r["p"] = pd.to_numeric(r["profit_loss_before_income_tax_corrected"], errors="coerce")
    r = r[r["p"].notna()]
    g = r.groupby("iso_partner").agg(
        n_cells=("p", "size"),
        n_parents=("iso_parent", "nunique"),
        n_years=("year", "nunique"),
        n_cbcr_groups_sum=("n_cbcr", lambda s: pd.to_numeric(s, errors="coerce").sum()),
    )
    g["thin_data"] = ((g["n_cells"] < CELLS_MIN) | (g["n_parents"] < PARENTS_MIN)
                      | (g["n_years"] < YEARS_MIN))
    if write:
        tables_dir, _ = config.output_dirs("deliverables/country_sheet")
        out = os.path.join(tables_dir, "data_coverage_by_partner.csv")
        g.sort_values(["thin_data", "n_cells"], ascending=[False, True]).to_csv(out)
    return g


def thin_iso_set(cov=None):
    if cov is None:
        cov = coverage_table(write=False)
    return set(cov.index[cov["thin_data"]])
