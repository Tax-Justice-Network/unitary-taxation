# =============================================================================
# Pipeline configuration.
#
# Update this file before running the analysis for another year and after
# storing the most up-to-date raw data. Contents:
#
#   1. Analysis period
#   2. Project folders
#   3. Output layout (where results are written)
#   4. Constant-dollar conversion
#   5. Raw data files
#   6. Extractive-pipeline intermediates
#   7. Tax-haven lists
#   8. Data-quality exclusions
#   9. Country groups and display names
# =============================================================================


# ── 1. Analysis period ───────────────────────────────────────────────────────

# First year of the analysis window.
first_year = 2016

# Number of years to analyse (window = first_year .. first_year + n_years − 1).
n_years = 7


# ── 2. Project folders ───────────────────────────────────────────────────────
# All paths are built from this file's own location, so scripts work no matter
# which directory they are run from. Only the current analysis year lives
# here; previous years are kept in data/archive and output/archive.

import sys as _sys
from pathlib import Path as _Path

_src_dir = _Path(__file__).resolve().parent
_project_root = _src_dir.parent

data_raw = str(_project_root / "data" / "raw") + "/"
data_intermediate = str(_project_root / "data" / "intermediate") + "/"
# Extractive sub-pipeline intermediate products (EITI-cleaned panels,
# calibrated rent fractions, BGS scaling, combined/per-mineral rents, the
# consolidated royalty panel, HQ shares). Produced by src/3_extractive_prep/.
data_intermediate_extractive = (
    str(_project_root / "data" / "intermediate" / "extractive") + "/"
)
data_final = str(_project_root / "data" / "final") + "/"

output_root = _project_root / "output"

# Make the extractive-prep helpers importable from any src/ script (e.g.
# `from _reference_prices import MINERAL_PRICES`). The prep scripts in
# src/3_extractive_prep/ already have that dir on sys.path; this adds it
# for the top-level src/ scripts too (they all do `from config import *`).
_extractive_prep_dir = str(_src_dir / "3_extractive_prep")
if _extractive_prep_dir not in _sys.path:
    _sys.path.insert(0, _extractive_prep_dir)

# Also expose src/ itself for shared modules at the top of src/ (e.g.
# `from _etr_construction import compute_partner_year_etrs`).
_src_dir_str = str(_src_dir)
if _src_dir_str not in _sys.path:
    _sys.path.insert(0, _src_dir_str)


# ── 3. Output layout ─────────────────────────────────────────────────────────
# The output/ tree mirrors the paper ("Unitary taxation.docx" + its Appendix):
#
#   output/
#     paper/            The exhibits exactly as numbered in the documents.
#       main_text/        Figures 1-10 and Tables 1-4 of the main paper.
#       appendix/         Figures/tables of the Appendix document (B-H).
#     estimates/        Full estimation output, one folder per scenario.
#       reported_only/    Main sample: directly reported CbCR rows only.
#       with_imputed_rows/  Full sample: aggregate rows disaggregated by the
#                           gravity model (used in Appendix F).
#         1_resources_ignored/            scenario 1
#         2_resources_excluded/           scenario 2
#         3_minimum_royalty_added/        scenario 3
#         resources_included_reference/   reference dataset (not a paper scenario)
#         positive_profits_only/          upper bound for loss consolidation
#                                         (archived analysis)
#     analysis/         Cross-scenario and cross-sample analyses feeding the
#                       paper sections; each folder is named for what it shows.
#     extractive/       Resource sub-pipeline outputs.
#     checks/           QA and diagnostics (bootstrap, coverage, outliers).
#     other_projects/   Material NOT part of the unitary-taxation paper.
#     archive/          Superseded runs and retired specifications.
#
# `output_dirs()` below is the single chokepoint every script writes through;
# scripts keep their original topic strings and these two tables place the
# files. To relocate a folder, edit the mapping here, not the scripts.

