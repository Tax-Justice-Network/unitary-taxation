# EITI company payments → headquarter-country dataset

A sub-pipeline that takes the **company-level payments-to-government** disclosed by
EITI, attributes each paying company to a **headquarter (GUO) country** via the full
Orbis extractive-entity universe, and rolls the payments up to a **(HQ country ×
source country × commodity × fiscal year × revenue type)** table. GRD (the
Government Revenue Dataset) only has country-level totals — it carries no company or
HQ dimension — so this is the only way to get a bilateral (HQ, source) view of
extractive government revenue.

The output of this pipeline feeds `src/4_correcting_cbcr_for_resource_payments.py`,
which adds back the pre-profit payments to / removes the resource profit base from
CbCR profits to produce the `cbcr_main_{excl,incl}_resource[_floored].csv` datasets.

## Scripts (`src/3_extractive_prep/`)

| | does | reads | writes |
|---|---|---|---|
| `1_6_pull_eiti_company_payments_api.py` | **primary source.** Page through the EITI Open Data `/revenue` endpoint (~267k records); keep `type == "company"`; classify each row by GFS code → bucket; drop VAT/GST/turnover; USD-normalise | EITI API | `eiti_revenue_company_raw.jsonl`, `eiti_company_payments_long.csv` |
| `1_6_parse_eiti_company_payments.py` | **fallback / cross-check.** Parse the "Part 5 — Company data" sheet of every EITI v2 Summary-Data workbook; join Part-4 GFS; FX-convert via World-Bank rates | `data/raw/EITI reports/<Country>/*.xlsx*`, `data/raw/API_PA.NUS.FCRF_*.csv` | same `eiti_company_payments_long.csv` |
| `1_7a_build_orbis_entity_universe.py` | Build the full Orbis extractive-entity universe (~600k entities) from `data/raw/orbis/{guo,static,financials}_orbis*.csv` (+ 2 `guo` batches in `.xlsx`). Each entity carries its GUO bvd/name/type/country directly, plus `n_subsidiaries` and peak operating revenue. Flag `in_cbcr_universe = (n_subsidiaries >= 2) OR (peak revenue >= €750M)` — a multi-entity extractive group above the CbCR turnover threshold (revenue-missing ⇒ not disqualifying; batches 33/35/36/38/39/42 are missing in the raw pull → ~15% of entities have no revenue) | raw Orbis CSV/XLSX | `orbis_entity_universe.csv` |
| `1_7_match_eiti_companies_to_orbis.py` | For each (source country, EITI company), match the name against the Orbis universe **blocked by the country the payment is made in** (override → exact-normalised in country → substring in country → fuzzy in country → exact-normalised global → substring global, against the in-CbCR-universe anchor set). HQ country = the matched entity's `guo_country`; carry `in_cbcr_universe` for the gating in 1_8 | `eiti_company_payments_long.csv`, `orbis_entity_universe.csv` | `eiti_company_hq_map.csv` |
| `1_8_resource_payments_by_hq_source.py` | Build the full **resource-payment** panel: aggregate matched EITI payments by (source, HQ, commodity, year); gate the **domestic** EITI rows (`hq_iso3 == source_iso3`) on `in_cbcr_universe` (pure-domestic SDFI / NOC payments are kept out of scope); cascade-fill the non-EITI source countries with `manual > grd > rent_proxy`, splitting each country-total by `hq_share_<commodity>` with a `domestic_share` going to the source country's NOC | `eiti_company_payments_long.csv`, `eiti_company_hq_map.csv`, `extractive_royalty_dataset_yearly.csv`, `hq_shares_by_commodity_yearly.csv`, `data/raw/resources/manual_resource_revenue.csv` | `resource_payments_by_hq_source_yearly.csv`, `resource_payments_by_hq_source_coverage.csv` |
| `1_8_eiti_payments_by_hq_source.py` | (legacy) Same aggregation **EITI-only** — no cascade — for cross-checks / standalone bilateral views | the EITI files above | `eiti_payments_by_hq_source_yearly.csv`, `eiti_payments_by_hq_source_summary.csv` |
| `qa_resource_payment_correction.py` | structural + reconciliation checks across 1_6 → 4 | all of the above + the cbcr_main_* files | `output/extractive/tables/resource_payment_correction_qa.txt` |

All intermediates land in `data/intermediate/extractive/`.

## `eiti_company_payments_long.csv` — columns

`iso3` (source country), `fy_label / fy_start_year / fy_end_year`, `sector` (Mining/Oil/…),
`commodity` (oil_gas / coal / minerals / other), `company_name`, `government_entity`,
`revenue_stream` (the EITI stream label), `gfs_classification` (GFS code + label from the
API row, or from Part 4 in the Excel parser), `revenue_type` ∈ **{royalty_like, cit, equity, other}**,
`reporting_currency`, `value_local`, `value_usd`, `value_usd_status`
(reported_usd / fx_converted / no_currency / no_fx / dropped_outlier), `payment_in_kind`,
`in_kind_volume`, `source_file` (Excel parser) / `source_url` (API puller).

`revenue_type` buckets (keyword-classified, English + French + Spanish/Portuguese):

