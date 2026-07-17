"""
Ten validity tests on the output of 3_resource_contribution.py.

Run after 3_resource_contribution.py. Prints PASS/FAIL with a one-line diagnostic
for each. Exits non-zero if any test fails so this can be wired into CI later.
"""

import sys
import pandas as pd
import numpy as np
from config import *

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format

# Tests cover BOTH the data assembly (script 3) and the carve-out (script 4),
# so we read the post-carve-out file which has the full column set.
OUT = f"{data_final}/cbcr_main_with_carveout.csv"
print(f"Loading {OUT}...")
df = pd.read_csv(OUT)
ext = pd.read_csv(extractive_royalty_yearly_data)
hq = pd.read_csv(hq_shares_yearly_data)
overrides = pd.read_csv(equity_add_back_overrides_data, comment="#")
overrides["add_back_equity"] = (
    overrides["add_back_equity"].astype(str).str.strip().str.upper().eq("TRUE")
)
no_eq = set(overrides.loc[~overrides["add_back_equity"], "iso3"])

print(f"  {len(df):,} rows; years {sorted(df['year'].unique())}\n")

results = []


def check(name, ok, detail):
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {name}\n         {detail}")
    results.append((name, ok, detail))


# ── Test 1: required columns present and no nulls in key fields ──
required = [
    "rent_total_usd",
    "rent_oil_gas_usd",
    "rent_coal_usd",
    "rent_minerals_usd",
    "captured_deductible_usd",
    "captured_cit_usd",
    "captured_equity_usd",
    "hq_share_oil_gas",
    "hq_share_coal",
    "hq_share_minerals",
    "alloc_weight_usd",
    "captured_deductible_allocated_usd",
    "captured_equity_allocated_usd",
    "profit_extractive_corrected",
    "equity_add_back_active",
    "rent_carry_forwarded",
]
missing = [c for c in required if c not in df.columns]
nulls = {c: int(df[c].isna().sum()) for c in required if c in df.columns}
bad_nulls = {c: n for c, n in nulls.items() if n > 0}
check(
    "T1: required columns present, no nulls",
    not missing and not bad_nulls,
    f"missing={missing}; null-counts={bad_nulls}" if (missing or bad_nulls) else
    f"all {len(required)} columns present, all non-null",
)

# ── Test 2: year coverage matches input CbCR ──
years_df = sorted(df["year"].dropna().unique())
expected_years = sorted(
    pd.read_csv(f"{data_final}/cbcr_main_disaggregated.csv")["year"]
    .dropna()
    .unique()
)
check(
    "T2: year coverage equals CbCR input",
    years_df == expected_years,
    f"output years {years_df} vs input {expected_years}",
)

# ── Test 3: rents and HQ shares non-negative ──
neg_rent = (
    (df["rent_oil_gas_usd"] < 0).sum()
    + (df["rent_coal_usd"] < 0).sum()
    + (df["rent_minerals_usd"] < 0).sum()
)
neg_hq = (
    (df["hq_share_oil_gas"] < 0).sum()
    + (df["hq_share_coal"] < 0).sum()
    + (df["hq_share_minerals"] < 0).sum()
)
check(
    "T3: rents and HQ shares non-negative",
    neg_rent == 0 and neg_hq == 0,
    f"negative rent cells: {neg_rent}; negative HQ cells: {neg_hq}",
)

# ── Test 4: HQ shares are constant within (parent, year) across rows ──
# (HQ share is a parent-level attribute; should not vary by partner)
nunique = (
    df.groupby(["iso_parent", "year"])[
        ["hq_share_oil_gas", "hq_share_coal", "hq_share_minerals"]
    ]
    .nunique()
    .max(axis=1)
)
n_violating = (nunique > 1).sum()
check(
    "T4: HQ shares constant within (parent, year)",
    n_violating == 0,
    f"{n_violating} (parent, year) cells have varying HQ shares (should be 0)",
)

# ── Test 5: rents are constant within (partner, year) across rows ──
nunique = (
    df.groupby(["iso_partner", "year"])[
        ["rent_oil_gas_usd", "rent_coal_usd", "rent_minerals_usd"]
    ]
    .nunique()
    .max(axis=1)
)
n_violating = (nunique > 1).sum()
check(
    "T5: rents constant within (partner, year)",
    n_violating == 0,
    f"{n_violating} (partner, year) cells have varying rents (should be 0)",
)

