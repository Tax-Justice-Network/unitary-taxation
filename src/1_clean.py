# %%
# ## The State of Tax Justice: Data cleaning
# TO DO: Get Orbis GUO information per year and adjust the code (of this notebook and the imputation notebook) accordingly.
#
# - Author: Alison Schultz, based on Javier Garcia-Bernado's work
# - Created: 4 August 2023
# - Last updated: 19 September 2024
#
# **Description**
# - This notebook is one out of three notebooks to estimate the tax losses caused by profit shifting by multinational enterprises (MNEs).
# - The analysis uses the misalignment method based on the country-by-country reports (CbCR) published by the OECD.
# - It produces:
#     - '{data_final}/cbcr_main_allsubgroupsonly.csv'
#     - '{data_final}/cbcr_main.csv'
#     - "{data_intermediate}/cbcr_imputation_sample.csv"
#
# **Outline**
# 1. Import and clean CbCR data
# 2. Import and clean other data needed for the analysis
# 3. Prepare final output datasets
#
# **To dos before running this notebook**
# 1. Adjust years for which the analysis should be run in 'config.py'.
# 2. Adjust all paths in 'config.py' for the current analysis.
# 3. Store the up-to-date versions of different datasets as specified in 'config.py' and update the dataset names where necessary.
# 4. Check the following resources regarding the CbCR data and adjust Section 1.2 of this notebook accordingly.
#     - Most recent version of OECD disclaimer: https://www.oecd.org/tax/tax-policy/anonymised-and-aggregated-cbcr-statistics-disclaimer.pdf
#     - Country notes (insert country of interest for COUNTRY): https://www.oecd.org/tax/tax-policy/COUNTRY-cbcr-country-specific-analysis.pdf
#     - Skim through raw data for potential misreporting
# 5. Load the environment "sotj_profit_shifting_estimates" (available via 'sotj_profit_shifting_estimates/environment.yml')

# %%
# 0. Setup

import pandas as pd
import numpy as np
import requests
import statsmodels.formula.api as smf

from config import *
from tjn_tools import data_processing


analysis_years = list(range(first_year, first_year + n_years))
last_year = analysis_years[-1]

CBCR_NUMERIC_VARS = [
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_entities",
]

RAW_WXD_FILL_COLS = [
    "unrelated_party_revenues",
    "profit_loss_before_income_tax",
    "adjusted_profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_cbcr",
    "n_cbcr_groups",
    "n_entities",
]


def check_missing_values(df, critical_columns):
    """
    Print the number and share of missing values in selected columns.
    Missing columns are reported explicitly.
    """
    total_observations = len(df)

    for column in critical_columns:
        if column not in df.columns:
            print(f"Column '{column}' is not present in the DataFrame.")
            continue

        count = df[column].isna().sum()
        if count > 0:
            percentage = (
                (count / total_observations) * 100 if total_observations > 0 else np.nan
            )
            print(
                f"{count} missing values found in column '{column}' "
                f"({percentage:.2f}% of total observations)."
            )
        else:
            print(f"No missing values found in column '{column}'.")


def check_duplicates(df, name, subset=None):
    """
    Print whether duplicates are present.
    """
    if df.duplicated(subset=subset).any():
        print(f"Warning: {name} contains duplicate rows.")
    else:
        print(f"No duplicates found in {name}.")


def fill_missing(df, iso, year, column, value):
    """
    Fill a single missing country-year-cell if it is currently missing.
    """
    mask = (df["iso_partner"] == iso) & (df["year"] == year) & (df[column].isna())
    df.loc[mask, column] = value


def add_or_fill_wxd_rows(cbcr):
    """
    Add or complete a raw WXD row for each parent-year-grouping block.

    WXD is always treated as the sum of all non-domestic entries except WXD itself.
    This is done on the raw variables before the dividend correction.
    """
    cbcr = cbcr.copy()
    group_cols = ["iso_parent", "year", "grouping"]
    new_rows = []

    wxd_fill_cols = [col for col in RAW_WXD_FILL_COLS if col in cbcr.columns]

    for (iso_parent, year, grouping), g in cbcr.groupby(group_cols, sort=False):
        wxd = g[g["iso_partner"] == "WXD"]
        base = g[(g["iso_partner"] != iso_parent) & (g["iso_partner"] != "WXD")].copy()

        if base.empty:
            continue

        replacement_values = {col: base[col].sum(min_count=1) for col in wxd_fill_cols}

        if not wxd.empty:
            wxd_idx = wxd.index[0]

            for col, val in replacement_values.items():
                if pd.isna(cbcr.at[wxd_idx, col]):
                    cbcr.at[wxd_idx, col] = val

            if "parent_jurisdiction" in cbcr.columns and pd.isna(
                cbcr.at[wxd_idx, "parent_jurisdiction"]
            ):
                parent_vals = g["parent_jurisdiction"].dropna()
                cbcr.at[wxd_idx, "parent_jurisdiction"] = (
                    parent_vals.iloc[0] if not parent_vals.empty else pd.NA
                )

            if "partner_jurisdiction" in cbcr.columns and pd.isna(
                cbcr.at[wxd_idx, "partner_jurisdiction"]
            ):
                cbcr.at[wxd_idx, "partner_jurisdiction"] = "World excluding domestic"

        else:
            new_row = {
                "iso_parent": iso_parent,
                "iso_partner": "WXD",
                "year": year,
                "grouping": grouping,
            }

            if "parent_jurisdiction" in cbcr.columns:
                parent_vals = g["parent_jurisdiction"].dropna()
                new_row["parent_jurisdiction"] = (
                    parent_vals.iloc[0] if not parent_vals.empty else pd.NA
                )

            if "partner_jurisdiction" in cbcr.columns:
                new_row["partner_jurisdiction"] = "World excluding domestic"

            for col, val in replacement_values.items():
                new_row[col] = val

            new_rows.append(new_row)

    if new_rows:
        cbcr = pd.concat([cbcr, pd.DataFrame(new_rows)], ignore_index=True)

    return cbcr


def correct_for_dividend_double_counting(row, year, corrections, tax_havens):
    """
    Correct reported profits for dividend double counting and store the corrected value
    in 'profit_loss_before_income_tax_corrected'.
    """
    profit = row.get("profit_loss_before_income_tax")

    if pd.isna(profit):
        return np.nan

    # Use adjusted profits if available
    if pd.notna(row.get("adjusted_profit_loss_before_income_tax")):
        return row["adjusted_profit_loss_before_income_tax"]

    # Do not correct non-positive profits
    if profit <= 0:
        return profit

    # Only apply the relevant year's rules
    if row["year"] != year:
        return profit

    # Domestic profits
    if row["iso_parent"] == row["iso_partner"]:
        domestic_correction = (
            corrections["domestic"].get(year, {}).get(row["iso_parent"], 0)
        )
        profit *= 1 - domestic_correction

    # Foreign profits
    else:
        taxhaven_correction = (
            corrections["taxhavens"].get(year, {}).get(row["iso_partner"], 0)
        )
        profit *= 1 - taxhaven_correction

        countrygroup_correction = (
            corrections["countrygroups"].get(year, {}).get(row["iso_partner"], 0)
        )
        profit *= 1 - countrygroup_correction

        foreign_correction = (
            corrections["foreign"].get(year, {}).get(row["iso_parent"], 0)
        )
        profit *= 1 - foreign_correction

        # Extra US tax haven correction in 2018
        if (
            row["iso_parent"] == "USA"
            and row["iso_partner"] in tax_havens
            and year == 2018
        ):
            profit *= 0.61

    return profit


