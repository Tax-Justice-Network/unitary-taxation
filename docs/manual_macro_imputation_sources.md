# Manual macro / CIT / wage imputation — values + source links

Some jurisdictions (mostly small territories absent from the World Bank / ILO
panels) have their **GDP, population, CIT rate or average wage hand-filled** in
`1_clean.py` (§2.3a for GDP/population, the CIT overrides, §2.4 for wages). Those
values — which used to be **hard-coded in the script** — and their source links
now live **together** in a single hand-maintained CSV. This document is the
human-readable overview.

## Where the values + links live

The machine-readable file is **`data/raw/manual_imputation_values.csv`**
(`iso_partner, year, variable, value, mode, source_url, note`). `1_clean.py`
reads it via `load_manual_imputation_values()` and applies it with
`apply_manual_values()`.

- `variable` ∈ {`gdp_current_usd`, `population`, `cit`, `wage_monthly`} — the
  target column it fills (in `gdp_population`, `cits`, `wages`).
- `mode`: `fill_if_missing` (set only where currently NaN — GDP/pop and the
  `.isna()`-gated CITs) or `override` (set unconditionally — wages and the flat
  CITs such as GIB=0, CAF=0.3).
- **GDP / population** values are per `(iso_partner, year)` — different years
  often cite different vintages/sources.
- **Wage** and **CIT** values use a blank `year` (one figure applied to all years).
- For carry-over years that cite another year's figure without a fresh URL, the
  CSV carries that country's representative source URL (with a note).
- Any **FX conversion / unit arithmetic** the old code did inline (e.g.
  `287988e3 × 0.69`, `× eur_usd_2022`, `/12`) is **precomputed** into `value`;
  the original figure is described in `note`.
- **Derived CIT values stay in code** (computed, not curated): `MTQ←FRA`,
  `BVT←NOR`, and `MLT × 1/7`.

Everything not listed here is the standard base source: World Bank WDI
(`NY.GDP.MKTP.CD` / `SP.POP.TOTL`) for GDP/population, OECD / Tax Foundation for
CIT, and ILO (mean nominal monthly earnings, USD) for wages.

## Coverage

Jurisdictions with hand-filled values (a ✓ in **CIT** means a curated rate in
the CSV; `MTQ`/`BVT` CITs are derived in code and not shown here):

| ISO | GDP | Population | Wage | CIT |
|---|:---:|:---:|:---:|:---:|
| AIA Anguilla | ✓ | ✓ | ✓ | |
| AND Andorra | | | | ✓ |
| CAF Central African Rep. | | | | ✓ |
| COD DR Congo | | | | ✓ |
| COK Cook Islands | ✓ | ✓ | ✓ | |
| ERI Eritrea | ✓ | | | |
| FLK Falkland Islands | ✓ | ✓ | | |
| GGY Guernsey | ✓ | ✓ | ✓ | |
| GIB Gibraltar | ✓ | ✓ | ✓ | ✓ |
| GLP Guadeloupe | ✓ | ✓ | ✓ | ✓ |
| GUF French Guiana | ✓ | ✓ | ✓ | ✓ |
| HTI Haiti | | | | ✓ |
| IOT Brit. Indian Ocean Terr. | ✓ | ✓ | | ✓ |
| JEY Jersey | ✓ | ✓ | ✓ | |
| MAF Saint Martin | | | ✓ | |
| MCO Monaco | | | | ✓ |
| MHL Marshall Islands | | | | ✓ |
| MNP Northern Mariana Is. | ✓ | ✓ | | |
| MTQ Martinique | ✓ | ✓ | | |
| NCL New Caledonia | | | | ✓ |
| PLW Palau | | | | ✓ |
| PRK North Korea | ✓ | ✓ | | ✓ |
| PYF French Polynesia | | | | ✓ |
| REU Réunion | ✓ | ✓ | | ✓ |
| SMR San Marino | ✓ | ✓ | | ✓ |
| SOM Somalia | | | | ✓ |
| SSD South Sudan | ✓ | | | |
| TLS Timor-Leste | | | | ✓ |
| TWN Taiwan | ✓ | ✓ | ✓ | |
| VEN Venezuela | ✓ | | | |
| VGB British Virgin Is. | ✓ | ✓ | | |
| WLF Wallis & Futuna | ✓ | ✓ | ✓ | |
| XKV/XKX Kosovo | ✓ | ✓ | | ✓ |
| YEM Yemen | | | | ✓ |

The exact per-year values and URLs are in `data/raw/manual_imputation_values.csv`.
To add or revise a value or source, edit that CSV (and this doc). **Editing a
value changes the cleaned dataset** (unlike the old sources-only file, the CSV is
now consumed by `1_clean.py`).
