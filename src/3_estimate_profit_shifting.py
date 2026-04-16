# %% [0] Imports
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import product
from config import *

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format


# %% [1] Run settings
# 1.1 Core settings for the current session
PROFIT_VAR = "profit_loss_before_income_tax_corrected"
ETR_THRESHOLDS = [np.inf]

OUTPUT_ROOT = Path(output_tables) / "unitary_taxation"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


# %% [1.2] Formula specifications
# Each formula is defined by the variables included in the apportionment key
# and the corresponding weights.

FORMULAS = [
    {
        "name": "employees_payroll",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [0.5, 0.0, 0.0, 0.5],
    },
    {
        "name": "ccctb",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [1 / 6, 1 / 3, 1 / 3, 1 / 6],
    },
    {
        "name": "double_weighted_sales",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [0.25, 0.5, 0.25, 0.0],
    },
    {
        "name": "sales_employees",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [0.5, 0.5, 0.0, 0.0],
    },
]


# %% [1.3] Tax-rate specifications
# We run three versions for each formula:
# - losses with CIT and gains with ETR
# - losses with ETR and gains with ETR
# - losses with CIT and gains with CIT

RATE_MODES = [
    {
        "name": "loss_cit_gain_etr",
        "loss_rate_col": "cit",
        "gain_rate_col": "etr_average_corrected",
    },
    {
        "name": "loss_etr_gain_etr",
        "loss_rate_col": "etr_average_corrected",
        "gain_rate_col": "etr_average_corrected",
    },
    {
        "name": "loss_cit_gain_cit",
        "loss_rate_col": "cit",
        "gain_rate_col": "cit",
    },
]


# %% [1.4] Input samples
# We run the same estimation on:
# - the disaggregated sample
# - the raw CbCR sample from the first cleaning notebook

INPUT_SAMPLES = {
    "disaggregated_data": Path(data_final) / "cbcr_main_disaggregated.csv",
    "raw_cbcr": Path(data_final) / "cbcr_main_allsubgroupsonly.csv",
}


# %% [2] Helper functions
# 2.1 General checks and formatting helpers


def check_duplicates(df, name):
    if df.duplicated().any():
        print(f"Warning: {name} contains duplicate rows.")
    else:
        print(f"No duplicates found in {name}.")


def format_threshold_for_name(x):
    if pd.isna(x):
        return "na"
    if np.isinf(x):
        return "inf"
    x = float(x)
    if x.is_integer():
        return str(int(x))
    return str(x).replace(".", "_")


def make_file_stub(formula_name, etr_threshold, rate_mode_name):
    return (
        f"{formula_name}"
        f"__etrmax_{format_threshold_for_name(etr_threshold)}"
        f"__{rate_mode_name}"
    )


def ensure_output_dir(sample_name):
    output_dir = OUTPUT_ROOT / sample_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# %% [2.2] Validation helpers


def validate_formula_spec(formula_spec):
    if "name" not in formula_spec:
        raise ValueError("Each formula specification must have a 'name'.")
    if "formula_vars" not in formula_spec or "weights" not in formula_spec:
        raise ValueError(
            f"Formula '{formula_spec.get('name', 'UNKNOWN')}' must define "
            "'formula_vars' and 'weights'."
        )
    if len(formula_spec["formula_vars"]) != len(formula_spec["weights"]):
        raise ValueError(
            f"Formula '{formula_spec['name']}' has different lengths for "
            "'formula_vars' and 'weights'."
        )
    if sum(formula_spec["weights"]) <= 0:
        raise ValueError(
            f"Formula '{formula_spec['name']}' must have at least one positive weight."
        )