_TOPIC_REMAP_EXACT = {
    # Estimation runs — sample with imputed rows (gravity disaggregation).
    "unitary_taxation_disaggregated": "estimates/with_imputed_rows/1_resources_ignored",
    "unitary_taxation_excl_resource": "estimates/with_imputed_rows/2_resources_excluded",
    "unitary_taxation_excl_resource_floored": "estimates/with_imputed_rows/3_minimum_royalty_added",
    "unitary_taxation_excl_resource_floored_allrowsalloc": "estimates/with_imputed_rows/3_minimum_royalty_added_allrows_alloc",
    "unitary_taxation_incl_resource": "estimates/with_imputed_rows/resources_included_reference",
    "unitary_taxation_positive_panel": "estimates/with_imputed_rows/positive_profits_only",
    # Estimation runs — reported-only sample (main sample of the paper).
    "unitary_taxation_disaggregated_reported": "estimates/reported_only/1_resources_ignored",
    "unitary_taxation_excl_resource_reported": "estimates/reported_only/2_resources_excluded",
    "unitary_taxation_excl_resource_floored_reported": "estimates/reported_only/3_minimum_royalty_added",
    "unitary_taxation_excl_resource_floored_allrowsalloc_reported": "estimates/reported_only/3_minimum_royalty_added_allrows_alloc",
    "unitary_taxation_incl_resource_reported": "estimates/reported_only/resources_included_reference",
    "unitary_taxation_positive_panel_reported": "estimates/reported_only/positive_profits_only",
    # Classic single-spec State of Tax Justice reference run.
    "unitary_taxation_sotj_15_avg": "analysis/classic_sotj_specification",
    # Bootstrap standard errors.
    "unitary_taxation_gravity_boot": "checks/bootstrap_with_imputed_rows",
    "unitary_taxation_gravity_boot_reported": "checks/bootstrap_reported_only",
    # Scenario-comparison figures on the imputed sample (7j).
    "three_scenarios/gravity": "analysis/scenario_comparison/with_imputed_rows",
    "three_scenarios/comparison": "analysis/origin_vs_destination/with_imputed_rows",
    # Country overview spreadsheets (7n) + cross-sample long table / 7o notes.
    "country_overview_reported": "analysis/country_overview/reported_only",
    "country_overview_gravity": "analysis/country_overview/with_imputed_rows",
    "deliverables/country_sheet": "analysis/country_overview/cross_sample",
    # Context comparisons: UT gains vs IMF credit / Marshall Plan.
    "context_comparisons": "analysis/context_comparisons",
    # Resource-correction summary table (7i).
    "deliverables/resource_correction": "analysis/resource_correction",
    # Loss-consolidation sensitivity (7e) — feeds Figure 10 / the tables doc.
    "deliverables/loss_consolidation_sensitivity": "analysis/loss_consolidation",
    # Paper tables (7f: reported sample = main text; 7p: sources table).
    "deliverables/paper_tables": "paper/main_text",
    # Haven leakage ratio (7g) — world loss per $1 a haven collects.
    "deliverables/haven_leakage": "analysis/haven_leakage",
    # Factor incidence (7d) — Figure 8 inputs.
    "deliverables/factor_incidence": "analysis/factor_incidence",
    # Direct paper topics: scripts producing numbered exhibits write here.
    "paper/main_text": "paper/main_text",
    "paper/appendix": "paper/appendix",
}

# First-path-segment remap for topics that may carry a nested sub-topic
# (e.g. "three_scenarios/gravity"; exact matches above win first).
_TOPIC_REMAP_PREFIX = {
    # Scenario-comparison figures/tables, reported-only sample (7a Part A);
    # "detail" holds 7a Part B's fuller multi-window summaries.
    "three_scenarios": "analysis/scenario_comparison/reported_only",
    "scenario_detail": "analysis/scenario_comparison/detail",
    "five_scenarios": "analysis/scenario_comparison/detail",   # legacy alias
    "comparison": "analysis/scenario_comparison/tax_base",
    # Origin- vs destination-based sales comparisons, reported-only sample.
    "destination_vs_origin": "analysis/origin_vs_destination/reported_only",
    # QA / diagnostics.
    "destination_sales": "checks/destination_sales",
    "etr_ut_income_groups": "checks/etr_by_income_group",
    "disaggregation": "checks/disaggregation",
    "country_profiles": "checks/country_profiles",
}


