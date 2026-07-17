# %% [markdown]
# Resource carve-out: variable royalty per the IISD/IGF Lassourd & Manley
# (2022) framework. Computes all three categories of variable royalty in
# parallel so the writeup can compare them; one is selected as the primary
# output via PRIMARY_CATEGORY.
#
# Reads:  data/final/cbcr_main_with_extractives.csv
# Writes: data/final/cbcr_main_with_carveout.csv
#
# ─── The three royalty categories ────────────────────────────────────────
#
# Category 1 — price-based royalty on gross revenue.
#   rate = f(commodity reference price for the year)
#   base = gross extractive revenue (volume × price)
#   Examples: Mauritania, Bolivia, Kyrgyzstan.
#
# Category 2 — margin-based royalty on gross revenue.
#   rate = f(operating margin = EBIT / gross revenue)
#   base = gross extractive revenue
#   Same base as Cat 1 but the rate moves with profitability rather than
#   commodity price.
#
# Category 3 — margin-based royalty on operating profit.
#   rate = f(operating margin)
#   base = resource rent (rent_<cat>_usd, used as the operating-profit
#   proxy because resource rent already isolates the surplus over costs)
#   Closer to a variable profit tax than a true royalty. Examples: Peru
#   and Chile mining royalties.
#
# All three apply only to the cross-border IOC pool — the (1 − state_share)
# factor strips out rent already captured by the host state through
# royalties + CIT + state PSA equity.
#
# ─── Per-row formulas (per commodity category c) ─────────────────────────
#
# Shared ingredients (built in script 3, present in cbcr_main_with_extractives):
#   price_c                 reference commodity price for the year
#   gross_revenue_c_usd     rent_c_usd / rent_fraction_c (back-computed; for
#                           EITI/EIA/BGS-sourced cells this exactly recovers
#                           the upstream <src>_revenue_usd; for WB cells it
#                           is approximate)
#   volume_c                gross_revenue_c / price_c (implied physical units)
#   rent_c_usd              resource rent (Cat 3 base)
#
# Computed here (script 4):
#   ioc_factor              (1 - state_share)
#   margin                  extractive_operating_margin per (iso_partner, year)
#                           = Σ profit_loss_before_income_tax_corrected
#                             / max(Σ unrelated_party_revenues, 1)
#
# Per-category rates:
#   cat1_rate_c   linear in price_c (per-category price range)
#   cat2_rate     linear in margin (uniform across commodities in same row)
#   cat3_rate     linear in margin (different range)
#
# Per-row royalty USD:
#   royalty_cat1_c[row] = cat1_rate_c × gross_revenue_c × hq_share_c × ioc_factor
#   royalty_cat2_c[row] = cat2_rate   × gross_revenue_c × hq_share_c × ioc_factor
#   royalty_cat3_c[row] = cat3_rate   × rent_c_usd     × hq_share_c × ioc_factor
#
# Total per variant:
#   expected_royalty_cat{1,2,3}_usd[row] = Σ_c royalty_cat{1,2,3}_c
#
# ─── Reference prices (Cat 1 rate) ───────────────────────────────────────
#
# The Cat 1 RATE is a function of the commodity reference price. The price
# tables here must match the price_<cat> columns built in script 3 and the
# reference prices in src/3_extractive_prep/2_9_combined_rents.py:
#   oil_gas   Brent (USD/bbl)
#   coal      Australian thermal coal (USD/tonne)
#   minerals  iron ore CFR China (USD/tonne) — single anchor for the basket
#
# ─── Simplifications to revisit (TODOs) ──────────────────────────────────
#
# - Cat 1 mineral rate is a per-HS-revenue-weighted blend of each mineral's
#   own price-based rate (from rents_per_mineral_yearly.csv, built by 2_9b).
#   The iron-ore price serves only as the fallback rate for partners whose
#   minerals came from WB-bundled data (no HS detail). HQ shares are still
#   bundled at the minerals level, so the per-mineral split affects the
#   *rate*, not which parent country gets attributed which mineral.
# - Gross revenue (script 3) for WB-only cells is back-computed using
#   calibrated rent fractions (flat per-category default fallback). For
#   EITI/EIA/BGS cells this is exact; for WB cells it is approximate.
# - The rate bands (Cat 1 and Cat 2: 1–10%; Cat 3: 1–12%) are TJN
#   modeller's calibrations. The IISD/IGF paper does not prescribe a
#   single canonical range. Tune via the constants below.

