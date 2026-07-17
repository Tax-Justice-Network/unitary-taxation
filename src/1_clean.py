# %%
# ## OECD Country by Country Reports: Data cleaning for misalignment analyses
#
# - Author: Alison Schultz, based on Javier Garcia-Bernado's work
# - Created: 4 August 2023
# - Last updated: 19 May 2026
#
# **Description**
# - This notebook is one out of three notebooks to estimate the tax losses caused by profit shifting by multinational enterprises (MNEs).
# - The analysis uses the misalignment method based on the country-by-country reports (CbCR) published by the OECD.
# - It produces:
#     - '{data_final}/cbcr_main_allsubgroupsonly.csv'
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
from _etr_construction import (
    compute_partner_year_etrs,
    safe_nonnegative_etr,
)

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


def load_manual_imputation_values():
    """Load the curated manual macro / CIT / wage values.

    Single source of truth for the values that used to be hard-coded in this
    script (small-territory GDP/population, the flat CIT overrides, and the
    hand-collected wages). Lives in ``data/raw/manual_imputation_values.csv``
    with columns ``iso_partner, year, variable, value, mode, source_url, note``.
    """
    manual = pd.read_csv(f"{data_raw}manual_imputation_values.csv")
    manual["year"] = pd.to_numeric(manual["year"], errors="coerce")
    return manual


def apply_manual_values(df, manual, variables):
    """Apply curated manual values (in place) to ``df`` for ``variables``.

    Each manual row sets ``df[variable]`` for the matching ``iso_partner``
    (and ``year`` if one is given; a blank year applies to every row for that
    jurisdiction). ``mode == "fill_if_missing"`` only writes where the cell is
    currently NaN; ``mode == "override"`` writes unconditionally. Rows whose
    target column is absent from ``df`` are skipped.
    """
    sub = manual[manual["variable"].isin(variables)]
    for _, row in sub.iterrows():
        column = row["variable"]
        if column not in df.columns:
            continue
        mask = df["iso_partner"] == row["iso_partner"]
        if pd.notna(row["year"]):
            mask &= df["year"] == int(row["year"])
        if row["mode"] == "fill_if_missing":
            mask &= df[column].isna()
        df.loc[mask, column] = float(row["value"])


MANUAL_VALUES = load_manual_imputation_values()


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

    # Use OECD adjusted profits if available.
    # In these cases, do not apply any further manual correction.
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


def main_etrs(file, grouping_name="Sub-groups with positive profits"):
    """Compute partner-year ETRs (domestic / foreign / average) over a rolling
    5-year window, for both reported profit and corrected profit.

    Thin wrapper around compute_partner_year_etrs in _etr_construction.py —
    called twice (uncorrected, corrected) and merged so the output columns
    match the canonical cleaning-stage names (etr_domestic, etr_foreign,
    etr_average, etr_domestic_corrected, etr_foreign_corrected,
    etr_average_corrected).
    """
    partner_uncorrected, _ = compute_partner_year_etrs(
        file,
        profit_col="profit_loss_before_income_tax",
        tax_col="income_tax_paid_on_cash_basis",
        suffix=None,
        grouping_col="grouping",
        grouping_value=grouping_name,
        window=2,
        pair_stats=False,
    )
    partner_corrected, _ = compute_partner_year_etrs(
        file,
        profit_col="profit_loss_before_income_tax_corrected",
        tax_col="income_tax_paid_on_cash_basis",
        suffix="corrected",
        grouping_col="grouping",
        grouping_value=grouping_name,
        window=2,
        pair_stats=False,
    )

    merged = partner_uncorrected.merge(
        partner_corrected, on=["iso_partner", "year"], how="outer"
    )
    return merged


def alternative_corrected_etrs(file, grouping_name="Sub-groups with positive profits"):
    """Pair-specific corrected ETR + partner-level median/p25/min over the
    rolling window. Thin wrapper around compute_partner_year_etrs.

    Returns (pair_year_df, partner_year_df) to preserve the original signature.
    """
    partner_year, pair_year = compute_partner_year_etrs(
        file,
        profit_col="profit_loss_before_income_tax_corrected",
        tax_col="income_tax_paid_on_cash_basis",
        suffix="corrected",
        grouping_col="grouping",
        grouping_value=grouping_name,
        window=2,
        pair_stats=True,
    )

    partner_stats_only = partner_year[
        [
            "iso_partner",
            "year",
            "etr_partner_median_corrected",
            "etr_partner_p25_corrected",
            "etr_partner_min_corrected",
        ]
    ].copy()

    return pair_year, partner_stats_only