def _remap_topic(topic: str) -> str:
    """Translate a flat topic name into its nested output location."""
    if topic in _TOPIC_REMAP_EXACT:
        return _TOPIC_REMAP_EXACT[topic]
    head, sep, tail = topic.partition("/")
    if head in _TOPIC_REMAP_PREFIX:
        return _TOPIC_REMAP_PREFIX[head] + (("/" + tail) if tail else "")
    return topic


def output_dirs(topic: str):
    """Return (tables_dir, figures_dir) Path objects for a topic.

    Both directories are created on first call. The topic is remapped into the
    nested output layout (see `_TOPIC_REMAP_*` above) so scripts can keep using
    their original flat topic strings. Usage:

        from config import output_dirs
        TABLES_DIR, FIGURES_DIR = output_dirs("extractive")
    """
    base = output_root / _remap_topic(topic)
    tables = base / "tables"
    figures = base / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    return tables, figures


# Path helper for scripts that READ another run's estimation outputs directly
# (writers go through output_dirs). Accepts the sample/scenario names used
# throughout the pipeline and returns the folder under output/estimates/.
ESTIMATES_SAMPLE_DIRS = {
    "reported_only": "reported_only",
    "gravity": "with_imputed_rows",
    "with_imputed_rows": "with_imputed_rows",
}
ESTIMATES_SCENARIO_DIRS = {
    "baseline": "1_resources_ignored",
    "disaggregated": "1_resources_ignored",
    "excl_resource": "2_resources_excluded",
    "excl_resource_floored": "3_minimum_royalty_added",
    "excl_resource_floored_allrowsalloc": "3_minimum_royalty_added_allrows_alloc",
    "incl_resource": "resources_included_reference",
    "positive_panel": "positive_profits_only",
}


def estimates_dir(sample: str, scenario: str) -> _Path:
    """output/estimates/<sample>/<scenario> as a Path.

    `sample` and `scenario` may be either the pipeline names ("gravity",
    "excl_resource", …) or the folder names themselves."""
    return (
        output_root / "estimates"
        / ESTIMATES_SAMPLE_DIRS.get(sample, sample)
        / ESTIMATES_SCENARIO_DIRS.get(scenario, scenario)
    )


# ── 4. Constant-dollar conversion ────────────────────────────────────────────

# US GDP deflator (BEA / FRED GDPDEF, annual average, index 2017 = 100). Used to
# express multi-year aggregates in constant BASE_YEAR US dollars:
#     value_in_base_usd = value_in_year_nominal × deflator_to_base()[year]
# The 2016–2022 entries are the original BEA vintage (kept unchanged so already
# published figures stay reproducible); 2023–2025 are appended annual averages
# computed from FRED GDPDEF quarterly data (all four quarters of 2025 observed).
US_GDP_DEFLATOR_2017100 = {
    2016: 98.13, 2017: 100.00, 2018: 102.29, 2019: 104.14,
    2020: 105.36, 2021: 110.22, 2022: 117.99,
    2023: 122.38, 2024: 125.42, 2025: 128.97,
}

# Base year for constant-dollar reporting. Every monetary aggregate in the
# deliverable figures/tables is expressed in constant BASE_YEAR US dollars.
# Change this single constant to rebase the whole study.
BASE_YEAR = 2025


def deflator_to_base(base_year=BASE_YEAR):
    """year → multiplicative factor converting that year's nominal USD to
    constant `base_year` USD (defaults to BASE_YEAR)."""
    d = US_GDP_DEFLATOR_2017100
    base = d[base_year]
    return {y: base / v for y, v in d.items()}


# ── 5. Raw data files ────────────────────────────────────────────────────────
# The most up-to-date file names of the raw inputs. All anchored to the
# project root via `data_raw`, so every script runs from any directory.

# CbCR file
## Please give the path to the most recent CbCR file here. This file can be downloaded here: https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI.
## The link still refers to the old data portal of the OECD. At a certain point in time, the data should be on the new data portal.
cbcr_data = data_raw + "cbcr/oecd_cbcr_tableI_2026-02.csv"

