# Update this config file before running the analysis for another year and after having stored the most up-to date raw data

# Insert first year of analysis
first_year = 2016

# Insert number of years you like to analyze
n_years = 5

# Specify paths (no need to update anything here if you are working in the Github directory)
data_raw = "../data/raw/"
data_intermediate = "../data/intermediate/"
data_final = "../data/final/"
output_tables = "../output/tables/"
output_figures = "../output/figures/"

# Specify the most up-to-date file names for the raw files

# CbCR file
## Please give the path to the most recent CbCR file here. This file can be downloaded here: https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.

cbcr_data = "../data/raw/CBCR_TABLEI_05022024171639681.csv"
# cbcr_data = "../data/raw/CBCR_TABLEI_20062023110215400_corrIDN_allcolumns.csv"

# CIT rates
## Please give the path to the most recent CIR data here. The data be downloaded here: https://taxfoundation.org/data/all/global/corporate-tax-rates-by-country-2022/ (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
cit_data = "../data/raw/1980-2022-Corporate-Tax-Rates-Around-the-World-1.xlsx"

# Wage data
## Please give the path to the most recent ILO wage data here. The data be downloaded here: https://www.ilo.org/ilostat-files/WEB_bulk_download/indicator/EAR_4MTH_SEX_ECO_CUR_NB_A.csv.gz (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
wage_data = "../data/raw/EAR_4MTH_SEX_OCU_CUR_NB_A.csv"

# GDP and population data
## Please give the path to the most recent GDP and population data from the World Bank here. The data be downloaded here: https://databank.worldbank.org/source/world-development-indicators/preview/on, selecting the series "GDP (current US$)" and "Population, total" (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
gdp_population_data = "../data/raw/worldbank_gdp_population.csv"

# Health expenditure data
## Please give the path to the most recent WHO health expenditure data from the World Bank here. The data be downloaded here: https://apps.who.int/nha/database/ViewData/Indicators/en, selecting "Domestic General Government Health Expenditure" and "million current US$" as a unit (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
health_expenditure_data = "../data/raw/who_government_health_expenditure.xlsx"

# TJN unilateral cross data (used for grouping countries into regions or other groups)
unilateral_cross = "../data/raw/20230615_unilateral_cross.csv"

gravity_data = "../data/raw/Gravity_V202102.dta"

# TJN unilateral cross data (used for grouping countries into regions or other groups)
bilateral_panel = "../data/raw/20230101_bilateral_panel.csv"

orbis_data = "../data/raw/orbis.xlsx"

# Secrecy jurisdictions
tax_havens = {
    "ARE",
    "BHS",
    "BMU",
    "BRB",
    "CHE",
    "CYM",
    "CYP",
    "CUW",
    "GGY",
    "GIB",
    "HKG",
    "HUN",
    "IMN",
    "IRL",
    "JEY",
    "LUX",
    "MAC",
    "MLT",
    "MUS",
    "NLD",
    "PRI",
    "SGP",
    "VGB",
}
# Country groups
aggregated_country_groups = {"AFRIC", "AMER", "ASIAT", "EUROP", "FJT"}
other_country_groups = {"GRPS", "OAF", "OAM", "OAS", "OTE"}
country_groups = {"AFRIC", "AMER", "ASIAT", "EUROP", "FJT", "GRPS", "OAF", "OAM", "OAS", "OTE"}
