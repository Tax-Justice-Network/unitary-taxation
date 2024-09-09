import tjn_tools
import pandas as pd
import seaborn as sns

# Set most recent cbcr year and its dataset here https://stats.oecd.org/Index.aspx?DataSetCode=CBCR_TABLEI
YEAR_CBCR = 2018
YEAR_SOTJ = 2023

DATA_PATH = "../../data"

pd.options.mode.chained_assignment = None  # default='warn', supress warnings for chained assignments
sns.set(font_scale=1.2, style="whitegrid")  # adjust settings for figures...

pd.set_option("display.max_columns", 100)  # ...and tables


# Input datasets - Notebook 1 - Section 1
CBCR_FILEraw = "../../data/raw/estimations/CBCR_TABLEI_20062023110215400.csv"
CBCR_FILE = "../../data/raw/estimations/CBCR_TABLEI_20062023110215400_corrIDN.csv"  # this is after a correction done for Indonesia, see notebook 1
ORBIS_FILE = "../../data/raw/estimations/orbis.xlsx"
CORPORATE_TAX_RATE_PATH = "../../data/raw/estimations/221124 Corporate tax rates.csv"
# Input datasets - Notebook 1 - Section 2
UNILATERAL_CROSS = f"{tjn_tools.paths.sharepoint_root}/TJN - Shared Documents/Research team/Data/Final data/20230615_unilateral_cross.csv"
UNILATERAL_PANEL = f"{tjn_tools.paths.sharepoint_root}/TJN - Shared Documents/Research team/Data/Final data/20230613_unilateral_panel.csv"
BILATERAL_CROSS = f"{tjn_tools.paths.sharepoint_root}/TJN - Shared Documents/Research team/Data/Final data/20230613_bilateral_cross.csv"
BILATERAL_PANEL = f"{tjn_tools.paths.sharepoint_root}/TJN - Shared Documents/Research team/Data/Final data/20230101_bilateral_panel.csv"
GRAV_FILE = f"{tjn_tools.paths.sharepoint_root}/TJN - Shared Documents/Research team/Data/Source data/022 CEPII/other/Gravity_V202102.dta"
LINK_FILE = (
    f"{tjn_tools.paths.sharepoint_root}/TJN - Shared Documents/Research team/Data/Source data/016 Papers/garcia-stausholm2020/combined_data_imputed copy.tsv"
)
# Path for METR analysis - Notebook 4
metr_path = f"{tjn_tools.paths.sharepoint_root}/TJN - Shared Documents/Workstreams/Scale of Tax Injustice/METR/2023"