def fix_corrected_wxd(cbcr, rtol=1e-6, atol=1e-3):
    """
    Rebuild corrected WXD profits after the row-wise dividend correction.

    This is done after corrected profits have been created.
    """
    cbcr = cbcr.copy()
    group_cols = ["iso_parent", "year", "grouping"]

    n_wxd_rows = 0
    n_domestic_wxd_only = 0
    n_exact_match = 0
    n_scaled = 0
    n_fallback = 0

    grouped_indices = cbcr.groupby(group_cols, sort=False).groups

    for _, idx in grouped_indices.items():
        idx = list(idx)
        block = cbcr.loc[idx].copy()

        iso_parent = block["iso_parent"].iloc[0]
        wxd_mask = block["iso_partner"] == "WXD"

        if not wxd_mask.any():
            continue

        wxd_idx = block.index[wxd_mask]
        n_wxd_rows += len(wxd_idx)

        reported_codes = set(block["iso_partner"].dropna())

        # If the block only has domestic and WXD, keep the raw WXD value
        if reported_codes == {iso_parent, "WXD"}:
            replacement_value = block.loc[
                wxd_mask, "profit_loss_before_income_tax"
            ].sum(min_count=1)
            cbcr.loc[wxd_idx, "profit_loss_before_income_tax_corrected"] = (
                replacement_value
            )
            n_domestic_wxd_only += len(wxd_idx)
            continue

        base_mask = (block["iso_partner"] != iso_parent) & (
            block["iso_partner"] != "WXD"
        )

        original_base_sum = block.loc[base_mask, "profit_loss_before_income_tax"].sum(
            min_count=1
        )
        corrected_base_sum = block.loc[
            base_mask, "profit_loss_before_income_tax_corrected"
        ].sum(min_count=1)
        original_wxd = block.loc[wxd_mask, "profit_loss_before_income_tax"].sum(
            min_count=1
        )

        if pd.isna(original_wxd) or pd.isna(corrected_base_sum):
            n_fallback += len(wxd_idx)
            continue

        if pd.notna(original_base_sum) and np.isclose(
            float(original_wxd),
            float(original_base_sum),
            rtol=rtol,
            atol=atol,
        ):
            replacement_value = corrected_base_sum
            n_exact_match += len(wxd_idx)

        elif pd.notna(original_base_sum) and float(original_base_sum) != 0:
            scale_factor = float(original_wxd) / float(original_base_sum)
            replacement_value = float(corrected_base_sum) * scale_factor
            n_scaled += len(wxd_idx)

        else:
            n_fallback += len(wxd_idx)
            continue

        cbcr.loc[wxd_idx, "profit_loss_before_income_tax_corrected"] = replacement_value

    print(f"WXD rows checked: {n_wxd_rows}")
    print(f"  domestic + WXD only: {n_domestic_wxd_only}")
    print(f"  exact-match replacements: {n_exact_match}")
    print(f"  scaled replacements: {n_scaled}")
    print(f"  fallback / unchanged: {n_fallback}")

    return cbcr


def calculate_etr(df):
    """
    Calculate ETRs from a country-level aggregation.
    """
    d = df.groupby("iso_partner", as_index=False)[
        [
            "income_tax_paid_on_cash_basis",
            "profit_loss_before_income_tax",
            "profit_loss_before_income_tax_corrected",
        ]
    ].sum()

    d["etr"] = d["income_tax_paid_on_cash_basis"] / d["profit_loss_before_income_tax"]
    d["etr_corrected"] = (
        d["income_tax_paid_on_cash_basis"]
        / d["profit_loss_before_income_tax_corrected"]
    )

    d[["etr", "etr_corrected"]] = (
        d[["etr", "etr_corrected"]]
        .replace([np.inf, -np.inf], np.nan)
        .clip(lower=0, upper=1)
    )

    return d[["iso_partner", "etr", "etr_corrected"]]


def main_etrs(file, grouping_name="Sub-groups with positive profits"):
    """
    Calculate rolling-window ETRs for each year.
    """
    df = file[
        [
            "iso_parent",
            "iso_partner",
            "year",
            "partner_jurisdiction",
            "grouping",
            "income_tax_paid_on_cash_basis",
            "profit_loss_before_income_tax",
            "profit_loss_before_income_tax_corrected",
        ]
    ].copy()

    df = df.loc[df["grouping"] == grouping_name].copy()

    results = []

    unique_years = sorted(df["year"].dropna().unique())

    for year in unique_years:
        start_year = year - 2
        end_year = year + 2

        df_window = df[(df["year"] >= start_year) & (df["year"] <= end_year)].copy()
        df_window = df_window.dropna(subset=["income_tax_paid_on_cash_basis"])

        df_foreign = df_window[df_window["iso_parent"] != df_window["iso_partner"]]
        df_domestic = df_window[df_window["iso_parent"] == df_window["iso_partner"]]
        df_average = df_window

        df_etr_domestic = calculate_etr(df_domestic).rename(
            columns={"etr": "etr_domestic", "etr_corrected": "etr_domestic_corrected"}
        )
        df_etr_foreign = calculate_etr(df_foreign).rename(
            columns={"etr": "etr_foreign", "etr_corrected": "etr_foreign_corrected"}
        )
        df_etr_average = calculate_etr(df_average).rename(
            columns={"etr": "etr_average", "etr_corrected": "etr_average_corrected"}
        )

        df_etr = df_etr_domestic.merge(df_etr_foreign, on="iso_partner", how="outer")
        df_etr = df_etr.merge(df_etr_average, on="iso_partner", how="outer")
        df_etr["year"] = year

        results.append(df_etr)

    return pd.concat(results, ignore_index=True)


# %%
# 1. Import and clean CbCR data
# 1.1 Import CbCR data

cbcr_variables = [
    "REF_AREA",
    "Reference area",
    "COUNTERPART_AREA",
    "Counterpart area",
    "Profit grouped by",
    "TIME_PERIOD",
    "Unrelated party revenues",
    "Profit (loss) before income tax",
    "Adjusted profit (loss) before income tax",
    "Income tax paid (on cash basis)",
    "Income tax accrued - current year",
    "Employees",
    "Tangible assets other than cash and cash equivalents",
    "Stated capital",
    "Total revenues",
    "Related party revenues",
    "Holding or managing intellectual property business activity",
    "Multinational enterprise groups",
    "Multinational enterprise sub-groups",
    "Entities",
]

cbcr_long = pd.read_csv(cbcr_data)

cbcr_wide = pd.pivot_table(
    cbcr_long,
    index=[
        "REF_AREA",
        "Reference area",
        "COUNTERPART_AREA",
        "Counterpart area",
        "Profit grouped by",
        "TIME_PERIOD",
    ],
    values="OBS_VALUE",
    columns="Measure",
).reset_index()

cbcr = cbcr_wide[cbcr_variables].copy()

# Remove non-existing jurisdictions, stateless entities, and empty world rows
cbcr = cbcr[
    (cbcr["COUNTERPART_AREA"] != "ANT_F")
    & (cbcr["COUNTERPART_AREA"] != "BVT")
    & (cbcr["COUNTERPART_AREA"] != "STLS")
    & (cbcr["COUNTERPART_AREA"] != "W")
].copy()

# Correct one empty line for Chile in 2016
cbcr = cbcr[
    ~(
        (cbcr["REF_AREA"] == "CHL")
        & (cbcr["TIME_PERIOD"] == 2016)
        & (cbcr["COUNTERPART_AREA"] == "F")
    )
].copy()

cbcr.rename(
    columns={
        "REF_AREA": "iso_parent",
        "Reference area": "parent_jurisdiction",
        "COUNTERPART_AREA": "iso_partner",
        "Counterpart area": "partner_jurisdiction",
        "Profit grouped by": "grouping",
        "TIME_PERIOD": "year",
        "Unrelated party revenues": "unrelated_party_revenues",
        "Profit (loss) before income tax": "profit_loss_before_income_tax",
        "Adjusted profit (loss) before income tax": "adjusted_profit_loss_before_income_tax",
        "Income tax paid (on cash basis)": "income_tax_paid_on_cash_basis",
        "Income tax accrued - current year": "income_tax_accrued_current_year",
        "Employees": "n_employees",
        "Tangible assets other than cash and cash equivalents": "tangible_assets_except_cash",
        "Stated capital": "stated_capital",
        "Total revenues": "total_revenues",
        "Related party revenues": "related_party_revenues",
        "Holding or managing intellectual property business activity": "holding_or_managing_ip",
        "Multinational enterprise groups": "n_cbcr",
        "Multinational enterprise sub-groups": "n_cbcr_groups",
        "Entities": "n_entities",
    },
    inplace=True,
)

check_duplicates(cbcr, "cbcr")

check_missing_values(
    cbcr,
    [
        "unrelated_party_revenues",
        "profit_loss_before_income_tax",
        "adjusted_profit_loss_before_income_tax",
        "income_tax_paid_on_cash_basis",
        "income_tax_accrued_current_year",
        "n_employees",
        "tangible_assets_except_cash",
        "stated_capital",
        "total_revenues",
        "related_party_revenues",
        "holding_or_managing_ip",
        "n_cbcr",
        "n_cbcr_groups",
        "n_entities",
    ],
)

# %%
# 1.1b Add raw WXD rows where needed

cbcr = add_or_fill_wxd_rows(cbcr)

parent_countries = cbcr["iso_parent"].drop_duplicates()
partner_countries = cbcr["iso_partner"].drop_duplicates()

print(f"Number of unique parent jurisdictions: {len(parent_countries)}")
print(
    f"Number of unique partner jurisdictions, including aggregated regions: {len(partner_countries)}"
)

partner_countries_filtered = partner_countries[~partner_countries.isin(non_countries)]
print(
    f"Number of unique partner jurisdictions, without aggregated regions: {len(partner_countries_filtered)}"
)

