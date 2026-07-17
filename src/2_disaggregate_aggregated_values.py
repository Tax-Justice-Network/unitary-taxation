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
# Distribution weights are calibrated over ALL years pooled together: each
# foreign partner's weight for a variable is the MEDIAN, across good
# reporter-years that reported the partner, of that reporter's share of the
# variable going to that partner. Taking the median (rather than summing /
# averaging over reporters) keeps a few large HQ countries -- which report big
# values and therefore appear -- from dominating the imputed shares; pooling
# over years relies on more observations.
# Aggregate values, including negative values, are distributed proportionally whenever
# positive weights exist. If all weights for a variable are zero, values are split equally.
# Negative weights are set to zero before weighting, except for the profit/tax
# variables in SIGNED_DISTRIBUTION_VARS, where signed weights are kept.
#
# WXD diagnostics are computed before any clipping of negative distributed values.
# After those diagnostics, negative distributed values are clipped to zero for
# non-profit and non-tax variables only. Profit and tax variables may remain negative.
#
# The final output contains country rows only.

# %%
import os
import sys
import pandas as pd
import numpy as np

# On Windows, stdout defaults to cp1252 and crashes when any printed line
# embeds the Arabic characters from the project path. Reconfigure stdout to
# UTF-8 with error-replacement so status prints never abort the script.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_min_corrected",
    "etr_parent_partner_corrected",
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
    "etr_domestic_corrected",
    "etr_foreign_corrected",
    "etr_average_corrected",
    "etr_partner_median_corrected",
    "etr_partner_p25_corrected",
    "etr_partner_min_corrected",
    "cit",
    "tax_revenue_current_usd",
    "gvt_health_expenditure",
    "wage_monthly",
]