# ── Test 6: alloc_weight matches the per-row rent × HQ_share formula
#           (one row per cell — enforced upstream by sanity test A2) ──
expected = (
    df["rent_oil_gas_usd"] * df["hq_share_oil_gas"]
    + df["rent_coal_usd"] * df["hq_share_coal"]
    + df["rent_minerals_usd"] * df["hq_share_minerals"]
) * (1.0 - df["state_share"]) + np.where(
    df["iso_parent"] == df["iso_partner"],
    df["rent_total_usd"] * df["state_share"],
    0.0,
)
diff = (df["alloc_weight_usd"] - expected).abs()
max_err = float(diff.max())
check(
    "T6: alloc_weight matches rent × HQ_share formula",
    max_err < 1e-3,
    f"max abs diff vs (1-state_share)×Σ_c rent×hq + state_self_pool: ${max_err:.6f}",
)

# ── Test 7: captured_deductible allocation conservation per (partner, year) ──
# Sum allocated should equal captured when any row has positive weight.
cells = (
    df.groupby(["iso_partner", "year"])
    .agg(
        captured=("captured_deductible_usd", "first"),
        allocated=("captured_deductible_allocated_usd", "sum"),
        sum_w=("alloc_weight_usd", "sum"),
    )
    .reset_index()
)
# Allocated == captured when sum_w > 0 (within tolerance for float math)
mismatches = cells[
    (cells["sum_w"] > 0)
    & ((cells["allocated"] - cells["captured"]).abs() > 1.0)
]
# Allocated == 0 when sum_w == 0
should_be_zero = cells[(cells["sum_w"] == 0) & (cells["allocated"] != 0)]
check(
    "T7: captured_deductible conserved per (partner, year)",
    len(mismatches) == 0 and len(should_be_zero) == 0,
    f"{len(mismatches)} cells with weight>0 but allocation off by >$1; "
    f"{len(should_be_zero)} cells with weight=0 but non-zero allocation",
)

# ── Test 8: captured_equity gating — flagged-FALSE countries get zero ──
gated_rows = df[df["iso_partner"].isin(no_eq)]
gated_eq_alloc = float(gated_rows["captured_equity_allocated_usd"].sum())
check(
    "T8: equity add-back gating (FALSE-list partners get 0 equity allocated)",
    abs(gated_eq_alloc) < 1.0,
    f"sum of equity allocated to FALSE-list partners: ${gated_eq_alloc:,.0f} (expect 0)",
)

# ── Test 9: profit add-back identity ──
expected = (
    df["profit_loss_before_income_tax_corrected"].fillna(0.0)
    + df["captured_deductible_allocated_usd"]
    + df["captured_equity_allocated_usd"]
)
diff = (df["profit_extractive_corrected"] - expected).abs()
max_err = float(diff.max())
check(
    "T9: profit_extractive_corrected = profit + ded_alloc + eq_alloc",
    max_err < 1e-3,
    f"max abs diff: ${max_err:.6f} (must NOT include captured_cit)",
)

# ── Test 10: carry-forward flag aligns with original-zero years ──
# rent_carry_forwarded should only be True for rows whose (iso_partner, year)
# had zero WB rents in the ORIGINAL extractive panel (the WB base value was
# filled by ffill/bfill from another year). Note: the flag tracks the WB
# base only; per-category EITI/EIA/BGS overlay carries are tagged inside
# rent_source rather than this boolean.
ext_orig = ext[["iso3", "year", "wb_total_rents_usd"]].copy()
ext_orig["wb_total_rents_usd"] = pd.to_numeric(
    ext_orig["wb_total_rents_usd"], errors="coerce"
).fillna(0.0)
ext_orig["original_zero"] = ext_orig["wb_total_rents_usd"].eq(0)
chk = df.merge(
    ext_orig[["iso3", "year", "original_zero"]].rename(
        columns={"iso3": "iso_partner"}
    ),
    on=["iso_partner", "year"],
    how="left",
)
chk["original_zero"] = chk["original_zero"].fillna(True)
inconsistent = chk[chk["rent_carry_forwarded"] & (~chk["original_zero"])]
# Cells where flag is False but ext was zero AND there was a prior non-zero year
# would be mis-flagged. Hard to check strictly without re-running; instead require
# strict subset: flag-True only where original was zero.
check(
    "T10: carry-forward flag only True where original WB rents were zero",
    len(inconsistent) == 0,
    f"{len(inconsistent)} rows flagged carry-forwarded despite non-zero original WB rents",
)

# ── Final summary ──
n_pass = sum(1 for _, ok, _ in results if ok)
n_fail = len(results) - n_pass
print(f"\nResults: {n_pass}/{len(results)} passed, {n_fail} failed")
sys.exit(0 if n_fail == 0 else 1)
