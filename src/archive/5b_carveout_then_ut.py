# %% [markdown]
# Carve-out then unitary taxation (UT): two-step analysis.
#
# Reads:  data/final/cbcr_main_with_carveout.csv  (one row per parent x partner x year)
# Writes: output/extractive/tables/carveout_then_ut/...
#
# ─── The carve-out, per (parent, partner) row ────────────────────────────
#
# The producing country's prior claim on its extraction value, allocated to
# this row, is
#
#   capture = max( minimum_royalty , min( actual_capture , rent ) )
#
#   minimum_royalty = expected_royalty_usd   (the modelled minimum royalty —
#                     Cat 1 by default; already scaled to the cross-border IOC
#                     pool and by (1 - state_share) in script 4)
#   actual_capture  = captured_total_usd × alloc_share   (everything the state
#                     actually takes from this extraction — royalties, excise,
#                     levies, bonuses/fees, SOE dividends/state equity, AND
#                     corporate income tax — we are deliberately instrument-
#                     agnostic; a CIT-reliant producer is protected like a
#                     royalty-reliant one)
#   rent            = rent_total_usd × alloc_share   (the cap: a state can't
#                     have a prior claim on more than the whole rent. This is
#                     what stops an inflated EITI "CIT" line — ordinary CIT on
#                     non-rent profit — from being treated as a prior claim:
#                     it pushes actual_capture above the rent and gets clipped.
#                     The rent-scaling floor in script 3 §3d deliberately does
#                     NOT scale the rent up to absorb CIT, so the clip bites.)
#   minimum is never capped: if the modelled minimum royalty exceeds the rent
#   estimate we keep the minimum.
#
# Of that claim, the part already EXPENSED in CbCR profit-before-tax
# (captured_deductible_allocated_usd: royalties / excise / levies) is already
# out of the pool. The remainder —
#
#   carveout_from_cbcr_profit = ( capture − captured_deductible_allocated )⁺
#
# — i.e. the royalty top-up above what was already expensed, plus the retained
# resource CIT, plus state equity / other — has to be carved out of CbCR
# profit-before-tax before UT runs. (We can't carve more than the positive
# profit actually booked in the cell, so it is clipped to that too.) No
# separate "add back then re-subtract": the netting is built in — if the state
# already meets the minimum and our modelled royalty is below its actual take,
# carveout_from_cbcr_profit only picks up the CIT/equity portion; the expensed
# royalties stay where they are.
#
#   profit_for_ut = ( profit_loss_before_income_tax_corrected − carveout_from_cbcr_profit )⁺
#
# → UT formulary apportionment redistributes profit_for_ut across each parent's
#   partners (SOTJ default: 50% employees + 50% payroll).
# → A producing country's resource take under the proposal ≈ `capture`
#   (= already-expensed royalties + carveout_from_cbcr_profit), and ≥
#   min(captured_total, rent), so no country gets less on its resources than it
#   currently does — except the few whose non-CIT capture alone already exceeds
#   the whole rent, who are capped at the rent.
#
# Two scenarios per country:
#   A. UT only — redistribute profit_loss_before_income_tax_corrected directly
#      (no carve-out). Resource instruments unchanged ⇒ compare formulary CIT
#      to current NON-resource CIT only (CbCR CIT − EITI resource CIT).
#   B. Carve-out then UT on profit_for_ut. Carve-out + the modelled royalty
#      replace the resource fiscal regime ⇒ compare (capture + formulary CIT on
#      the residual) to (all current resource revenue + current non-resource CIT).
#
# Toggle: APPLY_CARVEOUT=False reverts to plain UT on reported profit (= A).

# %%
import sys
import warnings
from pathlib import Path

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import data_final, output_dirs

ROOT = Path(__file__).resolve().parent.parent
INP = Path(data_final) / "cbcr_main_with_carveout.csv"
_TABLES_DIR, _ = output_dirs("extractive")
OUT_DIR = _TABLES_DIR / "carveout_then_ut"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# %% [1] Configuration
# SOTJ default formula: 50% employees + 50% payroll
FORMULA_VARS = ["n_employees", "payroll"]
FORMULA_WEIGHTS = [0.5, 0.5]

APPLY_CARVEOUT = True  # False ⇒ skip the carve-out, run UT on reported profit

