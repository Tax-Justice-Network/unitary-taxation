"""
Calibrate country-specific rent fractions empirically from the WB Resource
Rents indicator. Replaces the hardcoded RENT_FRACTION tables in
2_8_eiti_rent_estimate.py and 2_9_combined_rents.py with country-level
fractions reverse-engineered from WB's own (presumably country-specific
cost-curve) rent series 2016-2021.

For each (iso3, year, commodity):
    implied_rf = WB_rent[iso, c, y] / (volume[iso, c, y] × world_ref_price[c, y])

Sources of volume:
  - oil_gas / coal: EIA International Energy Statistics
  - minerals:       EITI cleaned production panel (HS-coded per commodity)

Then aggregated with the fallback hierarchy you asked for:
    1. Country median across 2016-2021 (need >= 2 cells)
    2. Region × IncomeGroup median (fine)
    3. Region median
    4. IncomeGroup median
    5. Global commodity median

Output:
    data/final/rent_fractions_calibrated.csv
      iso3, commodity, rent_fraction, source_group, n_cells

Country-classification source: data/raw/Metadata_Country_API_GC.TAX.TOTL.GD.ZS_*.csv
(WB's own Region + IncomeGroup classification).

Caveats baked into the methodology:
  - WB itself uses a global commodity price × country-modelled cost. Calibrating
    against WB inherits whatever country-specificity is in WB's underlying cost
    series. We saw empirically this varies meaningfully: SAU ~0.76, USA ~0.15,
    AGO ~0.61. So country-specific is real, not uniform.
  - Outlier filter (0.05 <= rf <= 1.0) drops cases where WB and EIA volumes
    materially disagree (e.g. MMR shows rf > 1.0; WB likely uses different
    volumes than EIA).
  - For minerals, the implied rf depends on our embedded HS-code prices, which
    are themselves approximate. So mineral rent fractions are noisier than
    oil/gas/coal.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT
from _reference_prices import (
    BRENT_USD_BBL, HENRY_HUB_USD_MMBTU, COAL_AUS_USD_T,
    MINERAL_PRICES, HS_PRICE_UNIT,
    MINERAL_VOL_TO_PRICE_MULT as MINERAL_VOLUME_TO_PRICE_UNIT,
)

OUT_PATH = EXT_INT / "rent_fractions_calibrated.csv"


def load_classification() -> pd.DataFrame:
    """Read WB country classification (Region + IncomeGroup) from raw metadata."""
    fp = RAW / "Metadata_Country_macro_variables/wb_tax_revenue_pct_gdp_2026-04.csv"
    if not fp.exists():
        # fallback: fewer countries
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


def compute_eia_revenue() -> pd.DataFrame:
    """Annual revenue from EIA volumes for oil_gas and coal categories."""
    eia = pd.read_csv(RAW / "resources" / "eia_energy_production.csv")
    eia = eia[eia["year"].between(2016, 2021)].copy()

    rows = []
    for _, r in eia.iterrows():
        year = int(r["year"])
        prod = r["production"]
        if pd.isna(prod) or prod <= 0:
            continue
        if r["fuel"] == "crude_oil_lease_condensate":
            rev = prod * 1000 * 365 * BRENT_USD_BBL.get(year, np.nan)
            cat, kind = "oil_gas", "oil"
        elif r["fuel"] == "natural_gas_dry":
            rev = prod * 1.037e6 * HENRY_HUB_USD_MMBTU.get(year, np.nan)
            cat, kind = "oil_gas", "gas"
        elif r["fuel"] == "coal_total":
            rev = prod * 1000 * COAL_AUS_USD_T.get(year, np.nan)
            cat, kind = "coal", "coal"
        else:
            continue
        if pd.notna(rev) and rev > 0:
            rows.append({"iso3": r["iso3"], "year": year, "category": cat,
                         "kind": kind, "revenue_usd": rev})
    df = pd.DataFrame(rows)
    return df.groupby(["iso3", "year", "category"], as_index=False)["revenue_usd"].sum()


def compute_eiti_minerals_revenue() -> pd.DataFrame:
    """Annual minerals revenue per (iso3, year): the gross_revenue_usd blend
    (reported value where available, else volume × reference price) summed
    over the EITI-reported HS codes. Built by 2_7_eiti_to_clean_panel.py —
    we just sum it here so the rent fractions are calibrated against the
    same revenue series the rent estimate uses."""
    eiti = pd.read_csv(EXT_INT / "eiti_production_clean_long.csv")
    eiti = eiti[
        eiti["category"].eq("minerals")
        & eiti["gross_revenue_usd"].gt(0)
        & eiti["year"].between(2016, 2021)
    ].copy()
    if eiti.empty:
        return pd.DataFrame(columns=["iso3", "year", "category", "revenue_usd"])
    g = eiti.groupby(["iso3", "year"], as_index=False)["gross_revenue_usd"].sum()
    g = g.rename(columns={"gross_revenue_usd": "revenue_usd"})
    g["category"] = "minerals"
    return g[["iso3", "year", "category", "revenue_usd"]]


def main():
    print("Loading inputs...")
    wb = pd.read_csv(RAW / "resources" / "wb_resource_rents.csv")
    wb = wb[wb["year"].between(2016, 2021)].copy()
    wb["iso3"] = wb["country_iso3"].astype(str).str.upper()
    wb["wb_oil_gas_rent"] = wb[["oil_rents_usd", "gas_rents_usd"]].sum(axis=1, min_count=1)
    wb["wb_coal_rent"] = wb["coal_rents_usd"]
    wb["wb_minerals_rent"] = wb["mineral_rents_usd"]

    classif = load_classification()
    print(f"  {len(classif)} countries with region/income classification")

    # Revenue per (iso3, year, category)
    eia_rev = compute_eia_revenue()
    eiti_rev = compute_eiti_minerals_revenue()
    revenue = pd.concat([eia_rev, eiti_rev], ignore_index=True)
    print(f"  {len(revenue)} (iso3, year, category) revenue cells")

    # Map WB rent per category onto the revenue cells
    wb_long = wb.melt(
        id_vars=["iso3", "year"],
        value_vars=["wb_oil_gas_rent", "wb_coal_rent", "wb_minerals_rent"],
        var_name="cat_col", value_name="wb_rent",
    )
    wb_long["category"] = wb_long["cat_col"].str.replace("wb_", "").str.replace("_rent", "")
    wb_long = wb_long.drop(columns="cat_col")

    df = revenue.merge(wb_long, on=["iso3", "year", "category"], how="inner")
    df = df[df["revenue_usd"] > 0]
    df = df[df["wb_rent"] > 0]
    df["implied_rf"] = df["wb_rent"] / df["revenue_usd"]

    # Outlier filter
    n_before = len(df)
    df = df[df["implied_rf"].between(0.05, 1.0)]
    print(f"  {len(df):,} cells after outlier filter (dropped {n_before - len(df)})")

    # ── Aggregate with fallback hierarchy ──
    # 1. Country median (need >= 2 years)
    country = (
        df.groupby(["iso3", "category"], as_index=False)
        .agg(rf=("implied_rf", "median"), n=("implied_rf", "size"))
    )
    country = country[country["n"] >= 2].copy()
    country["source_group"] = "country"

    # Attach region+income for grouping
    df_g = df.merge(classif, on="iso3", how="left")

    # 2. Region × IncomeGroup median
    rxi = (
        df_g.dropna(subset=["region", "income_group"])
        .groupby(["region", "income_group", "category"], as_index=False)
        .agg(rf=("implied_rf", "median"), n=("implied_rf", "size"))
    )
    # 3. Region median
    reg = (
        df_g.dropna(subset=["region"])
        .groupby(["region", "category"], as_index=False)
        .agg(rf=("implied_rf", "median"), n=("implied_rf", "size"))
    )
    # 4. Income median
    inc = (
        df_g.dropna(subset=["income_group"])
        .groupby(["income_group", "category"], as_index=False)
        .agg(rf=("implied_rf", "median"), n=("implied_rf", "size"))
    )
    # 5. Global median
    glob = (
        df.groupby("category", as_index=False)
        .agg(rf=("implied_rf", "median"), n=("implied_rf", "size"))
    )

    print("\n=== Group medians by category ===")
    for cat in ("oil_gas", "coal", "minerals"):
        g = glob[glob["category"] == cat]
        if not g.empty:
            print(f"  {cat:<10s} global median: {g.iloc[0]['rf']:.3f} (n={g.iloc[0]['n']})")

    print("\n=== Region medians (oil_gas) ===")
    for _, r in reg[reg["category"] == "oil_gas"].sort_values("rf", ascending=False).iterrows():
        print(f"  {r['region'][:32]:<32s}  rf={r['rf']:.3f} (n={r['n']})")
    print("\n=== Income medians (oil_gas) ===")
    for _, r in inc[inc["category"] == "oil_gas"].sort_values("rf", ascending=False).iterrows():
        print(f"  {r['income_group'][:25]:<25s}  rf={r['rf']:.3f} (n={r['n']})")

    # ── Build final lookup table ──
    # For every (iso3, category) we want a rent fraction. Walk the universe of
    # iso3s that appear in classification OR in country_table OR have any data.
    iso_universe = set(classif["iso3"].dropna()) | set(country["iso3"]) | set(df["iso3"])
    final_rows = []
    cat_set = ("oil_gas", "coal", "minerals")

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
            # 1. Country
            if (iso, cat) in country_lookup:
                r = country_lookup[(iso, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "rent_fraction": r["rf"],
                                   "source_group": "country",
                                   "n_cells": int(r["n"])})
                continue
            # 2. Region+Income
            if region and income and (region, income, cat) in rxi_lookup:
                r = rxi_lookup[(region, income, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "rent_fraction": r["rf"],
                                   "source_group": f"region+income:{region}|{income}",
                                   "n_cells": int(r["n"])})
                continue
            # 3. Region
            if region and (region, cat) in reg_lookup:
                r = reg_lookup[(region, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "rent_fraction": r["rf"],
                                   "source_group": f"region:{region}",
                                   "n_cells": int(r["n"])})
                continue
            # 4. Income
            if income and (income, cat) in inc_lookup:
                r = inc_lookup[(income, cat)]
                final_rows.append({"iso3": iso, "category": cat,
                                   "rent_fraction": r["rf"],
                                   "source_group": f"income:{income}",
                                   "n_cells": int(r["n"])})
                continue
            # 5. Global
            if cat in glob_lookup:
                r = glob_lookup[cat]
                final_rows.append({"iso3": iso, "category": cat,
                                   "rent_fraction": r["rf"],
                                   "source_group": "global",
                                   "n_cells": int(r["n"])})

    out = pd.DataFrame(final_rows)
    out.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(out):,} rows -> {OUT_PATH}")

    print("\n=== Source-group mix in final lookup ===")
    print(out["source_group"].apply(
        lambda s: s.split(":", 1)[0]
    ).value_counts().to_string())

    # Sanity: compare country-specific fractions for our key cases
    print("\n=== Calibrated rent fractions for key petroleum producers ===")
    for iso in ["LBY", "SAU", "IRQ", "ARE", "KWT", "QAT", "DZA", "IRN", "RUS",
                "NOR", "USA", "CAN", "NGA", "AGO", "GHA", "COG", "GAB", "EGY"]:
        rows = out[(out["iso3"] == iso)]
        if rows.empty:
            continue
        for _, r in rows.iterrows():
            if r["category"] == "oil_gas":
                print(f"  {iso} oil_gas: rf={r['rent_fraction']:.3f}  "
                      f"({r['source_group']})")


if __name__ == "__main__":
    main()
