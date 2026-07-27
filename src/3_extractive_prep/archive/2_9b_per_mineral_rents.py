"""
Per-mineral rent panel — the HS-code-level breakdown behind the bundled
"minerals" category in rents_combined_yearly.csv.

Run after 2_8a / 2_8b / 2_9. Reads:
  data/final/eiti_production_clean_long.csv   (EITI HS-level production volumes)
  data/raw/resources/bgs_mineral_production.csv          (BGS HS-level production volumes)
  data/final/rent_fractions_calibrated.csv     (2_8a — per-(iso, cat) rent fractions)
  data/final/bgs_scaling_factors.csv           (2_8b — per-(iso, cat) BGS→WB scale)

Writes:
  data/final/rents_per_mineral_yearly.csv      keyed (iso3, year, hs_code)

Method (mirrors the minerals path in 2_9_combined_rents.py, but keeps the
per-HS detail instead of summing it):
  - For each (iso3, year), the bundled minerals rent in 2_9 comes from a
    single source — EITI if EITI has mineral data for that cell, else BGS,
    else WB (which has no HS breakdown). This file emits the per-HS rows
    from that same winning source. WB-only cells get no per-HS rows.
  - Per HS row:
      gross_revenue_usd = volume × unit_conversion × price[hs, year]
                          (× bgs_scale[iso, "minerals"] for BGS rows)
      rent_usd          = gross_revenue_usd × rent_fraction["minerals", iso]
                          (calibrated; flat 0.30 fallback)
  - Per-HS rents are rescaled within each (iso, year) so they sum exactly
    to the validated bundled rent_minerals_usd from rents_combined_yearly.csv
    (which already applied the category-level sanity filter, captured-revenue
    floor, and carry-forward). The per-HS split therefore only sets the rate
    mix; the level comes from the validated bundled estimate. Country-years
    whose bundled minerals came from WB (no HS detail) simply have no rows
    here. No carry-forward of per-HS rows themselves.

Notes:
  - Reference price tables (MINERAL_PRICES, HS_PRICE_UNIT,
    MINERAL_VOL_TO_PRICE_MULT) come from the shared _reference_prices module
    (single source of truth, shared with 2_8a / 2_8b / 2_9).
  - No cross-source sanity filter at HS level (2_9 applies one at category
    level, and the rescale above inherits it). An absolute per-HS ceiling is
    still applied to catch gross unit bugs before the rescale.
"""

import sys
from pathlib import Path

import pandas as pd
import numpy as np

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT
from _reference_prices import (
    MINERAL_PRICES, HS_PRICE_UNIT, MINERAL_VOL_TO_PRICE_MULT,
    RENT_FRAC_DEFAULT,
)

OUT_PATH = EXT_INT / "rents_per_mineral_yearly.csv"
YEARS = list(range(2016, 2024))

RENT_FRAC_MINERALS_DEFAULT = RENT_FRAC_DEFAULT["minerals"]
# Absolute per-HS rent ceiling — catches source-side unit mislabels. No
# single (iso, year, mineral) rent should plausibly exceed this.
ABSOLUTE_CEILING_USD = 200.0e9


def _yearly_lookup(table, year):
    year = int(year)
    if year in table:
        return table[year]
    avail = sorted(table.keys())
    return table[avail[0]] if year < avail[0] else table[avail[-1]]


# ── Calibration lookups ──
def _load_calib_rent_fractions() -> dict:
    fp = EXT_INT / "rent_fractions_calibrated.csv"
    if not fp.exists():
        print("  [warn] rent_fractions_calibrated.csv missing; using flat 0.30")
        return {}
    df = pd.read_csv(fp)
    return {
        r["iso3"]: float(r["rent_fraction"])
        for _, r in df[df["category"] == "minerals"].iterrows()
        if pd.notna(r["rent_fraction"]) and float(r["rent_fraction"]) > 0
    }


def _load_bgs_scales() -> dict:
    fp = EXT_INT / "bgs_scaling_factors.csv"
    if not fp.exists():
        print("  [warn] bgs_scaling_factors.csv missing; BGS rents unscaled")
        return {}
    df = pd.read_csv(fp)
    return {
        r["iso3"]: float(r["scale"])
        for _, r in df[df["category"] == "minerals"].iterrows()
        if pd.notna(r["scale"]) and float(r["scale"]) > 0
    }