# Columns
PROFIT_REPORTED = "profit_loss_before_income_tax_corrected"  # CbCR-reported profit before income tax
MIN_ROYALTY_USD = "expected_royalty_usd"        # modelled minimum royalty (= PRIMARY_CATEGORY in 4_carveout.py).
                                                # Point at expected_royalty_cat2_usd / _cat3_usd for another variant.
CAPTURED_DEDUCTIBLE_ALLOC = "captured_deductible_allocated_usd"  # actual royalty-like (expensed) take, per-row (script 3)
CIT_RATE_COL = "cit"                            # statutory CIT rate per partner-year
CAPTURED_TOTAL = "captured_total_usd"
CAPTURED_DEDUCTIBLE = "captured_deductible_usd"
CAPTURED_CIT = "captured_cit_usd"
CAPTURED_EQUITY = "captured_equity_usd"
TAX_PAID_COL = "income_tax_paid_on_cash_basis"  # CbCR income tax paid, per (parent, partner)

# %% [2] Load data
print(f"Loading {INP}...")
df = pd.read_csv(INP, low_memory=False)
print(f"  {len(df):,} rows; years {sorted(df['year'].unique())}")
df = df.copy()
for c in [PROFIT_REPORTED, MIN_ROYALTY_USD, CAPTURED_DEDUCTIBLE_ALLOC, "alloc_weight_usd",
          "rent_total_usd", CAPTURED_TOTAL, CAPTURED_CIT] + FORMULA_VARS:
    if c not in df.columns:
        raise RuntimeError(f"Required column '{c}' missing from input")

# %% [3] Carve-out, per (parent, partner) row
_w = df["alloc_weight_usd"].fillna(0.0)
_w_sum = _w.groupby([df["iso_partner"], df["year"]]).transform("sum")
_alloc_share = np.where(_w_sum > 0, _w / _w_sum, 0.0)

# CbCR-attributable fraction of each producing country's modelled rent = the
# share of the rent that actually landed on a CbCR cell (Σ alloc_weight / rent,
# capped at 1). The complement is non-multinational / invisible domestic
# extraction — it shows up in EITI/GRD government revenue but has no CbCR profit
# counterpart, so we scale the captured government revenue down to the
# attributable share before using it anywhere. Where this fraction is 0 (e.g.
# the state takes ~100% of the rent and there is no domestic CbCR cell — UAE,
# Iraq, Kuwait, Qatar, Libya, Oman, … ) the country's resource sector is simply
# out of scope: no carve-out, not charged to any baseline.
_rent_py = df["rent_total_usd"].fillna(0.0)
_attr = (_w_sum.div(_rent_py.where(_rent_py > 0))).fillna(0.0).clip(upper=1.0).to_numpy()
df["cbcr_attributable_fraction"] = _attr

# Allocate the (CbCR-attributable share of the) partner-year quantities to rows.
df["captured_total_allocated_usd"] = df[CAPTURED_TOTAL].fillna(0.0) * _attr * _alloc_share
df["captured_cit_allocated_usd"]   = df[CAPTURED_CIT].fillna(0.0) * _attr * _alloc_share
df["rent_allocated_usd"]           = df["rent_total_usd"].fillna(0.0) * _alloc_share
# Attributable royalty-like (expensed) take, allocated; and the "other"/GRD-
# residual take, allocated. Both are treated as ALREADY OUT of CbCR pre-tax
# profit (like expensed royalties), so NOT carved out of profit again.
_ded = df[CAPTURED_DEDUCTIBLE_ALLOC].fillna(0.0) * _attr
_other_alloc = (
    (df[CAPTURED_TOTAL].fillna(0.0) - df[CAPTURED_DEDUCTIBLE].fillna(0.0)
     - df[CAPTURED_CIT].fillna(0.0) - df[CAPTURED_EQUITY].fillna(0.0)).clip(lower=0.0)
    * _attr * _alloc_share
)
df["captured_deductible_alloc_attr_usd"] = _ded
df["captured_other_alloc_attr_usd"] = _other_alloc
_already_out = _ded + _other_alloc  # the part of `capture` already outside pre-tax profit
_min_royalty = df[MIN_ROYALTY_USD].fillna(0.0)  # already CbCR-attributable (scaled by Σ hq_share × (1-state_share) in script 4)
P_raw = pd.to_numeric(df[PROFIT_REPORTED], errors="coerce").fillna(0.0)
# Loss-making cells are floored at 0 for the apportionment base (consistent
# across both scenarios; this simplified script does not net losses).
P = P_raw.clip(lower=0.0)
df["profit_reported_cbcr_raw_usd"] = P_raw       # true CbCR profit incl. loss cells
df["profit_before_carveout"] = P                 # positive-cell profit = UT-only base

