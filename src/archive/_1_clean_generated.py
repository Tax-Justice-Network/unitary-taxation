#!/usr/bin/env python
# coding: utf-8

# ## The State of Tax Justice: Data cleaning
# TO DO: Get Orbis GUO information per year adn adjust the code (of this notebook and the imputation notebook) accordingly.
# 
# - Author: Alison Schultz, based on Javier Garcia-Bernado's work
# - Created: 4 August 2023
# - Last updated: 19 September 2024
# 
# **Description**
# - This notebook is one out of three notebooks to estimate the tax losses caused by profit shifting by multinational enterprises (MNEs). The analysis used the misalignment method based on the country-by-country reports (CbCR) published by the OECD.
# - Details on the misalignment method and its background can be found here: https://www.sciencedirect.com/science/article/pii/S0305750X23003455, the working paper version is here: https://www.econstor.eu/bitstream/10419/286362/1/wp-2023-33.pdf 
# - This notebook imports and cleans all data. It produces two relevant datasets:
#     - '{data_final}/cbcr_main_no_imputation_allsubgroupsonly.csv': Cleaned CbCR data with all relevant variables for calculating misalignment based on CbCR reporting countries only in notebook '3_estimate_profit_shifting'. {data_final} and all other relevant paths are defined in 'config.py'.
#     - '{data_final}/cbcr_main_no_imputation.csv': Cleaned CbCR data with all relevant variables for calculating misalignment. Each parent-partner country combination has three rows in this dataset, one row for companies with positive profits, one for those with negative profits and one for all.
#     - "{data_intermediate}/cbcr_imputation_sample.csv": Cleaned CbCR data with all relevant variables for calculating misalignment and all variables that are used to estimate a comprehensive, global CbCR dataset later in the process. Values will later be imputed for those parent-partner combinations where the parent is not reporting to the OECD and for those where reporting is only done for aggregate country groups in notebook "2_multiple_imputation". For the imputation, a large range of ocuntry-level and bilateral data is added.
# 
# **Outline**
# 1. Import and clean CbCR data
# 2. Import and clean other data needed for the analysis
# 3. Prepare dataset for imputation
# 
# 
# **To dos before running this notebook**
# 1. Adjust years for which the analysis should be run in 'config.py'.
# 2. Adjust all paths in 'config.py' for the current analysis.
# 3. Store the up-to-date versions of different datasets as specified in 'config.py' and update the dataset names where necessary.
# 3. Check the following resources regarding the CbCR data and adjust Section 1.2 of this notebook accordingly.
#     - Most recent version of OECD disclaimer: https://www.oecd.org/tax/tax-policy/anonymised-and-aggregated-cbcr-statistics-disclaimer.pdf
#     - Country notes (instert country of interest for COUNTRY): https://www.oecd.org/tax/tax-policy/COUNTRY-cbcr-country-specific-analysis.pdf
#     - Skim through raw data for potential misreporting (e.g. very high values for ncertain countries where no such values are expected)
# 4. Load the environment "sotj_profit_shifting_estimates" (available via 'sotj_profit_shifting_estimates/environment.yml')

# ### 0. Load packages and define basic functions

# In[56]:


import pandas as pd
import numpy as np
from config import *
from tjn_tools import data_processing
import statsmodels.formula.api as smf
from itertools import product
from scipy.stats.mstats import winsorize


# Define functions that are relevant for the entire notebook

# In[57]:


# Function to check for missing values in critical columns
def check_missing_values(df, critical_columns):
    total_observations = len(df)
    missing = df[critical_columns].isnull().sum()

    for column, count in missing.items():
        if count > 0:
            percentage = (count / total_observations) * 100
            print(f"{count} missing values found in column '{column}' "
                  f"({percentage:.2f}% of total observations).")
        else:
            print(f"No missing values found in column '{column}'.")

# Function to check for duplicates
def check_duplicates(df, name):
    if df.duplicated().any():
        print(f"Warning: {name} contains duplicate rows.")
    else:
        print(f"No duplicates found in {name}.")


# ### 1. Import and clean CbCR data
# - 1.1 Import CbCR data
# - 1.2 Clean CbCR data
# - 1.3 Calculate ETRs

# #### 1.1 Import CbCR data
# Import the data and adjust small mistakes manually

# In[58]:


# CBCR variables to extract from the dataset
cbcr_variables = ['REF_AREA', 'Reference area', 'COUNTERPART_AREA', 'Counterpart area', 'Profit grouped by', 'TIME_PERIOD', 
                  'Unrelated party revenues', 'Profit (loss) before income tax', 'Adjusted profit (loss) before income tax', 
                  'Income tax paid (on cash basis)', 'Income tax accrued - current year', 'Employees', 
                  'Tangible assets other than cash and cash equivalents', 'Stated capital', 'Total revenues', 
                  'Related party revenues', 'Holding or managing intellectual property business activity', 
                  'Multinational enterprise groups', 'Multinational enterprise sub-groups', 'Entities']

# Read the CBCR data
cbcr_long = pd.read_csv(cbcr_data)

# Pivot the long data into wide format
cbcr_wide = pd.pivot_table(cbcr_long, index=['REF_AREA', 'Reference area', 'COUNTERPART_AREA', 'Counterpart area', 'Profit grouped by', 'TIME_PERIOD'], 
                           values="OBS_VALUE", columns="Measure").reset_index()

# Extract only the required variables
cbcr = cbcr_wide[cbcr_variables]

# Remove non-existing jurisdictions (Netherland Antilles, Bouvet Island) and stateless entities, which are a source of double counting
cbcr = cbcr[(cbcr['COUNTERPART_AREA'] != 'ANT_F') & (cbcr['COUNTERPART_AREA'] != 'BVT') & (cbcr['COUNTERPART_AREA'] != 'STLS')] 

# Rename columns to more readable names
cbcr.rename(columns={
    'REF_AREA': 'iso_parent',
    'Reference area': 'parent_jurisdiction',
    'COUNTERPART_AREA': 'iso_partner',
    'Counterpart area': 'partner_jurisdiction',
    'Profit grouped by': 'grouping',
    'TIME_PERIOD': 'year',
    'Unrelated party revenues': 'unrelated_party_revenues',
    'Profit (loss) before income tax': 'profit_loss_before_income_tax',
    'Adjusted profit (loss) before income tax': 'adjusted_profit_loss_before_income_tax',
    'Income tax paid (on cash basis)': 'income_tax_paid_on_cash_basis',
    'Income tax accrued - current year': 'income_tax_accrued_current_year',
    'Employees': 'n_employees',
    'Tangible assets other than cash and cash equivalents': 'tangible_assets_except_cash',
    'Stated capital': 'stated_capital',
    'Total revenues': 'total_revenues',
    'Related party revenues': 'related_party_revenues',
    'Holding or managing intellectual property business activity': 'holding_or_managing_ip',
    'Multinational enterprise groups': 'n_cbcr',
    'Multinational enterprise sub-groups': 'n_cbcr_groups',
    'Entities': 'n_entities'
}, inplace=True)

# Check for duplicates
check_duplicates(cbcr, "cbcr")

# Check for missing values after renaming columns
check_missing_values(cbcr, ['unrelated_party_revenues','profit_loss_before_income_tax','adjusted_profit_loss_before_income_tax',
    'income_tax_paid_on_cash_basis','income_tax_accrued_current_year','n_employees','tangible_assets_except_cash',
    'stated_capital','total_revenues','related_party_revenues','holding_or_managing_ip','n_cbcr','n_cbcr_groups','n_entities'])


# #### Make some manual adjustments to the data to correct misreporting

# In[59]:


# In a few instances, countries report "rest of the world" with "W_O", rather than with the correct WXD
# Replace 'W_O' with 'WXD' in 'iso_partner' and sum up the values in case both exist in a given year
cbcr.loc[cbcr['iso_partner'] == 'W_O', 'iso_partner'] = 'WXD'
grouping_columns = ['iso_parent', 'iso_partner', 'parent_jurisdiction', 'year', 'grouping']
variables_to_sum = [
    'unrelated_party_revenues',
    'profit_loss_before_income_tax',
    'adjusted_profit_loss_before_income_tax',
    'income_tax_paid_on_cash_basis',
    'income_tax_accrued_current_year',
    'n_employees',
    'tangible_assets_except_cash',
    'stated_capital',
    'total_revenues',
    'related_party_revenues',
    'holding_or_managing_ip',
    'n_cbcr',
    'n_cbcr_groups',
    'n_entities'
]

duplicates_mask = cbcr.duplicated(subset=grouping_columns, keep=False) & (cbcr['iso_partner'] == 'WXD')
duplicates = cbcr[duplicates_mask]
non_duplicates = cbcr[~duplicates_mask]
aggregation_dict = {
    'partner_jurisdiction': 'first',  # Keep the first 'partner_jurisdiction' value
    **{var: 'sum' for var in variables_to_sum},  # Sum specified variables
    **{col: 'first' for col in cbcr.columns if col not in grouping_columns + ['partner_jurisdiction'] + variables_to_sum}
}
aggregated_duplicates = duplicates.groupby(grouping_columns, as_index=False).agg(aggregation_dict)
cbcr = pd.concat([non_duplicates, aggregated_duplicates], ignore_index=True)

# Correct mistake in Argentinian data, where "S" has been used for "Other Asia", instead of "S_O"
cbcr.loc[
    (cbcr['iso_parent'] == "ARG") & 
    (cbcr['iso_partner'] == "S") & 
    (cbcr['year'] == 2019), 
    'iso_partner'
] = 'S_O'

# Even though Japan and Sweden do have a line for the continents in their 2021 reporting, these lines are all empty.
# As they report on the "other" countries from the continents for the same year, we set the continent reporting to 0 
rows_to_drop = cbcr.loc[
    (cbcr['iso_parent'].isin(["JPA", "SWE"])) &
    (cbcr['year'] == 2021) &
    (cbcr['iso_partner'].isin(["A", "E", "F", "S"]))
].index
cbcr.drop(index=rows_to_drop, inplace=True)

# Chile reports several lines without any (or without enough) content: 
# In 2016, WXD is empty, in 2018, USA and F are empty, in 2019, F_O is empty. 
# Therefore, these lines are dropped 
rows_to_drop_chile = cbcr.loc[
    (cbcr['iso_parent'] == "CHL") &
    (
        (cbcr['year'] == 2016) & (cbcr['iso_partner'] == "WXD") |
        (cbcr['year'] == 2018) & (cbcr['iso_partner'].isin(["USA", "F"])) |
        (cbcr['year'] == 2019) & (cbcr['iso_partner'] == "F_O")
    )
].index
cbcr.drop(index=rows_to_drop_chile, inplace=True)

# Canada reports only on some values in 2019. We drop the line where not even profits are reported for F
rows_to_drop_canada = cbcr.loc[
    (cbcr['iso_parent'] == "CAN") & (cbcr['year'] == 2019) & (cbcr['iso_partner'] == "F")
].index
cbcr.drop(index=rows_to_drop_canada, inplace=True)


# #### Check number of reporting and number of partner countries
# - Be aware that some of the "reporting countries" do not report on an actual country-by-country basis, but rather summarize country groups or just report domestic versus foreign numbers.
# - In the 2024 data, the following reporting countries do not report country-by-country. We exclude those from the "clean" analysis where we only use values that are actually in the data.
#     - Austria: Only continents in all years
#     - Czechia: Only Czechia versus rest of the world from 2019 to 2021
#     - Finland: Only Finland and rest of the world between 2016 and 2018 and Finland and continents between 2019 and 2021
#     - Greece: Only Greece and continents between 2017 and 2019
#     - Hungary: Only Hungary versus rest of the world between 2018 and 2021
#     - Isle of Man: Only continents between 2017 and 2020
#     - Ireland: Only Ireland versus rest of the world in all years
#     - Korea: Only Korea and rest of the world betweem 2016 and 2018 and Korea and continents between 2019 and 2021
#     - Macau: Only Macau versus rest of the world between 2019 and 2021
#     - Mauritius: Only Mauritius and continents between 2019 and 2021
#     - Morocco: Only Morocco and continents in 2021
#     - Netherlands: Only Netherlands versus rest of the world between 2016 and 2017
#     - Norway: Only Norway and continents 2016 and 2017
#     - New Zealand: Only New Zealand versus rest of the world between 2018 and 2021
#     - Poland: Only Poland and continents 2019 to 2021
#     - Sweden: Only Sweden and continents in all years
#     - United Kingdom: Only UK and continents between 2017 and 2021
#   