# ── Per-HS revenue from EITI ──
def _eiti_per_hs() -> pd.DataFrame:
    """Per-(iso3, year, hs_code) EITI mineral gross revenue, taken straight
    from the `gross_revenue_usd` blend in eiti_production_clean_long.csv
    (built by 2_7 — reported value where available, else volume × price).
    The cleaned file already has one row per (iso3, year, hs_code), so no
    re-aggregation is needed."""
    fp = EXT_INT / "eiti_production_clean_long.csv"
    if not fp.exists():
        print("  [warn] eiti_production_clean_long.csv missing; skipping EITI")
        return pd.DataFrame()
    eiti = pd.read_csv(fp)
    eiti["hs_code"] = eiti["hs_code"].astype(str).str.strip()
    eiti = eiti[
        (eiti["category"] == "minerals")
        & eiti["hs_code"].isin(MINERAL_PRICES.keys())
        & eiti["gross_revenue_usd"].gt(0)
        & eiti["year"].between(YEARS[0], YEARS[-1])
    ].copy()
    if eiti.empty:
        return pd.DataFrame()
    # Per-HS reference price (for the `price_usd` / `volume` columns we
    # surface — the revenue itself is the blend, which may be a reported
    # value rather than volume × price, so `volume × price_usd` won't
    # necessarily reproduce `gross_revenue_usd`).
    eiti["price_usd"] = eiti.apply(
        lambda r: MINERAL_PRICES.get(r["hs_code"], {}).get(int(r["year"])), axis=1
    )
    out = eiti[[
        "iso3", "year", "hs_code", "commodity_name_canonical",
        "volume_total", "volume_unit", "price_usd", "gross_revenue_usd",
    ]].rename(columns={
        "commodity_name_canonical": "commodity_name",
        "volume_total": "volume",
    })
    out["source"] = "EITI"
    return out