if APPLY_CARVEOUT:
    # capture = max( minimum_royalty , actual_capture ).
    # The "max = 100% of rent" cap is intentionally calibrated to the country's
    # own current capture (so it never binds below it) — i.e. effectively no
    # cap. Reason: the rent cap was meant to clip an EITI "CIT" line that's
    # really ordinary CIT on non-rent profit, but in the data it clips ≈$0/yr
    # (the rent-scaling floor already lifts the rent estimate to match capture),
    # while leaving it in place made resource economies "lose" their entire
    # current resource revenue in scenario B for a routing reason unrelated to
    # the cap. So: capture is at least the modelled minimum royalty and at least
    # what the state already takes; the residual profit (incl. any ordinary-CIT
    # base above the rent) still flows through UT only insofar as it sits in an
    # observable CbCR cell.
    df["capture_allocated_usd"] = np.maximum(_min_royalty, df["captured_total_allocated_usd"])
    # The part of `capture` still sitting inside CbCR profit-before-tax = capture
    # minus what's already out of it (expensed royalty-like + "other").
    _carveout_target = (df["capture_allocated_usd"] - _already_out).clip(lower=0.0)
    # Can't carve out more than the positive profit booked in the cell.
    df["carveout_from_cbcr_profit_usd"] = np.minimum(_carveout_target, P.clip(lower=0.0))
    # Reporting: the modelled-minimum top-up above what the state already takes via
    # royalty-like / other (non-profit) instruments.
    df["royalty_topup_usd"] = np.minimum(
        (_min_royalty - _already_out).clip(lower=0.0), P.clip(lower=0.0)
    )
else:
    df["capture_allocated_usd"] = 0.0
    df["carveout_from_cbcr_profit_usd"] = 0.0
    df["royalty_topup_usd"] = 0.0

df["profit_for_ut"] = (P - df["carveout_from_cbcr_profit_usd"]).clip(lower=0.0)
df["profit_after_carveout"] = df["profit_for_ut"]  # alias for UT step
# What the producing country newly retains out of CbCR profit (on top of the
# royalties it already collected — those were already expensed).
df["carveout_to_source_usd"] = df["carveout_from_cbcr_profit_usd"]


# %% [4] UT formulary apportionment
def apply_ut_misalignment(d, profit_var, formula_vars, formula_weights):
    """SOTJ misalignment redistribution. Adds: share_economy, theoretical_profit, misaligned_profit."""
    d = d.copy()
    activity = pd.Series(0.0, index=d.index)
    for var, weight in zip(formula_vars, formula_weights):
        if weight <= 0 or var not in d.columns:
            continue
        v = pd.to_numeric(d[var], errors="coerce").fillna(0.0).clip(lower=0.0)
        total_by_parent = v.groupby(d["iso_parent"]).transform("sum")
        share = np.where(total_by_parent > 0, v / total_by_parent, 0.0)
        activity = activity + share * weight
    d["economic_activity_partner_of_parent"] = activity
    total_activity_by_parent = activity.groupby(d["iso_parent"]).transform("sum")
    d["share_economy"] = np.where(total_activity_by_parent > 0, activity / total_activity_by_parent, 0.0)
    total_profit_by_parent = d.groupby("iso_parent")[profit_var].transform("sum")
    d["theoretical_profit"] = d["share_economy"] * total_profit_by_parent
    d["misaligned_profit"] = d[profit_var] - d["theoretical_profit"]
    return d


print("\nUT scenario A: UT-only on reported CbCR profit (no carve-out)...")
df_a = apply_ut_misalignment(df, "profit_before_carveout", FORMULA_VARS, FORMULA_WEIGHTS)
print("UT scenario B: carve-out then UT on residual profit...")
df_b = apply_ut_misalignment(df, "profit_after_carveout", FORMULA_VARS, FORMULA_WEIGHTS)


# %% [5] Per-partner carve-out + UT panel
def agg_partner(d, profit_var, label):
    return (
        d.groupby(["iso_partner", "year"])
        .agg(**{
            f"theoretical_profit_{label}": ("theoretical_profit", "sum"),
            f"reported_profit_{label}":    (profit_var, "sum"),
            f"misalignment_{label}":       ("misaligned_profit", "sum"),
        })
        .reset_index()
    )