def validate_input_data(cbcr_data, sample_name):
    required_cols = [
        "year",
        "iso_parent",
        "iso_partner",
        "partner_jurisdiction",
        "profit_loss_before_income_tax_corrected",
        "etr_average_corrected",
        "cit",
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
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

    missing_cols = [col for col in required_cols if col not in cbcr_data.columns]
    if missing_cols:
        raise ValueError(
            f"Missing required columns in sample '{sample_name}': {missing_cols}"
        )


# %% [2.3] Sample preparation helpers


def keep_actual_country_rows(df):
    """
    Keep only rows where the partner jurisdiction is an actual country/jurisdiction.
    This removes WXD, W_O, continent groups, residual groups, and similar aggregates.
    """
    out = df.copy()

    out = out.loc[out["iso_partner"].notna()].copy()
    out = out.loc[~out["iso_partner"].isin(non_countries)].copy()

    if "year" in out.columns:
        out["year"] = pd.to_numeric(out["year"], errors="coerce")

    return out


def coerce_numeric_columns(df, columns):
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def load_input_samples():
    """
    Load, clean, and validate all input samples.
    """
    numeric_cols = [
        "year",
        "profit_loss_before_income_tax_corrected",
        "etr_average_corrected",
        "cit",
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "tax_revenue_current_usd",
        "gvt_health_expenditure",
        "wage_monthly",
    ]

    samples = {}

    for sample_name, file_path in INPUT_SAMPLES.items():
        df = pd.read_csv(file_path)
        df = keep_actual_country_rows(df)
        df = coerce_numeric_columns(df, numeric_cols)
        validate_input_data(df, sample_name)

        print(f"\nLoaded sample: {sample_name}")
        print(f"  Rows: {len(df):,}")
        print(f"  Years: {sorted(df['year'].dropna().astype(int).unique())}")

        samples[sample_name] = df

    return samples


# %% [3] Core estimation functions
# 3.1 Misalignment calculation


def calculate_misalignment(
    cbcr_data,
    formula_vars,
    weights,
    profit_var="profit_loss_before_income_tax_corrected",
    etr_max=1.0,
):
    """
    Calculate misalignment for one year of data.

    Steps:
    1. Build within-parent shares for the variables in the chosen formula.
    2. Combine them into an economic activity share.
    3. Calculate theoretical profit from that share.
    4. Calculate misaligned profit as reported minus theoretical profit.
    5. Set positive misalignment to zero where the destination ETR exceeds the threshold.
    6. Rescale negative misalignment within parent so that total misalignment sums to zero.
    """
    df = cbcr_data.copy()

    if profit_var not in df.columns:
        raise ValueError(f"Profit variable '{profit_var}' not found in input data.")

    active_specs = []
    for var, weight in zip(formula_vars, weights):
        if var is None or weight <= 0:
            continue

        if var not in df.columns:
            raise ValueError(f"Formula variable '{var}' not found in input data.")

        df[var] = pd.to_numeric(df[var], errors="coerce")
        df.loc[df[var] < 0, var] = 0

        total_by_parent = df.groupby("iso_parent")[var].transform("sum")
        share_col = f"share_{var}"

        df[share_col] = np.where(total_by_parent > 0, df[var] / total_by_parent, 0)
        active_specs.append((share_col, weight))

    if not active_specs:
        raise ValueError("No active variables with positive weights found.")

    df["economic_activity_partner_of_parent"] = 0.0
    for share_col, weight in active_specs:
        df["economic_activity_partner_of_parent"] += df[share_col] * weight

    total_activity_by_parent = df.groupby("iso_parent")[
        "economic_activity_partner_of_parent"
    ].transform("sum")

    df["share_economy_partner_of_parent"] = np.where(
        total_activity_by_parent > 0,
        df["economic_activity_partner_of_parent"] / total_activity_by_parent,
        0,
    )

    total_profit_by_parent = df.groupby("iso_parent")[profit_var].transform("sum")
    df["theoretical_profit"] = (
        df["share_economy_partner_of_parent"] * total_profit_by_parent
    )
    df["misaligned_profit"] = df[profit_var] - df["theoretical_profit"]

    df.loc[
        (df["misaligned_profit"] > 0) & (df["etr_average_corrected"] > etr_max),
        "misaligned_profit",
    ] = 0

    def adjust_misalignment(group):
        total_neg = group.loc[group["misaligned_profit"] < 0, "misaligned_profit"].sum()
        total_pos = group.loc[group["misaligned_profit"] > 0, "misaligned_profit"].sum()

        if total_neg != 0:
            factor = -total_pos / total_neg
            group.loc[group["misaligned_profit"] < 0, "misaligned_profit"] *= factor

        return group

    adjusted_parts = []
    for _, group in df.groupby("iso_parent", sort=False):
        adjusted_parts.append(adjust_misalignment(group.copy()))

    df = pd.concat(adjusted_parts, ignore_index=True)
    return df


# %% [3.2] Country aggregation


def aggregate_country_results(
    misalignment_df,
    year,
    loss_rate_col,
    gain_rate_col,
    formula_name,
    etr_threshold,
    rate_mode_name,
    sample_name,
):
    """
    Aggregate misalignment results to the country level.
    """
    metadata_cols = [
        "partner_jurisdiction",
        "cit",
        "etr_average_corrected",
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

    unique_partners = misalignment_df.groupby("iso_partner", as_index=False)[
        metadata_cols
    ].first()

    country_results = misalignment_df.groupby("iso_partner", as_index=False).agg(
        negative_misalignment=("misaligned_profit", lambda x: x[x < 0].sum()),
        positive_misalignment=("misaligned_profit", lambda x: x[x > 0].sum()),
        theoretical_profit=("theoretical_profit", "sum"),
        reported_profit=(PROFIT_VAR, "sum"),
    )

    country_results["negative_misalignment"] = (
        -country_results["negative_misalignment"] / 1e6
    )
    country_results["positive_misalignment"] = (
        country_results["positive_misalignment"] / 1e6
    )
    country_results["theoretical_profit"] = country_results["theoretical_profit"] / 1e6
    country_results["reported_profit"] = country_results["reported_profit"] / 1e6

    country_results = country_results.merge(
        unique_partners, on="iso_partner", how="left"
    )

    country_results["tax_revenue_loss"] = (
        country_results["negative_misalignment"] * country_results[loss_rate_col]
    )
    country_results["tax_revenue_gain"] = (
        country_results["positive_misalignment"] * country_results[gain_rate_col]
    )

    total_positive = country_results["positive_misalignment"].sum()
    total_loss = country_results["tax_revenue_loss"].sum()

    country_results["tax_revenue_loss_caused_pct_of_total"] = np.where(
        total_positive > 0,
        country_results["positive_misalignment"] / total_positive,
        0,
    )
    country_results["tax_revenue_loss_caused_usd"] = (
        country_results["tax_revenue_loss_caused_pct_of_total"] * total_loss
    )
    country_results["tax_revenue_loss_suffered_pct_of_total"] = np.where(
        total_loss > 0,
        country_results["tax_revenue_loss"] / total_loss,
        0,
    )

    country_results["year"] = year
    country_results["formula_name"] = formula_name
    country_results["etr_threshold"] = etr_threshold
    country_results["rate_mode"] = rate_mode_name
    country_results["loss_rate_col"] = loss_rate_col
    country_results["gain_rate_col"] = gain_rate_col
    country_results["sample_name"] = sample_name

    return country_results


# %% [3.3] One-year runner


def run_estimation_year(
    year,
    cbcr_data,
    formula_spec,
    rate_mode,
    etr_threshold,
    sample_name,
):
    """
    Run the estimation for one year, one formula, one tax-rate mode, and one sample.
    """
    cbcr_year = cbcr_data.loc[cbcr_data["year"] == year].copy()

    if cbcr_year.empty:
        return None, None, None

    misalignment = calculate_misalignment(
        cbcr_data=cbcr_year,
        formula_vars=formula_spec["formula_vars"],
        weights=formula_spec["weights"],
        profit_var=PROFIT_VAR,
        etr_max=etr_threshold,
    )
    misalignment["year"] = year
    misalignment["formula_name"] = formula_spec["name"]
    misalignment["etr_threshold"] = etr_threshold
    misalignment["rate_mode"] = rate_mode["name"]
    misalignment["loss_rate_col"] = rate_mode["loss_rate_col"]
    misalignment["gain_rate_col"] = rate_mode["gain_rate_col"]
    misalignment["sample_name"] = sample_name

    country_results = aggregate_country_results(
        misalignment_df=misalignment,
        year=year,
        loss_rate_col=rate_mode["loss_rate_col"],
        gain_rate_col=rate_mode["gain_rate_col"],
        formula_name=formula_spec["name"],
        etr_threshold=etr_threshold,
        rate_mode_name=rate_mode["name"],
        sample_name=sample_name,
    )

    aggregate_row = {
        "sample_name": sample_name,
        "formula_name": formula_spec["name"],
        "etr_threshold": etr_threshold,
        "rate_mode": rate_mode["name"],
        "loss_rate_col": rate_mode["loss_rate_col"],
        "gain_rate_col": rate_mode["gain_rate_col"],
        "year": year,
        "total_shifted_musd": country_results["positive_misalignment"].sum(),
        "total_tax_loss_musd": country_results["tax_revenue_loss"].sum(),
        "total_tax_gain_musd": country_results["tax_revenue_gain"].sum(),
    }

    return misalignment, country_results, aggregate_row


# %% [4] Load and validate input samples
# 4.1 Load both samples

samples = load_input_samples()


# %% [4.2] Validate formulas and define years to run

for formula_spec in FORMULAS:
    validate_formula_spec(formula_spec)

years_requested = list(range(first_year, first_year + n_years))

sample_years = {}
for sample_name, df in samples.items():
    years_available = sorted(df["year"].dropna().astype(int).unique())
    years_to_run = [year for year in years_requested if year in years_available]

    sample_years[sample_name] = years_to_run

    print(f"\nSample: {sample_name}")
    print(f"  Years requested: {years_requested}")
    print(f"  Years run: {years_to_run}")


# %% [5] Run all specifications
# 5.1 Run all combinations of:
# - sample
# - formula
# - ETR threshold
# - tax-rate mode

run_summary_rows = []

for sample_name, df in samples.items():
    print("\n" + "=" * 100)
    print(f"RUNNING SAMPLE: {sample_name}")
    print("=" * 100)

    output_dir = ensure_output_dir(sample_name)

    for formula_spec, etr_threshold, rate_mode in product(
        FORMULAS, ETR_THRESHOLDS, RATE_MODES
    ):
        file_stub = make_file_stub(
            formula_name=formula_spec["name"],
            etr_threshold=etr_threshold,
            rate_mode_name=rate_mode["name"],
        )

        print("\n" + "-" * 100)
        print(
            f"Formula: {formula_spec['name']} | "
            f"ETR max: {etr_threshold} | "
            f"Rate mode: {rate_mode['name']}"
        )
        print("-" * 100)

        results_country = []
        results_misalignment = []
        results_aggregate = []

        for year in sample_years[sample_name]:
            misalignment, country_results, aggregate_row = run_estimation_year(
                year=year,
                cbcr_data=df,
                formula_spec=formula_spec,
                rate_mode=rate_mode,
                etr_threshold=etr_threshold,
                sample_name=sample_name,
            )

            if country_results is not None:
                results_country.append(country_results)
                results_misalignment.append(misalignment)
                results_aggregate.append(aggregate_row)

                print(
                    f"  {year}: shifted {aggregate_row['total_shifted_musd']:,.0f}M USD | "
                    f"tax loss {aggregate_row['total_tax_loss_musd']:,.0f}M USD | "
                    f"tax gain {aggregate_row['total_tax_gain_musd']:,.0f}M USD"
                )
            else:
                print(f"  {year}: no data")

        if results_country:
            country_all_years = pd.concat(results_country, ignore_index=True)
        else:
            country_all_years = pd.DataFrame()

        if results_misalignment:
            misalignment_all_years = pd.concat(results_misalignment, ignore_index=True)
        else:
            misalignment_all_years = pd.DataFrame()

        aggregate_df = pd.DataFrame(results_aggregate)

        country_all_years.to_csv(
            output_dir / f"country_estimates__{file_stub}.csv",
            index=False,
        )
        misalignment_all_years.to_csv(
            output_dir / f"misalignment__{file_stub}.csv",
            index=False,
        )
        aggregate_df.to_csv(
            output_dir / f"aggregate_results__{file_stub}.csv",
            index=False,
        )

        run_summary_rows.append(
            {
                "sample_name": sample_name,
                "formula_name": formula_spec["name"],
                "etr_threshold": etr_threshold,
                "rate_mode": rate_mode["name"],
                "loss_rate_col": rate_mode["loss_rate_col"],
                "gain_rate_col": rate_mode["gain_rate_col"],
                "n_country_rows": len(country_all_years),
                "n_misalignment_rows": len(misalignment_all_years),
                "n_years": len(aggregate_df),
                "total_shifted_musd_all_years": (
                    aggregate_df["total_shifted_musd"].sum()
                    if not aggregate_df.empty
                    else 0
                ),
                "total_tax_loss_musd_all_years": (
                    aggregate_df["total_tax_loss_musd"].sum()
                    if not aggregate_df.empty
                    else 0
                ),
                "total_tax_gain_musd_all_years": (
                    aggregate_df["total_tax_gain_musd"].sum()
                    if not aggregate_df.empty
                    else 0
                ),
                "country_file": str(output_dir / f"country_estimates__{file_stub}.csv"),
                "misalignment_file": str(output_dir / f"misalignment__{file_stub}.csv"),
                "aggregate_file": str(
                    output_dir / f"aggregate_results__{file_stub}.csv"
                ),
            }
        )


# %% [6] Save and display run summary
run_summary = pd.DataFrame(run_summary_rows)

run_summary.to_csv(
    OUTPUT_ROOT / "run_summary.csv",
    index=False,
)

print("\n" + "=" * 100)
print("RUN SUMMARY")
print("=" * 100)

if not run_summary.empty:
    print(run_summary.to_string(index=False))
else:
    print("No results produced.")
