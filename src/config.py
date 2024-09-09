# Update this config file before running the analysis for another year and after having stored the most up-to date raw data

# Insert first year of analysis
first_year = 2016

# Insert number of years you like to analyze
n_years = 6

# Specify paths (no need to update anything here if you are working in the Github directory)
data_raw = "../data/raw/2024/"
data_intermediate = "../data/intermediate/2024/"
data_final = "../data/final/2024/"
output_tables = "../output/tables/2024/"
output_figures = "../output/figures/2024/"

# Specify the most up-to-date file names for the raw files

# CbCR file
## Please give the path to the most recent CbCR file here. This file can be downloaded here: https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.

cbcr_data = "../data/raw/2024/OECD.CTP.TPS,DSD_CBCR@DF_CBCRI,1.0+all.csv"

# CIT rates
## Please give the path to the most recent CIR data here. The data be downloaded from the OECD for many countries here ('Measure: Combined corporate income tax rate'): https://data-explorer.oecd.org/vis?lc=en&fs[0]=Topic%2C1%7CTaxation%23TAX%23%7CCorporate%20tax%23TAX_CPT%23&pg=0&fc=Topic&bp=true&snb=15&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_TAX_CIT%40DF_CIT&df[ag]=OECD.CTP.TPS&df[vs]=1.0&dq=AUS%2BAUT%2BBEL%2BCAN%2BCHL%2BCOL%2BCRI%2BCZE%2BDNK%2BEST%2BFIN%2BFRA%2BDEU%2BGRC%2BHUN%2BISL%2BIRL%2BISR%2BITA%2BJPN%2BKOR%2BLVA%2BLTU%2BLUX%2BMEX%2BNLD%2BNZL%2BNOR%2BPOL%2BPRT%2BSVK%2BSVN%2BESP%2BSWE%2BCHE%2BTUR%2BGBR%2BUSA%2BALB%2BAGO%2BAND%2BAIA%2BATG%2BARG%2BARM%2BABW%2BAZE%2BBHS%2BBHR%2BGGY%2BBRB%2BBLZ%2BBEN%2BBMU%2BBIH%2BBWA%2BBRA%2BVGB%2BBRN%2BBGR%2BBFA%2BCPV%2BCMR%2BCYM%2BCHN%2BCOG%2BCOK%2BCIV%2BHRV%2BCUW%2BCOD%2BDJI%2BDMA%2BDOM%2BEGY%2BSWZ%2BFRO%2BGAB%2BGEO%2BGIB%2BGRL%2BGRD%2BHTI%2BHND%2BHKG%2BIND%2BIDN%2BIMN%2BJAM%2BJEY%2BJOR%2BKAZ%2BKEN%2BKWT%2BLBR%2BLIE%2BMAC%2BMYS%2BMDV%2BMLT%2BMRT%2BMUS%2BMCO%2BMNG%2BMNE%2BMSR%2BMAR%2BNAM%2BNGA%2BMKD%2BOMN%2BPAK%2BPAN%2BPNG%2BPRY%2BPER%2BPHL%2BQAT%2BROU%2BKNA%2BLCA%2BVCT%2BWSM%2BSMR%2BSAU%2BSEN%2BSRB%2BSYC%2BSLE%2BSGP%2BZAF%2BLKA%2BTHA%2BTGO%2BTTO%2BTUN%2BTCA%2BUKR%2BARE%2BURY%2BUZB%2BVNM%2BZMB.A.CIT_C.ST..S13%2BS1311%2BS13M..&to[TIME_PERIOD]=false&pd=2016%2C2024
# and for all other ones here: https://taxfoundation.org/data/global-tax/?_sft_topics=corporate-tax-rates-around-the-world#results (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
cit_data_oecd = "../data/raw/2024/OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,1.0+all.csv"
cit_data_taxfoundation = "../data/raw/2024/1980_2023_Corporate_Tax_Rates_Around_the_World_Tax_Foundation.xlsx"

# Wage data
## Please give the path to the most recent ILO wage data here. The data be downloaded here: https://www.ilo.org/ilostat-files/WEB_bulk_download/indicator/EAR_4MTH_SEX_ECO_CUR_NB_A.csv.gz (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
wage_data = "../data/raw/2024/EAR_4MTH_SEX_ECO_CUR_NB_A.csv"

# GDP and population data
## Please give the path to the most recent GDP and population data from the World Bank here. The data be downloaded here: https://databank.worldbank.org/source/world-development-indicators/preview/on, selecting the series "GDP (current US$)" and "Population, total" (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
gdp_population_data = "../data/raw/2024/e1345356-4d09-4026-a69b-adacf3d70354_Data.csv"

# Health expenditure data
## Please give the path to the most recent WHO health expenditure data here. The data be downloaded here: https://apps.who.int/nha/database/Select/Indicators/en selecting "Domestic General Government Health Expenditure" and "million current US$" as a unit (see notebook "1_clean").
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
health_expenditure_data = "../data/raw/2024/NHA indicators.xlsx"

# Tax revenue data
## Please give the path to the most recent tax revenue data here. The data be downloaded here: https://api.worldbank.org/v2/en/indicator/GC.TAX.TOTL.GD.ZS?downloadformat=csv
## In case you make manual adjustments to the file (not recommended), insert the adjusted file here.
tax_revenue_data = "../data/raw/2024/API_GC.TAX.TOTL.GD.ZS_DS2_en_csv_v2_2788687.csv"

# TJN unilateral cross data used for grouping countries into regions or other groups, from the TJN sharepoint:
unilateral_cross_data = "../data/raw/2024/20240626_unilateral_cross.csv"

# TJN bilateral panel data used for ..., from the TJN sharepoint:
bilateral_panel_data = "../data/raw/2024/20230101_bilateral_panel.csv"

# CEPI gravity data used for the imputation, from the TJN sharepoint: "...\Tax Justice Network Ltd\TJN - Shared Documents\Research team\Data\Source data\022 CEPII"
gravity_data = "../data/raw/2024/Gravity_V202211.csv"

# Comtrade Trade Data as processed and cleaned by BACI
comtrade_data = "../data/raw/2024/trade.dta"

# FDI from CDIS
cdis_data = "../data/raw/2024/fdi.dta"

# PI from CPIS
cpis_data = "../data/raw/2024/portfolio_investment.dta"

# bilateral bank deposits from BIS
bis_data = "../data/raw/2024/20240630_bis_lbs_tablea6_2.csv"

# Orbis data
orbis_data = "../data/raw/2024/orbis.xlsx"

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
aggregated_country_groups = {"W", "A", "E", "F", "S"}
other_country_groups = {"WXD", "A_O", "E_O", "F_O", "S_O"}
country_groups = {"AFRIC", "AMER", "ASIAT", "EUROP", "FJT", "GRPS", "OAF", "OAM", "OAS", "OTE"}