# %%
# 1.2 Adjust profits for dividend double counting

correction_domestic = {
    2016: {
        "ARG": 0.35,
        "AUS": 0.35,
        "AUT": 0.35,
        "BEL": 0.5,
        "BMU": 0.5,
        "BRA": 0.35,
        "CAN": 0.35,
        "CHE": 0.35,
        "USA": 0.74,
        "ZAF": 0.35,
    },
    2017: {
        "ARG": 0.35,
        "AUS": 0.35,
        "AUT": 0.35,
        "BEL": 0.5,
        "BMU": 0.5,
        "BRA": 0.35,
        "USA": 0.55,
        "ZAF": 0.35,
    },
    2018: {
        "ARG": 0.35,
        "AUS": 0.35,
        "AUT": 0.35,
        "BEL": 0.5,
        "BMU": 0.5,
        "BRA": 0.35,
        "USA": 0.74,
        "ZAF": 0.35,
    },
    2019: {
        "ARG": 0.35,
        "AUS": 0.35,
        "AUT": 0.35,
        "BEL": 0.5,
        "BMU": 0.5,
        "USA": 0.74,
        "ZAF": 0.35,
    },
    2020: {},
    2021: {},
    2022: {},
}

correction_foreign = {
    2016: {"USA": 0.07},
    2017: {"USA": 0.07},
    2018: {"USA": 0.39},
    2019: {"USA": 0.39},
    2020: {},
    2021: {},
    2022: {},
}

correction_taxhavens = {
    year: {key: 0.09 for key in tax_havens} for year in range(2016, 2020)
}
correction_countrygroups = {
    year: {key: 0.045 for key in other_country_groups} for year in range(2016, 2020)
}

corrections = {"domestic": {}, "foreign": {}, "taxhavens": {}, "countrygroups": {}}

for year in analysis_years:
    corrections["domestic"][year] = {key: 0 for key in parent_countries.tolist()}
    corrections["foreign"][year] = {key: 0 for key in parent_countries.tolist()}
    corrections["taxhavens"][year] = {key: 0 for key in partner_countries.tolist()}
    corrections["countrygroups"][year] = {key: 0 for key in partner_countries.tolist()}

    corrections["domestic"][year].update(correction_domestic.get(year, {}))
    corrections["foreign"][year].update(correction_foreign.get(year, {}))
    corrections["taxhavens"][year].update(correction_taxhavens.get(year, {}))
    corrections["countrygroups"][year].update(correction_countrygroups.get(year, {}))

    print(
        f"Applied corrections for year {year} (Domestic: {len(corrections['domestic'][year])} countries, "
        f"Foreign: {len(corrections['foreign'][year])}, Tax Havens: {len(corrections['taxhavens'][year])}, "
        f"Country Groups: {len(corrections['countrygroups'][year])})"
    )

print(corrections)

# %%
# 1.2b Apply profit correction row by row

for year in analysis_years:
    mask = cbcr["year"] == year
    original_values = cbcr.loc[mask, "profit_loss_before_income_tax"].copy()

    corrected_values = cbcr.loc[mask].apply(
        lambda row: correct_for_dividend_double_counting(
            row, year, corrections, tax_havens
        ),
        axis=1,
    )

    cbcr.loc[mask, "profit_loss_before_income_tax_corrected"] = corrected_values

    changed = (
        corrected_values.notna()
        & original_values.notna()
        & (corrected_values != original_values)
    ).sum()

    domestic_nonzero = {
        k: v for k, v in corrections["domestic"][year].items() if v != 0
    }
    foreign_nonzero = {k: v for k, v in corrections["foreign"][year].items() if v != 0}
    taxhavens_nonzero = {
        k: v for k, v in corrections["taxhavens"][year].items() if v != 0
    }
    countrygroups_nonzero = {
        k: v for k, v in corrections["countrygroups"][year].items() if v != 0
    }

    print(f"\nYear {year}")
    print(f"Processed rows: {mask.sum()}")
    print(f"Non-missing corrected entries: {corrected_values.notna().sum()}")
    print(f"Actually changed entries: {changed}")
    print(f"Domestic corrections: {domestic_nonzero}")
    print(f"Foreign corrections: {foreign_nonzero}")
    print(f"Tax haven corrections: {taxhavens_nonzero}")
    print(f"Country group corrections: {countrygroups_nonzero}")

# %%
# 1.2c Rebuild corrected WXD after corrected profits exist

cbcr = fix_corrected_wxd(cbcr)

# %%
# 1.2d Create log versions of selected variables

variables_to_log = [
    "profit_loss_before_income_tax_corrected",
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
]

for col_name in variables_to_log:
    if col_name in cbcr.columns:
        new_col_name = f"ln_{col_name}"
        cbcr[new_col_name] = np.log1p(cbcr[col_name].clip(lower=0))
        num_transformed = cbcr[new_col_name].notna().sum()
        print(
            f"Transformed {num_transformed} values for column '{col_name}' into '{new_col_name}'"
        )
    else:
        print(
            f"Column '{col_name}' not found in the DataFrame. Skipping transformation."
        )

# %%
# 1.3 Calculate ETRs

etrs = main_etrs(cbcr, grouping_name="Sub-groups with positive profits")

for year in etrs["year"].unique():
    num_partners = etrs[etrs["year"] == year].shape[0]
    print(
        f"Calculated ETRs for year {year} (Sub-groups with positive profits). Number of partners: {num_partners}"
    )

reporting_countries_with_no_positive_profits = set(
    cbcr.loc[
        (cbcr["iso_parent"] == cbcr["iso_partner"])
        & (cbcr["grouping"] == "Total (All sub-groups)"),
        "iso_parent",
    ]
) - set(
    cbcr.loc[
        (cbcr["iso_parent"] == cbcr["iso_partner"])
        & (cbcr["grouping"] == "Sub-groups with positive profits"),
        "iso_parent",
    ]
)

cbcr_countries_no_positive_profits = cbcr[
    (cbcr["iso_parent"].isin(reporting_countries_with_no_positive_profits))
    & (cbcr["iso_parent"] == cbcr["iso_partner"])
].copy()

etrs_no_positive_profits = main_etrs(
    cbcr_countries_no_positive_profits,
    grouping_name="Total (All sub-groups)",
)

for year in etrs_no_positive_profits["year"].unique():
    num_partners = etrs_no_positive_profits[
        etrs_no_positive_profits["year"] == year
    ].shape[0]
    print(
        f"Calculated ETRs for year {year} (Total - All sub-groups). Number of partners: {num_partners}"
    )

merged_df = etrs.merge(
    etrs_no_positive_profits[
        ["iso_partner", "year", "etr_domestic", "etr_domestic_corrected"]
    ],
    on=["iso_partner", "year"],
    how="left",
    suffixes=("", "_update"),
)

merged_df["etr_domestic"] = merged_df["etr_domestic"].combine_first(
    merged_df["etr_domestic_update"]
)
merged_df["etr_domestic_corrected"] = merged_df["etr_domestic_corrected"].combine_first(
    merged_df["etr_domestic_corrected_update"]
)

etrs = merged_df.drop(columns=["etr_domestic_update", "etr_domestic_corrected_update"])

updated_entries = (
    merged_df[["etr_domestic", "etr_domestic_corrected"]].notna().sum().sum()
)
print(
    f"Updated {updated_entries} entries for domestic ETRs based on 'Total (All sub-groups)' data."
)

check_duplicates(etrs, "ETRs", subset=["iso_partner", "year"])

check_missing_values(
    etrs,
    [
        "iso_partner",
        "year",
        "etr_domestic",
        "etr_foreign",
        "etr_average",
        "etr_average_corrected",
    ],
)

cbcr_etrs = cbcr.merge(etrs, on=["iso_partner", "year"], how="left")

check_missing_values(
    cbcr_etrs,
    ["etr_domestic", "etr_foreign", "etr_average", "etr_average_corrected"],
)

num_missing_domestic = cbcr_etrs["etr_domestic"].isna().sum()
num_missing_foreign = cbcr_etrs["etr_foreign"].isna().sum()
num_missing_average = cbcr_etrs["etr_average"].isna().sum()
num_missing_average_corrected = cbcr_etrs["etr_average_corrected"].isna().sum()
total_rows = cbcr_etrs.shape[0]

missing_percentage_domestic = (num_missing_domestic / total_rows) * 100
missing_percentage_foreign = (num_missing_foreign / total_rows) * 100
missing_percentage_average = (num_missing_average / total_rows) * 100
missing_percentage_average_corrected = (
    num_missing_average_corrected / total_rows
) * 100