# In[60]:


# Sample of reporting jurisdictions and partner jurisdictions 
parent_countries = cbcr['iso_parent'].drop_duplicates()
partner_countries  = cbcr['iso_partner'].drop_duplicates()

# Optionally print the number of unique jurisdictions for verification
print(f"Number of unique parent jurisdictions: {len(parent_countries)}")
print(f"Number of unique partner jurisdictions, including aggregated regions: {len(partner_countries)}")

# Count partner countries that are not in the non_countries list
partner_countries_filtered = partner_countries[~partner_countries.isin(non_countries)]
print(f"Number of unique partner jurisdictions, without aggregated regions: {len(partner_countries_filtered)}")


# #### Make some manual adjustments to the data to correct misreporting

# #### 1.2 Clean CBCR data: Adjust for the double counting of dividends (as we take it from 2017 where Garcia-Bernardo/Janský suggest these adjustments)
# 
# 
# **TO DO: CHECK WHETHER ETR ARGUMENT (DOMESTIC VERSUS FOREIGN ETR) MAKES SENSE FOR 2016, 2018, and 2019**
# 
# **Mario Q: we need to complete the dividends correction, right? This is not complete**
# 
# The CbCR data has the problem that dividends are partly double counted. We correct for this double counting, according to the following sources and considerations. The correction is applied to all subgroups (if their total profits are > 0) and the subgroup with positive profits. From 2020 on, there were rules in place on how to deal with intra-company dividends. If companies have followed these rules/countries have enforced these rules, the double counting should not be a problem from 2020 on. The OECD reports that the problem might persist, but we anyways assume that the issue is solved (as we somehow have to rely on the data to adhere to standards).
# - Argentina-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Australia-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Austria-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Belgium based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 50% of profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Bermuda based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 50% of profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Brazil-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Canada-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Switzerland-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Chile-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Cayman Islands based MNCs
#     - 2016 to 2019:
#         - MNCs have negative profits, so double counting is unlikely, no reduction in domestic or foreign profits
# - Denmark-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - France-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Germany-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Greece-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Hong-Kong-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Indonesia-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - India-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Ireland-based MNCs: CBCR Country notes: https://www.oecd.org/tax/tax-policy/ireland-cbcr-country-specific-analysis.pdf
#     - 2016: No issues found -> no correction
#     - 2018: Ireland-based MNCs have negative profits -> double counting should not be an issue, so we don't control for it
# - Isle of Man based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 50% of profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Italy-based MNCs: CBCR country notes: https://www.oecd.org/tax/tax-policy/italy-cbcr-country-specific-analysis.pdf
#     - 2016: The median value of dividends is XXX, the  average value of the share of dividends is equal to 38.2%, thus implying that dividends are concentrated in few firms.
#     - 2018: The mean and the median percentage of intracompany dividends estimated to be included in the CBCR, profit(loss) figure at the subgroup level is respectively 50% and 24% -> reduce profits by 50% to be conservative
#         - domestic: We reduce 50% of profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Japan-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Latvia-based MNCs
#     - 2016 to 2019:
#         - domestic: We do not reduce profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Lithuania-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Luxembourg-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Malaysia-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Mauritius-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Mexico-based MNCs:
#     - 2016 to 2019: According to the CBCR data, domestic ETRs similar to foreign ETRs -> likely no large double counting
#         - domestic: We do not reduce profits (as domestic ETR similar to foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Netherlands based MNCs: https://www.oecd.org/tax/tax-policy/united-kingdom-cbcr-country-specific-analysis.pdf
#     - 2016: 5794 out of 36802 is double counted
#         - domestic: We reduce profits by 15.74%
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
#     - 2017: NLD reports corrected data already in source
#         - domestic: We use corrected numbers
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
#     - 2018: NLD reports corrected data already in source
#         - domestic: We use corrected numbers
# - New Zealand-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
#   Norway-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Panama-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Peru-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Portugal-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Romania-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Saudi-Arabia-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Singapore based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 50% of profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Slovenia-based MNCs:
#     - 2016 to 2019:
#         - domestic: We do not reduce profits (as domestic ETR similar to foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Spain-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - South Africa-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Sweden-based MNCs: CBCR country notes: https://www.oecd.org/tax/tax-policy/sweden-cbcr-country-specific-analysis.pdf
#     - 2016: Dividends share 51.95%
#         - domestic: We reduce 51.59% of profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
#     - 2018: "...under the assumption that all companies included dividends in their CbCR figures one can subtract USD 29.8 billion from USD 49.1 billion..."
#         - domestic: We reduce 60.69% of reported profits
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - Turkey-based MNCs
#     - 2016 to 2019:
#         - domestic: We reduce 35% of profits (as domestic ETR << than foreign ETR)
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
# - United Kingdom based MNCs: https://www.oecd.org/tax/tax-policy/united-kingdom-cbcr-country-specific-analysis.pdf
#     - 2016: The total value of dividends extracted for groups we believe had included intragroup dividends received was approximately £55 billion: 78.169865 out of 152.918884 = 51.1%
#         - domestic: we reduce profits by 51.1%
#         - foreign: We do not reduce profits (except for tax havens and groups, see below)
#     - 2017: UK reports corrected data already in source -> We use corrected numbers
#     - 2018: UK reports corrected data already in source -> We use corrected numbers
# - US-based MNCs: García-Bernardo, Janský & Zucman (2022), https://gabriel-zucman.eu/files/GBJZ2021.pdf
#     - 2016
#     - 2017: domestic: 55%, foreign: 7%
#     - 2018: domestic: 75%, foreign: 39%
#         - Domestic profits: reduce 74% of profits
#         - Foreign profits: reduce 45% of profits for tax havens (as obvious from data, not planned)
# - Foreign income in tax havens and country groups
#         - booked in tax havens: 
#             - 2018: For US-based MNCs, García-Bernardo, Janský & Zucman (2022) find a double counting of 9% -> We remove 9% of profits booked in tax havens
#         - booked in grouped jurisdictions: As some of the grouped jurisdictions are tax havens, we apply 9% for 50% of the jurisdictions -> We remove 4.5% of profits
# 
# We do not correct for participation results (de-mergers, takeovers and disposal), as they typically involve tax avoidance strategies in tax havens.

# #### 1.2.1 Create dictionaries with all fractions by which profits need to be multiplied to correct

# In[61]:


# Define correction values for each year in dictionaries

# Domestic corrections
correction_domestic = {
    2016: {"ARG": 0.35, "AUS": 0.35, "AUT": 0.35, "BEL": 0.5, "BMU": 0.5, "BRA": 0.35, "CAN": 0.35, "CHE": 0.35, "USA": 0.74, "ZAF": 0.35},
    2017: {"ARG": 0.35, "AUS": 0.35, "AUT": 0.35, "BEL": 0.5, "BMU": 0.5, "BRA": 0.35, "USA": 0.55, "ZAF": 0.35},
    2018: {"ARG": 0.35, "AUS": 0.35, "AUT": 0.35, "BEL": 0.5, "BMU": 0.5, "BRA": 0.35, "USA": 0.74, "ZAF": 0.35},
    2019: {"ARG": 0.35, "AUS": 0.35, "AUT": 0.35, "BEL": 0.5, "BMU": 0.5, "USA": 0.74, "ZAF": 0.35},
    2020: {},
    2021: {}
}

# Foreign corrections
correction_foreign = {
    2016: {"USA": 0.07},
    2017: {"USA": 0.07},
    2018: {"USA": 0.39},
    2019: {"USA": 0.39},
    2020: {},
    2021: {}
}

# Tax havens and country groups corrections (using comprehensions)
correction_taxhavens = {year: {key: 0.09 for key in tax_havens} for year in range(2016, 2019)}
correction_countrygroups = {year: {key: 0.045 for key in other_country_groups} for year in range(2016, 2019)}

# Correction dictionary to hold all values
corrections = {
    "domestic": {},
    "foreign": {},
    "taxhavens": {},
    "countrygroups": {}
}

# Populate corrections for all years dynamically
for year in range(first_year, first_year + n_years + 1):
    corrections["domestic"][year] = {key: 0 for key in parent_countries.tolist()}
    corrections["foreign"][year] = {key: 0 for key in parent_countries.tolist()}
    corrections["taxhavens"][year] = {key: 0 for key in partner_countries.tolist()}
    corrections["countrygroups"][year] = {key: 0 for key in partner_countries.tolist()}

    # Update corrections using the predefined data
    corrections["domestic"][year].update(correction_domestic.get(year, {}))
    corrections["foreign"][year].update(correction_foreign.get(year, {}))
    corrections["taxhavens"][year].update(correction_taxhavens.get(year, {}))
    corrections["countrygroups"][year].update(correction_countrygroups.get(year, {}))

        # Log the corrections being applied for tracking
    print(f"Applied corrections for year {year} (Domestic: {len(corrections['domestic'][year])} countries, "
          f"Foreign: {len(corrections['foreign'][year])}, Tax Havens: {len(corrections['taxhavens'][year])}, "
          f"Country Groups: {len(corrections['countrygroups'][year])})")

# I want to see a snapshot of what was done above
print(corrections)    


# #### 1.2.2 Apply correction to main dataset

# In[62]:


def correct_for_dividend_double_counting(row, year):
    """
    Corrects reported profits for dividend double counting in the CBCR dataset, 
    storing the corrected profits in the new column 'profit_loss_before_income_tax_corrected'.

    Correction details are defined in the corrections dictionary for domestic profits, 
    foreign profits, profits in tax havens, and profits in country groups.
    """

    # Ensure that profit values are not NaN
    profit = row.get("profit_loss_before_income_tax")
    if pd.isna(profit):
        return np.nan  # If profit is missing, return NaN

    # 1. Use adjusted values when available
    if pd.notna(row.get("adjusted_profit_loss_before_income_tax")):
        return row["adjusted_profit_loss_before_income_tax"]

    # 2. Only apply corrections if profit > 0
    if profit <= 0:
        return profit  # No correction for non-positive profits

    # 3. Ensure the row's year matches the current correction year
    if row["year"] != year:
        return profit  # Skip if the year does not match the correction year

    # 4. Correct domestic profits
    if row["iso_parent"] == row["iso_partner"]:
        domestic_correction = corrections["domestic"].get(year, {}).get(row["iso_parent"], 0)
        profit *= (1 - domestic_correction)

    # 5. Correct foreign profits if iso_parent != iso_partner
    else:
        # Correct for tax havens
        taxhaven_correction = corrections["taxhavens"].get(year, {}).get(row["iso_partner"], 0)
        profit *= (1 - taxhaven_correction)

        # Correct for country groups
        countrygroup_correction = corrections["countrygroups"].get(year, {}).get(row["iso_partner"], 0)
        profit *= (1 - countrygroup_correction)

        # Correct foreign profits based on home jurisdiction peculiarities
        foreign_correction = corrections["foreign"].get(year, {}).get(row["iso_parent"], 0)
        profit *= (1 - foreign_correction)

        # 6. Specific correction for US tax havens in 2018
        if row["iso_parent"] == "USA" and row["iso_partner"] in tax_havens and year == 2018:
            profit *= 0.61  # Apply the specific 0.39 correction for US in tax havens in 2018

    return profit

