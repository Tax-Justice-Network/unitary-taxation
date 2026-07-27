# %%
"""
3_23 — Calibrate per-country BGS-vs-WB scaling factors.

The BGS volumes piped through our HS-mapped commodity subset and embedded
prices systematically under-count WB's bundled mineral_rents because:
  - our HS mapping covers ~25 buckets; WB's `mineral_rents` lumps every
    mineral commodity in one number (alumina, ferro-alloys, salt, gravel,
    gemstones, etc. are out of our scope or unpriced)
  - our embedded prices are Pink Sheet annual averages; WB may use slightly
    different prices internally
  - the calibrated rent fraction (from 3_22) was tuned against WB / EIA
    revenue; applied to BGS revenue (different basket) it does not perfectly
    align magnitudes

This step computes a country-specific multiplicative scaling factor per
(iso3, category) such that:

    rent_bgs_scaled = bgs_revenue x bgs_rent_fraction x bgs_scale

aligns with WB's published level on years where both exist. The same fallback
hierarchy as 3_22 is used (country median > region+income > region > income >
global).

Outlier filter: scale clipped to [0.2, 5.0]. Cells outside that range are
treated as data noise (commodity coverage too sparse, price mismatch, or
WB methodology break) and dropped from the calibration.

Pipeline: Extractive prep, stage 3_23 — after 3_22, before 3_24.

Reads:
  data/raw/extractive/bgs_mineral_production.csv        — BGS mineral production volumes (3_17)
  data/raw/extractive/wb_resource_rents.csv             — WB resource-rent series (3_15)
  data/intermediate/extractive/rent_fractions_calibrated.csv — calibrated rent fractions (3_22)
  data/guides/wb_tax_revenue_country_metadata.csv        — WB Region + IncomeGroup classification

Writes:
  data/intermediate/extractive/bgs_scaling_factors.csv  — iso3, category, scale, source_group, n_cells

Usage:
  python 3_23_calibrate_bgs_scaling.py

Author: Alison Schultz.
Created: 2026-07-17.  Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT
from _reference_prices import (
    MINERAL_PRICES, HS_PRICE_UNIT,
    COAL_AUS_USD_T as COAL_USD_T,
)

OUT_PATH = EXT_INT / "bgs_scaling_factors.csv"


# %% MARK: 2. Load inputs
def _yearly_lookup(table, year):
    if year in table:
        return table[year]
    available = sorted(table.keys())
    if year < available[0]:
        return table[available[0]]
    return table[available[-1]]


def load_classification() -> pd.DataFrame:
    # WB country classification metadata lives in data/guides/; without it
    # the region/income fallback tiers are silently disabled.
    fp = RAW.parent / "guides" / "wb_tax_revenue_country_metadata.csv"
    if not fp.exists():
        print(f"  [WARN] WB country classification not found at {fp} — "
              "region/income fallback tiers DISABLED (global medians only)")
        return pd.DataFrame(columns=["iso3", "region", "income_group"])
    m = pd.read_csv(fp)
    m = m.rename(columns={
        "Country Code": "iso3",
        "Region": "region",
        "IncomeGroup": "income_group",
    })
    return m[["iso3", "region", "income_group"]].dropna(
        subset=["iso3"]
    ).drop_duplicates("iso3")


def load_bgs_revenue() -> pd.DataFrame:
    """Compute (iso3, year, category) revenue from BGS volumes, mirroring
    load_bgs_rents in 3_24 but skipping the rent-fraction step."""
    bgs = pd.read_csv(RAW / "extractive" / "bgs_mineral_production.csv")

    def _norm_hs(v):
        if pd.isna(v):
            return ""
        try:
            return str(int(float(v)))
        except (TypeError, ValueError):
            return str(v).strip()

    bgs["hs_code"] = bgs["hs_code"].apply(_norm_hs)
    bgs = bgs[
        (bgs["hs_code"] != "")
        & bgs["production"].gt(0)
        & bgs["year"].between(2016, 2023)
    ].copy()
    bgs["category"] = np.where(
        bgs["hs_code"].isin(["2701", "2702"]), "coal", "minerals"
    )

    rev_rows = []
    for _, r in bgs.iterrows():
        hs = r["hs_code"]
        cat = r["category"]
        year = int(r["year"])
        unit_lc = str(r["unit"]).strip().lower()
        if cat == "coal":
            if not (unit_lc.startswith("tonnes") or unit_lc.startswith("metric tonnes")
                    or unit_lc.startswith("tonne")):
                continue
            mult = 1000.0 if "thousand" in unit_lc else 1.0
            rev = r["production"] * mult * _yearly_lookup(COAL_USD_T, year)
        else:
            if hs not in MINERAL_PRICES:
                continue
            price_unit = HS_PRICE_UNIT.get(hs)
            if unit_lc.startswith("tonnes") or unit_lc.startswith("metric tonnes"):
                canon, mult = "tonnes", 1.0
            elif unit_lc.startswith("kilograms") or unit_lc.startswith("kg"):
                canon, mult = "tonnes", 0.001
            elif unit_lc.startswith("carats"):
                canon, mult = "carats", 1.0
            elif unit_lc.startswith("ounces") or unit_lc == "oz":
                canon, mult = "tonnes", 3.11034768e-5
            else:
                continue
            converters = {
                ("tonnes", "USD/t"): 1.0,
                ("tonnes", "USD/oz"): 32150.7466,
                ("carats", "USD/carat"): 1.0,
            }
            converter = converters.get((canon, price_unit))
            if converter is None:
                continue
            price = MINERAL_PRICES[hs].get(year)
            if price is None:
                continue
            rev = r["production"] * mult * converter * price
        rev_rows.append({
            "iso3": r["iso3"], "year": year, "category": cat,
            "revenue_usd": rev,
        })

    df = pd.DataFrame(rev_rows)
    if df.empty:
        return df
    return (
        df.groupby(["iso3", "year", "category"], as_index=False)["revenue_usd"]
        .sum()
        .rename(columns={"revenue_usd": "bgs_revenue_usd"})
    )


# %% MARK: 3. Calibrate and write
def main():
    print("Loading inputs...")
    classif = load_classification()
    print(f"  {len(classif)} countries with region/income classification")

    bgs_rev = load_bgs_revenue()
    print(f"  {len(bgs_rev)} (iso3, year, category) BGS revenue cells")

    rf = pd.read_csv(EXT_INT / "rent_fractions_calibrated.csv")
    rf_lookup = {(r["iso3"], r["category"]): r["rent_fraction"]
                 for _, r in rf.iterrows()}

    wb = pd.read_csv(RAW / "extractive" / "wb_resource_rents.csv")
    wb = wb[wb["year"].between(2016, 2021)].copy()
    wb["iso3"] = wb["country_iso3"].astype(str).str.upper()
    wb["wb_minerals_rent"] = wb["mineral_rents_usd"]
    wb["wb_coal_rent"] = wb["coal_rents_usd"]
    wb_long = wb.melt(
        id_vars=["iso3", "year"],
        value_vars=["wb_minerals_rent", "wb_coal_rent"],
        var_name="cat_col", value_name="wb_rent",
    )
    wb_long["category"] = wb_long["cat_col"].str.replace("wb_", "").str.replace("_rent", "")
    wb_long = wb_long.drop(columns="cat_col")
    wb_long = wb_long[wb_long["wb_rent"] > 0]

    # Join BGS revenue with WB rent. Apply the calibrated rent fraction to
    # BGS revenue so we compare like-with-like.
    df = bgs_rev.merge(wb_long, on=["iso3", "year", "category"], how="inner")
    df["bgs_rf"] = df.apply(
        lambda r: rf_lookup.get((r["iso3"], r["category"]), 0.30), axis=1
    )
    df["bgs_rent_unscaled"] = df["bgs_revenue_usd"] * df["bgs_rf"]
    df = df[df["bgs_rent_unscaled"] > 0]
    df["scale"] = df["wb_rent"] / df["bgs_rent_unscaled"]

    # Outlier filter
    n_before = len(df)
    df = df[df["scale"].between(0.2, 5.0)]
    print(f"  {len(df):,} BGS×WB joint cells after outlier filter "
          f"(dropped {n_before - len(df)})")

    # Country median (n>=2)
    country = (
        df.groupby(["iso3", "category"], as_index=False)
        .agg(scale=("scale", "median"), n=("scale", "size"))
    )
    country = country[country["n"] >= 2].copy()

    # Group fallbacks
    df_g = df.merge(classif, on="iso3", how="left")
    rxi = (
        df_g.dropna(subset=["region", "income_group"])
        .groupby(["region", "income_group", "category"], as_index=False)
        .agg(scale=("scale", "median"), n=("scale", "size"))
    )
    reg = (
        df_g.dropna(subset=["region"])
        .groupby(["region", "category"], as_index=False)
        .agg(scale=("scale", "median"), n=("scale", "size"))
    )
    inc = (
        df_g.dropna(subset=["income_group"])
        .groupby(["income_group", "category"], as_index=False)
        .agg(scale=("scale", "median"), n=("scale", "size"))
    )
    glob = (
        df.groupby("category", as_index=False)
        .agg(scale=("scale", "median"), n=("scale", "size"))
    )

    print("\n=== Global median scale by category ===")
    for _, r in glob.iterrows():
        print(f"  {r['category']:<10s} scale={r['scale']:.3f} (n={r['n']})")

    print("\n=== Region medians (minerals) ===")
    for _, r in reg[reg["category"] == "minerals"].sort_values("scale", ascending=False).iterrows():
        print(f"  {r['region'][:32]:<32s}  scale={r['scale']:.3f} (n={r['n']})")
    print("\n=== Income medians (minerals) ===")
    for _, r in inc[inc["category"] == "minerals"].sort_values("scale", ascending=False).iterrows():
        print(f"  {r['income_group'][:25]:<25s}  scale={r['scale']:.3f} (n={r['n']})")

    # Build final lookup
    iso_universe = set(classif["iso3"].dropna()) | set(country["iso3"]) | set(df["iso3"])
    final_rows = []
    cat_set = ("minerals", "coal")
    country_lookup = {(r["iso3"], r["category"]): r for _, r in country.iterrows()}
    rxi_lookup = {(r["region"], r["income_group"], r["category"]): r for _, r in rxi.iterrows()}
    reg_lookup = {(r["region"], r["category"]): r for _, r in reg.iterrows()}
    inc_lookup = {(r["income_group"], r["category"]): r for _, r in inc.iterrows()}
    glob_lookup = {r["category"]: r for _, r in glob.iterrows()}
    classif_map = {r["iso3"]: (r["region"], r["income_group"])
                   for _, r in classif.iterrows()}

    for iso in sorted(iso_universe):
        region, income = classif_map.get(iso, (None, None))
        for cat in cat_set:
            if (iso, cat) in country_lookup:
                r = country_lookup[(iso, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "scale": r["scale"], "source_group": "country",
                                   "n_cells": int(r["n"])})
                continue
            if region and income and (region, income, cat) in rxi_lookup:
                r = rxi_lookup[(region, income, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "scale": r["scale"],
                                   "source_group": f"region+income:{region}|{income}",
                                   "n_cells": int(r["n"])})
                continue
            if region and (region, cat) in reg_lookup:
                r = reg_lookup[(region, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "scale": r["scale"],
                                   "source_group": f"region:{region}",
                                   "n_cells": int(r["n"])})
                continue
            if income and (income, cat) in inc_lookup:
                r = inc_lookup[(income, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "scale": r["scale"],
                                   "source_group": f"income:{income}",
                                   "n_cells": int(r["n"])})
                continue
            if cat in glob_lookup:
                r = glob_lookup[cat]
                final_rows.append({"iso3": iso, "category": cat,
                                   "scale": r["scale"],
                                   "source_group": "global",
                                   "n_cells": int(r["n"])})

    out = pd.DataFrame(final_rows)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(out):,} rows -> {OUT_PATH}")

    # Spot-check African mineral producers + comparators
    print("\n=== BGS scaling factors for key mineral producers ===")
    for iso in ["COD", "GIN", "ZAF", "ZMB", "MLI", "MRT", "TZA", "GHA",
                "BFA", "LBR", "SLE", "CHL", "PER", "AUS", "BRA", "CHN", "USA"]:
        rows = out[(out["iso3"] == iso) & (out["category"] == "minerals")]
        if rows.empty:
            continue
        for _, r in rows.iterrows():
            print(f"  {iso} minerals: scale={r['scale']:.2f}  ({r['source_group']})")


if __name__ == "__main__":
    main()
