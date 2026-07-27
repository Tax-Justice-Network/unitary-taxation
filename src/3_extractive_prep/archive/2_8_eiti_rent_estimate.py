"""
Build a rent estimate per (iso3, year, category) from the EITI cleaned
production panel.

Methodology aligned with the WB resource rents indicator family:

    rent_usd = volume × world_reference_price × rent_fraction

where:
  - volume                   from data/final/eiti_production_clean_long.csv
                             (already unit-normalized to tonnes, Sm3, oz, etc.)
  - world_reference_price    annual world reference benchmark per commodity
                             (WB Pink Sheet / LBMA / LME / Platts), embedded
                             below as a small table covering 2016-2024.
  - rent_fraction            commodity-specific (price - average unit cost) /
                             price ratio, embedded below. Rough WB-aligned
                             estimates, intended to be tuned.

Output:
  data/final/eiti_rents_estimated_yearly.csv
    iso3, year, category, rent_estimate_usd, n_commodities, commodity_list,
    revenue_estimate_usd, rent_fraction_avg

The result is the country's TOTAL extractive rent for that category-year as
reported by EITI, NOT just the captured government share. Comparable in
concept to wb_total_rents_usd partitioned by category.

Caveats:
  - Annual benchmark prices smooth out within-year volatility and intra-grade
    quality differences (e.g. heavy-vs-light crude, iron ore Fe content).
  - Rent fractions are commodity-level averages; country-specific operations
    (high-cost vs low-cost mines) will diverge. Tune in the cost-curve table
    below for sensitivity analysis.
  - "Other ores" (HS 2617) is summed at 30% rent fraction with a placeholder
    price, which is unreliable. Treat that line as indicative only.
  - Small commodities (silver, niobium, etc.) contribute little; the bulk of
    each country's rent comes from its 1-2 dominant commodities.
"""

import sys
from pathlib import Path

import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import FINAL

IN_PATH = FINAL / "eiti_production_clean_long.csv"
OUT_PATH = FINAL / "eiti_rents_estimated_yearly.csv"

# ── Reference prices per commodity per year ──
# Sources: WB Pink Sheet annual avg for oil/coal/metals/phosphates; LBMA for
# gold/silver; LME for base metals; Platts 62%Fe CFR for iron ore.
# All in USD per the price unit shown.