# CIT rates
## Please give the path to the most recent corporate income tax (CIT) rate data here. The data has downloaded from two differentthe OECD for many countries here ('Measure: Combined corporate income tax rate'): https://data-explorer.oecd.org/vis?lc=en&fs[0]=Topic%2C1%7CTaxation%23TAX%23%7CCorporate%20tax%23TAX_CPT%23&pg=0&fc=Topic&bp=true&snb=15&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_TAX_CIT%40DF_CIT&df[ag]=OECD.CTP.TPS&df[vs]=1.0&dq=AUS%2BAUT%2BBEL%2BCAN%2BCHL%2BCOL%2BCRI%2BCZE%2BDNK%2BEST%2BFIN%2BFRA%2BDEU%2BGRC%2BHUN%2BISL%2BIRL%2BISR%2BITA%2BJPN%2BKOR%2BLVA%2BLTU%2BLUX%2BMEX%2BNLD%2BNZL%2BNOR%2BPOL%2BPRT%2BSVK%2BSVN%2BESP%2BSWE%2BCHE%2BTUR%2BGBR%2BUSA%2BALB%2BAGO%2BAND%2BAIA%2BATG%2BARG%2BARM%2BABW%2BAZE%2BBHS%2BBHR%2BGGY%2BBRB%2BBLZ%2BBEN%2BBMU%2BBIH%2BBWA%2BBRA%2BVGB%2BBRN%2BBGR%2BBFA%2BCPV%2BCMR%2BCYM%2BCHN%2BCOG%2BCOK%2BCIV%2BHRV%2BCUW%2BCOD%2BDJI%2BDMA%2BDOM%2BEGY%2BSWZ%2BFRO%2BGAB%2BGEO%2BGIB%2BGRL%2BGRD%2BHTI%2BHND%2BHKG%2BIND%2BIDN%2BIMN%2BJAM%2BJEY%2BJOR%2BKAZ%2BKEN%2BKWT%2BLBR%2BLIE%2BMAC%2BMYS%2BMDV%2BMLT%2BMRT%2BMUS%2BMCO%2BMNG%2BMNE%2BMSR%2BMAR%2BNAM%2BNGA%2BMKD%2BOMN%2BPAK%2BPAN%2BPNG%2BPRY%2BPER%2BPHL%2BQAT%2BROU%2BKNA%2BLCA%2BVCT%2BWSM%2BSMR%2BSAU%2BSEN%2BSRB%2BSYC%2BSLE%2BSGP%2BZAF%2BLKA%2BTHA%2BTGO%2BTTO%2BTUN%2BTCA%2BUKR%2BARE%2BURY%2BUZB%2BVNM%2BZMB.A.CIT_C.ST..S13%2BS1311%2BS13M..&to[TIME_PERIOD]=false&pd=2016%2C2024
# and for all other ones here: https://taxfoundation.org/data/global-tax/?_sft_topics=corporate-tax-rates-around-the-world#results (see notebook "1_clean").
cit_data_oecd = data_raw + "tax_rates/oecd_cit_rates_2026-02.csv"
cit_data_taxfoundation = (
    data_raw + "tax_rates/taxfoundation_cit_rates_1980-2023.xlsx"
)

# Wage data
## Please give the path to the most recent ILO wage data "Wages and Working Time Statistics (COND)" here. The data be downloaded here: https://www.ilo.org/ilostat-files/WEB_bulk_download/indicator/EAR_4MTH_SEX_ECO_CUR_NB_A.csv.gz (see notebook "1_clean").
wage_data = data_raw + "macro_variables/ilo_wages_ear4mth_2025-08.csv"

# GDP and population data
## Please give the path to the most recent GDP and population data from the World Bank here. The data be downloaded here: https://databank.worldbank.org/source/world-development-indicators/preview/on, selecting the series "GDP (current US$)" and "Population, total" (see notebook "1_clean").
## NOTE: only POPULATION is taken from this file; GDP is overridden by the
## canonical WB snapshot below (this DataBank export is a stale vintage — it
## misses WB revisions such as Nigeria's +41% rebasing and Angola).
gdp_population_data = data_raw + "macro_variables/wb_gdp_population_2026-02.csv"

## Canonical GDP — the SINGLE GDP per (iso3, year) used across the repo
## (CbCR pipeline + extractive WB-GDP reference): WB WDI NY.GDP.MKTP.CD,
## current US$, dated snapshot. Refresh with src/_fetch_canonical_gdp.py.
canonical_gdp_data = data_raw + "macro_variables/wb_gdp_current_usd_2026-07.csv"

