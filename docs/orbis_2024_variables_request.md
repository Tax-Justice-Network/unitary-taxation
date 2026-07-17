# Orbis 2024 data request — variable checklist

Ordering checklist for the new Orbis datahub pull (catalog:
`docs/ub-datahub_orbis_2024.txt`). Use the **2024 vintage** of every table —
suffix **`_20240416`** — and the **EUR** currency variant wherever a currency
split exists (`*_eur_*`), to match the rest of the pipeline (real EUR).

> **Currency note.** `key_financials_eur_*` and `detailed_format_industries_eur_*`
> report **absolute EUR** (verified: Walmart `US710415188` ≈ €563bn), *not*
> thousands. The legacy extractive web-exports were in **thousands USD**;
> switching those inputs to these EUR tables removes a currency-conversion step.

> **⚠️ Ownership is NOT in this catalog.** The datahub list contains only
> financial + descriptive/identification tables. There is **no** shareholders /
> subsidiaries / GUO table in it (the `dmc_*` tables are *Directors, Managers &
> Contacts* — people, not ownership). The HQ↔market nexus
> (`1e_orbis_presence_matrix.py`, the Pass-2 GUO-50 expansion) and the extractive
> HQ-share GUO dedup all depend on ownership links, so the Orbis **ownership
> database** feed (the `Links` / `Links_current` product, with **GUO 50**) must be
> ordered **separately** alongside this request.

---

## Tier 1 — Essential (CbCR-universe build consumes these today)

### `key_financials_eur_20240416`
The workhorse table. Drives the consolidated-turnover ≥ €750M screen in
`build_cbcr_universe_pass1_financials.py` and carries the misalignment-relevant
financials. Only 25 columns — simplest to take the whole table. Columns the
pipeline actually uses:

| Column | Why |
|---|---|
| `BVD_ID` | entity key |
| `CONSOLIDATION_CODE` | C1/C2 (consolidated) filter |
| `CLOSING_DATE` | statement year |
| `NUMBER_OF_MONTHS` | annualisation sanity check |
| `ORIGINAL_CURRENCY` | currency sanity / conversion check |
| `OPERATING_REVENUE` | **the €750M screen** |
| `P_L_BEFORE_TAX` | profit |
| `TOTAL_ASSETS` | assets |
| `NUMBER_OF_EMPLOYEES` | employees |

*Pass 1 reads columns by case-insensitive header name, so column order in the
extract does not matter — only that these headers are present.*

---

## Tier 2 — Identification & matching
Entity → country / sector / parent. Needed for the extractive HQ matching and the
nexus, and to migrate that logic off the ad-hoc web-export CSVs onto the datahub.

### `contact_info_20240416`
| Column | Why |
|---|---|
| `BVD_ID` | key |
| `NAME_INTERNAT` | company name (matching) |
| `COUNTRY` | entity country |
| `COUNTRY_ISO_CODE` | entity jurisdiction ISO |

### `industry_classifications_20240416`
| Column | Why |
|---|---|
| `BVD_ID` | key |
| `NACE_REV_2_MAIN_SECTION` | sector screen |
| `NACE_REV_2_CORE_CODE` | extractive filter (Section B + 1920 + 4671) |
| `NACE_REV_2_PRIMARY_CODE` | extractive filter |
| `NACE_REV_2_SECONDARY_CODE` | extractive filter |
| `BVD_MAJOR_SECTOR` | coarse sector |

### `legal_info_20240416`
| Column | Why |
|---|---|
| `BVD_ID` | key |
| `STATUS` | active/inactive screen |
| `STANDARDISED_LEGAL_FORM` | entity-form screen |
| `TYPE_OF_ENTITY` | SOE / entity-type screen |
| `CATEGORY_OF_THE_COMPANY` | size/category |

### `identifiers_20240416`
| Column | Why |
|---|---|
| `BVD_ID` | key |
| `LEI` | match EITI company payments → Orbis HQ |
| `ISIN_NUMBER` | matching |
| `NATIONAL_ID_NUMBER` | matching |
| `VAT_TAX_NUMBER` | matching |

### `bvd_id_and_name_20240416`
`BVD_ID`, `NAME` — lightweight name lookup (skip if taking full `contact_info`).

---

## Tier 3 — Optional richer financials
Only if you want tangible assets / a fuller P&L straight from Orbis rather than
from the CbCR data.

### `detailed_format_industries_eur_20240416`
| Column | Why |
|---|---|
| `BVD_ID` | key |
| `CONSOLIDATION_CODE`, `CLOSING_DATE` | join keys |
| `NET_PROPERTY_PLANT_EQUIPMENT` | tangible assets (misalignment factor) |
| `INTANGIBLES`, `GOODWILL` | intangibles variants |
| `EARNINGS_BEFORE_TAX` | profit |
| `INCOME_TAXES` | tax |
| `NUMBER_OF_EMPLOYEES` | employees |

Financial-sector coverage (banks/insurers report differently): add
`banks_global_financials_and_ratios_eur_20240416` and
`insurances_global_financials_and_ratios_eur_20240416` if needed.

---

## Order separately — Ownership / `Links` product (not in this catalog)

The datahub catalog has **no** ownership table, so the ownership feed must be
ordered as its own product. Today the pipeline streams a BvD **Links** flatfile
(`D:\data\Orbis_raw\Ownership histo June text\Links_current.txt`, ~281 GB). Each
row is one **ownership link** (shareholder → subsidiary); BvD IDs encode the
country in their first two characters (mapped to ISO3 downstream).