print(
    f"Percentage of rows with missing domestic ETRs: {missing_percentage_domestic:.2f}%. "
    "There can be several missing values as we can only calculate domestic ETRs for reporting jurisdictions."
)
print(
    f"Percentage of rows with missing foreign ETRs: {missing_percentage_foreign:.2f}%"
)
print(
    f"Percentage of rows with missing average ETRs: {missing_percentage_average:.2f}%"
)
print(
    f"Percentage of rows with missing average corrected ETRs: {missing_percentage_average_corrected:.2f}%"
)

# %%
# 2. Import and clean other variables
# 2.1 Create the country-year sample used for merges

sample_jur_year = [(jur, year) for jur in partner_countries for year in analysis_years]

# %%
# 2.2 Import and clean corporate income tax rates

cits_oecd_raw = pd.read_csv(cit_data_oecd)
columns_cit_data = ["REF_AREA", "Measure", "Targeting", "TIME_PERIOD", "OBS_VALUE"]
cits_oecd_raw = cits_oecd_raw[columns_cit_data].copy()

cits_oecd = (
    cits_oecd_raw[
        (cits_oecd_raw["Measure"] == "Combined corporate income tax rate")
        & (cits_oecd_raw["Targeting"] == "Statutory")
        & (cits_oecd_raw["TIME_PERIOD"] >= first_year)
        & (cits_oecd_raw["TIME_PERIOD"] < first_year + n_years)
    ]
    .rename(
        columns={"REF_AREA": "iso_partner", "TIME_PERIOD": "year", "OBS_VALUE": "cit"}
    )
    .drop(columns=["Measure", "Targeting"])
    .copy()
)

cits_oecd["cit"] = cits_oecd["cit"] / 100

cits_wide_tf = pd.read_excel(cit_data_taxfoundation)
columns_cit_data_tf = ["iso_3"] + analysis_years
cits_wide_tf = cits_wide_tf[columns_cit_data_tf].copy()

cits_tf = cits_wide_tf.melt(
    id_vars=["iso_3"],
    value_vars=analysis_years,
    var_name="year",
    value_name="cit",
)
cits_tf.rename(columns={"iso_3": "iso_partner"}, inplace=True)
cits_tf["cit"] = cits_tf["cit"] / 100

cits = pd.merge(
    cits_oecd,
    cits_tf,
    on=["iso_partner", "year"],
    how="outer",
    suffixes=("_cits", "_cits_tf"),
)
cits["cit"] = cits["cit_cits"].combine_first(cits["cit_cits_tf"])
cits = cits[["iso_partner", "year", "cit"]].drop_duplicates().reset_index(drop=True)

for year in cits["year"].unique():
    fra_cit = cits.loc[
        (cits["iso_partner"] == "FRA") & (cits["year"] == year), "cit"
    ].values[0]
    cits.loc[(cits["iso_partner"] == "MTQ") & (cits["year"] == year), "cit"] = fra_cit
    if not ((cits["iso_partner"] == "MTQ") & (cits["year"] == year)).any():
        cits = pd.concat(
            [
                cits,
                pd.DataFrame(
                    {"iso_partner": ["MTQ"], "year": [year], "cit": [fra_cit]}
                ),
            ],
            ignore_index=True,
        )

    nor_cit = cits.loc[
        (cits["iso_partner"] == "NOR") & (cits["year"] == year), "cit"
    ].values[0]
    cits.loc[(cits["iso_partner"] == "BVT") & (cits["year"] == year), "cit"] = nor_cit
    if not ((cits["iso_partner"] == "BVT") & (cits["year"] == year)).any():
        cits = pd.concat(
            [
                cits,
                pd.DataFrame(
                    {"iso_partner": ["BVT"], "year": [year], "cit": [nor_cit]}
                ),
            ],
            ignore_index=True,
        )

missing_cits = [
    {"iso_partner": jur, "year": year}
    for jur, year in sample_jur_year
    if not ((cits["iso_partner"] == jur) & (cits["year"] == year)).any()
]
cits = pd.concat([cits, pd.DataFrame(missing_cits)], ignore_index=True)

cits.loc[cits["iso_partner"] == "MLT", "cit"] *= 1 / 7
cits.loc[cits["iso_partner"] == "GIB", "cit"] = 0
cits.loc[cits["iso_partner"] == "MCO", "cit"] = 0
cits.loc[cits["iso_partner"] == "AND", "cit"] = 0
cits.loc[cits["iso_partner"] == "CAF", "cit"] = 0.3
cits.loc[cits["iso_partner"] == "HTI", "cit"] = 0.3
cits.loc[cits["iso_partner"] == "YEM", "cit"] = 0.2
cits.loc[cits["iso_partner"] == "NCL", "cit"] = 0
cits.loc[(cits["iso_partner"] == "PRK") & (cits["cit"].isna()), "cit"] = 0.325
cits.loc[(cits["iso_partner"] == "COD") & (cits["cit"].isna()), "cit"] = 0.28
cits.loc[(cits["iso_partner"] == "TLS") & (cits["cit"].isna()), "cit"] = 0.10
cits.loc[(cits["iso_partner"] == "MHL") & (cits["cit"].isna()), "cit"] = 0
cits.loc[(cits["iso_partner"] == "GLP") & (cits["cit"].isna()), "cit"] = 0.15
cits.loc[(cits["iso_partner"] == "GUF") & (cits["cit"].isna()), "cit"] = 0.28
cits.loc[(cits["iso_partner"] == "IOT") & (cits["cit"].isna()), "cit"] = 0
cits.loc[(cits["iso_partner"] == "PLW") & (cits["cit"].isna()), "cit"] = 0
cits.loc[(cits["iso_partner"] == "PYF") & (cits["cit"].isna()), "cit"] = 0.27
cits.loc[(cits["iso_partner"] == "REU") & (cits["cit"].isna()), "cit"] = 0.15
cits.loc[(cits["iso_partner"] == "SOM") & (cits["cit"].isna()), "cit"] = 0.3
cits.loc[(cits["iso_partner"] == "XKV") & (cits["cit"].isna()), "cit"] = 0.1
cits.loc[(cits["iso_partner"] == "SMR") & (cits["cit"].isna()), "cit"] = 0.17

cbcr_etrs_cits = cbcr_etrs.merge(cits, on=["iso_partner", "year"], how="left")

missing_cit_rows = cbcr_etrs_cits[
    (cbcr_etrs_cits["cit"].isnull())
    & (~cbcr_etrs_cits["iso_partner"].isin(non_countries))
]

if not missing_cit_rows.empty:
    missing_iso_partners_cit = missing_cit_rows[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: CIT values are missing for the following iso_partner countries and years (excluding specified groups):"
    )
    for _, row in missing_iso_partners_cit.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing CIT values found.")

etr_missing_before = cbcr_etrs_cits[cbcr_etrs_cits["etr_average_corrected"].isna()][
    "iso_partner"
].unique()

mean_etr_by_country = cbcr_etrs_cits.groupby("iso_partner")[
    "etr_average_corrected"
].transform("mean")
cbcr_etrs_cits["etr_average_corrected"] = cbcr_etrs_cits[
    "etr_average_corrected"
].fillna(mean_etr_by_country)

etr_still_missing = cbcr_etrs_cits[cbcr_etrs_cits["etr_average_corrected"].isna()][
    "iso_partner"
].unique()

cbcr_etrs_cits["etr_average_corrected"] = cbcr_etrs_cits[
    "etr_average_corrected"
].fillna(cbcr_etrs_cits["cit"])

etr_missing_after = cbcr_etrs_cits[cbcr_etrs_cits["etr_average_corrected"].isna()][
    "iso_partner"
].unique()

etr_filled_with_cit = set(etr_still_missing) - set(etr_missing_after)
etr_filled_with_mean = (
    set(etr_missing_before) - set(etr_still_missing) - etr_filled_with_cit
)

if etr_filled_with_mean:
    print(
        f"ETR was filled using mean ETR from other years for iso_partner(s): {', '.join(sorted(etr_filled_with_mean))}"
    )
else:
    print("No missing ETRs were filled with mean ETR from other years.")

if etr_filled_with_cit:
    print(
        f"ETR was filled using CIT for iso_partner(s): {', '.join(sorted(etr_filled_with_cit))}"
    )
else:
    print("No missing ETRs were filled with CIT.")

cit_missing_before = cbcr_etrs_cits[cbcr_etrs_cits["cit"].isna()][
    "iso_partner"
].unique()

mean_cit_by_country = cbcr_etrs_cits.groupby("iso_partner")["cit"].transform("mean")
cbcr_etrs_cits["cit"] = cbcr_etrs_cits["cit"].fillna(mean_cit_by_country)

cit_still_missing = cbcr_etrs_cits[cbcr_etrs_cits["cit"].isna()]["iso_partner"].unique()

