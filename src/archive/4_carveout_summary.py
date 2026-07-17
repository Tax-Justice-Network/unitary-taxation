"""
Per-source-country summary comparing what extractive partner countries currently
capture (GRD/EITI/manual cascade) against what they would receive under the
flat rent x rate x HQ_share carve-out proposal (rent = layered EITI > BGS >
EIA > WB best estimate).

Run after 3_resource_contribution.py. Outputs:
- output/extractive/tables/carveout_vs_capture_by_partner_year.csv  (full panel)
- output/extractive/tables/carveout_vs_capture_by_partner.csv       (year-avg)
"""

import sys
import pandas as pd
import numpy as np
from config import *

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format

OUT_DIR, _ = output_dirs("extractive")

IN = f"{data_final}/cbcr_main_with_carveout.csv"
print(f"Loading {IN}...")
df = pd.read_csv(IN)
print(f"  {len(df):,} rows; years {sorted(df['year'].unique())}\n")

# Per-row carve-out is already in expected_royalty_usd. Sum it across parents
# to get the total proposed carve-out received by each (partner, year).
proposed = (
    df.groupby(["iso_partner", "year"], dropna=False)
    .agg(
        proposed_carveout_usd=("expected_royalty_usd", "sum"),
        alloc_weight_usd=("alloc_weight_usd", "sum"),
        n_parent_rows=("iso_parent", "size"),
    )
    .reset_index()
)

# Partner-level fields are constant within (partner, year) — take first.
partner_level = (
    df.groupby(["iso_partner", "year"], dropna=False)
    .agg(
        rent_total_usd=("rent_total_usd", "first"),
        rent_oil_gas_usd=("rent_oil_gas_usd", "first"),
        rent_coal_usd=("rent_coal_usd", "first"),
        rent_minerals_usd=("rent_minerals_usd", "first"),
        rent_source=("rent_source", "first"),
        captured_total_usd=("captured_total_usd", "first"),
        captured_deductible_usd=("captured_deductible_usd", "first"),
        captured_cit_usd=("captured_cit_usd", "first"),
        captured_equity_usd=("captured_equity_usd", "first"),
        captured_total_source=("captured_total_source", "first"),
        captured_deductible_source=("captured_deductible_source", "first"),
        captured_cit_source=("captured_cit_source", "first"),
        captured_equity_source=("captured_equity_source", "first"),
        captured_carry_forwarded=("captured_carry_forwarded", "first"),
        rent_carry_forwarded=("rent_carry_forwarded", "first"),
        effective_royalty_rate=("expected_royalty_rate", "first"),
    )
    .reset_index()
)
# Carve-out base = oil_gas + coal + minerals (forest excluded by design).
partner_level["rent_extractive_usd"] = partner_level[
    ["rent_oil_gas_usd", "rent_coal_usd", "rent_minerals_usd"]
].sum(axis=1, min_count=1)

panel = partner_level.merge(proposed, on=["iso_partner", "year"], how="outer")

# Coverage: how much of the partner's rent maps onto a CbCR-reporting parent
panel["hq_coverage_in_cbcr"] = np.where(
    panel["rent_total_usd"].fillna(0) > 0,
    panel["alloc_weight_usd"] / panel["rent_total_usd"],
    np.nan,
)

# Difference vs. actual capture (modelled carve-out minus existing capture)
panel["carveout_minus_capture_usd"] = (
    panel["proposed_carveout_usd"] - panel["captured_total_usd"]
)
panel["carveout_over_capture_ratio"] = np.where(
    panel["captured_total_usd"].fillna(0) > 0,
    panel["proposed_carveout_usd"] / panel["captured_total_usd"],
    np.nan,
)

