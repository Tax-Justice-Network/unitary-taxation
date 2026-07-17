"""
Correct CbCR profits & taxes for resource-related government payments, and
emit three deliverable datasets ready for unitary-taxation analysis.

The script takes `cbcr_main_disaggregated.csv` and the (HQ, source, commodity,
year) resource-payment panel and writes three files, each self-contained for
running script 5:

  1) data/final/cbcr_main_excl_resource.csv
       "Resources excluded" — strip the resource profit-base and the post-profit
       resource tax. Use for normal UT on the non-extractive corporate income
       only. Ships with the recomputed non-resource ETR family.
         profit_loss_excl_resource
            = profit_loss_before_income_tax_corrected − resource_profit_base_usd
         income_tax_paid_on_cash_basis_excl_resource
            = income_tax_paid_on_cash_basis − post_profit_payments_usd
       and etr_average_excl_resource / etr_partner_median_excl_resource /
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
       same values) so script 5 picks them up unchanged.

  3) data/final/cbcr_main_excl_resource_floored.csv
       "Resources excluded, minimum royalty enforced (IGF-ATAF Cat 1 alias;
       cat2 / cat3 also computed)" — same logic as (1) but the per-row
       `floor_add_on_{v}_usd` (the extra royalty the IGF-ATAF flexible floor
       would have compelled where the state's TOTAL resource take — pre-profit
       payments + post-profit taxes + equity income — fell below it) is also
       deducted from the UT profit pool, on top of the resource_profit_base
       removal. The tax line is left unchanged (the floor is a hypothetical
       royalty, not a counterfactual CIT). Total state recovery under this
       regime = UT-derived revenue on the smaller pool + Σ floor_add_on.

`cbcr_main_disaggregated.csv` (no resource correction; the "resources ignored"
baseline) is untouched by this script. No `cbcr_main_incl_resource_floored.csv`
is emitted: the 5-factor UT in scenario 4 substitutes for the resource regime
entirely, so a minimum-royalty floor on top of it is meaningless.

Inputs : data/final/cbcr_main_disaggregated.csv
         data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv   (built by 1_6 → 1_7 → 1_8)
         data/raw/resources/resource_profit_tax_rate.csv                                    (effective resource profit-tax rate by source × commodity; statutory CIT fallback)
         data/intermediate/extractive/rents_combined_yearly.csv                   (EITI > BGS > EIA > WB layered rents per (iso3, year, category))
         data/intermediate/extractive/rent_fractions_calibrated.csv               (per-(iso, category) rent fractions for back-computing gross revenue)
         data/intermediate/extractive/hq_shares_by_commodity_yearly.csv           (Orbis-derived HQ shares per (year, hq_iso3, commodity))
         src/3_extractive_prep/_reference_prices.py                               (Brent, coal, iron-ore-anchor price tables)
Outputs: data/final/cbcr_main_excl_resource.csv
         data/final/cbcr_main_incl_resource.csv
         data/final/cbcr_main_excl_resource_floored.csv
"""
import os
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import data_final, data_intermediate_extractive, TAX_HAVENS_FUNCTIONAL
from _reference_prices import (
    BRENT_USD_BBL, COAL_AUS_USD_T, MINERAL_PRICES, RENT_FRAC_DEFAULT,
)
from _etr_construction import compute_partner_year_etrs


