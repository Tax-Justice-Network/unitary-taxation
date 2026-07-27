# %%
"""
3_24 — Combine WB / EIA / EITI resource-rent measures into one panel.

Combine three resource-rent measures into a single panel for cross-comparison.

Sources joined per (iso3, year, category):
  - WB    commodity rents in USD
  - EIA   production volumes (priced with the calibrated rent fractions)
  - EITI  rent estimate computed from EITI production

Categories: oil_gas, coal, minerals (forest excluded — not in carve-out scope).

Years: 2016-2023 (with 2021-2022 the highest-priority comparison years).

Best-estimate hierarchy (configurable BEST_PRIORITY below):
  oil_gas:  EITI > EIA > WB
  coal:     EITI > EIA > WB
  minerals: EITI > WB

The priority assumes country-self-reported (EITI) > EIA-derived > WB-modeled,
because EITI uses on-the-ground volumes and African producers are the focal
case of the analysis. Switch the priority in BEST_PRIORITY if you want to
keep WB as the spine.

Pipeline: Extractive prep, stage 3_24 — after 3_23, before 3_25.

Reads:
  data/raw/extractive/wb_resource_rents.csv             — WB commodity rents in USD (3_15)
  data/raw/extractive/eia_energy_production.csv         — EIA oil/gas/coal volumes (3_16)
  data/raw/extractive/bgs_mineral_production.csv        — BGS mineral volumes (3_17)
  data/intermediate/extractive/eiti_production_clean_long.csv — EITI cleaned production (3_21)
  data/intermediate/extractive/rent_fractions_calibrated.csv  — calibrated rent fractions (3_22)
  data/intermediate/extractive/bgs_scaling_factors.csv  — BGS scaling factors (3_23)

Writes:
  data/intermediate/extractive/rents_combined_yearly.csv — iso3 x year x category, with rent_best_usd/source
  data/intermediate/extractive/rents_combined_2021_2022_wide.csv — wide pivot for 2021-2022

Usage:
  python 3_24_combined_rents.py

Author: Alison Schultz.
Created: 2026-07-17.  Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import sys
from pathlib import Path

import pandas as pd
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT
from _reference_prices import (
    BRENT_USD_BBL, HENRY_HUB_USD_MMBTU, COAL_AUS_USD_T,
    MINERAL_PRICES, HS_PRICE_UNIT, MINERAL_VOL_TO_PRICE_MULT,
    RENT_FRAC_DEFAULT,
)

# %% MARK: 2. Config and constants
OUT_LONG = EXT_INT / "rents_combined_yearly.csv"
OUT_WIDE_2122 = EXT_INT / "rents_combined_2021_2022_wide.csv"

YEARS = list(range(2016, 2024))
CATEGORIES = ["oil_gas", "coal", "minerals"]

# Priority order per category (first non-null wins)
BEST_PRIORITY = {
    "oil_gas":  ["eiti", "eia", "wb"],
    "coal":     ["eiti", "eia", "bgs", "wb"],
    "minerals": ["eiti", "bgs", "wb"],
}


# %% MARK: 3. Calibration lookups
def _yearly_lookup(table, year):
    if year in table:
        return table[year]
    available = sorted(table.keys())
    if year < available[0]:
        return table[available[0]]
    return table[available[-1]]


def load_calibrated_rent_fractions() -> pd.DataFrame:
    """Read 3_22 output. Returns DataFrame with iso3, category, rent_fraction,
    source_group. Falls back to empty DataFrame if file missing."""
    fp = EXT_INT / "rent_fractions_calibrated.csv"
    if not fp.exists():
        print("  [warn] rent_fractions_calibrated.csv missing; falling back "
              "to flat defaults. Run 3_22_calibrate_rent_fractions.py first.")
        return pd.DataFrame(columns=["iso3", "category", "rent_fraction",
                                     "source_group", "n_cells"])
    return pd.read_csv(fp)


def load_bgs_scaling_factors() -> dict:
    """Read 3_23 output. Returns dict mapping (iso3, category) -> (scale,
    source_label). Falls back to identity (1.0) if file missing."""
    fp = EXT_INT / "bgs_scaling_factors.csv"
    if not fp.exists():
        print("  [warn] bgs_scaling_factors.csv missing; BGS rents will not "
              "be scaled to WB level. Run 3_23_calibrate_bgs_scaling.py first.")
        return {}
    df = pd.read_csv(fp)
    return {(r["iso3"], r["category"]): (float(r["scale"]), str(r["source_group"]))
            for _, r in df.iterrows()}


def get_rent_fraction(iso3: str, category: str, calib_lookup: dict) -> tuple:
    """Look up the calibrated rent fraction for (iso3, category). Returns
    (rent_fraction, source_label). Falls back to flat default if missing."""
    rec = calib_lookup.get((iso3, category))
    if rec is not None:
        return float(rec["rent_fraction"]), str(rec["source_group"])
    return RENT_FRAC_DEFAULT.get(category, 0.40), "flat_default"


def get_bgs_scale(iso3: str, category: str, bgs_scale_lookup: dict) -> tuple:
    """Look up the BGS scaling factor for (iso3, category). Returns
    (scale, source_label). Falls back to 1.0 (no scaling) if missing."""
    rec = bgs_scale_lookup.get((iso3, category))
    if rec is not None:
        return rec
    return 1.0, "no_scale"


# %% MARK: 4. Source rent loaders
# ─────────────────────── WB rents ──────────────────────────────────────────
def load_wb_rents() -> pd.DataFrame:
    print("Loading WB rents...")
    wb = pd.read_csv(RAW / "extractive" / "wb_resource_rents.csv")
    wb = wb[wb["year"].between(YEARS[0], YEARS[-1])].copy()
    wb["iso3"] = wb["country_iso3"].astype(str).str.upper()

    # WB exposes per-commodity rents in USD. Aggregate to our 3 categories
    # (forest dropped intentionally — not in carve-out base).
    wb["wb_oil_gas_rents_usd"] = wb[["oil_rents_usd", "gas_rents_usd"]].sum(
        axis=1, min_count=1
    )
    wb["wb_coal_rents_usd"] = wb["coal_rents_usd"]
    wb["wb_minerals_rents_usd"] = wb["mineral_rents_usd"]

    keep = [
        "iso3", "year",
        "wb_oil_gas_rents_usd", "wb_coal_rents_usd", "wb_minerals_rents_usd",
        "total_rents_pct_gdp",
    ]
    wb = wb[keep]

    # Pivot to (iso3, year, category)
    long = wb.melt(
        id_vars=["iso3", "year", "total_rents_pct_gdp"],
        value_vars=["wb_oil_gas_rents_usd", "wb_coal_rents_usd",
                    "wb_minerals_rents_usd"],
        var_name="cat_col",
        value_name="rent_wb_usd",
    )
    long["category"] = long["cat_col"].str.replace(
        "wb_", ""
    ).str.replace("_rents_usd", "")
    long["category"] = long["category"].replace({"oil_gas": "oil_gas",
                                                  "coal": "coal",
                                                  "minerals": "minerals"})
    long["wb_published"] = long["rent_wb_usd"].notna()
    long = long[["iso3", "year", "category", "rent_wb_usd", "wb_published"]]
    return long


# ─────────────────────── EIA rents (computed with calibrated rf) ──────────
def load_eia_rents(calib_lookup: dict) -> pd.DataFrame:
    print("Loading EIA energy production -> rent estimate...")
    eia_raw = pd.read_csv(RAW / "extractive" / "eia_energy_production.csv")

    # Compute annual revenue per (iso3, year, fuel)
    rows = []
    for _, r in eia_raw.iterrows():
        year = int(r["year"])
        fuel = r["fuel"]
        prod = r["production"]
        unit = r["unit"]
        if pd.isna(prod) or prod <= 0:
            continue

        if fuel == "crude_oil_lease_condensate" and unit == "thousand_barrels_per_day":
            # kbbl/d -> annual barrels
            barrels = prod * 1000 * 365
            price = _yearly_lookup(BRENT_USD_BBL, year)
            revenue = barrels * price
            cat = "oil_gas"
        elif fuel == "natural_gas_dry" and unit == "billion_cubic_feet":
            # 1 BCF ~= 1.037e6 MMBtu (1037 BTU/scf typical)
            mmbtu = prod * 1.037e6
            price = _yearly_lookup(HENRY_HUB_USD_MMBTU, year)
            revenue = mmbtu * price
            cat = "oil_gas"
        elif fuel == "coal_total" and unit == "thousand_tonnes":
            tonnes = prod * 1000
            price = _yearly_lookup(COAL_AUS_USD_T, year)
            revenue = tonnes * price
            cat = "coal"
        else:
            # Skip the disaggregated coal subtypes (anthracite/bituminous/
            # lignite) since coal_total already covers the whole sum.
            continue

        rows.append({
            "iso3": r["iso3"],
            "year": year,
            "category": cat,
            "eia_revenue_usd": revenue,
            "eia_unit_price": price,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["iso3", "year", "category",
                                     "rent_eia_usd", "eia_revenue_usd",
                                     "eia_unit_price"])
    # Combine oil + gas revenue for each (iso3, year)
    grouped = (
        df.groupby(["iso3", "year", "category"], as_index=False)
        .agg(
            eia_revenue_usd=("eia_revenue_usd", "sum"),
            eia_unit_price=("eia_unit_price", "mean"),
        )
    )
    rfs = grouped.apply(
        lambda r: get_rent_fraction(r["iso3"], r["category"], calib_lookup),
        axis=1, result_type="expand",
    )
    rfs.columns = ["eia_rent_fraction", "eia_rf_source"]
    grouped = pd.concat([grouped, rfs], axis=1)
    grouped["rent_eia_usd"] = (
        grouped["eia_revenue_usd"] * grouped["eia_rent_fraction"]
    )
    return grouped


# ─────────────────────── EITI rents (computed with calibrated rf) ──────────
def load_eiti_rents(calib_lookup: dict) -> pd.DataFrame:
    """Compute EITI-derived rent estimates from the cleaned production panel.

    Uses the `gross_revenue_usd` blend built by 3_21_eiti_to_clean_panel.py —
    reported value (USD or local×FX) where the EITI report disclosed one,
    else volume × reference price — summed per (iso3, year, category), then
    multiplied by the calibrated country-level rent fraction from 3_22.
    """
    print("Loading EITI clean panel -> rent estimate (gross-revenue blend × calibrated rf)...")
    fp = EXT_INT / "eiti_production_clean_long.csv"
    if not fp.exists():
        print(f"  [warn] {fp} not present; skipping EITI rent.")
        return pd.DataFrame(columns=["iso3", "year", "category",
                                     "rent_eiti_usd", "eiti_n_commodities",
                                     "eiti_commodity_list"])
    eiti = pd.read_csv(fp)
    eiti["hs_code"] = eiti["hs_code"].astype(str).str.strip()
    eiti = eiti[
        eiti["category"].isin(CATEGORIES)
        & eiti["gross_revenue_usd"].gt(0)
        & eiti["year"].between(YEARS[0], YEARS[-1])
    ].copy()
    if eiti.empty:
        return pd.DataFrame(columns=["iso3", "year", "category",
                                     "rent_eiti_usd", "eiti_n_commodities",
                                     "eiti_commodity_list"])

    grouped = (
        eiti.groupby(["iso3", "year", "category"], as_index=False)
        .agg(
            eiti_revenue_usd=("gross_revenue_usd", "sum"),
            eiti_n_commodities=("commodity_name_canonical", "nunique"),
            eiti_commodity_list=(
                "commodity_name_canonical",
                lambda s: ", ".join(sorted(set(str(x) for x in s)))
            ),
        )
    )
    rfs = grouped.apply(
        lambda r: get_rent_fraction(r["iso3"], r["category"], calib_lookup),
        axis=1, result_type="expand",
    )
    rfs.columns = ["eiti_rent_fraction", "eiti_rf_source"]
    grouped = pd.concat([grouped, rfs], axis=1)
    grouped["rent_eiti_usd"] = (
        grouped["eiti_revenue_usd"] * grouped["eiti_rent_fraction"]
    )
    return grouped


# ─────────────────────── BGS rents (calibrated rf + WB-aligned scale) ─────
def load_bgs_rents(calib_lookup: dict, bgs_scale_lookup: dict) -> pd.DataFrame:
    """Compute BGS-derived rent estimates from the cleaned production panel,
    applying the calibrated country-level rent fraction.

    Reads data/raw/extractive/bgs_mineral_production.csv (produced by
    3_17_pull_bgs_minerals.py) and pipes mineral-commodity volumes through the
    same MINERAL_PRICES + MINERAL_VOL_TO_PRICE_MULT used by load_eiti_rents.

    BGS coverage:
      - All BGS implementing reporters (200+ countries) for the priced mineral
        commodities (HS 2510, 2601-2617, 7102/7106/7108/7110)
      - Mostly minerals; some coal records also pass through HS 2701 -> coal
      - Years 2016-2023 in our extract
    """
    print("Loading BGS mineral production -> rent estimate (calibrated rf)...")
    fp = RAW / "extractive" / "bgs_mineral_production.csv"
    if not fp.exists():
        print(f"  [warn] {fp} not present; skipping BGS rent.")
        return pd.DataFrame(columns=["iso3", "year", "category",
                                     "rent_bgs_usd", "bgs_n_commodities",
                                     "bgs_commodity_list"])
    bgs = pd.read_csv(fp)
    # hs_code is loaded as float (e.g. 7108.0) because empty strings get
    # treated as NaN; coerce to int-string ("7108") and drop empties.
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
        & bgs["year"].between(YEARS[0], YEARS[-1])
    ].copy()

    # Coal HS-codes get coal category; everything else mineral
    bgs["category"] = np.where(
        bgs["hs_code"].isin(["2701", "2702"]), "coal", "minerals"
    )

    rev_rows = []
    for _, r in bgs.iterrows():
        hs = r["hs_code"]
        cat = r["category"]
        year = int(r["year"])
        if cat == "coal":
            # BGS reports coal in tonnes; price in USD/t
            if str(r["unit"]).strip().lower() not in (
                "tonnes", "thousand tonnes", "metric tonnes", "tonne", "ton"
            ):
                continue
            mult = 1000.0 if "thousand" in str(r["unit"]).lower() else 1.0
            rev = r["production"] * mult * _yearly_lookup(COAL_AUS_USD_T, year)
        else:
            if hs not in MINERAL_PRICES:
                continue
            unit = str(r["unit"]).strip()
            price_unit = HS_PRICE_UNIT.get(hs)
            # BGS unit strings include trailing notes like "tonnes (gross
            # weight)" or "kilograms (metal content)" -- normalize.
            unit_lc = unit.lower()
            if unit_lc.startswith("tonnes") or unit_lc.startswith("metric tonnes"):
                canon_unit, mult = "tonnes", 1.0
            elif unit_lc.startswith("kilograms") or unit_lc.startswith("kg"):
                canon_unit, mult = "tonnes", 0.001
            elif unit_lc.startswith("carats"):
                canon_unit, mult = "carats", 1.0
            elif unit_lc.startswith("ounces") or unit_lc == "oz":
                canon_unit, mult = "tonnes", 3.11034768e-5
            else:
                continue
            converter = MINERAL_VOL_TO_PRICE_MULT.get((canon_unit, price_unit))
            if converter is None:
                continue
            price = MINERAL_PRICES[hs].get(year)
            if price is None:
                continue
            rev = r["production"] * mult * converter * price
        rev_rows.append({
            "iso3": r["iso3"], "year": year, "category": cat,
            "commodity": r["commodity"],
            "revenue_usd": rev,
        })

    rev_df = pd.DataFrame(rev_rows)
    if rev_df.empty:
        return pd.DataFrame(columns=["iso3", "year", "category",
                                     "rent_bgs_usd", "bgs_n_commodities",
                                     "bgs_commodity_list"])

    grouped = (
        rev_df.groupby(["iso3", "year", "category"], as_index=False)
        .agg(
            bgs_revenue_usd=("revenue_usd", "sum"),
            bgs_n_commodities=("commodity", "nunique"),
            bgs_commodity_list=(
                "commodity",
                lambda s: ", ".join(sorted(set(str(x) for x in s)))
            ),
        )
    )
    rfs = grouped.apply(
        lambda r: get_rent_fraction(r["iso3"], r["category"], calib_lookup),
        axis=1, result_type="expand",
    )
    rfs.columns = ["bgs_rent_fraction", "bgs_rf_source"]
    grouped = pd.concat([grouped, rfs], axis=1)

    # Apply per-country BGS-vs-WB scaling so BGS-derived rent magnitude
    # aligns with WB's published level on overlap years. The scale corrects
    # for the gap between our HS-mapped commodity subset and WB's bundled
    # mineral_rents (which lumps every mineral). See 3_23 for calibration.
    scales = grouped.apply(
        lambda r: get_bgs_scale(r["iso3"], r["category"], bgs_scale_lookup),
        axis=1, result_type="expand",
    )
    scales.columns = ["bgs_scale", "bgs_scale_source"]
    grouped = pd.concat([grouped, scales], axis=1)
    grouped["rent_bgs_usd"] = (
        grouped["bgs_revenue_usd"]
        * grouped["bgs_rent_fraction"]
        * grouped["bgs_scale"]
    )
    return grouped


# %% MARK: 5. Merge and best-estimate
# ─────────────────────── Merge & best-estimate ─────────────────────────────
def main():
    print("Loading calibrated rent fractions...")
    calib = load_calibrated_rent_fractions()
    calib_lookup = {(r["iso3"], r["category"]): r for _, r in calib.iterrows()}
    print(f"  {len(calib_lookup)} (iso3, category) entries")

    print("Loading BGS scaling factors...")
    bgs_scale_lookup = load_bgs_scaling_factors()
    print(f"  {len(bgs_scale_lookup)} (iso3, category) BGS scale entries")

    wb = load_wb_rents()
    eia = load_eia_rents(calib_lookup)
    eiti = load_eiti_rents(calib_lookup)
    bgs = load_bgs_rents(calib_lookup, bgs_scale_lookup)

    # Build the union of (iso3, year, category) keys present in any source
    keys = pd.concat([
        wb[["iso3", "year", "category"]],
        eia[["iso3", "year", "category"]],
        eiti[["iso3", "year", "category"]],
        bgs[["iso3", "year", "category"]],
    ]).drop_duplicates().reset_index(drop=True)

    out = (
        keys.merge(wb, on=["iso3", "year", "category"], how="left")
        .merge(eia, on=["iso3", "year", "category"], how="left")
        .merge(eiti, on=["iso3", "year", "category"], how="left")
        .merge(bgs, on=["iso3", "year", "category"], how="left")
    )
    out = out[out["year"].between(YEARS[0], YEARS[-1])].copy()

    # ── Sanity filter on derived rent estimates ──
    # EITI / BGS values come from XLSX volumes that occasionally have
    # source-side unit mislabels (gold reported as "Tonnes" when the unit is
    # actually grams or kilograms; gas reported in Scf instead of Sm3) or
    # decimal-separator confusion. These produce rent estimates that are
    # orders of magnitude too high.
    #
    # Rules (a row is dropped if ANY fires):
    #   1. Absolute ceiling: rent_<src> > ABSOLUTE_CEILING_USD per (iso, year,
    #      category). No extractive sector for any category-year-country has
    #      ever exceeded this; values above are almost certainly unit bugs.
    #   2. Cross-source HIGH ratio: rent_<src> exceeds SANITY_RATIO_HIGH × WB
    #      rent AND value > MIN_TRIGGER_USD. The min-trigger prevents dropping
    #      legitimate "fake zero" fixes for under-counted small economies
    #      (LBR iron ore, MRT iron ore, GIN bauxite where WB undercounts).
    #   3. Cross-source LOW ratio: rent_<src> is below SANITY_RATIO_LOW × WB
    #      rent AND WB itself is substantial (> MIN_WB_FOR_LOW_USD). Catches
    #      scale-parse bugs that make a source 20×+ too small (e.g. an EITI
    #      report tabulated "in thousands" — Ecuador crude — read literally).
    #      Safe vs the fake-zero fixes because those make the source LARGER
    #      than WB, never smaller.
    SANITY_RATIO_HIGH = 20.0
    MIN_TRIGGER_USD = 50.0e9      # high-side: only filter cells > $50B
    ABSOLUTE_CEILING_USD = 600.0e9  # $600B per (iso, year, cat)
    SANITY_RATIO_LOW = 0.05       # low-side: drop if < 5% of WB's published rent
    MIN_WB_FOR_LOW_USD = 100.0e6  # low-side: only when WB rent itself > $100M
    # SAU oil_gas peaked at ~$360B in 2022 high-price year and CHN coal
    # similarly peaked around ~$320B; ceiling at $600B leaves headroom while
    # still catching the trillion-scale unit-mislabel bugs.

    out = out.sort_values(["iso3", "category", "year"]).reset_index(drop=True)
    out["wb_for_check"] = out["rent_wb_usd"]
    out["wb_for_check"] = out.groupby(["iso3", "category"])["wb_for_check"].transform(
        lambda s: s.where(s.notna() & (s > 0), s.dropna().median()
                          if s.notna().any() else np.nan)
    )
    # The low-side check only trusts an actually-published WB value (not the
    # median fallback), to avoid dropping a source against a guessed benchmark.
    out["wb_published_for_low"] = out["rent_wb_usd"].where(out["rent_wb_usd"].notna()
                                                           & (out["rent_wb_usd"] > 0))

    n_filtered = {"eiti": 0, "bgs": 0, "eia": 0}
    for src in ("eiti", "bgs", "eia"):
        col = f"rent_{src}_usd"
        if col not in out.columns:
            continue
        absolute_bad = out[col].notna() & (out[col] > ABSOLUTE_CEILING_USD)
        cross_high = (
            out["wb_for_check"].notna()
            & (out["wb_for_check"] > 0)
            & out[col].notna()
            & (out[col] > MIN_TRIGGER_USD)
            & (out[col] > SANITY_RATIO_HIGH * out["wb_for_check"])
        )
        cross_low = (
            out["wb_published_for_low"].notna()
            & (out["wb_published_for_low"] > MIN_WB_FOR_LOW_USD)
            & out[col].notna()
            & (out[col] > 0)
            & (out[col] < SANITY_RATIO_LOW * out["wb_published_for_low"])
        )
        bad = cross_high | cross_low | absolute_bad
        if bad.any():
            n_filtered[src] = int(bad.sum())
            for _, r in out[bad][["iso3", "year", "category", col, "wb_for_check"]].iterrows():
                wb_v = r["wb_for_check"]
                wb_str = (f"{wb_v/1e9:.2f}B" if pd.notna(wb_v) else "n/a")
                print(f"    [sanity-drop] {src.upper():<4s} {r['iso3']} "
                      f"{int(r['year'])} {r['category']:<10s} "
                      f"value=${r[col]/1e9:,.3f}B  WB-bench={wb_str}")
            out.loc[bad, col] = np.nan
    out = out.drop(columns="wb_published_for_low")
    print(f"  sanity filter dropped: "
          f"{n_filtered['eiti']} EITI, {n_filtered['bgs']} BGS, "
          f"{n_filtered['eia']} EIA cells")
    out = out.drop(columns="wb_for_check")
    out = out.sort_values(["iso3", "year", "category"]).reset_index(drop=True)

    # Best-estimate selection
    def pick_best(row):
        cat = row["category"]
        order = BEST_PRIORITY.get(cat, ["wb"])
        for src in order:
            col = f"rent_{src}_usd"
            if col not in row:
                continue
            v = row[col]
            if pd.notna(v) and v > 0:
                return pd.Series({"rent_best_usd": v, "rent_best_source": src.upper()})
        return pd.Series({"rent_best_usd": np.nan, "rent_best_source": "MISSING"})

    print("Selecting best estimate per (iso3, year, category)...")
    best = out.apply(pick_best, axis=1)
    out = pd.concat([out, best], axis=1)

    out = out.sort_values(["iso3", "year", "category"]).reset_index(drop=True)

    # ── Carry forward / backward within (iso3, category) ──
    # When a country has rent data in some years but a gap in others (most
    # importantly 2022 for mineral producers like GIN, UGA, MDG, ETH whose
    # EITI templates haven't been released yet), the best-estimate gap is
    # filled from the nearest available year. Tag the carried rows so
    # downstream tables can show provenance.
    out["rent_best_source"] = out["rent_best_source"].fillna("MISSING").astype(str)
    is_missing = out["rent_best_usd"].isna() | (out["rent_best_usd"] <= 0)

    # ffill then bfill within country-category
    out_sorted = out.sort_values(["iso3", "category", "year"]).copy()
    out_sorted["rent_best_carry_fwd_usd"] = (
        out_sorted.groupby(["iso3", "category"])["rent_best_usd"]
        .transform(lambda s: s.where(s > 0).ffill())
    )
    out_sorted["rent_best_source_carry_fwd"] = (
        out_sorted.groupby(["iso3", "category"])["rent_best_source"]
        .transform(lambda s: s.where(s != "MISSING").ffill())
    )
    out_sorted["rent_best_carry_any_usd"] = (
        out_sorted.groupby(["iso3", "category"])["rent_best_carry_fwd_usd"]
        .transform(lambda s: s.bfill())
    )
    out_sorted["rent_best_source_carry_any"] = (
        out_sorted.groupby(["iso3", "category"])["rent_best_source_carry_fwd"]
        .transform(lambda s: s.bfill())
    )
    out = out_sorted.sort_index()

    # Apply the carried value where the original was missing/zero, tagging
    # source as "<orig>:carry_fwd" or "<orig>:carry_bwd".
    n_fwd = ((out["rent_best_usd"].isna() | (out["rent_best_usd"] <= 0))
             & out["rent_best_carry_fwd_usd"].gt(0)).sum()
    n_bwd = ((out["rent_best_usd"].isna() | (out["rent_best_usd"] <= 0))
             & out["rent_best_carry_fwd_usd"].isna()
             & out["rent_best_carry_any_usd"].gt(0)).sum()
    print(f"  carry-fwd filled {n_fwd} cells; carry-bwd filled {n_bwd} cells")

    fwd_mask = (
        (out["rent_best_usd"].isna() | (out["rent_best_usd"] <= 0))
        & out["rent_best_carry_fwd_usd"].gt(0)
    )
    out.loc[fwd_mask, "rent_best_usd"] = out.loc[fwd_mask, "rent_best_carry_fwd_usd"]
    out.loc[fwd_mask, "rent_best_source"] = (
        out.loc[fwd_mask, "rent_best_source_carry_fwd"].astype(str) + ":carry_fwd"
    )

    bwd_mask = (
        (out["rent_best_usd"].isna() | (out["rent_best_usd"] <= 0))
        & out["rent_best_carry_any_usd"].gt(0)
    )
    out.loc[bwd_mask, "rent_best_usd"] = out.loc[bwd_mask, "rent_best_carry_any_usd"]
    out.loc[bwd_mask, "rent_best_source"] = (
        out.loc[bwd_mask, "rent_best_source_carry_any"].astype(str) + ":carry_bwd"
    )

    out = out.drop(columns=[
        "rent_best_carry_fwd_usd", "rent_best_carry_any_usd",
        "rent_best_source_carry_fwd", "rent_best_source_carry_any",
    ])
    out = out.sort_values(["iso3", "year", "category"]).reset_index(drop=True)

    cols = [
        "iso3", "year", "category",
        "rent_wb_usd", "rent_eia_usd", "rent_eiti_usd", "rent_bgs_usd",
        "rent_best_usd", "rent_best_source",
        "wb_published", "eia_revenue_usd", "eia_unit_price",
        "eia_rent_fraction", "eia_rf_source",
        "eiti_revenue_usd", "eiti_rent_fraction", "eiti_rf_source",
        "eiti_n_commodities", "eiti_commodity_list",
        "bgs_revenue_usd", "bgs_rent_fraction", "bgs_rf_source",
        "bgs_scale", "bgs_scale_source",
        "bgs_n_commodities", "bgs_commodity_list",
    ]
    for c in cols:
        if c not in out.columns:
            out[c] = np.nan
    out[cols].to_csv(OUT_LONG, index=False)
    print(f"Wrote {len(out):,} rows -> {OUT_LONG}")

    # Wide pivoted view for 2021-2022 for quick eyeballing
    pri = out[out["year"].isin([2021, 2022])].copy()
    pri["rent_best_billion_usd"] = (pri["rent_best_usd"] / 1e9).round(2)
    pri["rent_wb_billion_usd"] = (pri["rent_wb_usd"] / 1e9).round(2)
    pri["rent_eia_billion_usd"] = (pri["rent_eia_usd"] / 1e9).round(2)
    pri["rent_eiti_billion_usd"] = (pri["rent_eiti_usd"] / 1e9).round(2)
    wide_cols = [
        "iso3", "year", "category",
        "rent_wb_billion_usd", "rent_eia_billion_usd", "rent_eiti_billion_usd",
        "rent_best_billion_usd", "rent_best_source",
        "eiti_n_commodities", "eiti_commodity_list",
    ]
    pri[wide_cols].to_csv(OUT_WIDE_2122, index=False)
    print(f"Wrote {len(pri):,} rows -> {OUT_WIDE_2122}")

    # Summary: how many cells get filled by each source for 2021-2022
    print("\n=== Best-source mix for 2021-2022 ===")
    for yr in (2021, 2022):
        for catname in CATEGORIES:
            cell = pri[(pri["year"] == yr) & (pri["category"] == catname)]
            counts = cell["rent_best_source"].value_counts().to_dict()
            print(f"  {yr} {catname:<10s}  {counts}")

    # Eyeball table for our priority African producers
    print("\n=== African producers, 2021-2022, $bn ===")
    afr = ["NGA", "AGO", "DZA", "EGY", "LBY", "GHA", "COG", "GAB", "TCD",
           "CIV", "CMR", "EQG", "SSD", "GIN", "LBR", "COD", "MOZ", "MRT",
           "MLI", "BFA", "TZA", "ZMB", "ZAF", "MDG", "SEN", "TGO", "UGA"]
    spot = pri[pri["iso3"].isin(afr)].copy()
    show_cols = [
        "iso3", "year", "category",
        "rent_wb_billion_usd", "rent_eia_billion_usd", "rent_eiti_billion_usd",
        "rent_best_billion_usd", "rent_best_source",
    ]
    print(spot[show_cols].sort_values(
        ["iso3", "year", "category"]
    ).to_string(index=False))


if __name__ == "__main__":
    main()