# Health expenditure data
## Please give the path to the most recent WHO health expenditure data here. The data be downloaded here: https://apps.who.int/nha/database/Select/Indicators/en selecting "Domestic General Government Health Expenditure" and "million current US$" as a unit (see notebook "1_clean").

# Tax revenue data
## Please give the path to the most recent tax revenue data here. The data be downloaded here: https://api.worldbank.org/v2/en/indicator/GC.TAX.TOTL.GD.ZS?downloadformat=csv

# Data on regions and membership in regional or international organizations
## Please copy the most recent version of TJN's unilateral cross data from the TJN sharepoint: "...\Tax Justice Network Ltd\TJN - Shared Documents\Research team\Data\Final data\{date}_unilateral_cross.csv"
## in the data/raw folder and give the path below.
unilateral_cross_data = data_raw + "country_info/tjn_portal_unilateral_cross_2024-06.csv"

# Exchange rates
exchange_rates_wb = data_raw + "macro_variables/wb_fx_official_rate_2026-02.csv"

# Consumer Price Index (national CPI, 2010=100). Used in 1_clean.py to
# extrapolate ILO survey wage observations across panel years for countries
# where ILO does not provide annual coverage. WB indicator FP.CPI.TOTL,
# downloaded from the WB Open Data API.
cpi_data = data_raw + "macro_variables/wb_cpi_2026-04.csv"

# Destination-based sales inputs (OECD 2020, "Tax Challenges Arising from
# Digitalisation - Economic Impact Assessment", Chapter 2, p.40ff). Used by
# 1a_destination_based_sales.py to build the destination-based-sales
# allocation keys, merged into the disaggregated CbCR dataset in script 2.
## OECD Analytical AMNE database, "AAMNE_XVEM": output, value added, exports
## and imports of domestic- (D) and foreign-owned (F) firms by host country,
## industry and ownership. Million USD, 2000-2020. http://oe.cd/gvc-mne
aamne_data = data_raw + "destination_based_sales/oecd_aamne_xvem_2026-06.csv"
## OECD Analytical AMNE "MNE" file: output, value added and trade split by
## ownership into foreign-owned (F), domestic-owned MNEs (D_MNE) and other
## domestic-owned non-MNE firms (D_OTH). Exports column is EXGR. Used as the
## exact source for MNE CFB sales (F + D_MNE); the XVEM file + flat 14% is the
## fallback if this is absent. Same http://oe.cd/gvc-mne download.
## 2026 edition (downloaded 2026-07-23): 2008-2023, 81 countries (adds AGO,
## ARE, COD, STP) — real data for 2021/2022, no roll-forward needed there.
aamne_dmne_data = data_raw + "destination_based_sales/oecd_aamne_mne_xvem_2026-07.csv"
## ITU "Individuals using the Internet" (% of population), long format
## (entityIso, dataYear, dataValue). Used for the ADS proxy.
itu_internet_data = data_raw + "destination_based_sales/itu_internet_users_2026-06.csv"
## UN National Accounts: individual consumption expenditure by COICOP item and
## institutional sector (national currency). The "Equals: Household final
## consumption expenditure" line for households is the ADS consumption input.
un_consumption_data = data_raw + "destination_based_sales/un_household_consumption_2026-06.csv"
## WTO Digitally Delivered Services bulk download: cross-border (Mode 1) trade
## in digitally delivered services by reporter (ISO2), year, flow (M/X),
## million US$. IMPORTS of the total (INDICATOR "DDS") proxy "remote" digital
## value consumed in a market but not booked as local turnover - i.e. the
## "ADS not in CFB" increment, added to CFB to form the combined sales key.
ddt_data = data_raw + "destination_based_sales/wto_dds_imports_2026-06.csv"
## OECD-WTO BaTIS (Balanced Trade in Services), bilateral EBOPS-2010 categories.
## Source of the "digitally DELIVERABLE services" imports aggregate (IMF-OECD-
## UNCTAD-WTO Handbook definition: SF, SG, SH, SI, SJ, SK1/SK) used by the
## broadened destination-sales measure — preferred over the WTO "digitally
## delivered" series, whose definition is unclear and narrower (see the G24
## paper, g24.org "Options for a Protocol on Services under the UNFCITC").
## Downloaded 2026-07-12: BPM6 December-2025 edition bulk CSV (2.8 GB;
## Reporter/Partner ISO2 + type flags, Flow M/X, Item_code EBOPS, Year,
## Reported/Final/Balanced value in million USD). The BALANCED value is the
## reconciled series (notes sheet) — used with Final_value as row fallback.
batis_data = (data_raw + "destination_based_sales/oecd_wto_batis_data_bpm6/"
              "OECD-WTO_BATIS_BPM6_December2025_bulk.csv")
