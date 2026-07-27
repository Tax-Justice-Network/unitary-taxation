"""
9i2 — Consolidation bounds: UT on the OECD positive-profit sub-group panel.

The headline UT pools each parent country's cells NET of losses ("Total (All
sub-groups)" panel) — implicitly full cross-border AND cross-group loss
offsetting. This script builds the OPPOSITE pole: the UT run on the
"Sub-groups with positive profits" panel only, with the negative-profit panel
contributing ZERO taxable profit to any jurisdiction (its losses neither shrink
the pool nor earn recovery credits; its factors claim nothing).

Three-number bracket (no double counting — the bounds are alternative worlds):
  revenue UPPER bound  = this positive-panel run          (no loss offsetting)
  headline             = all-groups panel                  (in between)
  revenue LOWER bound  = 9i (net pool + zero tax on loss cells)

CAVEAT: the OECD split is by the sign of each group's profit PER JURISDICTION
(sub-group = one group's entities in one partner country), NOT by group-wide
profitability. True group-level consolidation is unobservable in aggregate CbCR
data and lies inside the bracket.

Usage (three stages):
  python 9i2_consolidation_upper_bound.py prep       # build data/final/cbcr_main_positive_panel.csv
  # then run the UT on it:
  #   RUN_DATASET=disaggregated RUN_INPUT_FILE=cbcr_main_positive_panel.csv \
  #   RUN_OUTPUT_TOPIC=unitary_taxation_positive_panel REPORTED_ONLY=1 \
  #   DEST_SUBSET=destmnedds python 5_estimate_profit_shifting.py
  # and refresh the lower bound (9i now includes the baseline scenario):
  #   python 9i_loss_floored_sensitivity.py
  python 9i2_consolidation_upper_bound.py assemble   # bracket tables

Outputs (topic deliverables/loss_consolidation_sensitivity):
  consolidation_bounds_by_income_group.csv / _by_region.csv / _country_long.csv
Sample: reported-only. Scenario: BASELINE (no resource correction — script 4's
correction is keyed to the all-groups panel). Units: per-year average over
2016-2022 excl 2020, constant 2025 USD (paper convention).
"""
import os
import sys
import glob

import numpy as np
import pandas as pd

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC_DIR)
sys.path.insert(0, _SRC_DIR)
import config  # noqa: E402
from config import data_final  # noqa: E402

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

POSITIVE_PANEL_FILE = f"{data_final}cbcr_main_positive_panel.csv"
GROUPING_POS = "Sub-groups with positive profits"
GROUPING_NEG = "Sub-groups with negative profits"

AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
N_AVG_YEARS = len(AVG_YEARS)
_DEFL = config.deflator_to_base()

HEADLINE_FORMULA = "sales_employees_destmnedds"
HEADLINE_RATE = "loss_cit_gain_etr"
HEADLINE_ETR = "domfor"
HEADLINE_STUB = f"{HEADLINE_FORMULA}__etrdef_{HEADLINE_ETR}__etrmax_inf__{HEADLINE_RATE}"

IG_ORDER = ["low_income", "lower_middle_income", "upper_middle_income",
            "high_income", "investment_hub"]
REGION_ORDER = ["Africa", "Asia", "Latin America", "Caribbean/American isl.",
                "Northern America", "Europe", "Oceania"]

CAVEAT = (
    "Consolidation bounds: the positive-panel run (upper bound) apportions only the "
    "OECD 'Sub-groups with positive profits' panel — loss-making sub-groups contribute "
    "zero taxable profit to every jurisdiction (no pool shrink, no recovery credit, no "
    "factor claim). The 9i loss-consolidation figure is the lower bound (net pool + "
    "zero tax on loss cells). The OECD sub-group split is by sign of each group's "
    "profit PER JURISDICTION, not group-wide profitability, so true group-level "
    "consolidation is unobservable here and lies inside the bracket."
)


def _lp(p):
    if sys.platform == "win32":
        ap = os.path.abspath(p)
        if not ap.startswith("\\\\?\\"):
            return "\\\\?\\" + ap
    return p


