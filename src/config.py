# Update this config file before running the analysis for another year and after having stored the most up-to date raw data

# Insert first year of analysis
first_year = 2016

# Insert number of years you like to analyze
n_years = 6

# Specify paths. The year given here relates to the year when the State of Tax Justice is published
data_raw = "../data/2024/raw/"
data_intermediate = "../data/2024/intermediate/"
data_final = "../data/2024/final/"
output_tables = "../output/2024/tables/"
output_figures = "../output/2024/figures/"

# Specify the most up-to-date file names for the raw files

# CbCR file
## Please give the path to the most recent CbCR file here. This file can be downloaded here: https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI.
## The link still refers to the old data portal of the OECD. At a certain point in time, the data should be on the new data portal.
cbcr_data = "../data/2024/raw/OECD.CTP.TPS,DSD_CBCR@DF_CBCRI,1.0+all.csv"

# CIT rates
## Please give the path to the most recent corporate income tax (CIT) rate data here. The data has downloaded from two differentthe OECD for many countries here ('Measure: Combined corporate income tax rate'): https://data-explorer.oecd.org/vis?lc=en&fs[0]=Topic%2C1%7CTaxation%23TAX%23%7CCorporate%20tax%23TAX_CPT%23&pg=0&fc=Topic&bp=true&snb=15&df[ds]=dsDisseminateFinalDMZ&df[id]=DSD_TAX_CIT%40DF_CIT&df[ag]=OECD.CTP.TPS&df[vs]=1.0&dq=AUS%2BAUT%2BBEL%2BCAN%2BCHL%2BCOL%2BCRI%2BCZE%2BDNK%2BEST%2BFIN%2BFRA%2BDEU%2BGRC%2BHUN%2BISL%2BIRL%2BISR%2BITA%2BJPN%2BKOR%2BLVA%2BLTU%2BLUX%2BMEX%2BNLD%2BNZL%2BNOR%2BPOL%2BPRT%2BSVK%2BSVN%2BESP%2BSWE%2BCHE%2BTUR%2BGBR%2BUSA%2BALB%2BAGO%2BAND%2BAIA%2BATG%2BARG%2BARM%2BABW%2BAZE%2BBHS%2BBHR%2BGGY%2BBRB%2BBLZ%2BBEN%2BBMU%2BBIH%2BBWA%2BBRA%2BVGB%2BBRN%2BBGR%2BBFA%2BCPV%2BCMR%2BCYM%2BCHN%2BCOG%2BCOK%2BCIV%2BHRV%2BCUW%2BCOD%2BDJI%2BDMA%2BDOM%2BEGY%2BSWZ%2BFRO%2BGAB%2BGEO%2BGIB%2BGRL%2BGRD%2BHTI%2BHND%2BHKG%2BIND%2BIDN%2BIMN%2BJAM%2BJEY%2BJOR%2BKAZ%2BKEN%2BKWT%2BLBR%2BLIE%2BMAC%2BMYS%2BMDV%2BMLT%2BMRT%2BMUS%2BMCO%2BMNG%2BMNE%2BMSR%2BMAR%2BNAM%2BNGA%2BMKD%2BOMN%2BPAK%2BPAN%2BPNG%2BPRY%2BPER%2BPHL%2BQAT%2BROU%2BKNA%2BLCA%2BVCT%2BWSM%2BSMR%2BSAU%2BSEN%2BSRB%2BSYC%2BSLE%2BSGP%2BZAF%2BLKA%2BTHA%2BTGO%2BTTO%2BTUN%2BTCA%2BUKR%2BARE%2BURY%2BUZB%2BVNM%2BZMB.A.CIT_C.ST..S13%2BS1311%2BS13M..&to[TIME_PERIOD]=false&pd=2016%2C2024
# and for all other ones here: https://taxfoundation.org/data/global-tax/?_sft_topics=corporate-tax-rates-around-the-world#results (see notebook "1_clean").
cit_data_oecd = "../data/2024/raw/OECD.CTP.TPS,DSD_TAX_CIT@DF_CIT,1.0+all.csv"
cit_data_taxfoundation = "../data/2024/raw/1980_2023_Corporate_Tax_Rates_Around_the_World_Tax_Foundation.xlsx"

# Wage data
## Please give the path to the most recent ILO wage data "Wages and Working Time Statistics (COND)" here. The data be downloaded here: https://www.ilo.org/ilostat-files/WEB_bulk_download/indicator/EAR_4MTH_SEX_ECO_CUR_NB_A.csv.gz (see notebook "1_clean").
wage_data = "../data/2024/raw/Wages and Working Time Statistics (COND).csv"

# GDP and population data
## Please give the path to the most recent GDP and population data from the World Bank here. The data be downloaded here: https://databank.worldbank.org/source/world-development-indicators/preview/on, selecting the series "GDP (current US$)" and "Population, total" (see notebook "1_clean").
gdp_population_data = "../data/2024/raw/gdp_population_world_bank.csv"