## WB Trade (% of GDP), indicator NE.TRD.GNFS.ZS (API download CSV).
trade_openness_data = data_raw + "macro_variables/wb_trade_pct_gdp_2026-06.csv"
## WB Personal remittances, received (current US$), BX.TRF.PWKR.CD.DT (API CSV).
remittances_data = data_raw + "macro_variables/wb_remittances_received_2026-06.csv"
## WB Net official development assistance received (current US$),
## DT.ODA.ODAT.CD (Databank export, same wide format as the GDP/population file).
oda_data = data_raw + "context/wb_oda_received_2026-06.csv"


# ── 6. Extractive-pipeline intermediates ─────────────────────────────────────
# Built by the extractive sub-pipeline (src/3_extractive_prep/), so they live
# in data/intermediate/extractive/.

## Per-country-year panel combining WB resource rents, GRD captured revenue,
## EITI breakdown, and manual fills. Built by 3_25_build_consolidated_yearly.py
## (after 2_5 applies carry-classification fixes).
extractive_royalty_yearly_data = (
    data_intermediate_extractive + "extractive_royalty_dataset_yearly.csv"
)

## HQ shares by commodity per parent country and year, from the Orbis-based
## extractive companies pipeline (3_1 process_orbis_broad → 3_2
## compute_hq_shares_yearly). Long format: year, hq_iso3, commodity
## (oil_gas|coal|minerals), revenue_usd, share.
hq_shares_yearly_data = (
    data_intermediate_extractive + "hq_shares_by_commodity_yearly.csv"
)


# ── 7. Tax-haven lists ───────────────────────────────────────────────────────
# THREE lists, three distinct purposes. The representation and functional
# lists are both strict SUPERSETS of the cleaning list, so the lists never
# disagree on a jurisdiction they share:
#
#   7a. TAX_HAVENS_CLEANING       — drives the dividend correction (CHANGES NUMBERS)
#   7b. TAX_HAVENS_REPRESENTATION — the "tax_haven" display group (presentation only)
#   7c. TAX_HAVENS_FUNCTIONAL     — frozen set for two pipeline steps (CHANGES NUMBERS)
#
# The misalignment haven identification in script 5 is none of these — it is a
# separate ETR-threshold rule (<15% on the resource-corrected ETR), not list-based.

# ── 7a. Cleaning list ──
# The EXACT tax-haven list of García-Bernardo, Janský & Zucman (2026, "Did the
# Tax Cuts and Jobs Act Reduce Profit Shifting by US Multinational Companies?",
# IMF Economic Review, §4), which groups havens — following Reurink &
# García-Bernardo (2020) — into "profit centres" (used mainly for booking
# profit, little production) and "coordination centres" (booking plus
# management/coordination). It drives the García-Bernardo & Janský (2024)
# dividend double-counting correction in 1_clean.py (10% of haven profits,
# non-US MNCs, 2016-2019). Changing it changes the cleaned profit figures, so
# edit it only to track the GB methodology.
_GB_PROFIT_CENTRES = {
    "BMU",  # Bermuda
    "CYM",  # Cayman Islands
    "PRI",  # Puerto Rico
    "JEY",  # Jersey
    "IMN",  # Isle of Man
    "GIB",  # Gibraltar
    "BRB",  # Barbados
    "MUS",  # Mauritius
    "VGB",  # British Virgin Islands
    "BHS",  # Bahamas
    "MLT",  # Malta
}
_GB_COORDINATION_CENTRES = {
    "SGP",  # Singapore
    "NLD",  # Netherlands
    "CHE",  # Switzerland
    "IRL",  # Ireland
    "LUX",  # Luxembourg
    "HKG",  # Hong Kong
}
TAX_HAVENS_CLEANING = _GB_PROFIT_CENTRES | _GB_COORDINATION_CENTRES  # 17 jurisdictions

