# Orbis pull spec — extractive entity universe

What to extract from Orbis to (re)build `orbis_entity_universe.csv` (read by
`src/3_extractive_prep/1_7a_build_orbis_entity_universe.py`). The universe is
assembled from **three** extracts, all keyed on **BvD ID number**. Save the
results into `data/raw/orbis/` with the filename prefixes shown; the loader
globs `extractives_<kind>_orbis*.csv` so you can drop in multiple batch files.

## Entity / ID list to pull for

- **Entire universe** (re-extract everything): `data/intermediate/extractive/orbis_ENTIRE_universe_bvdids.tsv` — 612,911 BvD IDs (+ Company name). 1K-row batches in `orbis_entire_universe_batches/`.
- **Gap-fill only** (just the missing-revenue financials, limitation #2): `data/intermediate/extractive/orbis_financials_to_pull_ALL.tsv` — 82,495 BvD IDs. 1K-row batches in `orbis_pull_batches/`.
- Each file is a 2-column **tab-separated** list with a header row: `BvD ID` ⇥ `Company name`. Plain ID-only list: `orbis_financials_to_pull_BVDIDS_ONLY.txt`.

## Variables (exact Orbis names)

### 1. GUO / identification extract → `extractives_guo_orbis*.csv` (or .xlsx)
| Orbis variable | Used as |
|---|---|
| **BvD ID number** | entity key |
| **Name** (Company name) | entity name |
| **GUO - BvD ID number** | global ultimate owner id |
| **GUO - Name** | GUO name |
| **GUO - Type** | GUO entity type |
| **GUO - Country ISO code** | GUO (HQ) country |

> GUO = Global Ultimate Owner at Orbis' standard threshold (50%). Use the
> `GUO - …` column family (not "ISH"/"DUO").

### 2. Static / structure extract → `extractives_static_orbis*.csv`
| Orbis variable | Used as |
|---|---|
| **BvD ID number** | entity key |
| **Country ISO code** | entity country |
| **NACE Rev. 2, core code (4 digits)** | sector filter |
| **Number of subsidiaries** | the `n_subsidiaries ≥ 2` universe rule |

### 3. Financials extract → `extractives_financials_orbis*.csv`
| Orbis variable | Format | Used as |
|---|---|---|
| **BvD ID number** | — | entity key |
| **Operating revenue (Turnover)** | **th USD**, absolute, **one column per year 2016–2025** | the `peak revenue ≥ €750M` universe rule |

The loader takes the **peak** Operating revenue across the year columns, so any
subset of 2016–2025 works; pull the full range to match the existing schema.
Set currency = **USD**, units = **thousands**, values = **absolute** (not
trend/growth).

## After pulling

```
# drop files into data/raw/orbis/ as extractives_{guo,static,financials}_orbis_<batch>.csv
python src/3_extractive_prep/1_7a_build_orbis_entity_universe.py
```

`in_cbcr_universe = (Number of subsidiaries ≥ 2) OR (peak Operating revenue ≥ €750M ≈ 750,000 th USD)`.
