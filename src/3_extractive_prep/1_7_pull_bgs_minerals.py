"""
Pull British Geological Survey (BGS) World Mineral Statistics annual production
volumes 2016-2023 via the BGS OGC API and write them to a long-format CSV.

Endpoint: https://ogcapi.bgs.ac.uk/collections/world-mineral-statistics/items
   - Filter `bgs_statistic_type_trans=Production` to drop trade/refining/etc.
   - Per-year filter `year=YYYY-01-01T00:00:00` works (RFC3339-ish prefix).
     Generic datetime range filtering is broken on this API as of 2026-04, so
     we just iterate years 2016..2023.
   - Pagination by `?offset=N&limit=K`. The server fails on large limits
     (1000+ resets the connection); 200-500 is reliable.

Why we want BGS: the existing combined-rent panel (2_9) merges EITI > EIA > WB.
For minerals, EITI only has ~30 countries with mineral templates and WB has
not published 2022 universally. BGS publishes an annual mineral yearbook
covering 200+ countries with ~80 commodities and is current through ~2023, so
it is the best replacement for the 2022 mineral coverage gap (and a good
cross-check elsewhere).

Output: data/raw/resources/bgs_mineral_production.csv with columns
    iso3, year, commodity, sub_commodity, bgs_commodity_code,
    hs_code, production, unit, source

`hs_code` is mapped from `bgs_commodity_trans` to the same HS-4 buckets the
rest of the pipeline uses (see HS_TO_CATEGORY in 1_5_parse_eiti_xlsx.py).
Commodities outside our pricing table (cement, salt, aggregates, ferro-alloys,
refined-metal stages, etc.) get hs_code='' so 2_9 can filter them out.

Run:  python src/3_extractive_prep/1_7_pull_bgs_minerals.py
"""

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW

OUT_PATH = RAW / "resources" / "bgs_mineral_production.csv"

API_BASE = "https://ogcapi.bgs.ac.uk/collections/world-mineral-statistics/items"
UA = "sotj-research/0.1"
HEADERS = {"User-Agent": UA, "Accept": "application/json"}

YEARS = list(range(2016, 2024))   # 2016..2023 inclusive
PAGE_LIMIT = 500                    # server stable at 200-500; 1000+ resets
MAX_RETRIES = 4

# ── BGS commodity (`bgs_commodity_trans`) -> HS-4 mineral code ─────────────
# Only commodities whose HS bucket is priced in MINERAL_PRICES (2_9) get a
# non-empty hs_code, so they actually flow into the rent estimate. The rest
# are kept in the CSV (with hs_code="") for completeness / future use.
#
# HS reference (matches HS_TO_CATEGORY in 1_5_parse_eiti_xlsx.py):
#   2510 phosphates    2601 iron ore      2602 manganese
#   2603 copper        2604 nickel        2605 cobalt
#   2606 bauxite       2607 lead          2608 zinc
#   2609 tin           2610 chromium      2611 tungsten
#   2613 molybdenum    2614 titanium      2615 Nb/Ta/V/Zr
#   2616 precious-mtl  2617 other ores    7102 diamonds
#   7106 silver        7108 gold          7110 PGM
#
# We point each BGS "X, mine" / "X ore" row at the HS code for the contained-
# metal ore stage (so that volume × USD/t-of-metal-content matches MINERAL_PRICES
# in 2_9). Refined-metal rows ("X, refined", "X, smelter", "iron, pig",
# "steel, crude", "alumina", "aluminium primary") are intentionally NOT mapped
# because (a) they double-count primary mine stage already counted under "X,
# mine" / "bauxite" / "iron ore", and (b) MINERAL_PRICES anchors on the ore
# price, not the refined-metal price.
BGS_TO_HS = {
    # Iron / steel — keep ore stage, drop pig iron and crude steel
    "iron ore":                   "2601",
    # Manganese
    "manganese ore":              "2602",
    # Copper — mine production (metal content)
    "copper, mine":               "2603",
    # Nickel — mine production (metal content)
    "nickel, mine":               "2604",
    # Cobalt — mine production (metal content)
    "cobalt, mine":               "2605",
    # Bauxite (aluminium ore)
    "bauxite":                    "2606",
    # Lead
    "lead, mine":                 "2607",
    # Zinc
    "zinc, mine":                 "2608",
    # Tin
    "tin, mine":                  "2609",
    # Chromium
    "chromium ores and concentrates": "2610",
    # Tungsten
    "tungsten, mine":             "2611",
    # Molybdenum
    "molybdenum, mine":           "2613",
    # Titanium
    "titanium minerals":          "2614",
    # Nb/Ta/V/Zr group (HS 2615)
    "tantalum and niobium minerals": "2615",
    "vanadium, mine":             "2615",
    "zirconium minerals":         "2615",
    # Other ores bucket (HS 2617). Antimony/bismuth/uranium have no dedicated
    # 4-digit HS but conceptually belong in 2617.
    "antimony, mine":             "2617",
    "bismuth, mine":              "2617",
    "uranium":                    "2617",
    # Phosphates
    "phosphate rock":             "2510",
    # Precious stones / metals
    "diamond":                    "7102",
    "silver, mine":               "7106",
    "gold, mine":                 "7108",
    "platinum group metals, mine": "7110",
    # Lithium / rare earths — no priced HS bucket in our pipeline; keep blank
    # so they stay informational.
}