# ── Per-HS revenue from BGS ──
def _bgs_per_hs(bgs_scales: dict) -> pd.DataFrame:
    fp = RAW / "resources" / "bgs_mineral_production.csv"
    if not fp.exists():
        print("  [warn] bgs_mineral_production.csv missing; skipping BGS")
        return pd.DataFrame()
    bgs = pd.read_csv(fp)

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
        & ~bgs["hs_code"].isin(["2701", "2702"])   # coal codes — not minerals
        & bgs["production"].gt(0)
        & bgs["year"].between(YEARS[0], YEARS[-1])
    ].copy()
    rows = []
    for _, r in bgs.iterrows():
        hs = r["hs_code"]
        year = int(r["year"])
        if hs not in MINERAL_PRICES:
            continue
        unit = str(r["unit"]).strip()
        unit_lc = unit.lower()
        price_unit = HS_PRICE_UNIT.get(hs)
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
        scale = bgs_scales.get(r["iso3"], 1.0)
        vol_tonnes = float(r["production"]) * mult   # in canon_unit
        rev = vol_tonnes * converter * price * scale
        rows.append({
            "iso3": r["iso3"], "year": year, "hs_code": hs,
            "commodity_name": r["commodity"],
            "volume": vol_tonnes, "volume_unit": canon_unit,
            "price_usd": price, "gross_revenue_usd": rev, "source": "BGS",
            "bgs_scale": scale,
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    agg = (
        df.groupby(["iso3", "year", "hs_code"], as_index=False)
        .agg(
            commodity_name=("commodity_name", "first"),
            volume=("volume", "sum"),
            volume_unit=("volume_unit", "first"),
            price_usd=("price_usd", "first"),
            gross_revenue_usd=("gross_revenue_usd", "sum"),
            bgs_scale=("bgs_scale", "first"),
        )
    )
    agg["source"] = "BGS"
    return agg


def main():
    print("Loading calibration lookups...")
    rf_lookup = _load_calib_rent_fractions()
    bgs_scales = _load_bgs_scales()
    print(f"  {len(rf_lookup)} mineral rent fractions; {len(bgs_scales)} BGS scales")

    print("Building per-HS revenue from EITI...")
    eiti = _eiti_per_hs()
    print(f"  {len(eiti)} (iso, year, hs) EITI mineral rows")
    print("Building per-HS revenue from BGS...")
    bgs = _bgs_per_hs(bgs_scales)
    print(f"  {len(bgs)} (iso, year, hs) BGS mineral rows")

    # Source selection per (iso3, year): EITI if that country-year has ANY
    # EITI mineral data, else BGS. (Matches the bundled-minerals cascade in
    # 2_9: EITI > BGS > WB; WB has no HS detail so it drops out here.)
    eiti_keys = set(zip(eiti["iso3"], eiti["year"])) if not eiti.empty else set()

    if bgs.empty:
        bgs_use = pd.DataFrame()
    else:
        bgs_use = bgs[~bgs.apply(lambda r: (r["iso3"], r["year"]) in eiti_keys, axis=1)].copy()
    panel = pd.concat([eiti, bgs_use], ignore_index=True) if not eiti.empty else bgs_use
    if "bgs_scale" not in panel.columns:
        panel["bgs_scale"] = np.nan

    # Absolute-ceiling sanity drop.
    bad = panel["gross_revenue_usd"] > (ABSOLUTE_CEILING_USD / RENT_FRAC_MINERALS_DEFAULT)
    if bad.any():
        for _, r in panel[bad].iterrows():
            print(f"    [sanity-drop] {r['iso3']} {r['year']} HS{r['hs_code']} "
                  f"{r['commodity_name']}: gross ${r['gross_revenue_usd']/1e9:,.1f}B")
        panel = panel[~bad].copy()

    # Provisional rent per HS = gross_revenue × calibrated minerals fraction.
    panel["rent_fraction"] = panel["iso3"].map(
        lambda iso: rf_lookup.get(iso, RENT_FRAC_MINERALS_DEFAULT)
    )
    panel["rent_usd_provisional"] = panel["gross_revenue_usd"] * panel["rent_fraction"]

    # ── Anchor the per-HS split to the validated bundled rent_minerals ──
    # rents_combined_yearly.csv already applied the category-level sanity
    # filter, captured-revenue floor, and carry-forward. Rescale each
    # (iso, year)'s per-HS rents so they sum to that bundled value — the HS
    # split then determines the rate mix; the level comes from the
    # validated bundled estimate. Cells whose bundled source is WB (no HS
    # detail) or that have no per-HS rows are simply absent from this file.
    combined_fp = EXT_INT / "rents_combined_yearly.csv"
    bundled = {}
    if combined_fp.exists():
        comb = pd.read_csv(combined_fp)
        cm = comb[comb["category"] == "minerals"]
        bundled = {
            (r["iso3"], int(r["year"])): float(r["rent_best_usd"])
            for _, r in cm.iterrows()
            if pd.notna(r["rent_best_usd"]) and float(r["rent_best_usd"]) > 0
        }
    else:
        print("  [warn] rents_combined_yearly.csv missing; using provisional rents un-anchored")

    prov_sum = (
        panel.groupby(["iso3", "year"])["rent_usd_provisional"].transform("sum")
    )
    bundled_target = panel.apply(
        lambda r: bundled.get((r["iso3"], int(r["year"])), np.nan), axis=1
    )
    scale = np.where(
        (prov_sum > 0) & bundled_target.notna(),
        bundled_target / prov_sum,
        1.0,   # no bundled target: keep provisional (rare; e.g. carry-only cells)
    )
    panel["rent_anchor_scale"] = scale
    panel["rent_usd"] = panel["rent_usd_provisional"] * scale
    # Scale gross_revenue too so gross_revenue × rent_fraction == rent_usd stays
    # consistent within the file.
    panel["gross_revenue_usd"] = panel["gross_revenue_usd"] * scale
    panel = panel.drop(columns=["rent_usd_provisional"])
    panel = panel[panel["rent_usd"] > 0].copy()

    cols = [
        "iso3", "year", "hs_code", "commodity_name", "source",
        "volume", "volume_unit", "price_usd", "gross_revenue_usd",
        "rent_fraction", "bgs_scale", "rent_anchor_scale", "rent_usd",
    ]
    panel = panel[cols].sort_values(["iso3", "year", "hs_code"]).reset_index(drop=True)
    panel.to_csv(OUT_PATH, index=False)
    print(f"\nWrote {len(panel):,} (iso3, year, hs_code) rows -> {OUT_PATH}")

    # Reconciliation: per-(iso, year) sum of per-HS rent vs bundled (should
    # match exactly wherever a bundled target existed).
    if bundled:
        per = (
            panel.groupby(["iso3", "year"], as_index=False)["rent_usd"].sum()
            .rename(columns={"rent_usd": "rent_per_mineral_sum_usd"})
        )
        per["bundled"] = per.apply(
            lambda r: bundled.get((r["iso3"], int(r["year"])), np.nan), axis=1
        )
        cmp = per[per["bundled"].notna()].copy()
        cmp["abs_pct_diff"] = (
            (cmp["rent_per_mineral_sum_usd"] - cmp["bundled"]).abs()
            / cmp["bundled"].clip(lower=1.0)
        )
        n_off = int((cmp["abs_pct_diff"] > 1e-4).sum())
        print(f"\nReconciliation vs bundled rent_minerals: {len(cmp)} anchored "
              f"cells; {n_off} differ by >0.01% (should be 0)")

    # Top minerals by total rent across the panel.
    print("\nTop 12 minerals by total rent (all years, USD billions):")
    by_hs = (
        panel.groupby(["hs_code", "commodity_name"], as_index=False)["rent_usd"].sum()
        .sort_values("rent_usd", ascending=False)
    )
    for _, r in by_hs.head(12).iterrows():
        print(f"  HS{r['hs_code']:<5s} {r['commodity_name']:<22s}  ${r['rent_usd']/1e9:>7,.1f} B")


if __name__ == "__main__":
    main()
