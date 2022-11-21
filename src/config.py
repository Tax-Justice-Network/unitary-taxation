import tjn_internal

# Set last year that the data was updated here https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI
YEAR_CBCR = 2018
YEAR_SOTJ = 2023


# Input datasets - Notebook 1 - Section 1
CBCR_FILE = f"../data/raw/CBCR_TABLEI_17112022170811646.csv"
ORBIS_FILE = f"../data/raw/orbis.xlsx"  # TODO Use up-to-date data #TODO ask Javier how and where to retrieve it
# Input datasets - Notebook 1 - Section 2
UNILATERAL_CROSS = f"{tjn_internal.paths.final_data}/20210810_country-level-data.csv"  # unilateral cross #TODO Use 2022 data
UNILATERAL_PANEL = f"{tjn_internal.paths.final_data}/20210810_country-year-level-data.csv"  # unilateral panel #TODO Use 2022 data
BILATERAL_CROSS = f"{tjn_internal.paths.final_data}/20210810_bilateral-year-level-data.csv"  # bilateral cross #TODO Use 2022 data
GRAV_FILE = f"{tjn_internal.paths.source_data}/022 CEPII/other/Gravity_V202102.dta"  # TODO Use 2022 data
LINK_FILE = f"{tjn_internal.paths.source_data}/016 Papers/garcia-stausholm2020/combined_data_imputed copy.tsv"  # TODO Use 2022 data
