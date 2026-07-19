"""Fetch the canonical GDP series (WB WDI NY.GDP.MKTP.CD, GDP current US$) for the
CbCR window and write the single repo-wide GDP file.

This is the ONE canonical GDP per country-year used across the repo — the CbCR
pipeline (`1_clean.py`) and the extractive WB-GDP reference (`2_4`). Run
deliberately to refresh (it is a *dated* snapshot, so the pipeline stays
reproducible between refreshes).

    python src/_fetch_canonical_gdp.py

Writes: data/raw/wb_gdp_current_usd.csv  (iso3, year, gdp_current_usd)
"""
import csv
import json
import os
import urllib.request
from datetime import date

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "data", "raw", "wb_gdp_current_usd.csv")
INDICATOR = "NY.GDP.MKTP.CD"
YEARS = "2016:2022"


def main():
    rows, page = [], 1
    while True:
        url = (f"https://api.worldbank.org/v2/country/all/indicator/{INDICATOR}"
               f"?format=json&per_page=8000&date={YEARS}&page={page}")
        with urllib.request.urlopen(url) as r:
            meta, data = json.load(r)
        for x in data or []:
            if x["value"] is not None:
                rows.append((x["countryiso3code"], int(x["date"]), x["value"]))
        if page >= meta["pages"]:
            break
        page += 1

    import pycountry
    iso_ok = {c.alpha_3 for c in pycountry.countries}
    rows = sorted(t for t in rows if t[0] in iso_ok)   # drop WB aggregate rows

    hdr = (
        f"# Canonical GDP: World Bank WDI indicator {INDICATOR} (GDP, current US$),\n"
        f"# all reporting countries, {YEARS.replace(':', '-')}. Fetched {date.today()} from\n"
        f"# https://api.worldbank.org/v2/country/all/indicator/{INDICATOR} . WB aggregate\n"
        "# rows dropped (iso3 filtered against pycountry). SINGLE canonical GDP for the repo\n"
        "# (CbCR pipeline + extractive WB-GDP reference). Refresh: re-run this script.\n"
    )
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        f.write(hdr)
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["iso3", "year", "gdp_current_usd"])
        w.writerows(rows)
    print(f"wrote {OUT}: {len(rows)} rows")


if __name__ == "__main__":
    main()