# Apply the correction for each year and store the corrected values in a new column
for year in range(first_year, first_year + n_years):
    mask = cbcr["year"] == year
    corrected_values = cbcr.loc[mask].apply(lambda row: correct_for_dividend_double_counting(row, year), axis=1)
    cbcr.loc[mask, "profit_loss_before_income_tax_corrected"] = corrected_values

    # Optional: Print the number of corrected entries for each year for tracking purposes
    print(f"Year {year}: Corrected {corrected_values.notna().sum()} profit entries.")


# Create logged variables

# In[63]:


# List of columns to transform
variables_to_log = ['profit_loss_before_income_tax_corrected','unrelated_party_revenues', 'n_employees',
                    'tangible_assets_except_cash', 'stated_capital', 'total_revenues', 'related_party_revenues', 
                    'holding_or_managing_ip']

# Generate log values where needed, handling missing and negative values
for col_name in variables_to_log:
    if col_name in cbcr.columns:
        # Create a new column for the log transformation
        new_col_name = f'ln_{col_name}'

        # Apply log transformation with a small constant to avoid log(0) issues
        cbcr[new_col_name] = np.log1p(cbcr[col_name].clip(lower=0))  # np.log1p is log(1 + x), handles 0 and small values

        # Optionally log how many values were transformed for each column
        num_transformed = cbcr[new_col_name].notna().sum()
        print(f"Transformed {num_transformed} values for column '{col_name}' into '{new_col_name}'")
    else:
        print(f"Column '{col_name}' not found in the DataFrame. Skipping transformation.")


# #### 1.3 Calculate ETRs 
# 
# **TO DO: Clarify with Alex whether to use "income_tax_paid_on_cash_basis" or "income_tax_accrued_current_year" for ETR calculation (Garcia Bernardo/Janský (2024) mainly use tax accrued, we used to use "income_tax_paid_on_cash_basis")**
# 
# - We calculate ETRs for two reasons: 
#     1. We use them to double check whether our profit correction makes sense (it does if corrected ETRs of foreign and domestic firms are closer to each other than before the correction, see Garcia Bernardo/Janský (2024).
#     2. In our profit shifting estimates, we only consider profit shifting to jurisdictions with an ETR of below 15%. We therefore need to know the ETR by jurisdiction.
#     
# - We calculate ETRs based on the reported profits and based on the profits that have been corrected in 1.2 over a five years rolling window (starting two years before the current year and ending 2 years after the current year)

# In[64]:


def calculate_etr(df):
    """Calculate ETRs from CbCR data using rolling window totals."""
    # Group by 'iso_partner' and sum values over the rolling window
    d = df.groupby("iso_partner").sum()

    # Calculate ETRs based on the summed values
    d["etr"] = d["income_tax_accrued_current_year"] / d["profit_loss_before_income_tax"]
    d["etr_corrected"] = d["income_tax_accrued_current_year"] / d["profit_loss_before_income_tax_corrected"]

    return d[["etr", "etr_corrected"]]

def main_etrs(file, g="Sub-groups with positive profits"):
    """Calculate ETRs from CbCR data for each year using a rolling window."""
    # Select relevant columns
    df = file[["iso_parent", "iso_partner", "year", "partner_jurisdiction", "grouping", 
               "income_tax_accrued_current_year", "profit_loss_before_income_tax", 
               "profit_loss_before_income_tax_corrected"]]

    # Filter the grouping (e.g., Sub-groups with positive profits)
    df = df.loc[df["grouping"] == g]

    results = pd.DataFrame()

    # Get unique years in the dataset
    unique_years = df["year"].unique()

    for year in unique_years:
        # Define the rolling window period (2 years before and 2 years after the current year)
        start_year = year - 2
        end_year = year + 2

        # Filter data for the rolling window period
        df_window = df[(df["year"] >= start_year) & (df["year"] <= end_year)]
        df_window = df_window.dropna(subset=["income_tax_accrued_current_year"])

        # Calculate ETRs for domestic, foreign, and overall (average) profits
        df_foreign = df_window[df_window["iso_parent"] != df_window["iso_partner"]]
        df_domestic = df_window[df_window["iso_parent"] == df_window["iso_partner"]]
        df_average = df_window

        # Calculate ETRs for domestic, foreign, and average over the rolling window
        df_etr_domestic = calculate_etr(df_domestic).reset_index()
        df_etr_foreign = calculate_etr(df_foreign).reset_index()
        df_etr_average = calculate_etr(df_average).reset_index()

        # Merge the ETR dataframes on the "iso_partner" column
        df_etr = df_etr_domestic.merge(df_etr_foreign, on="iso_partner", how="outer", suffixes=("_domestic", "_foreign"))
        df_etr = df_etr.merge(df_etr_average, on="iso_partner", how="outer", suffixes=("", "_average"))

        # Rename the columns for clarity
        df_etr.columns = ["iso_partner", "etr_domestic", "etr_domestic_corrected", "etr_foreign", 
                          "etr_foreign_corrected", "etr_average", "etr_average_corrected"]

        # Add a "year" column to indicate the rolling window center year
        df_etr["year"] = year

        # Append the ETRs for this year to the results DataFrame
        results = pd.concat([results, df_etr], axis=0)

    return results


# In[65]:


def main_etrs(file, g="Sub-groups with positive profits"):
    """Calculate ETRs from CbCR data for each year using a rolling window."""
    # Select relevant columns
    df = file[["iso_parent", "iso_partner", "year", "partner_jurisdiction", "grouping", 
               "income_tax_accrued_current_year", "profit_loss_before_income_tax", 
               "profit_loss_before_income_tax_corrected"]]

    # Filter the grouping (e.g., Sub-groups with positive profits)
    df = df.loc[df["grouping"] == g]

    results = pd.DataFrame()

    # Get unique years in the dataset
    unique_years = df["year"].unique()

    for year in unique_years:
        # Define the rolling window period (2 years before and 2 years after the current year)
        start_year = year - 2
        end_year = year + 2

        # Filter data for the rolling window period
        df_window = df[(df["year"] >= start_year) & (df["year"] <= end_year)]
        df_window = df_window.dropna(subset=["income_tax_accrued_current_year"])

        # Calculate ETRs for domestic, foreign, and overall (average) profits
        df_foreign = df_window[df_window["iso_parent"] != df_window["iso_partner"]]
        df_domestic = df_window[df_window["iso_parent"] == df_window["iso_partner"]]
        df_average = df_window

        # Calculate ETRs for domestic, foreign, and average over the rolling window
        df_etr_domestic = calculate_etr(df_domestic).reset_index()
        df_etr_foreign = calculate_etr(df_foreign).reset_index()
        df_etr_average = calculate_etr(df_average).reset_index()

        # Merge the ETR dataframes on the "iso_partner" column
        df_etr = df_etr_domestic.merge(df_etr_foreign, on="iso_partner", how="outer", suffixes=("_domestic", "_foreign"))
        df_etr = df_etr.merge(df_etr_average, on="iso_partner", how="outer", suffixes=("", "_average"))

        # Rename the columns for clarity
        df_etr.columns = ["iso_partner", "etr_domestic", "etr_domestic_corrected", "etr_foreign", 
                          "etr_foreign_corrected", "etr_average", "etr_average_corrected"]

        # Add a "year" column to indicate the rolling window center year
        df_etr["year"] = year

        # Append the ETRs for this year to the results DataFrame
        results = pd.concat([results, df_etr], axis=0)

    return results


# In[66]:


# Calculate all relevant ETRs (Sub-groups with positive profits)
etrs = main_etrs(cbcr)

# Winsorize ETRs (trimming 2.5% from both tails)
etr_columns = [
    "etr_domestic", "etr_domestic_corrected", 
    "etr_foreign", "etr_foreign_corrected", 
    "etr_average", "etr_average_corrected"
]

for col in etr_columns:
    etrs[col] = winsorize(etrs[col], limits=[0.025, 0.025])

# Log the ETR calculations for the main calculation only once per year
for year in etrs["year"].unique():
    num_partners = etrs[etrs["year"] == year].shape[0]
    print(f"Calculated ETRs for year {year} (Sub-groups with positive profits). Number of partners: {num_partners}")

# Adjust domestic ETRs of countries which do not report positive profits
# For those countries, we calculate ETRs based on all sub-groups, not only sub-groups with positive profits
reporting_countries_with_no_positive_profits = set(
    cbcr.loc[(cbcr["iso_parent"] == cbcr["iso_partner"]) & (cbcr["grouping"] == "Total (All sub-groups)"), "iso_parent"]
) - set(
    cbcr.loc[(cbcr["iso_parent"] == cbcr["iso_partner"]) & (cbcr["grouping"] == "Sub-groups with positive profits"), "iso_parent"]
)

cbcr_countries_no_positive_profits = cbcr[
    (cbcr["iso_parent"].isin(reporting_countries_with_no_positive_profits)) & 
    (cbcr["iso_parent"] == cbcr["iso_partner"])
]

# Calculate ETRs for countries without positive profits, based on all sub-groups
etrs_no_positive_profits = main_etrs(cbcr_countries_no_positive_profits, g="Total (All sub-groups)")

# Log for the countries with no positive profits only once per year
for year in etrs_no_positive_profits["year"].unique():
    num_partners = etrs_no_positive_profits[etrs_no_positive_profits["year"] == year].shape[0]
    print(f"Calculated ETRs for year {year} (Total - All sub-groups). Number of partners: {num_partners}")

# Merge the original ETR data with the newly calculated ETRs for countries with no positive profits
merged_df = etrs.merge(
    etrs_no_positive_profits[['iso_partner', 'year', 'etr_domestic', 'etr_domestic_corrected']],
    on=['iso_partner', 'year'], 
    how='left', 
    suffixes=('', '_update')
)

# Update the values in 'etr_domestic' and 'etr_domestic_corrected' if the update values are not NaN
merged_df['etr_domestic'] = merged_df['etr_domestic'].combine_first(merged_df['etr_domestic_update'])
merged_df['etr_domestic_corrected'] = merged_df['etr_domestic_corrected'].combine_first(merged_df['etr_domestic_corrected_update'])

# Drop the temporary update columns
etrs = merged_df.drop(columns=['etr_domestic_update', 'etr_domestic_corrected_update'])

# Log the number of updated entries for tracking
updated_entries = merged_df[['etr_domestic', 'etr_domestic_corrected']].notna().sum().sum()
print(f"Updated {updated_entries} entries for domestic ETRs based on 'Total (All sub-groups)' data.")


# In[67]:


# Check for duplicates in the ETRs dataframe before merging
check_duplicates(etrs, "ETRs")

# Check for missing values in key columns before merging
check_missing_values(etrs, ["iso_partner", "year", "etr_domestic", "etr_foreign", "etr_average"])

# Merge ETRs into the main cbcr dataset
cbcr_etrs = cbcr.merge(etrs, on=["iso_partner", "year"], how="left")

# Check for missing ETRs after merging in critical columns
check_missing_values(cbcr_etrs, ["etr_domestic", "etr_foreign", "etr_average"])

# Calculate the percentage of missing values for domestic, foreign, and average ETRs
num_missing_domestic = cbcr_etrs["etr_domestic"].isna().sum()
num_missing_foreign = cbcr_etrs["etr_foreign"].isna().sum()
num_missing_average = cbcr_etrs["etr_average"].isna().sum()
total_rows = cbcr_etrs.shape[0]

missing_percentage_domestic = (num_missing_domestic / total_rows) * 100
missing_percentage_foreign = (num_missing_foreign / total_rows) * 100
missing_percentage_average = (num_missing_average / total_rows) * 100

# Print the percentage of rows with missing ETRs for domestic, foreign, and average
print(f"Percentage of rows with missing domestic ETRs: {missing_percentage_domestic:.2f}%. There can be several missing values as we can only calculate domestic ETRs for reporting jurisdictions.")
print(f"Percentage of rows with missing foreign ETRs: {missing_percentage_foreign:.2f}%")
print(f"Percentage of rows with missing average ETRs: {missing_percentage_average:.2f}%")


# ### 2. Import other variables needed
# - 2.1 Import corporate income tax rates
# - 2.2 Import salary data
# - 2.3 Import GDP and population data to impute missing values on salaries
# - 2.4 Import health expenditure data for comparisons