PRICES = {
    # Brent crude — USD/bbl. Convert to USD/Sm3 below (1 Sm3 = 6.2898 bbl)
    ("2709", "USD/bbl"): {
        2016: 43.74, 2017: 54.19, 2018: 71.31, 2019: 64.36,
        2020: 41.84, 2021: 70.86, 2022: 99.83, 2023: 82.49, 2024: 79.86,
    },
    # Natural gas — Henry Hub USD/MMBtu. Convert via 1 Sm3 = 0.0383 MMBtu
    ("2711", "USD/MMBtu"): {
        2016: 2.49, 2017: 2.96, 2018: 3.16, 2019: 2.57,
        2020: 2.03, 2021: 3.84, 2022: 6.45, 2023: 2.55, 2024: 2.41,
    },
    # Coal — Australian thermal coal USD/t
    ("2701", "USD/t"): {
        2016: 65.94, 2017: 88.28, 2018: 107.03, 2019: 77.78,
        2020: 60.83, 2021: 138.05, 2022: 357.97, 2023: 173.31, 2024: 135.55,
    },
    # Iron ore — Platts 62% Fe CFR China USD/t
    ("2601", "USD/t"): {
        2016: 58.42, 2017: 71.76, 2018: 69.79, 2019: 93.85,
        2020: 108.92, 2021: 161.71, 2022: 121.28, 2023: 119.56, 2024: 109.83,
    },
    # Manganese ore (44% Mn) — implied USD/t bulk price
    ("2602", "USD/t"): {
        2016: 165, 2017: 220, 2018: 200, 2019: 180,
        2020: 165, 2021: 250, 2022: 305, 2023: 215, 2024: 200,
    },
    # Copper — LME spot, USD/t (refined Cu equivalent; ore at lower grade
    # adjusted via rent_fraction)
    ("2603", "USD/t"): {
        2016: 4868, 2017: 6166, 2018: 6530, 2019: 6010,
        2020: 6181, 2021: 9317, 2022: 8822, 2023: 8490, 2024: 9152,
    },
    # Nickel — LME spot, USD/t
    ("2604", "USD/t"): {
        2016: 9595, 2017: 10410, 2018: 13122, 2019: 13903,
        2020: 13787, 2021: 18465, 2022: 25834, 2023: 21490, 2024: 16811,
    },
    # Cobalt — LME spot, USD/t
    ("2605", "USD/t"): {
        2016: 25500, 2017: 55700, 2018: 72500, 2019: 33500,
        2020: 31500, 2021: 51500, 2022: 64500, 2023: 33500, 2024: 26500,
    },
    # Bauxite — FOB Guinea/Brazil, USD/t (rough)
    ("2606", "USD/t"): {
        2016: 30, 2017: 33, 2018: 40, 2019: 35,
        2020: 32, 2021: 45, 2022: 50, 2023: 50, 2024: 55,
    },
    # Lead — LME, USD/t
    ("2607", "USD/t"): {
        2016: 1872, 2017: 2317, 2018: 2240, 2019: 2000,
        2020: 1825, 2021: 2200, 2022: 2150, 2023: 2120, 2024: 2073,
    },
    # Zinc — LME, USD/t
    ("2608", "USD/t"): {
        2016: 2095, 2017: 2891, 2018: 2922, 2019: 2547,
        2020: 2266, 2021: 3000, 2022: 3475, 2023: 2650, 2024: 2780,
    },
    # Tin — LME, USD/t
    ("2609", "USD/t"): {
        2016: 17956, 2017: 20064, 2018: 20146, 2019: 18661,
        2020: 17126, 2021: 32422, 2022: 31200, 2023: 25922, 2024: 30200,
    },
    # Chromium ore (estimate)
    ("2610", "USD/t"): {y: 200 for y in range(2016, 2025)},
    # Tungsten ore (APT WO3 equivalent)
    ("2611", "USD/t"): {y: 30000 for y in range(2016, 2025)},
    # Molybdenum ore (Mo metal equivalent)
    ("2613", "USD/t"): {
        2016: 16500, 2017: 18000, 2018: 25000, 2019: 25000,
        2020: 19000, 2021: 35000, 2022: 41000, 2023: 47000, 2024: 45000,
    },
    # Titanium ore (ilmenite)
    ("2614", "USD/t"): {y: 220 for y in range(2016, 2025)},
    # Niobium/Vanadium/Zirconium — rough composite
    ("2615", "USD/t"): {y: 30000 for y in range(2016, 2025)},
    # Precious metal ores (lump / placeholder; depends on grade)
    ("2616", "USD/t"): {y: 5000 for y in range(2016, 2025)},
    # Other ores — placeholder, very uncertain
    ("2617", "USD/t"): {y: 200 for y in range(2016, 2025)},
    # Phosphate rock — Morocco FOB, USD/t
    ("2510", "USD/t"): {
        2016: 113, 2017: 90, 2018: 88, 2019: 80,
        2020: 75, 2021: 123, 2022: 254, 2023: 322, 2024: 162,
    },
    # Diamonds — USD per carat (rough)
    ("7102", "USD/carat"): {y: 90 for y in range(2016, 2025)},
    # Silver — LBMA, USD/oz. Convert via 1 t = 32150.7466 oz
    ("7106", "USD/oz"): {
        2016: 17.14, 2017: 17.05, 2018: 15.71, 2019: 16.21,
        2020: 20.55, 2021: 25.14, 2022: 21.77, 2023: 23.35, 2024: 28.24,
    },
    # Gold — LBMA, USD/oz
    ("7108", "USD/oz"): {
        2016: 1251.0, 2017: 1257.5, 2018: 1268.5, 2019: 1392.6,
        2020: 1769.6, 2021: 1799.3, 2022: 1801.4, 2023: 1941.5, 2024: 2389.0,
    },
    # Platinum-group metals — composite, USD/oz
    ("7110", "USD/oz"): {y: 1000 for y in range(2016, 2025)},
}


# Rent fraction = (price - average_unit_cost) / price, intended as the share
# of revenue that constitutes economic rent. WB-aligned commodity averages.
# Tune per commodity for sensitivity testing.
RENT_FRACTION = {
    "2709": 0.70,   # Crude oil
    "2710": 0.40,   # Refined products (lower because already processed)
    "2711": 0.55,   # Natural gas
    "2701": 0.45,   # Coal
    "2702": 0.40,   # Lignite
    "2601": 0.55,   # Iron ore
    "2602": 0.45,   # Manganese
    "2603": 0.50,   # Copper ore
    "2604": 0.45,   # Nickel
    "2605": 0.55,   # Cobalt
    "2606": 0.65,   # Bauxite
    "2607": 0.40,   # Lead
    "2608": 0.40,   # Zinc
    "2609": 0.45,   # Tin
    "2610": 0.40,   # Chromium
    "2611": 0.45,   # Tungsten
    "2613": 0.45,   # Molybdenum
    "2614": 0.40,   # Titanium
    "2615": 0.50,   # Nb/V/Zr
    "2616": 0.50,   # Precious metal ores
    "2617": 0.30,   # Other ores (uncertain)
    "2510": 0.30,   # Phosphates (low rent)
    "7102": 0.70,   # Diamonds
    "7106": 0.40,   # Silver
    "7108": 0.65,   # Gold
    "7110": 0.50,   # PGM
}


# Conversion of stored EITI volume_unit to the price unit's denominator.
# (volume_unit, price_unit) -> volume multiplier so that
#   revenue = volume * mult * price[year]
VOLUME_TO_PRICE_UNIT = {
    # Oil/gas: stored as Sm3
    ("Sm3", "USD/bbl"): 6.2898,            # 1 Sm3 = 6.2898 bbl
    ("Sm3", "USD/MMBtu"): 0.0383,          # natural gas energy content (rough)
    ("Sm3 o.e.", "USD/bbl"): 6.2898,
    ("Sm3 o.e.", "USD/MMBtu"): 0.0383,
    # Mass: stored as tonnes
    ("tonnes", "USD/t"): 1.0,
    ("tonnes", "USD/oz"): 32150.7466,      # 1 t = 32150.7466 troy oz
    # Diamonds: stored as carats
    ("carats", "USD/carat"): 1.0,
}


