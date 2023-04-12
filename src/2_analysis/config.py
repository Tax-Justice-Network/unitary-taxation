import tjn_internal

# Years to compare with - A > B
YEAR_A = 2018
YEAR_B = 2017

# External paths for years A and B
SHAREPOINT_RAW_DATA_PATH = (
    tjn_internal.paths.sharepoint_root
    + r"/TJN - Shared Documents/Workstreams/Scale of Tax Injustice/State of Tax Justice report/Analysis/Corporate tax abuse/data/"
)
PATH_PSO_A = (
    SHAREPOINT_RAW_DATA_PATH + f"{YEAR_A}_tax_avoidance_sotj_table.xlsx"
)  # PSO stand for profit shifting outward
PATH_PSO_B = (
    SHAREPOINT_RAW_DATA_PATH + f"{YEAR_B}_tax_avoidance_sotj_table.xlsx"
)  # PREV stands dor previous year

PATH_INFLATION_WB = (
    SHAREPOINT_RAW_DATA_PATH + "20230308_world_bank_unilateral_panel.csv"
)  # WB stand for World Bank

PATH_MNC_PROFITS_A = SHAREPOINT_RAW_DATA_PATH + f"{YEAR_A}_replicates.csv"
PATH_MNC_PROFITS_B = (
    SHAREPOINT_RAW_DATA_PATH + f"{YEAR_B}_replicates.csv"
)  # MNC stands for Multinational Corporations


# Internal paths
PATH_PSO_A_CLEAN = (
    f"../../data/intermediate/analysis/profits_shifting_outward_{YEAR_A}.xlsx"
)
PATH_PSO_B_CLEAN = (
    f"../../data/intermediate/analysis/profits_shifting_outward_{YEAR_B}.xlsx"
)

### VISUALIZATIONS ###

# Years to evaluate
YEARS = [2016, 2017, 2018]