PAIR_YEARLY_METADATA_COLS = [
    "etr_parent_partner_corrected",
    # Number of CbCR-reporting MNE groups in this (parent, partner, year) cell.
    # Carried through (NaN on is_distributed==1 imputed rows, like the pair ETR)
    # to serve as the denominator for the destination-sales nexus coverage
    # fraction in 5_estimate_profit_shifting.py.
    "n_cbcr",
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
    "etr_domestic_corrected": "Float64",
    "etr_foreign_corrected": "Float64",
    "etr_average_corrected": "Float64",
    "etr_partner_median_corrected": "Float64",
    "etr_partner_p25_corrected": "Float64",
    "etr_partner_min_corrected": "Float64",
    "etr_parent_partner_corrected": "Float64",
    "n_cbcr": "Float64",
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
    # Profit / tax variables — added 2026-05-14 per user decision: do not allow
    # negative imputed values for any variable, including profit and tax.
    # Negative shares can still arise from the trimmed-mean weights (rarely,
    # since the weight is also clipped at 0), but if the allocation produces a
    # negative row value (e.g. from distributing a negative aggregate) it is
    # clipped to zero. Conservation is intentionally relaxed for imputed rows
    # — the conservation-invariant check at the end of the script logs the gap.
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
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

pair_rows = cbcr_full.loc[
    ~cbcr_full["iso_partner"].isin(non_countries),
    ["iso_parent", "iso_partner", "year"] + PAIR_YEARLY_METADATA_COLS,
].copy()

pair_yearly = (
    pair_rows.groupby(["iso_parent", "iso_partner", "year"], as_index=False)[
        PAIR_YEARLY_METADATA_COLS
    ]
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

for col in PAIR_YEARLY_METADATA_COLS:
    try:
        pair_yearly[col] = pair_yearly[col].astype(METADATA_DTYPES[col])
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
        if col not in METADATA_DTYPES:
            continue
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


def build_pair_metadata_lookup(cbcr_year, year, pair_yearly):
    """
    Build a reporter-partner-year lookup for pair-specific metadata.

    Priority:
    1. Metadata observed in the current cbcr_year country rows
    2. Fallback metadata from pair_yearly for the same year
    """
    reported_lookup = (
        cbcr_year[~cbcr_year["iso_partner"].isin(non_countries)]
        .drop_duplicates(subset=["iso_parent", "iso_partner"])
        .set_index(["iso_parent", "iso_partner"])
    )

    yearly_lookup = (
        pair_yearly.loc[pair_yearly["year"] == year]
        .drop(columns="year")
        .drop_duplicates(subset=["iso_parent", "iso_partner"])
        .set_index(["iso_parent", "iso_partner"])
    )

    all_pairs = reported_lookup.index.union(yearly_lookup.index)
    pair_lookup = pd.DataFrame(index=all_pairs)

    for col in PAIR_YEARLY_METADATA_COLS:
        dtype = METADATA_DTYPES[col]
        pair_lookup[col] = pd.Series(pd.NA, index=pair_lookup.index, dtype=dtype)

        if col in yearly_lookup.columns:
            yearly_series = yearly_lookup[col].copy()
            try:
                yearly_series = yearly_series.astype(dtype)
            except Exception:
                pass
            pair_lookup.loc[yearly_series.index, col] = yearly_series

        if col in reported_lookup.columns:
            reported_series = reported_lookup[col].copy()
            try:
                reported_series = reported_series.astype(dtype)
            except Exception:
                pass
            pair_lookup.loc[reported_series.index, col] = reported_series

    return pair_lookup


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


# Variables whose global aggregate weight is allowed to be negative when
# distributing aggregate rows. For these, partners that are systematically
# loss-making (negative profit, refund-driven negative tax accrual) get
# correctly-signed shares of the aggregate so misalignment between
# activity-where-it-happens and profit-where-it-shows-up is preserved in
# imputed rows. For non-signed variables (employees, revenues, assets, etc.),
# negative totals are clipped to zero as before.
SIGNED_DISTRIBUTION_VARS = {
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
    "income_tax_paid_on_cash_basis",
    "income_tax_accrued_current_year",
}

# Signed (profit/tax) imputed values are allowed to stay NEGATIVE end-to-end: a
# market that is on average loss-making keeps a correctly-signed negative imputed
# profit instead of being clamped to zero, so the activity-vs-profit misalignment
# the downstream estimation detects is preserved. This is now the fixed behaviour
# (the former ALLOW_NEGATIVE_SIGNED_SHARES toggle has been removed): the
# post-distribution clip below exempts SIGNED_DISTRIBUTION_VARS unconditionally.

# Factors whose profitability is used to impute the profit of distributed rows.
# For each factor f, the partner's profit-yield = Σ reported profit ÷ Σ reported f
# (pooled over its directly-reported foreign rows); the row's implied profit from f
# = row_f × that yield. The imputed profit is the MEAN of the implied profits over
# the factors for which the row has a positive value and the partner a defined
# yield. Fixed at all three activity factors (sales, employees, tangible assets),
# so profit reflects the partner's overall return on activity rather than its sales
# margin alone (which over-rewards consumer markets). The earlier sales-margin-only
# and weight-distributed profit variants have been removed — this is the sole method.
PROFIT_IMPUTATION_FACTORS = [
    "unrelated_party_revenues",
    "n_employees",
    "tangible_assets_except_cash",
]
# Robustness for the partner-specific profit yields. Each partner's per-factor
# yield (Σ reported profit ÷ Σ reported factor) is used directly and winsorized
# across partners at the 1st / 99th percentile, clipping only the explosive
# outliers produced by near-zero activity denominators. The winsor is
# sign-preserving: a partner that reported losses keeps a negative yield (and so a
# negative imputed profit), and a structurally high-profitability jurisdiction
# keeps its high yield.
PROFIT_YIELD_WINSOR = 0.01

# Disaggregation is a SINGLE method (the former IMPUTE_METHOD toggle is removed):
# bad-reporter aggregates (continent / WXD / W_O totals) are spread across ALL
# structurally-eligible markets, the three activity factors (employees / sales /
# tangible assets) are then re-weighted by the García-Bernardo & Janský (2024)
# gravity-model predictions (src/gravity/, data/intermediate/gravity/
# gravity_imputed_activity.csv) conserving each aggregate, and profit is imputed
# from each partner's reported profitability (see PROFIT_IMPUTATION_FACTORS).
# Bootstrap draw: when GRAVITY_BOOT_SEED is set, read the seed-tagged gravity
# activity and write a seed-tagged disaggregated dataset, so run_bootstrap.py can
# propagate imputation uncertainty into SEs.
_GBOOT = os.environ.get("GRAVITY_BOOT_SEED")
_BOOT_SUFFIX = f"__boot{_GBOOT}" if _GBOOT not in (None, "") else ""

# Stability threshold for signed allocation: when abs(denominator) for a
# signed variable is small relative to the max-abs of the partner weights,
# the resulting shares blow up. Skip allocation in that variable for the
# (rare) cell-year where the denominator is degenerate.
SIGNED_DENOMINATOR_MIN_RELATIVE = 0.05


# %%
def build_uniform_recipient_weights(partner_universe, continent_mapping):
    """Uniform (=1) per-variable weight tables over the FULL foreign-country
    universe — the BROAD recipient set.

    Trimmed-mean share weighting has been removed: bad-reporter aggregates are
    spread across EVERY structurally-eligible market, not just the partners that
    good reporters happened to report. The phase-1 distribution here uses a flat
    weight of 1 for every (variable, partner), which (a) selects the recipient
    set (all eligible markets) and (b) conserves each raw aggregate (an equal
    split sums back to the aggregate). The real within-group split of the three
    activity factors is then set by the gravity-model predictions, and profit by
    partner profitability, in the post-distribution step below — so the phase-1
    values for those columns are transient, and every other variable is cleared
    on imputed rows afterwards.

    Returns the same 4-tuple interface the distribution code expects
    (continent_foreign_total, global_foreign_total, n_reporters_per_partner,
    weight_source_per_partner).
    """
    partner_index = pd.Index(sorted(partner_universe), name="iso_partner")
    global_foreign_total = pd.DataFrame(1.0, index=partner_index, columns=CBCR_VARS)

    continent_foreign_total = {}
    for continent_name, countries in continent_mapping.items():
        sub = global_foreign_total[global_foreign_total.index.isin(countries)]
        continent_foreign_total[continent_name] = (
            sub.copy() if not sub.empty else pd.DataFrame(columns=CBCR_VARS)
        )

    # No per-partner reporter count under uniform weighting; the metadata column
    # records the (single) imputation method rather than a trimmed-mean source.
    n_reporters_per_partner = None
    weight_source_per_partner = pd.Series(
        "gravity_broad", index=global_foreign_total.index, name="weight_source"
    )
    return (continent_foreign_total, global_foreign_total,
            n_reporters_per_partner, weight_source_per_partner)


def distribute_aggregates_per_reporter(
    parent_data,
    iso_parent,
    continent_mapping,
    continent_foreign_total,
    global_foreign_total,
    n_reporters_per_partner=None,
    weight_source_per_partner=None,
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
    # n_reporters_for_partner_weight applies only to imputed rows, where it
    # captures how many MNEs in good_foreign contributed to the partner-level
    # weights. Country rows are direct reports (not imputed from weights), so
    # the field is NaN -- the concept doesn't apply.
    country_rows["n_reporters_for_partner_weight"] = pd.NA
    country_rows["weight_source_for_partner"] = pd.NA

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
        # Build TWO weight frames:
        #   relevant_clipped: negative weights clipped to zero. Used for
        #                     non-signed variables (employees, revenues, etc.)
        #   relevant_signed:  raw signed weights. Used for SIGNED_DISTRIBUTION_VARS
        #                     so partners systematically loss-making globally
        #                     get correctly-signed shares of aggregate profit
        #                     (preserving the activity-vs-profit misalignment
        #                     that the downstream estimation is built to detect).
        relevant_signed = foreign_total[
            foreign_total.index.isin(eligible_partners)
        ].copy()
        if relevant_signed.empty:
            return []

        relevant_clipped = relevant_signed.clip(lower=0)
        partner_list = list(relevant_signed.index)
        n_partners = len(partner_list)

        new_rows = []
        for iso_partner_target in partner_list:
            n_rep = (
                int(n_reporters_per_partner.get(iso_partner_target, 0))
                if n_reporters_per_partner is not None
                else 0
            )
            weight_src = (
                str(weight_source_per_partner.get(iso_partner_target, "median"))
                if weight_source_per_partner is not None
                else "median"
            )
            new_rows.append(
                {
                    "iso_parent": iso_parent,
                    "iso_partner": iso_partner_target,
                    "year": year,
                    "is_distributed": 1,
                    "distribution_source": distribution_source,
                    "source_aggregate_code": source_code,
                    "n_reporters_for_partner_weight": n_rep,
                    "weight_source_for_partner": weight_src,
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

            # Pick weight frame based on variable type
            use_signed = var in SIGNED_DISTRIBUTION_VARS
            weights = relevant_signed[var] if use_signed else relevant_clipped[var]
            denominator = weights.sum()
            sum_abs = weights.abs().sum()

            # For signed variables, fall back to clipped weights when the
            # signed denominator is degenerate (cancellation makes the ratio
            # explosive). Use SIGNED_DENOMINATOR_MIN_RELATIVE × max-abs as
            # the threshold.
            if (
                use_signed
                and (
                    sum_abs == 0
                    or abs(denominator)
                    < SIGNED_DENOMINATOR_MIN_RELATIVE * sum_abs
                )
            ):
                weights = relevant_clipped[var]
                denominator = weights.sum()

            if denominator != 0 and weights.abs().sum() > 0:
                running_sum = 0.0
                for i, iso_partner_target in enumerate(partner_list[:-1]):
                    value = (
                        agg_val
                        * weights.loc[iso_partner_target]
                        / denominator
                    )
                    new_rows[i][var] = value
                    running_sum += value
                new_rows[-1][var] = agg_val - running_sum
                continue

            # Fallback: all weights are zero, split equally
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
                # Spillover case: WXD residual is positive but every global
                # foreign partner is already covered by a continent residual
                # (F_O / E_O / A_O / S_O / world_other). The previous design
                # emitted a SECOND row per partner with source
                # "wxd_residual_added_to_nonreported", which produced duplicate
                # parent x partner x year rows downstream. Instead, add the
                # WXD residual proportionally to the existing distributed
                # rows (already covering the same set of partners) so the
                # partner-level totals reflect both the continent share and
                # the WXD spillover, on a single row per partner.
                wxd_eligible_nonreported = (
                    set(global_foreign_total.index)
                    - true_reported_foreign_partners
                    - {iso_parent}
                )

                if wxd_eligible_nonreported and distributed_rows:
                    # Per-variable, allocate the WXD residual proportionally
                    # to each existing distributed row, weighted by the
                    # partner's share of global_foreign_total restricted to
                    # the eligible-nonreported set. Uses signed weights for
                    # SIGNED_DISTRIBUTION_VARS (so partners systematically
                    # loss-making globally get correctly-signed residual
                    # shares) and clipped weights for the rest.
                    relevant_signed = global_foreign_total[
                        global_foreign_total.index.isin(wxd_eligible_nonreported)
                    ]
                    if not relevant_signed.empty:
                        relevant_clipped = relevant_signed.clip(lower=0)
                        for row in distributed_rows:
                            partner = row.get("iso_partner")
                            if partner not in relevant_signed.index:
                                continue
                            for var in CBCR_VARS:
                                rv = residual_values.get(var)
                                if rv is None or pd.isna(rv):
                                    continue
                                use_signed = var in SIGNED_DISTRIBUTION_VARS
                                weights_var = (
                                    relevant_signed[var]
                                    if use_signed
                                    else relevant_clipped[var]
                                )
                                denom_v = weights_var.sum()
                                sum_abs = weights_var.abs().sum()
                                if (
                                    use_signed
                                    and (
                                        sum_abs == 0
                                        or abs(denom_v)
                                        < SIGNED_DENOMINATOR_MIN_RELATIVE * sum_abs
                                    )
                                ):
                                    weights_var = relevant_clipped[var]
                                    denom_v = weights_var.sum()
                                if denom_v == 0 or weights_var.abs().sum() == 0:
                                    continue
                                share = weights_var.loc[partner] / denom_v
                                add_val = float(rv) * share
                                cur = row.get(var, 0.0)
                                if pd.isna(cur):
                                    cur = 0.0
                                row[var] = float(cur) + add_val
                            existing_src = str(row.get("distribution_source",
                                                       "")).strip()
                            if "wxd_spillover" not in existing_src:
                                row["distribution_source"] = (
                                    existing_src + "+wxd_spillover"
                                    if existing_src
                                    else "wxd_spillover"
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

    # After the WXD checks, clip negative distributed values to zero. Signed
    # (profit/tax) vars are exempt so their negative imputed values survive into
    # the conserved per-group aggregate, which the profitability recompute below
    # then redistributes sign-preserved.
    distributed_mask = result["is_distributed"] == 1

    clip_vars = [v for v in NONNEGATIVE_DISTRIBUTED_VARS if v not in SIGNED_DISTRIBUTION_VARS]

    for var in clip_vars:
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

# %% [markdown]
# Pre-pass: per year, drop redundant continent totals and determine the parents
# excluded from weight computation. The cleaned per-year frames and exclusion
# sets are kept so the distribution weights can be calibrated over ALL years
# pooled together (next cell).

# %%
cbcr_year_clean = {}
continent_total_audit_dict = {}
continent_total_audit_years = []
flagged_inconsistent_totals_dict = {}
excluded_parents_dict = {}

print("\nChecking continent totals and determining excluded reporters per year:")

for year in years:
    cbcr_year = cbcr_full[cbcr_full["year"] == year].copy()

    # Drop redundant continent totals and flag inconsistent total+_O cases
    cbcr_year, continent_total_audit, flagged_inconsistent_totals = (
        drop_redundant_continent_totals(cbcr_year, continent_mapping)
    )

    # Build exclusions for weight computation
    manual_excluded = get_excluded_parents_for_year(year).copy()
    if not flagged_inconsistent_totals.empty:
        flagged_parents = set(flagged_inconsistent_totals["iso_parent"].unique())
    else:
        flagged_parents = set()
    excluded_parents = manual_excluded | flagged_parents

    cbcr_year_clean[year] = cbcr_year
    continent_total_audit_dict[year] = continent_total_audit
    continent_total_audit_years.append(continent_total_audit)
    flagged_inconsistent_totals_dict[year] = flagged_inconsistent_totals
    excluded_parents_dict[year] = excluded_parents

    n_dropped_redundant_totals = (
        int(continent_total_audit["dropped_redundant_total"].sum())
        if not continent_total_audit.empty
        else 0
    )
    print(
        f"  {year}: dropped {n_dropped_redundant_totals} redundant continent "
        f"total rows; flagged {sorted(flagged_parents)}; "
        f"excluded {sorted(excluded_parents)}"
    )

# %% [markdown]
# Recipient universe for the BROAD gravity redistribution.
#
# Trimmed-mean share weighting is gone: a bad reporter's aggregate is spread
# across EVERY structurally-eligible foreign market (all real countries observed
# anywhere in the CbCR panel), with a flat phase-1 weight that conserves each
# aggregate. The actual within-group split of the three activity factors is set
# by the gravity model, and profit by partner profitability, in the
# post-distribution step further below.

# %%
partner_universe = set(partner_static["iso_partner"].dropna()) - set(non_countries)

(
    continent_foreign_total,
    global_foreign_total,
    n_reporters_per_partner,
    weight_source_per_partner,
) = build_uniform_recipient_weights(partner_universe, continent_mapping)

print(
    f"\nBroad recipient universe: {len(global_foreign_total)} foreign markets "
    f"eligible to receive gravity-imputed activity (flat phase-1 weights)."
)

# %%
all_years = []
diagnostics = []
wxd_checks = []
negative_wxd_warning_rows_all = []
negative_distributed_clipping_rows_all = []

print("\nDisaggregating rows per year:")

for year in years:
    print(f'\n{"=" * 60}\nYear {year}\n{"=" * 60}')

    cbcr_year = cbcr_year_clean[year]
    manual_excluded = get_excluded_parents_for_year(year)
    excluded_parents = excluded_parents_dict[year]
    flagged_parents = (
        set(flagged_inconsistent_totals_dict[year]["iso_parent"].unique())
        if not flagged_inconsistent_totals_dict[year].empty
        else set()
    )
    continent_total_audit = continent_total_audit_dict[year]
    n_dropped_redundant_totals = (
        int(continent_total_audit["dropped_redundant_total"].sum())
        if not continent_total_audit.empty
        else 0
    )

    n_good = cbcr_year[~cbcr_year["iso_parent"].isin(excluded_parents)][
        "iso_parent"
    ].nunique()
    n_excluded = cbcr_year[cbcr_year["iso_parent"].isin(excluded_parents)][
        "iso_parent"
    ].nunique()
    print(f"Reporters: {n_good} good + {n_excluded} excluded from weight computation")

    # Build metadata lookups
    partner_lookup = build_partner_metadata_lookup(
        cbcr_year=cbcr_year,
        year=year,
        partner_static=partner_static,
        partner_yearly=partner_yearly,
    )

    pair_lookup = build_pair_metadata_lookup(
        cbcr_year=cbcr_year,
        year=year,
        pair_yearly=pair_yearly,
    )

    # Disaggregate all reporters
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
            n_reporters_per_partner=n_reporters_per_partner,
            weight_source_per_partner=weight_source_per_partner,
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

    # Fill all non-pair metadata from partner lookup
    non_pair_cols = [
        col for col in METADATA_COLS if col != "etr_parent_partner_corrected"
    ]

    for col in non_pair_cols:
        missing = combined[col].isna()
        if missing.any():
            mapped = combined.loc[missing, "iso_partner"].map(partner_lookup[col])

            try:
                mapped = mapped.astype(METADATA_DTYPES[col])
            except Exception:
                pass

            combined.loc[missing, col] = mapped

    # Fill pair-specific corrected ETR from pair lookup for cells that were
    # actually reported in the source data. Distributed (is_distributed=1)
    # cells stay NaN — no real (parent, partner, year) report exists to
    # derive an ETR from, and we intentionally do NOT impute the pair ETR
    # here. Downstream consumers should treat etr_parent_partner_corrected
    # as a diagnostic only and rely on partner-year ETRs (median / p25 /
    # average / min) for any calculation that needs to cover distributed
    # rows.
    # Same treatment for every pair-year metadata column (the pair ETR and the
    # CbCR group count n_cbcr): map the reported value onto reported cells, leave
    # distributed (imputed) cells NaN — they have no real (parent, partner, year)
    # report. n_cbcr in particular is not carried on the good-reporter rows, so
    # the column is created here as NaN first and then filled from pair_lookup.
    for pair_col in PAIR_YEARLY_METADATA_COLS:
        if pair_col not in pair_lookup.columns:
            continue
        if pair_col not in combined.columns:
            combined[pair_col] = np.nan
        missing_pair = combined[pair_col].isna()
        if missing_pair.any():
            pair_index = pd.MultiIndex.from_frame(
                combined.loc[missing_pair, ["iso_parent", "iso_partner"]]
            )
            mapped_pair = pair_lookup.reindex(pair_index)[pair_col].to_numpy()
            combined.loc[missing_pair, pair_col] = mapped_pair

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

# %%
def _impute_profit_multifactor(frame, pcol, reported_mask, factors):
    """Per-row imputed profit from the partner's profitability on MULTIPLE factors.

    For each factor f in `factors`, the partner-level yield is
    Σ reported profit ÷ Σ reported f (pooled over the partner's directly-reported
    foreign rows, `reported_mask`). The row's implied profit from f = row_f × yield.
    The returned value is the arithmetic MEAN of the implied profits across the
    factors for which the row has a positive value AND the partner has a defined
    yield (so a row with 0 employees contributes no employee-based estimate, and a
    partner with no reported assets contributes no asset yield). Aligned to
    `frame.index`; NaN where no factor is usable (caller leaves such rows as-is).

    With factors == ["unrelated_party_revenues"] this reduces exactly to the old
    sales-margin imputation (imputed sales × reported profit/sales).
    """
    p = pd.to_numeric(frame[pcol], errors="coerce")
    est_sum = pd.Series(0.0, index=frame.index)
    est_cnt = pd.Series(0.0, index=frame.index)
    for f in factors:
        if f not in frame.columns:
            continue
        fv = pd.to_numeric(frame[f], errors="coerce")
        tab = pd.DataFrame(
            {"iso_partner": frame["iso_partner"], "p": p.where(reported_mask),
             "f": fv.where(reported_mask)}
        ).groupby("iso_partner").sum(min_count=1)
        own_yield = (tab["p"] / tab["f"]).where(tab["f"] > 0)
        # Winsorize the partner yields across partners at the 1st / 99th
        # percentile, clipping only the explosive thin-denominator outliers and
        # otherwise keeping each partner's own (sign-preserving) profitability.
        _lo, _hi = own_yield.quantile(PROFIT_YIELD_WINSOR), own_yield.quantile(1 - PROFIT_YIELD_WINSOR)
        yield_f = own_yield
        if pd.notna(_lo) and pd.notna(_hi):
            yield_f = own_yield.clip(_lo, _hi)
        implied = fv * frame["iso_partner"].map(yield_f)
        ok = implied.notna() & fv.notna() & (fv > 0)
        est_sum = est_sum + implied.where(ok, 0.0)
        est_cnt = est_cnt + ok.astype(float)
    return est_sum / est_cnt.where(est_cnt > 0)


# %%
# The single imputation method. Each bad-reporter aggregate group's distributed
# total (placed on ALL eligible markets with a flat phase-1 weight) is
# redistributed across its partners by the gravity-model predicted activity
# (conserving the aggregate) and capped to plausible per-country totals; profit is
# then imputed from each partner's reported profitability. Every other variable is
# cleared on distributed rows at the end.
_g = pd.read_csv(f"{data_intermediate}/gravity/gravity_imputed_activity{_BOOT_SUFFIX}.csv")
_g = _g.rename(columns={
    "pred_n_employees": "_g_n_employees",
    "pred_unrelated_party_revenues": "_g_unrelated_party_revenues",
    "pred_tangible_assets_except_cash": "_g_tangible_assets_except_cash",
})
df = cbcr_main_disaggregated.merge(
    _g[["iso_parent", "iso_partner", "year", "_g_n_employees",
        "_g_unrelated_party_revenues", "_g_tangible_assets_except_cash"]],
    on=["iso_parent", "iso_partner", "year"], how="left",
)
dist = df["is_distributed"] == 1
grp = [df["year"], df["iso_parent"], df["source_aggregate_code"]]
factor_map = {
    "n_employees": "_g_n_employees",
    "unrelated_party_revenues": "_g_unrelated_party_revenues",
    "tangible_assets_except_cash": "_g_tangible_assets_except_cash",
}
# ── Per-country TOTAL imputed-activity cap (2026-06-16) ───────────────────
# The redistribution conserves each (year, parent, source_aggregate) total —
# val = weight/Σweight × aggregate always sums back to the aggregate — so we
# can iteratively DOWN-WEIGHT any market whose *total* imputed activity exceeds
# an economic-size ceiling, and the freed share flows to other partners while
# the aggregate is preserved. Without this, fragile/small non-haven states are
# imputed implausibly large activity (e.g. Somalia ~6× GDP of MNE sales,
# Marshall Is ~197×). Anchors: GDP for sales/assets, population for employees.
# Recognised havens are EXEMPT (high sales/GDP is legitimate for them).
_CAP_SALES_X_GDP, _CAP_ASSETS_X_GDP, _CAP_EMP_X_POP = 2.0, 2.0, 0.5
_araw = pd.read_csv(
    f"{data_final}/cbcr_main_allsubgroupsonly.csv",
    usecols=["iso_partner", "year", "gdp_current_usd", "population"],
).drop_duplicates(["iso_partner", "year"])
# Fill missing GDP/population per country across the year panel (ffill+bfill),
# so country-years lacking GDP (e.g. Marshall Is. 2016, North Korea) still get
# a ceiling — otherwise the cap silently does not fire there.
_isos = df["iso_partner"].dropna().unique()
_yrs = sorted(int(y) for y in pd.to_numeric(df["year"], errors="coerce").dropna().unique())
_grid = pd.MultiIndex.from_product([_isos, _yrs],
                                   names=["iso_partner", "year"]).to_frame(index=False)
_araw = _grid.merge(_araw, on=["iso_partner", "year"], how="left").sort_values(
    ["iso_partner", "year"])
for _c in ["gdp_current_usd", "population"]:
    _araw[_c] = _araw.groupby("iso_partner")[_c].transform(lambda s: s.ffill().bfill())
_araw = _araw.rename(columns={"gdp_current_usd": "_gdp_anchor", "population": "_pop_anchor"})
df = df.merge(_araw, on=["iso_partner", "year"], how="left")
_gdp = pd.to_numeric(df["_gdp_anchor"], errors="coerce")
_pop = pd.to_numeric(df["_pop_anchor"], errors="coerce")
# Cap exemption uses the FROZEN functional haven set (not the presentational
# representation list): micro-state havens like Guernsey / Cook Islands must keep
# the exemption even though the outcome-based representation list dropped them.
_exempt = df["iso_partner"].isin(TAX_HAVENS_FUNCTIONAL)
_ceil_map = {
    "n_employees": (_CAP_EMP_X_POP * _pop).where(~_exempt, np.inf),
    "unrelated_party_revenues": (_CAP_SALES_X_GDP * _gdp).where(~_exempt, np.inf),
    "tangible_assets_except_cash": (_CAP_ASSETS_X_GDP * _gdp).where(~_exempt, np.inf),
}
_py = [df["iso_partner"], df["year"]]
_ncap = {}
for _col, _gcol in factor_map.items():
    cur = pd.to_numeric(df[_col], errors="coerce").fillna(0.0)
    gw = pd.to_numeric(df[_gcol], errors="coerce")
    gw = gw.where(gw.notna() & (gw > 0), cur).clip(lower=0).where(dist, 0.0)
    agg = cur.where(dist, 0.0).groupby(grp).transform("sum")
    ceil_row = _ceil_map[_col]
    val = pd.Series(0.0, index=df.index)
    for _ in range(10):
        gwsum = gw.groupby(grp).transform("sum")
        val = pd.Series(np.where(dist & (gwsum > 0), gw / gwsum * agg, 0.0),
                        index=df.index)
        tot = val.where(dist, 0.0).groupby(_py).transform("sum")
        over = dist & ceil_row.notna() & (tot > ceil_row) & (tot > 0)
        if not over.any():
            break
        gw = gw.mask(over, gw * (ceil_row / tot)).clip(lower=0)
    _ncap[_col] = int((dist & ceil_row.notna() & (val.groupby(_py).transform("sum") > ceil_row * 1.001)).sum())
    df[_col] = np.where(dist, val, df[_col])
print(f"  gravity activity cap: rows still > ceiling after capping "
      f"(all-partners-capped groups): {_ncap}")
df["payroll"] = (pd.to_numeric(df["n_employees"], errors="coerce").fillna(0)
                 * pd.to_numeric(df["wage_monthly"], errors="coerce").fillna(0) * 12)
_reported = (df["is_distributed"] == 0) & (df["iso_parent"] != df["iso_partner"])
for _pcol in ["profit_loss_before_income_tax_corrected", "profit_loss_before_income_tax"]:
    _p = pd.to_numeric(df[_pcol], errors="coerce")
    # Multi-factor profitability (sales + employees + tangible assets) applied to
    # each imputed row, then rescaled within the (year, parent, source_aggregate)
    # group to conserve the reported aggregate profit.
    prof = _impute_profit_multifactor(df, _pcol, _reported, PROFIT_IMPUTATION_FACTORS).where(dist).fillna(0.0)
    agg_prof = _p.where(dist, 0.0).groupby(grp).transform("sum")
    # Sign-robust share denominator (mirrors allocate_across_partners): when the
    # signed sum of the multi-factor estimates nearly cancels, the raw ratio
    # prof/profsum explodes (a tiny denominator inflates each share). Fall back
    # to positive-clipped shares in that case so micro-markets can't be assigned
    # absurd profit (e.g. Cook Is. −$294bn on $6bn sales).
    _signed = prof.groupby(grp).transform("sum")
    _abssum = prof.abs().groupby(grp).transform("sum")
    _share = prof.where(_signed.abs() >= 0.05 * _abssum, prof.clip(lower=0))
    _den = _share.groupby(grp).transform("sum")
    df[_pcol] = np.where(dist & (_den.abs() > 0), _share / _den * agg_prof, df[_pcol])

# Imputed rows carry ONLY the gravity-imputed activity, derived payroll, the
# profitability-imputed profit, and total_revenues (floored to the imputed
# unrelated-party sales — related-party revenue is not imputed). Every other CbCR
# variable is intentionally left blank on distributed rows (tax, related-party
# revenue, stated capital, entity counts, IP-holding are NOT imputed).
_imp_all = df["is_distributed"] == 1
df.loc[_imp_all, "total_revenues"] = pd.to_numeric(
    df.loc[_imp_all, "unrelated_party_revenues"], errors="coerce")
_NOT_IMPUTED_ON_DISTRIBUTED = [
    "related_party_revenues", "stated_capital", "n_entities",
    "holding_or_managing_ip",
    "income_tax_paid_on_cash_basis", "income_tax_accrued_current_year",
]
for _c in _NOT_IMPUTED_ON_DISTRIBUTED:
    if _c in df.columns:
        df.loc[_imp_all, _c] = np.nan
cbcr_main_disaggregated = df.drop(
    columns=[c for c in df.columns if c.startswith("_g_")] + ["_gdp_anchor", "_pop_anchor"]
)
print(f"  gravity imputation: activity + profit recomputed on {int(dist.sum())} "
      f"distributed rows; total_revenues floored to imputed sales and "
      f"tax/related/capital/entities/IP cleared on {int(_imp_all.sum())} distributed rows.")

# %%
# Merge destination-based sales (CFB), built by 0_destination_based_sales.py.
# Done here, after disaggregation, because the disaggregation step introduces
# partner jurisdictions that do not exist after script 1, and destination-based
# sales are a property of the market jurisdiction (iso_partner, year).
dest_sales = pd.read_csv(f"{data_intermediate}/destination_based_sales.csv")
cbcr_main_disaggregated = cbcr_main_disaggregated.merge(
    dest_sales,
    on=["iso_partner", "year"],
    how="left",
)
n_rows = len(cbcr_main_disaggregated)
n_with_cfb = cbcr_main_disaggregated["cfb_sales"].notna().sum()
n_with_ads = cbcr_main_disaggregated["ads_sales"].notna().sum()
print(f"\nDestination-based sales merged: CFB on {n_with_cfb} / {n_rows} rows, "
      f"ADS on {n_with_ads} / {n_rows} rows.")

# Bilateral (parent-specific) destination factor, if 1b's Part D produced it
# (requires the AAMNE bilateral download). Keyed by parent AND partner, unlike
# the market-level keys above. Absent file = no-op.
from pathlib import Path  # noqa: E402  (notebook-style script, local use)

_bilat_fp = Path(f"{data_intermediate}/destination_based_sales_bilateral.csv")
if _bilat_fp.exists():
    _bilat = pd.read_csv(_bilat_fp)
    cbcr_main_disaggregated = cbcr_main_disaggregated.merge(
        _bilat, on=["iso_parent", "iso_partner", "year"], how="left"
    )
    _nb = cbcr_main_disaggregated["mne_bilat_factor"].notna().sum()
    print(f"Bilateral destination factor merged on {_nb} / {n_rows} rows.")
else:
    print("Bilateral destination factor not found (1b Part D inactive) — skipped.")

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
# Apply canonical column order before writing
from _column_order import COLUMNS_STAGE_2, apply_canonical_order

cbcr_main_disaggregated = apply_canonical_order(
    cbcr_main_disaggregated, COLUMNS_STAGE_2
)
# Single canonical disaggregated dataset (gravity activity + profitability profit).
# Bootstrap draws append a __boot{seed} suffix.
_disagg_name = f"cbcr_main_disaggregated{_BOOT_SUFFIX}.csv"
cbcr_main_disaggregated.to_csv(f"{data_final}/{_disagg_name}", index=False)

DISAGG_TABLES, _ = output_dirs("disaggregation")

disaggregation_diagnostics.to_csv(
    DISAGG_TABLES / "disaggregation_diagnostics.csv",
    index=False,
)

continent_total_audit_all.to_csv(
    DISAGG_TABLES / "continent_total_audit.csv",
    index=False,
)

wxd_checks_all.to_csv(
    DISAGG_TABLES / "wxd_checks.csv",
    index=False,
)

if not negative_wxd_warnings_all.empty:
    negative_wxd_warnings_all.to_csv(
        DISAGG_TABLES / "negative_wxd_residual_warnings.csv",
        index=False,
    )

if not negative_distributed_clipping_all.empty:
    negative_distributed_clipping_all.to_csv(
        DISAGG_TABLES / "negative_distributed_values_clipped.csv",
        index=False,
    )

if not flagged_inconsistent_totals_all.empty:
    flagged_inconsistent_totals_all.to_csv(
        DISAGG_TABLES / "flagged_inconsistent_continent_totals.csv",
        index=False,
    )

print("\nSaved:")
print(f"  {data_final}/{_disagg_name}")
print(f"  {DISAGG_TABLES}/disaggregation_diagnostics.csv")
print(f"  {DISAGG_TABLES}/continent_total_audit.csv")
print(f"  {DISAGG_TABLES}/wxd_checks.csv")
if not negative_wxd_warnings_all.empty:
    print(f"  {DISAGG_TABLES}/negative_wxd_residual_warnings.csv")
if not negative_distributed_clipping_all.empty:
    print(f"  {DISAGG_TABLES}/negative_distributed_values_clipped.csv")
if not flagged_inconsistent_totals_all.empty:
    print(f"  {DISAGG_TABLES}/flagged_inconsistent_continent_totals.csv")


# %% [conservation invariant] domestic + non_domestic == raw_reported_total
#
# For every (year, iso_parent) reporter, verify that the sum of all output
# rows equals the raw reported "total" we expected the disaggregation to
# preserve. The reference total is:
#   - domestic (iso_partner == iso_parent in the raw input)
#   - + WXD value if the parent reported one
#   - or + sum of all reported continent codes / specific countries
# Only the IMPUTED variables are conservation-checked: the three gravity activity
# factors and the two profit columns (gravity conserves each (year, parent,
# source_aggregate) total, profit is rescaled to conserve it). The other CbCR
# variables are intentionally NOT imputed on distributed rows (total_revenues is
# floored to imputed sales; tax / related-party revenue / stated capital / entity
# counts / IP-holding are blank), so they are expected NOT to conserve and are
# excluded from the check.

print("\nConservation invariant check (imputed variables only):")
CONSERVED_VARS = [
    "n_employees",
    "unrelated_party_revenues",
    "tangible_assets_except_cash",
    "profit_loss_before_income_tax_corrected",
    "profit_loss_before_income_tax",
]
INVARIANT_ATOL = 1.0   # USD / counts; tolerance for floating-point summation
INVARIANT_RTOL = 1e-4

raw_input = cbcr_full.copy() if "cbcr_full" in dir() else None
if raw_input is not None:
    # Sum reported (per-parent-year, per variable) excluding sub-totals so we
    # don't double-count: domestic row + WXD row (if present) is the
    # canonical aggregate; otherwise sum the country + continent rows.
    invariant_fails = []
    for (yr, par), grp in cbcr_main_disaggregated.groupby(["year", "iso_parent"]):
        # Output sum (all output rows for this reporter)
        out_sum = grp[CBCR_VARS].sum()
        raw = raw_input[(raw_input["year"] == yr) & (raw_input["iso_parent"] == par)]
        if raw.empty:
            continue
        wxd_raw = raw[raw["iso_partner"] == "WXD"]
        dom_raw = raw[raw["iso_partner"] == par]
        if not wxd_raw.empty:
            ref_sum = (
                dom_raw[CBCR_VARS].sum().fillna(0)
                + wxd_raw[CBCR_VARS].sum().fillna(0)
            )
        else:
            # Without WXD, the raw input rows themselves are the reference
            # (continent codes + specific countries). The disaggregation
            # redistributes the continent codes to specific partners but the
            # parent-level sum is preserved.
            ref_sum = raw[CBCR_VARS].sum().fillna(0)
        for var in CONSERVED_VARS:
            ov = float(out_sum.get(var, 0) or 0)
            rv = float(ref_sum.get(var, 0) or 0)
            if abs(ov - rv) > max(INVARIANT_ATOL, INVARIANT_RTOL * max(abs(rv), 1.0)):
                invariant_fails.append({
                    "year": yr, "iso_parent": par, "variable": var,
                    "raw_total": rv, "output_total": ov, "diff": ov - rv,
                })
    if invariant_fails:
        ifd = pd.DataFrame(invariant_fails)
        ifd.to_csv(DISAGG_TABLES / "conservation_invariant_fails.csv", index=False)
        print(f"  FAIL: {len(invariant_fails)} (parent, year, variable) cells "
              f"failed conservation invariant")
        print(f"     details -> {DISAGG_TABLES}/conservation_invariant_fails.csv")
        # Top offenders
        worst = ifd.reindex(ifd['diff'].abs().sort_values(ascending=False).index).head(10)
        print(f"  Top 10 by absolute diff:")
        for _, r in worst.iterrows():
            print(f"    {int(r['year'])} {r['iso_parent']:<3s} {r['variable']:<40s} "
                  f"raw={r['raw_total']:>15,.1f} out={r['output_total']:>15,.1f} "
                  f"diff={r['diff']:>+12,.1f}")
    else:
        print("  PASS: every parent-year disaggregated total matches the raw "
              "reported total within tolerance")
else:
    print("  (raw input frame `cbcr_main_long` not in scope; skip)")


# %%
print(cbcr_main_disaggregated.columns.tolist())

# %%
