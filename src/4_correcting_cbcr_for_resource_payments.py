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
       would have compelled where actual capture fell below it) is also
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
         data/raw/resource_profit_tax_rate.csv                                    (effective resource profit-tax rate by source × commodity; statutory CIT fallback)
         data/intermediate/extractive/rents_combined_yearly.csv                   (EITI > BGS > EIA > WB layered rents per (iso3, year, category))
         data/intermediate/extractive/rent_fractions_calibrated.csv               (per-(iso, category) rent fractions for back-computing gross revenue)
         data/intermediate/extractive/hq_shares_by_commodity_yearly.csv           (Orbis-derived HQ shares per (year, hq_iso3, commodity))
         src/3_extractive_prep/_reference_prices.py                               (Brent, coal, iron-ore-anchor price tables)
Outputs: data/final/cbcr_main_excl_resource.csv
         data/final/cbcr_main_incl_resource.csv
         data/final/cbcr_main_excl_resource_floored.csv
"""
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import data_final, data_intermediate_extractive
from _reference_prices import (
    BRENT_USD_BBL, COAL_AUS_USD_T, MINERAL_PRICES, RENT_FRAC_DEFAULT,
)
from _etr_construction import compute_partner_year_etrs


CBCR = f"{data_final}cbcr_main_disaggregated.csv"
PAY = f"{data_intermediate_extractive}resource_payments_by_hq_source_yearly.csv"
RATE = "../data/raw/resource_profit_tax_rate.csv"
RENTS = f"{data_intermediate_extractive}rents_combined_yearly.csv"
RENT_FRAC = f"{data_intermediate_extractive}rent_fractions_calibrated.csv"
HQ_SHARES = f"{data_intermediate_extractive}hq_shares_by_commodity_yearly.csv"
HQ_SHARES_BY_SOURCE = f"{data_intermediate_extractive}hq_shares_by_source_commodity_yearly.csv"

OUT_EXCL = f"{data_final}cbcr_main_excl_resource.csv"
OUT_INCL = f"{data_final}cbcr_main_incl_resource.csv"
OUT_EXCL_FLOOR = f"{data_final}cbcr_main_excl_resource_floored.csv"

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
CAT1_FLOOR, CAT1_CAP = 0.012, 0.12   # price-based rate, on gross revenue
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


def main():
    cbcr = pd.read_csv(CBCR, low_memory=False)
    pay = pd.read_csv(PAY, comment="#")
    rate = pd.read_csv(RATE, comment="#")
    rate = rate[rate["source_iso3"].str.len() == 3]   # drop non-country placeholders

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
             "pre_profit", "resource_profit_base", "rate"]],
    )

    for variant, base_col, rate_col in (
        ("cat1", "gross_revenue_usd", "cat1_rate"),
        ("cat2", "gross_revenue_usd", "cat2_rate"),
        ("cat3", "rent_usd", "cat3_rate"),
    ):
        flex[f"flex_min_{variant}_usd"] = (
            flex[rate_col] * flex[base_col] * flex["hq_share"]
        )
        flex[f"pre_profit_floored_{variant}_usd"] = np.maximum(
            flex["pre_profit"], flex[f"flex_min_{variant}_usd"]
        )
        # Compute the floor add-on per (source, hq, commodity, year) so the
        # aggregated (parent, partner, year) figure correctly sums the
        # commodity-by-commodity gap. Computing it at the aggregated level
        # would conflate a multi-commodity reporter where one commodity is
        # above its floor and another is below.
        flex[f"floor_add_on_{variant}_usd"] = (
            flex[f"pre_profit_floored_{variant}_usd"] - flex["pre_profit"]
        )

    flex_cols = (
        [f"flex_min_{v}_usd" for v in FLEX_VARIANTS]
        + [f"pre_profit_floored_{v}_usd" for v in FLEX_VARIANTS]
        + [f"floor_add_on_{v}_usd" for v in FLEX_VARIANTS]
    )
    flex_agg = (
        flex.groupby(["hq_iso3", "source_iso3", "year"], as_index=False)[flex_cols].sum()
        .rename(columns={"hq_iso3": "iso_parent", "source_iso3": "iso_partner"})
    )

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

    P = pd.to_numeric(df[PCOL], errors="coerce").fillna(0.0)
    T = pd.to_numeric(df[TCOL], errors="coerce").fillna(0.0)

    # Cap resource_profit_base at the CbCR-reported profit (per row, positive
    # branch). CbCR `profit_loss_before_income_tax` is *already net of
    # pre-profit royalties*, but `resource_profit_base = post / rate` is the
    # implied resource profit BEFORE any deductions including pre-profit
    # royalties. Without the cap we strip more than is in CbCR, driving
    # `profit_loss_excl_resource` deeply negative for heavily-extractive
    # jurisdictions (e.g. UAE-domestic). Tax deduction is capped symmetrically
    # at the cash tax line so the ratio stays consistent.
    base_raw = df["resource_profit_base_usd"]
    tax_raw  = df["resource_tax_deduction_usd"]
    base_capped = np.where(P > 0, np.minimum(base_raw, P), base_raw)
    # Where the base was capped, scale the tax deduction by the same ratio
    # so excl_tax/excl_profit stays symmetric. Avoid div-by-zero.
    with np.errstate(divide="ignore", invalid="ignore"):
        cap_ratio = np.where(base_raw > 0, base_capped / base_raw, 1.0)
    tax_capped = tax_raw * cap_ratio
    df["resource_profit_base_usd"] = base_capped
    df["resource_tax_deduction_usd"] = tax_capped

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

    # excl_resource_floored: strip resource_profit_base AND the floor add-on.
    # Conceptual story: imagine the IGF-ATAF flexible royalty had been
    # enforced — for cells where actual royalty was below the floor, the
    # state would have collected the gap (floor_add_on_{v}_usd) as additional
    # royalty. Royalty is a pre-profit cost, so this would have *reduced*
    # the company's pre-tax profit by floor_add_on. The UT pool therefore
    # shrinks by that amount on top of the existing resource_profit_base
    # deduction. The tax line is left unchanged (the floor is a hypothetical
    # royalty, not a counterfactual CIT adjustment). When reporting total
    # state recovery under this regime, sum UT-derived revenue (from
    # script 5) + Σ floor_add_on_{v}_usd as the two separate streams.
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

    df["actual_resource_contribution_usd"] = (
        df["pre_profit_payments_usd"]
        + df["post_profit_payments_usd"]
        + df["equity_income_usd"]
    )

    # Per-parent-year totals (UT pools).
    grp = df.groupby(["iso_parent", "year"])
    df["total_profit_loss_excl_resource"] = (
        grp["profit_loss_excl_resource"].transform("sum")
    )
    df["total_profit_loss_incl_resource"] = (
        grp["profit_loss_incl_resource"].transform("sum")
    )
    for v in FLEX_VARIANTS:
        df[f"total_profit_loss_excl_resource_floored_{v}"] = (
            grp[f"profit_loss_excl_resource_floored_{v}"].transform("sum")
        )
    df["total_profit_loss_excl_resource_floored"] = (
        df[f"total_profit_loss_excl_resource_floored_{PRIMARY_CATEGORY}"]
    )

    # Non-resource ETR family (computed once on the excl_resource pair, then
    # used in all three output files).
    partner_year, pair_year = _compute_excl_resource_etrs(df)
    df = _attach_etrs(df, partner_year, pair_year)

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
    _write_dataset(df, excl_floored_cols, OUT_EXCL_FLOOR,
                   "cbcr_main_excl_resource_floored.csv")

    # Stitch resource_factor_usd back onto the disaggregated baseline so the
    # 5-factor alpha-blended formulas can run on it (needed for the additive
    # five-scenario variant in script 8, where UT runs on reported profit and
    # does NOT add back pre-profit royalty payments).
    rf_for_disagg = df[["iso_parent", "iso_partner", "year", "resource_factor_usd"]]
    # On reruns, the disaggregated CSV may already contain `resource_factor_usd`
    # from a previous stitch — drop it first so the merge doesn't create _x/_y.
    cbcr_stitch_base = cbcr.drop(columns=["resource_factor_usd"], errors="ignore")
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
          f"[appended resource_factor_usd]")

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
    sum_post = df["post_profit_payments_usd"].sum() / 1e9
    sum_dedn = df["resource_tax_deduction_usd"].sum() / 1e9
    extra_dedn = sum_dedn - sum_post
    print(f"excl_resource:")
    print(f"  profit_loss_excl_resource                = reported − ${sum_base:,.0f} B base   → ${sum_excl_p:,.0f} B")
    print(f"  income_tax_paid_on_cash_basis_excl_resource = reported − ${sum_dedn:,.0f} B tax-dedn  → ${sum_excl_t:,.0f} B")
    print(f"    (of the ${sum_dedn:,.0f} B deducted, ${sum_post:,.0f} B is actual post-profit;")
    print(f"     ${extra_dedn:,.0f} B is the CIT implied by the equity-binding-floor cases)")
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