a = agg_partner(df_a, "profit_before_carveout", "ut_only")
b = agg_partner(df_b, "profit_after_carveout", "carveout_then_ut")

cascade_totals = (
    df.groupby(["iso_partner", "year"])
    .agg(
        profit_reported_cbcr=("profit_before_carveout", "sum"),
        carveout_retained_from_profit=("carveout_from_cbcr_profit_usd", "sum"),
        royalty_topup=("royalty_topup_usd", "sum"),
        resource_cit_in_carveout=("captured_cit_allocated_usd", "sum"),
        capture_total_modelled=("capture_allocated_usd", "sum"),
        profit_ut_base=("profit_for_ut", "sum"),
    )
    .reset_index()
)

panel = (
    a.merge(b, on=["iso_partner", "year"], how="outer")
     .merge(cascade_totals, on=["iso_partner", "year"], how="outer")
     .fillna(0.0)
)
# Negative misalignment ⇒ the partner is a source country losing profit to havens;
# UT brings it back. ut_gain = -misalignment when negative, else 0.
panel["ut_gain_only"] = (-panel["misalignment_ut_only"]).clip(lower=0.0)
panel["ut_gain_after_carveout"] = (-panel["misalignment_carveout_then_ut"]).clip(lower=0.0)
panel["total_gain_carveout_plus_ut"] = panel["carveout_retained_from_profit"] + panel["ut_gain_after_carveout"]
panel["delta_total_gain"] = panel["total_gain_carveout_plus_ut"] - panel["ut_gain_only"]

panel = panel.sort_values(["iso_partner", "year"]).reset_index(drop=True)
PANEL_OUT = OUT_DIR / "carveout_then_ut_by_partner_year.csv"
panel.to_csv(PANEL_OUT, index=False)
print(f"\nWrote per-partner-year panel: {PANEL_OUT}")

_mean_cols = [c for c in panel.columns if c not in ("iso_partner", "year")]
avg = (
    panel.groupby("iso_partner")[_mean_cols].mean().reset_index()
    .sort_values("total_gain_carveout_plus_ut", ascending=False)
)
AVG_OUT = OUT_DIR / "carveout_then_ut_by_partner.csv"
avg.to_csv(AVG_OUT, index=False)
print(f"Wrote year-avg summary: {AVG_OUT}")

print("\n=== Top 20 source-country GAINERS (year-avg, $M) ===")
preview = avg.head(20).copy()
for c in ["carveout_retained_from_profit", "ut_gain_only", "ut_gain_after_carveout",
          "total_gain_carveout_plus_ut", "delta_total_gain"]:
    preview[c] = (preview[c] / 1e6).round(0)
print(preview[["iso_partner", "carveout_retained_from_profit", "ut_gain_only",
               "ut_gain_after_carveout", "total_gain_carveout_plus_ut", "delta_total_gain"]].to_string(index=False))


# %% [9] Extractive-sector accounting: profit waterfall (HQ side) + net gains (producing-country side)
#
# Scope: the whole CbCR/UT universe. The carve-out is a country-level instrument
# (it acts on all profit booked in a resource-producing jurisdiction; CbCR has
# no industry split), so the carve-out *amounts* are simply zero outside genuine
# extraction — restricting the footprint here would change nothing material.
#
# The carve-out is deducted on the PARENT/HQ side (it reduces the profit pool of
# the MNEs that own the production), so the profit waterfall is grouped by
# iso_parent. The redistribution and the net revenue gain land on the PRODUCING
# country (iso_partner) side. captured_* are partner-year quantities — taken once
# per partner-year (a parent==partner "self" row exists for only ~1/5 of them).
print("\nBuilding extractive-sector accounting...")
_ny = df["year"].nunique()
G   = lambda d, c: d[c].sum() / 1e9
GY  = lambda d, c: d[c].sum() / 1e9 / _ny
GYp = lambda d, c: d[c].clip(lower=0).sum() / 1e9 / _ny