cbcr_etrs_cits["cit"] = cbcr_etrs_cits["cit"].fillna(
    cbcr_etrs_cits["etr_average_corrected"]
)

cit_missing_after = cbcr_etrs_cits[cbcr_etrs_cits["cit"].isna()]["iso_partner"].unique()

cit_filled_with_etr = set(cit_still_missing) - set(cit_missing_after)
cit_filled_with_mean = (
    set(cit_missing_before) - set(cit_still_missing) - cit_filled_with_etr
)

if cit_filled_with_mean:
    print(
        f"CIT was filled using mean CIT from other years for iso_partner(s): {', '.join(sorted(cit_filled_with_mean))}"
    )
else:
    print("No missing CITs were filled with mean CIT from other years.")

if cit_filled_with_etr:
    print(
        f"CIT was filled using ETR for iso_partner(s): {', '.join(sorted(cit_filled_with_etr))}"
    )
else:
    print("No missing CITs were filled with ETR.")

# %%
# 2.3 Import and clean GDP and population data

gdp_population_long = pd.read_csv(gdp_population_data)

formatted_years = [f"{year} [YR{year}]" for year in analysis_years]
columns_gdp_population_data = ["Series Name", "Country Code"] + formatted_years
gdp_population_long = gdp_population_long[columns_gdp_population_data].copy()

gdp_population_long = gdp_population_long.melt(
    id_vars=["Country Code", "Series Name"],
    value_vars=formatted_years,
    var_name="Year",
    value_name="Value",
)

gdp_population = gdp_population_long.pivot_table(
    index=["Country Code", "Year"],
    columns="Series Name",
    values="Value",
    aggfunc="first",
).reset_index()

pop_col = (
    "Population, total"
    if "Population, total" in gdp_population.columns
    else "Population total"
)

gdp_population = gdp_population.rename(
    columns={
        "Country Code": "iso_partner",
        "Year": "year",
        "GDP (current US$)": "gdp_current_usd",
        pop_col: "population",
    }
)

gdp_population["year"] = gdp_population["year"].str.extract(r"(\d{4})").astype(int)

missing_markers = ["..", "...", "......", "—"]
gdp_population["gdp_current_usd"] = pd.to_numeric(
    gdp_population["gdp_current_usd"].replace(missing_markers, np.nan),
    errors="coerce",
)
gdp_population["population"] = pd.to_numeric(
    gdp_population["population"].replace(missing_markers, np.nan),
    errors="coerce",
)

gdp_population = gdp_population[
    ["iso_partner", "year", "gdp_current_usd", "population"]
].copy()

missing_gdp = gdp_population["gdp_current_usd"].isna().sum()
missing_population = gdp_population["population"].isna().sum()

print(f"Missing GDP values: {missing_gdp}")
print(f"Missing population values: {missing_population}")

print("iso_partner with missing GDP values:")
print(
    gdp_population.loc[gdp_population["gdp_current_usd"].isna(), "iso_partner"].unique()
)

print("iso_partner with missing population values:")
print(gdp_population.loc[gdp_population["population"].isna(), "iso_partner"].unique())

sample_jur_year_df = pd.DataFrame(
    sample_jur_year, columns=["iso_partner", "year"]
).drop_duplicates()
gdp_population = sample_jur_year_df.merge(
    gdp_population, on=["iso_partner", "year"], how="left"
)

kosovo_code = "XKX" if "XKX" in gdp_population["iso_partner"].unique() else "XKV"

eur_usd_2022 = 1.0530
gbp_usd_2022 = 1.0530 / 0.852601

years_covered = sorted(gdp_population["year"].dropna().unique())

# %%
# 2.3a Manual GDP and population fills

# Anguilla
for year, value in {
    2016: 331 * 1e6,
    2017: 322 * 1e6,
    2018: 322 * 1e6,
    2019: 380 * 1e6,
    2020: 380 * 1e6,
    2021: 380 * 1e6,
    2022: 388_972_051,
}.items():
    fill_missing(gdp_population, "AIA", year, "gdp_current_usd", value)

for year, value in {
    2016: 14.3 * 1e3,
    2017: 14.4 * 1e3,
    2018: 14.7 * 1e3,
    2019: 14.8 * 1e3,
    2020: 14.8 * 1e3,
    2021: 14.5 * 1e3,
    2022: 14_180,
}.items():
    fill_missing(gdp_population, "AIA", year, "population", value)

# British Indian Ocean Territory
for year in years_covered:
    fill_missing(gdp_population, "IOT", year, "gdp_current_usd", 1e6)
    fill_missing(gdp_population, "IOT", year, "population", 3000)

# British Virgin Islands
for year, value in {
    2016: 1279 * 1e6,
    2017: 1279 * 1e6,
    2018: 1653 * 1e6,
    2019: 1653 * 1e6,
    2020: 1653 * 1e6,
    2021: 1653 * 1e6,
    2022: 1_471_233_257,
}.items():
    fill_missing(gdp_population, "VGB", year, "gdp_current_usd", value)
fill_missing(gdp_population, "VGB", 2022, "population", 38_319)

# Cook Islands
for year, value in {
    2016: 287988 * 1e3 * 0.69,
    2017: 345587 * 1e3 * 0.7,
    2018: 391959 * 1e3 * 0.67,
    2019: 593585 * 1e3 * 0.64,
    2020: 397791 * 1e3 * 0.7,
    2021: 349192 * 1e3 * 0.71,
    2022: 289_749_646,
}.items():
    fill_missing(gdp_population, "COK", year, "gdp_current_usd", value)

for year, value in {
    2016: 15076,
    2017: 15076,
    2018: 15153,
    2019: 15216,
    2020: 15281,
    2021: 15342,
    2022: 14_723,
}.items():
    fill_missing(gdp_population, "COK", year, "population", value)

# Eritrea
for year, value in {
    2016: 2.21 * 1e9,
    2017: 1.9 * 1e9,
    2018: 2.01 * 1e9,
    2019: 1.98 * 1e9,
    2020: 1.98 * 1e9,
    2021: 1.98 * 1e9,
}.items():
    fill_missing(gdp_population, "ERI", year, "gdp_current_usd", value)

# French Guiana
for year, value in {
    2016: 4131 / 0.904 * 1e6,
    2017: 4127 / 0.8865 * 1e6,
    2018: 4353 * 1.1811 * 1e6,
    2019: 4431 * 1.11 * 1e6,
    2020: 4275 * 1.21 * 1e6,
    2021: 4450 * 1.13 * 1e6,
    2022: 4562 * eur_usd_2022 * 1e6,
}.items():
    fill_missing(gdp_population, "GUF", year, "gdp_current_usd", value)

for year, value in {
    2016: 267821,
    2017: 275191,
    2018: 282938,
    2019: 281678,
    2020: 285133,
    2021: 286618,
    2022: 288382,
}.items():
    fill_missing(gdp_population, "GUF", year, "population", value)

# Falkland Islands
fill_missing(gdp_population, "FLK", 2016, "gdp_current_usd", 206.4 * 1e6)
for year, value in {
    2016: 3478,
    2017: 3518,
    2018: 3521,
    2019: 3517,
    2020: 3506,
    2021: 3490,
}.items():
    fill_missing(gdp_population, "FLK", year, "population", value)

# Gibraltar
for year, value in {
    2016: 2.344 * 1.3349 * 1e9,
    2017: 2.344 * 1.3349 * 1e9,
    2018: 2.344 * 1.3349 * 1e9,
    2019: 2.344 * 1.3349 * 1e9,
    2020: 2.344 * 1.3349 * 1e9,
    2021: 2.344 * 1.3349 * 1e9,
}.items():
    fill_missing(gdp_population, "GIB", year, "gdp_current_usd", value)
fill_missing(gdp_population, "GIB", 2022, "population", 37_936)

# Guadeloupe
for year, value in {
    2016: 8712.316 / 0.904 * 1e6,
    2017: 8803.461 / 0.8865 * 1e6,
    2018: 9025.467 * 1.1811 * 1e6,
    2019: 9268.066 * 1.11 * 1e6,
    2020: 8857.257 * 1.21 * 1e6,
    2021: 9169.070 * 1.13 * 1e6,
    2022: 9877.241 * eur_usd_2022 * 1e6,
}.items():
    fill_missing(gdp_population, "GLP", year, "gdp_current_usd", value)

for year, value in {
    2016: 395700,
    2017: 402119,
    2018: 402119,
    2019: 384239,
    2020: 383559,
    2021: 384315,
    2022: 383569,
}.items():
    fill_missing(gdp_population, "GLP", year, "population", value)