# In[68]:


# Generate rows that should be present in the datasets (combining jurisdictions and years)
sample_jur_year = [(jur, year) for jur in partner_countries for year in range(first_year, first_year + n_years)]


# #### 2.1 Add corporate income tax rates

# In[69]:


# Start with OECD data
cits_oecd_raw = pd.read_csv(cit_data_oecd)
columns_cit_data = ['REF_AREA', 'Measure', 'Targeting', 'TIME_PERIOD', 'OBS_VALUE']
cits_oecd_raw = cits_oecd_raw[columns_cit_data]

# Filter and clean OECD CIT data
cits_oecd = cits_oecd_raw[
    (cits_oecd_raw['Measure'] == "Combined corporate income tax rate") & 
    (cits_oecd_raw['Targeting'] == "Statutory") & 
    (cits_oecd_raw['TIME_PERIOD'].between(first_year, first_year + n_years))
].rename(columns={
    'REF_AREA': 'iso_partner', 
    'TIME_PERIOD': 'year', 
    'OBS_VALUE': 'cit'
}).drop(columns=['Measure', 'Targeting'])

# Convert CIT rates from percentage to decimal
cits_oecd['cit'] = cits_oecd['cit'] / 100

# Add countries from Tax Foundation data that do not have OECD data
cits_wide_tf = pd.read_excel(cit_data_taxfoundation)
columns_cit_data_tf = ["iso_3"] + list(range(first_year, first_year + n_years))
cits_wide_tf = cits_wide_tf[columns_cit_data_tf]

# Transform Tax Foundation data from wide to long format
cits_tf = cits_wide_tf.melt(
    id_vars=['iso_3'], 
    value_vars=list(range(first_year, first_year + n_years)), 
    var_name='year', 
    value_name='cit'
)
cits_tf.rename(columns={"iso_3": "iso_partner"}, inplace=True)
cits_tf['cit'] = cits_tf['cit'] / 100

# Combine CIT data from both sources (OECD and Tax Foundation)
cits = pd.merge(cits_oecd, cits_tf, on=["iso_partner", "year"], how="outer", suffixes=('_cits', '_cits_tf'))
cits['cit'] = cits['cit_cits'].combine_first(cits['cit_cits_tf'])
cits = cits[['iso_partner', 'year', 'cit']].drop_duplicates().reset_index(drop=True)


# In[70]:


# Replace or add CIT rates for specific jurisdictions (Martinique, Bouvet Island)
for year in cits['year'].unique():
    # Replace or add CIT rate for Martinique (use France's CIT)
    fra_cit = cits.loc[(cits['iso_partner'] == 'FRA') & (cits['year'] == year), 'cit'].values[0]
    cits.loc[(cits['iso_partner'] == 'MTQ') & (cits['year'] == year), 'cit'] = fra_cit
    if not ((cits['iso_partner'] == 'MTQ') & (cits['year'] == year)).any():
        cits = pd.concat([cits, pd.DataFrame({'iso_partner': ['MTQ'], 'year': [year], 'cit': [fra_cit]})], ignore_index=True)

    # Replace or add CIT rate for Bouvet Island (use Norway's CIT)
    nor_cit = cits.loc[(cits['iso_partner'] == 'NOR') & (cits['year'] == year), 'cit'].values[0]
    cits.loc[(cits['iso_partner'] == 'BVT') & (cits['year'] == year), 'cit'] = nor_cit
    if not ((cits['iso_partner'] == 'BVT') & (cits['year'] == year)).any():
        cits = pd.concat([cits, pd.DataFrame({'iso_partner': ['BVT'], 'year': [year], 'cit': [nor_cit]})], ignore_index=True)

# Add further missing countries manually
missing_cits = [{'iso_partner': jur, 'year': year} for jur, year in sample_jur_year if not ((cits['iso_partner'] == jur) & (cits['year'] == year)).any()]
cits = pd.concat([cits, pd.DataFrame(missing_cits)], ignore_index=True)

# Replace missing CITs manually with reference URLs
cits.loc[cits['iso_partner'] == 'MLT', 'cit'] *= 1 / 7  # Adjust Malta's CIT by the 6/7th rule
cits.loc[cits['iso_partner'] == 'GIB', 'cit'] = 0  # Adjust Gibraltar's CIT as it only applies to resident income
cits.loc[cits['iso_partner'] == 'MCO', 'cit'] = 0  # Monaco adjustment
cits.loc[cits['iso_partner'] == 'AND', 'cit'] = 0  # Andorra adjustment
cits.loc[cits['iso_partner'] == 'CAF', 'cit'] = 0.3  # Central African Republic adjustment
cits.loc[cits['iso_partner'] == 'HTI', 'cit'] = 0.3  # Haiti adjustment
cits.loc[cits['iso_partner'] == 'YEM', 'cit'] = 0.2  # Yemen adjustment
cits.loc[cits['iso_partner'] == 'NCL', 'cit'] = 0  # Adjust to zero as only New Caledonian income is taxable
cits.loc[cits['iso_partner'] == 'PRK', 'cit'] = 0.325  # North Korea adjustment
cits.loc[cits['iso_partner'] == 'COD', 'cit'] = 0.28  # Congo (DRC) adjustment
cits.loc[cits['iso_partner'] == 'TLS', 'cit'] = 0.10  # Timor-Leste adjustment
cits.loc[cits['iso_partner'] == 'USA', 'cit'] = 0.27  # Include state-level taxes for the US
cits.loc[cits['iso_partner'] == 'MHL', 'cit'] = 0  # Marshall Islands adjustment: https://www.consilium.europa.eu/en/press/press-releases/2023/02/14/taxation-british-virgin-islands-costa-rica-marshall-islands-and-russia-added-to-eu-list-of-non-cooperative-jurisdictions-for-tax-purposes/
cits.loc[cits['iso_partner'] == 'GLP', 'cit'] = 0.15  # Guadeloupe adjustment: https://www.confiduss.com/en/jurisdictions/guadeloupe/economy/
cits.loc[cits['iso_partner'] == 'GUF', 'cit'] = 0.28  # French Guiana adjustment: https://thetradecouncil.com/2021/07/04/corporate-income-tax-in-french-guiana/
cits.loc[cits['iso_partner'] == 'IOT', 'cit'] = 0  # British Indian Ocean Territory adjustment
cits.loc[cits['iso_partner'] == 'PLW', 'cit'] = 0  # Palau adjustment: https://orbitax.com/taxhub/corporatetaxrates/PW/Palau
cits.loc[cits['iso_partner'] == 'PYF', 'cit'] = 0.27  # French Polynesia adjustment: https://orbitax.com/taxhub/countrychapters/PF/French-Polynesia/7890123caa2f4bbc950c93677678bece/Corporate-Income-Tax-588
cits.loc[cits['iso_partner'] == 'REU', 'cit'] = 0.15  # Réunion adjustment: https://www.confiduss.com/en/jurisdictions/reunion-island/
cits.loc[cits['iso_partner'] == 'SOM', 'cit'] = 0.3  # Somalia adjustment: https://sominvest.gov.so/procedures/tax-regime/
cits.loc[cits['iso_partner'] == 'XKV', 'cit'] = 0.1  # Kosovo adjustment: https://taxsummaries.pwc.com/kosovo/corporate/taxes-on-corporate-income
cits.loc[cits['iso_partner'] == 'SMR', 'cit'] = 0.17  # San Marino adjustment: https://www.orbitax.com/taxhub/countrychapters/SM/San%20Marino/f422ca9b24bb422f820ed2741b8b2b00/CorporateProfit-Taxes-591


# In[71]:


# Merge CITs into the main dataset
cbcr_etrs_cits = cbcr_etrs.merge(cits, on=["iso_partner", "year"], how="left")

# Check for any missing CIT values after the merge, but only for iso_partners not in non_countries
missing_cit_rows = cbcr_etrs_cits[
    (cbcr_etrs_cits['cit'].isnull()) & 
    (~cbcr_etrs_cits['iso_partner'].isin(non_countries))
]

# If there are missing CIT values, print the iso_partner countries and years with missing CIT
if not missing_cit_rows.empty:
    missing_iso_partners_cit = missing_cit_rows[['iso_partner', 'year']].drop_duplicates()
    print("Warning: CIT values are missing for the following iso_partner countries and years (excluding specified groups):")
    for _, row in missing_iso_partners_cit.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing CIT values found.")


# Some of the countries do not have ETRs, but CITs. We set the ETR to the CIT for these cases (and the reverse, but all countries have a CIT)
# 

# In[72]:


# Get iso_partner(s) with missing ETRs before filling
etr_missing_before = cbcr_etrs_cits[cbcr_etrs_cits['etr_average_corrected'].isna()]['iso_partner'].unique()

# Compute mean ETR per iso_partner, excluding NaN values
mean_etr_by_country = cbcr_etrs_cits.groupby('iso_partner')['etr_average_corrected'].transform('mean')

# Fill missing ETRs with mean ETR per iso_partner
cbcr_etrs_cits['etr_average_corrected'] = cbcr_etrs_cits['etr_average_corrected'].fillna(mean_etr_by_country)

# Get iso_partner(s) still missing ETRs after filling with mean ETR
etr_still_missing = cbcr_etrs_cits[cbcr_etrs_cits['etr_average_corrected'].isna()]['iso_partner'].unique()

# Fill remaining missing ETRs with CIT
cbcr_etrs_cits['etr_average_corrected'] = cbcr_etrs_cits['etr_average_corrected'].fillna(cbcr_etrs_cits['cit'])

# Get iso_partner(s) now missing ETRs (should be none, unless 'cit' is also missing)
etr_missing_after = cbcr_etrs_cits[cbcr_etrs_cits['etr_average_corrected'].isna()]['iso_partner'].unique()

# iso_partner(s) for which ETR was filled with CIT
etr_filled_with_cit = set(etr_still_missing) - set(etr_missing_after)

# iso_partner(s) for which ETR was filled with mean ETR from other years
etr_filled_with_mean = set(etr_missing_before) - set(etr_still_missing) - etr_filled_with_cit

# Output the partners that had ETRs filled
if etr_filled_with_mean:
    print(f"ETR was filled using mean ETR from other years for iso_partner(s): {', '.join(sorted(etr_filled_with_mean))}")
else:
    print("No missing ETRs were filled with mean ETR from other years.")

if etr_filled_with_cit:
    print(f"ETR was filled using CIT for iso_partner(s): {', '.join(sorted(etr_filled_with_cit))}")
else:
    print("No missing ETRs were filled with CIT.")

# Replace missing CIT rates with mean CIT per iso_partner, then with ETR if necessary

# Get iso_partner(s) with missing CIT before filling
cit_missing_before = cbcr_etrs_cits[cbcr_etrs_cits['cit'].isna()]['iso_partner'].unique()

# Compute mean CIT per iso_partner, excluding NaN values
mean_cit_by_country = cbcr_etrs_cits.groupby('iso_partner')['cit'].transform('mean')

# Fill missing CITs with mean CIT per iso_partner
cbcr_etrs_cits['cit'] = cbcr_etrs_cits['cit'].fillna(mean_cit_by_country)

# Get iso_partner(s) still missing CIT after filling with mean CIT
cit_still_missing = cbcr_etrs_cits[cbcr_etrs_cits['cit'].isna()]['iso_partner'].unique()

# Fill remaining missing CITs with ETR
cbcr_etrs_cits['cit'] = cbcr_etrs_cits['cit'].fillna(cbcr_etrs_cits['etr_average_corrected'])

# Get iso_partner(s) now missing CIT (should be none, unless 'etr_average_corrected' is also missing)
cit_missing_after = cbcr_etrs_cits[cbcr_etrs_cits['cit'].isna()]['iso_partner'].unique()

# iso_partner(s) for which CIT was filled with ETR
cit_filled_with_etr = set(cit_still_missing) - set(cit_missing_after)