# %%
import os
import sys
import pandas as pd
import numpy as np
from config import *

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format


# %% [1] Configuration

# Which category to alias as the primary `expected_royalty_*` columns.
PRIMARY_CATEGORY = "cat1"   # one of "cat1", "cat2", "cat3"

# Cat 1: rate scales linearly with commodity price.
CAT1_FLOOR, CAT1_CAP = 0.01, 0.10

# Cat 2: rate scales linearly with operating margin. Base = gross revenue.
CAT2_FLOOR, CAT2_CAP = 0.01, 0.10

# Cat 3: rate scales linearly with operating margin. Base = resource rent.
# Resource rent is roughly 30-50% of gross revenue, so Cat 3 with the same
# rate band would yield smaller absolute royalties than Cat 2 — wider rate
# band keeps total revenue comparable.
CAT3_FLOOR, CAT3_CAP = 0.01, 0.12

# Margin at which the rate hits its CAP. 60% follows the IISD/IGF
# variable-royalty calibration recommendation (mining margins above 50%
# are very rare per the paper's Fig 5).
MARGIN_AT_CAP = 0.60

# Profit variable used in the operating-margin numerator.
PROFIT_VAR = "profit_loss_before_income_tax_corrected"

# Reference price tables come from the shared module (src/3_extractive_prep/
# _reference_prices.py — single source of truth; importable here via the
# sys.path entry added in config.py). For minerals, IRON_ORE = the fallback
# anchor used only when a partner has no per-mineral detail.
from _reference_prices import (
    BRENT_USD_BBL, COAL_AUS_USD_T, MINERAL_PRICES,
    MINERAL_HIST_MIN, MINERAL_HIST_MAX,
)
IRON_ORE_USD_T = MINERAL_PRICES["2601"]
CATEGORY_PRICES = {
    "oil_gas": BRENT_USD_BBL,
    "coal": COAL_AUS_USD_T,
    "minerals": IRON_ORE_USD_T,   # fallback anchor when per-mineral data is absent
}
PRICE_UNIT = {
    "oil_gas": "USD/bbl (Brent)",
    "coal": "USD/tonne (Aus thermal)",
    "minerals": "USD/tonne (iron ore, fallback)",
}
# Historical price range (panel min/max) anchoring the Cat 1 rate scale.
HIST_PRICE_MIN = {cat: min(p.values()) for cat, p in CATEGORY_PRICES.items()}
HIST_PRICE_MAX = {cat: max(p.values()) for cat, p in CATEGORY_PRICES.items()}

PER_MINERAL_PANEL = f"{data_intermediate_extractive}rents_per_mineral_yearly.csv"

CATEGORIES = ("oil_gas", "coal", "minerals")


# %% [2] Inputs
print("Loading cbcr_main_with_extractives...")
IN_PATH = f"{data_final}/cbcr_main_with_extractives.csv"
df = pd.read_csv(IN_PATH)
print(f"  {len(df):,} rows; years {sorted(df['year'].unique())}")

# Sanity: the price/gross_revenue/volume columns must be present (built in
# script 3). If missing, the user has a stale extractives CSV.
_required = [f"{p}_{c}" for p in ("price", "volume")
             for c in CATEGORIES] + [f"gross_revenue_{c}_usd" for c in CATEGORIES]