def main():
    print(f"Loading {IN_PATH}...")
    df = pd.read_csv(IN_PATH)
    print(f"  {len(df):,} rows in")

    df = df.dropna(subset=["volume_total", "volume_unit", "hs_code"])
    df["hs_code"] = df["hs_code"].astype(str).str.strip()
    df["year"] = df["year"].astype(int)
    df["volume_unit"] = df["volume_unit"].astype(str).str.strip()
    df = df[df["volume_total"] > 0].copy()

    # Pick the right price series for each (hs_code, volume_unit) pair
    def compute_revenue(row):
        hs = row["hs_code"]
        unit = row["volume_unit"]
        year = row["year"]

        # Find the (hs, price_unit) entry whose price_unit is bridged to this
        # volume_unit by VOLUME_TO_PRICE_UNIT.
        for (hs_p, price_unit), prices in PRICES.items():
            if hs_p != hs:
                continue
            mult = VOLUME_TO_PRICE_UNIT.get((unit, price_unit))
            if mult is None:
                continue
            price = prices.get(year)
            if price is None:
                # Carry-fwd from latest available year if outside table
                avail_years = sorted(prices.keys())
                if year < avail_years[0]:
                    price = prices[avail_years[0]]
                else:
                    price = prices[avail_years[-1]]
            return pd.Series({
                "price_used": price,
                "price_unit_used": price_unit,
                "volume_mult": mult,
                "revenue_usd": row["volume_total"] * mult * price,
            })
        return pd.Series({
            "price_used": None,
            "price_unit_used": None,
            "volume_mult": None,
            "revenue_usd": None,
        })

    print("Computing per-commodity revenues...")
    enriched = df.apply(compute_revenue, axis=1)
    df = pd.concat([df, enriched], axis=1)

    # Diagnostic: rows we couldn't price
    n_unpriced = df["revenue_usd"].isna().sum()
    print(f"  unpriced rows (no price/unit match): {n_unpriced:,} of {len(df):,}")
    if n_unpriced > 0:
        unpriced = df[df["revenue_usd"].isna()].groupby(
            ["hs_code", "volume_unit"]
        ).size().reset_index(name="n")
        print("  unpriced (hs_code, unit) breakdown:")
        for _, r in unpriced.iterrows():
            print(f"    {r['hs_code']:>4} {r['volume_unit']:<15s}  {r['n']:>4}")

    df = df.dropna(subset=["revenue_usd"])
    df["rent_fraction"] = df["hs_code"].map(RENT_FRACTION).fillna(0.40)
    df["rent_estimate_usd"] = df["revenue_usd"] * df["rent_fraction"]

    # Per-row clean panel
    per_commodity_path = FINAL / "eiti_rents_per_commodity_yearly.csv"
    detail_cols = [
        "iso3", "year", "category", "hs_code", "commodity_name_canonical",
        "volume_total", "volume_unit", "price_used", "price_unit_used",
        "revenue_usd", "rent_fraction", "rent_estimate_usd",
    ]
    df[detail_cols].sort_values(
        ["iso3", "year", "category", "hs_code"]
    ).to_csv(per_commodity_path, index=False)
    print(f"\nWrote per-commodity detail -> {per_commodity_path}")

    # Aggregate to (iso3, year, category)
    agg = (
        df.groupby(["iso3", "year", "category"], as_index=False)
        .agg(
            rent_estimate_usd=("rent_estimate_usd", "sum"),
            revenue_estimate_usd=("revenue_usd", "sum"),
            n_commodities=("hs_code", "nunique"),
            commodity_list=(
                "commodity_name_canonical",
                lambda s: ", ".join(sorted(set(str(x) for x in s if pd.notna(x)))),
            ),
        )
    )
    agg["rent_fraction_avg"] = (
        agg["rent_estimate_usd"] / agg["revenue_estimate_usd"]
    ).round(3)

    agg.to_csv(OUT_PATH, index=False)
    print(f"Wrote category aggregate -> {OUT_PATH}")

    # Highlight 2021-2022 African producers
    print("\n=== 2021-2022 EITI rent estimates by category ===")
    afr = ["AGO", "ARM", "GAB", "GIN", "MDG", "MLI", "MRT", "MWI",
           "SEN", "TGO", "UGA", "ZMB", "ETH", "BFA"]
    show = agg[
        agg["iso3"].isin(afr)
        & agg["year"].isin([2021, 2022])
        & agg["category"].isin(["oil_gas", "coal", "minerals"])
    ].copy()
    show["rent_billion_usd"] = (show["rent_estimate_usd"] / 1e9).round(2)
    print(show[
        ["iso3", "year", "category", "rent_billion_usd",
         "n_commodities", "commodity_list"]
    ].sort_values(["iso3", "year", "category"]).to_string(index=False))


if __name__ == "__main__":
    main()