# ── (a) Profit waterfall by HQ/parent country ──────────────────────────────
# Decompose carveout_from_cbcr_profit into three components that partition it:
# the modelled royalty top-up (above states' royalties), then resource CIT,
# then the residual (state equity / SOE dividends / other in pre-tax profit).
df_b2 = df_b.copy()
_co = df_b2["carveout_from_cbcr_profit_usd"]
_rt = df_b2["royalty_topup_usd"].clip(upper=_co)
_cit_part = np.minimum(df_b2["captured_cit_allocated_usd"], (_co - _rt).clip(lower=0.0))
df_b2["co_royalty_topup_usd"] = _rt
df_b2["co_resource_cit_usd"]  = _cit_part
df_b2["co_equity_other_usd"]  = (_co - _rt - _cit_part).clip(lower=0.0)
hq = (
    df_b2.groupby(["iso_parent", "year"], as_index=False).agg(
        profit_reported_cbcr=("profit_before_carveout", "sum"),
        carveout_royalty_topup=("co_royalty_topup_usd", "sum"),
        carveout_resource_cit=("co_resource_cit_usd", "sum"),
        carveout_equity_other=("co_equity_other_usd", "sum"),
        carveout_total_from_profit=("carveout_from_cbcr_profit_usd", "sum"),
        profit_ut_base=("profit_for_ut", "sum"),
    )
)
hq = hq.sort_values(["iso_parent", "year"]).reset_index(drop=True)
HQ_OUT = OUT_DIR / "extractive_accounting_by_hq.csv"
hq.to_csv(HQ_OUT, index=False)
print(f"Wrote profit waterfall by HQ country: {HQ_OUT}")

# ── (b) Net gains by producing/partner country ─────────────────────────────
# "Current resource revenue" here = the CbCR-ATTRIBUTABLE part of GRD/EITI
# capture (scaled by cbcr_attributable_fraction in §3): the part attributable to
# CbCR-filing operators (IOCs / CbCR-filing SOEs). The non-attributable part —
# non-multinational/invisible domestic extraction that's in EITI but not in any
# CbCR cell — is left out of the analysis entirely.
_raw_resource_rev = (
    df[["iso_partner", "year", CAPTURED_TOTAL]].drop_duplicates(["iso_partner", "year"])[CAPTURED_TOTAL]
    .pipe(lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0)).sum()
)
_attr_resource_rev = df["captured_total_allocated_usd"].sum()
print(f"  [resource revenue: ${_raw_resource_rev/1e9:,.0f}B raw (GRD/EITI) → ${_attr_resource_rev/1e9:,.0f}B "
      f"CbCR-attributable; ${(_raw_resource_rev-_attr_resource_rev)/1e9:,.0f}B "
      f"(${(_raw_resource_rev-_attr_resource_rev)/1e9/_ny:,.0f}B/yr) is non-multinational/invisible domestic and out of scope]")

# df, df_a, df_b share the same row order (apply_ut_misalignment copies in place),
# so theoretical profit can be lifted across by position.
work = df[["iso_parent", "iso_partner", "year", "profit_before_carveout", "profit_for_ut",
           "carveout_from_cbcr_profit_usd", "capture_allocated_usd", "captured_cit_allocated_usd",
           "captured_total_allocated_usd", "captured_deductible_alloc_attr_usd", "captured_other_alloc_attr_usd",
           "cbcr_attributable_fraction", MIN_ROYALTY_USD, CIT_RATE_COL, TAX_PAID_COL]].copy()
work["theo_ut_only_row"] = df_a["theoretical_profit"].to_numpy()
work["theo_ut_after_carveout_row"] = df_b["theoretical_profit"].to_numpy()
work["cit_rate"] = pd.to_numeric(work[CIT_RATE_COL], errors="coerce").fillna(0.0)
work["tax_paid"] = pd.to_numeric(work[TAX_PAID_COL], errors="coerce").fillna(0.0).clip(lower=0.0)