# Alias: code that references `tax_havens` (e.g. the GB dividend correction)
# gets the CLEANING list.
tax_havens = TAX_HAVENS_CLEANING

# ── 7b. Representation list (29) ──
# Which jurisdictions are SHOWN as the "tax_haven" group in figures and
# tables. Feeds NO correction — purely presentational (no effect on estimates).
# RULE: the GB cleaning list, UNIONed with every
# jurisdiction that
#   (a) has a CTHI-2025 Haven Score >= 65
#       (data/raw/country_info/tjn_cthi_2025_scores.csv, cthi_2025_score), AND
#   (b) booked INWARD-shifted profit (reported_profit − theoretical_profit > 0)
#       in AT LEAST TWO years, 2016–2022 excl 2020, on the current headline
#       spec (reported-only / excl_resource / sales_employees_destmnedds /
#       etrdef_domfor / etrmax_inf),
# plus the MANUAL substance keep — the British Indian Ocean Territory
# (ISO IOT, "BIOT"; no CTHI score).
#
# The GB leg is effectively NON-BINDING: 15 of the 17 GB
# members pass the outcome test on their own (CTHI >= 65 and 4–6 inward-shift
# years each); only Puerto Rico and Barbados need it — both with the maximum
# 6/6 shift years but no CTHI score to compare against 65.
#
# Note: a simpler-looking rule — "unscored by CTHI + >=2 inward-shift years" —
# was checked and REJECTED: it would admit 44 jurisdictions incl. Canada,
# Japan, Saudi Arabia, Norway, Chile and Israel, because inward-shifted profit
# alone mostly flags HEADQUARTER-BIAS countries (domestic over-booking by their own
# MNEs). The CTHI >= 65 gate is what makes the shift test meaningful; for the
# two unscored members (PRI, BRB) the GB profit-centre classification stands
# in for the missing score.
#
# Membership judgement calls (see docs/tax_haven_lists.md for the full record):
# Hungary EXCLUDED (CTHI 69 but only a single inward-shift year, below the
# >=2-year gate that rejects single-year outliers; Anguilla is the thinnest keeper at exactly 2 years). Cook Islands
# dropped (no CTHI score, no inward-shift year). Guernsey qualifies on outcome.
# Saudi Arabia deliberately NOT added (no CTHI; its excess profit is ~98%
# home-booked — a HEADQUARTER-BIAS country, not a haven). The membership was evaluated
# once on the current headline run and FROZEN here — safe because the list
# feeds no estimate, only the display group.
_EXTRA_CTHI_GE65_2YR_SHIFT = {
    # ISO: CTHI-2025 Haven Score, #inward-shift years (of 6), max single-year
    # shift (m USD, headline destmnedds). Non-GB only (GB members that also pass
    # arrive via TAX_HAVENS_CLEANING).
    "MCO",  # Monaco 66, 6 yrs, +446
    "PAN",  # Panama 72, 5 yrs, +33,394
    "CUW",  # Curaçao 72, 5 yrs, +1,762
    "SYC",  # Seychelles 70, 5 yrs, +75
    "CYP",  # Cyprus 79, 4 yrs, +12,656
    "ABW",  # Aruba 71, 4 yrs, +144
    "ARE",  # United Arab Emirates 84, 3 yrs, +13,437
    "LBR",  # Liberia 67, 3 yrs, +526
    "GGY",  # Guernsey 100, 3 yrs, +311
    "LIE",  # Liechtenstein 67, 3 yrs, +253
    "AIA",  # Anguilla 100, 2 yrs, +35  (at the >=2 threshold)
}
_EXTRA_MANUAL = {
    "IOT",  # British Indian Ocean Territory — no CTHI / no FSI, kept on substance
}
TAX_HAVENS_REPRESENTATION = (
    TAX_HAVENS_CLEANING | _EXTRA_CTHI_GE65_2YR_SHIFT | _EXTRA_MANUAL
)