### What the pipeline reads today (the must-haves)

`1e_orbis_presence_matrix.py` and the Pass-2 awk filter read these three fields
**by column position** — col `0`, col `11`, col `13` — so the link-level layout
must keep them (or be re-indexed):

| Field | Role in pipeline |
|---|---|
| **Subsidiary `BvD ID`** (col 0) | subsidiary/entity; first 2 chars → **market** ISO |
| **Active / archived** flag (col 11) | keep only `active` links |
| **`GUO 50`** — global ultimate owner > 50% BvD ID (col 13) | first 2 chars → **HQ / source** ISO; drives the HQ↔market nexus and the Pass-2 GUO-50 expansion of in-scope groups |

> If the new ownership extract changes column order, update the positional
> indices in `1e_orbis_presence_matrix.py` (`p[0]`, `p[11]`, `p[13]`) and the
> Pass-2 awk filter — or switch them to header-name lookup like Pass 1 does.

### Recommended fields to request

**Essential**
- `Subsidiary BvD ID number`
- `Active / archived` (link status)
- `GUO 50 – BvD ID number` (global ultimate owner > 50%)

**Strongly recommended (used by the extractive HQ-share side; future-proofs the nexus)**
- `GUO 50 – Name`
- `GUO 50 – Country ISO code`
- `GUO 50 – Type` (entity type of the ultimate owner)
- `Shareholder BvD ID number` + `Shareholder name` (immediate owner)
- `Shareholder country ISO code`
- `Direct %` and `Total %` ownership (for thresholding beyond the 50% GUO rule)

**Useful extras (optional)**
- `DUO 50 – BvD ID` (domestic ultimate owner) — for domestic-vs-foreign HQ splits
- `Information date` / source — vintage of the link
- `Subsidiary name`, `Subsidiary country ISO code` (saves a join back to the
  entity tables for country, though the BvD-ID prefix already encodes it)

> **Currency:** the Links file has no monetary fields the pipeline relies on, so
> no EUR/USD choice applies here.

---

## Quick reference — table → role

| Table (2024 EUR) | Role | Tier |
|---|---|---|
| `key_financials_eur_20240416` | turnover/profit/assets/employees; €750M screen | 1 |
| `contact_info_20240416` | entity country + name | 2 |
| `industry_classifications_20240416` | NACE sector codes | 2 |
| `legal_info_20240416` | status / entity type | 2 |
| `identifiers_20240416` | LEI/ISIN/IDs for matching | 2 |
| `bvd_id_and_name_20240416` | name lookup | 2 |
| `detailed_format_industries_eur_20240416` | tangible assets, full P&L | 3 |
| *(separate)* `Links` / ownership | GUO-50, subsidiaries | — |

---

## Integration notes (dropping the new tables into the pipeline)

### Pass 1 — `build_cbcr_universe_pass1_financials.py`
No `usecols` to change: Pass 1 streams the flatfile and resolves columns by
**case-insensitive header name** (`"bvd id number"`, `"consolidation code"`,
`"closing date"`, `"operating revenue (turnover)"`). The `key_financials_eur_20240416`
extract ships those exact headers, so the only edit is the file path:

```python
# src/3_extractive_prep/build_cbcr_universe_pass1_financials.py
FIN = Path(r"D:\data\Orbis_raw\<new 2024 folder>\key_financials_eur_20240416.txt")
# THRESHOLD_EUR and YEARS unchanged; widen YEARS if the new vintage adds 2024 closers:
# YEARS = set(range(2016, 2025))
```

### Tier-2 tables — pandas `usecols` (header names exactly as in the catalog)

```python
USECOLS = {
    "contact_info_20240416": [
        "BVD_ID", "NAME_INTERNAT", "COUNTRY", "COUNTRY_ISO_CODE",
    ],
    "industry_classifications_20240416": [
        "BVD_ID", "NACE_REV_2_MAIN_SECTION", "NACE_REV_2_CORE_CODE",
        "NACE_REV_2_PRIMARY_CODE", "NACE_REV_2_SECONDARY_CODE", "BVD_MAJOR_SECTOR",
    ],
    "legal_info_20240416": [
        "BVD_ID", "STATUS", "STANDARDISED_LEGAL_FORM", "TYPE_OF_ENTITY",
        "CATEGORY_OF_THE_COMPANY",
    ],
    "identifiers_20240416": [
        "BVD_ID", "LEI", "ISIN_NUMBER", "NATIONAL_ID_NUMBER", "VAT_TAX_NUMBER",
    ],
    "key_financials_eur_20240416": [
        "BVD_ID", "CONSOLIDATION_CODE", "CLOSING_DATE", "NUMBER_OF_MONTHS",
        "ORIGINAL_CURRENCY", "OPERATING_REVENUE", "P_L_BEFORE_TAX",
        "TOTAL_ASSETS", "NUMBER_OF_EMPLOYEES",
    ],
}
# pd.read_csv(path, sep="\t", usecols=USECOLS[name], dtype=str)  # parse numerics after
```

> The catalog lists headers in `UPPER_SNAKE_CASE` (e.g. `OPERATING_REVENUE`), but
> some Orbis flatfile exports ship the human-readable form (`Operating revenue
> (Turnover)`). Confirm the actual header row of the delivered files and adjust
> `usecols` to match — or load with `dtype=str` and rename by position.
