# %%
"""
3_11 — Parse EITI country revenues.

Combine the bulk payment-level CSV (manually downloaded from eiti.org) with
the EITI API summary totals into a clean country x year table of total
government revenue plus a breakdown by revenue stream (GFS category).

The manual-download CSV is the primary source here because the EITI API's
`/revenue` endpoint does not consistently populate payment-type breakdowns
for many reporting countries — so the API-only path misses 40+ countries'
royalty/CIT decompositions. To refresh: download the latest bulk CSV from
EITI's data portal and overwrite the manual-download file below.

Pipeline: Extractive prep, stage 3_11 — ingests the EITI country-revenue
product (the first EITI ingest); feeds the 3_2x rent-combination stage.

Reads:
  data/raw/extractive/eiti_revenues_manual_download.csv  — EITI bulk payment-level download (manual)
  https://api.eiti.org/api/v2.0/summary_data              — EITI API summary totals + sector info

Writes:
  data/intermediate/extractive/eiti_revenues.csv          — country x year revenue by GFS stream

Usage:
  python 3_11_parse_eiti_country_revenues.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import csv
import os
import requests
import time
import json
from collections import defaultdict

# %% MARK: 2. Config and paths
from _paths import RAW, EXT_INT  # noqa: E402
RAW_CSV = RAW / "extractive" / "eiti_revenues_manual_download.csv"          # external download
OUTPUT_CSV = EXT_INT / "eiti_revenues.csv"                   # processed → intermediate
BASE_URL = "https://api.eiti.org/api/v2.0"


# %% MARK: 3. Fetch API data
def fetch_summary_data():
    """Fetch all summary_data records from the EITI API using page-based pagination."""
    session = requests.Session()
    all_data = []
    page = 1
    total = None

    while True:
        url = f"{BASE_URL}/summary_data?page={page}"
        for attempt in range(5):
            try:
                r = session.get(url, timeout=30)
                r.raise_for_status()
                break
            except Exception as e:
                if attempt < 4:
                    time.sleep(2 ** attempt)
                else:
                    raise

        data = r.json()
        if total is None:
            total = data.get("count", 0)
            print(f"  Total summary records: {total}")

        records = data.get("data", [])
        if not records:
            break

        all_data.extend(records)
        page += 1
        print(f"  Fetched {len(all_data)} / {total}...", end="\r")

        # Stop if no next page
        if "next" not in data or not data["next"]:
            break

    print(f"  Fetched {len(all_data)} / {total} - done.")
    return all_data


# %% MARK: 4. Build and write table
def main():
    # Step 1: Get summary data from API for totals and sector info
    print("Step 1: Fetching summary data from EITI API...")
    summaries = fetch_summary_data()

    summary_lookup = {}
    for s in summaries:
        iso3 = s.get("country.iso3", "")
        country_name = s.get("country.label", "")
        # Extract year from ID (e.g., "AF2009" -> "2009")
        sid = s.get("id", "")
        year = sid[2:] if len(sid) > 2 else ""

        summary_lookup[(iso3, year)] = {
            "country_name": country_name,
            "country_iso2": s.get("country.iso2", ""),
            "country_iso3": iso3,
            "year": year,
            "revenue_government_total_usd": s.get("revenue_government_sum"),
            "local_currency": s.get("currency"),
            "currency_rate_to_usd": s.get("currency_rate"),
            "sector_oil": s.get("sector_oil"),
            "sector_gas": s.get("sector_gas"),
            "sector_mining": s.get("sector_mining"),
        }

    print(f"  {len(summary_lookup)} country-year records from API.\n")

    # Step 2: Read the bulk revenue CSV
    print("Step 2: Reading bulk revenue CSV...")
    rev_rows = []
    with open(RAW_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rev_rows.append(row)
    print(f"  {len(rev_rows)} revenue line items.\n")

    # Step 3: Aggregate by country/year and GFS description (revenue stream)
    print("Step 3: Aggregating revenues by country, year, and revenue stream...")

    # Use GFS description as the revenue category
    # Aggregate at the GFS description level (broader than individual stream names)
    country_year_totals = defaultdict(float)
    country_year_streams = defaultdict(lambda: defaultdict(float))
    country_year_info = {}
    gfs_freq = defaultdict(int)

    for row in rev_rows:
        iso3 = row.get("iso3", "")
        year = row.get("year", "")
        country = row.get("country", "")
        gfs_desc = row.get("gfs_description", "").strip()
        if not gfs_desc:
            gfs_desc = "Unclassified"

        try:
            value_usd = float(row.get("value_reported_as_USD", 0) or 0)
        except (ValueError, TypeError):
            value_usd = 0.0

        key = (iso3, year)
        country_year_totals[key] += value_usd
        country_year_streams[key][gfs_desc] += value_usd

        if key not in country_year_info:
            country_year_info[key] = {
                "country_name": country,
                "country_iso3": iso3,
                "year": year,
            }

        gfs_freq[gfs_desc] += 1

    print(f"  {len(country_year_totals)} country-year combinations from bulk CSV.")
    print(f"  {len(gfs_freq)} distinct GFS categories.\n")

    # Sort GFS categories by frequency
    sorted_gfs = sorted(gfs_freq.items(), key=lambda x: -x[1])
    print("  GFS revenue categories (by frequency):")
    for cat, freq in sorted_gfs:
        print(f"    {cat}: {freq} line items")

    # All GFS categories as columns
    gfs_columns = [cat for cat, _ in sorted_gfs]

    # Step 4: Merge with API summary data and write output
    print(f"\nStep 4: Writing output CSV...")

    # Collect all country-year keys from both sources
    all_keys = set(country_year_totals.keys()) | set(summary_lookup.keys())

    base_cols = [
        "country_name", "country_iso2", "country_iso3", "year",
        "revenue_government_total_usd",
        "revenue_from_csv_sum_usd",
        "local_currency", "currency_rate_to_usd",
        "sector_oil", "sector_gas", "sector_mining",
    ]
    all_cols = base_cols + gfs_columns

    rows = []
    for key in sorted(all_keys, key=lambda k: (country_year_info.get(k, summary_lookup.get(k, {})).get("country_name", ""), k[1])):
        iso3, year = key
        api_info = summary_lookup.get(key, {})
        csv_info = country_year_info.get(key, {})

        row = {}
        row["country_name"] = api_info.get("country_name") or csv_info.get("country_name", "")
        row["country_iso2"] = api_info.get("country_iso2", "")
        row["country_iso3"] = iso3
        row["year"] = year
        row["revenue_government_total_usd"] = api_info.get("revenue_government_total_usd", "")
        row["revenue_from_csv_sum_usd"] = country_year_totals.get(key, "")
        row["local_currency"] = api_info.get("local_currency", "")
        row["currency_rate_to_usd"] = api_info.get("currency_rate_to_usd", "")
        row["sector_oil"] = api_info.get("sector_oil", "")
        row["sector_gas"] = api_info.get("sector_gas", "")
        row["sector_mining"] = api_info.get("sector_mining", "")

        for gfs in gfs_columns:
            val = country_year_streams.get(key, {}).get(gfs, "")
            row[gfs] = val if val != 0 else ""

        rows.append(row)

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_cols)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone! Saved {len(rows)} rows to:")
    print(f"  {OUTPUT_CSV}")
    print(f"\nColumns ({len(all_cols)} total):")
    for c in all_cols:
        print(f"  - {c}")

    # Quick summary stats
    print(f"\nSummary statistics:")
    countries = set(r["country_name"] for r in rows)
    years = set(r["year"] for r in rows)
    print(f"  Countries: {len(countries)}")
    print(f"  Year range: {min(years)} - {max(years)}")
    print(f"  Total rows: {len(rows)}")


if __name__ == "__main__":
    main()