acct = (
    work.groupby(["iso_partner", "year"], as_index=False).agg(
        profit_reported_cbcr=("profit_before_carveout", "sum"),
        profit_ut_base=("profit_for_ut", "sum"),
        carveout_retained_from_profit=("carveout_from_cbcr_profit_usd", "sum"),
        capture_routable_from_cbcr=("capture_allocated_usd", "sum"),  # part of the claim that lands on observable CbCR rows
        min_royalty_total=(MIN_ROYALTY_USD, "sum"),                   # Σ modelled minimum royalty over the partner-year
        resource_rev_total=("captured_total_allocated_usd", "sum"),   # CbCR-attributable resource revenue
        resource_rev_royaltylike=("captured_deductible_alloc_attr_usd", "sum"),
        resource_rev_cit=("captured_cit_allocated_usd", "sum"),
        resource_rev_other=("captured_other_alloc_attr_usd", "sum"),
        cit_paid_cbcr_in_country=("tax_paid", "sum"),
        cbcr_attributable_fraction=("cbcr_attributable_fraction", "first"),
        theo_ut_only=("theo_ut_only_row", "sum"),
        theo_ut_after_carveout=("theo_ut_after_carveout_row", "sum"),
        cit_rate=("cit_rate", "first"),
    )
)
acct["resource_rev_equity"] = (
    acct["resource_rev_total"] - acct["resource_rev_royaltylike"]
    - acct["resource_rev_cit"] - acct["resource_rev_other"]
).clip(lower=0.0)
# Raw (country-level) EITI/GRD resource CIT — used as a FLOOR on how much of the
# CbCR income tax paid in the country is resource CIT, so we don't bucket the
# oil/mining majors' income tax (which is genuinely resource CIT) as
# "non-resource CIT" in the scenario-B baseline when the country's attributable
# resource revenue is thin (its NOC doesn't file CbCR). For big SOE economies
# the attributable resource revenue dominates instead, so no double-counting.
_cit_full = (df[["iso_partner", "year", CAPTURED_CIT]].drop_duplicates(["iso_partner", "year"])
             .rename(columns={CAPTURED_CIT: "captured_cit_full"}))
_cit_full["captured_cit_full"] = pd.to_numeric(_cit_full["captured_cit_full"], errors="coerce").fillna(0.0)
acct = acct.merge(_cit_full, on=["iso_partner", "year"], how="left")
acct["captured_cit_full"] = acct["captured_cit_full"].fillna(0.0)
# "Non-resource CIT" = CbCR income tax paid in the country MINUS the larger of
# (the CbCR-attributable resource revenue) and (the EITI/GRD resource CIT).
# Floored at 0.
acct["cit_paid_non_resource"] = (
    acct["cit_paid_cbcr_in_country"] - np.maximum(acct["resource_rev_total"], acct["captured_cit_full"])
).clip(lower=0.0)
# For producing countries whose resource sector is entirely out of scope
# (cbcr_attributable_fraction ≈ 0 — a state-dominated resource economy with no
# CbCR footprint we can attach the carve-out to, e.g. Libya, Iraq, Kuwait,
# Qatar, Oman, …), the CbCR income tax booked there is overwhelmingly the
# (out-of-scope) resource sector — the oil/mining majors' local income tax — so
# it should not be counted as "non-resource CIT" in the comparison either.
acct.loc[acct["cbcr_attributable_fraction"].fillna(0.0) <= 0.01, "cit_paid_non_resource"] = 0.0

# Scenario A — UT only. Resource instruments unchanged ⇒ delta is purely the
# generic-CIT take vs current NON-resource CIT.
acct["ut_only_cit_take"] = acct["cit_rate"] * acct["theo_ut_only"].clip(lower=0.0)
acct["ut_only_net_gain"] = acct["ut_only_cit_take"] - acct["cit_paid_non_resource"]
acct["ut_only_profit_reallocated"] = acct["theo_ut_only"] - acct["profit_reported_cbcr"]

# Scenario B — carve-out + UT. The producing country's resource take is just a
# country-year quantity: the larger of its CURRENT take and our modelled minimum
# royalty — `resource_take_B = max( captured_total , min_royalty_total )`. (No
# row allocation is needed for this — the per-cell `capture_allocated`/
# `carveout_from_cbcr_profit` machinery only determines *which* CbCR cells the
# carve-out comes out of, i.e. which parents' profit pools shrink for the UT
# step.) With this, no country is ever modelled as getting less on its resources
# than today. Plus formulary CIT on the residual; compare to all current
# resource revenue + current non-resource CIT.
acct["resource_take_B"] = np.maximum(acct["resource_rev_total"], acct["min_royalty_total"])
acct["ut_ext_cit_take"] = acct["cit_rate"] * acct["theo_ut_after_carveout"].clip(lower=0.0)
acct["ut_ext_total_take"] = acct["resource_take_B"] + acct["ut_ext_cit_take"]
acct["ut_ext_baseline"] = acct["resource_rev_total"] + acct["cit_paid_non_resource"]
acct["ut_ext_net_gain"] = acct["ut_ext_total_take"] - acct["ut_ext_baseline"]
acct["ut_ext_profit_reallocated"] = acct["theo_ut_after_carveout"] - acct["profit_ut_base"]

