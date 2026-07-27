# %%
"""
4 — Correct CbCR profits & taxes for resource-related government payments.

Emit three deliverable datasets ready for unitary-taxation analysis.

The script takes `cbcr_main_disaggregated.csv` and the (HQ, source, commodity,
year) resource-payment panel and writes three files, each self-contained for
running script 5:

  1) data/final/cbcr_main_excl_resource.csv
       "Resources excluded" — strip the resource profit base and the matching
       resource tax. Use for normal UT on the non-extractive corporate income
       only. Ships with the recomputed non-resource ETR family.
         profit_loss_excl_resource
            = profit_loss_before_income_tax_corrected − resource_profit_base_usd
         income_tax_paid_on_cash_basis_excl_resource
            = income_tax_paid_on_cash_basis − resource_tax_deduction_usd
       The tax deduction is NOT the external post-profit payment figure —
       payments not booked in the CbCR income-tax line must not be deducted
       from it. It is derived from the CbCR tax line itself, per cell (method
       recorded in `resource_correction_method`): ETR-gap cells strip the tax
       in excess of the statutory CIT; inert cells strip the payment-derived
       profit base at the cell's OWN reported effective tax rate; only the
       negative-post relief case (e.g. UK decommissioning refunds) passes the
       external figure through. External payments shape the PROFIT base
       (post ÷ rate, vs equity), never the tax line directly.
       ETR columns: etr_average_excl_resource / etr_partner_median_excl_resource /
       etr_partner_p25_excl_resource / etr_partner_min_excl_resource /
       etr_parent_partner_excl_resource (diagnostic; missing on distributed
       rows by design).

  2) data/final/cbcr_main_incl_resource.csv
       "Resources included" — gross profit & tax up by the actual pre-profit
       resource payments (royalties, surface fees, signature & production
       bonuses, PSA profit-oil entitlements). The diagnostic
       `actual_resource_contribution_usd` carries the total state take
       (pre + post + equity) for the comparison with UT yield.
         profit_loss_incl_resource
            = profit_loss_before_income_tax_corrected + pre_profit_payments_usd
         income_tax_paid_on_cash_basis_incl_resource
            = income_tax_paid_on_cash_basis        + pre_profit_payments_usd
       ETRs carried over from the excl_resource computation (same column names,
       same values) so script 5 picks them up unchanged. Also carries the
       EXPLORATORY `resource_factor_usd` (gross production value × ownership
       share per (parent, partner, year)) — no paper scenario uses it; kept
       for experimenting with resource-weighted apportionment designs.

  3) "Resources excluded, minimum royalty enforced" — same logic as (1) but the
       per-row `floor_add_on_{v}_usd` (the extra royalty the IGF-ATAF flexible
       floor would have compelled where the state's TOTAL resource take —
       pre-profit payments + post-profit taxes + equity income — fell below it)
       is also deducted from the UT profit pool, on top of the
       resource_profit_base removal. The tax line is left unchanged (the floor
       is a hypothetical royalty, not a counterfactual CIT). Total state
       recovery under this regime = UT-derived revenue on the smaller pool
       + Σ floor_add_on. Cat 1 (price-based) is the headline and fills the
       unsuffixed alias columns; cat2 / cat3 are computed alongside.
       Written TWICE, differing only in where the floor add-on sits:

     3a) data/final/cbcr_main_excl_resource_floored.csv
       Each source country's total floor add-on RE-ALLOCATED onto its
       directly-reported rows (revenue-weighted), so the reported-only sample
       carries the full country floor — INCLUDING the slices whose owner has
       no CbCR line anywhere (owners in non-reporting jurisdictions; see the
       unmatched-floor diagnostic), which join the country pool here. The
       headline scenario-3 input (script 5 dataset `excl_resource_floored`).

     3b) data/final/cbcr_main_excl_resource_floored_allrows.csv
       The floor add-on left split across ALL rows (reported + imputed);
       cell-less owner slices are DROPPED here (per-line semantics).
       Used for the gravity / full sample, and — run reported-only — as the
       floor-allocation sensitivity (script 5 dataset
       `excl_resource_floored_allrowsalloc`): only the slice of each country's
       floor that fell on reported rows enters, bracketing the allocation
       choice against 3a.

`cbcr_main_disaggregated.csv` (no resource correction; the "resources ignored"
baseline) is untouched by this script. No `cbcr_main_incl_resource_floored.csv`
is emitted: a minimum-royalty floor is meaningful only on the excl_resource
base (incl_resource is a reference dataset, not a paper scenario).

Pipeline step 4 — after 2 (disaggregate) and the 3_extractive_prep chain, before 5 (estimation).

Reads:
  data/final/cbcr_main_disaggregated.csv                                  — disaggregated CbCR baseline (script 2)
  data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv  — (HQ, source, commodity, year) payment panel (3_31 → 3_33 → 3_38)
  data/raw/extractive/resource_profit_tax_rate.csv                        — effective resource profit-tax rate by source × commodity; statutory CIT fallback
  data/raw/extractive/resource_country_parameters.csv                     — include flag, curated resource rate r, EITI flag (source of truth)
  data/intermediate/extractive/rents_combined_yearly.csv                  — EITI > BGS > EIA > WB layered rents per (iso3, year, category)
  data/intermediate/extractive/rent_fractions_calibrated.csv              — per-(iso, category) rent fractions for back-computing gross revenue
  data/intermediate/extractive/hq_shares_by_commodity_yearly.csv          — Orbis-derived HQ shares per (year, hq_iso3, commodity)
  src/3_extractive_prep/_reference_prices.py                              — Brent, coal, iron-ore-anchor price tables

Writes:
  data/final/cbcr_main_excl_resource.csv                                  — (1) resources excluded (+ recomputed non-resource ETR family)
  data/final/cbcr_main_incl_resource.csv                                  — (2) resources included (+ actual_resource_contribution_usd, resource_factor_usd)
  data/final/cbcr_main_excl_resource_floored.csv                          — (3a) excl + IGF-ATAF floor, add-on re-allocated to reported rows
  data/final/cbcr_main_excl_resource_floored_allrows.csv                  — (3b) excl + IGF-ATAF floor, add-on split across all rows

Usage:
  python 4_correcting_cbcr_for_resource_payments.py                       — full run
  DISAGG_BOOT_SUFFIX=__boot<n> python 4_correcting_cbcr_for_resource_payments.py — correct a per-seed bootstrap file (seed-tagged outputs)

Author: Alison Schultz.
Created: 2026-06-03.  Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
# 0. Setup: imports, paths, shared constants
import os
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import data_raw, data_final, data_intermediate_extractive, TAX_HAVENS_FUNCTIONAL
from _reference_prices import (
    BRENT_USD_BBL, COAL_AUS_USD_T, MINERAL_PRICES, RENT_FRAC_DEFAULT,
)
from _etr_construction import compute_partner_year_etrs


# Single disaggregated input (gravity activity + profitability profit).
# DISAGG_BOOT_SUFFIX (e.g. "__boot7") lets the domestic/foreign bootstrap driver
# resource-correct a per-seed disaggregated file and write matching seed-tagged
# output files; empty (default) in normal runs.
_DB = os.environ.get("DISAGG_BOOT_SUFFIX", "")
CBCR = f"{data_final}cbcr_main_disaggregated{_DB}.csv"
PAY = f"{data_intermediate_extractive}resource_payments_by_hq_source_yearly.csv"
RATE = "../data/raw/extractive/resource_profit_tax_rate.csv"
ECR = f"{data_raw}extractive/effective_resource_cit_rates.csv"   # combined effective resource rate (r) for the ETR-gap
RENTS = f"{data_intermediate_extractive}rents_combined_yearly.csv"
RENT_FRAC = f"{data_intermediate_extractive}rent_fractions_calibrated.csv"
HQ_SHARES = f"{data_intermediate_extractive}hq_shares_by_commodity_yearly.csv"
HQ_SHARES_BY_SOURCE = f"{data_intermediate_extractive}hq_shares_by_source_commodity_yearly.csv"
PARAMS = "../data/raw/extractive/resource_country_parameters.csv"   # consolidated source of truth: include flag, curated resource rate r, EITI flag

OUT_EXCL = f"{data_final}cbcr_main_excl_resource{_DB}.csv"
OUT_INCL = f"{data_final}cbcr_main_incl_resource{_DB}.csv"
OUT_EXCL_FLOOR = f"{data_final}cbcr_main_excl_resource_floored{_DB}.csv"
# Two floored files (always written): the default carries the floor add-on
# REALLOCATED onto reported rows (for the REPORTED sample, where it is the
# headline); the _allrows file carries the floor add-on split across ALL rows
# (for the gravity / full-disaggregation sample). Script 5 picks the right one
# by REPORTED_ONLY.
OUT_EXCL_FLOOR_ALLROWS = f"{data_final}cbcr_main_excl_resource_floored_allrows{_DB}.csv"

PCOL = "profit_loss_before_income_tax_corrected"
TCOL = "income_tax_paid_on_cash_basis"
RATE_MIN, RATE_MAX = 0.05, 0.95   # sanity bounds on the profit-tax divisor

# Shared commodity reference (prices + historical bands; floor schedules and
# the exploratory resource factor)
CATEGORIES = ("oil_gas", "coal", "minerals")
CAT_REF_PRICES = {
    "oil_gas": BRENT_USD_BBL,
    "coal": COAL_AUS_USD_T,
    "minerals": MINERAL_PRICES["2601"],   # iron ore CFR China — single anchor
}
HIST_PRICE_MIN = {c: min(p.values()) for c, p in CAT_REF_PRICES.items()}
HIST_PRICE_MAX = {c: max(p.values()) for c, p in CAT_REF_PRICES.items()}


def _yearly_lookup(table, year):
    year = int(year)
    if year in table:
        return table[year]
    avail = sorted(table.keys())
    return table[avail[0]] if year < avail[0] else table[avail[-1]]





# ETR family suffix on the resource-corrected (non-resource) ETRs.
ETR_SUFFIX = "excl_resource"
ETR_COLS_PARTNER = [
    f"etr_domestic_{ETR_SUFFIX}",
    f"etr_foreign_{ETR_SUFFIX}",
    f"etr_average_{ETR_SUFFIX}",
    f"etr_partner_median_{ETR_SUFFIX}",
    f"etr_partner_p25_{ETR_SUFFIX}",
    f"etr_partner_p10_{ETR_SUFFIX}",
    f"etr_partner_min_{ETR_SUFFIX}",
]
ETR_COL_PAIR = f"etr_parent_partner_{ETR_SUFFIX}"

# Pre-existing ETR columns on the disaggregated file. These are dropped from
# all three new output files: they were computed on reported (pre-correction)
# profit/tax and have no methodological meaning once the profit/tax columns
# are resource-corrected.
ETR_COLS_TO_DROP = [
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_p10_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
]




# %% [markdown] MARK: 2. Resources excluded (machinery)
# 1. Output (1) — resources excluded: allocator + non-resource ETR machinery
#    (cbcr_main_excl_resource.csv)

# %%
# The cell allocator and the non-resource ETR construction: payment-level
# corrections land on CbCR cells here, and the excl_resource (profit, tax)
# pair gets its partner-year ETR family.

def _allocate_payments_to_cbcr_cells(cbcr, agg, payment_cols):
    """Merge an (iso_parent, iso_partner, year)-keyed `agg` frame onto cbcr,
    then split each cell-level payment across its rows in proportion to the
    row's gross revenue (fallback: equal split). Returns df with the merged
    payment columns. cbcr can have >1 row per cell when bad-reporter
    disaggregation appended a distributed row alongside the directly-reported
    one."""
    df = cbcr.merge(agg, on=["iso_parent", "iso_partner", "year"], how="left")
    for c in payment_cols:
        df[c] = df[c].fillna(0.0)

    cell = ["iso_parent", "iso_partner", "year"]
    rev = pd.to_numeric(df["total_revenues"], errors="coerce").fillna(0.0).abs()
    rev_sum = rev.groupby([df[c] for c in cell]).transform("sum")
    n_rows = df.groupby(cell)[PCOL].transform("size")
    w = np.where(rev_sum > 0, rev / rev_sum.replace(0, np.nan), 1.0 / n_rows)
    w = pd.Series(w, index=df.index).fillna(1.0 / n_rows)

    for c in payment_cols:
        df[c] = df[c] * w
    return df


def _compute_excl_resource_etrs(df):
    """Compute the non-resource ETR family from (profit_loss_excl_resource,
    income_tax_paid_on_cash_basis_excl_resource). ETRs are calculated only
    from directly-reported rows (is_distributed == 0), to avoid imputed
    tax / profit values flowing into the ETR construction.

    Returns (partner_year_df, pair_year_df) ready to merge back onto df.
    Pair ETR is NaN on distributed rows by design (no real report for that
    (parent, partner, year) cell)."""
    reported = df[df["is_distributed"] == 0].copy()
    partner_year, pair_year = compute_partner_year_etrs(
        reported,
        profit_col="profit_loss_excl_resource",
        tax_col="income_tax_paid_on_cash_basis_excl_resource",
        suffix=ETR_SUFFIX,
        window=2,
        pair_stats=True,
    )
    return partner_year, pair_year


def _attach_etrs(df, partner_year, pair_year):
    """Merge the non-resource ETR columns onto df.

    Partner-year stats (domestic/foreign/average/median/p25/min) merge on
    (iso_partner, year) and so apply to distributed rows too — they are
    properties of the partner-year, not the specific pair.

    Pair ETR merges on (iso_parent, iso_partner, year), then is force-NaNed
    on distributed rows: even though the rolling window could pick up a
    real report of the same pair in another year, the user has decided that
    the pair-ETR column is a diagnostic that should ONLY carry a value when
    the (parent, partner, year) cell itself was directly reported. is_distributed
    == 1 → NaN."""
    df = df.merge(partner_year, on=["iso_partner", "year"], how="left")
    df = df.merge(pair_year, on=["iso_parent", "iso_partner", "year"], how="left")
    df.loc[df["is_distributed"] == 1, ETR_COL_PAIR] = np.nan
    return df


def _fill_excl_resource_etrs(df):
    """Mirror 1_clean.fill_missing_cit_and_corrected_etrs for the excl_resource
    ETR family. Where the measured partner-year ETR is UNDEFINED (NaN) — e.g. the
    negligible / non-positive pooled-profit base guarded in _etr_construction
    (ETR_MIN_PROFIT_BASE_USD) — fall back to the partner's mean measured rate
    across years, then to the statutory CIT. This keeps the script-5 haven test
    and revenue legs (which both key off etr_average_excl_resource) from ever
    seeing a NaN rate: an undefined effective rate is treated as "taxed at the
    statutory rate" (so a thin-profit jurisdiction with CIT>15% reads as a
    non-haven), not as a zero-tax haven. The pair ETR is a diagnostic and is left
    untouched (NaN on distributed rows by design)."""
    if "cit" not in df.columns:
        return df
    cit = pd.to_numeric(df["cit"], errors="coerce")
    for col in ETR_COLS_PARTNER:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        partner_mean = s.groupby(df["iso_partner"]).transform("mean")
        df[col] = s.fillna(partner_mean).fillna(cit).clip(lower=0, upper=1)
    return df


# %% [markdown] MARK: 3. Shared Orbis ownership shares
# 2. Shared: Orbis ownership shares — the per-(source, HQ, commodity, year)
#    ownership table with a global fallback — the minimum-royalty floor's
#    ownership base, also consumed by the exploratory resource factor.

# %%
def _build_bilateral_hq_table_with_fallback(rent_keys):
    """Build a combined Orbis HQ-share table keyed on
    `(source_iso3, year, hq_iso3, commodity)`.

    - **Bilateral layer**: rows from `hq_shares_by_source_commodity_yearly.csv`,
      i.e. per `(source, hq, commodity, year)`. These come from Orbis with the
      builder's small-market fallback (<3 entities OR <$10M aggregate ⇒ row
      uses global per-(hq, commodity) split, but is still attributed to that
      source).
    - **Zero-Orbis-presence fallback**: for `(source, commodity, year)` keys
      that are in `rent_keys` (i.e. have rent>0) but completely absent from the
      bilateral table — typically major producers where Orbis under-represents
      foreign IOCs (Iraq, Angola, Libya, Venezuela, …) — we append fallback
      rows using the global per-(hq, commodity, year) split, renormalised to
      sum to 1 within (year, commodity), applied to that source.

    `rent_keys` is the set of `(source_iso3, year, commodity)` triples for
    which we want a defined HQ split.
    """
    hq_bilateral = pd.read_csv(HQ_SHARES_BY_SOURCE)
    hq_bilateral = hq_bilateral[hq_bilateral["commodity"].isin(CATEGORIES)].copy()
    hq_bilateral["share"] = pd.to_numeric(hq_bilateral["share"], errors="coerce").fillna(0.0)
    hq_bilateral = hq_bilateral[["source_iso3", "hq_iso3", "commodity", "year", "share"]].rename(
        columns={"share": "hq_share"}
    )

    present = hq_bilateral[["source_iso3", "year", "commodity"]].drop_duplicates()
    missing = (
        rent_keys.drop_duplicates()
        .merge(present, on=["source_iso3", "year", "commodity"], how="left", indicator=True)
    )
    missing = missing[missing["_merge"] == "left_only"][["source_iso3", "year", "commodity"]]

    hq_global = pd.read_csv(HQ_SHARES)
    hq_global = hq_global[hq_global["commodity"].isin(CATEGORIES)].copy()
    hq_global["share"] = pd.to_numeric(hq_global["share"], errors="coerce").fillna(0.0)
    denom = hq_global.groupby(["year", "commodity"])["share"].transform("sum").replace(0, 1)
    hq_global["share"] = hq_global["share"] / denom
    hq_global = hq_global[["year", "hq_iso3", "commodity", "share"]].rename(
        columns={"share": "hq_share"}
    )

    fallback = missing.merge(hq_global, on=["year", "commodity"], how="inner")
    fallback = fallback[["source_iso3", "hq_iso3", "commodity", "year", "hq_share"]]
    return pd.concat([hq_bilateral, fallback], ignore_index=True)


# %% [markdown] MARK: 4. Exploratory resource factor
# 3. Exploratory: the resource factor (no paper scenario — kept for
#    experimentation; ships on incl_resource and the disaggregated baseline)

# %%
def _compute_resource_factor():
    """Compute the EXPLORATORY `resource_factor_usd` per (iso_parent, iso_partner, year).

    Kept for experimentation only — no paper scenario uses it (the former
    5-factor formula route was removed); the column ships on the incl_resource
    reference file and the disaggregated baseline for playing with
    resource-weighted apportionment designs.

    Definition (bilateral):
      resource_factor[parent=HQ_C, partner=SRC_S, year=Y]
          = Σ_<commodity c> gross_revenue[S, c, Y] × hq_share[S, C, c, Y]

    where gross_revenue is derived from WB/EITI/BGS rents divided by a per-(iso,
    category) rent fraction (same source as the flexible-royalty `flex_min`
    calculation), and `hq_share[S, C, c, Y]` is the Orbis-derived share of
    *country S's* commodity-c extractive activity owned by parents in country C
    (from `hq_shares_by_source_commodity_yearly.csv` — Orbis subsidiary-in-S
    grouped by GUO-in-C). The small-market fallback inside that builder falls
    back to the global `hq_shares_by_commodity_yearly.csv` for (source,
    commodity, year) cells that have <3 distinct entities or <$10M aggregate
    revenue, so non-Orbis-covered country-commodity pairs still get a sensible
    HQ split.

    Bilateral specificity: the factor uses the source-specific
    per-(hq, commodity, year) share rather than the *global* one (which would
    be the same number for every source country with that commodity). The
    source-specific share means e.g. Exxon (US parent) operating in Angola
    picks up a US share of Angolan oil derived from US firms' actual Angolan
    presence, not US's overall ~25% global oil HQ share. The factor is still uniform across all
    parents from a given HQ country in a given (source, commodity, year) cell
    — distinguishing extractive vs non-extractive parents within the same HQ
    jurisdiction would need parent-specific NACE weighting from Orbis, a
    separate refinement.
    """
    rents = pd.read_csv(RENTS)
    rents = rents[rents["category"].isin(CATEGORIES)].copy()
    rents["rent_usd"] = pd.to_numeric(
        rents["rent_best_usd"], errors="coerce"
    ).fillna(0.0)

    rf = pd.read_csv(RENT_FRAC)
    rf_map = {
        (r["iso3"], r["category"]): float(r["rent_fraction"])
        for _, r in rf.iterrows()
        if pd.notna(r["rent_fraction"]) and float(r["rent_fraction"]) > 0
    }

    def _rf_for(iso3, cat):
        return rf_map.get((iso3, cat), RENT_FRAC_DEFAULT[cat])

    rents["rent_fraction"] = [
        _rf_for(i, c) for i, c in zip(rents["iso3"], rents["category"])
    ]
    rents["gross_revenue_usd"] = np.where(
        rents["rent_fraction"] > 0,
        rents["rent_usd"] / rents["rent_fraction"],
        0.0,
    )
    rents = rents.rename(columns={"iso3": "source_iso3", "category": "commodity"})
    rents = rents[["source_iso3", "year", "commodity", "gross_revenue_usd"]]

    hq = _build_bilateral_hq_table_with_fallback(
        rent_keys=rents[["source_iso3", "year", "commodity"]].drop_duplicates()
    )

    # Bilateral merge on (source, commodity, year) — each rents row expands to (source, hq, commodity, year).
    merged = rents.merge(hq, on=["source_iso3", "year", "commodity"], how="inner")
    merged["resource_factor_usd"] = merged["gross_revenue_usd"] * merged["hq_share"]

    # Aggregate over commodities → (hq, source, year)
    out = (
        merged.groupby(["hq_iso3", "source_iso3", "year"], as_index=False)[
            "resource_factor_usd"
        ].sum()
    )
    out = out.rename(columns={"hq_iso3": "iso_parent", "source_iso3": "iso_partner"})
    return out


# %% [markdown] MARK: 5. Output writer
# 4. Output writer

# %%

def _write_dataset(df, columns, out_path, label):
    out_cols = [c for c in columns if c in df.columns]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise RuntimeError(f"{label}: missing columns {missing}")
    df[out_cols].to_csv(out_path, index=False)
    print(f"Wrote {out_path}  ({len(df):,} rows, {len(out_cols)} columns)")


# %% [markdown] MARK: 6. Minimum royalty (IGF-ATAF floor)
# 5. Output (3) — minimum royalty, IGF-ATAF floor
#    (cbcr_main_excl_resource_floored.csv + _allrows.csv)

# %%
# Everything below this line belongs to the minimum-royalty files (3a/3b) only:
# the flexible-royalty schedules, the floor-input builder, and the two
# floored-column writers. The floor is applied LAST in main(), mirroring the
# header numbering (the floor sits on top of the completed resources-excluded data).

# IGF-ATAF flexible-royalty schedules (clean round bounds; Cat 1 env-overridable).
# Cat 1 (headline): a price-linked royalty rate on gross production value that
# rises linearly with the commodity price, from CAT1_FLOOR at the commodity's
# historical price minimum to CAT1_CAP at its historical maximum
# (HIST_PRICE_MIN/MAX below; interpolation in `_linear_rate`).
CAT1_FLOOR = float(os.environ.get("CAT1_FLOOR", "0.01"))   # 1% of gross revenue, at the price minimum
CAT1_CAP = float(os.environ.get("CAT1_CAP", "0.10"))       # 10% of gross revenue, at the price maximum
CAT2_FLOOR, CAT2_CAP = 0.01, 0.10   # margin-linked rate, on gross revenue
CAT3_FLOOR, CAT3_CAP = 0.01, 0.12   # margin-linked rate, on rent
MARGIN_AT_CAP = 0.60                # IGF/IISD calibration: margins above 50% rare


PRIMARY_CATEGORY = "cat1"
FLEX_VARIANTS = ("cat1", "cat2", "cat3")

def _linear_rate(value, v_min, v_max, r_floor, r_cap):
    """Linear ramp from r_floor at v_min to r_cap at v_max, clipped outside."""
    if v_max == v_min:
        return np.full_like(np.asarray(value, dtype=float), r_floor, dtype=float)
    m = (np.asarray(value, dtype=float) - v_min) / (v_max - v_min)
    m = np.clip(m, 0.0, 1.0)
    return r_floor + (r_cap - r_floor) * m


def _resolve_rate_by_year(rate, years, col):
    """Expand the per-commodity rate table to (source_iso3, commodity, year).

    Rows with a blank year_start/year_end are the sample-agnostic default and
    apply to every year; rows with a range apply only within [year_start,
    year_end] and WIN over the agnostic row for those years. Returns a frame
    keyed on (source_iso3, commodity, year) carrying `col`, so a downstream
    merge on that triple is one-to-one."""
    yrs = sorted(pd.to_numeric(pd.Series(years), errors="coerce").dropna().astype(int).unique())
    has_ys = (rate["year_start"].notna() if "year_start" in rate.columns
              else pd.Series(False, index=rate.index))
    ag = rate.loc[~has_ys, ["source_iso3", "commodity", col]]
    exp = (ag.assign(_k=1).merge(pd.DataFrame({"year": yrs, "_k": 1}), on="_k")
           .drop(columns="_k"))
    exp["_yspec"] = False
    if has_ys.any():
        ys = rate.loc[has_ys].copy()
        ys["year_start"] = pd.to_numeric(ys["year_start"], errors="coerce")
        ys["year_end"] = pd.to_numeric(ys["year_end"], errors="coerce")
        parts = [{"source_iso3": rr["source_iso3"], "commodity": rr["commodity"],
                  col: rr[col], "year": y, "_yspec": True}
                 for _, rr in ys.iterrows() for y in yrs
                 if rr["year_start"] <= y <= rr["year_end"]]
        if parts:
            exp = pd.concat([exp, pd.DataFrame(parts)], ignore_index=True)
    return (exp.sort_values("_yspec")
            .drop_duplicates(["source_iso3", "commodity", "year"], keep="last")
            .drop(columns="_yspec"))


def _build_flex_inputs(cbcr, pay):
    """Build per (source, commodity, year) rent / gross_revenue / price / rates
    plus per (source, year) margin and per (hq, commodity, year) HQ share. Returns
    a `pay`-shaped frame with all flex inputs merged on."""
    rents = pd.read_csv(RENTS)
    rents = rents[rents["category"].isin(CATEGORIES)].copy()
    rents["rent_usd"] = pd.to_numeric(rents["rent_best_usd"], errors="coerce").fillna(0.0)

    # Guard against egregious EITI rent leaks (local-currency / in-kind-volume
    # values that escaped the cleaning step's power-of-10 check). Sierra Leone
    # 2020/2021 are the known case: EITI-sourced minerals rent of $18–21bn vs a
    # BGS figure of ~$0.1bn (Leones ≈ 1e4/USD → ~100–250× inflation). Where the
    # EITI-sourced best rent exceeds 20× a positive BGS alternative, fall back to
    # the BGS rent. 20× is conservative — legitimate EITI>BGS gaps are far smaller.
    if {"rent_best_source", "rent_bgs_usd"}.issubset(rents.columns):
        bgs = pd.to_numeric(rents["rent_bgs_usd"], errors="coerce")
        leak = (
            rents["rent_best_source"].astype(str).eq("EITI")
            & (bgs > 0)
            & (rents["rent_usd"] > 20.0 * bgs)
        )
        if leak.any():
            print(f"  [SLE-type guard] capped {int(leak.sum())} EITI rent-leak cell(s) to BGS: "
                  + ", ".join(f"{r.iso3}/{int(r.year)}/{r.category}" for _, r in rents[leak].iterrows()))
            rents.loc[leak, "rent_usd"] = bgs[leak].values

    rf = pd.read_csv(RENT_FRAC)
    rf_map = {(r["iso3"], r["category"]): float(r["rent_fraction"])
              for _, r in rf.iterrows()
              if pd.notna(r["rent_fraction"]) and float(r["rent_fraction"]) > 0}

    def _rf_for(iso3, cat):
        return rf_map.get((iso3, cat), RENT_FRAC_DEFAULT[cat])

    rents["rent_fraction"] = [_rf_for(i, c) for i, c in zip(rents["iso3"], rents["category"])]
    rents["price"] = [_yearly_lookup(CAT_REF_PRICES[c], y)
                      for c, y in zip(rents["category"], rents["year"])]
    rents["gross_revenue_usd"] = np.where(
        rents["rent_fraction"] > 0,
        rents["rent_usd"] / rents["rent_fraction"],
        0.0,
    )
    rents["cat1_rate"] = 0.0
    for cat in CATEGORIES:
        m = rents["category"].eq(cat)
        if m.any():
            rents.loc[m, "cat1_rate"] = _linear_rate(
                rents.loc[m, "price"].values,
                HIST_PRICE_MIN[cat], HIST_PRICE_MAX[cat],
                CAT1_FLOOR, CAT1_CAP,
            )
    rents = rents.rename(columns={"iso3": "source_iso3", "category": "commodity"})
    # Genuine countries only: the WB-rents-derived table carries aggregate rows
    # (WLD, IBT, LMY, ...). With the outer payments/ownership merge below these
    # would manufacture phantom floor rows for non-countries - keep only codes
    # that exist as CbCR partners or payment sources.
    _real = set(cbcr["iso_partner"].astype(str)) | set(pay["source_iso3"].astype(str))
    rents = rents[rents["source_iso3"].isin(_real)]
    rents = rents[["source_iso3", "year", "commodity",
                   "rent_usd", "gross_revenue_usd", "price", "cat1_rate"]]

    cb = cbcr[["iso_partner", "year", PCOL, "unrelated_party_revenues"]].copy()
    cb[PCOL] = pd.to_numeric(cb[PCOL], errors="coerce").fillna(0.0)
    cb["unrelated_party_revenues"] = pd.to_numeric(
        cb["unrelated_party_revenues"], errors="coerce").fillna(0.0)
    g = cb.groupby(["iso_partner", "year"], as_index=False).agg(
        _profit=(PCOL, "sum"), _rev=("unrelated_party_revenues", "sum"))
    g["margin"] = g["_profit"] / g["_rev"].where(g["_rev"] > 1.0, 1.0)
    g["margin"] = g["margin"].clip(upper=1.0)
    margin = g.rename(columns={"iso_partner": "source_iso3"})[["source_iso3", "year", "margin"]]

    # Bilateral HQ share + zero-Orbis-presence global-share fallback (same
    # logic as `_compute_resource_factor`). Each (source, commodity, year)
    # cell that exists in the bilateral table uses its source-specific HQ
    # split; cells missing from the bilateral file (e.g. Iraq oil, Angola
    # oil — countries where Orbis under-represents foreign IOCs) fall back
    # to the global per-(hq, commodity, year) split, renormalised to sum
    # to 1 within (year, commodity).
    hq = _build_bilateral_hq_table_with_fallback(
        rent_keys=rents[["source_iso3", "year", "commodity"]].drop_duplicates()
    )

    # UNION of payment rows and ownership-share rows: the floor
    # base is rate x gross x hq_share, so it must cover the FULL ownership-share
    # table, not just the HQs that happen to have payment rows. Restricting to
    # payment rows would silently drop every owner without recorded payments -
    # the very under-payers a minimum royalty exists to catch - and would make
    # the floor shrink whenever the payments panel gets more concentrated
    # (Guinea's floor would collapse from ~150 to ~6 $m/yr through exactly this).
    # An owner with production share but no payments gets capture 0 and its
    # full floor share; a payer absent from the Orbis share table keeps its
    # capture (offsetting the aggregate) with no floor of its own.
    flex = pay.merge(hq, on=["source_iso3", "year", "hq_iso3", "commodity"], how="outer")
    flex = flex.merge(rents, on=["source_iso3", "year", "commodity"], how="left")
    flex = flex.merge(margin, on=["source_iso3", "year"], how="left")
    for c in ("rent_usd", "gross_revenue_usd", "price", "cat1_rate", "margin", "hq_share",
              "pre_profit", "post_profit_payments_usd", "equity_income_usd"):
        if c in flex.columns:
            flex[c] = flex[c].fillna(0.0)
    flex["cat2_rate"] = _linear_rate(flex["margin"].values, 0.0, MARGIN_AT_CAP, CAT2_FLOOR, CAT2_CAP)
    flex["cat3_rate"] = _linear_rate(flex["margin"].values, 0.0, MARGIN_AT_CAP, CAT3_FLOOR, CAT3_CAP)
    return flex



def _reallocate_floor_to_reported(df, lost_floor=None):
    """Return a COPY of df with each source's total floor add-on re-allocated
    onto its DIRECTLY-REPORTED rows (is_distributed==0), per (iso_partner, year).
    Cells whose (iso_partner, year) has no reported row keep the original
    (all-rows) allocation. This makes the reported-only UT sample carry the full
    minimum-royalty deduction (so the pool deduction and the royalty stream live
    in one universe) — at the cost of loading a source's whole floor onto
    whichever parents report it directly.

    Weighting is RESOURCE-TARGETED: the floor is a resource royalty, so it is
    spread across the source's reported cells in proportion to each cell's
    `resource_profit_base_usd` (the resource profit stripped in the §2.1.1
    correction), NOT its total (all-sector) revenue — otherwise a resource
    royalty would land on the reporters' non-resource activity. Where a source's
    reported cells carry no resource base in a year (the resource profit was
    stripped only to non-reported / imputed cells), we fall back to
    total-revenue weighting, and finally to an equal split.

    `lost_floor`: per-(iso_partner, year) floor
    add-on whose owner has NO CbCR line anywhere in the panel (owners in
    non-reporting jurisdictions — Mongolia's domestic miners, Bahamas/BVI
    holding vehicles, Russian owners — see the unmatched-floor diagnostic).
    The floor binds country-wide and its royalty stream accrues to the SOURCE
    country, so in this re-allocated file those amounts join the country pool
    spread over the reporting rows. The all-rows file keeps per-line semantics
    and lets them drop."""
    df = df.copy()
    if "is_distributed" not in df.columns:
        return df
    rep = (df["is_distributed"] == 0).to_numpy()
    keys = [df["iso_partner"], df["year"]]
    n_rep = pd.Series(rep.astype(float), index=df.index).groupby(keys).transform("sum")
    # resource-base weight (primary), total-revenue weight (fallback), equal (last)
    res = (pd.to_numeric(df.get("resource_profit_base_usd", 0.0), errors="coerce")
           .fillna(0.0).abs())
    rev = pd.to_numeric(df["total_revenues"], errors="coerce").fillna(0.0).abs()
    res_rep = pd.Series(np.where(rep, res, 0.0), index=df.index)
    rev_rep = pd.Series(np.where(rep, rev, 0.0), index=df.index)
    res_rep_sum = res_rep.groupby(keys).transform("sum")
    rev_rep_sum = rev_rep.groupby(keys).transform("sum")
    w = np.where(
        res_rep_sum > 0, res_rep / res_rep_sum.replace(0, np.nan),
        np.where(rev_rep_sum > 0, rev_rep / rev_rep_sum.replace(0, np.nan),
                 np.where(rep, 1.0 / n_rep.replace(0, np.nan), 0.0)),
    )
    w = pd.Series(w, index=df.index).fillna(0.0)
    has_rep = (n_rep > 0).to_numpy()
    for v in FLEX_VARIANTS:
        col = f"floor_add_on_{v}_usd"
        tot = df.groupby(keys)[col].transform("sum")
        if lost_floor is not None and col in lost_floor.columns:
            _lm = lost_floor[col]
            _extra = pd.Series(
                pd.MultiIndex.from_arrays([df["iso_partner"], df["year"]]).map(_lm),
                index=df.index,
            ).fillna(0.0)
            tot = tot + _extra
        df[col] = np.where(has_rep, tot * w, df[col])
    return df


def _compute_floored_cols(df):
    """Given floor_add_on_{v}_usd on df, build the floored profit columns
    (profit_loss_excl_resource − floor_add_on), the tax line (unchanged =
    excl_resource tax), the cat-1 aliases, and the per-(parent, year) floored
    profit totals. Mutates and returns df. Depends on the floor_add_on
    allocation, so it is called once per output file (all-rows vs reported)."""
    for v in FLEX_VARIANTS:
        df[f"profit_loss_excl_resource_floored_{v}"] = (
            df["profit_loss_excl_resource"] - df[f"floor_add_on_{v}_usd"]
        )
        df[f"income_tax_paid_on_cash_basis_excl_resource_floored_{v}"] = (
            df["income_tax_paid_on_cash_basis_excl_resource"]
        )
    df["profit_loss_excl_resource_floored"] = (
        df[f"profit_loss_excl_resource_floored_{PRIMARY_CATEGORY}"]
    )
    df["income_tax_paid_on_cash_basis_excl_resource_floored"] = (
        df[f"income_tax_paid_on_cash_basis_excl_resource_floored_{PRIMARY_CATEGORY}"]
    )
    grp = df.groupby(["iso_parent", "year"])
    for v in FLEX_VARIANTS:
        df[f"total_profit_loss_excl_resource_floored_{v}"] = (
            grp[f"profit_loss_excl_resource_floored_{v}"].transform("sum")
        )
    df["total_profit_loss_excl_resource_floored"] = (
        df[f"total_profit_loss_excl_resource_floored_{PRIMARY_CATEGORY}"]
    )
    return df



# %% [markdown] MARK: 7. main
# 6. main — run (1) -> (2) -> (3) and write the four files

# %%
def main():
    cbcr = pd.read_csv(CBCR, low_memory=False, float_precision="round_trip")
    # round_trip: the stitch-back at the end rewrites this file, and the default
    # parser can shift floats by one last-bit per read/write cycle - round_trip
    # keeps repeated runs byte-stable.
    # Idempotency: this script stitches `etr_average_excl_resource` back onto
    # the disaggregated file at the end, so on a re-run it is already present
    # (plus the exploratory `resource_factor_usd`). Drop both
    # here so they don't pollute base_cols or collide (x/y suffixes) below.
    cbcr = cbcr.drop(columns=["resource_factor_usd", "etr_average_excl_resource"], errors="ignore")
    pay = pd.read_csv(PAY, comment="#")
    rate = pd.read_csv(RATE, comment="#")
    rate = rate[rate["source_iso3"].str.len() == 3]   # drop non-country placeholders

    # Consolidated control table (single source of truth). It decides which
    # countries are genuine resource economies (include), the curated resource
    # profit-tax rate r, and whether the country is covered by EITI. Excluded
    # (non-resource) countries get NO resource correction; the ETR-gap fires only
    # for included, non-EITI countries that carry a curated rate (see below).
    params = pd.read_csv(PARAMS)
    included_iso = set(params.loc[params["include"].astype(str).str.lower() == "yes", "iso3"])
    eiti_iso = set(params.loc[params["eiti"].astype(str).str.lower().isin(["true", "yes", "1"]), "iso3"])
    r_curated = pd.to_numeric(params.set_index("iso3")["resource_rate"], errors="coerce").dropna()

    # Source-aware trust: a (source, year) cell is "trusted" — the correction is left
    # to the actual payment data and the ETR-gap strip is OFF — ONLY where its payment
    # `data_source` for that year is genuine EITI or hand-curated manual. A
    # country-level EITI flag alone would wrongly shield EITI-flagged countries
    # that actually fall back to GRD/rent-proxy IN the analysis window. Norway is the
    # marquee case: flagged EITI, but 2016-2022 is entirely `grd_distributed` (its EITI
    # panel covers only 2010-2015 & 2023), so its high residual non-resource ETR must be
    # corrected via the gap strip. Saudi Arabia: its manual 0.20 Aramco-CIT rate
    # demonstrably under-removes the resource tax, so SAU cells are treated as
    # un-trusted and corrected at the researched 0.45 effective rate
    # (resource_country_parameters.csv).
    _ptrust = pay["data_source"].astype(str).str.contains("eiti|manual", case=False, na=False)
    trusted_year = {
        (str(i), int(y))
        for i, y in pay.loc[_ptrust, ["source_iso3", "year"]].dropna().to_numpy()
    }
    trusted_year -= {("SAU", y) for y in range(2016, 2023)}
    # United Arab Emirates: the payments panel
    # observes only OMV and TotalEnergies among the foreign concession
    # partners — BP, CNPC, INPEX, ENI and the Indian consortium publish no
    # payment reports, yet their emirate concession income tax IS in the CbCR
    # tax line (residual non-resource ETRs up to 0.44 in a ~0-statutory
    # environment). Un-trust ARE so the ETR-gap strips that tax from the CbCR
    # line itself at the curated r = 0.65 (emirate decrees: 55% base, bands
    # to 85%; petroleum exempt from the 9% federal CIT per IMF CR24 Annex VII).
    trusted_year -= {("ARE", y) for y in range(2016, 2023)}

    # Resource-DOMINATED economies — the target set for the generalized residual-ETR
    # floor (applied to every economy whose above-CIT residual ETR is genuinely
    # unremoved resource tax). A country qualifies if its extractive rents
    # are >= 5% of GDP (structural resource-dependence) OR (computed in the correction
    # from the resource share of its own CbCR profit) >= 30%. Diversified economies
    # (UK, Mexico, India, Turkey, Poland, South Africa, Ethiopia, Kenya, …) are
    # EXCLUDED so their above-CIT ETR — which reflects withholding/minimum taxes, not
    # resources — is NOT misattributed to resources and stripped. Tax havens are
    # excluded (their ETR is handled by list-based haven identification) — using the
    # FROZEN functional set, NOT the (presentational) representation list: Saudi
    # Arabia is on the representation list but, as a resource-dominated economy,
    # must keep this floor. See docs/extractive/resource_correction_etr_floor.md.
    _rents = pd.to_numeric(params.set_index("iso3")["extractive_rents_pct_gdp"], errors="coerce")
    dominated_rents_iso = set(_rents[_rents >= 5.0].index)
    haven_iso = set(TAX_HAVENS_FUNCTIONAL)

    # Year-aware rate resolution: rows carrying year_start/year_end apply only
    # within [year_start, year_end] (e.g. USA 2016-2017 pre-TCJA 35%, GBR 2022
    # Energy Profits Levy); rows with a blank range are the sample-agnostic
    # default. Expand to (source, commodity, year) for the years present, the
    # year-specific value winning, then merge on the triple so no pay row is
    # duplicated by a country having both an agnostic and a year-specific rate.
    pay = pay.merge(
        _resolve_rate_by_year(rate, pay["year"], "effective_resource_profit_tax_rate"),
        on=["source_iso3", "commodity", "year"], how="left",
    )
    stat_cit = (
        cbcr[["iso_partner", "year", "cit"]].drop_duplicates()
        .rename(columns={"iso_partner": "source_iso3", "cit": "statutory_cit"})
    )
    pay = pay.merge(stat_cit, on=["source_iso3", "year"], how="left")
    pay["rate"] = (
        pay["effective_resource_profit_tax_rate"].fillna(pay["statutory_cit"])
        .fillna(0.30).clip(lower=RATE_MIN, upper=RATE_MAX)
    )

    # Per-partner resource rate r for the ETR-gap correction below: the rate at
    # which resource profit is taxed, used to convert excess-over-statutory CbCR
    # tax into a resource profit base. The gap operates on the CbCR INCOME-TAX
    # line, so r must be the income-tax-based resource profit-tax rate — i.e. the
    # per-commodity `resource_profit_tax_rate.csv` (CIT + profit-based special
    # taxes). We prefer that; the broader `combined_effective_rate` (which can
    # fold in royalty/equity take that is NOT in the CbCR income-tax line) is only
    # a fallback where no per-commodity rate exists; then the 0.30 default.
    ecr = pd.read_csv(ECR, comment="#")
    ecr = ecr[ecr["iso3"].astype(str).str.len() == 3]
    r_combined = ecr.set_index("iso3")["combined_effective_rate"]
    r_bycomm = rate.groupby("source_iso3")["effective_resource_profit_tax_rate"].max()
    r_idx = sorted(set(r_combined.index) | set(r_bycomm.index) | set(r_curated.index))
    r_partner_tbl = pd.DataFrame({"iso_partner": r_idx})
    # The consolidated table's curated rate is authoritative (it folds in the
    # web-researched per-country rates); fall back to the per-commodity income-tax
    # rate, then the combined effective rate.
    r_partner_tbl["resource_rate_partner"] = (
        r_partner_tbl["iso_partner"].map(r_curated)
        .fillna(r_partner_tbl["iso_partner"].map(r_bycomm))
        .fillna(r_partner_tbl["iso_partner"].map(r_combined))
    )

    post = pay["post_profit_payments_usd"].fillna(0.0)
    equity = pay["equity_income_usd"].fillna(0.0)
    # Negative post-profit (net tax refund) is floored to a ZERO resource base
    # (author decision 2026-07-26): a refund must not be back-divided by the rate
    # into an imputed resource LOSS that then adds profit back to the non-resource
    # base. That former negative-relief path only ever fired for MEX (Pemex refund
    # years), inflating Mexico's non-resource UT base by +$20.75bn (a $4.97bn refund
    # ÷ 0.24). Positive post keeps max(post/rate, equity) as before.
    pay["resource_profit_base"] = np.where(
        post < 0, 0.0, np.maximum(post / pay["rate"], equity)
    )

    # Tax-side counterpart of resource_profit_base, kept symmetric with the
    # profit-side branch that won:
    #   - post-branch wins  → deduct `post` from cash tax. Tautologically,
    #     `post = (post / rate) × rate` so this equals base × rate.
    #   - equity-branch wins → deduct `equity × rate` from cash tax. This
    #     treats equity_income as if it were a profit base of size equity
    #     and removes the CIT that *would* be due on it at the project rate.
    #     Without this symmetry the ETR on the excl_resource pair would be
    #     biased: we'd be subtracting the equity slice from profit but not
    #     subtracting the corresponding CIT on it from the tax line.
    #   - negative-post case: floored to a ZERO deduction (2026-07-26), symmetric
    #     with the zero profit base above — a net refund strips nothing rather than
    #     adding tax back. (Retires the former UK-decommissioning relief, which in
    #     practice only ever fired for MEX.)
    equity_binds = (post >= 0) & (equity > post / pay["rate"])
    pay["resource_tax_deduction"] = np.where(
        equity_binds, equity * pay["rate"], np.maximum(post, 0.0)
    )

    pay["pre_profit"] = pay["pre_profit_payments_usd"].fillna(0.0)


    # ---- (1) Resources excluded ----------------------------------------
    # Aggregate the payment-level corrections to (parent, partner, year),
    # allocate them onto the CbCR cells, then run the per-cell decomposition.
    agg = (
        pay.groupby(["hq_iso3", "source_iso3", "year"], as_index=False)
        .agg(
            pre_profit_payments_usd=("pre_profit", "sum"),
            post_profit_payments_usd=("post_profit_payments_usd", "sum"),
            equity_income_usd=("equity_income_usd", "sum"),
            resource_profit_base_usd=("resource_profit_base", "sum"),
            resource_tax_deduction_usd=("resource_tax_deduction", "sum"),
        )
        .rename(columns={"hq_iso3": "iso_parent", "source_iso3": "iso_partner"})
    )
    for c in agg.columns:
        if c.endswith("_usd"):
            agg[c] = pd.to_numeric(agg[c], errors="coerce").fillna(0.0)

    payment_cols = [
        "pre_profit_payments_usd", "post_profit_payments_usd",
        "equity_income_usd", "resource_profit_base_usd",
        "resource_tax_deduction_usd",
    ]

    # ── Diagnostic: corrections whose (parent, partner, year) cell has
    # no CbCR line are silently lost in the left merge below. Make that loss
    # visible: write the unmatched cells + $ volume so mis-attributed HQ shares
    # (payments assigned to HQs with no line in the source country) are auditable.
    _cells = cbcr[["iso_parent", "iso_partner", "year"]].drop_duplicates()
    _chk = agg.merge(_cells, on=["iso_parent", "iso_partner", "year"], how="left", indicator=True)
    _unm = _chk[_chk["_merge"] == "left_only"].drop(columns="_merge")
    _diag_path = f"{data_intermediate_extractive}resource_correction_unmatched_cells.csv"
    _bkt = ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd"]
    if len(_unm):
        _tot = _unm[_bkt].sum().sum()
        _dom = _unm[_unm.iso_parent == _unm.iso_partner][_bkt].sum().sum()
        print(f"  [diag] {len(_unm):,} correction cells have NO CbCR line and are dropped: "
              f"${_tot/1e9:,.1f}B total (${_dom/1e9:,.1f}B domestic non-reporter, "
              f"${(_tot-_dom)/1e9:,.1f}B foreign) → {_diag_path}")
        _unm.sort_values(_bkt[0], ascending=False).to_csv(_diag_path, index=False)
    else:
        print("  [diag] every correction cell matched a CbCR line")

    df = _allocate_payments_to_cbcr_cells(cbcr, agg, payment_cols)

    # Drop the reported-profit ETR columns from the resource-corrected outputs.
    # The disaggregated file keeps them; the resource-corrected files get the
    # non-resource family computed below.
    df = df.drop(columns=[c for c in ETR_COLS_TO_DROP if c in df.columns])
    df = df.merge(r_partner_tbl, on="iso_partner", how="left")

    P = pd.to_numeric(df[PCOL], errors="coerce").fillna(0.0)
    T = pd.to_numeric(df[TCOL], errors="coerce").fillna(0.0)

    # ── Resource decomposition: ETR-gap unified with the external estimate ──
    # The non-resource portion of a cell is taxed at the statutory CIT `c`; any
    # tax *in excess* of that (observed ETR > c) must come from resource activity
    # taxed at the higher resource rate `r`. So:
    #     resource_profit = (T − c·P) / (r − c),   resource_tax = r · resource_profit
    # hard-capped at the cell's reported profit/tax. For zero-CIT jurisdictions
    # (UAE, Bahrain) the gap = ALL reported tax, correctly stripping the foreign-
    # oil-major petroleum tax that the external + domestic_share path mis-places
    # onto the ~0-tax domestic cell.
    #
    # Both legs are hard-capped: a profit-only cap that scaled the tax deduction
    # by the profit-cap ratio would NEVER cap tax at reported tax → negative
    # residual non-resource tax for heavily-taxed resource cells (36 countries in
    # the audit). Where the gap is inert (observed ETR ≤ statutory CIT — typical for
    # high-CIT cells with exempt/loss-netted profit) we fall back to the external
    # estimate, hard-capped per cell. Negative-post relief (e.g. UK
    # decommissioning) is preserved so excl_tax can exceed reported there.
    c = pd.to_numeric(df["cit"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=0.60)
    r = pd.to_numeric(df["resource_rate_partner"], errors="coerce").fillna(0.30).clip(RATE_MIN, RATE_MAX)

    # Eligibility for the ETR-gap strip, from the consolidated control table:
    #   • included_cell  — a genuine resource economy (include=yes). Excluded
    #     (non-resource) countries get NO correction at all (see below). This
    #     prevents false positives — without the gate, Ireland, France, Belgium,
    #     Singapore, … would be pulled in by trivial WB rent-proxy panel rows and
    #     stripped of huge spurious amounts.
    #   • not EITI — the EITI panel is authoritative & comprehensive for EITI
    #     countries, so the gap is OFF for them; resource is removed only on the
    #     EITI (source, HQ) pairs that carry a panel amount (via the external
    #     path below), zero elsewhere.
    #   • has a curated rate — only fire where we actually have a researched
    #     resource rate r to convert the tax gap into a resource profit base.
    # Elsewhere an above-statutory ETR is not necessarily resource-related (it can
    # reflect withholding, one-off settlements, etc.), so the gap must not fire.
    included_cell = df["iso_partner"].isin(included_iso)
    # Source-aware trust gate (per-year, not a country-level EITI flag): a cell is
    # trusted (gap OFF) only if its actual (iso_partner, year) payment source is
    # EITI/manual — see `trusted_year` above. So an EITI-flagged country on GRD data
    # in-window (Norway) is NOT trusted and DOES get the ETR-gap correction.
    _cellkey = list(zip(df["iso_partner"].astype(str), df["year"].astype("Int64").astype("int64")))
    trusted_cell = pd.Series([k in trusted_year for k in _cellkey], index=df.index) & included_cell
    # ARE hybrid: the gap premise — capture flows through the
    # income-tax line — holds for the FOREIGN concession partners (55-85%
    # emirate income tax) but NOT for ADNOC's domestic cell, whose capture is
    # royalties + dividends outside the tax line. So the domestic ARE cell
    # stays trusted (external route: max(post ÷ r, equity), with the
    # IMF-grounded equity fractions), while foreign ARE cells use the gap.
    trusted_cell |= ((df["iso_partner"] == "ARE") & (df["iso_parent"] == "ARE")
                     & included_cell)
    has_curated_rate = df["iso_partner"].isin(set(r_curated.index))
    gap_eligible = included_cell & (~trusted_cell) & has_curated_rate
    gap_active = gap_eligible & (r > c) & (T > c * P)
    with np.errstate(divide="ignore", invalid="ignore"):
        rp_gap_raw = np.where(gap_active, (T - c * P) / (r - c), 0.0)
    rp_gap = np.clip(rp_gap_raw, 0.0, np.where(P > 0, P, 0.0))
    # Tax stripped by the gap = ALL tax in excess of the statutory CIT that would
    # be due on the residual NON-resource profit (P − resource_profit). For a
    # fully-resource cell (rp_gap → P) this removes ALL the tax, so zero-CIT
    # producers (UAE, Bahrain) end with non-resource ETR ≈ 0 and stay havens
    # regardless of r. (Using `min(r·rp_gap, T)` instead would leave r·P of tax
    # behind on full-resource cells, lifting UAE's non-resource ETR to ~0.19.)
    # For partial cells the residual ETR equals the statutory rate c, as intended.
    rt_gap = np.where(gap_active, np.clip(T - c * (P - rp_gap), 0.0, T), 0.0)

    base_raw = df["resource_profit_base_usd"]
    tax_raw = df["resource_tax_deduction_usd"]
    neg_relief = (tax_raw < 0).to_numpy()

    # Inert resource cells (observed ETR ≤ statutory, so the gap finds no
    # differentially-taxed resource): we cannot reliably identify resource tax,
    # and the external tax estimate over-strips high-CIT countries (e.g. COD,
    # statutory 31.7%, reported foreign ETR already 10.9%), pushing them below
    # their own reported rate. So strip the external resource PROFIT base at the
    # cell's OWN reported ETR — this removes resource activity from the pool while
    # leaving the residual non-resource ETR equal to the reported ETR (no
    # artificial haven-isation of high-CIT economies).
    reported_etr = np.where(P > 0, T / P, 0.0)
    rp_ext = np.where(P > 0, np.minimum(base_raw, P), 0.0)
    rt_ext = np.clip(rp_ext * reported_etr, 0.0, T)

    use_gap = gap_active.to_numpy() & (rp_gap > 0)
    relief_use = neg_relief & (~use_gap)
    rp = np.where(use_gap, rp_gap, rp_ext)
    rt = np.where(use_gap, rt_gap, rt_ext)
    # Former negative-post relief — now INERT: `resource_tax_deduction` is floored
    # at 0 (2026-07-26), so `relief_use` is always False and these are no-ops. Kept
    # for structural clarity; a negative post strips nothing (see base construction).
    rp = np.where(relief_use, base_raw, rp)
    rt = np.where(relief_use, tax_raw, rt)

    # ---- Generalized residual-ETR floor for RESOURCE-DOMINATED economies --------
    # Applied to EVERY resource-dominated economy whose residual
    # non-resource ETR still exceeds statutory CIT after the paths above — i.e. the
    # payment data under-removed the resource tax (weak manual/EITI/GRD coverage or a
    # too-low assumed rate), leaving unremoved resource profit taxed above statutory.
    # We strip that residual excess-over-CIT tax and the matching resource profit in
    # lockstep at rate rr (>= CIT), so the residual non-resource ETR lands at the
    # statutory rate c. Gated to resource-dominated, non-haven cells so it does NOT
    # touch diversified economies (UK, Mexico, India…) whose above-CIT ETR is
    # withholding/minimum taxes, not resources. See
    # docs/extractive/resource_correction_etr_floor.md.
    resid_P = P - rp
    resid_T = T - rt
    _cshr = (pd.Series(rp, index=df.index).groupby(df["iso_partner"]).transform("sum")
             / pd.Series(P, index=df.index).groupby(df["iso_partner"]).transform("sum").replace(0, np.nan))
    country_res_share = _cshr.fillna(0.0).to_numpy()
    dominated = (
        included_cell.to_numpy()
        & (~df["iso_partner"].isin(haven_iso).to_numpy())
        & (df["iso_partner"].isin(dominated_rents_iso).to_numpy() | (country_res_share >= 0.30))
    )
    over_floor = dominated & (~neg_relief) & (resid_P > 0) & (resid_T > c * resid_P)
    rr_floor = np.maximum(r, c + 0.05)   # remove strictly above CIT so the strip converges
    with np.errstate(divide="ignore", invalid="ignore"):
        add_rp = np.where(over_floor, np.clip((resid_T - c * resid_P) / (rr_floor - c), 0.0, resid_P), 0.0)
    add_rt = np.where(over_floor, np.clip(resid_T - c * (resid_P - add_rp), 0.0, resid_T), 0.0)
    floored_cell = add_rp > 0
    rp = rp + add_rp
    rt = rt + add_rt
    if floored_cell.any():
        _fc = sorted(set(df.loc[pd.Series(floored_cell, index=df.index), "iso_partner"]))
        print(f"  [resource-dominated ETR floor] capped residual non-resource ETR at "
              f"statutory CIT on {int(floored_cell.sum()):,} cell(s) across "
              f"{len(_fc)} economies: {_fc}; extra profit stripped "
              f"${add_rp.sum()/1e9:.1f}B, extra tax ${add_rt.sum()/1e9:.1f}B.")

    # ---- Manual resource-rent correction for three under-corrected producers ----
    # A country-level investigation of every non-haven UT loser found three
    # producers whose loss is driven by resource profit the standard correction
    # UNDER-removes: Equatorial Guinea (GNQ), Papua New Guinea (PNG) and Malaysia
    # (MYS). For these the state take ÷ assumed statutory rate falls far short of
    # the actual resource economic profit (weak fiscal regime — a large slice of
    # oil/gas profit is company-retained and lightly taxed), so residual resource
    # profit stays in the pool and is reallocated away by the activity formula.
    # We floor their stripped base at the country's resource RENT (the layered
    # EITI > BGS > EIA > WB best estimate in rents_combined_yearly.csv), capped at
    # the cell's reported profit — equivalent to backing the resource profit out at
    # the country's ACTUAL effective rate (take ÷ rent) rather than the assumed
    # statutory rate. The cap means a diversified producer (Malaysia) loses only
    # its resource-rent share, not its manufacturing profit. The extra profit is
    # removed at the cell's reported ETR, so the residual non-resource ETR is
    # unchanged. This is a NAMED manual correction, not a general floor — it never
    # touches any other economy. See docs/extractive/resource_correction_etr_floor.md.
    RENTFLOOR_MANUAL_ISO = {"GNQ", "PNG", "MYS"}
    _rent = pd.read_csv(RENTS)
    _rent["_r"] = pd.to_numeric(_rent["rent_best_usd"], errors="coerce").fillna(0.0)
    _rent_sy = _rent.groupby(["iso3", "year"], as_index=False)["_r"].sum()
    _rent_map = {(str(i), int(y)): float(v) for i, y, v
                 in zip(_rent_sy["iso3"], _rent_sy["year"], _rent_sy["_r"])}
    rent_cell = np.array([_rent_map.get((str(i), int(y)), 0.0)
                          for i, y in zip(df["iso_partner"], df["year"])], dtype=float)
    _g = [df["iso_partner"], df["year"]]
    cur_rp_sy = pd.Series(rp, index=df.index).groupby(_g).transform("sum").to_numpy()
    P_pos = np.where(P > 0, P, 0.0)
    P_sy = pd.Series(P_pos, index=df.index).groupby(_g).transform("sum").to_numpy()
    # target stripped base per (source, year) = min(max(current, rent), booked profit)
    target_sy = np.minimum(np.maximum(cur_rp_sy, rent_cell), P_sy)
    gap_sy = np.maximum(target_sy - cur_rp_sy, 0.0)
    w_pos = np.where(P_sy > 0, P_pos / P_sy, 0.0)     # share the gap by positive profit
    rentfloor_gate = df["iso_partner"].isin(RENTFLOOR_MANUAL_ISO).to_numpy()
    add_rp_rent = np.where(rentfloor_gate, gap_sy * w_pos, 0.0)
    add_rp_rent = np.clip(add_rp_rent, 0.0, np.maximum(P_pos - rp, 0.0))   # never exceed remaining profit
    add_rt_rent = add_rp_rent * reported_etr                              # remove at reported ETR
    rentfloor_cell = add_rp_rent > 1.0
    rp = rp + add_rp_rent
    rt = rt + add_rt_rent
    if rentfloor_cell.any():
        _rf = sorted(set(df.loc[pd.Series(rentfloor_cell, index=df.index), "iso_partner"]))
        print(f"  [manual resource-rent correction] raised the stripped base to the resource "
              f"rent on {int(rentfloor_cell.sum()):,} cell(s) across {len(_rf)} named producers: "
              f"{_rf}; extra profit stripped ${add_rp_rent.sum()/1e9:.1f}B.")

    # Excluded (non-resource) countries: no resource correction at all — their
    # excl_resource profit/tax equal the reported baseline.
    excluded_cell = (~included_cell).to_numpy()
    rp = np.where(excluded_cell, 0.0, rp)
    rt = np.where(excluded_cell, 0.0, rt)
    df["resource_profit_base_usd"] = rp
    df["resource_tax_deduction_usd"] = rt
    df["resource_correction_method"] = np.where(
        excluded_cell, "excluded_non_resource",
        np.where(floored_cell & ~excluded_cell, "resource_dominated_etr_floor",
        np.where(use_gap, "etr_gap",
                 np.where(relief_use, "external_relief", "external_reported_etr"))),
    )

    # excl_resource: strip resource_profit_base from profit and the matching
    # resource_tax_deduction from cash tax. The deduction follows whichever
    # branch (post or equity) won on the profit side, so the ratio
    # `excl_tax / excl_profit` is symmetric in either case.
    df["profit_loss_excl_resource"] = P - df["resource_profit_base_usd"]
    df["income_tax_paid_on_cash_basis_excl_resource"] = (
        T - df["resource_tax_deduction_usd"]
    )

    # ---- (2) Resources included (reference) -----------------------------
    # incl_resource: gross profit and tax up by actual pre-profit resource
    # payments (royalties etc. — costs that already reduced reported profit).
    df["profit_loss_incl_resource"] = P + df["pre_profit_payments_usd"]
    df["income_tax_paid_on_cash_basis_incl_resource"] = (
        T + df["pre_profit_payments_usd"]
    )

    # ---- (3) Minimum royalty (IGF-ATAF floor) ---------------------------
    # Built LAST, mirroring the paper: the floor sits on top of the completed
    # resources-excluded correction. Constructed at (source, HQ, commodity,
    # year) level, aggregated country-wide, then allocated onto the CbCR cells
    # in a second allocation pass (same within-cell revenue weights as the
    # payments above, so the split is identical to a combined pass).
    flex = _build_flex_inputs(
        cbcr,
        pay[["source_iso3", "hq_iso3", "commodity", "year",
             "pre_profit", "post_profit_payments_usd", "equity_income_usd",
             "resource_profit_base", "rate"]],
    )

    # The IGF-ATAF minimum royalty is a floor on the state's TOTAL resource
    # take, not just on the expensed pre-profit royalties. So the floor is
    # compared against actual total capture (pre-profit royalties/fees +
    # post-profit taxes + state equity income) — the same pre+post+equity
    # quantity carried in `actual_resource_contribution_usd`. The add-on is
    # only the shortfall of that total below the floor; a country that
    # already collects enough via profit-based taxes and/or equity (even if
    # its expensed royalties are tiny) gets no top-up.
    flex["total_capture"] = (
        flex["pre_profit"].fillna(0.0)
        + flex["post_profit_payments_usd"].fillna(0.0)
        + flex["equity_income_usd"].fillna(0.0)
    )
    for variant, base_col, rate_col in (
        ("cat1", "gross_revenue_usd", "cat1_rate"),
        ("cat2", "gross_revenue_usd", "cat2_rate"),
        ("cat3", "rent_usd", "cat3_rate"),
    ):
        flex[f"flex_min_{variant}_usd"] = (
            flex[rate_col] * flex[base_col] * flex["hq_share"]
        )

    # The floor binds on the AGGREGATE, not commodity-by-commodity. We first
    # sum each (source, hq, year) cell's total capture and its minimum-royalty
    # requirement across all its commodities, THEN take the max. This maps
    # 1:1 to the CbCR (iso_partner, iso_parent, year) cell. Computing the floor
    # per-commodity instead spuriously tops up a jurisdiction on the minerals
    # where it under-collects while ignoring the (often larger) surplus on the
    # minerals where it over-collects — e.g. China's total take ($343B) exceeds
    # its summed minimum ($309B), yet a per-commodity floor would still add
    # ~$142B. Assessing the whole resource sector together (the aggregate) is
    # both more defensible as a minimum-royalty concept and avoids that
    # artifact: a jurisdiction collecting enough overall gets no top-up.
    flex_min_cols = [f"flex_min_{v}_usd" for v in FLEX_VARIANTS]
    flex_agg = (
        flex.groupby(["hq_iso3", "source_iso3", "year"], as_index=False)
        .agg({"total_capture": "sum", **{c: "sum" for c in flex_min_cols}})
        .rename(columns={"hq_iso3": "iso_parent", "source_iso3": "iso_partner"})
    )
    # COUNTRY-WIDE floor: the minimum binds on the SOURCE COUNTRY's aggregate
    # capture vs its aggregate floor, not per HQ. A per-HQ max would create
    # attribution-sensitive add-ons for countries whose aggregate capture already
    # exceeds the floor (Σ max(c_h, m_h) > max(Σc, Σm); Zimbabwe would keep a
    # ~$170m/yr per-HQ add-on even with its mining CIT recorded). The country
    # add-on is allocated across the country's (hq, year) rows by ownership share
    # of the floor base (flex_min), so the profit-side deduction still lands
    # bilaterally.
    # The CAPTURE side of the test is ALL resource revenue, tier-independent:
    # the payments panel drops unmatched / domestic-non-MNE
    # EITI rows (right for the correction, wrong for "did the state collect
    # enough?"). Credit each (source, year) with the LARGEST complete recorded
    # figure: panel take, full EITI company total (pre-gating, corrected values,
    # negatives clipped per row), and - only where the panel year is itself an
    # extrapolation - the GRD total resource revenue (real fiscal data beats our
    # gap-fill). Manual-tier countries keep their curated totals (panel = full).
    _el = pd.read_csv(f"{data_intermediate_extractive}eiti_company_payments_long.csv",
                      usecols=["iso3", "year", "value_usd"], low_memory=False)
    _el["v"] = pd.to_numeric(_el["value_usd"], errors="coerce").clip(lower=0)
    _eiti_full = _el.groupby(["iso3", "year"])["v"].sum()
    _rd = pd.read_csv(f"{data_intermediate_extractive}extractive_royalty_dataset_yearly.csv",
                      usecols=["iso3", "year", "grd_total_resource_rev_usd"])
    _grd_tot = pd.to_numeric(_rd.set_index(["iso3", "year"])["grd_total_resource_rev_usd"],
                             errors="coerce")
    _extrap = (pay.groupby(["source_iso3", "year"])["data_source"]
                  .apply(lambda s: s.astype(str).str.contains("extrapolated").all()))
    _keys = list(zip(flex_agg["iso_partner"], flex_agg["year"]))
    _eiti_v = pd.Series([_eiti_full.get(k, 0.0) for k in _keys], index=flex_agg.index)
    _grd_v = pd.Series([_grd_tot.get(k, np.nan) for k in _keys], index=flex_agg.index).fillna(0.0)
    _is_ext = pd.Series([bool(_extrap.get(k, False)) for k in _keys], index=flex_agg.index)

    for v in FLEX_VARIANTS:
        cty = flex_agg.groupby(["iso_partner", "year"])
        cap_sum = cty["total_capture"].transform("sum")
        capture_all = np.maximum(cap_sum, _eiti_v)
        capture_all = np.where(_is_ext, np.maximum(capture_all, _grd_v), capture_all)
        min_sum = cty[f"flex_min_{v}_usd"].transform("sum")
        addon_cty = (min_sum - capture_all).clip(lower=0.0)
        w = np.where(min_sum > 0, flex_agg[f"flex_min_{v}_usd"] / min_sum.replace(0, np.nan), 0.0)
        flex_agg[f"floor_add_on_{v}_usd"] = addon_cty * pd.Series(w, index=flex_agg.index).fillna(0.0)
        flex_agg[f"capture_floored_{v}_usd"] = (
            flex_agg["total_capture"] + flex_agg[f"floor_add_on_{v}_usd"]
        )
    flex_cols = (
        flex_min_cols
        + [f"capture_floored_{v}_usd" for v in FLEX_VARIANTS]
        + [f"floor_add_on_{v}_usd" for v in FLEX_VARIANTS]
    )
    flex_agg = flex_agg[["iso_parent", "iso_partner", "year"] + flex_cols]

    # Floor cells with no CbCR line are silently lost in the left merge of the
    # allocation below — make that visible (companion to the payments
    # diagnostic above).
    _fchk = flex_agg.merge(_cells, on=["iso_parent", "iso_partner", "year"], how="left", indicator=True)
    _funm = _fchk[_fchk["_merge"] == "left_only"].drop(columns="_merge")
    if len(_funm):
        _ftot = _funm[[f"floor_add_on_{v}_usd" for v in FLEX_VARIANTS]].sum()
        print(f"  [diag] {len(_funm):,} floor cells have NO CbCR line and are dropped: "
              + ", ".join(f"{v}=${_ftot[f'floor_add_on_{v}_usd']/1e9:,.1f}B" for v in FLEX_VARIANTS)
              + f" → {data_intermediate_extractive}resource_correction_unmatched_floor_cells.csv")
        _funm.to_csv(f"{data_intermediate_extractive}resource_correction_unmatched_floor_cells.csv", index=False)
        # (source, year) totals of the cell-less floor — absorbed into the
        # country pool by the reported-reallocated (3a) file only.
        lost_floor = _funm.groupby(["iso_partner", "year"])[
            [f"floor_add_on_{v}_usd" for v in FLEX_VARIANTS]].sum()

    if len(_funm) == 0:
        lost_floor = None

    df = _allocate_payments_to_cbcr_cells(df, flex_agg, flex_cols)

    # The minimum-royalty floor applies only to genuine resource economies; zero
    # the floor add-on for excluded (non-resource) countries so they get no floor
    # revenue (without this, ~$10B would land on France, Ireland,
    # Switzerland, Singapore, Japan, … via trivial WB rent-proxy rents).
    excl_partner = ~df["iso_partner"].isin(included_iso)
    for v in FLEX_VARIANTS:
        df.loc[excl_partner, f"floor_add_on_{v}_usd"] = 0.0

    # The minimum royalty is a PROTECTION FOR LOW-CAPACITY RESOURCE PRODUCERS —
    # the IGF-ATAF flexible royalty targets states with limited administrative
    # capacity to audit profit-based fiscal instruments. The floor therefore
    # binds ONLY for source countries whose OFFICIAL World Bank income group is
    # low or lower-middle income; high- and upper-middle-income producers are
    # taken to have the capacity to set their own fiscal terms and receive no
    # hypothetical top-up.
    # The gate uses the OFFICIAL WB classification (looked up from
    # data/final/cbcr_main.csv), NOT the pipeline's wb_income_group — the latter
    # overwrites havens as "tax_haven", and a hub that is officially
    # low-income (e.g. Liberia) must keep the floor while a high-income hub
    # (Netherlands, $2.1bn; UAE) must not. Env-overridable.
    FLOOR_BINDING_INCOME_GROUPS = set(
        g.strip() for g in os.environ.get(
            "FLOOR_BINDING_INCOME_GROUPS",
            "low_income,lower_middle_income").split(",") if g.strip()
    )
    if FLOOR_BINDING_INCOME_GROUPS:
        _official = (
            pd.read_csv(f"{data_final}cbcr_main.csv",
                        usecols=["iso_partner", "wb_income_group_official"],
                        low_memory=False)
            .dropna(subset=["wb_income_group_official"])
            .drop_duplicates("iso_partner")
            .set_index("iso_partner")["wb_income_group_official"]
        )
        _grp = df["iso_partner"].map(_official)
        if "wb_income_group" in df.columns:
            _grp = _grp.fillna(df["wb_income_group"])   # fallback where WB doesn't classify
        _not_binding = ~_grp.isin(FLOOR_BINDING_INCOME_GROUPS)
        _zeroed = sorted(set(
            df.loc[_not_binding & (df[f"floor_add_on_{PRIMARY_CATEGORY}_usd"] > 0),
                   "iso_partner"]))
        for v in FLEX_VARIANTS:
            df.loc[_not_binding, f"floor_add_on_{v}_usd"] = 0.0
        # The cell-less floor slices (lost_floor) are re-injected onto the
        # reported rows by _reallocate_floor_to_reported AFTER this gate, so
        # they must be gated too. Otherwise a non-binding source whose floor is
        # entirely cell-less — e.g. China, whose floor is all in the 2022 price
        # spike and booked by domestic non-reporters — keeps its full floor via
        # the reallocation even though its directly-allocated rows were zeroed.
        if lost_floor is not None and len(lost_floor):
            _lf_iso = pd.Index(lost_floor.index.get_level_values("iso_partner"))
            _lf_grp = pd.Series(_lf_iso, index=lost_floor.index).map(_official)
            if "wb_income_group" in df.columns:
                _pipe_grp = (df.drop_duplicates("iso_partner")
                             .set_index("iso_partner")["wb_income_group"])
                _lf_grp = _lf_grp.fillna(
                    pd.Series(_lf_iso, index=lost_floor.index).map(_pipe_grp))
            _lf_not_binding = (~_lf_grp.isin(FLOOR_BINDING_INCOME_GROUPS)).to_numpy()
            _lf_has_floor = (
                lost_floor[f"floor_add_on_{PRIMARY_CATEGORY}_usd"] > 0).to_numpy()
            _zeroed = sorted(set(_zeroed)
                             | set(_lf_iso[_lf_not_binding & _lf_has_floor]))
            for v in FLEX_VARIANTS:
                col = f"floor_add_on_{v}_usd"
                if col in lost_floor.columns:
                    lost_floor.loc[_lf_not_binding, col] = 0.0
        if _zeroed:
            print(f"  [floor gate] minimum royalty binding only for "
                  f"{sorted(FLOOR_BINDING_INCOME_GROUPS)} (official WB groups); "
                  f"zeroed the floor add-on for {len(_zeroed)} higher-income "
                  f"producers: {_zeroed}")

    # excl_resource_floored conceptual story: imagine the IGF-ATAF flexible
    # royalty had been enforced as a floor on the state's TOTAL resource take
    # (pre-profit royalties + post-profit taxes + equity income). Where that
    # total capture fell below the floor, the state would have collected the
    # shortfall (floor_add_on_{v}_usd) as additional royalty. Royalty is a
    # pre-profit cost, so it would have *reduced* the company's pre-tax profit;
    # the UT pool shrinks by floor_add_on on top of the resource_profit_base
    # deduction, and the tax line is unchanged. Total state recovery = UT-derived
    # revenue (script 5) + Σ floor_add_on as two separate streams.
    #
    # The floored profit columns depend on the floor_add_on ALLOCATION, so they
    # are NOT built here. Instead two floored files are written below from the
    # same floor_add_on base: the _allrows file (split across all rows, for the
    # gravity / full sample) and the default file (re-allocated onto reported
    # rows, for the reported sample) — see `_compute_floored_cols` /
    # `_reallocate_floor_to_reported` and the two-file write.

    df["actual_resource_contribution_usd"] = (
        df["pre_profit_payments_usd"]
        + df["post_profit_payments_usd"]
        + df["equity_income_usd"]
    )

    # Per-parent-year totals (UT pools) — non-floored (allocation-independent).
    grp = df.groupby(["iso_parent", "year"])
    df["total_profit_loss_excl_resource"] = (
        grp["profit_loss_excl_resource"].transform("sum")
    )
    df["total_profit_loss_incl_resource"] = (
        grp["profit_loss_incl_resource"].transform("sum")
    )

    # Non-resource ETR family (computed once on the excl_resource pair, then
    # used in all three output files).
    partner_year, pair_year = _compute_excl_resource_etrs(df)
    df = _attach_etrs(df, partner_year, pair_year)
    df = _fill_excl_resource_etrs(df)

    # Exploratory resource factor (no paper scenario): merged so the
    # incl_resource file and the disaggregated stitch-back carry it for
    # experimentation. Drop first on reruns to avoid merge collisions.
    if "resource_factor_usd" in df.columns:
        df = df.drop(columns=["resource_factor_usd"])
    rf = _compute_resource_factor()
    df = df.merge(rf, on=["iso_parent", "iso_partner", "year"], how="left")
    df["resource_factor_usd"] = df["resource_factor_usd"].fillna(0.0)

    # ── Columns per output file ──────────────────────────────────────────
    base_cols = [c for c in cbcr.columns if c not in ETR_COLS_TO_DROP]
    etr_cols = ETR_COLS_PARTNER + [ETR_COL_PAIR]

    excl_cols = (
        base_cols
        + [
            "resource_profit_base_usd",
            "resource_tax_deduction_usd",
            "post_profit_payments_usd",
            "equity_income_usd",
            "profit_loss_excl_resource",
            "income_tax_paid_on_cash_basis_excl_resource",
            "total_profit_loss_excl_resource",
        ]
        + etr_cols
    )

    incl_cols = (
        base_cols
        + [
            "pre_profit_payments_usd",
            "post_profit_payments_usd",
            "equity_income_usd",
            "actual_resource_contribution_usd",
            "resource_factor_usd",
            "profit_loss_incl_resource",
            "income_tax_paid_on_cash_basis_incl_resource",
            "total_profit_loss_incl_resource",
        ]
        + etr_cols
    )

    excl_floored_cols = (
        base_cols
        + [
            "resource_profit_base_usd",
            "resource_tax_deduction_usd",
            "post_profit_payments_usd",
            "equity_income_usd",
            "pre_profit_payments_usd",
            "actual_resource_contribution_usd",
        ]
        + [f"flex_min_{v}_usd" for v in FLEX_VARIANTS]
        + [f"floor_add_on_{v}_usd" for v in FLEX_VARIANTS]
        + [f"profit_loss_excl_resource_floored_{v}" for v in FLEX_VARIANTS]
        + [f"income_tax_paid_on_cash_basis_excl_resource_floored_{v}" for v in FLEX_VARIANTS]
        + [f"total_profit_loss_excl_resource_floored_{v}" for v in FLEX_VARIANTS]
        + [
            "profit_loss_excl_resource_floored",
            "income_tax_paid_on_cash_basis_excl_resource_floored",
            "total_profit_loss_excl_resource_floored",
        ]
        + etr_cols
    )

    _write_dataset(df, excl_cols, OUT_EXCL, "cbcr_main_excl_resource.csv")
    _write_dataset(df, incl_cols, OUT_INCL, "cbcr_main_incl_resource.csv")

    # Two floored files from the same floor_add_on base (see note above):
    #   _allrows → floor split across ALL rows (gravity / full-disaggregation sample)
    #   default  → floor re-allocated onto REPORTED rows (reported sample, headline)
    # Script 5 picks the file by REPORTED_ONLY.
    df_floor_allrows = _compute_floored_cols(df.copy())
    _write_dataset(df_floor_allrows, excl_floored_cols, OUT_EXCL_FLOOR_ALLROWS,
                   "cbcr_main_excl_resource_floored_allrows.csv")
    # `df` carries the reported-row allocation afterwards (used by the summary
    # prints below). This file ALSO absorbs the cell-less ("lost") floor into
    # each source country's pool (lost_floor); the _allrows file above lets it
    # drop — per-line semantics there.
    df = _compute_floored_cols(_reallocate_floor_to_reported(df, lost_floor=lost_floor))
    _write_dataset(df, excl_floored_cols, OUT_EXCL_FLOOR,
                   "cbcr_main_excl_resource_floored.csv")

    # Stitch the resource-corrected average ETR (etr_average_excl_resource)
    # onto the disaggregated baseline so the 15% haven test in script 5 can use
    # the NON-resource ETR even on the baseline "resources ignored" dataset
    # (project decision: the misalignment haven threshold always refers to the
    # resource-corrected ETR). Consumed by 7c and the domestic-foreign
    # bootstrap as well.
    stitch_cols = ["iso_parent", "iso_partner", "year", "etr_average_excl_resource",
                   "resource_factor_usd"]   # factor = exploratory extra
    etr_for_disagg = df[stitch_cols]
    # On reruns, the disaggregated CSV may already contain the stitched column
    # (and resource_factor_usd) — drop first so the merge doesn't
    # create _x/_y duplicates.
    cbcr_stitch_base = cbcr.drop(
        columns=["resource_factor_usd", "etr_average_excl_resource"], errors="ignore"
    )
    cbcr_aug = cbcr_stitch_base.merge(
        etr_for_disagg, on=["iso_parent", "iso_partner", "year"], how="left",
    )
    cbcr_aug["resource_factor_usd"] = cbcr_aug["resource_factor_usd"].fillna(0.0)
    if len(cbcr_aug) != len(cbcr):
        raise RuntimeError(
            f"disaggregated augmentation row count changed: {len(cbcr):,} → {len(cbcr_aug):,}"
        )
    cbcr_aug.to_csv(CBCR, index=False)
    print(f"Wrote {CBCR}  ({len(cbcr_aug):,} rows, {len(cbcr_aug.columns)} columns)  "
          f"[appended etr_average_excl_resource + resource_factor_usd (exploratory)]")

    # ── Headline diagnostics ──────────────────────────────────────────────
    print()
    sum_p = P.sum() / 1e9
    sum_t = T.sum() / 1e9
    print(f"Σ reported profit:                   ${sum_p:>10,.0f} B")
    print(f"Σ reported cash tax:                 ${sum_t:>10,.0f} B")
    print()
    sum_excl_p = df["profit_loss_excl_resource"].sum() / 1e9
    sum_excl_t = df["income_tax_paid_on_cash_basis_excl_resource"].sum() / 1e9
    sum_base = df["resource_profit_base_usd"].sum() / 1e9
    sum_dedn = df["resource_tax_deduction_usd"].sum() / 1e9
    print(f"excl_resource:")
    print(f"  profit_loss_excl_resource                = reported − ${sum_base:,.0f} B base   → ${sum_excl_p:,.0f} B")
    print(f"  income_tax_paid_on_cash_basis_excl_resource = reported − ${sum_dedn:,.0f} B tax-dedn  → ${sum_excl_t:,.0f} B")
    if "resource_correction_method" in df.columns:
        ms = df.groupby("resource_correction_method")["resource_tax_deduction_usd"].sum() / 1e9
        print("    tax deduction by method (USD B): "
              + ", ".join(f"{k}={v:,.0f}" for k, v in ms.items()))
    print()
    sum_incl_p = df["profit_loss_incl_resource"].sum() / 1e9
    sum_incl_t = df["income_tax_paid_on_cash_basis_incl_resource"].sum() / 1e9
    sum_pre = df["pre_profit_payments_usd"].sum() / 1e9
    sum_actual = df["actual_resource_contribution_usd"].sum() / 1e9
    print(f"incl_resource:")
    print(f"  profit_loss_incl_resource                = reported + ${sum_pre:,.0f} B pre-profit  → ${sum_incl_p:,.0f} B")
    print(f"  income_tax_paid_on_cash_basis_incl_resource = reported + ${sum_pre:,.0f} B pre-profit  → ${sum_incl_t:,.0f} B")
    print(f"  actual_resource_contribution (pre+post+equity, diagnostic):  ${sum_actual:,.0f} B")
    print()
    print(f"excl_resource_floored (Cat 1 alias = default):")
    print(f"  floor enforced on TOTAL resource take (pre+post+equity), not pre-profit alone.")
    print(f"  pre = profit_loss_excl_resource − floor_add_on_<cat>; tax line unchanged from excl_resource.")
    print(f"  Total recovered revenue = (UT-derived revenue on the smaller pool) + Σ floor_add_on_<cat>.")
    for v in FLEX_VARIANTS:
        addon = df[f"floor_add_on_{v}_usd"].sum() / 1e9
        prof = df[f"profit_loss_excl_resource_floored_{v}"].sum() / 1e9
        marker = "  (alias = cat1)" if v == PRIMARY_CATEGORY else ""
        print(f"  {v}: floor_add_on (≡ extra royalty revenue) ${addon:,.0f} B, "
              f"profit ${prof:,.0f} B{marker}")

    n_dist_nan_pair = df.loc[df["is_distributed"] == 1, ETR_COL_PAIR].isna().sum()
    n_rep_nonnan_pair = df.loc[df["is_distributed"] == 0, ETR_COL_PAIR].notna().sum()
    print()
    print(f"ETR sanity ({ETR_COL_PAIR}):")
    print(f"  distributed rows with NaN: {n_dist_nan_pair:,}/{(df['is_distributed']==1).sum():,}")
    print(f"  reported rows with value:  {n_rep_nonnan_pair:,}/{(df['is_distributed']==0).sum():,}")


if __name__ == "__main__":
    main()