# Health expenditure data
## Please give the path to the most recent WHO health expenditure data here. The data be downloaded here: https://apps.who.int/nha/database/Select/Indicators/en selecting "Domestic General Government Health Expenditure" and "million current US$" as a unit (see notebook "1_clean").
health_expenditure_data = "../data/2024/raw/WHO health expenditure.xlsx"

# Tax revenue data
## Please give the path to the most recent tax revenue data here. The data be downloaded here: https://api.worldbank.org/v2/en/indicator/GC.TAX.TOTL.GD.ZS?downloadformat=csv
tax_revenue_data = "../data/2024/raw/Tax Revenue Data World Bank.csv"

# Data on regions and membership in regional or international organizations
## Please copy the most recent version of TJN's unilateral cross data from the TJN sharepoint: "...\Tax Justice Network Ltd\TJN - Shared Documents\Research team\Data\Final data\{date}_unilateral_cross.csv"
## in the data/raw/{sotj_year} folder and give the path below.
unilateral_cross_data = "../data/2024/raw/20240626_unilateral_cross.csv"

# Gravity data (including data on distance, but also common history, common currency and so on)
## Please copy the most recent version of the CEPII gravity data used for the imputation, from the TJN sharepoint: "...\Tax Justice Network Ltd\TJN - Shared Documents\Research team\Data\Source data\022 CEPII"
## in the data/raw/{sotj_year} folder and give the path below.
gravity_data = "../data/2024/raw/Gravity_V202211.csv"

# Bilateral Trade
## Please copy the most recent version of cleaned Comtrade Trade Data to the folder data/raw/{sotj_year} and give the path below.
## The data is processed and cleaned by BACI which includes mirrored statistics where missings occur and can be found at
## TJN's sharepoint at: "...\Tax Justice Network Ltd\TJN - Shared Documents\Research team\Data\Source data\033 BACI"
comtrade_data = "../data/2024/raw/trade.dta"

# Bilateral FDI
## Please copy the most recent version of the IMF's FDI data to the folder data/raw/{sotj_year} and give the path below.
## The data is from the IMF's Coordinated Direct Investment Survey (CDIS, https://data.imf.org/?sk=40313609-F037-48C1-84B1-E1F1CE54D6D5)
## It is cleaned to include mirrored statistics where missings occur in the IFF Tracker Github folder: "GitHub\iff_tracker\data"
cdis_data = "../data/2024/raw/fdi.dta"

# Bilateral Portfolio Investment
## Please copy the most recent version of the IMF's Portfolio Investment data to the folder data/raw/{sotj_year} and give the path below.
## The data is from the IMF's Coordinated Portfolio Investment Survey (CPIS, https://data.imf.org/?sk=b981b4e3-4e58-467e-9b90-9de0c3367363)
## It is cleaned to include mirrored statistics where missings occur in the IFF Tracker Github folder: "GitHub\iff_tracker\data"
cpis_data = "../data/2024/raw/portfolio_investment.dta"

# Bilateral banking claims
## Please copy the most recent version of the bilateral bank deposits from the Bank of International Settlement (BIS) to the folder data/raw/{sotj_year} and give the path below.
## The data is from the BIS' Locational Banking Statistics (LBS) Table 6.2, https://data.bis.org/topics/LBS/data?pdqId=BIS%2CPDQ_A6_2%2C1.0&data_view=table&filter=FREQ%3DQ%255EL_MEASURE%3DS%255EL_INSTR%3DA%257CG%255EL_DENOM%3DTO1%255EL_CURR_TYPE%3DA%255EL_PARENT_CTY_TXT%3DAll%2520countries%2520%28total%29%255EL_REP_BANK_TYPE%3DA%255EL_CP_SECTOR%3DA%257CN%255EL_CP_COUNTRY_TXT%3DArgentina%255EL_POS_TYPE%3DN%255ELAST_N_PERIODS%3D1&rows=L_INSTR%7CL_REP_CTY&cols=L_POSITION%7CL_CP_SECTOR%7CTIME_PERIOD&settings=asc%7Cdesc%7Cname
## It is cleaned to include mirrored statistics where missings occur in the IFF Tracker Github folder: "GitHub\iff_tracker\data"
bis_data = "../data/2024/raw/20240630_bis_lbs_tablea6_2.csv"

# Consolidated banking claims per country
## Please copy the most recent version of the total consolidated banking claims from the BIS (Table B4) that can be downloaded here: https://data.bis.org/static/bulk/WS_CBS_PUB_csv_col.zip
bis_consolidated_data = "../data/2024/raw/WS_CBS_PUB_csv_col.csv"

# Number of firms
## Orbis data on number of firms above USD 750mn revenue headquartered in a country, from Orbis flatfiles (to be obtained externally).
## Please store the data in the folder data/raw/{sotj_year} and adjust the path below accordingly.
orbis_data = "../data/2024/raw/orbis.xlsx"

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