def fill_missing_cit_and_corrected_etrs(df):
    """
    Final fallback step after CIT has been merged.

    Logic:
    1. Complete CIT first:
       - fill with country mean CIT across years
       - then use corrected ETR columns as backup
       - then use the global median CIT as final safeguard

    2. Complete corrected ETRs:
       - partner-year ETRs: fill with country mean over years, then CIT
       - pair-specific ETR: fill with pair mean over years, then partner mean,
         then CIT

    Aggregate partner rows remain untouched.
    """
    df = df.copy()

    corrected_partner_cols = [
        "etr_domestic_corrected",
        "etr_foreign_corrected",
        "etr_average_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_min_corrected",
    ]
    pair_specific_col = "etr_parent_partner_corrected"

    real_mask = ~df["iso_partner"].isin(non_countries)
    real = df.loc[real_mask].copy()

    # Complete CIT first
    real["cit"] = pd.to_numeric(real["cit"], errors="coerce").clip(lower=0, upper=1)

    cit_missing_before = real["cit"].isna().sum()

    mean_cit_by_country = real.groupby("iso_partner")["cit"].transform("mean")
    real["cit"] = real["cit"].fillna(mean_cit_by_country)

    cit_backup_cols = [
        "etr_average_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_min_corrected",
        "etr_parent_partner_corrected",
    ]

    for col in cit_backup_cols:
        if col in real.columns:
            real["cit"] = real["cit"].fillna(real[col])

    global_median_cit = real["cit"].median(skipna=True)
    real["cit"] = real["cit"].fillna(global_median_cit).clip(lower=0, upper=1)

    cit_missing_after = real["cit"].isna().sum()

    print(f"CIT missing before fallback: {cit_missing_before}")
    print(f"CIT missing after fallback: {cit_missing_after}")

    # Fill pair-specific corrected ETR
    if pair_specific_col in real.columns:
        real[pair_specific_col] = pd.to_numeric(
            real[pair_specific_col], errors="coerce"
        )

        missing_before = real[pair_specific_col].isna().sum()

        pair_mean = real.groupby(["iso_parent", "iso_partner"])[
            pair_specific_col
        ].transform("mean")
        partner_mean = real.groupby("iso_partner")[pair_specific_col].transform("mean")

        real[pair_specific_col] = real[pair_specific_col].fillna(pair_mean)
        real[pair_specific_col] = real[pair_specific_col].fillna(partner_mean)
        real[pair_specific_col] = real[pair_specific_col].fillna(real["cit"])
        real[pair_specific_col] = real[pair_specific_col].clip(lower=0, upper=1)

        missing_after = real[pair_specific_col].isna().sum()
        print(
            f"{pair_specific_col}: filled {missing_before - missing_after} missing values; remaining missing {missing_after}"
        )

    # Fill partner-level corrected ETRs
    for col in corrected_partner_cols:
        if col not in real.columns:
            continue

        real[col] = pd.to_numeric(real[col], errors="coerce")
        missing_before = real[col].isna().sum()

        partner_mean = real.groupby("iso_partner")[col].transform("mean")

        real[col] = real[col].fillna(partner_mean)
        real[col] = real[col].fillna(real["cit"])
        real[col] = real[col].clip(lower=0, upper=1)

        missing_after = real[col].isna().sum()
        print(
            f"{col}: filled {missing_before - missing_after} missing values; remaining missing {missing_after}"
        )

    fill_cols = ["cit"] + [c for c in corrected_partner_cols if c in real.columns]
    if pair_specific_col in real.columns:
        fill_cols.append(pair_specific_col)

    df.loc[real_mask, fill_cols] = real[fill_cols]

    return df


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

# Drop four counterpart codes outright (this is the ONLY place the pipeline
# excludes any partner rows):
#   ANT_F  Netherlands Antilles  — dissolved 2010, no longer a jurisdiction.
#   BVT    Bouvet Island         — uninhabited dependency, not a real market.
#   STLS   Stateless             — see below.
#   W      World (all partners)  — the reporter's own grand total; keeping it
#                                  would double-count every partner row.
#
# STATELESS ENTITIES (STLS). OECD CbCR reports a separate "Stateless" partner
# row per reporter for sub-entities the parent could not assign to any tax
# jurisdiction. We DROP these rows entirely and do NOT redistribute their
# profit/activity to any country: stateless profit has no real location, so
# there is no geographic basis for reallocating it. Importantly, the OECD flags
# stateless income as a known source of DOUBLE COUNTING with the partner rows
# (the same profit can appear both here and under a named partner), so dropping
# it is part of how we deal with duplicate profits. The misalignment/UT method
# then operates only on profit booked in identifiable jurisdictions.
_drop_codes = ["ANT_F", "BVT", "W", "STLS"]
cbcr = cbcr[~cbcr["COUNTERPART_AREA"].isin(_drop_codes)].copy()

# Correct one empty line for Chile in 2016
cbcr = cbcr[
    ~(
        (cbcr["REF_AREA"] == "CHL")
        & (cbcr["TIME_PERIOD"] == 2016)
        & (cbcr["COUNTERPART_AREA"] == "F")
    )
].copy()

# Drop Romania's 2022 record entirely — it is corrupt at source. The OECD raw
# data reports an impossible 492m employees for Romanian MNEs in 2022 (incl.
# ~105m in the US and ~83m in Israel; vs ~0.98m in 2021), a ~1,600x inflated
# payroll, and collapsed/negative tangible assets and revenues. The whole 2022
# submission is internally inconsistent, so Romania is treated as a non-reporter
# for 2022 (verified against the raw CbCR file; not a pipeline artefact).
cbcr = cbcr[~((cbcr["REF_AREA"] == "ROU") & (cbcr["TIME_PERIOD"] == 2022))].copy()

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


