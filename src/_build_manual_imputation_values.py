"""One-time migration generator for ``data/raw/manual_imputation_values.csv``.

Historically the manually-collected macro values for small territories
(GDP, population, wages) and the CIT overrides lived hard-coded inside
``1_clean.py``.  This script captures those exact values (verbatim
expressions, so the numbers are bit-identical) and merges in the source
URLs / notes that previously lived in the standalone
``manual_imputation_sources.csv`` — producing one combined, hand-maintainable
file ``manual_imputation_values.csv`` with columns:

    iso_partner, year, variable, value, mode, source_url, note

``mode``:
    fill_if_missing  — only set the cell if it is currently NaN (GDP/pop and
                       the ``.isna()``-gated CIT overrides).
    override         — set unconditionally (wages and the flat CIT overrides).
``year`` blank  — applies to every row for that ``iso_partner`` (year-agnostic).

Derived CIT values stay in ``1_clean.py`` (they are computed, not curated):
  - MTQ ← FRA, BVT ← NOR  (copied from another jurisdiction each year)
  - MLT  *= 1/7           (multiplicative 5/6 refund adjustment)

After this migration the CSV is the source of truth and is edited by hand; the
guard below refuses to clobber an existing file so re-running can never wipe
hand edits.  Delete the CSV first if you genuinely want to regenerate.
"""

from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RAW = _PROJECT_ROOT / "data" / "raw"
_OUT = _RAW / "manual_imputation_values.csv"
_OLD_SOURCES = _RAW / "manual_imputation_sources.csv"

# FX constants used by the GDP fills (verbatim from 1_clean.py).
eur_usd_2022 = 1.0530
gbp_usd_2022 = 1.0530 / 0.852601

records = []


def add(iso, year, variable, value, mode):
    records.append(
        {
            "iso_partner": iso,
            "year": year,
            "variable": variable,
            "value": value,
            "mode": mode,
        }
    )


def add_year_dict(iso, variable, mapping, mode="fill_if_missing"):
    for year, value in mapping.items():
        add(iso, year, variable, value, mode)


# ---------------------------------------------------------------------------
# 2.3a GDP / population manual fills  (fill_if_missing)
# ---------------------------------------------------------------------------

# Anguilla
add_year_dict(
    "AIA",
    "gdp_current_usd",
    {
        2016: 331 * 1e6,
        2017: 322 * 1e6,
        2018: 322 * 1e6,
        2019: 380 * 1e6,
        2020: 380 * 1e6,
        2021: 380 * 1e6,
        2022: 388_972_051,
    },
)
add_year_dict(
    "AIA",
    "population",
    {
        2016: 14.3 * 1e3,
        2017: 14.4 * 1e3,
        2018: 14.7 * 1e3,
        2019: 14.8 * 1e3,
        2020: 14.8 * 1e3,
        2021: 14.5 * 1e3,
        2022: 14_180,
    },
)

# British Indian Ocean Territory  (year-agnostic: filled for every year)
add("IOT", None, "gdp_current_usd", 1e6, "fill_if_missing")
add("IOT", None, "population", 3000, "fill_if_missing")

# British Virgin Islands
add_year_dict(
    "VGB",
    "gdp_current_usd",
    {
        2016: 1279 * 1e6,
        2017: 1279 * 1e6,
        2018: 1653 * 1e6,
        2019: 1653 * 1e6,
        2020: 1653 * 1e6,
        2021: 1653 * 1e6,
        2022: 1_471_233_257,
    },
)
add("VGB", 2022, "population", 38_319, "fill_if_missing")

# Cook Islands
add_year_dict(
    "COK",
    "gdp_current_usd",
    {
        2016: 287988 * 1e3 * 0.69,
        2017: 345587 * 1e3 * 0.7,
        2018: 391959 * 1e3 * 0.67,
        2019: 593585 * 1e3 * 0.64,
        2020: 397791 * 1e3 * 0.7,
        2021: 349192 * 1e3 * 0.71,
        2022: 289_749_646,
    },
)
add_year_dict(
    "COK",
    "population",
    {
        2016: 15076,
        2017: 15076,
        2018: 15153,
        2019: 15216,
        2020: 15281,
        2021: 15342,
        2022: 14_723,
    },
)

