"""
Single source of truth for the commodity reference-price tables used across
the extractive-rent pipeline.

Before this module existed, MINERAL_PRICES / HS_PRICE_UNIT /
MINERAL_VOL_TO_PRICE_MULT / the energy-price tables were copy-pasted into
2_8a, 2_8b, 2_9, 2_9b, 3_resource_contribution.py and 4_carveout.py — six
copies that had to be kept in sync by hand. Import from here instead:

    from _reference_prices import MINERAL_PRICES, HS_PRICE_UNIT, ...

Conventions
-----------
- Each mineral "ore/concentrate" HS code is priced at the benchmark *metal*
  (or dominant traded product) price. This deliberately over-estimates
  concentrate value; the per-country rent-fraction calibration (2_8a)
  corrects the systematic level error.
- Years 2016-2024. Missing years are carried forward/backward by the
  callers' `_yearly_lookup` helpers.
- Flat values are placeholders for commodities without a readily-available
  annual series — refine before external publication. The flagged ones:
    2602 manganese, 2614 titanium, 2615 Nb/Ta/V/Zr, 2616 precious-metal
    ores n.e.s., 2617 other ores, 7102 diamonds.
- The 8 base/industrial-metal codes (2607 lead, 2608 zinc, 2609 tin, 2610
  ferrochrome, 2611 tungsten, 2613 molybdenum) and 7110 PGMs use rough
  benchmark proxies (LME annual averages where available; ferrochrome /
  tungsten APT-equiv / Mo-oxide / platinum approximations otherwise).
"""

# ── Energy reference prices ──────────────────────────────────────────────
BRENT_USD_BBL = {
    2016: 43.74, 2017: 54.19, 2018: 71.31, 2019: 64.36,
    2020: 41.84, 2021: 70.86, 2022: 99.83, 2023: 82.49, 2024: 79.86,
}
HENRY_HUB_USD_MMBTU = {
    2016: 2.49, 2017: 2.96, 2018: 3.16, 2019: 2.57,
    2020: 2.03, 2021: 3.84, 2022: 6.45, 2023: 2.55, 2024: 2.41,
}
COAL_AUS_USD_T = {
    2016: 65.94, 2017: 88.28, 2018: 107.03, 2019: 77.78,
    2020: 60.83, 2021: 138.05, 2022: 357.97, 2023: 173.31, 2024: 135.55,
}

# ── Per-mineral reference prices (HS-4 code -> {year: price}) ─────────────
MINERAL_PRICES = {
    "2510": dict(zip(range(2016, 2025), [113, 90, 88, 80, 75, 123, 254, 322, 162])),       # phosphate rock
    "2601": dict(zip(range(2016, 2025), [58.42, 71.76, 69.79, 93.85, 108.92, 161.71, 121.28, 119.56, 109.83])),  # iron ore CFR China
    "2602": {y: 200 for y in range(2016, 2025)},                                            # manganese (flat placeholder)
    "2603": dict(zip(range(2016, 2025), [4868, 6166, 6530, 6010, 6181, 9317, 8822, 8490, 9152])),               # copper (LME)
    "2604": dict(zip(range(2016, 2025), [9595, 10410, 13122, 13903, 13787, 18465, 25834, 21490, 16811])),       # nickel (LME)
    "2605": dict(zip(range(2016, 2025), [25500, 55700, 72500, 33500, 31500, 51500, 64500, 33500, 26500])),      # cobalt
    "2606": dict(zip(range(2016, 2025), [30, 33, 40, 35, 32, 45, 50, 50, 55])),             # bauxite
    "2607": dict(zip(range(2016, 2025), [1872, 2317, 2240, 1997, 1826, 2200, 2145, 2136, 2080])),               # lead (LME avg)
    "2608": dict(zip(range(2016, 2025), [2090, 2891, 2922, 2546, 2266, 3003, 3440, 2651, 2779])),               # zinc (LME avg)
    "2609": dict(zip(range(2016, 2025), [17934, 20061, 20145, 18661, 17125, 31173, 31350, 25960, 30100])),      # tin (LME avg)
    "2610": dict(zip(range(2016, 2025), [1100, 1500, 1450, 1100, 1050, 1700, 1900, 1500, 1300])),               # ferrochrome (HC), approx
    "2611": dict(zip(range(2016, 2025), [18000, 25000, 30000, 24000, 22000, 28000, 30000, 30000, 30000])),      # tungsten APT-equiv, approx
    "2613": dict(zip(range(2016, 2025), [14000, 18000, 26000, 25000, 18000, 35000, 40000, 50000, 45000])),      # molybdenum oxide/metal, approx
    "2614": {y: 220 for y in range(2016, 2025)},                                            # titanium ore (flat placeholder)
    "2615": {y: 30000 for y in range(2016, 2025)},                                          # Nb/Ta/V/Zr ores (flat placeholder)
    "2616": {y: 100 for y in range(2016, 2025)},                                            # precious-metal ores n.e.s. (crude bulk-ore proxy)
    # NOTE: HS 2617 "Other ores" is deliberately NOT priced — it's an
    # unidentifiable catch-all, so we can't attach a meaningful price.
    # 2_7_eiti_to_clean_panel.py categorises it as "other" (excluded from
    # the carve-out base) and the BGS/WB paths skip it for lack of a price.
    "7102": {y: 90 for y in range(2016, 2025)},                                             # diamonds (flat placeholder, USD/carat)
    "7106": dict(zip(range(2016, 2025), [17.14, 17.05, 15.71, 16.21, 20.55, 25.14, 21.77, 23.35, 28.24])),      # silver (USD/oz)
    "7108": dict(zip(range(2016, 2025), [1251.0, 1257.5, 1268.5, 1392.6, 1769.6, 1799.3, 1801.4, 1941.5, 2389.0])),  # gold (USD/oz)
    "7110": dict(zip(range(2016, 2025), [990, 950, 880, 870, 880, 1090, 960, 970, 950])),   # PGMs ~ platinum annual avg (USD/oz)
}
HS_PRICE_UNIT = {
    "2510": "USD/t", "2601": "USD/t", "2602": "USD/t", "2603": "USD/t",
    "2604": "USD/t", "2605": "USD/t", "2606": "USD/t",
    "2607": "USD/t", "2608": "USD/t", "2609": "USD/t", "2610": "USD/t",
    "2611": "USD/t", "2613": "USD/t",
    "2614": "USD/t", "2615": "USD/t", "2616": "USD/t",   # 2617 ("Other ores") intentionally unpriced
    "7102": "USD/carat", "7106": "USD/oz", "7108": "USD/oz", "7110": "USD/oz",
}
MINERAL_VOL_TO_PRICE_MULT = {
    # (volume_unit, price_unit) -> multiplier so revenue = volume * mult * price
    ("tonnes", "USD/t"): 1.0,
    ("tonnes", "USD/oz"): 32150.7466,
    ("carats", "USD/carat"): 1.0,
}

# Per-HS panel-range min/max (anchors the per-HS Cat 1 royalty rate scale).
MINERAL_HIST_MIN = {hs: min(p.values()) for hs, p in MINERAL_PRICES.items()}
MINERAL_HIST_MAX = {hs: max(p.values()) for hs, p in MINERAL_PRICES.items()}

# Last-resort flat rent fractions when no calibrated (iso, category) value
# exists (calibrated values come from data/final/rent_fractions_calibrated.csv).
RENT_FRAC_DEFAULT = {"oil_gas": 0.50, "coal": 0.30, "minerals": 0.30}