def correct_source_data_artifacts(cbcr):
    """Correct clearly-corrupt source CbCR cells before ETR construction.

    Two list-free, jurisdiction-agnostic time-series fingerprints (detected on the
    comprehensive 'Total (All sub-groups)' grouping, then applied to every grouping
    of the flagged (iso_parent, iso_partner, year) cell):

    (1) UNITS ERROR — profit, income tax AND tangible assets each jump >3x the
        cell's own other-year average while revenue & employees stay in their normal
        range, AND the resulting profit margin > 0.5. The real-activity fields
        (revenue, headcount) are the correctly-filed parts, so profit/tax/assets are
        reset to revenue x the cell's average ratio over its other years. (E.g.
        Indonesia domestic 2018: 97% margin, assets ~4x GDP, tax ~25x normal — every
        other year ~10% margin; the foreign Indonesian cells that year are normal.)

    (2) EVERYTHING INFLATED (hyperinflation / bad FX conversion) — revenue itself is
        corrupt too, so there is no trustworthy field to rescale against. A general
        "revenue >> the cell's own history" rule fires on dozens of legitimate cells
        (new large operations, bad-reporter continent aggregates), so these are NOT
        auto-detected; they are listed explicitly in HYPERINFLATION_CELLS as known
        corrupt-at-source records (cf. the Romania-2022 drop) and interpolated from
        their adjacent years. Currently: Mexico->Venezuela 2020 (Venezuela bolivar
        conversion — every field ~20-400x too big; both neighbours ~$0.1bn).
    """
    # Known hyperinflation / FX-corruption cells (add (parent, partner, year) here).
    HYPERINFLATION_CELLS = [("MEX", "VEN", 2020)]
    PROFIT = "profit_loss_before_income_tax"
    REV = "total_revenues"
    EMP = "n_employees"
    RESCALE_COLS = [
        "profit_loss_before_income_tax", "adjusted_profit_loss_before_income_tax",
        "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year",
        "tangible_assets_except_cash",
    ]
    MONEY_COLS = RESCALE_COLS + [
        "total_revenues", "unrelated_party_revenues", "related_party_revenues",
        "stated_capital",
    ]
    num = {c: pd.to_numeric(cbcr[c], errors="coerce") for c in
           set(MONEY_COLS + [EMP]) if c in cbcr.columns}
    tot_mask = cbcr["grouping"] == "Total (All sub-groups)"
    tot = cbcr[tot_mask].copy()
    for c in num:
        tot[c] = num[c][tot_mask]

    units_cells = []
    for (p, pt), g in tot.groupby(["iso_parent", "iso_partner"]):
        if g["year"].nunique() < 4:
            continue
        g = g.sort_values("year")
        for _, r in g.iterrows():
            o = g[g["year"] != r["year"]]

            def spike(col, k=3.0):
                m = o[col].mean()
                return bool(m > 0 and r[col] > k * m)

            def flat(col, k=2.0):
                m = o[col].mean()
                return bool(m <= 0 or abs(r[col]) <= k * abs(m))

            rev = r[REV]
            margin = (r[PROFIT] / rev) if (pd.notna(rev) and rev > 0) else np.nan
            # units error: income/balance-sheet fields spike, real activity flat
            if (pd.notna(r[PROFIT]) and r[PROFIT] / 1e9 >= 2
                    and spike(PROFIT) and spike("income_tax_paid_on_cash_basis")
                    and spike("tangible_assets_except_cash")
                    and flat(REV) and flat(EMP)
                    and pd.notna(margin) and margin > 0.5):
                units_cells.append((p, pt, int(r["year"])))

    # Hyperinflation cells come from the explicit list, not auto-detection.
    _present = set(zip(cbcr["iso_parent"], cbcr["iso_partner"]))
    inflated_cells = [(p, pt, y) for (p, pt, y) in HYPERINFLATION_CELLS
                      if (p, pt) in _present]

    def cell_grouping_rows(p, pt):
        return (cbcr["iso_parent"] == p) & (cbcr["iso_partner"] == pt)

    for (p, pt, y) in units_cells:
        for grp in cbcr.loc[cell_grouping_rows(p, pt), "grouping"].unique():
            m = cell_grouping_rows(p, pt) & (cbcr["grouping"] == grp)
            sub = cbcr[m]
            yr = pd.to_numeric(sub["year"], errors="coerce")
            if y not in yr.values:
                continue
            others = sub[yr != y]
            rev_o = pd.to_numeric(others[REV], errors="coerce")
            rev_y = pd.to_numeric(sub.loc[yr == y, REV], errors="coerce").iloc[0]
            if not (pd.notna(rev_y) and rev_y != 0):
                continue
            # Only correct a grouping whose OWN value is anomalous (impossible
            # margin > 0.5) — so e.g. the normal 'negative profits' grouping is left
            # untouched while 'Total' and 'positive profits' (both corrupt) are fixed.
            profit_y = pd.to_numeric(sub.loc[yr == y, PROFIT], errors="coerce").iloc[0]
            if not (pd.notna(profit_y) and profit_y / rev_y > 0.5):
                continue
            for col in RESCALE_COLS:
                if col not in cbcr.columns:
                    continue
                ratio = (pd.to_numeric(others[col], errors="coerce") / rev_o)
                ratio = ratio.replace([np.inf, -np.inf], np.nan).mean()
                if pd.notna(ratio):
                    cbcr.loc[m & (pd.to_numeric(cbcr["year"], errors="coerce") == y), col] = rev_y * ratio
        print(f"  [artifact] UNITS-ERROR rescaled {p}->{pt} {y} "
              f"(profit/tax/assets reset to revenue x avg ratio, all groupings)")

    for (p, pt, y) in inflated_cells:
        for grp in cbcr.loc[cell_grouping_rows(p, pt), "grouping"].unique():
            m = cell_grouping_rows(p, pt) & (cbcr["grouping"] == grp)
            sub = cbcr[m]
            yr = pd.to_numeric(sub["year"], errors="coerce")
            if y not in yr.values:
                continue
            for col in MONEY_COLS:
                if col not in cbcr.columns:
                    continue
                nb = [pd.to_numeric(sub.loc[yr == y + d, col], errors="coerce").iloc[0]
                      for d in (-1, 1) if (y + d) in yr.values
                      and len(sub.loc[yr == y + d, col])]
                nb = [v for v in nb if pd.notna(v)]
                if nb:
                    cbcr.loc[m & (pd.to_numeric(cbcr["year"], errors="coerce") == y), col] = float(np.mean(nb))
        print(f"  [artifact] HYPERINFLATION interpolated {p}->{pt} {y} "
              f"(all monetary fields = mean of adjacent years, all groupings)")

    if not units_cells and not inflated_cells:
        print("  [artifact] no corrupt source cells detected")
    return cbcr