_missing = [c for c in _required if c not in df.columns]
if _missing:
    raise SystemExit(
        f"cbcr_main_with_extractives.csv is missing carve-out input columns "
        f"{_missing}. Re-run 3_resource_contribution.py first."
    )


# %% [3] Helpers

def _linear_rate(value, v_min, v_max, r_floor, r_cap):
    """Linear scale: r_floor at v_min, r_cap at v_max, clipped outside."""
    if v_max == v_min:
        return r_floor
    multiplier = (value - v_min) / (v_max - v_min)
    multiplier = np.clip(multiplier, 0.0, 1.0)
    return r_floor + (r_cap - r_floor) * multiplier


def _yearly_lookup(table, year):
    year = int(year)
    if year in table:
        return table[year]
    avail = sorted(table.keys())
    return table[avail[0]] if year < avail[0] else table[avail[-1]]


def _load_per_mineral_panel():
    """Read rents_per_mineral_yearly.csv (built by 2_9b) and attach the
    per-HS Cat 1 rate. Returns None if the file isn't present."""
    if not os.path.exists(PER_MINERAL_PANEL):
        print(f"  [warn] {PER_MINERAL_PANEL} not present — Cat 1 minerals "
              f"falls back to the iron-ore anchor. Run 2_9b_per_mineral_rents.py.")
        return None
    pm = pd.read_csv(PER_MINERAL_PANEL)
    pm["hs_code"] = pm["hs_code"].astype(str).str.strip()
    pm = pm[pm["hs_code"].isin(MINERAL_PRICES.keys())].copy()
    # Per-HS Cat 1 rate scales that mineral's price between its own panel
    # min and max. Flat-priced minerals (min==max) get the floor rate.
    pm["cat1_rate_hs"] = pm.apply(
        lambda r: float(_linear_rate(
            r["price_usd"], MINERAL_HIST_MIN[r["hs_code"]],
            MINERAL_HIST_MAX[r["hs_code"]], CAT1_FLOOR, CAT1_CAP,
        )),
        axis=1,
    )
    return pm


# %% [4] Operating margin per (iso_partner, year)
#
# Aggregate margin across all extractive parents in the cell. Used by Cat 2
# and Cat 3 rates. Partner-year-level (constant within a partner-year).
print("Computing extractive_operating_margin per (iso_partner, year)...")
extractive_rows = df["alloc_weight_usd"] > 0
margin_by_cell = (
    df[extractive_rows]
    .groupby(["iso_partner", "year"])
    .apply(
        lambda g: (
            g[PROFIT_VAR].fillna(0).sum()
            / max(g["unrelated_party_revenues"].fillna(0).sum(), 1.0)
        ),
        include_groups=False,
    )
    .rename("extractive_operating_margin")
    .reset_index()
)
df = df.merge(margin_by_cell, on=["iso_partner", "year"], how="left")
# Margins outside [-1, 1] are usually data noise. Clip the upper end at 1.
df["extractive_operating_margin"] = (
    df["extractive_operating_margin"].fillna(0.0).clip(upper=1.0)
)


# %% [4b] Per-mineral panel → revenue-weighted Cat 1 mineral rate
#
# rents_per_mineral_yearly.csv (2_9b) holds the per-HS-code mineral rent /
# gross revenue / price for each (iso3, year). The Cat 1 mineral rate for a
# partner-year is the gross-revenue-weighted average of the per-HS Cat 1
# rates: cat1_rate_minerals = Σ_hs (cat1_rate_hs × gross_rev_hs) / Σ_hs gross_rev_hs.
# Partners absent from the panel (minerals came from WB-bundled, no HS
# detail) fall back to the iron-ore anchor below.
pm_panel = _load_per_mineral_panel()
if pm_panel is not None and not pm_panel.empty:
    blended = (
        pm_panel.assign(_num=lambda d: d["cat1_rate_hs"] * d["gross_revenue_usd"])
        .groupby(["iso3", "year"], as_index=False)
        .agg(_num=("_num", "sum"), _den=("gross_revenue_usd", "sum"))
    )
    blended["cat1_rate_minerals_blended"] = np.where(
        blended["_den"] > 0, blended["_num"] / blended["_den"], np.nan
    )
    blended = blended[["iso3", "year", "cat1_rate_minerals_blended"]].rename(
        columns={"iso3": "iso_partner"}
    )
    df = df.merge(blended, on=["iso_partner", "year"], how="left")
    n_blended = df["cat1_rate_minerals_blended"].notna().sum()
    print(f"  per-mineral blended Cat 1 rate available for {n_blended:,} rows")