# ── stage 1: prep ────────────────────────────────────────────────────────────
def prep():
    print("Building the positive-panel UT input dataset ...")
    cb = pd.read_csv(f"{data_final}cbcr_main.csv", low_memory=False)
    n_all = (cb["grouping"] == "Total (All sub-groups)").sum()
    pos = cb[cb["grouping"] == GROUPING_POS].copy()
    print(f"  rows: all-groups panel {n_all:,} | positive panel {len(pos):,}")
    pos = pos.drop(columns=["grouping"])

    # payroll exactly as script 2 builds it
    pos["payroll"] = (
        pd.to_numeric(pos["n_employees"], errors="coerce").fillna(0)
        * pd.to_numeric(pos["wage_monthly"], errors="coerce").fillna(0)
        * 12
    )
    # the whole panel is directly reported
    pos["is_distributed"] = 0

    # destination shares (script 2 normally merges these)
    dest = pd.read_csv(f"{_ROOT}/data/intermediate/destination_based_sales.csv")
    dest_cols = [c for c in dest.columns if c not in ("iso_partner", "year")]
    pos = pos.merge(dest, on=["iso_partner", "year"], how="left")
    n_dest = pos["mne_plus_dds_share"].notna().sum()
    print(f"  merged destination shares ({len(dest_cols)} cols); "
          f"mne_plus_dds_share coverage {n_dest:,}/{len(pos):,}")

    pos.to_csv(POSITIVE_PANEL_FILE, index=False)
    print(f"  wrote {POSITIVE_PANEL_FILE}  ({len(pos):,} rows)")
    print("\nNow run the UT on it:\n"
          "  RUN_DATASET=disaggregated RUN_INPUT_FILE=cbcr_main_positive_panel.csv \\\n"
          "  RUN_OUTPUT_TOPIC=unitary_taxation_positive_panel REPORTED_ONLY=1 \\\n"
          "  DEST_SUBSET=destmnedds python 5_estimate_profit_shifting.py")


# ── stage 2: assemble the bracket ───────────────────────────────────────────
def _load_country_estimates(tables_inner_dir, stub):
    """Per-country revenue gain + taxable-profit change for one spec, converted
    to per-year-average constant-2025-USD millions."""
    p = os.path.join(tables_inner_dir, f"country_estimates__{stub}.csv")
    d = pd.read_csv(_lp(p), low_memory=False)
    d = d[d["year"].isin(AVG_YEARS)]
    cf = d["year"].map(_DEFL).fillna(1.0) / N_AVG_YEARS
    for c in ("revenue_gain_from_ut", "theoretical_profit", "reported_profit"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0) * cf
    g = d.groupby(["iso_partner", "wb_income_group", "region_tjn"],
                  dropna=False, as_index=False).agg(
        revenue_gain=("revenue_gain_from_ut", "sum"),
        theoretical_profit=("theoretical_profit", "sum"),
        reported_profit=("reported_profit", "sum"),
    )
    return g