print("Source-data artifact correction:")
cbcr = correct_source_data_artifacts(cbcr)

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
#
# Sources:
#
# General corrections:
# Garcia-Bernardo, J. and Janský, P. (2024).
# "Profit shifting of multinational corporations worldwide."
# World Development, 177, 106527.
#
# USA-specific corrections:
# Garcia-Bernardo, J., Janský, P. and Zucman, G. (2026).
# "Did the Tax Cuts and Jobs Act Reduce Profit Shifting by US Multinational Companies?"
#
# Assumptions:
# - 2016 is treated like 2017.
# - From 2020 onwards, no corrections are applied.
# - Italy receives the standard 35% correction.
# - NLD and GBR use OECD-adjusted profits where available and are therefore
#   not separately corrected here.
# - Aggregated country groups receive a 5% correction because they may contain
#   tax havens.

correction_domestic = {
    2016: {"USA": 0.54},
    2017: {"USA": 0.54},
    2018: {"USA": 0.74},
    2019: {"USA": 0.42},
    2020: {},
    2021: {},
    2022: {},
}

correction_foreign = {
    2016: {"USA": 0.07},
    2017: {"USA": 0.07},
    2018: {"USA": 0.39},
    2019: {"USA": 0.28},
    2020: {},
    2021: {},
    2022: {},
}

correction_domestic_other_countries = {
    year: {
        # Domestic ETR substantially below foreign ETR
        "BEL": 0.50,
        "SGP": 0.50,
        "BMU": 0.50,
        # Domestic ETR exceeds foreign ETR
        "LVA": 0.00,
        "SVN": 0.00,
        "LUX": 0.00,
    }
    for year in range(2016, 2020)
}

correction_taxhavens = {
    year: {key: 0.10 for key in tax_havens} for year in range(2016, 2020)
}

# Aggregated country groups may contain tax havens.
# Apply half of the tax haven correction.

correction_countrygroups = {
    year: {key: 0.05 for key in other_country_groups} for year in range(2016, 2020)
}

corrections = {
    "domestic": {},
    "foreign": {},
    "taxhavens": {},
    "countrygroups": {},
}

for year in analysis_years:

    corrections["domestic"][year] = {key: 0 for key in parent_countries.tolist()}

    corrections["foreign"][year] = {key: 0 for key in parent_countries.tolist()}

    corrections["taxhavens"][year] = {key: 0 for key in partner_countries.tolist()}

    corrections["countrygroups"][year] = {key: 0 for key in partner_countries.tolist()}

    # General domestic correction (2016–2019 only)
    if year in range(2016, 2020):
        corrections["domestic"][year].update(
            {key: 0.35 for key in parent_countries.tolist()}
        )

    # Country-specific domestic corrections
    corrections["domestic"][year].update(
        correction_domestic_other_countries.get(year, {})
    )

    # USA-specific domestic corrections
    corrections["domestic"][year].update(correction_domestic.get(year, {}))

    # USA-specific foreign corrections
    corrections["foreign"][year].update(correction_foreign.get(year, {}))

    # Tax haven corrections
    corrections["taxhavens"][year].update(correction_taxhavens.get(year, {}))

    # Country-group corrections
    corrections["countrygroups"][year].update(correction_countrygroups.get(year, {}))

    print(
        f"Applied corrections for year {year} "
        f"(Domestic: {len(corrections['domestic'][year])} countries, "
        f"Foreign: {len(corrections['foreign'][year])}, "
        f"Tax Havens: {len(corrections['taxhavens'][year])}, "
        f"Country Groups: {len(corrections['countrygroups'][year])})"
    )

print(corrections)

# 1.2b Apply profit correction row by row

for year in analysis_years:
    mask = cbcr["year"] == year
    original_values = cbcr.loc[mask, "profit_loss_before_income_tax"].copy()

    adjusted_available = cbcr.loc[
        mask, "adjusted_profit_loss_before_income_tax"
    ].notna()

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

    changed_by_adjusted_profit = (
        adjusted_available
        & corrected_values.notna()
        & original_values.notna()
        & (corrected_values != original_values)
    ).sum()

    changed_by_manual_correction = (
        ~adjusted_available
        & corrected_values.notna()
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
    print(f"Changed via OECD adjusted profits: {changed_by_adjusted_profit}")
    print(f"Changed via manual correction rules: {changed_by_manual_correction}")
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

# Main rolling-window ETRs
etrs = main_etrs(cbcr, grouping_name="Sub-groups with positive profits")

for year in etrs["year"].unique():
    num_partners = etrs[etrs["year"] == year].shape[0]
    print(
        f"Calculated main rolling-window ETRs for year {year} "
        f"(Sub-groups with positive profits). Number of partners: {num_partners}"
    )

# Domestic fallback for reporting countries with no positive-profit subgroup entry
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
        f"Calculated domestic fallback ETRs for year {year} "
        f"(Total - All sub-groups). Number of partners: {num_partners}"
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
    f"Updated {updated_entries} entries for domestic ETRs based on "
    f"'Total (All sub-groups)' data."
)

# Additional rolling-window corrected ETRs
pair_etrs_corrected, partner_etrs_corrected = alternative_corrected_etrs(
    cbcr,
    grouping_name="Sub-groups with positive profits",
)

