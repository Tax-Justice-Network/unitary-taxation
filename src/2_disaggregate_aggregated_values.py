# %% [markdown]
# Disaggregate aggregated CbCR rows
#
# This script produces a row-level dataset of disaggregated CbCR partner rows.
# It does NOT yet run the misalignment calculation.
#
# Rules:
# - `_O` codes (`E_O`, `A_O`, `F_O`, `S_O`) are treated as residual continent aggregates
# - Single-letter codes (`E`, `A`, `F`, `S`) are checked first as possible continent totals
#   that may just be redundant summary lines
# - If a continent total comes together with individual country rows and/or the
#   corresponding `_O` row, the script checks whether the total is simply equal to
#   (all reported country rows in that continent + corresponding `_O`)
# - If yes, that continent total row is dropped before disaggregation because it is
#   only a redundant summary line
# - If both a single-letter code and the corresponding `_O` code exist but do not
#   add up consistently, that reporter-year is flagged and excluded from weight
#   computation
# - After this cleaning step, retained single-letter codes are treated like residual
#   continent values in the distribution step
# - `W_O` is treated as a global foreign residual
# - `WXD` is treated as total non-domestic activity:
#   after subtracting already covered foreign country rows and distributed residuals,
#   any remaining `WXD` residual is distributed to still-unreported foreign countries;
#   if no uncovered countries remain, that residual is distributed across foreign
#   countries without a true reported country row, including countries that may
#   already have received continent residual imputations
#
# Distribution weights come from good reporters' granular foreign data.
# Aggregate values, including negative values, are distributed proportionally whenever
# positive weights exist. If all weights for a variable are zero, values are split equally.
# Negative foreign totals used as weights are set to zero before weighting.
#
# WXD diagnostics are computed before any clipping of negative distributed values.
# After those diagnostics, negative distributed values are clipped to zero for
# non-profit and non-tax variables only. Profit and tax variables may remain negative.
#
# The final output contains country rows only.

# %%
import pandas as pd
import numpy as np
from config import *

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format

# Load full CbCR data early so it can be used to build reference tables
cbcr_full = pd.read_csv(f"{data_final}/cbcr_main_allsubgroupsonly.csv")
years = sorted(cbcr_full["year"].dropna().unique())

print(f"Loaded {len(cbcr_full)} rows")
print(f"Years: {years}")


# %% [markdown]
# 1. Constants and rules