# iso_partner(s) for which CIT was filled with mean CIT from other years
cit_filled_with_mean = set(cit_missing_before) - set(cit_still_missing) - cit_filled_with_etr

# Output the partners that had CITs filled
if cit_filled_with_mean:
    print(f"CIT was filled using mean CIT from other years for iso_partner(s): {', '.join(sorted(cit_filled_with_mean))}")
else:
    print("No missing CITs were filled with mean CIT from other years.")

if cit_filled_with_etr:
    print(f"CIT was filled using ETR for iso_partner(s): {', '.join(sorted(cit_filled_with_etr))}")
else:
    print("No missing CITs were filled with ETR.")


# #### 2.2 Add GDP and population

# In[73]:


# Read the GDP and population data
gdp_population_long = pd.read_csv(gdp_population_data)
years = list(range(first_year, first_year + n_years))
formatted_years = [f"{year} [YR{year}]" for year in years]
columns_gdp_population_data = ["Series Name", "Country Code"] + formatted_years
gdp_population_long = gdp_population_long[columns_gdp_population_data]

# Melt the long-format dataset
gdp_population_long = gdp_population_long.melt(
    id_vars=["Country Code", "Series Name"], 
    value_vars=formatted_years,
    var_name="Year",
    value_name="Value"
)

# Pivot the data to wide format
gdp_population = gdp_population_long.pivot_table(
    index=["Country Code", "Year"], 
    columns="Series Name", 
    values="Value", 
    aggfunc='first'
).reset_index()

# Rename columns for consistency
gdp_population = gdp_population.rename(columns={
    "Country Code": "iso_partner",
    "Year": "year",
    "GDP (current US$)": "gdp_current_usd",
})
# Handle both old ("Population, total") and new ("Population total") World Bank column names
pop_col = "Population, total" if "Population, total" in gdp_population.columns else "Population total"
gdp_population = gdp_population.rename(columns={
    pop_col: "population"
})

# Extract the year from the "Year" column and convert to integer
gdp_population['year'] = gdp_population['year'].str.extract(r'(\d{4})').astype(int)

# Handle missing or non-numeric values for GDP and Population
gdp_population['gdp_current_usd'].replace(['..', '...', '......', '—'], np.nan, inplace=True)
gdp_population['gdp_current_usd'] = pd.to_numeric(gdp_population['gdp_current_usd'], errors='coerce')

gdp_population['population'].replace(['..', '...', '......', '—'], np.nan, inplace=True)
gdp_population['population'] = pd.to_numeric(gdp_population['population'], errors='coerce')

# Log any remaining missing values in critical columns
missing_gdp = gdp_population['gdp_current_usd'].isna().sum()
missing_population = gdp_population['population'].isna().sum()

# Print iso_partner with missing GDP or Population values
missing_gdp_iso_partner = gdp_population[gdp_population['gdp_current_usd'].isna()]['iso_partner'].unique()
missing_population_iso_partner = gdp_population[gdp_population['population'].isna()]['iso_partner'].unique()


# In[ ]:


# Add missing countries
missing_gdp_population = []
for jur_year in sample_jur_year:
    if not ((gdp_population['iso_partner'] == jur_year[0]) & (gdp_population['year'] == jur_year[1])).any():
        missing_gdp_population.append({'iso_partner': jur_year[0], 'year': jur_year[1]})
gdp_population = pd.concat([gdp_population, pd.DataFrame(missing_gdp_population)], ignore_index=True)

# Impute missing data from other sources, in particular GDP and population as this will be used to impute other values

# Anguilla
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 331 * 1e6    # 2015 value (as 2016 is not available): http://data.un.org/en/iso/ai.html
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & ((gdp_population['year'] == 2017) | (gdp_population['year'] == 2018)), 'gdp_current_usd'] = 322 * 1e6 # same for 2017 and 2018, as there is no 2017 and 2016 data: http://data.un.org/en/iso/ai.html
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 380 * 1e6 # 2021 data
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 380 * 1e6 # 2021 data
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 380 * 1e6 # 2021 data

gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2016), 'population'] = 14.3 * 1e3 # https://worldpopulationreview.com/countries/anguilla-population
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2017), 'population'] = 14.4 * 1e3  # https://worldpopulationreview.com/countries/anguilla-population
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2018), 'population'] = 14.7 * 1e3  # https://worldpopulationreview.com/countries/anguilla-population
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2019), 'population'] = 14.8 * 1e3 
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2020), 'population'] = 14.8 * 1e3 
gdp_population.loc[(gdp_population['iso_partner'] == 'AIA') & (gdp_population['year'] == 2021), 'population'] = 14.5 * 1e3 

# British Indian Ocean Territory
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 1e6   
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 1e6

gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2016), 'population'] = 3000 # https://en.wikipedia.org/wiki/British_Indian_Ocean_Territory#Economy
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2017), 'population'] = 3000 # https://en.wikipedia.org/wiki/British_Indian_Ocean_Territory#Economy
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2018), 'population'] = 3000 # https://en.wikipedia.org/wiki/British_Indian_Ocean_Territory#Economy
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2019), 'population'] = 3000
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2020), 'population'] = 3000
gdp_population.loc[(gdp_population['iso_partner'] == 'IOT') & (gdp_population['year'] == 2021), 'population'] = 3000

# British Virgin Islands
gdp_population.loc[(gdp_population['iso_partner'] == 'VGB') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 1279 * 1e6 # 2015 values as no 2016 values available, https://unctadstat.unctad.org/countryprofile/generalprofile/en-gb/092/index.html
gdp_population.loc[(gdp_population['iso_partner'] == 'VGB') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 1279 * 1e6 # 2015 values as no 2016 values available, https://unctadstat.unctad.org/countryprofile/generalprofile/en-gb/092/index.html
gdp_population.loc[(gdp_population['iso_partner'] == 'VGB') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 1653 * 1e6 # 2021 values as no 2018 values available, https://unctadstat.unctad.org/countryprofile/generalprofile/en-gb/092/index.html
gdp_population.loc[(gdp_population['iso_partner'] == 'VGB') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 1653 * 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'VGB') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 1653 * 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'VGB') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 1653 * 1e6

# Cook Islands
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 287988 * 1e3 * 0.69 # https://stats.pacificdata.org
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 345587 * 1e3 * 0.7 # https://stats.pacificdata.org
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 391959 * 1e3 * 0.67 # https://stats.pacificdata.org
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 593585 * 1e3 * 0.64 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=26&tm=gdp&df[ds]=ds%3ASPC2&df[id]=DF_NATIONAL_ACCOUNTS&df[ag]=SPC&df[vs]=1.0&pd=2012%2C&dq=A.DOM..GDPC&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 397791 * 1e3 * 0.7 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=26&tm=gdp&df[ds]=ds%3ASPC2&df[id]=DF_NATIONAL_ACCOUNTS&df[ag]=SPC&df[vs]=1.0&pd=2012%2C&dq=A.DOM..GDPC&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 349192 * 1e3 * 0.71 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=26&tm=gdp&df[ds]=ds%3ASPC2&df[id]=DF_NATIONAL_ACCOUNTS&df[ag]=SPC&df[vs]=1.0&pd=2012%2C&dq=A.DOM..GDPC&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false

gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2016), 'population'] = 15076 # 2017, https://stats.pacificdata.org/vis?pg=0&bp=true&snb=50&tm=population&df[ds]=ds%3ASPC2&df[id]=DF_POP_PROJ&df[ag]=SPC&df[vs]=3.0&pd=2017%2C2027&dq=A..MIDYEARPOPEST._T._T&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2017), 'population'] = 15076 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=50&tm=population&df[ds]=ds%3ASPC2&df[id]=DF_POP_PROJ&df[ag]=SPC&df[vs]=3.0&pd=2017%2C2027&dq=A..MIDYEARPOPEST._T._T&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2018), 'population'] = 15153 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=50&tm=population&df[ds]=ds%3ASPC2&df[id]=DF_POP_PROJ&df[ag]=SPC&df[vs]=3.0&pd=2017%2C2027&dq=A..MIDYEARPOPEST._T._T&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2019), 'population'] = 15216 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=50&tm=population&df[ds]=ds%3ASPC2&df[id]=DF_POP_PROJ&df[ag]=SPC&df[vs]=3.0&pd=2017%2C2027&dq=A..MIDYEARPOPEST._T._T&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2020), 'population'] = 15281 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=50&tm=population&df[ds]=ds%3ASPC2&df[id]=DF_POP_PROJ&df[ag]=SPC&df[vs]=3.0&pd=2017%2C2027&dq=A..MIDYEARPOPEST._T._T&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false
gdp_population.loc[(gdp_population['iso_partner'] == 'COK') & (gdp_population['year'] == 2021), 'population'] = 15342 # https://stats.pacificdata.org/vis?pg=0&bp=true&snb=50&tm=population&df[ds]=ds%3ASPC2&df[id]=DF_POP_PROJ&df[ag]=SPC&df[vs]=3.0&pd=2017%2C2027&dq=A..MIDYEARPOPEST._T._T&ly[rw]=GEO_PICT&ly[cl]=TIME_PERIOD&to[TIME_PERIOD]=false

# Eritrea
gdp_population.loc[(gdp_population['iso_partner'] == 'ERI') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 2.21 * 1e9  # https://www.statista.com/statistics/510484/gross-domestic-product-gdp-in-eritrea/
gdp_population.loc[(gdp_population['iso_partner'] == 'ERI') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 1.9 * 1e9  # https://www.statista.com/statistics/510484/gross-domestic-product-gdp-in-eritrea/
gdp_population.loc[(gdp_population['iso_partner'] == 'ERI') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 2.01 * 1e9  # https://www.statista.com/statistics/510484/gross-domestic-product-gdp-in-eritrea/
gdp_population.loc[(gdp_population['iso_partner'] == 'ERI') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 1.98 * 1e9  # https://www.statista.com/statistics/510484/gross-domestic-product-gdp-in-eritrea/
gdp_population.loc[(gdp_population['iso_partner'] == 'ERI') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 1.98 * 1e9  # 2019 value, https://www.statista.com/statistics/510484/gross-domestic-product-gdp-in-eritrea/
gdp_population.loc[(gdp_population['iso_partner'] == 'ERI') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 1.98 * 1e9  # 2019 value, https://www.statista.com/statistics/510484/gross-domestic-product-gdp-in-eritrea/

# French Guiana
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 4131/0.904 * 1e6    # https://www.insee.fr/en/statistiques/serie/010751772#Tableau
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 4127/0.8865 * 1e6   # https://www.insee.fr/en/statistiques/serie/010751772#Tableau
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 4353 * 1.1811 * 1e6 # https://www.insee.fr/en/statistiques/serie/010751772#Tableau
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 4431 * 1.11 * 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 4275 * 1.21 * 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 4450 * 1.13 * 1e6

gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2016), 'population'] = 267821 # https://statisticstimes.com/demographics/country/french-guiana-population.php
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2017), 'population'] = 275191 # https://statisticstimes.com/demographics/country/french-guiana-population.php
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2018), 'population'] = 282938 # https://statisticstimes.com/demographics/country/french-guiana-population.php
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2019), 'population'] = 281678 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2020), 'population'] = 285133 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls
gdp_population.loc[(gdp_population['iso_partner'] == 'GUF') & (gdp_population['year'] == 2021), 'population'] = 286618 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls

