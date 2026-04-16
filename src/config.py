# Update this config file before running the analysis for another year and after having stored the most up-to date raw data

# Insert first year of analysis
first_year = 2016

# Insert number of years you like to analyze
n_years = 7

# Specify paths (flat structure - old years archived in data/archive and output/archive)
data_raw = "../data/raw/"
data_intermediate = "../data/intermediate/"
data_final = "../data/final/"
output_tables = "../output/tables"
output_figures = "../output/figures"

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


# Define relevant country groups
## Secrecy jurisdictions
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
## Country groups
aggregated_country_groups = {"W", "A", "E", "F", "S"}
## Country groups "other"
other_country_groups = {"WXD", "A_O", "E_O", "F_O", "S_O", "W_O"}
## Non-countries
non_countries = aggregated_country_groups | other_country_groups