- **cit** — ordinary/extraordinary income tax, corporation tax, petroleum profits/income tax, supplemental petroleum tax, additional-profits/windfall/solidarity taxes, "impôt sur les sociétés", "impuesto sobre la renta", …
- **equity** — SOE dividends, state direct financial interest (SDFI/Petoro), state share of profit oil, "produced petroleum sold by the state" / crude-oil export sales by the NOC, carried interest, …
- **royalty_like** — royalties (incl. "redevance"/"regalía"), bonuses, production entitlements, licence/area/surface fees, customs/import & export duties, severance/extraction taxes, fines & penalties, exploration/exploitation fees, infrastructure & training-fund contributions, …
- **other** — everything else: CO₂/environmental taxes, payroll/social-security contributions, "government revenue not disaggregated by stream", unidentifiable acronyms, etc.
- VAT / GST / sales / turnover taxes are **not** in the dataset — those rows are dropped at parse time.

## `eiti_company_hq_map.csv` — columns

`source_iso3`, `company_name`, `n_payment_rows`, `value_usd`,
`match_method` (override / exact_norm_country / substring_country / fuzzy_country /
exact_norm_global / substring_global / unmatched), `match_score`,
`matched_bvd_id`, `matched_orbis_name`, `matched_guo_name`, `guo_type`,
`hq_iso3` (= matched entity's `guo_country`), `in_cbcr_universe`.

Unmatched companies are **dropped** by 1_8 (treated as local, per the project decision —
not redistributed by HQ shares).

## `resource_payments_by_hq_source_yearly.csv` — columns

`source_iso3`, `hq_iso3`, `commodity` ∈ {oil_gas, coal, minerals, unknown, other},
`year`, `pre_profit_payments_usd`, `post_profit_payments_usd`, `equity_income_usd`,
`other_payments_usd`, `data_source` ∈ {eiti_bilateral, manual_distributed,
grd_distributed, rent_proxy}.

- **pre_profit_payments_usd** — royalties, licence/area/surface fees, signature & production bonuses, production entitlements (expensed → NOT already in CbCR profit; added back to get the *before-resource-payments* dataset).
- **post_profit_payments_usd** — corporate income tax + special petroleum/mining taxes + windfall (the profit-based take — already deducted from CbCR profit).
- **equity_income_usd** — state dividends / state-participation income (out of post-tax profit).
- **other_payments_usd** — anything classified "other" by 1_6.

`resource_payments_by_hq_source_coverage.csv` is a (source × year) provenance table
showing which cascade layer each country fell into.

## Coverage & caveats (current run)

- EITI API pull: ~91.8k company rows, ~$2.84 trn USD-converted, 58 source countries (2007–2023). ~98k of 245k raw EITI records lacked a country/year link and were dropped (≈$540B / 18% of value — recoverable by dereferencing `organisation.summary_data`).
- **Company → HQ matching (1_7 against full Orbis universe):** ~**24% of distinct names** / ~**80% of payment value** matched (was 19% / 78% under the old broad-list matcher). HQ = the matched entity's GUO country. Top foreign HQs by matched value: India, China, UK, Canada, Germany (Wintershall Dea), US, Australia, Turkey.
- **Domestic gating in 1_8**: domestic EITI rows whose matched entity is NOT in the CbCR universe (pure-domestic operators, SDFI vehicles, sub-threshold NOCs) are kept OUT — ≈$358B of payments by such operators. Their host governments still collect the revenue; it just doesn't belong in a CbCR-based UT analysis.
- **Cascade for non-EITI source countries** (manual > GRD > rent-proxy, country totals split by `hq_share_<commodity>` × `domestic_share`):
  - **manual** — `data/raw/resources/manual_resource_revenue.csv` (252 rows, 25 countries). Sourced figures: SAU (MoF dashboard), RUS (MinFin federal-budget execution), CHN (MoF resource-tax), IND oil&gas (PPAC) + IND minerals (IBM annexures 2020-21/2021-22), ZAF (SARS MPRR royalty), UZB (MoF budget brief, partial), BRA oil&gas (ANP royalties+SP for 2021), MYS oil&gas (Petronas-contribution headlines, rough), LSO/LAO tiny estimates. Still flagged-estimate (priority to upgrade): Kuwait, UAE, Qatar, Iran, Algeria, Australia, USA (ONRR), Canada. Confidence column carried; sources documented in `docs/extractive/manual_resource_data_sources.md`.
  - **GRD** — UNU-WIDER country-level resource revenue, split pre/post/equity from the GRD tax breakdown, commodity-split via WB rents.
  - **rent_proxy** — WB total resource rents × an assumed government capture rate (`RENT_CAPTURE_RATE = 0.35`), only above `rents/GDP ≥ 0.5%`. ~71 minor source countries land here at low confidence.
- **Manual overrides EITI for PER & MEX** (`MANUAL_OVERRIDES_EITI` in 1_8) — Peru's SUNAT (2016–22) is ~65% larger than EITI for the 2016–20 overlap and EITI Peru is missing 2021–22 entirely; Mexico's EITI bilateral is very thin because Pemex doesn't file to EITI, so the manual table (Pemex fiscal contribution from SHCP / 20-F) is used instead.
- **Iraq quirk**: Iraq's EITI lists crude-oil *buyers* (Indian/Chinese/European refiners and trading houses) as "companies" making "payments" — so India / China etc. show up as large "HQs" for payments to the Iraqi government. These are state crude sales, not extractor taxes — interpret accordingly. Implausibly large single-row values (in-kind volumes mistaken for amounts; |value| > $50bn) are dropped at parse time.

## Re-run order

`1_6_pull_eiti_company_payments_api.py` → `1_7a_build_orbis_entity_universe.py` →
`1_7_match_eiti_companies_to_orbis.py` → `1_8_resource_payments_by_hq_source.py` →
(optional) `qa_resource_payment_correction.py`.

The legacy `1_8_eiti_payments_by_hq_source.py` can be re-run after `1_7` for a
pure-EITI bilateral view.