def fetch_year(year: int):
    """Iterate all production records for a given calendar year.

    BGS's all-Production stream times out (the unfiltered query is too large
    to compute server-side). The per-year filter format
    `year=YYYY-01-01T00:00:00` works for SOME years (2016, 2022, 2023 in
    practice) and returns non-JSON for others. We try each year, tolerate
    per-year failure, and report what we got.
    """
    rows = []
    offset = 0
    total = None
    while True:
        qs = [
            ("bgs_statistic_type_trans", "Production"),
            ("year", f"{year}-01-01T00:00:00"),
            ("limit", str(PAGE_LIMIT)),
            ("offset", str(offset)),
        ]
        url = API_BASE + "?" + urllib.parse.urlencode(qs)
        req = urllib.request.Request(url, headers=HEADERS)

        for attempt in range(MAX_RETRIES):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = r.read()
                payload = json.loads(raw)
                break
            except json.JSONDecodeError as exc:
                # Server returned HTML / error page for this year — give up.
                print(f"    [skip] year={year}: non-JSON response (BGS year "
                      f"filter rejection)")
                return rows
            except Exception as exc:
                if attempt == MAX_RETRIES - 1:
                    print(f"    [fail] year={year} offset={offset}: {exc}")
                    return rows
                wait = 2 ** attempt
                print(f"    [retry {attempt+1}] year={year} offset={offset}: "
                      f"{exc} (sleeping {wait}s)")
                time.sleep(wait)

        feats = payload.get("features", [])
        if total is None:
            total = int(payload.get("numberMatched", 0) or 0)
        if not feats:
            break
        rows.extend(feats)
        offset += len(feats)
        if offset >= total:
            break
        time.sleep(0.2)  # be nice to the server
    return rows


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    by_year = Counter()
    YEARS_SET = set(YEARS)

    print(f"Pulling BGS Production records year-by-year for "
          f"{YEARS[0]}-{YEARS[-1]} (limit={PAGE_LIMIT})...")
    feats_all = []
    for y in YEARS:
        print(f"  year={y}...", end="", flush=True)
        feats = fetch_year(y)
        print(f" {len(feats):>5} records returned")
        for f in feats:
            f.setdefault("_year_hint", y)
        feats_all.extend(feats)
    print(f"  Total returned: {len(feats_all):,}")

    for f in feats_all:
        p = f.get("properties", {}) or {}
        iso3 = (p.get("country_iso3_code") or "").strip().upper()
        if len(iso3) != 3 or not iso3.isalpha():
            continue
        # year is a date-time string like '2017-01-01T00:00:00'; take the
        # leading 4 chars
        yr_str = (p.get("year") or "")[:4]
        try:
            y = int(yr_str)
        except ValueError:
            y = f.get("_year_hint")
            if y is None:
                continue
        if y not in YEARS_SET:
            continue
        commodity = p.get("bgs_commodity_trans")
        if commodity is None:
            continue
        sub = p.get("bgs_sub_commodity_trans") or ""
        qty = p.get("quantity")
        if qty is None:
            continue
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            continue
        if qty <= 0:
            # Drop true zero / not-produced rows. Keeping them only
            # bloats the CSV and confuses downstream coverage stats.
            continue
        unit = p.get("units") or ""
        code = p.get("bgs_commodity_code")
        hs = BGS_TO_HS.get(str(commodity).strip().lower(), "")
        all_rows.append({
            "iso3": iso3,
            "year": y,
            "commodity": commodity,
            "sub_commodity": sub,
            "bgs_commodity_code": code if code is not None else "",
            "hs_code": hs,
            "production": qty,
            "unit": unit,
            "source": "BGS_WMS",
        })
        by_year[y] += 1

    if not all_rows:
        print("No rows produced; aborting.")
        return

    cols = ["iso3", "year", "commodity", "sub_commodity",
            "bgs_commodity_code", "hs_code", "production", "unit", "source"]
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in all_rows:
            w.writerow(r)
    print(f"\nWrote {len(all_rows):,} rows -> {OUT_PATH}")

    # ── Coverage stats ──
    print("\nRows kept by year:")
    for y in YEARS:
        print(f"  {y}: {by_year[y]:>6,}")

    # Top 20 commodities by row count
    by_commod = Counter()
    by_hs = Counter()
    for r in all_rows:
        by_commod[r["commodity"]] += 1
        by_hs[r["hs_code"] or "(unmapped)"] += 1
    print("\nTop 20 commodities by row count:")
    for c, n in by_commod.most_common(20):
        hs = BGS_TO_HS.get(str(c).strip().lower(), "")
        tag = f"HS {hs}" if hs else "(no HS)"
        print(f"  {n:>6,}  {c:<35s}  {tag}")

    print("\nRows by HS bucket (the priced ones flow into 2_9 rent calc):")
    for hs, n in sorted(by_hs.items()):
        print(f"  {hs:<12s}  {n:>6,}")

    # Spot-check African mineral producers in 2022
    afr = ["COD", "GIN", "MRT", "MLI", "BFA", "GHA", "TZA", "ZMB",
           "ZAF", "NER", "NGA", "MOZ", "MDG"]
    print("\nAfrican producer 2022 spot check (commodity counts, mapped HS only):")
    for iso in afr:
        cs = sorted({
            r["commodity"] for r in all_rows
            if r["iso3"] == iso and r["year"] == 2022 and r["hs_code"]
        })
        if cs:
            print(f"  {iso}: {len(cs):>2}  {', '.join(cs)}")
        else:
            print(f"  {iso}: (none)")


if __name__ == "__main__":
    main()