# Guernsey
for year, value in {
    2016: 2934 * 1.3552 * 1e6,
    2017: 3101 * 1.289 * 1e6,
    2018: 3170 * 1.3349 * 1e6,
    2019: 3248 * 1e6 * 1.31,
    2020: 3125 * 1e6 * 1.32,
    2021: 3446 * 1e6 * 1.34,
    2022: 3349 * gbp_usd_2022 * 1e6,
}.items():
    fill_missing(gdp_population, "GGY", year, "gdp_current_usd", value)

for year, value in {
    2016: 61908,
    2017: 62046,
    2018: 62506,
    2019: 62885,
    2020: 63156,
    2021: 63664,
    2022: 63950,
}.items():
    fill_missing(gdp_population, "GGY", year, "population", value)

# Jersey
for year, value in {
    2016: 4.11 * 1.3552 * 1e9,
    2017: 4.304 * 1.289 * 1e9,
    2018: 4.642 * 1.3349 * 1e9,
    2019: 4.885 * 1.31 * 1e9,
    2020: 4.528 * 1.32 * 1e9,
    2021: 5.087 * 1.34 * 1e9,
    2022: 5761 * gbp_usd_2022 * 1e6,
}.items():
    fill_missing(gdp_population, "JEY", year, "gdp_current_usd", value)

for year, value in {
    2016: 102200,
    2017: 102700,
    2018: 103300,
    2019: 103200,
    2020: 103300,
    2021: 103100,
    2022: 103300,
}.items():
    fill_missing(gdp_population, "JEY", year, "population", value)

# Kosovo
for year, value in {
    2016: 6.68 * 1e9,
    2017: 7.18 * 1e9,
    2018: 7.88 * 1e9,
    2019: 7.9 * 1e9,
    2020: 7.73 * 1e9,
    2021: 9.42 * 1e9,
    2022: 9_375_000_000,
}.items():
    fill_missing(gdp_population, kosovo_code, year, "gdp_current_usd", value)

for year, value in {
    2016: 1777557,
    2017: 1791003,
    2018: 1797085,
    2019: 1788878,
    2020: 1790133,
    2021: 1786038,
}.items():
    fill_missing(gdp_population, kosovo_code, year, "population", value)

# Northern Mariana Islands
for year, value in {
    2016: 1230 * 1e6,
    2017: 1560 * 1e6,
    2018: 1301 * 1e6,
    2019: 1181 * 1e6,
    2020: 858 * 1e6,
    2021: 1181 * 1e6,
    2022: 1_096_000_000,
}.items():
    fill_missing(gdp_population, "MNP", year, "gdp_current_usd", value)
fill_missing(gdp_population, "MNP", 2022, "population", 46_078)

# Martinique
fill_missing(gdp_population, "MTQ", 2021, "gdp_current_usd", 9459 * 1e6 * 1.12)
fill_missing(
    gdp_population, "MTQ", 2022, "gdp_current_usd", 9653.712 * eur_usd_2022 * 1e6
)
for year, value in {
    2016: 378865,
    2017: 371502,
    2018: 364089,
    2019: 359611,
    2020: 356615,
    2021: 353278,
    2022: 361019,
}.items():
    fill_missing(gdp_population, "MTQ", year, "population", value)

# North Korea
fill_missing(gdp_population, "PRK", 2016, "gdp_current_usd", 772921776)

# Réunion
for year, value in {
    2016: 18065 / 0.904 * 1e6,
    2017: 18555 / 0.8865 * 1e6,
    2018: 18822 * 1.1811 * 1e6,
    2019: 19367 * 1.11 * 1e6,
    2020: 19032 * 1.21 * 1e6,
    2021: 20412 * 1.13 * 1e6,
    2022: 21668.213 * eur_usd_2022 * 1e6,
}.items():
    fill_missing(gdp_population, "REU", year, "gdp_current_usd", value)

for year, value in {
    2016: 926628,
    2017: 932739,
    2018: 941187,
    2019: 861210,
    2020: 863083,
    2021: 871157,
    2022: 881348,
}.items():
    fill_missing(gdp_population, "REU", year, "population", value)

# San Marino
for year, value in {
    2016: 1.468 * 1e9,
    2017: 1.529 * 1e9,
    2018: 1.655 * 1e9,
    2019: 1.616 * 1e9,
    2020: 1.541 * 1e9,
    2021: 1.855 * 1e9,
    2022: 1_833_000_000,
}.items():
    fill_missing(gdp_population, "SMR", year, "gdp_current_usd", value)

for year, value in {
    2016: 33834,
    2017: 34056,
    2018: 34156,
    2019: 34178,
    2020: 34007,
    2021: 33745,
}.items():
    fill_missing(gdp_population, "SMR", year, "population", value)

# Saint Martin
fill_missing(gdp_population, "MAF", 2021, "gdp_current_usd", 649_206_263)
fill_missing(gdp_population, "MAF", 2022, "population", 28_870)

# South Sudan
for year, value in {
    2016: 2.9 * 1e9,
    2017: 1.8 * 1e9,
    2018: 3.12 * 1e9,
    2019: 4.04 * 1e9,
    2020: 5.42 * 1e9,
    2021: 5.94 * 1e9,
    2022: 5_317_000_000,
}.items():
    fill_missing(gdp_population, "SSD", year, "gdp_current_usd", value)
fill_missing(gdp_population, "SSD", 2022, "population", 11_000_000)

# Taiwan
for year, value in {
    2016: 543.08 * 1e9,
    2017: 590.73 * 1e9,
    2018: 609.2 * 1e9,
    2019: 611.4 * 1e9,
    2020: 673.18 * 1e9,
    2021: 773.04 * 1e9,
    2022: 765_624_000_000,
}.items():
    fill_missing(gdp_population, "TWN", year, "gdp_current_usd", value)

for year, value in {
    2016: 23512136,
    2017: 23665024,
    2018: 23726185,
    2019: 23674138,
    2020: 23663459,
    2021: 23663459,
    2022: 23_420_111,
}.items():
    fill_missing(gdp_population, "TWN", year, "population", value)

# Venezuela
for year, value in {
    2016: 112.92 * 1e9,
    2017: 115.88 * 1e9,
    2018: 102.02 * 1e9,
    2019: 73 * 1e9,
    2020: 43.79 * 1e9,
    2021: 57.67 * 1e9,
    2022: 89_013_000_000,
}.items():
    fill_missing(gdp_population, "VEN", year, "gdp_current_usd", value)
fill_missing(gdp_population, "VEN", 2022, "population", 28_213_017)

# Wallis and Futuna
for year, value in {
    2016: 139500 * 1e3,
    2017: 139500 * 1e3,
    2018: 139500 * 1e3,
    2019: 139500 * 1e3,
    2020: 139500 * 1e3,
    2021: 139500 * 1e3,
}.items():
    fill_missing(gdp_population, "WLF", year, "gdp_current_usd", value)

for year, value in {
    2016: 12060,
    2017: 11936,
    2018: 11816,
    2019: 11502,
    2020: 11441,
    2021: 11369,
    2022: 11_478,
}.items():
    fill_missing(gdp_population, "WLF", year, "population", value)

for col in ["gdp_current_usd", "population"]:
    values_2021 = gdp_population.loc[
        gdp_population["year"] == 2021, ["iso_partner", col]
    ].rename(columns={col: f"{col}_2021"})
    gdp_population = gdp_population.merge(values_2021, on="iso_partner", how="left")

    mask_2022_missing = (gdp_population["year"] == 2022) & (gdp_population[col].isna())
    gdp_population.loc[mask_2022_missing, col] = gdp_population.loc[
        mask_2022_missing, f"{col}_2021"
    ]

    gdp_population = gdp_population.drop(columns=[f"{col}_2021"])

avg_gdp = gdp_population.groupby("iso_partner")["gdp_current_usd"].transform("mean")
gdp_population["gdp_current_usd"] = gdp_population["gdp_current_usd"].fillna(avg_gdp)

avg_pop = gdp_population.groupby("iso_partner")["population"].transform("mean")
gdp_population["population"] = gdp_population["population"].fillna(avg_pop)

cbcr_etrs_cits_gdp = cbcr_etrs_cits.merge(
    gdp_population,
    on=["iso_partner", "year"],
    how="left",
)

missing_gdp_rows = cbcr_etrs_cits_gdp[
    (cbcr_etrs_cits_gdp["gdp_current_usd"].isnull())
    & (~cbcr_etrs_cits_gdp["iso_partner"].isin(non_countries))
]
missing_population_rows = cbcr_etrs_cits_gdp[
    (cbcr_etrs_cits_gdp["population"].isnull())
    & (~cbcr_etrs_cits_gdp["iso_partner"].isin(non_countries))
]