else:
    df["cat1_rate_minerals_blended"] = np.nan


# %% [5] Per-row rates for each category
#
# Inputs price_<cat>, gross_revenue_<cat>_usd, volume_<cat> and rent_<cat>_usd
# are already in df (built in script 3). Here we only derive the rates.
print("Computing rates for cat1 (price-based), cat2 and cat3 (margin-based)...")

# Cat 1: per-category rate scales with that category's reference price.
# For minerals, prefer the per-HS-revenue-weighted blended rate (4b); fall
# back to the iron-ore anchor for partners with no per-mineral detail.
for cat in CATEGORIES:
    p_min = HIST_PRICE_MIN[cat]
    p_max = HIST_PRICE_MAX[cat]
    anchored = df[f"price_{cat}"].apply(
        lambda p: float(_linear_rate(p, p_min, p_max, CAT1_FLOOR, CAT1_CAP))
    )
    if cat == "minerals":
        df["cat1_rate_minerals"] = df["cat1_rate_minerals_blended"].combine_first(anchored)
    else:
        df[f"cat1_rate_{cat}"] = anchored

# Cat 2 and Cat 3: single rate per row driven by margin (constant within
# a partner-year, so no per-category split needed).
margin_series = df["extractive_operating_margin"]
df["cat2_rate"] = _linear_rate(
    margin_series, 0.0, MARGIN_AT_CAP, CAT2_FLOOR, CAT2_CAP
)
df["cat3_rate"] = _linear_rate(
    margin_series, 0.0, MARGIN_AT_CAP, CAT3_FLOOR, CAT3_CAP
)


# %% [6] Per-category per-row royalty USD for each variant
#
#   royalty_cat1_<c> = cat1_rate_<c> × gross_revenue_<c>_usd × hq_share_<c> × ioc_factor
#   royalty_cat2_<c> = cat2_rate     × gross_revenue_<c>_usd × hq_share_<c> × ioc_factor
#   royalty_cat3_<c> = cat3_rate     × rent_<c>_usd          × hq_share_<c> × ioc_factor
#
# Cat 3 uses rent_<c>_usd as the operating-profit proxy.
print("Computing per-category per-row royalty for cat1, cat2, cat3...")
ioc_factor = 1.0 - df["state_share"]

for cat in CATEGORIES:
    gross = df[f"gross_revenue_{cat}_usd"]
    rent_c = df[f"rent_{cat}_usd"]
    hq = df[f"hq_share_{cat}"]
    rate1 = df[f"cat1_rate_{cat}"]

    df[f"expected_royalty_cat1_{cat}_usd"] = rate1 * gross * hq * ioc_factor
    df[f"expected_royalty_cat2_{cat}_usd"] = df["cat2_rate"] * gross * hq * ioc_factor
    df[f"expected_royalty_cat3_{cat}_usd"] = df["cat3_rate"] * rent_c * hq * ioc_factor


# %% [7] Variant totals + blended effective rate
print("Aggregating totals per variant...")
ioc_gross_revenue = sum(
    df[f"gross_revenue_{c}_usd"] * df[f"hq_share_{c}"] for c in CATEGORIES
) * ioc_factor
ioc_rent = sum(
    df[f"rent_{c}_usd"] * df[f"hq_share_{c}"] for c in CATEGORIES
) * ioc_factor

