import tjn_internal

# Set most recent cbcr year and its dataset here https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI
YEAR_CBCR = 2018
YEAR_SOTJ = 2023


# Input datasets - Notebook 1 - Section 1
CBCR_FILE = f"../data/raw/CBCR_TABLEI_17112022170811646.csv"
ORBIS_FILE = f"../data/raw/orbis.xlsx"
CORPORATE_TAX_RATE_PATH = f"../data/raw/221124 Corporate tax rates.csv"
# Input datasets - Notebook 1 - Section 2
UNILATERAL_CROSS = f"{tjn_internal.paths.final_data}/20210810_country-level-data.csv"  # TODO Take most up-to-date version
UNILATERAL_PANEL = f"{tjn_internal.paths.final_data}/20210810_country-year-level-data.csv"  # TODO Take most up-to-date version
BILATERAL_CROSS = f"{tjn_internal.paths.final_data}/20210810_bilateral-year-level-data.csv"  # TODO Take most up-to-date version
GRAV_FILE = f"{tjn_internal.paths.source_data}/022 CEPII/other/Gravity_V202102.dta"
LINK_FILE = f"{tjn_internal.paths.source_data}/016 Papers/garcia-stausholm2020/combined_data_imputed copy.tsv"