# Falkland Islands
gdp_population.loc[(gdp_population['iso_partner'] == 'FLK') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 206.4 * 1e6    # 2015 data, as no better data exists: https://en.wikipedia.org/wiki/Economy_of_the_Falkland_Islands

gdp_population.loc[(gdp_population['iso_partner'] == 'FLK') & (gdp_population['year'] == 2016), 'population'] = 3478 # https://www.worldometers.info/world-population/falkland-islands-malvinas-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'FLK') & (gdp_population['year'] == 2017), 'population'] = 3518
gdp_population.loc[(gdp_population['iso_partner'] == 'FLK') & (gdp_population['year'] == 2018), 'population'] = 3521
gdp_population.loc[(gdp_population['iso_partner'] == 'FLK') & (gdp_population['year'] == 2019), 'population'] = 3517
gdp_population.loc[(gdp_population['iso_partner'] == 'FLK') & (gdp_population['year'] == 2020), 'population'] = 3506
gdp_population.loc[(gdp_population['iso_partner'] == 'FLK') & (gdp_population['year'] == 2021), 'population'] = 3490

# Gibraltar
gdp_population.loc[(gdp_population['iso_partner'] == 'GIB') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 2.344 * 1.3349 * 1e9 # 2018 data, as no older data exists, https://en.wikipedia.org/wiki/Economy_of_Gibraltar
gdp_population.loc[(gdp_population['iso_partner'] == 'GIB') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 2.344 * 1.3349 * 1e9 # 2018 data, as no older data exists, https://en.wikipedia.org/wiki/Economy_of_Gibraltar
gdp_population.loc[(gdp_population['iso_partner'] == 'GIB') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 2.344 * 1.3349 * 1e9 # https://en.wikipedia.org/wiki/Economy_of_Gibraltar
gdp_population.loc[(gdp_population['iso_partner'] == 'GIB') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 2.344 * 1.3349 * 1e9
gdp_population.loc[(gdp_population['iso_partner'] == 'GIB') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 2.344 * 1.3349 * 1e9
gdp_population.loc[(gdp_population['iso_partner'] == 'GIB') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 2.344 * 1.3349 * 1e9

# Guadeloupe
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 8712.316/0.904 * 1e6    # https://www.ceicdata.com/en/france/esa-2010-gdp-by-region-current-prices-base-2014/gdp-guadeloupe
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 8803.461/0.8865 * 1e6 # https://www.ceicdata.com/en/france/esa-2010-gdp-by-region-current-prices-base-2014/gdp-guadeloupe
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 9025.467*1.1811 * 1e6 # https://www.ceicdata.com/en/france/esa-2010-gdp-by-region-current-prices-base-2014/gdp-guadeloupe
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 9268.066 * 1.11 * 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 8857.257 * 1.21 * 1e6
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 9169.070 * 1.13 * 1e6

gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2016), 'population'] = 395700 # Google
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2017), 'population'] = 402119 # https://en.wikipedia.org/wiki/Guadeloupe
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2018), 'population'] = 402119 # 2017 data as no 2018 data available: https://en.wikipedia.org/wiki/Guadeloupe
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2019), 'population'] = 384239 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2020), 'population'] = 383559 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls
gdp_population.loc[(gdp_population['iso_partner'] == 'GLP') & (gdp_population['year'] == 2021), 'population'] = 384315 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls

# Guernsey
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 2934 * 1.3552 * 1e6 # https://gov.gg/CHttpHandler.ashx?id=160890&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 3101 * 1.289 * 1e6  # https://gov.gg/CHttpHandler.ashx?id=160890&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 3170 * 1.3349 * 1e6 # https://gov.gg/CHttpHandler.ashx?id=160890&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 3248 * 1e6 * 1.31 # https://gov.gg/CHttpHandler.ashx?id=160890&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 3125 * 1e6 * 1.32 # https://gov.gg/CHttpHandler.ashx?id=160890&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 3446 * 1e6 * 1.34 # https://gov.gg/CHttpHandler.ashx?id=160890&p=0

gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2016), 'population'] = 61908 # https://gov.gg/CHttpHandler.ashx?id=121746&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2017), 'population'] = 62046 # https://gov.gg/CHttpHandler.ashx?id=121746&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2018), 'population'] = 62506 # https://gov.gg/CHttpHandler.ashx?id=121746&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2019), 'population'] = 62885 # https://www.gov.gg/CHttpHandler.ashx?id=169995&p=0
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2020), 'population'] = 63156
gdp_population.loc[(gdp_population['iso_partner'] == 'GGY') & (gdp_population['year'] == 2021), 'population'] = 63664

# Jersey
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2016), 'gdp_current_usd'] =  4.11 * 1.3552 * 1e9  # https://www.gov.je/news/2017/pages/gvaandgdp2016.aspx
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2017), 'gdp_current_usd'] =  4.304 * 1.289 * 1e9 # https://www.gov.je/news/2018/pages/measuringjerseyseconomy2017.aspx
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2018), 'gdp_current_usd'] =  4.642 * 1.3349 * 1e9 # https://www.gov.je/news/2019/pages/measuringjerseyseconomy2018.aspx
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 4.885 * 1.31 * 1e9  # https://www.gov.je/news/2020/pages/measuringjerseyseconomy2019.aspx
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 4.528 * 1.32 * 1e9  # https://www.gov.je/SiteCollectionDocuments/Government%20and%20administration/R%20GVA%20and%20GDP%202020%2020211001%20SJ.pdf
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 5.087 * 1.34 * 1e9  # https://www.gov.je/SiteCollectionDocuments/Government%20and%20administration/R%20GVA%20and%20GDP%202021%2020221005%20SJ.pdf

gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2016), 'population'] = 102200
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2017), 'population'] = 102700
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2018), 'population'] = 103300
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2019), 'population'] = 103200 
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2020), 'population'] = 103300 
gdp_population.loc[(gdp_population['iso_partner'] == 'JEY') & (gdp_population['year'] == 2021), 'population'] = 103100

# Kosovo
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 6.68 * 1e9 # https://de.statista.com/statistik/daten/studie/415738/umfrage/bruttoinlandsprodukt-bip-des-kosovo/
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 7.18 * 1e9 # https://de.statista.com/statistik/daten/studie/415738/umfrage/bruttoinlandsprodukt-bip-des-kosovo/
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 7.88 * 1e9 # https://de.statista.com/statistik/daten/studie/415738/umfrage/bruttoinlandsprodukt-bip-des-kosovo/
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 7.9 * 1e9
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 7.73 * 1e9
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 9.42 * 1e9

gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2016), 'population'] = 1777557 # https://data.worldbank.org/indicator/SP.POP.TOTL?locations=XK
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2017), 'population'] = 1791003 # https://data.worldbank.org/indicator/SP.POP.TOTL?locations=XK
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2018), 'population'] = 1797085 # https://data.worldbank.org/indicator/SP.POP.TOTL?locations=XK
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2019), 'population'] = 1788878
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2020), 'population'] = 1790133
gdp_population.loc[(gdp_population['iso_partner'] == 'XKV') & (gdp_population['year'] == 2021), 'population'] = 1786038

# Mariana Islands
gdp_population.loc[(gdp_population['iso_partner'] == 'MNP') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 1230 * 1e6 # https://www.bea.gov/sites/default/files/2023-01/cngdp0123.pdf
gdp_population.loc[(gdp_population['iso_partner'] == 'MNP') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 1560 * 1e6 # https://www.bea.gov/sites/default/files/2023-01/cngdp0123.pdf
gdp_population.loc[(gdp_population['iso_partner'] == 'MNP') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 1301 * 1e6 # https://www.bea.gov/sites/default/files/2023-01/cngdp0123.pdf
gdp_population.loc[(gdp_population['iso_partner'] == 'MNP') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 1181 * 1e6 # https://www.bea.gov/sites/default/files/2023-01/cngdp0123.pdf
gdp_population.loc[(gdp_population['iso_partner'] == 'MNP') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 858 * 1e6 # https://www.bea.gov/sites/default/files/2023-01/cngdp0123.pdf
gdp_population.loc[(gdp_population['iso_partner'] == 'MNP') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 1181 * 1e6 # 2019 value, https://www.bea.gov/sites/default/files/2023-01/cngdp0123.pdf

# Martinique
gdp_population.loc[(gdp_population['iso_partner'] == 'MTQ') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 9459 * 1e6 * 1.12 # 2022 values, https://www.insee.fr/fr/statistiques/7677143

gdp_population.loc[(gdp_population['iso_partner'] == 'MTQ') & (gdp_population['year'] == 2016), 'population'] = 378865 # https://www.worldometers.info/world-population/martinique-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'MTQ') & (gdp_population['year'] == 2017), 'population'] = 371502 # https://www.worldometers.info/world-population/martinique-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'MTQ') & (gdp_population['year'] == 2018), 'population'] = 364089 # https://www.worldometers.info/world-population/martinique-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'MTQ') & (gdp_population['year'] == 2019), 'population'] = 359611 # https://www.worldometers.info/world-population/martinique-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'MTQ') & (gdp_population['year'] == 2020), 'population'] = 356615 # https://www.worldometers.info/world-population/martinique-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'MTQ') & (gdp_population['year'] == 2021), 'population'] = 353278 # https://www.worldometers.info/world-population/martinique-population/

# North Korea
gdp_population.loc[(gdp_population['iso_partner'] == 'PRK') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 772921776 # 2015 data as no other years available, https://www.cia.gov/the-world-factbook/countries/korea-north/#economy

# Reunión
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 18065/0.904 * 1e6    # https://www.insee.fr/en/statistiques/serie/010751763
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 18555/0.8865 * 1e6   # https://www.insee.fr/en/statistiques/serie/010751763
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 18822 * 1.1811 * 1e6 # https://www.insee.fr/en/statistiques/serie/010751763
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 19367 * 1.11 * 1e6 # https://www.insee.fr/en/statistiques/serie/010751763
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 19032 * 1.21 * 1e6 # https://www.insee.fr/en/statistiques/serie/010751763
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 20412 * 1.13 * 1e6 # https://www.insee.fr/en/statistiques/serie/010751763

gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2016), 'population'] = 926628 # https://www.worldometers.info/world-population/reunion-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2017), 'population'] = 932739 # https://www.worldometers.info/world-population/reunion-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2018), 'population'] = 941187 # https://www.worldometers.info/world-population/reunion-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2019), 'population'] = 861210 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2020), 'population'] = 863083 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls
gdp_population.loc[(gdp_population['iso_partner'] == 'REU') & (gdp_population['year'] == 2021), 'population'] = 871157 # https://www.insee.fr/fr/statistiques/fichier/7752095/estim-pop-nreg-sexe-gca-1975-2024.xls

# San Marino
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 1.468 * 1e9 # Google figure linking to https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 1.529 * 1e9 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 1.655 * 1e9 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 1.616 * 1e9 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 1.541 * 1e9 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 1.855 * 1e9 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en

gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2016), 'population'] = 33834 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2017), 'population'] = 34056 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2018), 'population'] = 34156 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2019), 'population'] = 34178 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2020), 'population'] = 34007 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en
gdp_population.loc[(gdp_population['iso_partner'] == 'SMR') & (gdp_population['year'] == 2021), 'population'] = 33745 # https://datacommons.org/place/country/SMR?utm_medium=explore&mprop=count&popt=Person&hl=en


# Saint Martin
gdp_population.loc[gdp_population['iso_partner'] == 'MAF', 'gdp'] = 772921776 # 2014 data as other years are not available, https://data.worldbank.org/indicator/NY.GDP.MKTP.CD?locations=MF

# South Sudan
gdp_population.loc[(gdp_population['iso_partner'] == 'SSD') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 2.9 * 1e9  # Google
gdp_population.loc[(gdp_population['iso_partner'] == 'SSD') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 1.8 * 1e9  # Google
gdp_population.loc[(gdp_population['iso_partner'] == 'SSD') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 3.12 * 1e9 # https://www.statista.com/statistics/727342/gross-domestic-product-gdp-in-south-sudan/
gdp_population.loc[(gdp_population['iso_partner'] == 'SSD') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 4.04 * 1e9  
gdp_population.loc[(gdp_population['iso_partner'] == 'SSD') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 5.42 * 1e9 
gdp_population.loc[(gdp_population['iso_partner'] == 'SSD') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 5.94 * 1e9 

# Taiwan
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 543.08 * 1e9 # https://www.statista.com/statistics/727589/gross-domestic-product-gdp-in-taiwan/
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 590.73 * 1e9 # https://www.statista.com/statistics/727589/gross-domestic-product-gdp-in-taiwan/
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 609.2 * 1e9  # https://www.statista.com/statistics/727589/gross-domestic-product-gdp-in-taiwan/
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 611.4  * 1e9 # https://www.statista.com/statistics/727589/gross-domestic-product-gdp-in-taiwan/
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2020), 'gdp_current_usd'] =  673.18 * 1e9 # https://www.statista.com/statistics/727589/gross-domestic-product-gdp-in-taiwan/
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 773.04 * 1e9

gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2016), 'population'] = 23512136 # 2015 as no 2016 data, https://worldpopulationreview.com/countries/taiwan-population
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2017), 'population'] = 23665024 #https://worldpopulationreview.com/countries/taiwan-population
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2018), 'population'] = 23726185 #https://worldpopulationreview.com/countries/taiwan-population
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2019), 'population'] = 23674138
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2020), 'population'] = 23663459
gdp_population.loc[(gdp_population['iso_partner'] == 'TWN') & (gdp_population['year'] == 2021), 'population'] = 23663459 #2020 data