for variant in ("cat1", "cat2", "cat3"):
    royalty_cols = [f"expected_royalty_{variant}_{c}_usd" for c in CATEGORIES]
    df[f"expected_royalty_{variant}_usd"] = df[royalty_cols].sum(axis=1)
    # Blended rate denominator: gross revenue for cat1/cat2; rent for cat3.
    denom = ioc_rent if variant == "cat3" else ioc_gross_revenue
    df[f"expected_royalty_{variant}_rate"] = np.where(
        denom > 0,
        df[f"expected_royalty_{variant}_usd"] / denom,
        np.nan,
    )

# Primary aliases follow PRIMARY_CATEGORY toggle.
df["expected_royalty_usd"] = df[f"expected_royalty_{PRIMARY_CATEGORY}_usd"]
df["expected_royalty_rate"] = df[f"expected_royalty_{PRIMARY_CATEGORY}_rate"]


# %% [8] Output — main carveout dataset
from _column_order import COLUMNS_STAGE_4, apply_canonical_order
df = apply_canonical_order(df, COLUMNS_STAGE_4)

OUT = f"{data_final}/cbcr_main_with_carveout.csv"
df.to_csv(OUT, index=False)
print(f"\nWrote {len(df):,} rows -> {OUT}")


# %% [8b] Per-mineral carve-out companion
#
# cbcr_main_carveout_per_mineral.csv — one row per (year, iso_partner,
# hs_code) showing the HS-code-level breakdown of the minerals carve-out:
# the per-HS rent / gross revenue / price / Cat 1 rate, the partner-year's
# IOC weight Σ_parents(hq_share_minerals × (1-state_share)), and the three
# royalty variants attributed to that mineral (summed across parent rows).
#
# Consistency: Σ_hs cat1_royalty_usd per partner-year == the partner-year's
# share of expected_royalty_cat1_minerals_usd in the main dataset.
if pm_panel is not None and not pm_panel.empty:
    print("Building per-mineral carve-out companion...")
    # IOC weight per (iso_partner, year): Σ over parent rows of
    # hq_share_minerals × (1 - state_share).
    _w = df.assign(
        _ioc_w=df["hq_share_minerals"].fillna(0) * (1.0 - df["state_share"].fillna(0))
    )
    ioc_w = (
        _w.groupby(["iso_partner", "year"], as_index=False)
        .agg(
            mineral_ioc_weight=("_ioc_w", "sum"),
            cat2_rate=("cat2_rate", "first"),
            cat3_rate=("cat3_rate", "first"),
            extractive_operating_margin=("extractive_operating_margin", "first"),
        )
        .rename(columns={"iso_partner": "iso3"})
    )
    pm = pm_panel.merge(ioc_w, on=["iso3", "year"], how="inner")
    pm["expected_royalty_cat1_usd"] = (
        pm["cat1_rate_hs"] * pm["gross_revenue_usd"] * pm["mineral_ioc_weight"]
    )
    pm["expected_royalty_cat2_usd"] = (
        pm["cat2_rate"] * pm["gross_revenue_usd"] * pm["mineral_ioc_weight"]
    )
    pm["expected_royalty_cat3_usd"] = (
        pm["cat3_rate"] * pm["rent_usd"] * pm["mineral_ioc_weight"]
    )
    pm = pm.rename(columns={
        "iso3": "iso_partner",
        "cat1_rate_hs": "cat1_rate",
        "price_usd": "price",
        "volume": "volume",
        "gross_revenue_usd": "gross_revenue_usd",
        "rent_usd": "rent_usd",
    })
    pm_cols = [
        "year", "iso_partner", "hs_code", "commodity_name", "source",
        "volume", "volume_unit", "price", "gross_revenue_usd",
        "rent_fraction", "rent_usd",
        "extractive_operating_margin", "mineral_ioc_weight",
        "cat1_rate", "cat2_rate", "cat3_rate",
        "expected_royalty_cat1_usd", "expected_royalty_cat2_usd",
        "expected_royalty_cat3_usd",
    ]
    for c in pm_cols:
        if c not in pm.columns:
            pm[c] = np.nan
    pm = pm[pm_cols].sort_values(["year", "iso_partner", "hs_code"]).reset_index(drop=True)
    PM_OUT = f"{data_final}/cbcr_main_carveout_per_mineral.csv"
    pm.to_csv(PM_OUT, index=False)
    print(f"Wrote {len(pm):,} (year, iso_partner, hs_code) rows -> {PM_OUT}")

    # Consistency check: per-HS Cat 1 sum vs the main dataset's bundled value.
    perhs_sum = pm.groupby(["iso_partner", "year"], as_index=False)[
        "expected_royalty_cat1_usd"
    ].sum().rename(columns={"expected_royalty_cat1_usd": "_perhs"})
    main_sum = df.groupby(["iso_partner", "year"], as_index=False)[
        "expected_royalty_cat1_minerals_usd"
    ].sum().rename(columns={"expected_royalty_cat1_minerals_usd": "_main"})
    chk = perhs_sum.merge(main_sum, on=["iso_partner", "year"], how="left")
    chk["_diff"] = (chk["_perhs"] - chk["_main"]).abs()
    n_off = int((chk["_diff"] > max(1.0, 1e-6)).sum())
    print(f"  consistency: {len(chk)} partner-years; {n_off} with |Cat1 per-HS sum "
          f"− main bundled| > $1 (should be 0 for per-mineral partners)")