# Eritrea
add_year_dict(
    "ERI",
    "gdp_current_usd",
    {
        2016: 2.21 * 1e9,
        2017: 1.9 * 1e9,
        2018: 2.01 * 1e9,
        2019: 1.98 * 1e9,
        2020: 1.98 * 1e9,
        2021: 1.98 * 1e9,
    },
)

# French Guiana
add_year_dict(
    "GUF",
    "gdp_current_usd",
    {
        2016: 4131 / 0.904 * 1e6,
        2017: 4127 / 0.8865 * 1e6,
        2018: 4353 * 1.1811 * 1e6,
        2019: 4431 * 1.11 * 1e6,
        2020: 4275 * 1.21 * 1e6,
        2021: 4450 * 1.13 * 1e6,
        2022: 4562 * eur_usd_2022 * 1e6,
    },
)
add_year_dict(
    "GUF",
    "population",
    {
        2016: 267821,
        2017: 275191,
        2018: 282938,
        2019: 281678,
        2020: 285133,
        2021: 286618,
        2022: 288382,
    },
)

# Falkland Islands
add("FLK", 2016, "gdp_current_usd", 206.4 * 1e6, "fill_if_missing")
add_year_dict(
    "FLK",
    "population",
    {
        2016: 3478,
        2017: 3518,
        2018: 3521,
        2019: 3517,
        2020: 3506,
        2021: 3490,
    },
)

# Gibraltar
add_year_dict(
    "GIB",
    "gdp_current_usd",
    {
        2016: 2.344 * 1.3349 * 1e9,
        2017: 2.344 * 1.3349 * 1e9,
        2018: 2.344 * 1.3349 * 1e9,
        2019: 2.344 * 1.3349 * 1e9,
        2020: 2.344 * 1.3349 * 1e9,
        2021: 2.344 * 1.3349 * 1e9,
    },
)
add("GIB", 2022, "population", 37_936, "fill_if_missing")

# Guadeloupe
add_year_dict(
    "GLP",
    "gdp_current_usd",
    {
        2016: 8712.316 / 0.904 * 1e6,
        2017: 8803.461 / 0.8865 * 1e6,
        2018: 9025.467 * 1.1811 * 1e6,
        2019: 9268.066 * 1.11 * 1e6,
        2020: 8857.257 * 1.21 * 1e6,
        2021: 9169.070 * 1.13 * 1e6,
        2022: 9877.241 * eur_usd_2022 * 1e6,
    },
)
add_year_dict(
    "GLP",
    "population",
    {
        2016: 395700,
        2017: 402119,
        2018: 402119,
        2019: 384239,
        2020: 383559,
        2021: 384315,
        2022: 383569,
    },
)

# Guernsey
add_year_dict(
    "GGY",
    "gdp_current_usd",
    {
        2016: 2934 * 1.3552 * 1e6,
        2017: 3101 * 1.289 * 1e6,
        2018: 3170 * 1.3349 * 1e6,
        2019: 3248 * 1e6 * 1.31,
        2020: 3125 * 1e6 * 1.32,
        2021: 3446 * 1e6 * 1.34,
        2022: 3349 * gbp_usd_2022 * 1e6,
    },
)
add_year_dict(
    "GGY",
    "population",
    {
        2016: 61908,
        2017: 62046,
        2018: 62506,
        2019: 62885,
        2020: 63156,
        2021: 63664,
        2022: 63950,
    },
)

# Jersey
add_year_dict(
    "JEY",
    "gdp_current_usd",
    {
        2016: 4.11 * 1.3552 * 1e9,
        2017: 4.304 * 1.289 * 1e9,
        2018: 4.642 * 1.3349 * 1e9,
        2019: 4.885 * 1.31 * 1e9,
        2020: 4.528 * 1.32 * 1e9,
        2021: 5.087 * 1.34 * 1e9,
        2022: 5761 * gbp_usd_2022 * 1e6,
    },
)
add_year_dict(
    "JEY",
    "population",
    {
        2016: 102200,
        2017: 102700,
        2018: 103300,
        2019: 103200,
        2020: 103300,
        2021: 103100,
        2022: 103300,
    },
)