# Venezuela
gdp_population.loc[(gdp_population['iso_partner'] == 'VEN') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 112.92 * 1e9 # https://www.statista.com/statistics/370937/gross-domestic-product-gdp-in-venezuela/
gdp_population.loc[(gdp_population['iso_partner'] == 'VEN') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 115.88 * 1e9 # https://www.statista.com/statistics/370937/gross-domestic-product-gdp-in-venezuela/
gdp_population.loc[(gdp_population['iso_partner'] == 'VEN') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 102.02 * 1e9 # https://www.statista.com/statistics/370937/gross-domestic-product-gdp-in-venezuela/
gdp_population.loc[(gdp_population['iso_partner'] == 'VEN') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 73 * 1e9
gdp_population.loc[(gdp_population['iso_partner'] == 'VEN') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 43.79 * 1e9
gdp_population.loc[(gdp_population['iso_partner'] == 'VEN') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 57.67 * 1e9

# Wallis and Futuna
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2016), 'gdp_current_usd'] = 139500 * 1e3 # https://stats.pacificdata.org/
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2017), 'gdp_current_usd'] = 139500 * 1e3 # https://stats.pacificdata.org/
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2018), 'gdp_current_usd'] = 139500 * 1e3 # https://stats.pacificdata.org/
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2019), 'gdp_current_usd'] = 139500 * 1e3 
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2020), 'gdp_current_usd'] = 139500 * 1e3 
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2021), 'gdp_current_usd'] = 139500 * 1e3 

gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2016), 'population'] = 12060 # https://www.worldometers.info/world-population/wallis-and-futuna-islands-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2017), 'population'] = 11936 # https://www.worldometers.info/world-population/wallis-and-futuna-islands-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2018), 'population'] = 11816 # https://www.worldometers.info/world-population/wallis-and-futuna-islands-population/
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2019), 'population'] = 11502
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2020), 'population'] = 11441
gdp_population.loc[(gdp_population['iso_partner'] == 'WLF') & (gdp_population['year'] == 2021), 'population'] = 11369

# if there's information on some years: replace missing values with average value over years
avg_gdp = gdp_population.groupby('iso_partner')['gdp_current_usd'].transform('mean')
gdp_population['gdp_current_usd'].fillna(avg_gdp, inplace=True)
avg_pop = gdp_population.groupby('iso_partner')['population'].transform('mean')
gdp_population['population'].fillna(avg_pop, inplace=True)


# **Checking GDP and population for missings is very relevant, as the two variables will be used later to calculate missing salaries and salaries are part of most of the formulas to estimate misalignment.**

# In[ ]:


# Merge GDP and population to the main dataset
cbcr_etrs_cits_gdp = cbcr_etrs_cits.merge(gdp_population, on=["iso_partner", "year"], how="left")

# Check for missing GDP and population rows, but only for iso_partners not in the excluded groups
missing_gdp_rows = cbcr_etrs_cits_gdp[
    (cbcr_etrs_cits_gdp['gdp_current_usd'].isnull()) & 
    (~cbcr_etrs_cits_gdp['iso_partner'].isin(non_countries))
]
missing_population_rows = cbcr_etrs_cits_gdp[
    (cbcr_etrs_cits_gdp['population'].isnull()) & 
    (~cbcr_etrs_cits_gdp['iso_partner'].isin(non_countries))
]

# If there are missing GDP values, print the iso_partner countries and years with missing GDP
if not missing_gdp_rows.empty:
    missing_iso_partners_gdp = missing_gdp_rows[['iso_partner', 'year']].drop_duplicates()
    print("Warning: GDP is missing for the following iso_partner countries and years:")
    for _, row in missing_iso_partners_gdp.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing GDP values found.")

# If there are missing population values, print the iso_partner countries and years with missing population
if not missing_population_rows.empty:
    missing_iso_partners_population = missing_population_rows[['iso_partner', 'year']].drop_duplicates()
    print("Warning: Population is missing for the following iso_partner countries and years:")
    for _, row in missing_iso_partners_population.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing population values found.")


# #### 2.3 Add salary data

# In[ ]:


# Load the wage data and select relevant rows
wages_fulltable = pd.read_csv(wage_data)

# Detect file format: old ILO bulk format (codes) vs new label format
if 'sex' in wages_fulltable.columns:
    # Old format with code columns (sex, classif1, classif2, ref_area)
    both_sexes = wages_fulltable['sex'] == 'SEX_T'
    all_occupations = wages_fulltable['classif1'] == 'ECO_SECTOR_TOTAL'
    in_usd = wages_fulltable['classif2'] == 'CUR_TYPE_USD'
    relevant_years = (wages_fulltable['time'] >= first_year) & (wages_fulltable['time'] <= first_year + n_years)
    relevant_rows = both_sexes & all_occupations & in_usd & relevant_years
    wages = wages_fulltable.loc[relevant_rows, ['ref_area', 'time', 'obs_value']].reset_index(drop=True)
    wages.rename(columns={"ref_area": "iso_partner", "time": "year", "obs_value": "wage_monthly"}, inplace=True)
else:
    # New label format (sex.label, classif1.label, ref_area.label)
    import pycountry
    both_sexes = wages_fulltable['sex.label'] == 'Total'
    in_usd = wages_fulltable['classif1.label'] == 'Currency: U.S. dollars'
    relevant_years = (wages_fulltable['time'] >= first_year) & (wages_fulltable['time'] <= first_year + n_years)
    relevant_rows = both_sexes & in_usd & relevant_years
    wages = wages_fulltable.loc[relevant_rows, ['ref_area.label', 'time', 'obs_value']].reset_index(drop=True)
    wages.rename(columns={"ref_area.label": "country_name", "time": "year", "obs_value": "wage_monthly"}, inplace=True)

    # Map country names to ISO3 codes
    manual_map = {
        'Bolivia (Plurinational State of)': 'BOL',
        'Congo, Democratic Republic of the': 'COD',
        'Hong Kong, China': 'HKG',
        'Republic of Korea': 'KOR',
        'Kosovo': 'XKV',
        'Macao, China': 'MAC',
    }
    def name_to_iso3(name):
        if name in manual_map:
            return manual_map[name]
        try:
            return pycountry.countries.lookup(name).alpha_3
        except:
            return None
    wages['iso_partner'] = wages['country_name'].map(name_to_iso3)
    unmapped = wages[wages['iso_partner'].isna()]['country_name'].unique()
    if len(unmapped) > 0:
        print(f"Warning: Could not map {len(unmapped)} country names to ISO3: {unmapped}")
    wages = wages.dropna(subset=['iso_partner'])
    wages = wages[['iso_partner', 'year', 'wage_monthly']]

# Add missing countries for wages
missing_wages = []
for jur_year in sample_jur_year:
    if not ((wages['iso_partner'] == jur_year[0]) & (wages['year'] == jur_year[1])).any():
        missing_wages.append({'iso_partner': jur_year[0], 'year': jur_year[1]})
wages = pd.concat([wages, pd.DataFrame(missing_wages)], ignore_index=True)

# If some years have information, replace missing values with average value over years
avg_wage = wages.groupby('iso_partner')['wage_monthly'].transform('mean')
wages['wage_monthly'].fillna(avg_wage, inplace=True)

# Include missing wage data based on the SOTJ 2023, transformed to US dollars based on the applicable exchange rate in a given year
# Anguilla: Wage in USD - https://www.salaryexpert.com/salary/area/netherlands/the-valley--anguilla
wages.loc[wages['iso_partner'] == 'AIA', 'wage_monthly'] = 74620.18 / 12  

# Cook Islands: Average salary data in USD - https://worldsalaries.com/average-salary-in-cook-islands/
wages.loc[wages['iso_partner'] == 'COK', 'wage_monthly'] = 2913.46        

# Guernsey: Average salary data in USD - https://www.salaryexplorer.com/average-salary-wage-comparison-guernsey-c90
wages.loc[wages['iso_partner'] == 'GGY', 'wage_monthly'] = 9859.02        

# Gibraltar: Average salary data in USD - https://worldsalaries.com/average-salary-in-gibraltar/
wages.loc[wages['iso_partner'] == 'GIB', 'wage_monthly'] = 4462           

# Guadeloupe: Average salary data in USD - https://www.salaryexplorer.com/average-salary-wage-comparison-guadalupe-t1601
wages.loc[wages['iso_partner'] == 'GLP', 'wage_monthly'] = 2277.85        

# French Guiana: Average monthly wage in USD - https://www.insee.fr/en/statistiques/serie/001781953
wages.loc[wages['iso_partner'] == 'GUF', 'wage_monthly'] = 16983.03 / 12  

# Jersey: Average earnings (transformed to monthly) - https://www.gov.je/StatisticsPerformance/EmploymentEarnings/pages/earningsincomestatistics.aspx
wages.loc[wages['iso_partner'] == 'JEY', 'wage_monthly'] = 1098.36 * 4    

# Saint Martin: Average annual wage in USD - https://www.sint-maarten.net/population/life
wages.loc[wages['iso_partner'] == 'MAF', 'wage_monthly'] = 46000 / 12     

# Taiwan: Average monthly wage in USD - https://nhglobalpartners.com/countries/taiwan/hiring-employees/average-salary/
wages.loc[wages['iso_partner'] == 'TWN', 'wage_monthly'] = 21689 / 12     

# Wallis and Futuna: Average salary in USD - https://www.salaryexplorer.com/average-salary-wage-comparison-wallis-and-futuna-c239
wages.loc[wages['iso_partner'] == 'WLF', 'wage_monthly'] = 625.75         


# In[ ]:


# Merge wages into the main dataset (gdp_population)
cbcr_etrs_cits_gdp_wages = cbcr_etrs_cits_gdp.merge(wages, on=["iso_partner", "year"], how="left")

# Identify missing wages after the merge, but only for iso_partners not in non_countries
missing_wages_after_merge = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages['wage_monthly'].isna()) & 
    (~cbcr_etrs_cits_gdp_wages['iso_partner'].isin(non_countries))
]

# If there are missing wage values, print the iso_partner countries and years with missing wage data
if not missing_wages_after_merge.empty:
    missing_iso_partners_wages = missing_wages_after_merge[['iso_partner', 'year']].drop_duplicates()
    print("Warning: The following years and countries have to be imputed in the next step:")
    for _, row in missing_iso_partners_wages.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing wage data after the merge.")


# ##### 2.3.2 Impute wages with OLS estimate based on log(gdp) and log(population)

# In[ ]:


# List to store countries with implausible wage values
offsample = []  

# Iterate over countries, GDP per capita, and monthly wages to identify implausible values
for i, gdp_per_capita, wage in zip(
    cbcr_etrs_cits_gdp_wages["iso_partner"],
    cbcr_etrs_cits_gdp_wages["gdp_current_usd"] / cbcr_etrs_cits_gdp_wages["population"],
    cbcr_etrs_cits_gdp_wages["wage_monthly"],
):
    # Ensure the GDP per capita and wage are valid and non-zero before log calculation
    if gdp_per_capita > 0 and wage > 0:
        # Log ratio of wage to GDP per capita and apply rule of thumb to detect implausible values
        if (np.log(gdp_per_capita / 12 / wage) > np.log2(1.5)) or (np.log(gdp_per_capita / 12 / wage) < -2):
            offsample.append(i)  # Append country to offsample if wage is implausible