else:
    print("  [skip] per-mineral companion (panel not available)")


# %% [9] Console summary
print(f"\nPrimary expected_royalty_* aliases: {PRIMARY_CATEGORY}")
print(f"\nReference price ranges (panel 2016-2024, used by Cat 1):")
for cat in CATEGORIES:
    print(
        f"  {cat:<10s}  {PRICE_UNIT[cat]:<26s}  "
        f"min ${HIST_PRICE_MIN[cat]:>8,.2f}  max ${HIST_PRICE_MAX[cat]:>8,.2f}  "
        f"=> rate {CAT1_FLOOR:.0%} - {CAT1_CAP:.0%}"
    )

print("\nMargin-based rate ranges:")
print(f"  Cat 2  rate {CAT2_FLOOR:.0%} - {CAT2_CAP:.0%} on gross revenue, "
      f"linear in margin (0 to {MARGIN_AT_CAP:.0%})")
print(f"  Cat 3  rate {CAT3_FLOOR:.0%} - {CAT3_CAP:.0%} on resource rent, "
      f"linear in margin (0 to {MARGIN_AT_CAP:.0%})")

print("\nGlobal carve-out totals by variant (USD billions):")
for variant in ("cat1", "cat2", "cat3"):
    total = df[f"expected_royalty_{variant}_usd"].sum() / 1e9
    denom = ioc_rent if variant == "cat3" else ioc_gross_revenue
    mean_rate = df.loc[denom > 0, f"expected_royalty_{variant}_rate"].mean()
    label = "Cat 1 (price-rate × gross rev)" if variant == "cat1" else (
        "Cat 2 (margin-rate × gross rev)" if variant == "cat2" else
        "Cat 3 (margin-rate × rent)"
    )
    print(f"  {label:<32s}  ${total:>7,.1f} B  "
          f"(mean blended effective rate {mean_rate:.1%})")

print(f"\nPer-category breakdown for primary variant ({PRIMARY_CATEGORY}):")
for cat in CATEGORIES:
    sub = df[f"expected_royalty_{PRIMARY_CATEGORY}_{cat}_usd"].sum() / 1e9
    print(f"  {cat:<10s}  ${sub:>7,.1f} B")
