"""
Scenario-4 calibration: compare new-system capture under the alpha-blended
5-factor formulas against the *current capture from CbCR-filing multinationals
only* — i.e., the part of resource capture and corporate tax revenue that
flows through the MNEs in our CbCR sample (which is what scenario 4 would
substitute for).

Inputs:
  output/unitary_taxation_incl_resource/tables/summary_country_year_long.csv
  data/final/cbcr_main_incl_resource.csv   (actual_resource_contribution_usd
                                            + income_tax_paid_on_cash_basis,
                                            both at the (parent, partner, year)
                                            level for CbCR-filing MNEs)

For each candidate formula (alpha_20pct / alpha_30pct / alpha_50pct), the new-
system capture for each source country S is approximated as

    new_capture[S] = Σ_year theoretical_profit[parent, partner=S, year] × CIT_S
                     (per-year statutory CIT; clipped to [0, 1])

The current capture from CbCR MNEs is

    cbcr_capture[S] = Σ income_tax_paid_on_cash_basis[parent, partner=S, year]
                     + Σ actual_resource_contribution_usd[parent, partner=S, year]

So the comparison is "what scenario 4 would yield" vs "what the CbCR-filing
MNEs currently pay to source country S in tax + royalty + equity income".

We report Σ new_capture vs Σ cbcr_capture globally, and a top-30 country-
level comparison.

Usage:  python _scenario4_calibration.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import output_dirs, data_final

WINDOW_YEARS = list(range(2016, 2023))
HEADLINE_YEARS = [2021, 2022]
DEFAULT_ETR = "average"
DEFAULT_RATE_MODE = "loss_cit_gain_etr"

ALPHA_FORMULAS = [
    "employees_payroll_resource_alpha_20pct",
    "employees_payroll_resource_alpha_30pct",
    "employees_payroll_resource_alpha_50pct",
]

tables_dir, _ = output_dirs("unitary_taxation_incl_resource")
long_csv = tables_dir / "summary_country_year_long.csv"
long_df = pd.read_csv(long_csv, low_memory=False)

# Reference: CbCR-MNE-attributable capture per source country = CIT they
# actually pay to the source country + resource capture (royalties + post-
# profit + equity) attributed to the same MNEs. Both are summed from the
# cbcr_main_incl_resource.csv file — so the comparison is restricted to
# capture that flows through MNEs in our CbCR sample (which is what
# scenario 4 actually replaces).
incl = pd.read_csv(
    Path(data_final) / "cbcr_main_incl_resource.csv",
    usecols=[
        "iso_partner", "year",
        "actual_resource_contribution_usd",
        "income_tax_paid_on_cash_basis",
    ],
    low_memory=False,
)


def calibration_table(years_filter, label):
    sub_incl = incl[incl["year"].isin(years_filter)].copy()
    sub_incl["cit_cbcr_musd"] = (
        pd.to_numeric(sub_incl["income_tax_paid_on_cash_basis"], errors="coerce").fillna(0) / 1e6
    )
    sub_incl["resource_capture_musd"] = (
        pd.to_numeric(sub_incl["actual_resource_contribution_usd"], errors="coerce").fillna(0) / 1e6
    )
    actual = sub_incl.groupby("iso_partner", as_index=False).agg(
        cit_cbcr_musd=("cit_cbcr_musd", "sum"),
        resource_capture_musd=("resource_capture_musd", "sum"),
    )
    actual["cbcr_capture_musd"] = actual["cit_cbcr_musd"] + actual["resource_capture_musd"]
    total_cbcr_cit = actual["cit_cbcr_musd"].sum()
    total_resource = actual["resource_capture_musd"].sum()
    total_actual = actual["cbcr_capture_musd"].sum()

    sub = long_df[
        long_df["year"].isin(years_filter)
        & (long_df["etr_name"] == DEFAULT_ETR)
        & (long_df["rate_mode"] == DEFAULT_RATE_MODE)
        & long_df["formula_name"].isin(ALPHA_FORMULAS)
    ].copy()

    # New capture[S] = Σ theoretical_profit attributed to partner=S × CIT[S]
    # `theoretical_profit` in the long file is already in MUSD (script 5 scales internally).
    sub["theoretical_profit_musd"] = pd.to_numeric(sub["theoretical_profit"], errors="coerce")
    sub["cit"] = pd.to_numeric(sub["cit"], errors="coerce").fillna(0.25).clip(lower=0, upper=1)
    sub["new_capture_musd"] = sub["theoretical_profit_musd"] * sub["cit"]

    per_formula = (
        sub.groupby(["formula_name", "iso_partner"], as_index=False)["new_capture_musd"].sum()
    )

    print(f"\n=== Calibration: {label} ===")
    print(f"CbCR-MNE attributable current capture over {label}:")
    print(f"  Σ CIT paid by CbCR MNEs:                ${total_cbcr_cit / 1e3:,.0f} B")
    print(f"  Σ resource capture (pre+post+equity):   ${total_resource / 1e3:,.0f} B")
    print(f"  Σ TOTAL current capture (CIT + resrc):  ${total_actual / 1e3:,.0f} B")
    print()
    print("Scenario 4 (substitution): UT replaces existing resource regime")
    print(f"  {'Formula':<46}{'Σ new_capture':>16}{'vs current':>14}{'ratio':>10}")
    for f in ALPHA_FORMULAS:
        sub_f = per_formula[per_formula["formula_name"] == f]
        total_new = sub_f["new_capture_musd"].sum()
        diff = total_new - total_actual
        ratio = total_new / total_actual if total_actual > 0 else 0
        print(f"  {f:<46}{total_new / 1e3:>14,.0f} B{diff / 1e3:>+12,.0f} B{ratio:>10.2f}")
    print()
    print("Scenario 5 (additive): existing resource regime keeps current capture,")
    print("                       UT runs on top → new_total = current_resource + UT_yield")
    print(f"  {'Formula':<46}{'Σ new_capture':>16}{'vs current':>14}{'ratio':>10}")
    for f in ALPHA_FORMULAS:
        sub_f = per_formula[per_formula["formula_name"] == f]
        ut_yield = sub_f["new_capture_musd"].sum()
        total_new = total_resource + ut_yield
        diff = total_new - total_actual
        ratio = total_new / total_actual if total_actual > 0 else 0
        print(f"  {f:<46}{total_new / 1e3:>14,.0f} B{diff / 1e3:>+12,.0f} B{ratio:>10.2f}")

    # Country-level comparison for the middle (30%) variant
    f_mid = ALPHA_FORMULAS[1]
    mid = per_formula[per_formula["formula_name"] == f_mid]
    merged = actual.merge(mid[["iso_partner", "new_capture_musd"]], on="iso_partner", how="outer").fillna(0)
    merged["delta_musd"] = merged["new_capture_musd"] - merged["cbcr_capture_musd"]
    merged["delta_pct"] = np.where(
        merged["cbcr_capture_musd"].abs() > 1,
        100 * merged["delta_musd"] / merged["cbcr_capture_musd"],
        np.nan,
    )
    merged = merged.sort_values("cbcr_capture_musd", ascending=False).head(30)
    out_csv = tables_dir / f"scenario4_calibration_{label.replace(' ','').replace('–','_')}.csv"
    merged.to_csv(out_csv, index=False)
    print(f"\nTop 30 source countries by current CbCR capture, comparison vs new ({f_mid}):")
    print(f"  {'iso':<5}{'CIT cur':>12}{'+resource':>12}{'= total':>12}{'new':>12}{'Δ':>12}{'Δ %':>8}")
    for _, r in merged.iterrows():
        pct_str = f"{r['delta_pct']:+.0f}%" if not pd.isna(r["delta_pct"]) else "n/a"
        print(f"  {r['iso_partner']:<5}{r['cit_cbcr_musd']:>12,.0f}{r['resource_capture_musd']:>12,.0f}"
              f"{r['cbcr_capture_musd']:>12,.0f}{r['new_capture_musd']:>12,.0f}"
              f"{r['delta_musd']:>+12,.0f}{pct_str:>8}")
    print(f"\n  (full table at {out_csv})")


calibration_table(WINDOW_YEARS, "2016-22")
calibration_table(HEADLINE_YEARS, "2021-22")