if not missing_gdp_rows.empty:
    missing_iso_partners_gdp = missing_gdp_rows[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print("Warning: GDP is missing for the following iso_partner countries and years:")
    for _, row in missing_iso_partners_gdp.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing GDP values found.")

if not missing_population_rows.empty:
    missing_iso_partners_population = missing_population_rows[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: Population is missing for the following iso_partner countries and years:"
    )
    for _, row in missing_iso_partners_population.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing population values found.")

# %%
# 2.4 Import and clean wage data

wages_fulltable = pd.read_csv(wage_data)

if "sex" in wages_fulltable.columns:
    both_sexes = wages_fulltable["sex"] == "SEX_T"
    all_occupations = wages_fulltable["classif1"] == "ECO_SECTOR_TOTAL"
    in_usd = wages_fulltable["classif2"] == "CUR_TYPE_USD"
    relevant_years = (wages_fulltable["time"] >= first_year) & (
        wages_fulltable["time"] <= last_year
    )
    relevant_rows = both_sexes & all_occupations & in_usd & relevant_years

    wages = wages_fulltable.loc[
        relevant_rows, ["ref_area", "time", "obs_value"]
    ].reset_index(drop=True)
    wages.rename(
        columns={
            "ref_area": "iso_partner",
            "time": "year",
            "obs_value": "wage_monthly",
        },
        inplace=True,
    )

else:
    import pycountry

    both_sexes = wages_fulltable["sex.label"] == "Total"
    in_usd = wages_fulltable["classif1.label"] == "Currency: U.S. dollars"
    relevant_years = (wages_fulltable["time"] >= first_year) & (
        wages_fulltable["time"] <= last_year
    )
    relevant_rows = both_sexes & in_usd & relevant_years

    wages = wages_fulltable.loc[
        relevant_rows, ["ref_area.label", "time", "obs_value"]
    ].reset_index(drop=True)
    wages.rename(
        columns={
            "ref_area.label": "country_name",
            "time": "year",
            "obs_value": "wage_monthly",
        },
        inplace=True,
    )

    manual_map = {
        "Bolivia (Plurinational State of)": "BOL",
        "Congo, Democratic Republic of the": "COD",
        "Hong Kong, China": "HKG",
        "Republic of Korea": "KOR",
        "Kosovo": kosovo_code,
        "Macao, China": "MAC",
    }

    def name_to_iso3(name):
        if name in manual_map:
            return manual_map[name]
        try:
            return pycountry.countries.lookup(name).alpha_3
        except Exception:
            return None

    wages["iso_partner"] = wages["country_name"].map(name_to_iso3)
    unmapped = wages[wages["iso_partner"].isna()]["country_name"].unique()
    if len(unmapped) > 0:
        print(
            f"Warning: Could not map {len(unmapped)} country names to ISO3: {unmapped}"
        )

    wages = wages.dropna(subset=["iso_partner"])
    wages = wages[["iso_partner", "year", "wage_monthly"]].copy()

missing_wages = []
for jur, year in sample_jur_year:
    if not ((wages["iso_partner"] == jur) & (wages["year"] == year)).any():
        missing_wages.append({"iso_partner": jur, "year": year})

wages = pd.concat([wages, pd.DataFrame(missing_wages)], ignore_index=True)

avg_wage = wages.groupby("iso_partner")["wage_monthly"].transform("mean")
wages["wage_monthly"] = wages["wage_monthly"].fillna(avg_wage)

wages.loc[wages["iso_partner"] == "AIA", "wage_monthly"] = 74620.18 / 12
wages.loc[wages["iso_partner"] == "COK", "wage_monthly"] = 2913.46
wages.loc[wages["iso_partner"] == "GGY", "wage_monthly"] = 9859.02
wages.loc[wages["iso_partner"] == "GIB", "wage_monthly"] = 4462
wages.loc[wages["iso_partner"] == "GLP", "wage_monthly"] = 2277.85
wages.loc[wages["iso_partner"] == "GUF", "wage_monthly"] = 16983.03 / 12
wages.loc[wages["iso_partner"] == "JEY", "wage_monthly"] = 1098.36 * 4
wages.loc[wages["iso_partner"] == "MAF", "wage_monthly"] = 46000 / 12
wages.loc[wages["iso_partner"] == "TWN", "wage_monthly"] = 21689 / 12
wages.loc[wages["iso_partner"] == "WLF", "wage_monthly"] = 625.75

cbcr_etrs_cits_gdp_wages = cbcr_etrs_cits_gdp.merge(
    wages,
    on=["iso_partner", "year"],
    how="left",
)

missing_wages_after_merge = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages["wage_monthly"].isna())
    & (~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(non_countries))
]

if not missing_wages_after_merge.empty:
    missing_iso_partners_wages = missing_wages_after_merge[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: The following years and countries have to be imputed in the next step:"
    )
    for _, row in missing_iso_partners_wages.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing wage data after the merge.")

# %%
# 2.4b Impute wages using GDP and population

offsample_countries = []

for country, gdp_per_capita, wage in zip(
    cbcr_etrs_cits_gdp_wages["iso_partner"],
    cbcr_etrs_cits_gdp_wages["gdp_current_usd"]
    / cbcr_etrs_cits_gdp_wages["population"],
    cbcr_etrs_cits_gdp_wages["wage_monthly"],
):
    if pd.notna(gdp_per_capita) and pd.notna(wage) and gdp_per_capita > 0 and wage > 0:
        ratio = np.log(gdp_per_capita / 12 / wage)
        if (ratio > np.log2(1.5)) or (ratio < -2):
            offsample_countries.append(country)

offsample_countries = list(dict.fromkeys(offsample_countries))

ols_sample = cbcr_etrs_cits_gdp_wages[
    ~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(offsample_countries)
].copy()

ols_sample = ols_sample.dropna(subset=["wage_monthly", "gdp_current_usd", "population"])
ols_sample = ols_sample[
    (ols_sample["wage_monthly"] > 0)
    & (ols_sample["gdp_current_usd"] > 0)
    & (ols_sample["population"] > 0)
].copy()

cbcr_etrs_cits_gdp_wages["pred_wage_monthly"] = np.nan

if not ols_sample.empty:
    ols_regression = smf.ols(
        formula="np.log(wage_monthly) ~ np.log(gdp_current_usd) + np.log(population)",
        data=ols_sample,
    )
    ols_fitted_values = ols_regression.fit()

    cbcr_etrs_cits_gdp_wages["pred_wage_monthly"] = np.exp(
        ols_fitted_values.predict(cbcr_etrs_cits_gdp_wages)
    )

cbcr_etrs_cits_gdp_wages.loc[
    cbcr_etrs_cits_gdp_wages["wage_monthly"].isna(), "wage_monthly"
] = cbcr_etrs_cits_gdp_wages.loc[
    cbcr_etrs_cits_gdp_wages["wage_monthly"].isna(), "pred_wage_monthly"
]

cbcr_etrs_cits_gdp_wages.drop(columns=["pred_wage_monthly"], inplace=True)

missing_after_imputation = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages["wage_monthly"].isna())
    & (~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(non_countries))
].shape[0]
print(f"Missing wages after imputation: {missing_after_imputation}")

missing_wages_countries_years = cbcr_etrs_cits_gdp_wages[
    (cbcr_etrs_cits_gdp_wages["wage_monthly"].isna())
    & (~cbcr_etrs_cits_gdp_wages["iso_partner"].isin(non_countries))
][["iso_partner", "year"]].drop_duplicates()

for _, row in missing_wages_countries_years.iterrows():
    country = row["iso_partner"]
    year = row["year"]
    reasons = []

    if country in offsample_countries:
        reasons.append("wages flagged as implausible")

    country_year_slice = cbcr_etrs_cits_gdp_wages[
        (cbcr_etrs_cits_gdp_wages["iso_partner"] == country)
        & (cbcr_etrs_cits_gdp_wages["year"] == year)
    ]

    if country_year_slice["gdp_current_usd"].isna().any():
        reasons.append("missing GDP data")
    if country_year_slice["population"].isna().any():
        reasons.append("missing population data")

    reason_str = (
        ", ".join(reasons)
        if reasons
        else "no wage data available even after prediction"
    )
    print(f"Wages missing for {country} in year {year}: {reason_str}")

cbcr_etrs_cits_gdp_wages["payroll"] = (
    cbcr_etrs_cits_gdp_wages["n_employees"]
    * cbcr_etrs_cits_gdp_wages["wage_monthly"]
    * 12
)

for col_name in ["wage_monthly", "gdp_current_usd", "population"]:
    cbcr_etrs_cits_gdp_wages[f"ln_{col_name}"] = np.log1p(
        cbcr_etrs_cits_gdp_wages[col_name].clip(lower=0)
    )

# %%
# 2.5 Import and clean government health expenditure data

health_expenditure_wide = pd.read_excel(health_expenditure_data)