# Kosovo  (both ISO variants get the same values; whichever exists is filled)
_kosovo_gdp = {
    2016: 6.68 * 1e9,
    2017: 7.18 * 1e9,
    2018: 7.88 * 1e9,
    2019: 7.9 * 1e9,
    2020: 7.73 * 1e9,
    2021: 9.42 * 1e9,
    2022: 9_375_000_000,
}
_kosovo_pop = {
    2016: 1777557,
    2017: 1791003,
    2018: 1797085,
    2019: 1788878,
    2020: 1790133,
    2021: 1786038,
}
for _iso in ("XKX", "XKV"):
    add_year_dict(_iso, "gdp_current_usd", _kosovo_gdp)
    add_year_dict(_iso, "population", _kosovo_pop)

# Northern Mariana Islands
add_year_dict(
    "MNP",
    "gdp_current_usd",
    {
        2016: 1230 * 1e6,
        2017: 1560 * 1e6,
        2018: 1301 * 1e6,
        2019: 1181 * 1e6,
        2020: 858 * 1e6,
        2021: 1181 * 1e6,
        2022: 1_096_000_000,
    },
)
add("MNP", 2022, "population", 46_078, "fill_if_missing")

# Martinique
add("MTQ", 2021, "gdp_current_usd", 9459 * 1e6 * 1.12, "fill_if_missing")
add("MTQ", 2022, "gdp_current_usd", 9653.712 * eur_usd_2022 * 1e6, "fill_if_missing")
add_year_dict(
    "MTQ",
    "population",
    {
        2016: 378865,
        2017: 371502,
        2018: 364089,
        2019: 359611,
        2020: 356615,
        2021: 353278,
        2022: 361019,
    },
)

# North Korea
add("PRK", 2016, "gdp_current_usd", 772921776, "fill_if_missing")

# Réunion
add_year_dict(
    "REU",
    "gdp_current_usd",
    {
        2016: 18065 / 0.904 * 1e6,
        2017: 18555 / 0.8865 * 1e6,
        2018: 18822 * 1.1811 * 1e6,
        2019: 19367 * 1.11 * 1e6,
        2020: 19032 * 1.21 * 1e6,
        2021: 20412 * 1.13 * 1e6,
        2022: 21668.213 * eur_usd_2022 * 1e6,
    },
)
add_year_dict(
    "REU",
    "population",
    {
        2016: 926628,
        2017: 932739,
        2018: 941187,
        2019: 861210,
        2020: 863083,
        2021: 871157,
        2022: 881348,
    },
)

# San Marino
add_year_dict(
    "SMR",
    "gdp_current_usd",
    {
        2016: 1.468 * 1e9,
        2017: 1.529 * 1e9,
        2018: 1.655 * 1e9,
        2019: 1.616 * 1e9,
        2020: 1.541 * 1e9,
        2021: 1.855 * 1e9,
        2022: 1_833_000_000,
    },
)
add_year_dict(
    "SMR",
    "population",
    {
        2016: 33834,
        2017: 34056,
        2018: 34156,
        2019: 34178,
        2020: 34007,
        2021: 33745,
    },
)

# Saint Martin
add("MAF", 2021, "gdp_current_usd", 649_206_263, "fill_if_missing")
add("MAF", 2022, "population", 28_870, "fill_if_missing")

# South Sudan
add_year_dict(
    "SSD",
    "gdp_current_usd",
    {
        2016: 2.9 * 1e9,
        2017: 1.8 * 1e9,
        2018: 3.12 * 1e9,
        2019: 4.04 * 1e9,
        2020: 5.42 * 1e9,
        2021: 5.94 * 1e9,
        2022: 5_317_000_000,
    },
)
add("SSD", 2022, "population", 11_000_000, "fill_if_missing")

# Taiwan
add_year_dict(
    "TWN",
    "gdp_current_usd",
    {
        2016: 543.08 * 1e9,
        2017: 590.73 * 1e9,
        2018: 609.2 * 1e9,
        2019: 611.4 * 1e9,
        2020: 673.18 * 1e9,
        2021: 773.04 * 1e9,
        2022: 765_624_000_000,
    },
)
add_year_dict(
    "TWN",
    "population",
    {
        2016: 23512136,
        2017: 23665024,
        2018: 23726185,
        2019: 23674138,
        2020: 23663459,
        2021: 23663459,
        2022: 23_420_111,
    },
)