acct = acct.sort_values(["iso_partner", "year"]).reset_index(drop=True)
ACCT_OUT = OUT_DIR / "extractive_accounting_by_partner_year.csv"
acct.to_csv(ACCT_OUT, index=False)
print(f"Wrote net gains by producing country (panel): {ACCT_OUT}")
acct_avg = (acct.groupby("iso_partner").mean(numeric_only=True).reset_index()
            .sort_values("ut_ext_net_gain", ascending=False))
ACCT_AVG_OUT = OUT_DIR / "extractive_accounting_by_partner.csv"
acct_avg.to_csv(ACCT_AVG_OUT, index=False)
print(f"Wrote net gains by producing country (year-avg): {ACCT_AVG_OUT}")

# ── Console summary ────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("EXTRACTIVE-SECTOR ACCOUNTING ($B; 'pooled' = sum 2016-2022, '/yr' = per-year avg)")
print("=" * 80)
_net_cbcr_profit = df["profit_reported_cbcr_raw_usd"].sum() / 1e9
print("Profit waterfall — deducted on the HQ/parent side (whole CbCR universe):")
print(f"  Profit reported in CbCR (positive cells; loss cells floored at 0)  pooled {G(hq,'profit_reported_cbcr'):>9,.0f}   /yr {GY(hq,'profit_reported_cbcr'):>8,.0f}")
print(f"    [memo: net of loss cells the total is ${_net_cbcr_profit:,.0f}B pooled / ${_net_cbcr_profit/_ny:,.0f}B per yr]")
print(f"  − carve out for source countries, of which:        pooled {G(hq,'carveout_total_from_profit'):>9,.0f}   /yr {GY(hq,'carveout_total_from_profit'):>8,.0f}")
print(f"      modelled royalty top-up (above states' royalties)              /yr {GY(hq,'carveout_royalty_topup'):>8,.0f}")
print(f"      resource CIT retained at source                                /yr {GY(hq,'carveout_resource_cit'):>8,.0f}")
print(f"      state equity / SOE dividends / other in profit                 /yr {GY(hq,'carveout_equity_other'):>8,.0f}")
print(f"  = profit base for UT                               pooled {G(hq,'profit_ut_base'):>9,.0f}   /yr {GY(hq,'profit_ut_base'):>8,.0f}")
print()
print("Resource revenue collected today (EITI/GRD, all instruments):")
print(f"  total {GY(acct,'resource_rev_total'):>7,.0f}/yr  =  royalty-like {GY(acct,'resource_rev_royaltylike'):>6,.0f}  +  CIT {GY(acct,'resource_rev_cit'):>5,.0f}  +  equity/SOE {GY(acct,'resource_rev_equity'):>5,.0f}  +  other {GY(acct,'resource_rev_other'):>6,.0f}")
print(f"  CbCR income tax paid in producing countries {GY(acct,'cit_paid_cbcr_in_country'):>7,.0f}/yr  ⇒  non-resource CIT {GY(acct,'cit_paid_non_resource'):>7,.0f}/yr")
print(f"  Modelled resource take = max(current take, modelled min royalty) {GY(acct,'resource_take_B'):>7,.0f}/yr   (current take {GY(acct,'resource_rev_total'):>6,.0f}/yr; modelled min royalty {GY(acct,'min_royalty_total'):>6,.0f}/yr; newly out of CbCR profit {GY(acct,'carveout_retained_from_profit'):>6,.0f}/yr)")
print()
print("Scenario A — UT ONLY (no carve-out)   [baseline = current non-resource CIT only]")
print(f"  Profit reallocated to gaining countries (gross)        /yr {GYp(acct,'ut_only_profit_reallocated'):>8,.0f}")
print(f"  Net revenue gain — gainers only                        /yr {GYp(acct,'ut_only_net_gain'):>8,.0f}")
print(f"  Net revenue change — all countries (net)               /yr {GY(acct,'ut_only_net_gain'):>8,.0f}")
print()
print("Scenario B — CARVE-OUT + UT   [baseline = all current resource revenue + non-resource CIT]")
print(f"  Profit reallocated to gaining countries (gross)        /yr {GYp(acct,'ut_ext_profit_reallocated'):>8,.0f}")
print(f"  Net revenue gain — gainers only                        /yr {GYp(acct,'ut_ext_net_gain'):>8,.0f}")
print(f"  Net revenue change — all countries (net)               /yr {GY(acct,'ut_ext_net_gain'):>8,.0f}")