health_expenditure_wide = health_expenditure_wide[
    health_expenditure_wide["Indicators"]
    == "Domestic General Government Health Expenditure (GGHE-D)"
].copy()

health_expenditure_wide = health_expenditure_wide.dropna(subset=["Countries"]).copy()
health_expenditure_wide["iso_partner"] = pd.NA

health_expenditure_wide.loc[
    health_expenditure_wide["Countries"] == "Netherlands (Kingdom of the)",
    "iso_partner",
] = "NLD"
print("Netherlands value corrected")

health_expenditure_wide.loc[
    health_expenditure_wide["Countries"] == "Türkiye", "iso_partner"
] = "TUR"
print("Turkey value corrected")

health_expenditure_wide.loc[
    health_expenditure_wide["Countries"]
    == "occupied Palestinian territory, including east Jerusalem",
    "iso_partner",
] = "PSE"
print("Palestine value corrected")

mask_missing_iso = health_expenditure_wide["iso_partner"].isna()
health_expenditure_wide.loc[mask_missing_iso, "iso_partner"] = (
    health_expenditure_wide.loc[mask_missing_iso, "Countries"].map(
        data_processing.get_iso3
    )
)

year_cols = [str(year) for year in analysis_years]
columns_health_data = ["iso_partner"] + year_cols
health_expenditure_wide = health_expenditure_wide[columns_health_data].copy()

health_expenditure = health_expenditure_wide.melt(
    id_vars=["iso_partner"],
    value_vars=year_cols,
    var_name="year",
    value_name="gvt_health_expenditure",
)

health_expenditure["year"] = health_expenditure["year"].astype(int)
health_expenditure["gvt_health_expenditure"] = (
    pd.to_numeric(health_expenditure["gvt_health_expenditure"], errors="coerce") * 1e6
)
health_expenditure["ln_gvt_health_expenditure"] = np.log1p(
    health_expenditure["gvt_health_expenditure"].clip(lower=0)
)

cbcr_etrs_cits_gdp_wages_health = cbcr_etrs_cits_gdp_wages.merge(
    health_expenditure,
    on=["iso_partner", "year"],
    how="left",
)

missing_health_expenditure_rows = cbcr_etrs_cits_gdp_wages_health[
    (cbcr_etrs_cits_gdp_wages_health["gvt_health_expenditure"].isna())
    & (~cbcr_etrs_cits_gdp_wages_health["iso_partner"].isin(non_countries))
]

missing_health_expenditure_count = missing_health_expenditure_rows.shape[0]
print(
    f"Missing government health expenditure data after the merge: {missing_health_expenditure_count}"
)

missing_health_expenditure_countries_years = missing_health_expenditure_rows[
    ["iso_partner", "year"]
].drop_duplicates()

for _, row in missing_health_expenditure_countries_years.iterrows():
    print(
        f"Health expenditure data missing for {row['iso_partner']} in year {row['year']}"
    )

# %%
# 2.6 Import and clean tax revenue data

tax_revenue_wide = pd.read_csv(tax_revenue_data, skiprows=4)

tax_revenue = tax_revenue_wide.melt(
    id_vars=["Country Code"],
    value_vars=[str(year) for year in analysis_years],
    var_name="year",
    value_name="tax_revenue_pct_gdp",
)
tax_revenue.rename(columns={"Country Code": "iso_partner"}, inplace=True)
tax_revenue["year"] = tax_revenue["year"].astype(int)

cbcr_etrs_cits_gdp_wages_health_taxes = cbcr_etrs_cits_gdp_wages_health.merge(
    tax_revenue,
    on=["iso_partner", "year"],
    how="left",
)

cbcr_etrs_cits_gdp_wages_health_taxes["tax_revenue_pct_gdp"] = pd.to_numeric(
    cbcr_etrs_cits_gdp_wages_health_taxes["tax_revenue_pct_gdp"],
    errors="coerce",
)
cbcr_etrs_cits_gdp_wages_health_taxes["gdp_current_usd"] = pd.to_numeric(
    cbcr_etrs_cits_gdp_wages_health_taxes["gdp_current_usd"],
    errors="coerce",
)

cbcr_etrs_cits_gdp_wages_health_taxes["tax_revenue_current_usd"] = (
    cbcr_etrs_cits_gdp_wages_health_taxes["tax_revenue_pct_gdp"]
    / 100
    * cbcr_etrs_cits_gdp_wages_health_taxes["gdp_current_usd"]
)

missing_tax_revenue_rows = cbcr_etrs_cits_gdp_wages_health_taxes[
    (cbcr_etrs_cits_gdp_wages_health_taxes["tax_revenue_pct_gdp"].isna())
    & (~cbcr_etrs_cits_gdp_wages_health_taxes["iso_partner"].isin(non_countries))
]

missing_tax_revenue_count = missing_tax_revenue_rows.shape[0]
print(
    f"Missing tax revenue percentage of GDP data after the merge: {missing_tax_revenue_count}"
)

missing_tax_revenue_countries_years = missing_tax_revenue_rows[
    ["iso_partner", "year"]
].drop_duplicates()

for _, row in missing_tax_revenue_countries_years.iterrows():
    print(f"Tax revenue data missing for {row['iso_partner']} in year {row['year']}")

# %%
# 2.7 Import region variables and World Bank income groups

regions = pd.read_csv(
    unilateral_cross_data,
    usecols=[
        "iso3",
        "region_tjn",
        "ukt",
        "gbr_oct",
        "oecd_oct",
        "oecd",
        "eu28",
        "nld_oct",
    ],
).dropna(subset=["iso3"])

regions.rename(columns={"iso3": "iso_partner"}, inplace=True)
regions.loc[regions["iso_partner"] == "XXK", "iso_partner"] = "XKV"

url = "https://api.worldbank.org/v2/country?format=json&per_page=400"

try:
    wb_response = requests.get(url, timeout=30)
    wb_response.raise_for_status()
    wb_json = wb_response.json()

    if isinstance(wb_json, list) and len(wb_json) > 1 and wb_json[1] is not None:
        wb_raw = wb_json[1]
    else:
        wb_raw = []

except Exception as exc:
    print(f"Warning: could not download World Bank income groups. {exc}")
    wb_raw = []

wb_income = pd.DataFrame(
    [
        {
            "iso_partner": c["id"],
            "wb_income_group": c["incomeLevel"]["value"],
            "wb_income_group_id": c["incomeLevel"]["id"],
        }
        for c in wb_raw
        if c.get("region", {}).get("value") != "Aggregates"
        and c.get("id") is not None
        and len(c.get("id")) == 3
    ]
)

if wb_income.empty:
    wb_income = pd.DataFrame(
        columns=["iso_partner", "wb_income_group", "wb_income_group_id"]
    )
else:
    wb_income["wb_income_group"] = wb_income["wb_income_group"].replace(
        {
            "Low income": "low_income",
            "Lower middle income": "lower_middle_income",
            "Upper middle income": "upper_middle_income",
            "High income": "high_income",
        }
    )

# %%
# 3. Merge final datasets and save outputs

cbcr_main = cbcr_etrs_cits_gdp_wages_health_taxes.merge(
    regions,
    on=["iso_partner"],
    how="left",
)

cbcr_main = cbcr_main.merge(
    wb_income,
    on="iso_partner",
    how="left",
)

cbcr_main["eu"] = cbcr_main["eu28"]
cbcr_main.loc[
    (cbcr_main["iso_partner"] == "GBR") & (cbcr_main["year"] >= 2020),
    "eu",
] = 0
cbcr_main.drop(columns=["eu28"], inplace=True)

variables_to_replace = ["ukt", "gbr_oct", "oecd_oct", "oecd", "eu", "nld_oct"]
cbcr_main[variables_to_replace] = cbcr_main[variables_to_replace].fillna(0)

cbcr_main_allsubgroupsonly = cbcr_main[
    cbcr_main["grouping"] == "Total (All sub-groups)"
].copy()
cbcr_main_allsubgroupsonly.drop(columns=["grouping"], inplace=True)

# %%
# 3.1 Save outputs

cbcr_main.to_csv(f"{data_final}/cbcr_main.csv", index=False)
cbcr_main_allsubgroupsonly.to_csv(
    f"{data_final}/cbcr_main_allsubgroupsonly.csv",
    index=False,
)

# %%
# 3.2 Final checks

check_duplicates(cbcr_main_allsubgroupsonly, "final dataset (reporting sample only)")

inf_check = cbcr_main.isin([np.inf, -np.inf]).any().any()
if inf_check:
    print("There were inf or -inf values in the DataFrame.")
else:
    print("No inf or -inf values found in the DataFrame.")

print(cbcr_main_allsubgroupsonly.columns.tolist())
