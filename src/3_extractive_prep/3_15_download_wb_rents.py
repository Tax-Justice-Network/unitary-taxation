"""
Download World Bank World Development Indicators on natural resource rents.
Uses the WB API v2, saves a merged CSV with USD-level calculations.
"""

import urllib.request
import json
import csv
import os
import time

BASE_URL = "https://api.worldbank.org/v2/country/all/indicator/{indicator}?format=json&per_page=20000&date=2000:2023"

INDICATORS = {
    "NY.GDP.MKTP.CD": "gdp_current_usd",
    "NY.GDP.TOTL.RT.ZS": "total_rents_pct_gdp",
    "NY.GDP.PETR.RT.ZS": "oil_rents_pct_gdp",
    "NY.GDP.NGAS.RT.ZS": "gas_rents_pct_gdp",
    "NY.GDP.COAL.RT.ZS": "coal_rents_pct_gdp",
    "NY.GDP.MINR.RT.ZS": "mineral_rents_pct_gdp",
    "NY.GDP.FRST.RT.ZS": "forest_rents_pct_gdp",
}

# Store data keyed by (iso3, year)
data = {}

for indicator_code, col_name in INDICATORS.items():
    url = BASE_URL.format(indicator=indicator_code)
    print(f"Downloading {indicator_code} ({col_name})...")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
        result = json.loads(raw)
    except Exception as e:
        print(f"  ERROR downloading {indicator_code}: {e}")
        continue

    if not isinstance(result, list) or len(result) < 2:
        print(f"  WARNING: unexpected response for {indicator_code}")
        continue

    metadata = result[0]
    records = result[1]
    total = metadata.get("total", len(records))
    print(f"  Got {len(records)} records (total available: {total})")

    if total > len(records):
        print(f"  WARNING: not all records fetched. Got {len(records)} of {total}.")

    for rec in records:
        iso3 = rec.get("countryiso3code") or rec.get("country", {}).get("id", "")
        country_name = rec.get("country", {}).get("value", "")
        year = rec.get("date", "")
        value = rec.get("value")

        if not iso3 or not year:
            continue

        key = (iso3, year)
        if key not in data:
            data[key] = {
                "country_name": country_name,
                "country_iso3": iso3,
                "year": year,
            }
        # Prefer non-empty country name
        if country_name and not data[key]["country_name"]:
            data[key]["country_name"] = country_name

        data[key][col_name] = value

    # Brief pause to be polite to the API
    time.sleep(1)

# Build rows and calculate USD levels
pct_cols = [
    ("total_rents_pct_gdp", "total_rents_usd"),
    ("oil_rents_pct_gdp", "oil_rents_usd"),
    ("gas_rents_pct_gdp", "gas_rents_usd"),
    ("coal_rents_pct_gdp", "coal_rents_usd"),
    ("mineral_rents_pct_gdp", "mineral_rents_usd"),
    ("forest_rents_pct_gdp", "forest_rents_usd"),
]

fieldnames = [
    "country_name",
    "country_iso3",
    "year",
    "gdp_current_usd",
    "total_rents_pct_gdp",
    "oil_rents_pct_gdp",
    "gas_rents_pct_gdp",
    "coal_rents_pct_gdp",
    "mineral_rents_pct_gdp",
    "forest_rents_pct_gdp",
    "total_rents_usd",
    "oil_rents_usd",
    "gas_rents_usd",
    "coal_rents_usd",
    "mineral_rents_usd",
    "forest_rents_usd",
]

rows = []
for key in sorted(data.keys()):
    row = data[key]
    gdp = row.get("gdp_current_usd")

    for pct_col, usd_col in pct_cols:
        pct_val = row.get(pct_col)
        if gdp is not None and pct_val is not None:
            row[usd_col] = pct_val * gdp / 100.0
        else:
            row[usd_col] = None

    # Fill missing fields with empty
    for f in fieldnames:
        if f not in row:
            row[f] = None

    rows.append(row)

from _paths import RAW  # noqa: E402
out_path = RAW / "resources" / "wb_resource_rents.csv"

with open(out_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)

print(f"\nDone. Wrote {len(rows)} rows to:\n  {out_path}")