print(
    "Calculated additional corrected rolling-window ETRs: "
    "pair-specific, median, p25, and minimum."
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

cbcr_etrs = cbcr_etrs.merge(
    partner_etrs_corrected,
    on=["iso_partner", "year"],
    how="left",
)

cbcr_etrs = cbcr_etrs.merge(
    pair_etrs_corrected,
    on=["iso_parent", "iso_partner", "year"],
    how="left",
)

alternative_etr_cols = [
    "etr_parent_partner_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_min_corrected",
]

for col in alternative_etr_cols:
    if col in cbcr_etrs.columns:
        cbcr_etrs[col] = cbcr_etrs[col].clip(lower=0, upper=1)

check_missing_values(
    cbcr_etrs,
    [
        "etr_domestic",
        "etr_foreign",
        "etr_average",
        "etr_average_corrected",
        "etr_parent_partner_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_min_corrected",
    ],
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
    f"Percentage of rows with missing average corrected ETRs before CIT fallback: "
    f"{missing_percentage_average_corrected:.2f}%"
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

# Malta's 5/6 shareholder refund -> effective 1/7 of the headline rate. This is
# a derived (multiplicative) adjustment, so it stays in code; MTQ<-FRA and
# BVT<-NOR above are likewise derived. The flat and fill-if-missing CIT
# overrides (GIB, MCO, AND, CAF, ..., SMR) now live in
# data/raw/manual_imputation_values.csv.
cits.loc[cits["iso_partner"] == "MLT", "cit"] *= 1 / 7
apply_manual_values(cits, MANUAL_VALUES, ["cit"])

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
        "Warning: CIT values are missing for the following iso_partner countries and years "
        "(excluding specified groups) before fallback:"
    )
    for _, row in missing_iso_partners_cit.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing CIT values found before fallback.")

cbcr_etrs_cits = fill_missing_cit_and_corrected_etrs(cbcr_etrs_cits)

missing_cit_rows_after = cbcr_etrs_cits[
    (cbcr_etrs_cits["cit"].isnull())
    & (~cbcr_etrs_cits["iso_partner"].isin(non_countries))
]

if not missing_cit_rows_after.empty:
    missing_iso_partners_cit_after = missing_cit_rows_after[
        ["iso_partner", "year"]
    ].drop_duplicates()
    print(
        "Warning: CIT values are still missing after fallback for the following "
        "iso_partner countries and years:"
    )
    for _, row in missing_iso_partners_cit_after.iterrows():
        print(f"iso_partner: {row['iso_partner']}, year: {row['year']}")
else:
    print("No missing CIT values found after fallback.")

check_missing_values(
    cbcr_etrs_cits,
    [
        "cit",
        "etr_domestic_corrected",
        "etr_foreign_corrected",
        "etr_average_corrected",
        "etr_parent_partner_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_min_corrected",
    ],
)

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

# %%
# 2.3a Manual GDP and population fills.
# Curated values + their source URLs now live in
# data/raw/manual_imputation_values.csv (see load_manual_imputation_values).
# These are fill-if-missing: only small territories absent from WB fill here.
apply_manual_values(gdp_population, MANUAL_VALUES, ["gdp_current_usd", "population"])

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

# %%
# 2.4a Outlier filter on ILO USD observations.
#
# Some ILO survey years are wildly inconsistent with the rest of the
# country's series. Liberia's 2017 LFS reports $1,309/month vs $95-$122 from
# HIES surveys (real Liberian formal-sector wages are ~$100-200). The LFS
# row also lists the "Local currency" value as the same 1,308.61 -- a
# dual-currency artefact where Liberian respondents reported in USD but
# were tagged as "Local currency". Without filtering, the outlier anchors
# the CPI extrapolation and corrupts every subsequent year for that country.
#
# Filter rule: per country, drop observations whose USD value is >3x or
# <1/3x the country's median USD value computed across ALL available ILO
# years (not just panel range), so countries with only 1-2 panel-year
# observations still get a robust median.
if "country_name" in wages.columns or "iso_partner" in wages.columns:
    # Compute the country median from the full ILO USD history (all years)
    if "sex" in wages_fulltable.columns:
        all_usd = wages_fulltable.loc[
            both_sexes & all_occupations & in_usd, ["ref_area", "obs_value"]
        ].rename(columns={"ref_area": "iso_partner", "obs_value": "w"})
    else:
        all_usd = wages_fulltable.loc[
            (wages_fulltable["sex.label"] == "Total")
            & (wages_fulltable["classif1.label"] == "Currency: U.S. dollars"),
            ["ref_area.label", "obs_value"],
        ].rename(columns={"ref_area.label": "country_name", "obs_value": "w"})
        all_usd["iso_partner"] = all_usd["country_name"].map(name_to_iso3)
        all_usd = all_usd.dropna(subset=["iso_partner"])[["iso_partner", "w"]]
    country_med_full = all_usd.groupby("iso_partner")["w"].median()
    country_med = wages["iso_partner"].map(country_med_full)
    outliers = (
        country_med.notna()
        & (country_med > 0)
        & wages["wage_monthly"].notna()
        & (
            (wages["wage_monthly"] > 3.0 * country_med)
            | (wages["wage_monthly"] < (1.0 / 3.0) * country_med)
        )
    )
    if outliers.any():
        n_drops = int(outliers.sum())
        countries_affected = wages.loc[outliers, "iso_partner"].unique().tolist()
        print(
            f"Wage outlier filter dropped {n_drops} observations "
            f"in {len(countries_affected)} countries: {sorted(countries_affected)}"
        )
        wages.loc[outliers, "wage_monthly"] = np.nan
        # Leave rows with wage_monthly=NaN so CPI extrapolation in 2.4a
        # treats them as missing and re-imputes from clean LCY anchors.


# %%
# 2.4b CPI-based extrapolation of ILO observations across missing panel years.
#
# Many countries in the panel (especially LMI/L) have only 1-2 ILO survey
# observations across 2016-2022. Filling missing years with the country mean
# leaves wage_monthly constant across years for those cases, hiding wage
# growth and high-inflation effects. We instead anchor on each country's
# local-currency wage observation(s) from the ILO file, scale the LCY value
# to other panel years using national CPI, and convert to USD using each
# year's exchange rate.
#
#     wage_USD[year] = wage_LCY[obs_year]
#                      × CPI[year] / CPI[obs_year]
#                      / exchange_rate[year]
#
# When multiple LCY observations exist, we anchor on the closest year for
# each target. Countries with no LCY observation skip this step and fall
# through to the OLS-on-GDP-per-capita prediction in 2.4b.

# Pull local-currency wage observations from the same ILO survey rows
if "sex" in wages_fulltable.columns:
    in_lcy = wages_fulltable["classif2"] == "CUR_TYPE_LCU"
    lcy_relevant = (
        both_sexes
        & all_occupations
        & in_lcy
        & (
            (wages_fulltable["time"] >= first_year)
            & (wages_fulltable["time"] <= last_year)
        )
    )
    wages_lcy = wages_fulltable.loc[
        lcy_relevant, ["ref_area", "time", "obs_value"]
    ].rename(
        columns={
            "ref_area": "iso_partner",
            "time": "year",
            "obs_value": "wage_monthly_lcy",
        }
    )
else:
    in_lcy = wages_fulltable["classif1.label"] == "Currency: Local currency"
    lcy_relevant = (
        both_sexes
        & in_lcy
        & (
            (wages_fulltable["time"] >= first_year)
            & (wages_fulltable["time"] <= last_year)
        )
    )
    wages_lcy = wages_fulltable.loc[
        lcy_relevant, ["ref_area.label", "time", "obs_value"]
    ].rename(
        columns={
            "ref_area.label": "country_name",
            "time": "year",
            "obs_value": "wage_monthly_lcy",
        }
    )
    wages_lcy["iso_partner"] = wages_lcy["country_name"].map(name_to_iso3)
    wages_lcy = wages_lcy.dropna(subset=["iso_partner"])
    wages_lcy = wages_lcy[["iso_partner", "year", "wage_monthly_lcy"]]

# Apply the same per-country outlier filter to LCY observations. For
# dual-currency countries (Liberia, Ecuador, Panama), some surveys report
# wages in USD but tag them as "Local currency". Those values are far below
# the proper LCY scale, get caught by the 1/3-median floor, and dropped.
if not wages_lcy.empty:
    lcy_med = wages_lcy.groupby("iso_partner")["wage_monthly_lcy"].transform("median")
    lcy_outliers = (
        lcy_med.notna()
        & (lcy_med > 0)
        & wages_lcy["wage_monthly_lcy"].notna()
        & (
            (wages_lcy["wage_monthly_lcy"] > 3.0 * lcy_med)
            | (wages_lcy["wage_monthly_lcy"] < (1.0 / 3.0) * lcy_med)
        )
    )
    if lcy_outliers.any():
        print(
            f"LCY-side outlier filter dropped {int(lcy_outliers.sum())} "
            f"ILO LCY observations (countries: "
            f"{sorted(wages_lcy.loc[lcy_outliers, 'iso_partner'].unique().tolist())})"
        )
        wages_lcy = wages_lcy[~lcy_outliers].reset_index(drop=True)


def _load_wb_long(path, value_name):
    """WB WDI CSVs have header rows + wide format with 1960..2025 columns."""
    df = pd.read_csv(path, skiprows=4)
    year_cols = [c for c in df.columns if str(c).isdigit()]
    long = df.melt(
        id_vars=["Country Code"],
        value_vars=year_cols,
        var_name="year",
        value_name=value_name,
    )
    long["year"] = long["year"].astype(int)
    long = long.rename(columns={"Country Code": "iso_partner"})
    return long[["iso_partner", "year", value_name]].dropna(subset=[value_name])


cpi_long = _load_wb_long(cpi_data, "cpi")
fx_long = _load_wb_long(exchange_rates_wb, "fx_lcu_per_usd")

# For each (iso_partner, target_year) needing a wage, find the nearest LCY
# observation, scale by CPI, divide by FX to get USD.
sample_target = (
    wages[wages["wage_monthly"].isna()][["iso_partner", "year"]]
    .drop_duplicates()
    .reset_index(drop=True)
)


def _extrapolate_one(iso, target_year):
    obs = wages_lcy[wages_lcy["iso_partner"] == iso]
    if obs.empty:
        return np.nan
    # Pick the closest observation year
    obs = obs.assign(distance=(obs["year"] - target_year).abs())
    nearest = obs.loc[obs["distance"].idxmin()]
    obs_year = int(nearest["year"])
    lcy_obs = float(nearest["wage_monthly_lcy"])

    cpi_target = cpi_long[
        (cpi_long["iso_partner"] == iso) & (cpi_long["year"] == target_year)
    ]
    cpi_obs = cpi_long[
        (cpi_long["iso_partner"] == iso) & (cpi_long["year"] == obs_year)
    ]
    fx_target = fx_long[
        (fx_long["iso_partner"] == iso) & (fx_long["year"] == target_year)
    ]
    if cpi_target.empty or cpi_obs.empty or fx_target.empty:
        return np.nan
    cpi_t = float(cpi_target.iloc[0]["cpi"])
    cpi_o = float(cpi_obs.iloc[0]["cpi"])
    fx_t = float(fx_target.iloc[0]["fx_lcu_per_usd"])
    if cpi_o <= 0 or fx_t <= 0:
        return np.nan
    return lcy_obs * (cpi_t / cpi_o) / fx_t


sample_target["wage_extrapolated"] = sample_target.apply(
    lambda r: _extrapolate_one(r["iso_partner"], int(r["year"])), axis=1
)

# Plausibility check on extrapolated values. The CPI/FX extrapolation
# silently fails for countries with currency redenominations between the
# ILO observation year and panel range -- e.g. Sierra Leone redenominated
# 1:1000 in 2022, so an ILO observation in old leones combined with WB FX
# in new leones produces a wage 1000x too high. Without country-by-country
# overrides we can't detect the redenomination directly, but we can detect
# implausible USD outputs by comparing to GDP per capita: a monthly wage
# can't reasonably exceed annual GDP per capita.
#
# Filter rule: extrapolated wage > (GDP per capita) / 12 × 5  →  reject.
# That allows up to 5x GDP/capita as the cap (very generous; most countries'
# average wage falls far below GDP/capita on a monthly basis).

# Pull GDP per capita for the plausibility check
gdp_pc = cbcr_etrs_cits_gdp.drop_duplicates(["iso_partner", "year"])[
    ["iso_partner", "year", "gdp_current_usd", "population"]
].copy()
gdp_pc["gdp_per_capita"] = gdp_pc["gdp_current_usd"] / gdp_pc["population"]
sample_target = sample_target.merge(
    gdp_pc[["iso_partner", "year", "gdp_per_capita"]],
    on=["iso_partner", "year"],
    how="left",
)
# Two-sided check:
#  (a) Upper: extrapolated wage > 5x monthly GDP/capita → likely
#      redenomination (SLE, BDI, etc.)
#  (b) Lower: country has ILO USD observations and extrapolated wage is
#      <1/5 of the country's median ILO USD wage → likely LCY-unit issue
#      (Iceland's "Local currency" values are in unusual units)
country_usd_median_map = (
    all_usd.groupby("iso_partner")["w"].median() if "all_usd" in dir() else None
)
sample_target["country_usd_median"] = (
    sample_target["iso_partner"].map(country_usd_median_map)
    if country_usd_median_map is not None
    else np.nan
)
implausible_high = (
    sample_target["wage_extrapolated"].notna()
    & sample_target["gdp_per_capita"].notna()
    & (sample_target["gdp_per_capita"] > 0)
    & (
        sample_target["wage_extrapolated"]
        > 5.0 * sample_target["gdp_per_capita"] / 12.0
    )
)
implausible_low = (
    sample_target["wage_extrapolated"].notna()
    & sample_target["country_usd_median"].notna()
    & (sample_target["country_usd_median"] > 0)
    & (sample_target["wage_extrapolated"] < 0.2 * sample_target["country_usd_median"])
)
implausible = implausible_high | implausible_low
if implausible.any():
    rejected_iso = sample_target.loc[implausible, "iso_partner"].unique().tolist()
    n_high = int(implausible_high.sum())
    n_low = int(implausible_low.sum())
    print(
        f"Rejected {int(implausible.sum())} extrapolated wages "
        f"({n_high} too high vs GDP/cap, {n_low} too low vs ILO USD median). "
        f"Likely currency redenomination or LCY-unit mismatch. "
        f"Countries: {sorted(rejected_iso)}"
    )
    sample_target.loc[implausible, "wage_extrapolated"] = np.nan
sample_target = sample_target.drop(columns=["gdp_per_capita", "country_usd_median"])

# Merge extrapolated values into wages
wages = wages.merge(
    sample_target.rename(columns={"wage_extrapolated": "_w_extrap"}),
    on=["iso_partner", "year"],
    how="left",
)
mask_fill = wages["wage_monthly"].isna() & wages["_w_extrap"].notna()
wages.loc[mask_fill, "wage_monthly"] = wages.loc[mask_fill, "_w_extrap"]
n_extrap = int(mask_fill.sum())
n_extrap_countries = wages.loc[mask_fill, "iso_partner"].nunique()
print(
    f"CPI-extrapolated wages: {n_extrap} (iso, year) cells across "
    f"{n_extrap_countries} countries."
)
wages = wages.drop(columns=["_w_extrap"])

# Final fall-back to country mean for any remaining gaps (e.g. countries with
# no LCY observation OR no CPI / FX coverage). The OLS imputation in 2.4b
# kicks in for any rows still NaN here.
avg_wage = wages.groupby("iso_partner")["wage_monthly"].transform("mean")
wages["wage_monthly"] = wages["wage_monthly"].fillna(avg_wage)

# Hand-collected monthly wages for small territories missing from ILO. These
# are unconditional overrides; the values + sources live in
# data/raw/manual_imputation_values.csv (see load_manual_imputation_values).
apply_manual_values(wages, MANUAL_VALUES, ["wage_monthly"])

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
# 2.4c Impute wages using GDP and population

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

wb_income_base = pd.DataFrame(
    [
        {
            "iso_partner": c["id"],
            "wb_income_group_official": c["incomeLevel"]["value"],
            "wb_income_group_id_official": c["incomeLevel"]["id"],
        }
        for c in wb_raw
        if c.get("region", {}).get("value") != "Aggregates"
        and c.get("id") is not None
        and len(c.get("id")) == 3
    ]
)

if wb_income_base.empty:
    wb_income_base = pd.DataFrame(
        columns=[
            "iso_partner",
            "wb_income_group_official",
            "wb_income_group_id_official",
        ]
    )
else:
    wb_income_base["wb_income_group_official"] = wb_income_base[
        "wb_income_group_official"
    ].replace(
        {
            "Low income": "low_income",
            "Lower middle income": "lower_middle_income",
            "Upper middle income": "upper_middle_income",
            "High income": "high_income",
            "Not classified": pd.NA,
            "": pd.NA,
        }
    )
    wb_income_base["wb_income_group_id_official"] = wb_income_base[
        "wb_income_group_id_official"
    ].replace({"": pd.NA})

# Expand to country-year
wb_income = pd.DataFrame(
    sample_jur_year, columns=["iso_partner", "year"]
).drop_duplicates()

wb_income = wb_income.merge(
    wb_income_base,
    on="iso_partner",
    how="left",
)

# Start custom analytical income group from official WB group
wb_income["wb_income_group"] = wb_income["wb_income_group_official"]
wb_income["wb_income_group_id"] = wb_income["wb_income_group_id_official"]

# -------------------------------------------------
# 1. Overwrite investment hubs consistently
# -------------------------------------------------
# The "investment_hub" income group is the REPRESENTATION haven list from
# config: TAX_HAVENS_REPRESENTATION = the GB cleaning core ∪ (CTHI-2024 Haven
# Score > 65 AND net profit-shifting recipient in our results) ∪ Saudi Arabia
# (manual: no CTHI score, FSI 69). Edit the list in config.py, not here.
investment_hub_codes = sorted(TAX_HAVENS_REPRESENTATION)

wb_income.loc[
    wb_income["iso_partner"].isin(investment_hub_codes),
    ["wb_income_group", "wb_income_group_id"],
] = ["investment_hub", "HUB"]

# -------------------------------------------------
# 2. Manual fills for countries / territories not covered well by WB
# -------------------------------------------------
manual_income_map = {
    # Countries you flagged earlier
    "ETH": ("low_income", "LIC"),
    "VEN": ("upper_middle_income", "UMC"),
    # Missing country-years from your check
    "TWN": ("high_income", "HIC"),
    "XKV": ("lower_middle_income", "LMC"),
    # French overseas departments / territories in your data
    "GLP": ("high_income", "HIC"),
    "GUF": ("high_income", "HIC"),
    "MTQ": ("high_income", "HIC"),
    "REU": ("high_income", "HIC"),
    "WLF": ("high_income", "HIC"),
    # Other territories in your missing list
    "FLK": ("high_income", "HIC"),
}

for iso, (group, group_id) in manual_income_map.items():
    wb_income.loc[wb_income["iso_partner"] == iso, "wb_income_group"] = group
    wb_income.loc[wb_income["iso_partner"] == iso, "wb_income_group_id"] = group_id

# Optional 3-group version plus investment hubs
wb_income["wb_income_group_3"] = wb_income["wb_income_group"].replace(
    {
        "low_income": "low_income",
        "lower_middle_income": "middle_income",
        "upper_middle_income": "middle_income",
        "high_income": "high_income",
        "investment_hub": "investment_hub",
    }
)

# Final check: remaining missing values among real countries only
remaining_missing_wb = wb_income[
    (~wb_income["iso_partner"].isin(non_countries))
    & (wb_income["wb_income_group"].isna())
][["iso_partner", "year"]].drop_duplicates()

if not remaining_missing_wb.empty:
    print("Warning: wb_income_group still missing for:")
    print(
        remaining_missing_wb.sort_values(["iso_partner", "year"]).to_string(index=False)
    )
else:
    print("No missing wb_income_group values remain.")

print(
    wb_income.loc[
        wb_income["iso_partner"].isin(
            [
                "ETH",
                "VEN",
                "AIA",
                "COK",
                "GGY",
                "GLP",
                "GUF",
                "IOT",
                "JEY",
                "REU",
                "TWN",
                "WLF",
                "XKV",
                "MTQ",
                "FLK",
            ]
        ),
        [
            "iso_partner",
            "year",
            "wb_income_group",
            "wb_income_group_id",
            "wb_income_group_3",
        ],
    ]
    .drop_duplicates()
    .sort_values(["iso_partner", "year"])
    .to_string(index=False)
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
    on=["iso_partner", "year"],
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

# %%
# The manually-collected values for the small territories hand-filled above
# (GDP / population / wages for San Marino, the French overseas departments,
# Taiwan, the Pacific islands, the Channel Islands, etc.) and the flat CIT
# overrides are NOT stored as columns in the dataset. They live — values AND
# their source URLs together — in a single hand-maintained reference:
#   - data/raw/manual_imputation_values.csv    (iso_partner, year, variable,
#                                                value, mode, source_url, note)
#   - docs/manual_macro_imputation_sources.md  (human-readable overview)
# Edit that CSV to add or revise a value or its source; the script consumes it
# via load_manual_imputation_values() / apply_manual_values().

cbcr_main_allsubgroupsonly = cbcr_main[
    cbcr_main["grouping"] == "Total (All sub-groups)"
].copy()
cbcr_main_allsubgroupsonly.drop(columns=["grouping"], inplace=True)

# %%
# 3.1 Save outputs (canonical column order from _column_order.py)
from _column_order import COLUMNS_STAGE_1, apply_canonical_order

cbcr_main = apply_canonical_order(cbcr_main, COLUMNS_STAGE_1)
cbcr_main_allsubgroupsonly = apply_canonical_order(
    cbcr_main_allsubgroupsonly, COLUMNS_STAGE_1
)

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

check_missing_values(
    cbcr_main_allsubgroupsonly,
    [
        "cit",
        "etr_domestic_corrected",
        "etr_foreign_corrected",
        "etr_average_corrected",
        "etr_parent_partner_corrected",
        "etr_partner_median_corrected",
        "etr_partner_p25_corrected",
        "etr_partner_min_corrected",
    ],
)

print(cbcr_main_allsubgroupsonly.columns.tolist())
