import tjn_internal

# Set most recent cbcr year and its dataset here https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI
YEAR_CBCR = 2018
YEAR_SOTJ = 2023


# Input datasets - Notebook 1 - Section 1
CBCR_FILE = "../../data/raw/estimations/CBCR_TABLEI_12062023113505025.csv"
ORBIS_FILE = "../../data/raw/estimations/orbis.xlsx"
CORPORATE_TAX_RATE_PATH = "../../data/raw/estimations/221124 Corporate tax rates.csv"
# Input datasets - Notebook 1 - Section 2
UNILATERAL_CROSS = f"{tjn_internal.paths.final_data}/20210810_country-level-data.csv"  # TODO Take most up-to-date version
UNILATERAL_PANEL = f"{tjn_internal.paths.final_data}/20210810_country-year-level-data.csv"  # TODO Take most up-to-date version
BILATERAL_CROSS = f"{tjn_internal.paths.final_data}/20210810_bilateral-year-level-data.csv"  # TODO Take most up-to-date version
GRAV_FILE = f"{tjn_internal.paths.source_data}/022 CEPII/other/Gravity_V202102.dta"
LINK_FILE = f"{tjn_internal.paths.source_data}/016 Papers/garcia-stausholm2020/combined_data_imputed copy.tsv"
# Path for METR analysis - [I will adapt the structure of my notebook to also include every single input file here based on tjn_internal in the next days]
path = f"{tjn_internal.paths.sharepoint_root}/TJN - Shared Documents/Workstreams/Scale of Tax Injustice/METR/2023"
# Path for wealth tax estimates
WEALTH_TAX = f"{tjn_internal.paths.sharepoint_root}/TJN - Shared Documents/Workstreams/Scale of Tax Injustice/Wealth tax/2_data"
WEALTH_TAX_INPUT = f"{WEALTH_TAX}/1_input"
WEALTH_TAX_OUTPUT = f"{WEALTH_TAX}/2_output"