# Single disaggregated input (gravity activity + profitability profit). The former
# DISAGG_VARIANT toggle (trimmed-mean vs "_gravity") is gone — there is one method.
# DISAGG_BOOT_SUFFIX (e.g. "__boot7") lets the domestic/foreign bootstrap driver
# resource-correct a per-seed disaggregated file and write matching seed-tagged
# output files; empty (default) in normal runs.
_DB = os.environ.get("DISAGG_BOOT_SUFFIX", "")
CBCR = f"{data_final}cbcr_main_disaggregated{_DB}.csv"
PAY = f"{data_intermediate_extractive}resource_payments_by_hq_source_yearly.csv"
RATE = "../data/raw/resources/resource_profit_tax_rate.csv"
ECR = f"{data_final}effective_resource_cit_rates.csv"   # combined effective resource rate (r) for the ETR-gap
RENTS = f"{data_intermediate_extractive}rents_combined_yearly.csv"
RENT_FRAC = f"{data_intermediate_extractive}rent_fractions_calibrated.csv"
HQ_SHARES = f"{data_intermediate_extractive}hq_shares_by_commodity_yearly.csv"
HQ_SHARES_BY_SOURCE = f"{data_intermediate_extractive}hq_shares_by_source_commodity_yearly.csv"
PARAMS = "../data/raw/resources/resource_country_parameters.csv"   # consolidated source of truth: include flag, curated resource rate r, EITI flag

OUT_EXCL = f"{data_final}cbcr_main_excl_resource{_DB}.csv"
OUT_INCL = f"{data_final}cbcr_main_incl_resource{_DB}.csv"
OUT_EXCL_FLOOR = f"{data_final}cbcr_main_excl_resource_floored{_DB}.csv"
# Two floored files (always written): the default carries the floor add-on
# REALLOCATED onto reported rows (for the REPORTED sample, where it is the
# headline); the _allrows file carries the floor add-on split across ALL rows
# (for the gravity / full-disaggregation sample). Script 5 picks the right one
# by REPORTED_ONLY. (This replaces the old single-file FLOOR_ON_REPORTED toggle.)
OUT_EXCL_FLOOR_ALLROWS = f"{data_final}cbcr_main_excl_resource_floored_allrows{_DB}.csv"

PCOL = "profit_loss_before_income_tax_corrected"
TCOL = "income_tax_paid_on_cash_basis"
RATE_MIN, RATE_MAX = 0.05, 0.95   # sanity bounds on the profit-tax divisor

# IGF-ATAF flexible-royalty schedule (originally mirrored retired src/4_carveout.py
# at 1%–10% for Cat 1). Cat 1 was raised to 1.2%–12% (2026-06-03) so that the
# minimum-royalty scenario (S3) flips Burkina Faso — the headline low-income
# "wins only with the floor" example — to a net revenue winner under ALL four
# formula families (it already flipped under three-factor / double-weighted at
# the old rate; SOTJ & CCCTB needed the higher schedule). This globally raises
# the Cat-1 floor add-on for every country.
CAT1_FLOOR, CAT1_CAP = float(os.environ.get("CAT1_FLOOR", "0.01")), float(os.environ.get("CAT1_CAP", "0.10"))   # price-based variable royalty, 1%–10% on gross revenue (clean round bounds, 2026-07-01). Cap lowered 0.12→0.10 earlier so China's price-driven 2022 floor lands "a little positive" without a large overshoot. Floor & cap env-overridable.
CAT2_FLOOR, CAT2_CAP = 0.01, 0.10   # margin-based rate, on gross revenue
CAT3_FLOOR, CAT3_CAP = 0.01, 0.12   # margin-based rate, on rent
MARGIN_AT_CAP = 0.60                # IGF/IISD calibration: margins above 50% rare

CATEGORIES = ("oil_gas", "coal", "minerals")
CAT_REF_PRICES = {
    "oil_gas": BRENT_USD_BBL,
    "coal": COAL_AUS_USD_T,
    "minerals": MINERAL_PRICES["2601"],   # iron ore CFR China — single anchor
}
HIST_PRICE_MIN = {c: min(p.values()) for c, p in CAT_REF_PRICES.items()}
HIST_PRICE_MAX = {c: max(p.values()) for c, p in CAT_REF_PRICES.items()}

PRIMARY_CATEGORY = "cat1"
FLEX_VARIANTS = ("cat1", "cat2", "cat3")