# Venezuela
add_year_dict(
    "VEN",
    "gdp_current_usd",
    {
        2016: 112.92 * 1e9,
        2017: 115.88 * 1e9,
        2018: 102.02 * 1e9,
        2019: 73 * 1e9,
        2020: 43.79 * 1e9,
        2021: 57.67 * 1e9,
        2022: 89_013_000_000,
    },
)
add("VEN", 2022, "population", 28_213_017, "fill_if_missing")

# Wallis and Futuna
add_year_dict(
    "WLF",
    "gdp_current_usd",
    {
        2016: 139500 * 1e3,
        2017: 139500 * 1e3,
        2018: 139500 * 1e3,
        2019: 139500 * 1e3,
        2020: 139500 * 1e3,
        2021: 139500 * 1e3,
    },
)
add_year_dict(
    "WLF",
    "population",
    {
        2016: 12060,
        2017: 11936,
        2018: 11816,
        2019: 11502,
        2020: 11441,
        2021: 11369,
        2022: 11_478,
    },
)

# ---------------------------------------------------------------------------
# CIT overrides
# ---------------------------------------------------------------------------
# Flat overrides (unconditional, every year).
for _iso, _val in {
    "GIB": 0,
    "MCO": 0,
    "AND": 0,
    "CAF": 0.3,
    "HTI": 0.3,
    "YEM": 0.2,
    "NCL": 0,
}.items():
    add(_iso, None, "cit", _val, "override")

# Fill-if-missing overrides.
for _iso, _val in {
    "PRK": 0.325,
    "COD": 0.28,
    "TLS": 0.10,
    "MHL": 0,
    "GLP": 0.15,
    "GUF": 0.28,
    "IOT": 0,
    "PLW": 0,
    "PYF": 0.27,
    "REU": 0.15,
    "SOM": 0.3,
    "XKV": 0.1,
    "SMR": 0.17,
}.items():
    add(_iso, None, "cit", _val, "fill_if_missing")

# ---------------------------------------------------------------------------
# 2.4 Wages  (unconditional override, every year)
# ---------------------------------------------------------------------------
for _iso, _val in {
    "AIA": 74620.18 / 12,
    "COK": 2913.46,
    "GGY": 9859.02,
    "GIB": 4462,
    "GLP": 2277.85,
    "GUF": 16983.03 / 12,
    "JEY": 1098.36 * 4,
    "MAF": 46000 / 12,
    "TWN": 21689 / 12,
    "WLF": 625.75,
}.items():
    add(_iso, None, "wage_monthly", _val, "override")


# ---------------------------------------------------------------------------
# Assemble + merge source URLs / notes from the legacy sources file.
# ---------------------------------------------------------------------------
out = pd.DataFrame.from_records(records)
out["year"] = out["year"].astype("Int64")

src_lookup = {}
if _OLD_SOURCES.exists():
    old = pd.read_csv(_OLD_SOURCES)
    for _, r in old.iterrows():
        yr = r["year"]
        yr = int(yr) if pd.notna(yr) and str(yr).strip() != "" else None
        src_lookup[(r["iso_partner"], yr, r["variable"])] = (
            r.get("source_url", ""),
            r.get("note", ""),
        )


def _lookup(row):
    yr = int(row["year"]) if pd.notna(row["year"]) else None
    key = (row["iso_partner"], yr, row["variable"])
    if key in src_lookup:
        return src_lookup[key]
    # year-agnostic fallback (wages stored with blank year in old file)
    key2 = (row["iso_partner"], None, row["variable"])
    return src_lookup.get(key2, ("", ""))


out[["source_url", "note"]] = out.apply(
    lambda r: pd.Series(_lookup(r)), axis=1
)

out = out[
    ["iso_partner", "year", "variable", "value", "mode", "source_url", "note"]
]
out = out.sort_values(["variable", "iso_partner", "year"]).reset_index(drop=True)

if _OUT.exists():
    raise SystemExit(
        f"{_OUT} already exists — refusing to overwrite hand-maintained file. "
        "Delete it first if you really want to regenerate."
    )

out.to_csv(_OUT, index=False)
print(f"Wrote {len(out)} rows to {_OUT.name}")
print(out.groupby(["variable", "mode"]).size().to_string())
