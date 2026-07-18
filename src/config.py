# Update this config file before running the analysis for another year and after having stored the most up-to date raw data

# Insert first year of analysis
first_year = 2016

# Insert number of years you like to analyze
n_years = 7

# Specify paths (flat structure - old years archived in data/archive and output/archive)
# Anchored to the project directory (resolved from this file's location) so
# callers can run from any CWD — play button, terminal, Interactive window.
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

# Output is organized as output/<topic>/{tables,figures}/. Use the
# `output_dirs(topic)` helper below from any analysis script so the layout
# stays consistent. `output_root` is anchored to the project directory
# (resolved from this file's location) so callers can run from any CWD.
import sys as _sys

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


# ── Output-folder organisation (2026-06-16) ──────────────────────────────────
# The pipeline is organised under output/ by SAMPLE and ROLE, so the many flat
# `unitary_taxation_*` topics map into a tidy nested tree. `output_dirs()` is
# the single chokepoint every script uses, so the mapping lives here — scripts
# keep their original topic strings and the files land in the nested location.
#
#   output/
#     unitary_taxation/
#       gravity/{baseline,excl_resource,excl_resource_floored}/   MAIN (gravity-imputed full)
#       reported_only/{baseline,excl_resource,excl_resource_floored,incl_resource}/  recorded profits, no imputed rows
#     deliverables/{three_scenarios,destination_vs_origin,five_scenarios,comparison}/
#     diagnostics/{destination_sales,etr_ut_income_groups,disaggregation,country_profiles,gravity_boot}/
#     extractive/
#     archive/{...}                                                    legacy single-topic UT output
#
# There is one disaggregation method (gravity activity + profitability profit), so
# the full-mode topics map straight to unitary_taxation/gravity/. Reported-only is
# one sample regardless of imputation (imputed rows are dropped), so it has a
# single home.
_TOPIC_REMAP_EXACT = {
    # Gravity-imputed FULL sample — the single disaggregation method. The plain
    # full-mode topics now carry it (there is no longer a separate trimmed-mean
    # full sample, so no `_gravity` suffix and no archive/trimmed_full split).
    # Folders are named for the scenario.
    "unitary_taxation_disaggregated": "unitary_taxation/gravity/baseline",
    "unitary_taxation_excl_resource": "unitary_taxation/gravity/excl_resource",
    "unitary_taxation_excl_resource_floored": "unitary_taxation/gravity/excl_resource_floored",
    "unitary_taxation_incl_resource": "unitary_taxation/gravity/incl_resource",
    # reported-only sample (recorded profits, no imputed rows)
    "unitary_taxation_disaggregated_reported": "unitary_taxation/reported_only/baseline",
    "unitary_taxation_excl_resource_reported": "unitary_taxation/reported_only/excl_resource",
    "unitary_taxation_excl_resource_floored_reported": "unitary_taxation/reported_only/excl_resource_floored",
    "unitary_taxation_incl_resource_reported": "unitary_taxation/reported_only/incl_resource",
    # legacy pre-dataset-split single-topic UT output (read by 8_figures_taxrates.py)
    "unitary_taxation": "archive/unitary_taxation_legacy",
    # bootstrap SE diagnostics
    "unitary_taxation_gravity_boot": "unitary_taxation/diagnostics/gravity_boot",
    "unitary_taxation_gravity_boot_reported": "unitary_taxation/diagnostics/gravity_boot_reported",
    # --- Deliverable FIGURES embedded under each sample (easy-to-read folders) ---
    # Gravity-sample figure deliverables (sub-topics of "three_scenarios" used by
    # 9c_gravity_destination_comparison.py).
    "three_scenarios/gravity": "unitary_taxation/gravity/three_scenario_figures",
    "three_scenarios/comparison": "unitary_taxation/gravity/imputation_comparison",
    # Per-sample country overview spreadsheets (9g writes one Excel per sample,
    # embedded in that sample's folder).
    "country_overview_reported": "unitary_taxation/reported_only/country_overview",
    "country_overview_gravity": "unitary_taxation/gravity/country_overview",
    # Context comparisons (9t): headline UT gains vs outstanding IMF credit and
    # vs the Marshall Plan — reported-only sample deliverable.
    "context_comparisons": "unitary_taxation/reported_only/context_comparisons",
    # Cross-sample tidy long table + negative-estimate explanations (9g long CSV +
    # 9h) — these explicitly compare the two samples, so they stay cross-sample.
    "deliverables/country_sheet": "unitary_taxation/across_samples/country_overview",
    # Resource-correction table (9f) — a cross-sample, data-level result.
    "deliverables/resource_correction": "unitary_taxation/across_samples/resource_correction",
    # Loss-consolidation sensitivity (9i) — ex-post zero-tax-on-reported-losses
    # correction, a cross-sample additional estimate (not the main spec).
    "deliverables/loss_consolidation_sensitivity": "unitary_taxation/across_samples/loss_consolidation_sensitivity",
    # Paper deliverable tables (9j) — country-level scenario/formula result tables
    # for both samples, plus the hand-collected data-sources table (9k).
    "deliverables/paper_tables": "unitary_taxation/across_samples/paper_tables",
    # Haven leakage ratio (9p) — world revenue loss havens CAUSE per $1 they COLLECT.
    "deliverables/haven_leakage": "unitary_taxation/across_samples/haven_leakage",
    # Factor incidence (9q) — pure single-factor revenue effects by income group.
    "deliverables/factor_incidence": "unitary_taxation/across_samples/factor_incidence",
}

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