# ETR family suffix on the resource-corrected (non-resource) ETRs.
ETR_SUFFIX = "excl_resource"
ETR_COLS_PARTNER = [
    f"etr_domestic_{ETR_SUFFIX}",
    f"etr_foreign_{ETR_SUFFIX}",
    f"etr_average_{ETR_SUFFIX}",
    f"etr_partner_median_{ETR_SUFFIX}",
    f"etr_partner_p25_{ETR_SUFFIX}",
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
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
]


def _linear_rate(value, v_min, v_max, r_floor, r_cap):
    """Linear ramp from r_floor at v_min to r_cap at v_max, clipped outside."""
    if v_max == v_min:
        return np.full_like(np.asarray(value, dtype=float), r_floor, dtype=float)
    m = (np.asarray(value, dtype=float) - v_min) / (v_max - v_min)
    m = np.clip(m, 0.0, 1.0)
    return r_floor + (r_cap - r_floor) * m


def _yearly_lookup(table, year):
    year = int(year)
    if year in table:
        return table[year]
    avail = sorted(table.keys())
    return table[avail[0]] if year < avail[0] else table[avail[-1]]


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

    flex = pay.merge(rents, on=["source_iso3", "year", "commodity"], how="left")
    flex = flex.merge(margin, on=["source_iso3", "year"], how="left")
    flex = flex.merge(hq, on=["source_iso3", "year", "hq_iso3", "commodity"], how="left")
    for c in ("rent_usd", "gross_revenue_usd", "price", "cat1_rate", "margin", "hq_share"):
        flex[c] = flex[c].fillna(0.0)
    flex["cat2_rate"] = _linear_rate(flex["margin"].values, 0.0, MARGIN_AT_CAP, CAT2_FLOOR, CAT2_CAP)
    flex["cat3_rate"] = _linear_rate(flex["margin"].values, 0.0, MARGIN_AT_CAP, CAT3_FLOOR, CAT3_CAP)
    return flex


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