# Floor framing: the carve-out as a minimum guarantee on existing capture.
# A country never gets less than what its current fiscal regime delivers;
# countries below the modelled level are lifted to it. This is the
# politically defensible framing -- well-functioning regimes (SAU, NOR,
# IRQ, KWT) keep what they have; weak regimes (ZAF, COD, GHA, GIN) get a
# top-up.
#
#   floor_carveout_usd  = max(modelled_carveout, captured_total)
#   additional_revenue  = max(0, modelled_carveout - captured_total)
#                       = floor_carveout - captured_total
panel["captured_total_usd_filled"] = panel["captured_total_usd"].fillna(0)
panel["proposed_carveout_usd_filled"] = panel["proposed_carveout_usd"].fillna(0)
panel["floor_carveout_usd"] = panel[
    ["captured_total_usd_filled", "proposed_carveout_usd_filled"]
].max(axis=1)
panel["additional_revenue_usd"] = (
    panel["floor_carveout_usd"] - panel["captured_total_usd_filled"]
)
panel = panel.drop(columns=["captured_total_usd_filled",
                             "proposed_carveout_usd_filled"])

# Drop partner rows that have no extractive footprint at all
panel = panel[
    (panel["rent_total_usd"].fillna(0) > 0)
    | (panel["captured_total_usd"].fillna(0) > 0)
    | (panel["proposed_carveout_usd"].fillna(0) > 0)
].copy()

panel = panel.sort_values(["iso_partner", "year"]).reset_index(drop=True)

OUT_PANEL = OUT_DIR / "carveout_vs_capture_by_partner_year.csv"
panel.to_csv(OUT_PANEL, index=False)
print(f"Wrote panel ({len(panel):,} rows): {OUT_PANEL}")

# Year-average view (mean across years where data is available)
mean_cols = [
    "rent_total_usd",
    "rent_oil_gas_usd",
    "rent_coal_usd",
    "rent_minerals_usd",
    "captured_total_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
    "proposed_carveout_usd",
    "floor_carveout_usd",
    "additional_revenue_usd",
    "alloc_weight_usd",
    "effective_royalty_rate",
    "hq_coverage_in_cbcr",
    "carveout_minus_capture_usd",
]
avg = (
    panel.groupby("iso_partner", dropna=False)[mean_cols].mean(numeric_only=True).reset_index()
)
years_per_partner = (
    panel.groupby("iso_partner", dropna=False)["year"]
    .agg(years_n="nunique", year_min="min", year_max="max")
    .reset_index()
)
avg = avg.merge(years_per_partner, on="iso_partner", how="left")
avg["carveout_over_capture_ratio"] = np.where(
    avg["captured_total_usd"].fillna(0) > 0,
    avg["proposed_carveout_usd"] / avg["captured_total_usd"],
    np.nan,
)
avg = avg.sort_values("additional_revenue_usd", ascending=False).reset_index(drop=True)

OUT_AVG = OUT_DIR / "carveout_vs_capture_by_partner.csv"
avg.to_csv(OUT_AVG, index=False)
print(f"Wrote year-avg ({len(avg):,} partners): {OUT_AVG}")

# Quick console preview, sorted by additional revenue (the floor framing's
# new-money number)
print("\nTop 20 partners by additional revenue from carve-out (year-avg, USD M):")
preview = avg.head(20).copy()
for c in ["rent_total_usd", "captured_total_usd", "proposed_carveout_usd",
          "floor_carveout_usd", "additional_revenue_usd",
          "carveout_minus_capture_usd"]:
    preview[c] = (preview[c] / 1e6).round(0)
preview["effective_royalty_rate"] = preview["effective_royalty_rate"].round(3)
preview["hq_coverage_in_cbcr"] = preview["hq_coverage_in_cbcr"].round(3)
preview["carveout_over_capture_ratio"] = preview["carveout_over_capture_ratio"].round(2)
print(
    preview[
        [
            "iso_partner",
            "captured_total_usd",
            "proposed_carveout_usd",
            "floor_carveout_usd",
            "additional_revenue_usd",
            "effective_royalty_rate",
            "hq_coverage_in_cbcr",
            "years_n",
        ]
    ].to_string(index=False)
)