def deflator_to_2022():
    """Deprecated backward-compatible alias — deflate to constant 2022 USD.
    New code should call deflator_to_base() (BASE_YEAR)."""
    return deflator_to_base(2022)


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

# First-path-segment remap for deliverable / diagnostic topics (which may carry
# a nested sub-topic, e.g. "three_scenarios/gravity").
_TOPIC_REMAP_PREFIX = {
    # Reported-only figure deliverables embedded under that sample's folder.
    # (The gravity-sample variants are handled by the exact-match entries above.)
    "three_scenarios": "unitary_taxation/reported_only/three_scenario_figures",
    "five_scenarios": "unitary_taxation/reported_only/five_scenario_figures",
    "destination_vs_origin": "unitary_taxation/reported_only/origin_vs_destination",
    "comparison": "unitary_taxation/across_samples/comparison",
    # Diagnostics now live under the unitary_taxation/ tree.
    "destination_sales": "unitary_taxation/diagnostics/destination_sales",
    "etr_ut_income_groups": "unitary_taxation/diagnostics/etr_ut_income_groups",
    "disaggregation": "unitary_taxation/diagnostics/disaggregation",
    "country_profiles": "unitary_taxation/diagnostics/country_profiles",
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


# TJN shared folder for IFF portal data
tjn_shared_bilateral = r"C:\Users\aliso\Tax Justice Network Ltd\TJN - Shared Documents\Research team\Projects long-term\SOTJ\Tables\bilateral"

# Specify the most up-to-date file names for the raw files

# CbCR file
## Please give the path to the most recent CbCR file here. This file can be downloaded here: https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI.
## The link still refers to the old data portal of the OECD. At a certain point in time, the data should be on the new data portal.
cbcr_data = "../data/raw/OECD.CTP.TPS,DSD_CBCR@DF_CBCRI,1.1+all.csv"

# CIT rates
## Please give the path to the most recent corporate income tax (CIT) rate data here. The data has downloaded from two differentthe OECD for many countries here ('Measure: Combined corporate income tax rate'): https://data-explorer.oecd.org/vis?lc=en&fs[0]=Topic%2C1%7CTaxation%23TAX%23%7CCorporate%20tax%23TAX_CPT%23&pg=0&fc=Topic&bp=true&snb=15&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_TAX_CIT%40DF_CIT&df[ag]=OECD.CTP.TPS&df[vs]=1.0&dq=AUS%2BAUT%2BBEL%2BCAN%2BCHL%2BCOL%2BCRI%2BCZE%2BDNK%2BEST%2BFIN%2BFRA%2BDEU%2BGRC%2BHUN%2BISL%2BIRL%2BISR%2BITA%2BJPN%2BKOR%2BLVA%2BLTU%2BLUX%2BMEX%2BNLD%2BNZL%2BNOR%2BPOL%2BPRT%2BSVK%2BSVN%2BESP%2BSWE%2BCHE%2BTUR%2BGBR%2BUSA%2BALB%2BAGO%2BAND%2BAIA%2BATG%2BARG%2BARM%2BABW%2BAZE%2BBHS%2BBHR%2BGGY%2BBRB%2BBLZ%2BBEN%2BBMU%2BBIH%2BBWA%2BBRA%2BVGB%2BBRN%2BBGR%2BBFA%2BCPV%2BCMR%2BCYM%2BCHN%2BCOG%2BCOK%2BCIV%2BHRV%2BCUW%2BCOD%2BDJI%2BDMA%2BDOM%2BEGY%2BSWZ%2BFRO%2BGAB%2BGEO%2BGIB%2BGRL%2BGRD%2BHTI%2BHND%2BHKG%2BIND%2BIDN%2BIMN%2BJAM%2BJEY%2BJOR%2BKAZ%2BKEN%2BKWT%2BLBR%2BLIE%2BMAC%2BMYS%2BMDV%2BMLT%2BMRT%2BMUS%2BMCO%2BMNG%2BMNE%2BMSR%2BMAR%2BNAM%2BNGA%2BMKD%2BOMN%2BPAK%2BPAN%2BPNG%2BPRY%2BPER%2BPHL%2BQAT%2BROU%2BKNA%2BLCA%2BVCT%2BWSM%2BSMR%2BSAU%2BSEN%2BSRB%2BSYC%2BSLE%2BSGP%2BZAF%2BLKA%2BTHA%2BTGO%2BTTO%2BTUN%2BTCA%2BUKR%2BARE%2BURY%2BUZB%2BVNM%2BZMB.A.CIT_C.ST..S13%2BS1311%2BS13M..&to[TIME_PERIOD]=false&pd=2016%2C2024
# and for all other ones here: https://taxfoundation.org/data/global-tax/?_sft_topics=corporate-tax-rates-around-the-world#results (see notebook "1_clean").
cit_data_oecd = "../data/raw/OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,2.0+all.csv"
cit_data_taxfoundation = (
    "../data/raw/1980_2023_Corporate_Tax_Rates_Around_the_World_Tax_Foundation.xlsx"
)

# Wage data
## Please give the path to the most recent ILO wage data "Wages and Working Time Statistics (COND)" here. The data be downloaded here: https://www.ilo.org/ilostat-files/WEB_bulk_download/indicator/EAR_4MTH_SEX_ECO_CUR_NB_A.csv.gz (see notebook "1_clean").
wage_data = "../data/raw/EAR_4MTH_SEX_CUR_NB_A-full-2025-08-25.csv"

# GDP and population data
## Please give the path to the most recent GDP and population data from the World Bank here. The data be downloaded here: https://databank.worldbank.org/source/world-development-indicators/preview/on, selecting the series "GDP (current US$)" and "Population, total" (see notebook "1_clean").
gdp_population_data = "../data/raw/55f1d958-0a59-4690-ab16-59602d3dab91_Data.csv"

# Health expenditure data
## Please give the path to the most recent WHO health expenditure data here. The data be downloaded here: https://apps.who.int/nha/database/Select/Indicators/en selecting "Domestic General Government Health Expenditure" and "million current US$" as a unit (see notebook "1_clean").
health_expenditure_data = "../data/raw/WHO health expenditure.xlsx"

# Tax revenue data
## Please give the path to the most recent tax revenue data here. The data be downloaded here: https://api.worldbank.org/v2/en/indicator/GC.TAX.TOTL.GD.ZS?downloadformat=csv
tax_revenue_data = "../data/raw/API_GC.TAX.TOTL.GD.ZS_DS2_en_csv_v2_1167.csv"

# Data on regions and membership in regional or international organizations
## Please copy the most recent version of TJN's unilateral cross data from the TJN sharepoint: "...\Tax Justice Network Ltd\TJN - Shared Documents\Research team\Data\Final data\{date}_unilateral_cross.csv"
## in the data/raw/{sotj_year} folder and give the path below.
unilateral_cross_data = "../data/raw/20240626_unilateral_cross.csv"

# Number of firms
## Orbis data on number of firms above USD 750mn revenue headquartered in a country, from Orbis flatfiles (to be obtained externally).
## Please store the data in the folder data/raw/{sotj_year} and adjust the path below accordingly.
orbis_data = "../data/raw/orbis.xlsx"

# Exchange rates
exchange_rates_wb = "../data/raw/API_PA.NUS.FCRF_DS2_en_csv_v2_114.csv"

# Consumer Price Index (national CPI, 2010=100). Used in 1_clean.py to
# extrapolate ILO survey wage observations across panel years for countries
# where ILO does not provide annual coverage. WB indicator FP.CPI.TOTL,
# downloaded from the WB Open Data API.
cpi_data = "../data/raw/API_FP.CPI.TOTL_DS2_en_csv_v2_115366.csv"

# Destination-based sales inputs (OECD 2020, "Tax Challenges Arising from
# Digitalisation - Economic Impact Assessment", Chapter 2, p.40ff). Used by
# src/0_destination_based_sales.py to build the CFB (and later ADS)
# destination-based-sales allocation key, merged into the disaggregated CbCR
# dataset in script 2.
## OECD Analytical AMNE database, "AAMNE_XVEM": output, value added, exports
## and imports of domestic- (D) and foreign-owned (F) firms by host country,
## industry and ownership. Million USD, 2000-2020. http://oe.cd/gvc-mne
aamne_data = "../data/raw/AAMNE_XVEM(2).csv"
## OECD Analytical AMNE "MNE" file: output, value added and trade split by
## ownership into foreign-owned (F), domestic-owned MNEs (D_MNE) and other
## domestic-owned non-MNE firms (D_OTH). Exports column is EXGR. Used as the
## exact source for MNE CFB sales (F + D_MNE); the XVEM file + flat 14% is the
## fallback if this is absent. Same http://oe.cd/gvc-mne download.
aamne_dmne_data = "../data/raw/AAMNE_MNE_XVEM.csv"
## OECD Analytical AMNE BILATERAL output (downloaded 2026-07-12): WIDE format —
## year, cou (HOST), isic (sector), then one column per OWNER country (incl.
## ROW; the host's own column = domestic-owned output). Million USD, 2000-2020.
## Drives the bilateral (parent-specific) destination-sales variant in 1b
## (Part D). Same http://oe.cd/gvc-mne family.
aamne_bilateral_data = "../data/raw/aamne-bilateral-output.csv"
## ITU "Individuals using the Internet" (% of population), long format
## (entityIso, dataYear, dataValue). Used for the ADS proxy.
itu_internet_data = "../data/raw/itu_individualsusinginternet.csv"
## UN National Accounts: individual consumption expenditure by COICOP item and
## institutional sector (national currency). The "Equals: Household final
## consumption expenditure" line for households is the ADS consumption input.
un_consumption_data = "../data/raw/UN_consumption.csv"
## WTO Digitally Delivered Services bulk download: cross-border (Mode 1) trade
## in digitally delivered services by reporter (ISO2), year, flow (M/X),
## million US$. IMPORTS of the total (INDICATOR "DDS") proxy "remote" digital
## value consumed in a market but not booked as local turnover - i.e. the
## "ADS not in CFB" increment, added to CFB to form the combined sales key.
ddt_data = "../data/raw/DDS_bulk_download.csv"
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
batis_data = ("../data/raw/OECD-WTO_BATIS_data_BPM6-1/"
              "OECD-WTO_BATIS_BPM6_December2025_bulk.csv")
## WB Trade (% of GDP), indicator NE.TRD.GNFS.ZS (API download CSV).
trade_openness_data = "../data/raw/API_NE.TRD.GNFS.ZS_DS2_en_csv_v2_355938.csv"
## WB Personal remittances, received (current US$), BX.TRF.PWKR.CD.DT (API CSV).
remittances_data = "../data/raw/API_BX.TRF.PWKR.CD.DT_DS2_en_csv_v2_355149.csv"
## WB Net official development assistance received (current US$),
## DT.ODA.ODAT.CD (Databank export, same wide format as the GDP/population file).
oda_data = "../data/raw/f6cb9ec3-b98a-448f-9f40-6e850bf1cc88_Data.csv"

# Resource carve-out inputs — built by the extractive sub-pipeline
# (src/3_extractive_prep/), so they live in data/intermediate/extractive/.
## Per-country-year panel combining WB resource rents, GRD captured revenue,
## EITI breakdown, and manual fills. Built by 2_4_build_consolidated_yearly.py
## (after 2_5 applies carry-classification fixes). Consumed by
## 3_resource_contribution.py.
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

## Country overrides for whether captured equity / SOE dividends should be
## added back to CbCR profit. Default TRUE for unlisted countries. FALSE for
## countries whose dominant SOE reports to CbCR (avoids double-counting).
equity_add_back_overrides_data = "../data/raw/equity_add_back_country_overrides.csv"


# ── Tax-haven lists ──────────────────────────────────────────────────────────
# We keep TWO lists for two distinct purposes, with the representation list a
# strict SUPERSET of the cleaning list (so there is one consistent core haven
# set throughout, and the lists never disagree on a jurisdiction they share).
#
# 1) TAX_HAVENS_CLEANING — used in DATA CLEANING (the analytical definition).
#    This is the EXACT tax-haven list of García-Bernardo, Janský & Zucman (2026,
#    "Did the Tax Cuts and Jobs Act Reduce Profit Shifting by US Multinational
#    Companies?", IMF Economic Review, §4), which groups havens — following
#    Reurink & García-Bernardo (2020) — into "profit centres" (used mainly for
#    booking profit, little production) and "coordination centres" (booking plus
#    management/coordination). It drives the García-Bernardo & Janský (2024)
#    dividend double-counting correction in 1_clean.py (10% of haven profits,
#    non-US MNCs, 2016-2019). Changing it changes the cleaned profit figures, so
#    edit it only to track the GB methodology.
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

# ─────────────────────────────────────────────────────────────────────────────
# TWO DISTINCT HAVEN CONCEPTS — do not conflate them:
#
#   (a) CORRECTION havens  — TAX_HAVENS_CLEANING (above). A fixed, list-based set
#       that DRIVES A DATA CORRECTION (the García-Bernardo dividend double-count
#       removal in 1_clean.py). Changing it CHANGES THE ESTIMATES. It is an input,
#       so it must be known before the pipeline runs → it lives here in config.
#       (The misalignment haven identification in script 5 is a separate, ETR-
#       threshold rule (<15% on the resource-corrected ETR), also not list-based.)
#
#   (b) REPRESENTATION havens — which jurisdictions are SHOWN as the haven country
#       group in the figures. This is purely presentational (no effect on any
#       estimate). The definition is OUTCOME-based — a jurisdiction is presented
#       as a haven iff the GB cleaning list contains it, OR it has a CTHI-2025
#       Haven Score >= 65 AND booked inward-shifted profit in at least two years —
#       and is FROZEN below as TAX_HAVENS_REPRESENTATION (the outcome was
#       evaluated once on the current headline run; freezing is safe because
#       the list feeds no estimate, only the `investment_hub` display group).
# ─────────────────────────────────────────────────────────────────────────────

# 2) TAX_HAVENS_REPRESENTATION (29) — used for REPRESENTATION / reporting
#    (income-group classification: these jurisdictions are shown as the
#    "investment_hub" group in figures and tables). It feeds NO cleaning
#    correction, so it is purely presentational (no effect on estimates).
#    RULE (adopted 2026-07-18, replacing the 2026-07-11 "CTHI-2024>65 & pooled
#    net-recipient" rule): the GB cleaning list, UNIONed with every jurisdiction
#    that
#      (a) has a CTHI-2025 Haven Score >= 65
#          (data/raw/cthi_2025_scores.csv, cthi_2025_score), AND
#      (b) booked INWARD-shifted profit (reported_profit − theoretical_profit
#          > 0) in AT LEAST TWO years, 2016–2022 excl 2020, on the current
#          headline spec (reported-only / excl_resource /
#          sales_employees_destmnedds / etrdef_domfor / etrmax_inf),
#    plus the MANUAL substance keep BIOT (no CTHI score). Puerto Rico and
#    Barbados are GB profit centres, so the GB leg keeps them despite having no
#    CTHI score. Jurisdictions without a CTHI score are otherwise NOT eligible
#    (Saudi Arabia stays out — HOME-BIAS, ~98% home-booked, see note below).
#    Vs the 2026-07-11 list this ADDS Liberia (CTHI 67, 3 inward-shift years) and
#    DROPS Cook Islands (no CTHI score AND no inward-shift year). Guernsey now
#    qualifies on the outcome rule (CTHI 100, 3 years) so it is no longer a
#    manual add. HUNGARY was CONSIDERED but EXCLUDED: CTHI 69 with a single
#    inward-shift year (2016, +4.2bn) but a large net LOSER in all five other
#    window years (~−28bn pooled), so it fails the >=2-year gate — the gate is
#    set at 2 precisely to reject such single-year outliers. Anguilla is the
#    thinnest keeper (exactly 2 years). See docs/tax_haven_lists.md.
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
# Manual substance keep — no CTHI score, retained as a classic haven.
# Puerto Rico / Barbados need no entry here (GB profit centres). Cook Islands
# was dropped 2026-07-18 (no CTHI score and no inward-shift year).
# Saudi Arabia was CONSIDERED (no CTHI; FSI 69; net recipient) but deliberately
# NOT added: its excess profit is ~98% home-booked — own-MNE domestic
# over-booking, i.e. a HOME-BIAS country, not a haven.
_EXTRA_MANUAL = {
    "IOT",  # British Indian Ocean Territory — no CTHI / no FSI, kept on substance
}
TAX_HAVENS_REPRESENTATION = (
    TAX_HAVENS_CLEANING | _EXTRA_CTHI_GE65_2YR_SHIFT | _EXTRA_MANUAL
)

# DEPRECATED alias: the narrow variant is retired — its purpose (dropping the
# debatable Costa Rica / Latvia / Lebanon) is subsumed by the net-recipient
# condition, which excludes all three. Kept so stale imports fail loudly enough
# in review rather than silently diverging.
TAX_HAVENS_REPRESENTATION_NARROW = TAX_HAVENS_REPRESENTATION

# 3) TAX_HAVENS_FUNCTIONAL — FROZEN at the pre-2026-07-11 representation
#    membership (GB ∪ CTHI ≥ 67 ∪ Cook Is / BIOT substance adds). Two pipeline
#    steps use a haven set FUNCTIONALLY — they change NUMBERS, not display:
#      * 2_disaggregate: recognised havens are exempt from the per-country
#        imputed-activity caps (2×GDP / 0.5×pop) — micro-state havens like
#        Guernsey and the Cook Islands legitimately host activity above GDP;
#      * 4_correcting (resource-dominated ETR floor): havens are excluded from
#        the floor gate. Saudi Arabia must NEVER be added to this set — it must
#        keep the script-4 "Saudi fix" floor, which haven status here would
#        silently disable.
#    Keeping this set frozen makes the outcome-based re-definition of
#    TAX_HAVENS_REPRESENTATION purely presentational (identical estimates).
TAX_HAVENS_FUNCTIONAL = TAX_HAVENS_CLEANING | {
    "GGY", "AIA", "ARE", "CYP", "PAN", "CUW", "LBN", "CRI", "LVA", "ABW",
    "EST", "SYC", "HUN", "LIE", "LBR",   # CTHI ≥ 67 under the old rule
    "COK", "IOT",                        # old substance adds (not scored by CTHI)
}

# NB: an OUTCOME-based alternative (a jurisdiction is a haven if its pooled
# period-average ETR is below a threshold) was explored but NOT adopted — it both
# drops marquee havens (IRL/LUX/MLT/CHE/HKG/NLD/MUS/GGY/COK) and pulls in
# loss-year / tiny-profit non-havens. The candidate jurisdictions are documented
# in docs/tax_haven_lists.md ("Explored but not adopted"); regenerate them with
# src/_build_etr_haven_list.py. There is intentionally no such list constant here.

# Backward-compatible alias: existing code that references `tax_havens` (e.g. the
# GB dividend correction) gets the CLEANING list, which is its original meaning.
tax_havens = TAX_HAVENS_CLEANING
## Country groups
aggregated_country_groups = {"W", "A", "E", "F", "S"}
## Country groups "other"
other_country_groups = {"WXD", "A_O", "E_O", "F_O", "S_O", "W_O"}
## Non-countries
non_countries = aggregated_country_groups | other_country_groups