def _compute_resource_factor():
    """Compute the 5th-factor `resource_factor_usd` per (iso_parent, iso_partner, year).

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

    Bilateral specificity (added 2026-05-14): the factor previously used the
    *global* per-(hq, commodity, year) share (same number for every source
    country with that commodity). Switching to the source-specific share means
    e.g. Exxon (US parent) operating in Angola now picks up a US share of
    Angolan oil derived from US firms' actual Angolan presence, not US's
    overall ~25% global oil HQ share. The factor is still uniform across all
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


def _write_dataset(df, columns, out_path, label):
    out_cols = [c for c in columns if c in df.columns]
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise RuntimeError(f"{label}: missing columns {missing}")
    df[out_cols].to_csv(out_path, index=False)
    print(f"Wrote {out_path}  ({len(df):,} rows, {len(out_cols)} columns)")


def _reallocate_floor_to_reported(df):
    """Return a COPY of df with each source's total floor add-on re-allocated
    onto its DIRECTLY-REPORTED rows (is_distributed==0), revenue-weighted, per
    (iso_partner, year). Cells whose (iso_partner, year) has no reported row keep
    the original (all-rows) allocation. This makes the reported-only UT sample
    carry the full minimum-royalty deduction (so the pool deduction and the
    royalty stream live in one universe) — at the cost of loading a source's
    whole floor onto whichever parents report it directly."""
    df = df.copy()
    if "is_distributed" not in df.columns:
        return df
    rev = pd.to_numeric(df["total_revenues"], errors="coerce").fillna(0.0).abs()
    rep = (df["is_distributed"] == 0).to_numpy()
    keys = [df["iso_partner"], df["year"]]
    n_rep = pd.Series(rep.astype(float), index=df.index).groupby(keys).transform("sum")
    rev_rep = pd.Series(np.where(rep, rev, 0.0), index=df.index)
    rev_rep_sum = rev_rep.groupby(keys).transform("sum")
    w = np.where(
        rev_rep_sum > 0, rev_rep / rev_rep_sum.replace(0, np.nan),
        np.where(rep, 1.0 / n_rep.replace(0, np.nan), 0.0),
    )
    w = pd.Series(w, index=df.index).fillna(0.0)
    has_rep = (n_rep > 0).to_numpy()
    for v in FLEX_VARIANTS:
        col = f"floor_add_on_{v}_usd"
        tot = df.groupby(keys)[col].transform("sum")
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


def main():
    cbcr = pd.read_csv(CBCR, low_memory=False)
    # Idempotency: this script stitches `resource_factor_usd` and
    # `etr_average_excl_resource` back onto the disaggregated file at the end, so on a
    # re-run they are already present. Drop them here so they don't pollute base_cols
    # or collide (x/y suffixes) when the ETR family is recomputed and re-merged below.
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
    # `data_source` for that year is genuine EITI or hand-curated manual. This replaces
    # the country-level `eiti_iso` flag, which wrongly shielded EITI-flagged countries
    # that actually fall back to GRD/rent-proxy IN the analysis window. Norway is the
    # marquee case: flagged EITI, but 2016-2022 is entirely `grd_distributed` (its EITI
    # panel covers only 2010-2015 & 2023), so its high residual non-resource ETR must be
    # corrected via the gap strip. Saudi Arabia is a documented exception: its manual
    # rate (0.20 Aramco CIT) under-removes, so it is deliberately made correctable and
    # fixed via its effective rate (see resource_country_parameters.csv, SAU=0.45).
    _ptrust = pay["data_source"].astype(str).str.contains("eiti|manual", case=False, na=False)
    trusted_year = {
        (str(i), int(y))
        for i, y in pay.loc[_ptrust, ["source_iso3", "year"]].dropna().to_numpy()
    }
    trusted_year -= {("SAU", y) for y in range(2016, 2023)}

    # Resource-DOMINATED economies — the target set for the generalized residual-ETR
    # floor (the "Saudi fix" applied to every economy whose above-CIT residual ETR is
    # genuinely unremoved resource tax). A country qualifies if its extractive rents
    # are >= 5% of GDP (structural resource-dependence) OR (computed in the correction
    # from the resource share of its own CbCR profit) >= 30%. Diversified economies
    # (UK, Mexico, India, Turkey, Poland, South Africa, Ethiopia, Kenya, …) are
    # EXCLUDED so their above-CIT ETR — which reflects withholding/minimum taxes, not
    # resources — is NOT misattributed to resources and stripped. Tax havens are
    # excluded (their ETR is handled by list-based haven identification) — using the
    # FROZEN functional set, NOT the (presentational) representation list: Saudi
    # Arabia is on the representation list but must keep this floor (it is the
    # original "Saudi fix" target). See docs/extractive/resource_correction_etr_floor.md.
    _rents = pd.to_numeric(params.set_index("iso3")["extractive_rents_pct_gdp"], errors="coerce")
    dominated_rents_iso = set(_rents[_rents >= 5.0].index)
    haven_iso = set(TAX_HAVENS_FUNCTIONAL)

    pay = pay.merge(
        rate[["source_iso3", "commodity", "effective_resource_profit_tax_rate"]],
        on=["source_iso3", "commodity"], how="left",
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
    pay["resource_profit_base"] = np.where(
        post < 0, post / pay["rate"], np.maximum(post / pay["rate"], equity)
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
    #   - negative-post case (e.g. UK decommissioning relief): deduct
    #     `post` itself (negative) so excl tax > reported there, mirroring
    #     the negative profit-base treatment.
    equity_binds = (post >= 0) & (equity > post / pay["rate"])
    pay["resource_tax_deduction"] = np.where(
        equity_binds, equity * pay["rate"], post
    )

    pay["pre_profit"] = pay["pre_profit_payments_usd"].fillna(0.0)

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
    for v in FLEX_VARIANTS:
        flex_agg[f"capture_floored_{v}_usd"] = np.maximum(
            flex_agg["total_capture"], flex_agg[f"flex_min_{v}_usd"]
        )
        flex_agg[f"floor_add_on_{v}_usd"] = (
            flex_agg[f"capture_floored_{v}_usd"] - flex_agg["total_capture"]
        )
    flex_cols = (
        flex_min_cols
        + [f"capture_floored_{v}_usd" for v in FLEX_VARIANTS]
        + [f"floor_add_on_{v}_usd" for v in FLEX_VARIANTS]
    )
    flex_agg = flex_agg[["iso_parent", "iso_partner", "year"] + flex_cols]

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
    agg = agg.merge(flex_agg, on=["iso_parent", "iso_partner", "year"], how="left")

    payment_cols = (
        ["pre_profit_payments_usd", "post_profit_payments_usd",
         "equity_income_usd", "resource_profit_base_usd",
         "resource_tax_deduction_usd"]
        + flex_cols
    )
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
    # oil-major petroleum tax that the external + domestic_share path mis-placed
    # onto the ~0-tax domestic cell.
    #
    # This REPLACES the old profit-only cap, which scaled the tax deduction by the
    # profit-cap ratio and so NEVER capped tax at reported tax → negative residual
    # non-resource tax for heavily-taxed resource cells (36 countries in the
    # audit). Where the gap is inert (observed ETR ≤ statutory CIT — typical for
    # high-CIT cells with exempt/loss-netted profit) we fall back to the external
    # estimate, hard-capped per cell. Negative-post relief (e.g. UK
    # decommissioning) is preserved so excl_tax can exceed reported there.
    c = pd.to_numeric(df["cit"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=0.60)
    r = pd.to_numeric(df["resource_rate_partner"], errors="coerce").fillna(0.30).clip(RATE_MIN, RATE_MAX)

    # Eligibility for the ETR-gap strip, from the consolidated control table:
    #   • included_cell  — a genuine resource economy (include=yes). Excluded
    #     (non-resource) countries get NO correction at all (see below). This
    #     removes the old false positives — Ireland, France, Belgium, Singapore,
    #     … were pulled in by trivial WB rent-proxy panel rows and stripped huge
    #     spurious amounts.
    #   • not EITI — the EITI panel is authoritative & comprehensive for EITI
    #     countries, so the gap is OFF for them; resource is removed only on the
    #     EITI (source, HQ) pairs that carry a panel amount (via the external
    #     path below), zero elsewhere.
    #   • has a curated rate — only fire where we actually have a researched
    #     resource rate r to convert the tax gap into a resource profit base.
    # Elsewhere an above-statutory ETR is not necessarily resource-related (it can
    # reflect withholding, one-off settlements, etc.), so the gap must not fire.
    included_cell = df["iso_partner"].isin(included_iso)
    # Source-aware trust gate (replaces the old country-level `eiti_cell`): a cell is
    # trusted (gap OFF) only if its actual (iso_partner, year) payment source is
    # EITI/manual — see `trusted_year` above. So an EITI-flagged country on GRD data
    # in-window (Norway) is NOT trusted and DOES get the ETR-gap correction.
    _cellkey = list(zip(df["iso_partner"].astype(str), df["year"].astype("Int64").astype("int64")))
    trusted_cell = pd.Series([k in trusted_year for k in _cellkey], index=df.index) & included_cell
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
    # regardless of r. (The old `min(r·rp_gap, T)` left r·P of tax behind on
    # full-resource cells, lifting UAE's non-resource ETR to ~0.19.) For partial
    # cells the residual ETR equals the statutory rate c, as intended.
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
    # negative-post relief (e.g. UK decommissioning): keep the external figures.
    rp = np.where(relief_use, base_raw, rp)
    rt = np.where(relief_use, tax_raw, rt)

    # ---- Generalized residual-ETR floor for RESOURCE-DOMINATED economies --------
    # The "Saudi fix", applied to EVERY resource-dominated economy whose residual
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

    # incl_resource: gross profit and tax up by actual pre-profit resource
    # payments (royalties etc. — costs that already reduced reported profit).
    df["profit_loss_incl_resource"] = P + df["pre_profit_payments_usd"]
    df["income_tax_paid_on_cash_basis_incl_resource"] = (
        T + df["pre_profit_payments_usd"]
    )

    # The minimum-royalty floor applies only to genuine resource economies; zero
    # the floor add-on for excluded (non-resource) countries so they get no floor
    # revenue (removes the ~$10B that previously landed on France, Ireland,
    # Switzerland, Singapore, Japan, … via trivial WB rent-proxy rents).
    excl_partner = ~df["iso_partner"].isin(included_iso)
    for v in FLEX_VARIANTS:
        df.loc[excl_partner, f"floor_add_on_{v}_usd"] = 0.0

    # The minimum royalty is a protection for LOW-CAPACITY resource producers:
    # binding ONLY for source countries whose OFFICIAL World Bank income group is
    # low or lower-middle income (2026-07-11, user decision). High-income
    # producers were always excluded (all UT winners anyway); UPPER-MIDDLE income
    # — dominated by China ($87bn of the $171bn 6-yr add-on), Indonesia ($30bn)
    # and South Africa ($15bn) — are now excluded too: the earlier rationale
    # ("China is a genuine UT loser that the floor turns a little positive") is
    # stale under the current headline spec (sales_employees_destcfb / ETR-CIT),
    # where China is a net revenue winner without any floor.
    # The gate uses the OFFICIAL WB classification (looked up from
    # data/final/cbcr_main.csv), NOT the pipeline's wb_income_group — the latter
    # overwrites havens as "investment_hub", and a hub that is officially
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

    # 4th-factor `resource_factor_usd` (for the five-factor formula on
    # incl_resource). Zero for non-resource (parent, partner) pairs. The
    # disaggregated CSV is overwritten with this column at the end of main
    # so on a rerun the column may already exist — drop it first to avoid
    # merge collisions.
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
    # prints below); floor_add_on totals are conserved by the re-allocation.
    df = _compute_floored_cols(_reallocate_floor_to_reported(df))
    _write_dataset(df, excl_floored_cols, OUT_EXCL_FLOOR,
                   "cbcr_main_excl_resource_floored.csv")

    # Stitch resource_factor_usd back onto the disaggregated baseline so the
    # 5-factor alpha-blended formulas can run on it (needed for the additive
    # five-scenario variant in script 8, where UT runs on reported profit and
    # does NOT add back pre-profit royalty payments). Also stitch the
    # resource-corrected average ETR (etr_average_excl_resource) so the 15%
    # haven test in script 5 can use the NON-resource ETR even on the baseline
    # "resources ignored" dataset (project decision: the misalignment haven
    # threshold always refers to the resource-corrected ETR).
    stitch_cols = ["iso_parent", "iso_partner", "year", "resource_factor_usd"]
    if "etr_average_excl_resource" in df.columns:
        stitch_cols.append("etr_average_excl_resource")
    rf_for_disagg = df[stitch_cols]
    # On reruns, the disaggregated CSV may already contain these stitched
    # columns — drop them first so the merge doesn't create _x/_y.
    cbcr_stitch_base = cbcr.drop(
        columns=["resource_factor_usd", "etr_average_excl_resource"], errors="ignore"
    )
    cbcr_aug = cbcr_stitch_base.merge(
        rf_for_disagg, on=["iso_parent", "iso_partner", "year"], how="left",
    )
    cbcr_aug["resource_factor_usd"] = cbcr_aug["resource_factor_usd"].fillna(0.0)
    if len(cbcr_aug) != len(cbcr):
        raise RuntimeError(
            f"disaggregated augmentation row count changed: {len(cbcr):,} → {len(cbcr_aug):,}"
        )
    cbcr_aug.to_csv(CBCR, index=False)
    print(f"Wrote {CBCR}  ({len(cbcr_aug):,} rows, {len(cbcr_aug.columns)} columns)  "
          f"[appended resource_factor_usd + etr_average_excl_resource]")

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
