# Data guides — database index

One line per external database used by the pipeline. Convention for raw files:
`<source>_<content>_<date>.<ext>` — the trailing date is the **download vintage**
(YYYY-MM, from the file's download time) unless the name carries an explicit data
coverage (e.g. `1980-2023`). Layout reorganised 2026-07-22; the old→new rename map
is in `_raw_reorg_manifest_2026-07-22.txt` (git renames; untracked moves analogous).

This folder holds **codebooks / metadata only** — no pipeline inputs. Method PDFs
live in `docs/`.

## raw/cbcr/
| File | Source | Consumer |
|---|---|---|
| `oecd_cbcr_tableI_*.csv` (gitignored, ~465MB) | OECD Corporate Tax Statistics, CbCR Table I — https://data-explorer.oecd.org (DSD_CBCR@DF_CBCRI) | `1_clean.py` |
| `oecd_cbcr_reporters_over_time_*.xlsx` | own compilation from OECD CbCR | reference |
| `pcbcr/` (gitignored) | public CbCR report PDFs (provenance) | none (docs/pcbcr_us_noncompliance.md) |

## raw/tax_rates/
| File | Source | Consumer |
|---|---|---|
| `oecd_cit_rates_*.csv` | OECD Corporate Tax Statistics, CIT rates (DSD_TAX_CIT@DF_CIT) | `1_clean.py` |
| `taxfoundation_cit_rates_1980-2023.xlsx` | Tax Foundation, Corporate Tax Rates Around the World | `1_clean.py` (fallback rates) |
| `oecd_rsglobal_cit_revenue_t1200_s13_usd_2026-07.csv` | OECD Global Revenue Statistics (DSD_REV_COMP_GLOBAL@DF_RSGLOBAL, T_1200, S13) | `9j_paper_tables.py` (table3c) |

## raw/macro_variables/
| File | Source | Consumer |
|---|---|---|
| `wb_gdp_population_*.csv` | World Bank WDI bundle (SP.POP.TOTL, NY.GDP.MKTP.CD, …) | `1_clean.py` (config `gdp_population_data`) |
| `wb_gdp_current_usd_*.csv` | World Bank WDI NY.GDP.MKTP.CD | gravity features, `_fetch_canonical_gdp.py` |
| `wb_cpi_*.csv` | World Bank WDI FP.CPI.TOTL | `1_clean.py` (wage extrapolation) |
| `wb_tax_revenue_pct_gdp_*.csv` | World Bank WDI GC.TAX.TOTL.GD.ZS (**total central-gov tax, NOT CIT**) | `1_clean.py` (`tax_revenue_current_usd`) |
| `wb_trade_pct_gdp_*.csv` | World Bank WDI NE.TRD.GNFS.ZS | `1a` destination regressions |
| `wb_fx_official_rate_*.csv` | World Bank WDI PA.NUS.FCRF | extractive prep (LCU→USD) |
| `wb_remittances_received_*.csv` | World Bank WDI BX.TRF.PWKR.CD.DT | `1a` (remittance adjustment) |
| `ilo_wages_ear4mth_2025-08.csv` | ILO ILOSTAT EAR_4MTH_SEX_CUR_NB_A (monthly earnings) | `1_clean.py` (config `wage_data`) |
| `who_health_expenditure_*.xlsx` | WHO Global Health Expenditure Database | `1_clean.py` |
| `bls_us_cpi_annual.csv` | US BLS CUUR0000SA0 (hand-curated) | `config.deflator_to_base()` (2025-USD deflation), 9t |
| `manual_imputation_values.csv` | hand-maintained (sources inline per row) | `1_clean.py` — see docs/manual_macro_imputation_sources.md |

## raw/destination_based_sales/
| File | Source | Consumer |
|---|---|---|
| `oecd_aamne_mne_xvem_*.csv`, `oecd_aamne_xvem_*.csv` | OECD Analytical AMNE (2026 edition, 2008–2023, 81 countries; readme: `data/guides/oecd_aamne_readme_2026-07.xlsx`) | `1a_destination_based_sales.py` |
| `wto_dds_imports_*.csv` | WTO digitally-delivered-services bulk download | `1a` (DDS fallback) |
| `oecd_wto_batis_data_bpm6/` (gitignored, ~2.8GB) | OECD-WTO BaTIS BPM6 (codes: `guides/oecd_wto_batis_codes_bpm6/`) | `1a` (headline DDS leg) |
| `un_household_consumption_*.csv` | UN data, household consumption | `1a` (ADS proxy legacy) |
| `itu_internet_users_*.csv` | ITU, individuals using the internet | `1a` (ADS proxy legacy) |

## raw/country_info/
| File | Source | Consumer |
|---|---|---|
| `tjn_cthi_2025_scores.csv` | TJN Corporate Tax Haven Index 2025 | `config.py` (TAX_HAVENS_REPRESENTATION rule) |
| `tjn_portal_cthi_*.csv`, `tjn_portal_fsi_*.csv`, `tjn_portal_unilateral_cross_2024-06.csv` | TJN data portal | haven-list analyses |
| `un_g77_members.csv` | UN G77 membership | 9t context groupings |

## raw/context/
| File | Source | Consumer |
|---|---|---|
| `wb_imf_credit_outstanding_*.csv` | World Bank IDS DT.DOD.DIMF.CD | `9t` (IMF-credit comparison) |
| `crs_marshall_plan_aid.csv` | CRS report R45079 (hand-curated) | `9t` (Marshall-Plan comparison) |
| `debt_data/balmov2.txt` | World Bank IDS balances snapshot (hand-downloaded) | `9t` |
| `wb_oda_received_*.csv` | World Bank WDI ODA bundle | `1_clean.py` (config `oda_data`) |
| `climate_finance/` | CPI Landscape of Climate Finance in Africa 2024 (curated `cpi_africa_*.csv` are read; source xlsx gitignored) | `_build_taxloss_climate_comparison.py` |
| `sau_mof_budget_dashboard_2026.csv` | Saudi MoF Interactive Budget Dashboard export | manual_resource_revenue sourcing (SAU) |

## raw/extractive/ (extractive sub-pipeline)
See `docs/extractive/*.md`. Contains the curated resource tables
(`manual_resource_revenue.csv`, `resource_country_parameters.csv`, …), the
`resource_profits_manual_sources/{imf,government,company}` provenance documents
(ISO3_Doc_YEAR names; gitignored), `eiti_reports/` (EITI Summary-Data xlsx
templates, gitignored; consumed by `1_5*`), and the Orbis extractive extracts.

## raw/orbis/ (gitignored — proprietary)
Orbis pulls; bridge tables derived from them ARE committed under data/intermediate.
See docs/orbis_2024_variables_request.md. `company_segment_overrides.csv` (curated)
lives here too.

## raw/gravity/ (gitignored — large public downloads)
García-Bernardo & Janský (2024) gravity-imputation inputs. Kept as a self-contained
model-input bundle (not folded into macro_variables). See docs/gravity_features_sources.md.

## Superseded / never-used → data/archive/raw_superseded/
HEALTH_REAC_nurses.csv · EAR_EMTA (old ILO wage vintage) · Tax Revenue Data World
Bank.csv · portal_unilateral_cross.csv · cthi_unilateral_cross_scores.csv ·
education_expenditure_wb.csv

## Generated country dossiers → output/extractive/country_resource_info/
Moved out of raw/ 2026-07-22 (they are OUTPUTS of `country_resource_info.py`,
not inputs).