# %%
CBCR_VARS = [
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

METADATA_COLS = [
    "partner_jurisdiction",
    "etr_average_corrected",
    "cit",
    "tax_revenue_current_usd",
    "gvt_health_expenditure",
    "region_tjn",
    "wb_income_group",
    "ukt",
    "oecd",
    "oecd_oct",
    "nld_oct",
    "wage_monthly",
]

STATIC_METADATA_COLS = [
    "partner_jurisdiction",
    "region_tjn",
    "wb_income_group",
    "ukt",
    "oecd",
    "oecd_oct",
    "nld_oct",
]

YEARLY_METADATA_COLS = [
    "etr_average_corrected",
    "cit",
    "tax_revenue_current_usd",
    "gvt_health_expenditure",
    "wage_monthly",
]

CONTINENT_CODES = {
    "E_O": "Europe",
    "E": "Europe",
    "A_O": "Americas",
    "A": "Americas",
    "F_O": "Africa",
    "F": "Africa",
    "S_O": "Asia_Oceania",
    "S": "Asia_Oceania",
}

CONTINENT_TO_SINGLE = {
    "Europe": "E",
    "Americas": "A",
    "Africa": "F",
    "Asia_Oceania": "S",
}

CONTINENT_TO_RESIDUAL = {
    "Europe": "E_O",
    "Americas": "A_O",
    "Africa": "F_O",
    "Asia_Oceania": "S_O",
}

EXCLUSION_CONDITIONS = [
    ("AUT", 2016, 2022),  # Austria: only continents
    ("BHR", 2022, 2022),  # Bahrain: continents only (new in 2022)
    ("CAN", 2022, 2022),  # Canada: few granular partners, heavily aggregated
    ("COL", 2022, 2022),  # Colombia: too few granular partners
    ("CZE", 2019, 2022),  # Czechia: only domestic vs ROW
    ("FIN", 2016, 2022),  # Finland: only continents
    ("GRC", 2017, 2019),  # Greece
    ("GBR", 2017, 2022),  # UK: only continents
    ("HUN", 2018, 2022),  # Hungary: only domestic vs ROW
    ("IMN", 2017, 2020),  # Isle of Man
    ("IRL", 2016, 2022),  # Ireland: only continents
    ("KOR", 2016, 2022),  # Korea: only continents
    ("MAC", 2019, 2021),  # Macau (improved in 2022)
    ("MAR", 2021, 2022),  # Morocco: only domestic vs ROW
    ("MUS", 2019, 2022),  # Mauritius: continents only
    ("NLD", 2016, 2017),  # Netherlands (2016-2017 only)
    ("NLD", 2022, 2022),  # Netherlands: few granular partners in 2022
    ("NOR", 2016, 2017),  # Norway
    ("NZL", 2018, 2022),  # New Zealand: only domestic vs ROW
    ("POL", 2019, 2021),  # Poland (improved in 2022)
    ("SWE", 2016, 2022),  # Sweden: only continents
    ("UKR", 2022, 2022),  # Ukraine: only WXD (new in 2022)
]

METADATA_DTYPES = {
    "partner_jurisdiction": "string",
    "etr_average_corrected": "Float64",
    "cit": "Float64",
    "tax_revenue_current_usd": "Float64",
    "gvt_health_expenditure": "Float64",
    "wage_monthly": "Float64",
    "region_tjn": "string",
    "wb_income_group": "string",
    "ukt": "Float64",
    "oecd": "Float64",
    "oecd_oct": "Float64",
    "nld_oct": "Float64",
}

# Variables for which negative WXD residuals should trigger a warning if materially negative
WXD_WARNING_VARS = [
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_entities",
]

# Small negative residuals are ignored for warning purposes
WXD_WARNING_ATOL = 1e-3

# Variables that should never remain negative on distributed rows
# Profit and tax variables are intentionally excluded.
NONNEGATIVE_DISTRIBUTED_VARS = [
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
    "stated_capital",
    "total_revenues",
    "related_party_revenues",
    "holding_or_managing_ip",
    "n_entities",
]


# %% [markdown]
# 2. Lookup data


# %%
def first_non_null(series):
    non_null = series.dropna()
    return non_null.iloc[0] if not non_null.empty else pd.NA


partner_rows = cbcr_full.loc[
    ~cbcr_full["iso_partner"].isin(non_countries),
    ["iso_partner", "year"] + STATIC_METADATA_COLS + YEARLY_METADATA_COLS,
].copy()

partner_static = (
    partner_rows.groupby("iso_partner", as_index=False)[STATIC_METADATA_COLS]
    .agg(first_non_null)
    .copy()
)

partner_yearly = (
    partner_rows.groupby(["iso_partner", "year"], as_index=False)[YEARLY_METADATA_COLS]
    .agg(first_non_null)
    .copy()
)

for col in STATIC_METADATA_COLS:
    try:
        partner_static[col] = partner_static[col].astype(METADATA_DTYPES[col])
    except Exception:
        pass

for col in YEARLY_METADATA_COLS:
    try:
        partner_yearly[col] = partner_yearly[col].astype(METADATA_DTYPES[col])
    except Exception:
        pass

continent_mapping = {
    "Europe": set(
        partner_static.loc[partner_static["region_tjn"] == "Europe", "iso_partner"]
    ),
    "Americas": set(
        partner_static.loc[
            partner_static["region_tjn"].isin(
                ["Latin America", "Northern America", "Caribbean/American isl."]
            ),
            "iso_partner",
        ]
    ),
    "Africa": set(
        partner_static.loc[partner_static["region_tjn"] == "Africa", "iso_partner"]
    ),
    "Asia_Oceania": set(
        partner_static.loc[
            partner_static["region_tjn"].isin(["Asia", "Oceania"]),
            "iso_partner",
        ]
    ),
}

for name, countries in continent_mapping.items():
    print(f"{name}: {len(countries)} countries")


# %% [markdown]
# 3. Helper functions


# %%
def get_excluded_parents_for_year(year):
    return {iso for iso, start, end in EXCLUSION_CONDITIONS if start <= year <= end}


def build_partner_metadata_lookup(cbcr_year, year, partner_static, partner_yearly):
    """
    Build a partner-level metadata lookup.

    Priority:
    1. Metadata observed in the current cbcr_year country rows
    2. Fallback metadata from the partner_yearly dataframe, where available
    3. Fallback metadata from the partner_static dataframe, where available
    """
    reported_lookup = (
        cbcr_year[~cbcr_year["iso_partner"].isin(non_countries)]
        .drop_duplicates(subset=["iso_partner"])
        .set_index("iso_partner")
    )

    static_lookup = partner_static.set_index("iso_partner")
    yearly_lookup = (
        partner_yearly.loc[partner_yearly["year"] == year]
        .drop(columns="year")
        .set_index("iso_partner")
    )

    all_partners = sorted(
        set(reported_lookup.index)
        .union(set(static_lookup.index))
        .union(set(yearly_lookup.index))
    )
    metadata_lookup = pd.DataFrame(index=all_partners)

    for col in METADATA_COLS:
        dtype = METADATA_DTYPES[col]
        metadata_lookup[col] = pd.Series(
            pd.NA, index=metadata_lookup.index, dtype=dtype
        )

        if col in static_lookup.columns:
            static_series = static_lookup[col].copy()
            try:
                static_series = static_series.astype(dtype)
            except Exception:
                pass
            metadata_lookup.loc[static_series.index, col] = static_series

        if col in yearly_lookup.columns:
            yearly_series = yearly_lookup[col].copy()
            try:
                yearly_series = yearly_series.astype(dtype)
            except Exception:
                pass
            metadata_lookup.loc[yearly_series.index, col] = yearly_series

        if col in reported_lookup.columns:
            reported_series = reported_lookup[col].copy()
            try:
                reported_series = reported_series.astype(dtype)
            except Exception:
                pass
            metadata_lookup.loc[reported_series.index, col] = reported_series

    return metadata_lookup


def get_aggregate_row(parent_data, code):
    rows = parent_data[parent_data["iso_partner"] == code]
    if rows.empty:
        return None
    return rows.iloc[0]


def series_allclose(left, right, vars_to_check, rtol=1e-6, atol=1e-3):
    """
    Compare two Series across vars_to_check.
    Missing on both sides is ignored.
    Returns True only if all comparable variables are close and at least one
    variable was actually compared.
    """
    compared_any = False

    for var in vars_to_check:
        lval = left.get(var, pd.NA)
        rval = right.get(var, pd.NA)

        if pd.isna(lval) and pd.isna(rval):
            continue

        if pd.isna(lval) != pd.isna(rval):
            return False

        compared_any = True
        if not np.isclose(float(lval), float(rval), rtol=rtol, atol=atol):
            return False

    return compared_any


def has_nonzero_values(values_dict, atol=1e-12):
    for val in values_dict.values():
        if pd.notna(val) and abs(float(val)) > atol:
            return True
    return False


def drop_redundant_continent_totals(cbcr_year, continent_mapping):
    """
    For each reporter-year, check whether a single-letter continent total
    (A/E/F/S) is only a redundant summary line.

    The check is:
    continent total == all reported country rows in that continent + corresponding _O

    This includes the domestic row automatically when the continent is the
    reporter's own continent.

    If yes, drop the single-letter continent total before disaggregation.

    If both the single-letter row and the _O row exist but do not add up
    consistently, flag the reporter-year.
    """
    df = cbcr_year.copy()

    group_cols = ["iso_parent"]
    if "year" in df.columns:
        group_cols.append("year")

    grouped_indices = df.groupby(group_cols, sort=False).groups

    rows_to_drop = []
    audit_rows = []
    flagged_rows = []

    for group_key, idx in grouped_indices.items():
        idx = list(idx)
        parent_data = df.loc[idx]

        if isinstance(group_key, tuple):
            group_info = {col: group_key[i] for i, col in enumerate(group_cols)}
        else:
            group_info = {group_cols[0]: group_key}

        for continent_name in continent_mapping.keys():
            single_code = CONTINENT_TO_SINGLE[continent_name]
            residual_code = CONTINENT_TO_RESIDUAL[continent_name]

            single_rows = parent_data[parent_data["iso_partner"] == single_code]
            residual_rows = parent_data[parent_data["iso_partner"] == residual_code]
            residual_row = get_aggregate_row(parent_data, residual_code)

            if single_rows.empty:
                continue

            single_values_dict = single_rows.iloc[0][CBCR_VARS].to_dict()
            single_row_is_empty = not has_nonzero_values(single_values_dict)

            if single_row_is_empty:
                rows_to_drop.extend(single_rows.index.tolist())

                audit_rows.append(
                    {
                        **group_info,
                        "continent": continent_name,
                        "single_code": single_code,
                        "residual_code": residual_code,
                        "has_single_row": True,
                        "n_single_rows": int(len(single_rows)),
                        "single_row_is_empty": True,
                        "has_reported_country_rows": False,
                        "n_reported_country_rows_in_continent": 0,
                        "has_residual_row": not residual_rows.empty,
                        "matches_reported_plus_residual": False,
                        "dropped_redundant_total": False,
                        "flagged_inconsistent_total_with_residual": False,
                        "dropped_empty_single_total": True,
                    }
                )
                continue

            continent_countries = continent_mapping[continent_name]
            reported_country_rows = parent_data[
                parent_data["iso_partner"].isin(continent_countries)
            ]
            reported_sum = reported_country_rows[CBCR_VARS].sum()

            has_reported_country_rows = not reported_country_rows.empty
            has_residual_row = residual_row is not None

            single_values = single_rows.iloc[0][CBCR_VARS]
            comparison_sum = reported_sum.copy()

            if has_residual_row:
                comparison_sum = comparison_sum.add(
                    residual_row[CBCR_VARS], fill_value=0
                )

            matches_components = False
            dropped_redundant_total = False
            flagged_inconsistent_total = False

            if has_reported_country_rows or has_residual_row:
                matches_components = series_allclose(
                    single_values, comparison_sum, CBCR_VARS
                )

                if matches_components:
                    rows_to_drop.extend(single_rows.index.tolist())
                    dropped_redundant_total = True
                elif has_residual_row:
                    flagged_inconsistent_total = True
                    flagged_rows.append(
                        {
                            **group_info,
                            "continent": continent_name,
                            "single_code": single_code,
                            "residual_code": residual_code,
                            "issue": "single_total_not_equal_to_reported_countries_plus_residual",
                        }
                    )

            audit_rows.append(
                {
                    **group_info,
                    "continent": continent_name,
                    "single_code": single_code,
                    "residual_code": residual_code,
                    "has_single_row": True,
                    "n_single_rows": int(len(single_rows)),
                    "single_row_is_empty": False,
                    "has_reported_country_rows": has_reported_country_rows,
                    "n_reported_country_rows_in_continent": int(
                        len(reported_country_rows)
                    ),
                    "has_residual_row": has_residual_row,
                    "matches_reported_plus_residual": matches_components,
                    "dropped_redundant_total": dropped_redundant_total,
                    "flagged_inconsistent_total_with_residual": flagged_inconsistent_total,
                    "dropped_empty_single_total": False,
                }
            )

    if rows_to_drop:
        df = df.drop(index=rows_to_drop).copy()

    audit_df = pd.DataFrame(audit_rows)
    flagged_df = pd.DataFrame(flagged_rows)

    return df, audit_df, flagged_df


# %% [markdown]
# 4. Core distribution functions


# %%
def compute_distribution_foreign(cbcr_year, excluded_parents, continent_mapping):
    """
    Compute per-variable foreign totals from good reporters for later distribution.
    These totals are used as weights and are only turned into shares after restricting
    to the eligible recipient set.

    Negative totals are clipped to zero for weighting purposes.
    """
    good_foreign = cbcr_year[
        (~cbcr_year["iso_parent"].isin(excluded_parents))
        & (~cbcr_year["iso_partner"].isin(non_countries))
        & (cbcr_year["iso_partner"] != cbcr_year["iso_parent"])
    ]

    global_foreign_total = (
        good_foreign.groupby("iso_partner")[CBCR_VARS].sum().clip(lower=0)
    )

    continent_foreign_total = {}
    for continent_name, countries in continent_mapping.items():
        cont_data = good_foreign[good_foreign["iso_partner"].isin(countries)]
        if cont_data.empty:
            continent_foreign_total[continent_name] = pd.DataFrame(columns=CBCR_VARS)
        else:
            continent_foreign_total[continent_name] = (
                cont_data.groupby("iso_partner")[CBCR_VARS].sum().clip(lower=0)
            )

    return continent_foreign_total, global_foreign_total


def distribute_aggregates_per_reporter(
    parent_data,
    iso_parent,
    continent_mapping,
    continent_foreign_total,
    global_foreign_total,
):
    """
    For a single reporter, keep country-level rows and distribute aggregated rows.

    Logic:
    1. Keep all individually reported country rows as-is
    2. _O codes -> distribute residual continent values to unreported foreign countries
    3. Single-letter codes -> also treat as residual continent values and distribute
       them to unreported foreign countries in that continent
    4. W_O -> first distribute to still-uncovered foreign countries; if none are
       left, distribute only across already imputed foreign rows
    5. WXD -> compute the residual part of WXD after deducting all already covered
       non-domestic rows, variable by variable
         - first distribute it to still-uncovered foreign countries
         - only if there are none, distribute it across all foreign countries for
           which the parent does NOT report a true country row, including countries
           that may already have received continent residual imputations

    Aggregate values, including negative values, are distributed proportionally
    whenever positive weights exist. If all weights are zero, values are split equally.

    WXD diagnostics are evaluated before clipping negative distributed values to zero
    for non-profit and non-tax variables.

    Final output contains country rows only.
    Metadata is merged later, so this function only keeps identifier columns
    and CBCR value columns.
    """
    year = parent_data["year"].iloc[0] if "year" in parent_data.columns else pd.NA

    base_cols = [
        c
        for c in ["year", "iso_parent", "iso_partner"] + CBCR_VARS
        if c in parent_data.columns
    ]

    country_rows = parent_data.loc[
        ~parent_data["iso_partner"].isin(non_countries),
        base_cols,
    ].copy()

    country_rows["is_distributed"] = 0
    country_rows["distribution_source"] = "reported_country"
    country_rows["source_aggregate_code"] = pd.NA

    true_reported_foreign_partners = set(
        country_rows.loc[country_rows["iso_partner"] != iso_parent, "iso_partner"]
    )
    covered_foreign_partners = set(true_reported_foreign_partners)

    distributed_rows = []
    continents_processed = set()
    negative_wxd_warning_rows = []
    clipping_rows = []

    def allocate_across_partners(
        agg_values,
        eligible_partners,
        foreign_total,
        iso_parent,
        year,
        distribution_source,
        source_code,
    ):
        relevant = foreign_total[foreign_total.index.isin(eligible_partners)].copy()
        if relevant.empty:
            return []

        relevant = relevant.clip(lower=0)
        partner_list = list(relevant.index)
        n_partners = len(partner_list)
        denominators = relevant.sum()

        new_rows = []
        for iso_partner_target in partner_list:
            new_rows.append(
                {
                    "iso_parent": iso_parent,
                    "iso_partner": iso_partner_target,
                    "year": year,
                    "is_distributed": 1,
                    "distribution_source": distribution_source,
                    "source_aggregate_code": source_code,
                }
            )

        for var in CBCR_VARS:
            agg_val = agg_values.get(var, 0)

            if pd.isna(agg_val):
                for row in new_rows:
                    row[var] = 0
                continue

            agg_val = float(agg_val)

            if n_partners == 1:
                new_rows[0][var] = agg_val
                continue

            # Use proportional distribution for both positive and negative aggregates
            # whenever positive weights exist
            if denominators[var] > 0:
                running_sum = 0.0

                for i, iso_partner_target in enumerate(partner_list[:-1]):
                    value = (
                        agg_val
                        * relevant.loc[iso_partner_target, var]
                        / denominators[var]
                    )
                    new_rows[i][var] = value
                    running_sum += value

                new_rows[-1][var] = agg_val - running_sum
                continue

            # Fallback: if all weights are zero, split equally
            base_value = agg_val / n_partners
            running_sum = 0.0

            for i in range(n_partners - 1):
                new_rows[i][var] = base_value
                running_sum += base_value

            new_rows[-1][var] = agg_val - running_sum

        return new_rows

    # Step 1: residual continent codes (_O)
    for code in ["E_O", "A_O", "F_O", "S_O"]:
        agg_row = parent_data[parent_data["iso_partner"] == code]
        if agg_row.empty:
            continue

        continent_name = CONTINENT_CODES[code]
        continents_processed.add(continent_name)

        eligible_partners = (
            continent_mapping[continent_name] - covered_foreign_partners - {iso_parent}
        )
        if not eligible_partners:
            continue

        foreign_total = continent_foreign_total.get(
            continent_name, pd.DataFrame(columns=CBCR_VARS)
        )
        if foreign_total.empty:
            continue

        agg_values = agg_row.iloc[0][CBCR_VARS].to_dict()
        if not has_nonzero_values(agg_values):
            continue

        new_rows = allocate_across_partners(
            agg_values=agg_values,
            eligible_partners=eligible_partners,
            foreign_total=foreign_total,
            iso_parent=iso_parent,
            year=year,
            distribution_source="continent_residual",
            source_code=code,
        )
        distributed_rows.extend(new_rows)
        covered_foreign_partners.update([row["iso_partner"] for row in new_rows])

    # Step 2: single-letter continent codes, also treated as residual values
    # Reason: these codes may either represent a residual part of a continent or
    # the full continent total when no country rows from that continent are reported.
    # Treating them as residual values works in both cases: it distributes only the
    # uncovered part when country rows exist, and the full continent total otherwise.
    for code in ["E", "A", "F", "S"]:
        continent_name = CONTINENT_CODES[code]
        if continent_name in continents_processed:
            continue

        agg_row = parent_data[parent_data["iso_partner"] == code]
        if agg_row.empty:
            continue

        continents_processed.add(continent_name)

        eligible_partners = (
            continent_mapping[continent_name] - covered_foreign_partners - {iso_parent}
        )
        if not eligible_partners:
            continue

        foreign_total = continent_foreign_total.get(
            continent_name, pd.DataFrame(columns=CBCR_VARS)
        )
        if foreign_total.empty:
            continue

        agg_values = agg_row.iloc[0][CBCR_VARS].to_dict()
        if not has_nonzero_values(agg_values):
            continue

        new_rows = allocate_across_partners(
            agg_values=agg_values,
            eligible_partners=eligible_partners,
            foreign_total=foreign_total,
            iso_parent=iso_parent,
            year=year,
            distribution_source="continent_single_code_residual",
            source_code=code,
        )
        distributed_rows.extend(new_rows)
        covered_foreign_partners.update([row["iso_partner"] for row in new_rows])

    # Step 3: W_O = global foreign residual
    # Only distribute W_O to still-uncovered foreign countries.
    # If no uncovered countries remain, do not allocate W_O again,
    # because that would double count already covered foreign activity.
    w_o_row = parent_data[parent_data["iso_partner"] == "W_O"]
    if not w_o_row.empty:
        agg_values = w_o_row.iloc[0][CBCR_VARS].to_dict()

        if has_nonzero_values(agg_values):
            eligible_uncovered = (
                set(global_foreign_total.index)
                - covered_foreign_partners
                - {iso_parent}
            )

            if eligible_uncovered:
                new_rows = allocate_across_partners(
                    agg_values=agg_values,
                    eligible_partners=eligible_uncovered,
                    foreign_total=global_foreign_total,
                    iso_parent=iso_parent,
                    year=year,
                    distribution_source="world_other_residual",
                    source_code="W_O",
                )
                distributed_rows.extend(new_rows)
                covered_foreign_partners.update(
                    [row["iso_partner"] for row in new_rows]
                )
            else:
                print(
                    f"Skipping W_O for {iso_parent}, {year}: "
                    f"no uncovered foreign partners remain."
                )

    # Step 4: WXD residual
    # WXD is treated as total non-domestic activity. After subtracting already
    # covered non-domestic rows, the remaining residual is distributed.
    wxd_row = parent_data[parent_data["iso_partner"] == "WXD"]
    reported_codes = set(parent_data["iso_partner"].dropna())
    wxd_only_reporter = reported_codes.issubset({iso_parent, "WXD"})

    if not wxd_row.empty:
        current_result = (
            pd.concat(
                [country_rows, pd.DataFrame(distributed_rows)],
                ignore_index=True,
            )
            if distributed_rows
            else country_rows.copy()
        )

        already_covered_sum = current_result.loc[
            current_result["iso_partner"] != iso_parent, CBCR_VARS
        ].sum()

        wxd_values = wxd_row.iloc[0][CBCR_VARS]

        residual_values = {}
        for var in CBCR_VARS:
            wxd_val = wxd_values.get(var, pd.NA)
            covered_val = already_covered_sum.get(var, pd.NA)

            if pd.isna(wxd_val):
                residual_values[var] = pd.NA
                continue

            covered_num = 0 if pd.isna(covered_val) else float(covered_val)
            residual = float(wxd_val) - covered_num
            residual_values[var] = residual

            if (var in WXD_WARNING_VARS) and (residual < -WXD_WARNING_ATOL):
                warning_row = {
                    "year": year,
                    "iso_parent": iso_parent,
                    "variable": var,
                    "wxd_value": float(wxd_val),
                    "already_covered_value": covered_num,
                    "wxd_residual": residual,
                }
                negative_wxd_warning_rows.append(warning_row)
                print(
                    f"WARNING: negative WXD residual for {iso_parent}, {year}, {var}: "
                    f"WXD={float(wxd_val):,.6f}, covered={covered_num:,.6f}, residual={residual:,.6f}"
                )

        if has_nonzero_values(residual_values):
            current_foreign_partners = set(
                current_result.loc[
                    current_result["iso_partner"] != iso_parent, "iso_partner"
                ]
            )

            wxd_eligible_uncovered = (
                set(global_foreign_total.index)
                - true_reported_foreign_partners
                - current_foreign_partners
                - {iso_parent}
            )

            if wxd_eligible_uncovered:
                new_rows = allocate_across_partners(
                    agg_values=residual_values,
                    eligible_partners=wxd_eligible_uncovered,
                    foreign_total=global_foreign_total,
                    iso_parent=iso_parent,
                    year=year,
                    distribution_source="wxd_residual_to_uncovered",
                    source_code="WXD",
                )
                distributed_rows.extend(new_rows)
                covered_foreign_partners.update(
                    [row["iso_partner"] for row in new_rows]
                )

            else:
                wxd_eligible_nonreported = (
                    set(global_foreign_total.index)
                    - true_reported_foreign_partners
                    - {iso_parent}
                )

                if wxd_eligible_nonreported:
                    new_rows = allocate_across_partners(
                        agg_values=residual_values,
                        eligible_partners=wxd_eligible_nonreported,
                        foreign_total=global_foreign_total,
                        iso_parent=iso_parent,
                        year=year,
                        distribution_source="wxd_residual_added_to_nonreported",
                        source_code="WXD",
                    )
                    distributed_rows.extend(new_rows)
                    covered_foreign_partners.update(
                        [row["iso_partner"] for row in new_rows]
                    )

    # Final result for all reporters, including those without WXD
    if distributed_rows:
        result = pd.concat(
            [country_rows, pd.DataFrame(distributed_rows)],
            ignore_index=True,
        )
    else:
        result = country_rows

    # Internal WXD check, computed before clipping negative distributed values
    if not wxd_row.empty:
        wxd_values = wxd_row.iloc[0][CBCR_VARS]
        non_domestic_sum = result.loc[
            result["iso_partner"] != iso_parent, CBCR_VARS
        ].sum()

        wxd_check = {
            "year": year,
            "iso_parent": iso_parent,
            "has_wxd_row": 1,
            "wxd_only_reporter": int(wxd_only_reporter),
            "wxd_matches_non_domestic_rows": series_allclose(
                wxd_values,
                non_domestic_sum,
                CBCR_VARS,
                rtol=1e-4,
                atol=1e-1,
            ),
            "wxd_max_abs_diff": max(
                [
                    abs(round(float(non_domestic_sum[var]) - float(wxd_values[var])))
                    for var in CBCR_VARS
                    if pd.notna(wxd_values.get(var, pd.NA))
                    and pd.notna(non_domestic_sum.get(var, pd.NA))
                ],
                default=pd.NA,
            ),
        }
    else:
        wxd_check = {
            "year": year,
            "iso_parent": iso_parent,
            "has_wxd_row": 0,
            "wxd_only_reporter": int(wxd_only_reporter),
            "wxd_matches_non_domestic_rows": pd.NA,
            "wxd_max_abs_diff": pd.NA,
        }

    # After the WXD checks, clip negative distributed values to zero for variables
    # that should not be negative. Profit and tax variables may remain negative.
    distributed_mask = result["is_distributed"] == 1

    for var in NONNEGATIVE_DISTRIBUTED_VARS:
        negative_mask = distributed_mask & result[var].notna() & (result[var] < 0)
        if negative_mask.any():
            negative_rows = result.loc[
                negative_mask,
                [
                    "year",
                    "iso_parent",
                    "iso_partner",
                    "distribution_source",
                    "source_aggregate_code",
                    var,
                ],
            ].copy()
            negative_rows = negative_rows.rename(columns={var: "value_before_clipping"})
            negative_rows["variable"] = var
            clipping_rows.extend(negative_rows.to_dict("records"))

            n_neg = int(negative_mask.sum())
            print(
                f"Clipping {n_neg} negative distributed values to zero for "
                f"{iso_parent}, {year}, variable {var}"
            )
            result.loc[negative_mask, var] = 0

    return (
        result,
        len(distributed_rows),
        len(continents_processed),
        wxd_check,
        negative_wxd_warning_rows,
        clipping_rows,
    )


# %% [markdown]
# 5. Main pipeline: build row-level disaggregated dataset

# %%
print("\nManually excluded from weight computation per year:")
for year in years:
    excluded = get_excluded_parents_for_year(year)
    print(f"  {year}: {len(excluded)} countries - {sorted(excluded)}")

# %%
all_years = []
diagnostics = []
continent_total_audit_years = []
wxd_checks = []
negative_wxd_warning_rows_all = []
negative_distributed_clipping_rows_all = []
flagged_inconsistent_totals_dict = {}
excluded_parents_dict = {}

print("\nChecking continent totals, computing weights, and disaggregating rows:")

for year in years:
    print(f'\n{"=" * 60}\nYear {year}\n{"=" * 60}')

    cbcr_year = cbcr_full[cbcr_full["year"] == year].copy()

    # Step 1: Drop redundant continent totals and flag inconsistent total+_O cases
    cbcr_year, continent_total_audit, flagged_inconsistent_totals = (
        drop_redundant_continent_totals(cbcr_year, continent_mapping)
    )

    continent_total_audit_years.append(continent_total_audit)

    # Step 2: Build exclusions for weight computation
    manual_excluded = get_excluded_parents_for_year(year).copy()

    if not flagged_inconsistent_totals.empty:
        flagged_parents = set(flagged_inconsistent_totals["iso_parent"].unique())
    else:
        flagged_parents = set()

    excluded_parents = manual_excluded | flagged_parents

    flagged_inconsistent_totals_dict[year] = flagged_inconsistent_totals
    excluded_parents_dict[year] = excluded_parents

    n_dropped_redundant_totals = (
        int(continent_total_audit["dropped_redundant_total"].sum())
        if not continent_total_audit.empty
        else 0
    )

    print(f"Dropped redundant continent total rows: {n_dropped_redundant_totals}")
    print(
        f"Flagged parents with inconsistent single-letter + _O totals: {sorted(flagged_parents)}"
    )
    print(f"Excluded parents for weight computation: {sorted(excluded_parents)}")

    # Step 3: Compute foreign totals used as distribution weights
    continent_foreign_total, global_foreign_total = compute_distribution_foreign(
        cbcr_year, excluded_parents, continent_mapping
    )

    n_good = cbcr_year[~cbcr_year["iso_parent"].isin(excluded_parents)][
        "iso_parent"
    ].nunique()
    n_excluded = cbcr_year[cbcr_year["iso_parent"].isin(excluded_parents)][
        "iso_parent"
    ].nunique()
    print(f"Reporters: {n_good} good + {n_excluded} excluded from weight computation")

    # Step 4: Build partner metadata lookup
    partner_lookup = build_partner_metadata_lookup(
        cbcr_year=cbcr_year,
        year=year,
        partner_static=partner_static,
        partner_yearly=partner_yearly,
    )

    # Step 5: Disaggregate all reporters
    processed_reporters = []
    total_distributed = 0
    reporters_with_distribution = 0

    for iso_parent, parent_data in cbcr_year.groupby("iso_parent", sort=False):
        (
            processed,
            n_distributed,
            _,
            wxd_check,
            negative_wxd_warning_rows,
            clipping_rows,
        ) = distribute_aggregates_per_reporter(
            parent_data=parent_data,
            iso_parent=iso_parent,
            continent_mapping=continent_mapping,
            continent_foreign_total=continent_foreign_total,
            global_foreign_total=global_foreign_total,
        )

        processed_reporters.append(processed)
        wxd_checks.append(wxd_check)

        if negative_wxd_warning_rows:
            negative_wxd_warning_rows_all.extend(negative_wxd_warning_rows)

        if clipping_rows:
            negative_distributed_clipping_rows_all.extend(clipping_rows)

        total_distributed += n_distributed

        if n_distributed > 0:
            reporters_with_distribution += 1

    combined = pd.concat(processed_reporters, ignore_index=True)

    # Step 6: Fill partner metadata for distributed rows
    for col in METADATA_COLS:
        target_dtype = METADATA_DTYPES[col]

        if col not in combined.columns:
            combined[col] = pd.Series(pd.NA, index=combined.index, dtype=target_dtype)
        else:
            try:
                combined[col] = combined[col].astype(target_dtype)
            except Exception:
                pass

        missing = combined[col].isna()
        if missing.any():
            mapped = combined.loc[missing, "iso_partner"].map(partner_lookup[col])

            try:
                mapped = mapped.astype(target_dtype)
            except Exception:
                pass

            combined.loc[missing, col] = mapped

    combined["year"] = year

    preferred_cols = (
        [
            "year",
            "iso_parent",
            "iso_partner",
            "is_distributed",
            "distribution_source",
            "source_aggregate_code",
        ]
        + CBCR_VARS
        + METADATA_COLS
    )
    existing_preferred = [c for c in preferred_cols if c in combined.columns]
    other_cols = [c for c in combined.columns if c not in existing_preferred]
    combined = combined[existing_preferred + other_cols]

    all_years.append(combined)

    diagnostics.append(
        {
            "year": year,
            "n_rows_input": int(len(cbcr_full[cbcr_full["year"] == year])),
            "n_rows_after_dropping_redundant_totals": int(len(cbcr_year)),
            "n_rows_output": int(len(combined)),
            "n_reporters_total": int(cbcr_year["iso_parent"].nunique()),
            "n_reporters_manual_excluded_from_weights": int(len(manual_excluded)),
            "n_reporters_flagged_inconsistent_totals": int(len(flagged_parents)),
            "n_reporters_total_excluded_from_weights": int(len(excluded_parents)),
            "n_redundant_continent_totals_dropped": int(n_dropped_redundant_totals),
            "n_distributed_rows": int(total_distributed),
            "n_reporters_with_distribution": int(reporters_with_distribution),
        }
    )

    print(
        f"Distributed {total_distributed} rows across {reporters_with_distribution} reporters"
    )
    print(f"Output rows: {len(combined)}")


# %% [markdown]
# 6. Final outputs

# %%
cbcr_main_disaggregated = pd.concat(all_years, ignore_index=True)

cbcr_main_disaggregated["payroll"] = (
    pd.to_numeric(cbcr_main_disaggregated["n_employees"], errors="coerce").fillna(0)
    * pd.to_numeric(cbcr_main_disaggregated["wage_monthly"], errors="coerce").fillna(0)
    * 12
)

disaggregation_diagnostics = pd.DataFrame(diagnostics)
continent_total_audit_all = pd.concat(continent_total_audit_years, ignore_index=True)
wxd_checks_all = pd.DataFrame(wxd_checks)
negative_wxd_warnings_all = pd.DataFrame(negative_wxd_warning_rows_all)
negative_distributed_clipping_all = pd.DataFrame(negative_distributed_clipping_rows_all)

non_empty_flagged = [
    df for df in flagged_inconsistent_totals_dict.values() if not df.empty
]
if non_empty_flagged:
    flagged_inconsistent_totals_all = pd.concat(non_empty_flagged, ignore_index=True)
else:
    flagged_inconsistent_totals_all = pd.DataFrame()

cbcr_main_disaggregated = cbcr_main_disaggregated.sort_values(
    ["year", "iso_parent", "iso_partner"]
).reset_index(drop=True)

print(f"\nFinal disaggregated dataset: {len(cbcr_main_disaggregated)} rows")
print(cbcr_main_disaggregated.head())

if not negative_wxd_warnings_all.empty:
    print(
        f"\nNegative WXD residual warnings: {len(negative_wxd_warnings_all)} "
        f"variable-level cases"
    )

if not negative_distributed_clipping_all.empty:
    print(
        f"Negative distributed values clipped to zero: "
        f"{len(negative_distributed_clipping_all)} row-variable cases"
    )


# %%
cbcr_main_disaggregated.to_csv(
    f"{data_final}/cbcr_main_disaggregated.csv",
    index=False,
)

disaggregation_diagnostics.to_csv(
    f"{output_tables}/disaggregation_diagnostics.csv",
    index=False,
)

continent_total_audit_all.to_csv(
    f"{output_tables}/continent_total_audit.csv",
    index=False,
)

wxd_checks_all.to_csv(
    f"{output_tables}/wxd_checks.csv",
    index=False,
)

if not negative_wxd_warnings_all.empty:
    negative_wxd_warnings_all.to_csv(
        f"{output_tables}/negative_wxd_residual_warnings.csv",
        index=False,
    )

if not negative_distributed_clipping_all.empty:
    negative_distributed_clipping_all.to_csv(
        f"{output_tables}/negative_distributed_values_clipped.csv",
        index=False,
    )

if not flagged_inconsistent_totals_all.empty:
    flagged_inconsistent_totals_all.to_csv(
        f"{output_tables}/flagged_inconsistent_continent_totals.csv",
        index=False,
    )

print("\nSaved:")
print(f"  {data_final}/cbcr_main_disaggregated.csv")
print(f"  {output_tables}/disaggregation_diagnostics.csv")
print(f"  {output_tables}/continent_total_audit.csv")
print(f"  {output_tables}/wxd_checks.csv")
if not negative_wxd_warnings_all.empty:
    print(f"  {output_tables}/negative_wxd_residual_warnings.csv")
if not negative_distributed_clipping_all.empty:
    print(f"  {output_tables}/negative_distributed_values_clipped.csv")
if not flagged_inconsistent_totals_all.empty:
    print(f"  {output_tables}/flagged_inconsistent_continent_totals.csv")


# %%
print(cbcr_main_disaggregated.columns.tolist())

# %%