def assemble():
    tables_dir, _ = config.output_dirs("deliverables/loss_consolidation_sensitivity")

    # upper bound: positive-panel run
    up_dir = os.path.join(_ROOT, "output", "unitary_taxation", "reported_only",
                          "positive_panel", "tables", "disaggregated")
    if not glob.glob(os.path.join(up_dir, "country_estimates__*.csv")):
        sys.exit(f"[error] no positive-panel run found under {up_dir} — "
                 "run stage 'prep' + the script-5 command first.")
    up = _load_country_estimates(up_dir, HEADLINE_STUB).rename(columns={
        "revenue_gain": "upper_bound_rev_musd",
        "theoretical_profit": "upper_theoretical_musd",
        "reported_profit": "positive_panel_reported_musd"})

    # headline: all-groups baseline run
    head_dir = os.path.join(_ROOT, "output", "unitary_taxation", "reported_only",
                            "baseline", "tables", "disaggregated")
    head = _load_country_estimates(head_dir, HEADLINE_STUB).rename(columns={
        "revenue_gain": "headline_rev_musd",
        "theoretical_profit": "headline_theoretical_musd",
        "reported_profit": "allpanel_reported_musd"})

    # lower bound: 9i baseline output
    lc_path = os.path.join(tables_dir, "loss_consolidation_country_long.csv")
    lc = pd.read_csv(lc_path)
    lc = lc[(lc["sample"] == "reported_only") & (lc["scenario"] == "baseline")
            & (lc["formula"] == HEADLINE_FORMULA) & (lc["rate_mode"] == HEADLINE_RATE)
            & (lc["etr_threshold"].astype(str) == "inf")
            & lc["etr"].astype(str).str.contains(HEADLINE_ETR)]
    if lc.empty:
        sys.exit("[error] 9i baseline rows missing in loss_consolidation_country_long.csv "
                 "— rerun 9i_loss_floored_sensitivity.py (now includes the baseline scenario).")
    lo = lc.groupby(["iso_partner"], as_index=False).agg(
        lower_bound_rev_musd=("revenue_gain_loss_consolidated_musd", "sum"))

    # negative-panel accounting (zeroed loss mass), per-year-average 2025 USD
    cb = pd.read_csv(f"{data_final}cbcr_main.csv",
                     usecols=["iso_partner", "year", "grouping",
                              "profit_loss_before_income_tax_corrected"], low_memory=False)
    neg = cb[(cb["grouping"] == GROUPING_NEG) & cb["year"].isin(AVG_YEARS)].copy()
    neg["v"] = (pd.to_numeric(neg["profit_loss_before_income_tax_corrected"],
                              errors="coerce").fillna(0.0)
                * neg["year"].map(_DEFL).fillna(1.0) / N_AVG_YEARS)
    negc = neg.groupby("iso_partner", as_index=False)["v"].sum().rename(
        columns={"v": "zeroed_loss_cells_musd"})
    negc["zeroed_loss_cells_musd"] /= 1e6

    m = (head.merge(up, on=["iso_partner", "wb_income_group", "region_tjn"], how="outer")
             .merge(lo, on="iso_partner", how="left")
             .merge(negc, on="iso_partner", how="left"))
    for c in ("headline_rev_musd", "upper_bound_rev_musd", "lower_bound_rev_musd",
              "zeroed_loss_cells_musd"):
        m[c] = m[c].fillna(0.0)
    m["bracket_width_musd"] = m["upper_bound_rev_musd"] - m["lower_bound_rev_musd"]

    cols = ["iso_partner", "wb_income_group", "region_tjn",
            "lower_bound_rev_musd", "headline_rev_musd", "upper_bound_rev_musd",
            "bracket_width_musd", "zeroed_loss_cells_musd",
            "allpanel_reported_musd", "positive_panel_reported_musd",
            "headline_theoretical_musd", "upper_theoretical_musd"]
    long = m[cols].sort_values("headline_rev_musd", ascending=False)
    long.to_csv(os.path.join(tables_dir, "consolidation_bounds_country_long.csv"), index=False)

    val = ["lower_bound_rev_musd", "headline_rev_musd", "upper_bound_rev_musd",
           "bracket_width_musd", "zeroed_loss_cells_musd"]
    byg = (m.groupby("wb_income_group")[val].sum().reindex(IG_ORDER) / 1e3).round(2)
    byg.to_csv(os.path.join(tables_dir, "consolidation_bounds_by_income_group.csv"))
    byr = (m.groupby("region_tjn")[val].sum().reindex(REGION_ORDER) / 1e3).round(2)
    byr.to_csv(os.path.join(tables_dir, "consolidation_bounds_by_region.csv"))

    with open(os.path.join(tables_dir, "README_CONSOLIDATION_BOUNDS.txt"),
              "w", encoding="utf-8") as fh:
        fh.write(CAVEAT + "\n")

    # ── verification ──
    lo_t, he_t, up_t = (m[c].sum() / 1e3 for c in
                        ("lower_bound_rev_musd", "headline_rev_musd", "upper_bound_rev_musd"))
    print(f"\n=== consolidation bracket, headline spec ({HEADLINE_STUB}) ===")
    print(f"  world Δ revenue/yr ($B, 2025 USD): LOWER {lo_t:,.1f}  <=  "
          f"HEADLINE {he_t:,.1f}  <=  UPPER {up_t:,.1f}")
    if not (lo_t <= he_t + 1e-6):
        print("  [WARN] ordering violated: lower > headline — investigate")
    if not (he_t <= up_t + 1e-6):
        print("  [WARN] ordering violated: headline > upper — investigate "
              "(possible if the positive panel's ETRs/coverage differ materially)")
    print(f"  zeroed loss cells: {m.zeroed_loss_cells_musd.sum()/1e3:,.1f} $B/yr "
          f"(reported losses excluded from the base)")
    print("\nby income group ($B/yr):")
    print(byg.to_string())
    print("\n" + CAVEAT)


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else ""
    if stage == "prep":
        prep()
    elif stage == "assemble":
        assemble()
    else:
        sys.exit("usage: 9i2_consolidation_upper_bound.py {prep|assemble}")