# ── 7c. Functional list (frozen) ──
# Two pipeline steps use a haven set FUNCTIONALLY — they change NUMBERS, not
# display:
#   * 2_disaggregate: recognised havens are exempt from the per-country
#     imputed-activity caps (2×GDP / 0.5×pop) — micro-state havens like
#     Guernsey and the Cook Islands legitimately host activity above GDP;
#   * 4_correcting (resource-dominated ETR floor): havens are excluded from
#     the floor gate. Resource-dominated economies (e.g. Saudi Arabia) must
#     stay OUT of this set — haven status here would silently exempt them
#     from the residual-ETR floor that strips their unremoved resource tax.
# Membership is GB ∪ CTHI >= 67 ∪ Cook Is / BIOT substance adds, held fixed
# so that re-definitions of the representation list stay purely presentational
# (identical estimates).
TAX_HAVENS_FUNCTIONAL = TAX_HAVENS_CLEANING | {
    "GGY", "AIA", "ARE", "CYP", "PAN", "CUW", "LBN", "CRI", "LVA", "ABW",
    "EST", "SYC", "HUN", "LIE", "LBR",   # CTHI >= 67
    "COK", "IOT",                        # substance adds (not scored by CTHI)
}

# NB: an OUTCOME-based alternative (a jurisdiction is a haven if its pooled
# period-average ETR is below a threshold) was explored but NOT adopted — it both
# drops marquee havens (IRL/LUX/MLT/CHE/HKG/NLD/MUS/GGY/COK) and pulls in
# loss-year / tiny-profit non-havens. The candidate jurisdictions are documented
# in docs/tax_haven_lists.md ("Explored but not adopted"); regenerate them with
# src/archive/_build_etr_haven_list.py. There is intentionally no such list here.


# ── 8. Data-quality exclusions (presentation only) ───────────────────────────
# Jurisdictions whose CbCR-reported profits are orders of magnitude larger than
# their real economies — reporting anomalies, not economics. They are excluded
# from AGGREGATE/RANKING presentation outputs (winner/loser tables, income-group
# bars in scripts 6/7a) but NEVER removed from the data files or estimates:
#   LSO  Lesotho        — ~$38B/yr reported vs ~$2B GDP and ~$35M mining take.
#   FSM  Micronesia     — ~$19B/yr reported with 22k employee-years; likely a
#                         flag-of-convenience / shipping-registry artifact.
#   GUF  French Guiana  — ~$16B/yr with $0 resource activity; likely a French
#                         overseas-territory CbCR reporting artifact.
#   BTN  Bhutan         — small economy with disproportionate reported profit.
# Single source of truth; scripts import THIS set.
DATA_QUALITY_EXCLUSIONS = {"LSO", "FSM", "GUF", "BTN"}


# ── 9. Country groups and display names ──────────────────────────────────────

# CbCR aggregate partner codes (continents / world), and their "other" residual
# counterparts. `non_countries` marks every row that is not a real jurisdiction.
aggregated_country_groups = {"W", "A", "E", "F", "S"}
other_country_groups = {"WXD", "A_O", "E_O", "F_O", "S_O", "W_O"}
non_countries = aggregated_country_groups | other_country_groups

# Short / common country names for deliverable tables, overriding pycountry's
# official long names. Politically-sensitive labels confirmed with the author.
# Hong Kong / Macao are kept standalone (no "China" qualifier), like Taiwan.
COUNTRY_NAME_OVERRIDES = {
    "TWN": "Taiwan", "KOR": "South Korea", "PRK": "North Korea",
    "PSE": "Palestine", "XKV": "Kosovo", "XKX": "Kosovo",
    "COD": "DR Congo", "COG": "Congo (Rep.)",
    "BOL": "Bolivia", "BRN": "Brunei", "IRN": "Iran", "LAO": "Laos",
    "MDA": "Moldova", "RUS": "Russia", "SYR": "Syria", "TZA": "Tanzania",
    "VEN": "Venezuela", "VNM": "Vietnam", "FSM": "Micronesia",
    "VGB": "British Virgin Islands", "VIR": "U.S. Virgin Islands",
}