# Remove duplicates from offsample
offsample = list(dict.fromkeys(offsample))

# Remove implausible values from the regression dataset
ols_sample = cbcr_etrs_cits_gdp_wages[~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(offsample)]

# Run OLS regression to predict wages based on GDP and population
ols_regression = smf.ols(
    formula="np.log(wage_monthly) ~ np.log(gdp_current_usd) + np.log(population)", data=ols_sample
)
ols_fitted_values = ols_regression.fit()

# Add predicted wage values to the dataset
cbcr_etrs_cits_gdp_wages["pred_wage_monthly"] = np.exp(ols_fitted_values.predict(cbcr_etrs_cits_gdp_wages))

# Substitute missing wages with predicted wages if they are NaN
cbcr_etrs_cits_gdp_wages.loc[cbcr_etrs_cits_gdp_wages["wage_monthly"].isna(), "wage_monthly"] = cbcr_etrs_cits_gdp_wages.loc[
    cbcr_etrs_cits_gdp_wages["wage_monthly"].isna(), "pred_wage_monthly"
]

# Remove the column with predicted wages as it was only used for imputation
cbcr_etrs_cits_gdp_wages.drop(columns=["pred_wage_monthly"], inplace=True)


# In[ ]:


# Check missing wage values after imputation for actual countries only
missing_after_imputation = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages['wage_monthly'].isna()) & 
    (~cbcr_etrs_cits_gdp_wages['iso_partner'].isin(non_countries))
].shape[0]
print(f"Missing wages after imputation: {missing_after_imputation}")

# Identify countries and years where wages are still missing after imputation
missing_wages_countries_years = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages['wage_monthly'].isna()) & 
    (~cbcr_etrs_cits_gdp_wages['iso_partner'].isin(non_countries))
][['iso_partner', 'year']].drop_duplicates()

# Explain why wages are still missing for each country and year
for _, row in missing_wages_countries_years.iterrows():
    country = row['iso_partner']
    year = row['year']
    reasons = []

    # Check if the country and year are in offsample (implausible wages)
    if (country, year) in offsample:
        reasons.append("wages flagged as implausible")

    # Check if GDP or population data is missing for this year
    if cbcr_etrs_cits_gdp_wages[
        (cbcr_etrs_cits_gdp_wages['iso_partner'] == country) & (cbcr_etrs_cits_gdp_wages['year'] == year)
    ]["gdp_current_usd"].isna().any():
        reasons.append("missing GDP data")
    if cbcr_etrs_cits_gdp_wages[
        (cbcr_etrs_cits_gdp_wages['iso_partner'] == country) & (cbcr_etrs_cits_gdp_wages['year'] == year)
    ]["population"].isna().any():
        reasons.append("missing population data")

    # Print out the reason for missing wages for the specific country and year
    reason_str = ", ".join(reasons) if reasons else "no wage data available even after prediction"
    print(f"Wages missing for {country} in year {year}: {reason_str}")


# Create payroll variable

# In[ ]:


cbcr_etrs_cits_gdp_wages['payroll'] = cbcr_etrs_cits_gdp_wages['n_employees'] * cbcr_etrs_cits_gdp_wages['wage_monthly'] * 12


# Log values

# In[ ]:


# List of columns to apply log transformation
variables_to_log = ['wage_monthly', 'gdp_current_usd', 'population']

# Generate log-transformed columns where needed
for col_name in variables_to_log:
    new_col_name = f'ln_{col_name}'
    # Apply log transformation with a small constant to avoid log(0)
    cbcr_etrs_cits_gdp_wages[new_col_name] = np.log1p(cbcr_etrs_cits_gdp_wages[col_name])  # log1p(x) is equivalent to log(1 + x)


# #### 2.4 Add Health data

# In[ ]:


health_expenditure_wide = pd.read_excel(health_expenditure_data)
health_expenditure_wide = health_expenditure_wide[health_expenditure_wide['Indicators'] == "Domestic General Government Health Expenditure (GGHE-D)"]
health_expenditure_wide = health_expenditure_wide.dropna(subset=['Countries'])
health_expenditure_wide["iso_partner"] = health_expenditure_wide["Countries"].map(data_processing.get_iso3)
health_expenditure_wide["iso_partner"].loc[health_expenditure_wide["Countries"] == "Netherlands (Kingdom of the)"] = "NLD"
print("Netherlands value corrected")
health_expenditure_wide["iso_partner"].loc[health_expenditure_wide["Countries"] == "Türkiye"] = "TUR"
print("Turkey value corrected")
columns_health_data = ["iso_partner"] + [str(year) for year in range(first_year, first_year + n_years)]
health_expenditure_wide = health_expenditure_wide[columns_health_data]
value_vars = [str(year) for year in range(first_year, first_year + n_years)]
health_expenditure = health_expenditure_wide.melt(id_vars=['iso_partner'], 
                  value_vars=value_vars, 
                  var_name='year', 
                  value_name='gvt_health_expenditure')
health_expenditure['gvt_health_expenditure'] = health_expenditure['gvt_health_expenditure'] * 1e6 #Transform million USD value into USD value


# Log values

# In[ ]:


health_expenditure['gvt_health_expenditure'] = pd.to_numeric(health_expenditure['gvt_health_expenditure'], errors='coerce')
health_expenditure['ln_gvt_health_expenditure'] = np.log(1 + health_expenditure['gvt_health_expenditure'])


# In[ ]:


# Merge health expenditure data to the main dataset
health_expenditure['year'] = health_expenditure['year'].astype(int)
cbcr_etrs_cits_gdp_wages_health = cbcr_etrs_cits_gdp_wages.merge(
    health_expenditure, on=["iso_partner", "year"], how="left"
)

# Check for missing health expenditure values after the merge for actual countries
missing_health_expenditure_rows = cbcr_etrs_cits_gdp_wages_health[
    (cbcr_etrs_cits_gdp_wages_health['gvt_health_expenditure'].isna()) & 
    (~cbcr_etrs_cits_gdp_wages_health['iso_partner'].isin(non_countries))
]

# Count the number of missing health expenditure entries
missing_health_expenditure_count = missing_health_expenditure_rows.shape[0]
print(f"Missing government health expenditure data after the merge: {missing_health_expenditure_count}")

# Identify countries and years where health expenditure is still missing after the merge
missing_health_expenditure_countries_years = missing_health_expenditure_rows[['iso_partner', 'year']].drop_duplicates()

# Print out the missing health expenditure data per country and year
for _, row in missing_health_expenditure_countries_years.iterrows():
    country = row['iso_partner']
    year = row['year']
    print(f"Health expenditure data missing for {country} in year {year}")


# #### 2.5 Add data on tax revenue

# In[ ]:


tax_revenue_wide = pd.read_csv(tax_revenue_data, skiprows=4)
value_vars = [str(year) for year in range(first_year, first_year + n_years)]
tax_revenue = tax_revenue_wide.melt(id_vars=['Country Code'], 
                  value_vars=value_vars, 
                  var_name='year', 
                  value_name='tax_revenue_pct_gdp')
tax_revenue.rename(columns={"Country Code": "iso_partner"}, inplace=True)


# In[ ]:


# Merge tax revenue data to the main dataset
tax_revenue['year'] = tax_revenue['year'].astype(int)
cbcr_etrs_cits_gdp_wages_health_taxes = cbcr_etrs_cits_gdp_wages_health.merge(
    tax_revenue, on=["iso_partner", "year"], how="left"
)

# Convert necessary columns to numeric, coercing errors
cbcr_etrs_cits_gdp_wages_health_taxes['tax_revenue_pct_gdp'] = pd.to_numeric(cbcr_etrs_cits_gdp_wages_health_taxes['tax_revenue_pct_gdp'], errors='coerce')
cbcr_etrs_cits_gdp_wages_health_taxes['gdp_current_usd'] = pd.to_numeric(cbcr_etrs_cits_gdp_wages_health_taxes['gdp_current_usd'], errors='coerce')

# Calculate tax revenue in USD
cbcr_etrs_cits_gdp_wages_health_taxes['tax_revenue_current_usd'] = (
    cbcr_etrs_cits_gdp_wages_health_taxes['tax_revenue_pct_gdp'] / 100 * cbcr_etrs_cits_gdp_wages_health_taxes['gdp_current_usd']
)

# Check for missing tax revenue values (tax_revenue_pct_gdp) after the merge for actual countries
missing_tax_revenue_rows = cbcr_etrs_cits_gdp_wages_health_taxes[
    (cbcr_etrs_cits_gdp_wages_health_taxes['tax_revenue_pct_gdp'].isna()) &
    (~cbcr_etrs_cits_gdp_wages_health_taxes['iso_partner'].isin(non_countries))
]

# Count the number of missing tax revenue entries
missing_tax_revenue_count = missing_tax_revenue_rows.shape[0]
print(f"Missing tax revenue percentage of GDP data after the merge: {missing_tax_revenue_count}")

# Identify countries and years where tax revenue percentage is still missing after the merge
missing_tax_revenue_countries_years = missing_tax_revenue_rows[['iso_partner', 'year']].drop_duplicates()

# Print out the missing tax revenue data per country and year
for _, row in missing_tax_revenue_countries_years.iterrows():
    country = row['iso_partner']
    year = row['year']
    print(f"Tax revenue data missing for {country} in year {year}")


# #### 2.6 Add regions and country groups

# In[ ]:


regions = pd.read_csv(unilateral_cross_data, usecols=['iso3', 'region_tjn','ukt','gbr_oct','oecd_oct','oecd','eu28','nld_oct','cthi_2021_share','cthi_2021_score']).dropna(subset=["iso3"])
regions.rename(columns={'iso3': 'iso_partner'}, inplace=True)


# In[ ]:


cbcr_main_no_imputation = cbcr_etrs_cits_gdp_wages_health_taxes.merge(regions, on=["iso_partner"], how="left")
# Create time-varying eu variable
cbcr_main_no_imputation['eu'] = cbcr_main_no_imputation['eu28']
cbcr_main_no_imputation.loc[(cbcr_main_no_imputation['iso_partner'] == 'GBR') & 
                            (cbcr_main_no_imputation['year'] >= 2020), 'eu'] = 0
cbcr_main_no_imputation.drop(columns=['eu28'], inplace=True)
# When the membership variables are missing, they are actually 0
variables_to_replace = ['ukt', 'gbr_oct', 'oecd_oct', 'oecd', 'eu', 'nld_oct']
cbcr_main_no_imputation[variables_to_replace] = cbcr_main_no_imputation[variables_to_replace].fillna(0)

cbcr_main_no_imputation_allsubgroupsonly = cbcr_main_no_imputation[cbcr_main_no_imputation["grouping"] == "Total (All sub-groups)"].copy()
cbcr_main_no_imputation_allsubgroupsonly.drop(columns=['grouping'], inplace=True)

# Save the resulting DataFrames to CSV files
cbcr_main_no_imputation.to_csv(f'{data_final}/cbcr_main_no_imputation.csv', index=False)
cbcr_main_no_imputation_allsubgroupsonly.to_csv(f'{data_final}/cbcr_main_no_imputation_allsubgroupsonly.csv', index=False)


# #### 2.7 Double check final "pure" dataset, i.e. the one without imputation

# Check for duplicates

# In[ ]:


# Check for duplicates
check_duplicates(cbcr_main_no_imputation_allsubgroupsonly, "final dataset (reporting sample only)")


# Check for infinite or negative infinite values

# In[ ]:


inf_check = cbcr_main_no_imputation.isin([np.inf, -np.inf]).any().any()
if inf_check:
    print("There were inf or -inf values in the DataFrame.")
else:
    print("No inf or -inf values found in the DataFrame.")

