# %% [0] Home-group unitary-taxation estimate (US or EU-27 multinationals).
#
# Self-contained sibling of `src/5_estimate_profit_shifting.py`. It runs the
# exact same UT formulary-apportionment machinery but on the subset of the
# baseline disaggregated CbCR whose parent jurisdiction is in the selected HOME
# GROUP. Because `calculate_misalignment` already estimates each parent
# independently (everything is grouped by `iso_parent`), restricting the input
# to a parent set yields a clean view of that group's MNEs — who they shift
# profit into and which jurisdictions lose tax to them.
#
# Select the group with the HOME_GROUP env var:
#   HOME_GROUP=USA   → US multinationals      → output/us_multinationals/
#   HOME_GROUP=EU27  → EU-27 multinationals   → output/eu_multinationals/
# Figure labels follow HOME_LABEL ("US"/"EU"). The script was first built as the
# US-only project, hence the directory name `src/us_only/`.
#
# Outputs mirror script 5's full per-spec format (country_estimates,
# misalignment, aggregate_results, run_summary, summary figures).
#
# This file does NOT modify script 5. Set HOME_GROUP / RUN_DATASET /
# REPORTED_ONLY env vars to vary the run (see below).
import os
import sys
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from itertools import product

# On Windows, stdout defaults to cp1252 and crashes when any printed line
# embeds the Arabic characters from the project path (the long run_summary
# table at the end prints rows containing the absolute file paths). Use
# UTF-8 with error-replacement so the run reaches the figure / summary
# export stages.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# This script lives in src/us_only/, one level below src/ where config.py and
# the shared pipeline modules live. Put src/ on the path so `from config
# import *` (and the helpers it pulls in) resolve exactly as they do for the
# top-level scripts. config.py anchors all data/output paths to the project
# root via its own __file__, so this works regardless of CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import *

pd.set_option("display.max_columns", None)
pd.options.display.float_format = "{:,.2f}".format


# %% [1] Run settings
# 1.1 Home group — which MNEs to analyse, by parent jurisdiction.
#
# UT misalignment is computed per `iso_parent`, so restricting the input CbCR to
# a parent set yields a clean view of that group's MNEs. Pick the group with the
# HOME_GROUP env var; each writes to its own output topic. (UK/GBR is
# deliberately not offered: it is a bad reporter for 2017-2022, so its CbCR is
# mostly aggregates and would distort the picture.)
EU27 = {
    "AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA",
    "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD",
    "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE",
}
HOME_GROUPS = {
    "USA":  {"parents": {"USA"}, "label": "US", "topic": "us_multinationals"},
    "EU27": {"parents": set(EU27), "label": "EU", "topic": "eu_multinationals"},
}
HOME_GROUP = os.environ.get("HOME_GROUP", "USA")
if HOME_GROUP not in HOME_GROUPS:
    raise ValueError(f"HOME_GROUP must be one of {list(HOME_GROUPS)}; got {HOME_GROUP!r}")
_home = HOME_GROUPS[HOME_GROUP]
PARENT_SET = _home["parents"]   # parent jurisdictions kept in the sample
HOME_LABEL = _home["label"]     # used in figure titles/notes ("US" / "EU")
HOME_TOPIC = _home["topic"]     # output/<topic>/

# 1.2 Dataset configuration (baseline disaggregated CbCR only — the standard
# headline UT input). The output topic follows the home group so US and EU runs
# never collide.
DATASET_CONFIGS = {
    "disaggregated": {
        "input_file": "cbcr_main_disaggregated.csv",
        "profit_var": "profit_loss_before_income_tax_corrected",
        "tax_var": "income_tax_paid_on_cash_basis",
        "etr_suffix": "corrected",
        "output_topic": HOME_TOPIC,
    },
}

RUN_DATASET = os.environ.get("RUN_DATASET", "disaggregated")
# <-- change RUN_DATASET (in code or env var) per run.

# REPORTED_ONLY toggle. When True, filter input CbCR rows to
# `is_distributed == 0` — i.e., keep only directly-reported country rows and
# drop all rows that came from disaggregating bad-reporter aggregates.
#
# DEFAULT IS OFF here (unlike script 5, where it defaults on). The whole point
# of the baseline *disaggregated* dataset is to include the disaggregated
# partner cells — for the US these are ~600 rows / ~$0.8tn of profit in
# countries the US reported only inside regional/"Other" aggregates (small
# states and havens). Dropping them would collapse the run back to reported-
# only and lose much of the US tax-haven footprint. Set REPORTED_ONLY=1 for a
# no-imputation sensitivity view (output goes to a `_reported` suffixed topic).
REPORTED_ONLY = os.environ.get("REPORTED_ONLY", "0") not in ("0", "false", "False", "")

# Minimum-ETR threshold for treating over-reporting as profit shifting. With
# ETR_MAX=inf (default) ALL misalignment is captured regardless of the
# destination's ETR and the balancing rescale is off. With ETR_MAX=0.15 only
# profit shifted into sub-15%-ETR destinations counts (haven-only), and the
# rescale is on. Set the env var ETR_MAX=inf or =0.15; each writes to its own
# output topic / shared-folder prefix (etr15 tag) so both can coexist.
_etr_max_env = os.environ.get("ETR_MAX", "inf").strip().lower()
if _etr_max_env in ("inf", "infinity", "none", ""):
    _ETR_MAX = np.inf
    ETR_TAG = "inf"
else:
    _ETR_MAX = float(_etr_max_env)
    ETR_TAG = f"etr{int(round(_ETR_MAX * 100))}"   # 0.15 -> 'etr15'

_cfg = DATASET_CONFIGS[RUN_DATASET]
PROFIT_VAR = _cfg["profit_var"]
TAX_VAR = _cfg["tax_var"]
ETR_SUFFIX = _cfg["etr_suffix"]
# Topic suffix: inf is left untagged (the established us_/eu_multinationals
# folders); a finite threshold gets an _etrNN suffix so the two configs don't
# overwrite each other.
_OUTPUT_TOPIC = (
    _cfg["output_topic"]
    + ("_reported" if REPORTED_ONLY else "")
    + ("" if ETR_TAG == "inf" else f"_{ETR_TAG}")
)

# Partner-year ETR columns derived from the active suffix. The
# parent-partner pair ETR is a diagnostic (never used in UT) — kept available
# in column ordering and validation, but not in ETR_SPECS.
ETR_FAMILY_PARTNER = [
    f"etr_average_{ETR_SUFFIX}",
    f"etr_partner_median_{ETR_SUFFIX}",
    f"etr_partner_p25_{ETR_SUFFIX}",
    f"etr_partner_min_{ETR_SUFFIX}",
]
ETR_COL_PAIR = f"etr_parent_partner_{ETR_SUFFIX}"
ETR_COL_DOMESTIC = f"etr_domestic_{ETR_SUFFIX}"
ETR_COL_FOREIGN = f"etr_foreign_{ETR_SUFFIX}"
ETR_COL_AVERAGE = f"etr_average_{ETR_SUFFIX}"
ETR_COL_MEDIAN = f"etr_partner_median_{ETR_SUFFIX}"
ETR_COL_P25 = f"etr_partner_p25_{ETR_SUFFIX}"
ETR_COL_MIN = f"etr_partner_min_{ETR_SUFFIX}"

ETR_THRESHOLDS = [_ETR_MAX]

OUTPUT_TABLES, OUTPUT_FIGURES = output_dirs(_OUTPUT_TOPIC)
# OUTPUT_ROOT keeps backward-compatible naming as the per-sample tables root.
OUTPUT_ROOT = OUTPUT_TABLES

# 1.2 Optional execution switches
RUN_BILATERALS = False


# %% [1.3] Formula specifications
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
    {
        "name": "three_factors",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
        ],
        "weights": [1 / 3, 1 / 3, 1 / 3, 0.0],
    },
    # ── 5-factor formulas: add a resource_activity factor that is a SUBSTITUTE
    # for the resource exclusion/correction logic. These are designed for the
    # incl_resource dataset (where pre-profit resource payments are added back
    # to the profit pool); the resource factor pulls apportionment toward
    # source countries so they don't end up "losing" their resource share to
    # other countries via formula apportionment. Weight is rebalanced from
    # the SOTJ-default 50/50 employees-payroll base.
    {
        "name": "employees_payroll_resource_10pct",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
            "resource_factor_usd",
        ],
        "weights": [0.45, 0.0, 0.0, 0.45, 0.10],
    },
    {
        "name": "employees_payroll_resource_20pct",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
            "resource_factor_usd",
        ],
        "weights": [0.40, 0.0, 0.0, 0.40, 0.20],
    },
    {
        "name": "employees_payroll_resource_30pct",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
            "resource_factor_usd",
        ],
        "weights": [0.35, 0.0, 0.0, 0.35, 0.30],
    },
    {
        "name": "employees_payroll_resource_50pct",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
            "resource_factor_usd",
        ],
        "weights": [0.25, 0.0, 0.0, 0.25, 0.50],
    },
    {
        "name": "ccctb_with_resources_30pct",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
            "resource_factor_usd",
        ],
        "weights": [1 / 6 * 0.70, 1 / 3 * 0.70, 1 / 3 * 0.70, 1 / 6 * 0.70, 0.30],
    },
    {
        "name": "three_factors_with_resources_30pct",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
            "resource_factor_usd",
        ],
        "weights": [1 / 3 * 0.70, 1 / 3 * 0.70, 1 / 3 * 0.70, 0.0, 0.30],
    },
    {
        "name": "double_weighted_sales_with_resources_30pct",
        "formula_vars": [
            "n_employees",
            "unrelated_party_revenues",
            "tangible_assets_except_cash",
            "payroll",
            "resource_factor_usd",
        ],
        "weights": [0.25 * 0.70, 0.50 * 0.70, 0.25 * 0.70, 0.0, 0.30],
    },
    # ── Alpha-blended scenario-4 variants (Option A′, 2026-05-14). Each
    # parent's profit is allocated by a per-parent blend:
    #   share = α[P] × primary_share(5-factor) + (1 − α[P]) × secondary_share(4-factor)
    # where α[P] = Σ resource_factor_usd[P, ·, ·] / Σ total_revenues[P, ·, ·]
    # (computed in compute_alpha_per_parent and merged onto the sample as
    # `alpha_resource_per_parent`). This avoids the over-allocation of 30%
    # of every MNE's profits to extractive partners regardless of whether
    # that MNE has any extractive activity.
    {
        "name": "employees_payroll_resource_alpha_10pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.45, 0.0, 0.0, 0.45, 0.10],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.5, 0.0, 0.0, 0.5],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "employees_payroll_resource_alpha_20pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.40, 0.0, 0.0, 0.40, 0.20],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.5, 0.0, 0.0, 0.5],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "employees_payroll_resource_alpha_30pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.35, 0.0, 0.0, 0.35, 0.30],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.5, 0.0, 0.0, 0.5],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "employees_payroll_resource_alpha_50pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.25, 0.0, 0.0, 0.25, 0.50],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.5, 0.0, 0.0, 0.5],
        "alpha_col": "alpha_resource_per_parent",
    },
    # ── Alpha-blended 5-factor formulas across the four 4-factor families.
    # Within each scenario in script 8 we hold α fixed (substitution = 30%,
    # additive = 10%) and vary the family. The α controls how much of the
    # primary 5-factor formula contributes vs the family-specific 4-factor
    # secondary. Primary weights: family × (1 − α) + resource_factor × α.
    {
        "name": "ccctb_resource_alpha_30pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [1/6 * 0.70, 1/3 * 0.70, 1/3 * 0.70, 1/6 * 0.70, 0.30],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [1/6, 1/3, 1/3, 1/6],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "ccctb_resource_alpha_10pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [1/6 * 0.90, 1/3 * 0.90, 1/3 * 0.90, 1/6 * 0.90, 0.10],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [1/6, 1/3, 1/3, 1/6],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "three_factors_resource_alpha_30pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [1/3 * 0.70, 1/3 * 0.70, 1/3 * 0.70, 0.0, 0.30],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [1/3, 1/3, 1/3, 0.0],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "three_factors_resource_alpha_10pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [1/3 * 0.90, 1/3 * 0.90, 1/3 * 0.90, 0.0, 0.10],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [1/3, 1/3, 1/3, 0.0],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "double_weighted_sales_resource_alpha_30pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.25 * 0.70, 0.50 * 0.70, 0.25 * 0.70, 0.0, 0.30],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.25, 0.50, 0.25, 0.0],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "double_weighted_sales_resource_alpha_10pct",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.25 * 0.90, 0.50 * 0.90, 0.25 * 0.90, 0.0, 0.10],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.25, 0.50, 0.25, 0.0],
        "alpha_col": "alpha_resource_per_parent",
    },
    # ── Scenario 5: "resource as additional equal-weight factor"
    # Instead of 10% or 30% weight on resources within the primary 5-factor,
    # treat resources as just one more factor in the formula, weighted in line
    # with each family's structure:
    #   - SOTJ:  3 equal factors (employees, payroll, resources) at 1/3 each
    #   - CCCTB: 4 factor "groups" at 25% each — (employees+payroll, sales,
    #            assets, resources). Within labour, employees and payroll
    #            still share equally → 1/8 / 1/4 / 1/4 / 1/8 / 1/4.
    #   - Three-factor: 4 equal factors (employees, sales, assets, resources).
    #   - Double-weighted sales: 5 factors with sales still double-weighted
    #            relative to the others → 0.2 / 0.4 / 0.2 / 0 / 0.2.
    # Same α-blending logic as the other alpha-blended formulas — applied
    # only to the extractive share α[P] of each parent's profit.
    {
        "name": "employees_payroll_resource_alpha_equal",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [1/3, 0.0, 0.0, 1/3, 1/3],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.5, 0.0, 0.0, 0.5],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "ccctb_resource_alpha_equal",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.125, 0.25, 0.25, 0.125, 0.25],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [1/6, 1/3, 1/3, 1/6],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "three_factors_resource_alpha_equal",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.25, 0.25, 0.25, 0.0, 0.25],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [1/3, 1/3, 1/3, 0.0],
        "alpha_col": "alpha_resource_per_parent",
    },
    {
        "name": "double_weighted_sales_resource_alpha_equal",
        "formula_vars": ["n_employees", "unrelated_party_revenues",
                         "tangible_assets_except_cash", "payroll", "resource_factor_usd"],
        "weights": [0.2, 0.4, 0.2, 0.0, 0.2],
        "secondary_formula_vars": ["n_employees", "unrelated_party_revenues",
                                   "tangible_assets_except_cash", "payroll"],
        "secondary_weights": [0.25, 0.50, 0.25, 0.0],
        "alpha_col": "alpha_resource_per_parent",
    },
]


# %% [1.4] ETR specifications — built from the active ETR_SUFFIX.
# etr_parent_partner_{suffix} is intentionally NOT a UT spec: it is missing
# on distributed (is_distributed=1) rows by design. The column still flows
# through the pipeline as a diagnostic — kept in validate_input_data,
# load_input_samples, and output column ordering — but not as an ETR over
# which UT estimates are computed.
ETR_SPECS_FULL = [
    {"name": "average", "etr_col": ETR_COL_AVERAGE},
    {"name": "median",  "etr_col": ETR_COL_MEDIAN},
    {"name": "p25",     "etr_col": ETR_COL_P25},
    {"name": "minimum", "etr_col": ETR_COL_MIN},
]
ETR_SPECS_MINIMAL = [  # only what `8_four_scenario_report.py` consumes
    {"name": "average", "etr_col": ETR_COL_AVERAGE},
]


# %% [1.5] Tax-rate mode templates
RATE_MODE_TEMPLATES_FULL = [
    {
        "name": "loss_cit_gain_etr",
        "loss_rate_kind": "cit",
        "gain_rate_kind": "etr",
    },
    {
        "name": "loss_etr_gain_etr",
        "loss_rate_kind": "etr",
        "gain_rate_kind": "etr",
    },
    {
        "name": "loss_cit_gain_cit",
        "loss_rate_kind": "cit",
        "gain_rate_kind": "cit",
    },
]
RATE_MODE_TEMPLATES_MINIMAL = [  # only what `8_four_scenario_report.py` consumes
    {"name": "loss_cit_gain_etr", "loss_rate_kind": "cit", "gain_rate_kind": "etr"},
    {"name": "loss_etr_gain_etr", "loss_rate_kind": "etr", "gain_rate_kind": "etr"},
    # CIT/CIT — both legs at statutory CIT. Needed for countries (e.g. South
    # Sudan) whose effective tax rate is degenerate (sign-flipping profit base
    # → ETR clipped to 0), where mixing ETR and CIT legs decouples the revenue
    # sign from the tax-base sign. A single consistent rate keeps them aligned.
    {"name": "loss_cit_gain_cit", "loss_rate_kind": "cit", "gain_rate_kind": "cit"},
]


# Toggle (2026-05-14): trim ETR × rate-mode combinations to only what the
# five-scenario report (script 8) actually consumes. Switching to MINIMAL
# reduces the spec count per formula from 12 → 2 (6× faster UT runs).
# Set MINIMAL = False if you need the full set (e.g., for the
# winners-losers / loss-sensitivity tables that span more specs).
MINIMAL = True
ETR_SPECS = ETR_SPECS_MINIMAL if MINIMAL else ETR_SPECS_FULL
RATE_MODE_TEMPLATES = RATE_MODE_TEMPLATES_MINIMAL if MINIMAL else RATE_MODE_TEMPLATES_FULL


# %% [1.6] Input samples — single sample per run, driven by RUN_DATASET.
INPUT_SAMPLES = {
    RUN_DATASET: Path(data_final) / _cfg["input_file"],
}


# %% [2] Helper functions
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


def make_file_stub(formula_name, etr_name, etr_threshold, rate_mode_name):
    return (
        f"{formula_name}"
        f"__etrdef_{etr_name}"
        f"__etrmax_{format_threshold_for_name(etr_threshold)}"
        f"__{rate_mode_name}"
    )


def ensure_output_dir(sample_name):
    output_dir = OUTPUT_ROOT / sample_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _longpath(p):
    """On Windows, prefix paths > 240 chars with the \\\\?\\ long-path namespace
    so open() bypasses the legacy 260-char MAX_PATH limit. The OneDrive +
    Arabic-character project root pushes some country_estimates filenames
    (esp. `_alpha_10pct`) over the limit. A no-op on non-Windows."""
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s


def resolve_rate_mode(rate_mode_template, etr_spec):
    if rate_mode_template["loss_rate_kind"] == "etr":
        loss_rate_col = etr_spec["etr_col"]
    else:
        loss_rate_col = "cit"

    if rate_mode_template["gain_rate_kind"] == "etr":
        gain_rate_col = etr_spec["etr_col"]
    else:
        gain_rate_col = "cit"

    return {
        "name": rate_mode_template["name"],
        "loss_rate_col": loss_rate_col,
        "gain_rate_col": gain_rate_col,
        "loss_rate_kind": rate_mode_template["loss_rate_kind"],
        "gain_rate_kind": rate_mode_template["gain_rate_kind"],
    }


def classify_income_group(value):
    if pd.isna(value):
        return "other_or_missing"

    s = str(value).strip().lower()
    s = s.replace(" ", "_").replace("-", "_")

    if s == "low_income":
        return "low_income"

    if s in {"lower_middle_income", "upper_middle_income", "middle_income"}:
        return "middle_income"

    if s == "high_income":
        return "high_income"

    return "other_or_missing"


AGGREGATE_INCOME_GROUPS = [
    "global",
    "low_income",
    "middle_income",
    "high_income",
    "other_or_missing",
]


INCOME_LABELS = {
    "global": "Global",
    "low_income": "Low income",
    "middle_income": "Middle income",
    "high_income": "High income",
    "other_or_missing": "Other / missing",
}


def safe_series_sum(series):
    return series.sum(min_count=1)


def make_aggregate_row(
    df,
    year,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    loss_rate_col,
    gain_rate_col,
    sample_name,
    income_group_bucket,
):
    if df.empty:
        n_countries = 0
        total_shifted_musd = 0
        total_tax_loss_musd = 0
        total_tax_gain_musd = 0
        total_revenue_gain_from_ut_musd = 0
        mean_revenue_gain_from_ut_musd = np.nan
        total_current_tax_paid_cash_musd = np.nan
        revenue_gain_from_ut_pct_of_current_tax_paid = np.nan
        tax_revenue_loss_pct_of_current_tax_paid = np.nan
        tax_revenue_gain_pct_of_current_tax_paid = np.nan
    else:
        n_countries = df["iso_partner"].nunique()
        total_shifted_musd = df["positive_misalignment"].sum()
        total_tax_loss_musd = df["tax_revenue_loss"].sum()
        total_tax_gain_musd = df["tax_revenue_gain"].sum()
        total_revenue_gain_from_ut_musd = df["revenue_gain_from_ut"].sum()
        mean_revenue_gain_from_ut_musd = df["revenue_gain_from_ut"].mean()
        total_current_tax_paid_cash_musd = safe_series_sum(
            df["current_tax_paid_cash_musd"]
        )

        if (
            pd.notna(total_current_tax_paid_cash_musd)
            and total_current_tax_paid_cash_musd > 0
        ):
            revenue_gain_from_ut_pct_of_current_tax_paid = (
                100 * total_revenue_gain_from_ut_musd / total_current_tax_paid_cash_musd
            )
            tax_revenue_loss_pct_of_current_tax_paid = (
                100 * total_tax_loss_musd / total_current_tax_paid_cash_musd
            )
            tax_revenue_gain_pct_of_current_tax_paid = (
                100 * total_tax_gain_musd / total_current_tax_paid_cash_musd
            )
        else:
            revenue_gain_from_ut_pct_of_current_tax_paid = np.nan
            tax_revenue_loss_pct_of_current_tax_paid = np.nan
            tax_revenue_gain_pct_of_current_tax_paid = np.nan

    return {
        "sample_name": sample_name,
        "formula_name": formula_name,
        "etr_name": etr_name,
        "etr_col": etr_col,
        "etr_threshold": etr_threshold,
        "threshold_rate_col": threshold_rate_col,
        "rate_mode": rate_mode_name,
        "loss_rate_col": loss_rate_col,
        "gain_rate_col": gain_rate_col,
        "year": year,
        "income_group_bucket": income_group_bucket,
        "n_countries": n_countries,
        "total_shifted_musd": total_shifted_musd,
        "total_tax_loss_musd": total_tax_loss_musd,
        "total_tax_gain_musd": total_tax_gain_musd,
        "total_revenue_gain_from_ut_musd": total_revenue_gain_from_ut_musd,
        "mean_revenue_gain_from_ut_musd": mean_revenue_gain_from_ut_musd,
        "total_current_tax_paid_cash_musd": total_current_tax_paid_cash_musd,
        "revenue_gain_from_ut_pct_of_current_tax_paid": revenue_gain_from_ut_pct_of_current_tax_paid,
        "tax_revenue_loss_pct_of_current_tax_paid": tax_revenue_loss_pct_of_current_tax_paid,
        "tax_revenue_gain_pct_of_current_tax_paid": tax_revenue_gain_pct_of_current_tax_paid,
    }


def build_aggregate_rows(
    country_results,
    year,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    loss_rate_col,
    gain_rate_col,
    sample_name,
):
    df = country_results.copy()
    df["income_group_bucket"] = df["wb_income_group"].apply(classify_income_group)

    rows = []

    rows.append(
        make_aggregate_row(
            df=df,
            year=year,
            formula_name=formula_name,
            etr_name=etr_name,
            etr_col=etr_col,
            etr_threshold=etr_threshold,
            threshold_rate_col=threshold_rate_col,
            rate_mode_name=rate_mode_name,
            loss_rate_col=loss_rate_col,
            gain_rate_col=gain_rate_col,
            sample_name=sample_name,
            income_group_bucket="global",
        )
    )

    for bucket in AGGREGATE_INCOME_GROUPS:
        if bucket == "global":
            continue

        subset = df.loc[df["income_group_bucket"] == bucket].copy()

        rows.append(
            make_aggregate_row(
                df=subset,
                year=year,
                formula_name=formula_name,
                etr_name=etr_name,
                etr_col=etr_col,
                etr_threshold=etr_threshold,
                threshold_rate_col=threshold_rate_col,
                rate_mode_name=rate_mode_name,
                loss_rate_col=loss_rate_col,
                gain_rate_col=gain_rate_col,
                sample_name=sample_name,
                income_group_bucket=bucket,
            )
        )

    return pd.DataFrame(rows)


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


def validate_etr_spec(etr_spec):
    if "name" not in etr_spec or "etr_col" not in etr_spec:
        raise ValueError("Each ETR specification must define 'name' and 'etr_col'.")


def validate_input_data(cbcr_data, sample_name):
    required_cols = [
        "year",
        "iso_parent",
        "iso_partner",
        "partner_jurisdiction",
        PROFIT_VAR,
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
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


def fill_column_with_fallbacks(df, target_col, fallback_cols):
    out = df.copy()

    if target_col not in out.columns:
        return out

    for fallback_col in fallback_cols:
        if fallback_col not in out.columns:
            continue
        missing = out[target_col].isna()
        out.loc[missing, target_col] = out.loc[missing, fallback_col]

    return out


def ensure_tax_rate_columns(df):
    """Fill missing values on the four partner-year UT ETR columns from each
    other (and cit as last resort) so UT can run on every row. The pair-ETR
    column is a diagnostic and is NEVER imputed here — distributed rows keep
    NaN by design."""
    out = df.copy()

    out = fill_column_with_fallbacks(
        out,
        ETR_COL_MEDIAN,
        [ETR_COL_P25, ETR_COL_MIN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_P25,
        [ETR_COL_MEDIAN, ETR_COL_MIN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_MIN,
        [ETR_COL_P25, ETR_COL_MEDIAN, ETR_COL_AVERAGE, "cit"],
    )
    out = fill_column_with_fallbacks(
        out,
        ETR_COL_AVERAGE,
        [ETR_COL_MEDIAN, ETR_COL_P25, ETR_COL_MIN, "cit"],
    )

    return out


def ensure_current_tax_source_column(df):
    out = df.copy()

    if TAX_VAR not in out.columns:
        out[TAX_VAR] = np.nan
    else:
        out[TAX_VAR] = pd.to_numeric(out[TAX_VAR], errors="coerce")

    return out


def load_input_samples():
    numeric_cols = [
        "year",
        PROFIT_VAR,
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "cit",
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "tax_revenue_current_usd",
        "gvt_health_expenditure",
        "wage_monthly",
        TAX_VAR,
    ]

    samples = {}

    for sample_name, file_path in INPUT_SAMPLES.items():
        df = pd.read_csv(file_path)
        df = keep_actual_country_rows(df)

        # Home-group restriction: keep only MNEs whose parent jurisdiction is in
        # PARENT_SET. Done before the REPORTED_ONLY / numeric-coercion / ETR-fill
        # steps so everything downstream (share economy, profit pool, ETR
        # fallbacks, alpha) is computed within the home-parent universe only.
        if PARENT_SET:
            n_before_parent = len(df)
            df = df[df["iso_parent"].isin(PARENT_SET)].copy()
            print(
                f"  HOME_GROUP='{HOME_GROUP}' ({HOME_LABEL}): kept {len(df):,} of "
                f"{n_before_parent:,} rows; {df['iso_parent'].nunique()} parent / "
                f"{df['iso_partner'].nunique()} partner jurisdictions."
            )
            if df.empty:
                raise ValueError(
                    f"No rows left after HOME_GROUP='{HOME_GROUP}'. Check the "
                    f"parent ISO codes in PARENT_SET."
                )

        if REPORTED_ONLY:
            n_before = len(df)
            df = df[df["is_distributed"] == 0].copy()
            n_after_dist = len(df)
            # Drop "bad reporters": parents whose only remaining row is the
            # domestic row (iso_partner == iso_parent) — they have no
            # cross-border country-level data left after the keep_actual_country_rows
            # and is_distributed==0 filters. Mathematically they contribute 0 to
            # the misalignment signal (the formula factors collapse to 100% in
            # the parent's own country, so theoretical == reported); explicitly
            # dropping them shrinks the parent universe to the actual reporting
            # population.
            cross_border_parents = (
                df.loc[df["iso_partner"] != df["iso_parent"], "iso_parent"].unique()
            )
            n_parents_before = df["iso_parent"].nunique()
            df = df[df["iso_parent"].isin(cross_border_parents)].copy()
            n_parents_after = df["iso_parent"].nunique()
            print(f"  REPORTED_ONLY filter: kept {n_after_dist:,} of {n_before:,} rows "
                  f"after is_distributed==0; then dropped {n_parents_before - n_parents_after} "
                  f"bad-reporter parents (no cross-border country data after filter), "
                  f"leaving {len(df):,} rows for {n_parents_after} parents.")
        df = coerce_numeric_columns(df, numeric_cols)
        df = ensure_tax_rate_columns(df)
        df = ensure_current_tax_source_column(df)
        validate_input_data(df, sample_name)

        print(f"\nLoaded sample: {sample_name}{' (reported-only)' if REPORTED_ONLY else ''}")
        print(f"  Rows: {len(df):,}")
        print(f"  Years: {sorted(df['year'].dropna().astype(int).unique())}")

        for etr_spec in ETR_SPECS:
            n_missing = df[etr_spec["etr_col"]].isna().sum()
            print(f"  Missing {etr_spec['etr_col']}: {n_missing:,}")

        n_missing_cit = df["cit"].isna().sum()
        print(f"  Missing cit: {n_missing_cit:,}")

        if TAX_VAR in df.columns:
            n_missing_tax_paid = df[TAX_VAR].isna().sum()
            print(f"  Missing {TAX_VAR}: {n_missing_tax_paid:,}")

        # Compute α[parent] for the alpha-blended scenario-4 formulas. Defined
        # only for incl_resource where resource_factor_usd exists; for other
        # samples we attach a zero column so blended formulas (if accidentally
        # selected) degrade gracefully to pure secondary (4-factor) allocation.
        df = _attach_alpha_per_parent(df)

        samples[sample_name] = df

    return samples


def _attach_alpha_per_parent(df):
    """Compute α[parent] = Σ resource_factor_usd / Σ total_revenues per
    parent, capped at 1.0; merge it back onto df as a row-level constant
    column `alpha_resource_per_parent`.

    α is parent-level, not (parent, partner, year) — every row for a given
    iso_parent carries the same α value (so the alpha-blend in
    `calculate_misalignment` cleanly factors profit into a resource-share
    pool and a non-resource pool per parent).

    On samples without `resource_factor_usd` (everything except
    cbcr_main_incl_resource.csv), α is 0 — alpha-blended formulas in
    those samples degrade to pure 4-factor secondary.
    """
    if "resource_factor_usd" not in df.columns:
        df["alpha_resource_per_parent"] = 0.0
        return df

    rev = pd.to_numeric(df["total_revenues"], errors="coerce").fillna(0.0).clip(lower=0)
    rf = pd.to_numeric(df["resource_factor_usd"], errors="coerce").fillna(0.0).clip(lower=0)
    by_parent = pd.DataFrame({"iso_parent": df["iso_parent"], "rev": rev, "rf": rf})
    sums = by_parent.groupby("iso_parent", as_index=False).agg(
        rev_total=("rev", "sum"), rf_total=("rf", "sum")
    )
    sums["alpha"] = np.where(
        sums["rev_total"] > 0, sums["rf_total"] / sums["rev_total"], 0.0,
    )
    sums["alpha"] = sums["alpha"].clip(lower=0.0, upper=1.0)
    df = df.merge(sums[["iso_parent", "alpha"]], on="iso_parent", how="left")
    df = df.rename(columns={"alpha": "alpha_resource_per_parent"})
    df["alpha_resource_per_parent"] = df["alpha_resource_per_parent"].fillna(0.0)
    return df


# %% [2.4] Column ordering helpers
def order_columns(df, preferred_cols):
    if df.empty:
        return df.copy()

    preferred_existing = [c for c in preferred_cols if c in df.columns]
    remaining = sorted([c for c in df.columns if c not in preferred_existing])
    return df[preferred_existing + remaining].copy()


def order_country_columns(df):
    preferred = [
        "iso_partner",
        "partner_jurisdiction",
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "wb_income_group",
        "region_tjn",
        "ukt",
        "oecd",
        "oecd_oct",
        "nld_oct",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        "current_tax_paid_cash_usd_raw",
        "current_tax_paid_cash_musd",
        "negative_misalignment",
        "positive_misalignment",
        "theoretical_profit",
        "reported_profit",
        "tax_revenue_loss",
        "tax_revenue_gain",
        "revenue_gain_from_ut",
        "tax_revenue_loss_caused_musd",
        "tax_revenue_loss_caused_pct_of_total",
        "tax_revenue_loss_suffered_pct_of_total",
        "revenue_gain_from_ut_pct_of_current_tax_paid",
        "tax_revenue_loss_pct_of_current_tax_paid",
        "tax_revenue_gain_pct_of_current_tax_paid",
        "tax_revenue_current_usd",
        "gvt_health_expenditure",
        "wage_monthly",
    ]
    return order_columns(df, preferred)


def order_aggregate_columns(df):
    preferred = [
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "income_group_bucket",
        "n_countries",
        "total_shifted_musd",
        "total_tax_loss_musd",
        "total_tax_gain_musd",
        "total_revenue_gain_from_ut_musd",
        "mean_revenue_gain_from_ut_musd",
        "total_current_tax_paid_cash_musd",
        "revenue_gain_from_ut_pct_of_current_tax_paid",
        "tax_revenue_loss_pct_of_current_tax_paid",
        "tax_revenue_gain_pct_of_current_tax_paid",
    ]
    return order_columns(df, preferred)


def order_misalignment_columns(df):
    preferred = [
        "iso_parent",
        "iso_partner",
        "partner_jurisdiction",
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        PROFIT_VAR,
        "theoretical_profit",
        "misaligned_profit",
        "positive_misalignment_musd_row",
        "negative_misalignment_musd_row",
        "tax_revenue_loss_suffered_musd_row",
        "tax_revenue_loss_caused_musd_row",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
        TAX_VAR,
        "n_employees",
        "unrelated_party_revenues",
        "tangible_assets_except_cash",
        "payroll",
        "economic_activity_partner_of_parent",
        "share_economy_partner_of_parent",
        "wb_income_group",
        "region_tjn",
        "ukt",
        "oecd",
        "oecd_oct",
        "nld_oct",
    ]
    return order_columns(df, preferred)


def order_run_summary_columns(df):
    preferred = [
        "sample_name",
        "formula_name",
        "etr_name",
        "etr_col",
        "etr_threshold",
        "threshold_rate_col",
        "rate_mode",
        "loss_rate_col",
        "gain_rate_col",
        "n_country_rows",
        "n_misalignment_rows",
        "n_years",
        "total_shifted_musd_all_years",
        "total_tax_loss_musd_all_years",
        "total_tax_gain_musd_all_years",
        "total_revenue_gain_from_ut_musd_all_years",
        "total_current_tax_paid_cash_musd_all_years",
        "revenue_gain_from_ut_pct_of_current_tax_paid_all_years",
        "total_revenue_gain_from_ut_low_income_musd_all_years",
        "total_revenue_gain_from_ut_middle_income_musd_all_years",
        "country_file",
        "misalignment_file",
        "aggregate_file",
        "n_bilateral_rows",
        "bilateral_file",
    ]
    return order_columns(df, preferred)


def order_bilateral_columns(df):
    preferred = [
        "year",
        "iso_responsible",
        "iso_affected",
        "shifted_profit_musd",
        "tax_loss_musd",
    ]
    return order_columns(df, preferred)


# %% [3] Core estimation functions
def _compute_share_economy(df, formula_vars, weights, share_prefix=""):
    """Compute share_economy_partner_of_parent for one formula spec.

    Returns the (share_col_name, df-with-new-column) pair. Mutates df.
    """
    active_specs = []
    for var, weight in zip(formula_vars, weights):
        if var is None or weight <= 0:
            continue
        if var not in df.columns:
            raise ValueError(f"Formula variable '{var}' not found in input data.")

        df[var] = pd.to_numeric(df[var], errors="coerce")
        df.loc[df[var] < 0, var] = 0

        total_by_parent = df.groupby("iso_parent")[var].transform("sum")
        share_col = f"share_{share_prefix}{var}"
        df[share_col] = np.where(total_by_parent > 0, df[var] / total_by_parent, 0)
        active_specs.append((share_col, weight))

    if not active_specs:
        raise ValueError("No active variables with positive weights found.")

    activity_col = f"economic_activity_{share_prefix}partner_of_parent"
    df[activity_col] = 0.0
    for share_col, weight in active_specs:
        df[activity_col] += df[share_col] * weight

    total_activity = df.groupby("iso_parent")[activity_col].transform("sum")
    out_col = f"share_economy_{share_prefix}partner_of_parent"
    df[out_col] = np.where(total_activity > 0, df[activity_col] / total_activity, 0)
    return out_col, df


def calculate_misalignment(
    cbcr_data,
    formula_vars,
    weights,
    profit_var=None,
    etr_max=0.15,
    threshold_rate_col=None,
    loss_rate_col=None,
    secondary_formula_vars=None,
    secondary_weights=None,
    alpha_col=None,
):
    """Compute misalignment of reported profit vs formulary-apportioned profit.

    Standard mode (no secondary formula): all of each parent's profit is
    allocated by `(formula_vars, weights)`. Compatible with all existing callers.

    Variable-weight scenario-4 mode (Option A′, added 2026-05-14): pass
    `secondary_formula_vars` + `secondary_weights` + `alpha_col` to enable a
    per-parent blend of two formula allocations. For each row:

        share = α[parent] × primary_share + (1 − α[parent]) × secondary_share

    where α is read from `df[alpha_col]` (a constant within each parent —
    typically the parent's resource-intensity fraction from
    `compute_alpha_per_parent`). The primary formula is the resource-augmented
    5-factor; the secondary is the same minus the resource factor. The result
    is equivalent to splitting each parent's profit pool into a resource-share
    (α) and non-resource-share (1−α) and allocating each separately.
    """
    # Defaults pulled from the active dataset config when callers omit them.
    if profit_var is None:
        profit_var = PROFIT_VAR
    if threshold_rate_col is None:
        threshold_rate_col = ETR_COL_AVERAGE
    df = cbcr_data.copy()

    if profit_var not in df.columns:
        raise ValueError(f"Profit variable '{profit_var}' not found in input data.")

    if threshold_rate_col not in df.columns:
        raise ValueError(
            f"Threshold rate column '{threshold_rate_col}' not found in input data."
        )

    if loss_rate_col is not None and loss_rate_col not in df.columns:
        raise ValueError(f"Loss rate column '{loss_rate_col}' not found in input data.")

    primary_col, df = _compute_share_economy(df, formula_vars, weights, share_prefix="")

    if secondary_formula_vars is not None and alpha_col is not None:
        if secondary_weights is None:
            raise ValueError("secondary_weights required when secondary_formula_vars is set.")
        if alpha_col not in df.columns:
            raise ValueError(f"alpha_col '{alpha_col}' not found in input data.")
        secondary_col, df = _compute_share_economy(
            df, secondary_formula_vars, secondary_weights, share_prefix="secondary_"
        )
        alpha = pd.to_numeric(df[alpha_col], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
        df["share_economy_partner_of_parent"] = (
            alpha * df[primary_col] + (1.0 - alpha) * df[secondary_col]
        )
    else:
        df["share_economy_partner_of_parent"] = df[primary_col]

    total_profit_by_parent = df.groupby("iso_parent")[profit_var].transform("sum")
    # Floor parent worldwide profit pool at 0 for UT apportionment. When a
    # parent's worldwide profit (under the active profit_var) is non-positive,
    # skip apportionment for that parent — partners retain their reported
    # values (theoretical = reported, misalignment = 0). Prevents UT from
    # redistributing a negative aggregate pro-rata across all partners (which
    # otherwise drags non-resource partners more negative; see the Somalia
    # case under excl_resource).
    parent_positive = total_profit_by_parent > 0
    df["theoretical_profit"] = np.where(
        parent_positive,
        df["share_economy_partner_of_parent"] * total_profit_by_parent,
        df[profit_var],
    )
    df["misaligned_profit"] = df[profit_var] - df["theoretical_profit"]

    df.loc[
        (df["misaligned_profit"] > 0) & (df[threshold_rate_col] > etr_max),
        "misaligned_profit",
    ] = 0

    def adjust_misalignment(group):
        total_neg = group.loc[group["misaligned_profit"] < 0, "misaligned_profit"].sum()
        total_pos = group.loc[group["misaligned_profit"] > 0, "misaligned_profit"].sum()

        # Balancing rescales each parent's negative misalignments to match its
        # positives (haven-accounting conservation within the MNE). Skip it when
        # NO minimum-ETR threshold is applied (etr_max = inf): in that pure
        # reapportionment regime the recovered revenue must track the tax base
        # exactly (revenue = reapportioned base × rate), which requires
        # neg − pos == theoretical − reported. The rescale would otherwise break
        # that identity and decouple the revenue sign from the tax-base sign.
        # Tie-in: whenever the minimum ETR is off, it is off for revenue too.
        if total_neg != 0 and not np.isinf(etr_max):
            factor = -total_pos / total_neg
            group.loc[group["misaligned_profit"] < 0, "misaligned_profit"] *= factor

        if loss_rate_col is not None:
            group["positive_misalignment_musd_row"] = np.where(
                group["misaligned_profit"] > 0,
                group["misaligned_profit"] / 1e6,
                0.0,
            )
            group["negative_misalignment_musd_row"] = np.where(
                group["misaligned_profit"] < 0,
                -group["misaligned_profit"] / 1e6,
                0.0,
            )
            group["tax_revenue_loss_suffered_musd_row"] = (
                group["negative_misalignment_musd_row"] * group[loss_rate_col]
            )

            total_positive_musd = group["positive_misalignment_musd_row"].sum()
            total_tax_loss_suffered_musd = group[
                "tax_revenue_loss_suffered_musd_row"
            ].sum()

            group["tax_revenue_loss_caused_musd_row"] = np.where(
                total_positive_musd > 0,
                (
                    group["positive_misalignment_musd_row"]
                    / total_positive_musd
                    * total_tax_loss_suffered_musd
                ),
                0.0,
            )

        return group

    adjusted_parts = []
    for _, group in df.groupby("iso_parent", sort=False):
        adjusted_parts.append(adjust_misalignment(group.copy()))

    df = pd.concat(adjusted_parts, ignore_index=True)
    return df


def aggregate_country_results(
    misalignment_df,
    year,
    loss_rate_col,
    gain_rate_col,
    formula_name,
    etr_name,
    etr_col,
    etr_threshold,
    threshold_rate_col,
    rate_mode_name,
    sample_name,
):
    metadata_cols = [
        "partner_jurisdiction",
        "cit",
        ETR_COL_AVERAGE,
        ETR_COL_MEDIAN,
        ETR_COL_P25,
        ETR_COL_MIN,
        ETR_COL_PAIR,
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
        tax_revenue_loss_caused_musd=("tax_revenue_loss_caused_musd_row", "sum"),
    )

    current_tax_paid = misalignment_df.groupby("iso_partner", as_index=False).agg(
        current_tax_paid_cash_usd_raw=(
            TAX_VAR,
            lambda x: x.sum(min_count=1),
        )
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
    country_results = country_results.merge(
        current_tax_paid, on="iso_partner", how="left"
    )

    country_results["tax_revenue_loss"] = (
        country_results["negative_misalignment"] * country_results[loss_rate_col]
    )
    country_results["tax_revenue_gain"] = (
        country_results["positive_misalignment"] * country_results[gain_rate_col]
    )

    total_loss = country_results["tax_revenue_loss"].sum()

    country_results["revenue_gain_from_ut"] = (
        country_results["tax_revenue_loss"] - country_results["tax_revenue_gain"]
    )

    country_results["tax_revenue_loss_caused_pct_of_total"] = np.where(
        total_loss > 0,
        country_results["tax_revenue_loss_caused_musd"] / total_loss,
        0,
    )
    country_results["tax_revenue_loss_suffered_pct_of_total"] = np.where(
        total_loss > 0,
        country_results["tax_revenue_loss"] / total_loss,
        0,
    )

    country_results["current_tax_paid_cash_musd"] = np.where(
        country_results["current_tax_paid_cash_usd_raw"].notna(),
        country_results["current_tax_paid_cash_usd_raw"].clip(lower=0) / 1e6,
        np.nan,
    )

    country_results["revenue_gain_from_ut_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["revenue_gain_from_ut"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["tax_revenue_loss_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["tax_revenue_loss"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["tax_revenue_gain_pct_of_current_tax_paid"] = np.where(
        country_results["current_tax_paid_cash_musd"] > 0,
        100
        * country_results["tax_revenue_gain"]
        / country_results["current_tax_paid_cash_musd"],
        np.nan,
    )

    country_results["year"] = year
    country_results["formula_name"] = formula_name
    country_results["etr_name"] = etr_name
    country_results["etr_col"] = etr_col
    country_results["etr_threshold"] = etr_threshold
    country_results["threshold_rate_col"] = threshold_rate_col
    country_results["rate_mode"] = rate_mode_name
    country_results["loss_rate_col"] = loss_rate_col
    country_results["gain_rate_col"] = gain_rate_col
    country_results["sample_name"] = sample_name

    return country_results


def run_estimation_year(
    year,
    cbcr_data,
    formula_spec,
    etr_spec,
    rate_mode,
    etr_threshold,
    sample_name,
):
    cbcr_year = cbcr_data.loc[cbcr_data["year"] == year].copy()

    if cbcr_year.empty:
        return None, None, None

    misalignment = calculate_misalignment(
        cbcr_data=cbcr_year,
        formula_vars=formula_spec["formula_vars"],
        weights=formula_spec["weights"],
        profit_var=PROFIT_VAR,
        etr_max=etr_threshold,
        threshold_rate_col=etr_spec["etr_col"],
        loss_rate_col=rate_mode["loss_rate_col"],
        secondary_formula_vars=formula_spec.get("secondary_formula_vars"),
        secondary_weights=formula_spec.get("secondary_weights"),
        alpha_col=formula_spec.get("alpha_col"),
    )
    misalignment["year"] = year
    misalignment["formula_name"] = formula_spec["name"]
    misalignment["etr_name"] = etr_spec["name"]
    misalignment["etr_col"] = etr_spec["etr_col"]
    misalignment["etr_threshold"] = etr_threshold
    misalignment["threshold_rate_col"] = etr_spec["etr_col"]
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
        etr_name=etr_spec["name"],
        etr_col=etr_spec["etr_col"],
        etr_threshold=etr_threshold,
        threshold_rate_col=etr_spec["etr_col"],
        rate_mode_name=rate_mode["name"],
        sample_name=sample_name,
    )

    aggregate_rows = build_aggregate_rows(
        country_results=country_results,
        year=year,
        formula_name=formula_spec["name"],
        etr_name=etr_spec["name"],
        etr_col=etr_spec["etr_col"],
        etr_threshold=etr_threshold,
        threshold_rate_col=etr_spec["etr_col"],
        rate_mode_name=rate_mode["name"],
        loss_rate_col=rate_mode["loss_rate_col"],
        gain_rate_col=rate_mode["gain_rate_col"],
        sample_name=sample_name,
    )

    return misalignment, country_results, aggregate_rows


# %% [4] Load and validate input samples
for formula_spec in FORMULAS:
    validate_formula_spec(formula_spec)

for etr_spec in ETR_SPECS:
    validate_etr_spec(etr_spec)

samples = load_input_samples()


# %% [4.2] Define years to run
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
run_summary_rows = []

for sample_name, df in samples.items():
    print("\n" + "=" * 100)
    print(f"RUNNING SAMPLE: {sample_name}")
    print("=" * 100)

    output_dir = ensure_output_dir(sample_name)

    # Skip 5-factor formulas if the sample lacks `resource_factor_usd`.
    # Additional methodology filter: non-alpha 5-factor formulas (the
    # `*_with_resources_30pct` / `_resource_<N>pct` series) only make sense
    # on `incl_resource` (where pre-profit royalties are added back); on
    # other datasets resources are stripped or unmodified, so a flat
    # resource-factor weight is conceptually inconsistent. The alpha-blended
    # variants (`*_resource_alpha_<N>pct`) are kept everywhere because they
    # gracefully degrade (α=0 → 4-factor secondary) when there's no resource
    # activity in the parent.
    available_cols = set(df.columns)
    formulas_for_sample = [
        f for f in FORMULAS
        if all(v in available_cols for v in f["formula_vars"])
        and (sample_name == "incl_resource"
             or "resource" not in f["name"]
             or "alpha" in f["name"])
    ]
    skipped = [f["name"] for f in FORMULAS if f not in formulas_for_sample]
    if skipped:
        print(f"  [skip {len(skipped)} formulas not applicable to this sample] "
              f"{', '.join(skipped)}")

    for formula_spec, etr_spec, etr_threshold, rate_mode_template in product(
        formulas_for_sample, ETR_SPECS, ETR_THRESHOLDS, RATE_MODE_TEMPLATES
    ):
        rate_mode = resolve_rate_mode(rate_mode_template, etr_spec)

        file_stub = make_file_stub(
            formula_name=formula_spec["name"],
            etr_name=etr_spec["name"],
            etr_threshold=etr_threshold,
            rate_mode_name=rate_mode["name"],
        )

        print("\n" + "-" * 100)
        print(
            f"Formula: {formula_spec['name']} | "
            f"ETR definition: {etr_spec['name']} ({etr_spec['etr_col']}) | "
            f"ETR max: {etr_threshold} | "
            f"Rate mode: {rate_mode['name']}"
        )
        print("-" * 100)

        results_country = []
        results_misalignment = []
        results_aggregate = []

        for year in sample_years[sample_name]:
            misalignment, country_results, aggregate_rows = run_estimation_year(
                year=year,
                cbcr_data=df,
                formula_spec=formula_spec,
                etr_spec=etr_spec,
                rate_mode=rate_mode,
                etr_threshold=etr_threshold,
                sample_name=sample_name,
            )

            if country_results is not None:
                results_country.append(country_results)
                results_misalignment.append(misalignment)
                results_aggregate.append(aggregate_rows)

                global_row = aggregate_rows.loc[
                    aggregate_rows["income_group_bucket"] == "global"
                ].iloc[0]

                print(
                    f"  {year}: shifted {global_row['total_shifted_musd']:,.0f}M USD | "
                    f"tax loss {global_row['total_tax_loss_musd']:,.0f}M USD | "
                    f"tax gain {global_row['total_tax_gain_musd']:,.0f}M USD"
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

        if results_aggregate:
            aggregate_df = pd.concat(results_aggregate, ignore_index=True)
        else:
            aggregate_df = pd.DataFrame()

        country_all_years = order_country_columns(country_all_years)
        misalignment_all_years = order_misalignment_columns(misalignment_all_years)
        aggregate_df = order_aggregate_columns(aggregate_df)

        country_file = output_dir / f"country_estimates__{file_stub}.csv"
        misalignment_file = output_dir / f"misalignment__{file_stub}.csv"
        aggregate_file = output_dir / f"aggregate_results__{file_stub}.csv"

        country_all_years.to_csv(_longpath(country_file), index=False)
        misalignment_all_years.to_csv(_longpath(misalignment_file), index=False)
        aggregate_df.to_csv(_longpath(aggregate_file), index=False)

        if not aggregate_df.empty:
            aggregate_global_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "global"
            ].copy()

            aggregate_low_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "low_income"
            ].copy()

            aggregate_middle_df = aggregate_df.loc[
                aggregate_df["income_group_bucket"] == "middle_income"
            ].copy()
        else:
            aggregate_global_df = pd.DataFrame()
            aggregate_low_df = pd.DataFrame()
            aggregate_middle_df = pd.DataFrame()

        total_current_tax_paid_cash_musd_all_years = (
            safe_series_sum(aggregate_global_df["total_current_tax_paid_cash_musd"])
            if not aggregate_global_df.empty
            and "total_current_tax_paid_cash_musd" in aggregate_global_df.columns
            else np.nan
        )

        if (
            pd.notna(total_current_tax_paid_cash_musd_all_years)
            and total_current_tax_paid_cash_musd_all_years > 0
        ):
            revenue_gain_from_ut_pct_of_current_tax_paid_all_years = (
                100
                * aggregate_global_df["total_revenue_gain_from_ut_musd"].sum()
                / total_current_tax_paid_cash_musd_all_years
            )
        else:
            revenue_gain_from_ut_pct_of_current_tax_paid_all_years = np.nan

        run_summary_rows.append(
            {
                "sample_name": sample_name,
                "formula_name": formula_spec["name"],
                "etr_name": etr_spec["name"],
                "etr_col": etr_spec["etr_col"],
                "etr_threshold": etr_threshold,
                "threshold_rate_col": etr_spec["etr_col"],
                "rate_mode": rate_mode["name"],
                "loss_rate_col": rate_mode["loss_rate_col"],
                "gain_rate_col": rate_mode["gain_rate_col"],
                "n_country_rows": len(country_all_years),
                "n_misalignment_rows": len(misalignment_all_years),
                "n_years": (
                    aggregate_global_df["year"].nunique()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_shifted_musd_all_years": (
                    aggregate_global_df["total_shifted_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_tax_loss_musd_all_years": (
                    aggregate_global_df["total_tax_loss_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_tax_gain_musd_all_years": (
                    aggregate_global_df["total_tax_gain_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_revenue_gain_from_ut_musd_all_years": (
                    aggregate_global_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_global_df.empty
                    else 0
                ),
                "total_current_tax_paid_cash_musd_all_years": total_current_tax_paid_cash_musd_all_years,
                "revenue_gain_from_ut_pct_of_current_tax_paid_all_years": revenue_gain_from_ut_pct_of_current_tax_paid_all_years,
                "total_revenue_gain_from_ut_low_income_musd_all_years": (
                    aggregate_low_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_low_df.empty
                    else 0
                ),
                "total_revenue_gain_from_ut_middle_income_musd_all_years": (
                    aggregate_middle_df["total_revenue_gain_from_ut_musd"].sum()
                    if not aggregate_middle_df.empty
                    else 0
                ),
                "country_file": str(country_file),
                "misalignment_file": str(misalignment_file),
                "aggregate_file": str(aggregate_file),
            }
        )


# %% [6] Save and display run summary
run_summary = pd.DataFrame(run_summary_rows)
run_summary = order_run_summary_columns(run_summary)

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


# %% [6.1] Per-year headline table (all years, global bucket).
# The run_summary above sums across all years; this breaks the same global
# totals out year-by-year for every formula × rate-mode spec, so the full
# 2016–2022 panel is available in one tidy file. Built from the per-spec
# aggregate_results files already written above (global income bucket only).
_agg_paths = sorted(Path(OUTPUT_ROOT).glob("**/aggregate_results__*.csv"))
_per_year_parts = []
for _p in _agg_paths:
    try:
        _adf = pd.read_csv(_longpath(_p))
    except Exception:
        continue
    if _adf.empty or "income_group_bucket" not in _adf.columns:
        continue
    _g = _adf.loc[_adf["income_group_bucket"] == "global"].copy()
    if not _g.empty:
        _per_year_parts.append(_g)

if _per_year_parts:
    per_year = pd.concat(_per_year_parts, ignore_index=True)
    _keep = [
        "year",
        "sample_name",
        "formula_name",
        "etr_name",
        "rate_mode",
        "n_countries",
        "total_shifted_musd",
        "total_tax_loss_musd",
        "total_tax_gain_musd",
        "total_revenue_gain_from_ut_musd",
        "total_current_tax_paid_cash_musd",
        "revenue_gain_from_ut_pct_of_current_tax_paid",
    ]
    per_year = per_year[[c for c in _keep if c in per_year.columns]].copy()
    per_year = per_year.sort_values(
        ["formula_name", "rate_mode", "etr_name", "year"]
    ).reset_index(drop=True)
    per_year_path = OUTPUT_ROOT / "headline_by_year.csv"
    per_year.to_csv(per_year_path, index=False)
    _yr_lo, _yr_hi = first_year, first_year + n_years - 1
    print(f"\nPer-year headline table ({_yr_lo}–{_yr_hi}) saved: {per_year_path}")
else:
    print("\nNo aggregate_results files found for the per-year headline table.")


# %% [6A] Summary exports and two-panel figures over the full panel.
# US-only project: summarise across ALL analysis years (2016–2022) rather than
# script 5's 2021+2022 window. The aggregates below sum over SUMMARY_YEARS, so
# widening it to the whole panel makes every figure / income table all-years.

import matplotlib.pyplot as plt

SUMMARY_YEARS = list(range(first_year, first_year + n_years))
# Human-readable span (e.g. "2016-2022") used in filenames, sheet names and
# figure captions so nothing is mislabelled as a two-year window.
SPAN_LABEL = f"{min(SUMMARY_YEARS)}_{max(SUMMARY_YEARS)}"
# TARGET_SAMPLE must match the active RUN_DATASET (the sole entry of
# INPUT_SAMPLES). Previously hardcoded to "disaggregated_data" which broke
# the summary exports for any other dataset.
TARGET_SAMPLE = RUN_DATASET
TARGET_RATE_MODE = "loss_cit_gain_etr"
# Default targets p25/minimum ETRs (used by loss-sensitivity tables), but
# those ETRs aren't computed in MINIMAL mode. Fall back to whatever's
# present — for MINIMAL this resolves to ["average"].
_AVAILABLE_ETR_NAMES = [s["name"] for s in ETR_SPECS]
TARGET_ETR_NAMES = [n for n in ["p25", "minimum"] if n in _AVAILABLE_ETR_NAMES] or _AVAILABLE_ETR_NAMES[:1]

EXCLUDED_COUNTRIES = ["COD", "UGA", "BFA", "LBR", "NGA", "EGY", "AGO"]

_SUMMARY_STUB = f"summary_{min(SUMMARY_YEARS)}_{max(SUMMARY_YEARS)}_{TARGET_SAMPLE}"
SUMMARY_OUTPUT_DIR = OUTPUT_TABLES / _SUMMARY_STUB
SUMMARY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CHARTS_DIR = OUTPUT_FIGURES / _SUMMARY_STUB
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

FORMULA_ORDER = [f["name"] for f in FORMULAS]

INCOME_ORDER = [
    "global",
    "low_income",
    "lower_middle_income",
    "upper_middle_income",
    "high_income",
    "investment_hub",
]

INCOME_LABELS = {
    "global": "Global",
    "low_income": "Low income",
    "lower_middle_income": "Lower middle income",
    "upper_middle_income": "Upper middle income",
    "high_income": "High income",
    "investment_hub": "Investment hub",
}

ETR_LABELS = {
    "p25": "25th percentile ETR",
    "minimum": "Minimum ETR",
}


def classify_income_group(value):
    s = str(value).strip().lower()
    s = s.replace(" ", "_").replace("-", "_")
    return s


def safe_sum(series):
    return pd.to_numeric(series, errors="coerce").sum(min_count=1)


def first_non_missing(series):
    s = series.dropna()
    return np.nan if s.empty else s.iloc[0]


def order_income_groups(df):
    out = df.copy()
    extra_groups = sorted(
        [
            g
            for g in out["income_group_bucket"].dropna().unique()
            if g not in INCOME_ORDER
        ]
    )
    order = INCOME_ORDER + extra_groups
    out["income_group_bucket"] = pd.Categorical(
        out["income_group_bucket"],
        categories=order,
        ordered=True,
    )
    out = out.sort_values("income_group_bucket").copy()
    out["income_group_bucket"] = out["income_group_bucket"].astype(str)
    out["income_group_label"] = (
        out["income_group_bucket"].map(INCOME_LABELS).fillna(out["income_group_bucket"])
    )
    return out


def read_selected_runs_from_summary(run_summary_df):
    rs = run_summary_df.copy()
    rs["etr_threshold"] = pd.to_numeric(rs["etr_threshold"], errors="coerce")

    _thr = ETR_THRESHOLDS[0]
    _thr_mask = (np.isinf(rs["etr_threshold"]) if np.isinf(_thr)
                 else np.isclose(rs["etr_threshold"], _thr))
    rs = rs.loc[
        (rs["sample_name"] == TARGET_SAMPLE)
        & (rs["rate_mode"] == TARGET_RATE_MODE)
        & (rs["etr_name"].isin(TARGET_ETR_NAMES))
        & _thr_mask
    ].copy()

    if rs.empty:
        raise ValueError(
            f"No matching runs found. Check TARGET_SAMPLE, TARGET_RATE_MODE, "
            f"TARGET_ETR_NAMES and etr_threshold = {_thr}."
        )

    return rs


def build_country_year_baselines(sample_name):
    source_path = INPUT_SAMPLES[sample_name]
    df = pd.read_csv(source_path)
    df = keep_actual_country_rows(df)

    needed_numeric = [
        "year",
        PROFIT_VAR,
        TAX_VAR,
        "income_tax_accrued_current_year",
        "tax_revenue_current_usd",
    ]
    df = coerce_numeric_columns(df, needed_numeric)
    df = df.loc[df["year"].isin(SUMMARY_YEARS)].copy()

    if TAX_VAR in df.columns:
        tax_col = TAX_VAR
    elif "tax_revenue_current_usd" in df.columns:
        tax_col = "tax_revenue_current_usd"
    else:
        raise ValueError("No current tax-paid column found.")

    out = df.groupby(["iso_partner", "year"], as_index=False).agg(
        current_tax_paid_cash_raw_usd=(tax_col, safe_sum),
        current_taxable_profits_raw_usd=(PROFIT_VAR, safe_sum),
    )

    # Aggregate first, then clip to zero.
    out["current_tax_paid_cash_musd"] = out["current_tax_paid_cash_raw_usd"].apply(
        lambda x: np.nan if pd.isna(x) else max(x, 0) / 1e6
    )
    out["current_taxable_profits_musd"] = out["current_taxable_profits_raw_usd"].apply(
        lambda x: np.nan if pd.isna(x) else max(x, 0) / 1e6
    )

    return out[
        [
            "iso_partner",
            "year",
            "current_tax_paid_cash_musd",
            "current_taxable_profits_musd",
        ]
    ]


def build_country_long(selected_runs, baselines_df):
    parts = []

    for row in selected_runs.itertuples(index=False):
        df = pd.read_csv(_longpath(row.country_file))
        if df.empty:
            continue

        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df = df.loc[df["year"].isin(SUMMARY_YEARS)].copy()
        if df.empty:
            continue

        df["income_group_bucket"] = df["wb_income_group"].apply(classify_income_group)

        df["cit_used_country_year"] = pd.to_numeric(df["cit"], errors="coerce")
        df["etr_used_country_year"] = (
            pd.to_numeric(df[row.etr_col], errors="coerce")
            if row.etr_col in df.columns
            else np.nan
        )

        df["net_change_in_taxable_profits_musd"] = pd.to_numeric(
            df["negative_misalignment"], errors="coerce"
        ) - pd.to_numeric(df["positive_misalignment"], errors="coerce")

        df = df.drop(
            columns=[
                c
                for c in ["current_tax_paid_cash_musd", "current_taxable_profits_musd"]
                if c in df.columns
            ],
            errors="ignore",
        )

        df = df.merge(baselines_df, on=["iso_partner", "year"], how="left")

        # All-years totals (sum over every year in SUMMARY_YEARS), plus the
        # weighted-average CIT/ETR actually used across those years. No
        # per-single-year split columns — this project summarises the whole
        # panel, so a 2021/2022 split would be both misleading and unused.
        out = df.groupby(
            [
                "iso_partner",
                "partner_jurisdiction",
                "wb_income_group",
                "income_group_bucket",
                "formula_name",
                "etr_name",
            ],
            as_index=False,
        ).agg(
            gain_loss_from_fa_musd=("revenue_gain_from_ut", "sum"),
            net_change_taxable_profits_musd=(
                "net_change_in_taxable_profits_musd",
                "sum",
            ),
            current_tax_paid_cash_total_musd=("current_tax_paid_cash_musd", "sum"),
            current_taxable_profits_total_musd=(
                "current_taxable_profits_musd",
                "sum",
            ),
            cit_mean=("cit_used_country_year", "mean"),
            etr_used_mean=("etr_used_country_year", "mean"),
            n_years=("year", "nunique"),
        )

        parts.append(out)

    if not parts:
        return pd.DataFrame()

    out = pd.concat(parts, ignore_index=True)

    out["gain_loss_pct_current_tax_paid"] = np.where(
        out["current_tax_paid_cash_total_musd"] > 0,
        100
        * out["gain_loss_from_fa_musd"]
        / out["current_tax_paid_cash_total_musd"],
        np.nan,
    )

    out["net_change_taxable_profits_pct"] = np.where(
        out["current_taxable_profits_total_musd"] > 0,
        100
        * out["net_change_taxable_profits_musd"]
        / out["current_taxable_profits_total_musd"],
        np.nan,
    )

    return out


def add_global_rows(df, group_cols_without_income, value_cols):
    if df.empty:
        return df

    global_rows = df.groupby(group_cols_without_income, as_index=False).agg(
        {col: "sum" for col in value_cols}
    )
    global_rows["income_group_bucket"] = "global"

    return pd.concat([df, global_rows], ignore_index=True)


def build_income_gain_loss(country_long):
    value_cols = [
        "gain_loss_from_fa_musd",
        "current_tax_paid_cash_total_musd",
    ]

    out = country_long.groupby(
        ["income_group_bucket", "formula_name", "etr_name"],
        as_index=False,
    ).agg(
        gain_loss_from_fa_musd=("gain_loss_from_fa_musd", "sum"),
        current_tax_paid_cash_total_musd=(
            "current_tax_paid_cash_total_musd",
            "sum",
        ),
    )

    out = add_global_rows(
        out,
        group_cols_without_income=["formula_name", "etr_name"],
        value_cols=value_cols,
    )

    out["gain_loss_pct_current_tax_paid"] = np.where(
        out["current_tax_paid_cash_total_musd"] > 0,
        100
        * out["gain_loss_from_fa_musd"]
        / out["current_tax_paid_cash_total_musd"],
        np.nan,
    )

    return order_income_groups(out)


def build_income_taxable(country_long):
    # Taxable-profit change is independent of ETR; take each formula-country once.
    tmp = country_long.drop_duplicates(["iso_partner", "formula_name"]).copy()

    value_cols = [
        "net_change_taxable_profits_musd",
        "current_taxable_profits_total_musd",
    ]

    out = tmp.groupby(
        ["income_group_bucket", "formula_name"],
        as_index=False,
    ).agg(
        net_change_taxable_profits_musd=("net_change_taxable_profits_musd", "sum"),
        current_taxable_profits_total_musd=(
            "current_taxable_profits_total_musd",
            "sum",
        ),
    )

    out = add_global_rows(
        out,
        group_cols_without_income=["formula_name"],
        value_cols=value_cols,
    )

    out["net_change_taxable_profits_pct"] = np.where(
        out["current_taxable_profits_total_musd"] > 0,
        100
        * out["net_change_taxable_profits_musd"]
        / out["current_taxable_profits_total_musd"],
        np.nan,
    )

    return order_income_groups(out)


def make_two_panel_figure(
    df,
    figure_no,
    title,
    caption,
    file_stub,
    value_bn_col,
    value_pct_col,
    filter_etr_name=None,
):
    chart_df = df.copy()

    if filter_etr_name is not None:
        chart_df = chart_df.loc[chart_df["etr_name"] == filter_etr_name].copy()

    if chart_df.empty:
        print(f"No data for Figure {figure_no}; skipping.")
        return

    chart_df = order_income_groups(chart_df)

    labels = (
        chart_df[["income_group_bucket", "income_group_label"]]
        .drop_duplicates()
        .set_index("income_group_bucket")["income_group_label"]
        .to_dict()
    )

    bn_wide = chart_df.pivot_table(
        index="income_group_bucket",
        columns="formula_name",
        values=value_bn_col,
        aggfunc="sum",
    ).reindex(INCOME_ORDER)

    pct_wide = chart_df.pivot_table(
        index="income_group_bucket",
        columns="formula_name",
        values=value_pct_col,
        aggfunc="sum",
    ).reindex(INCOME_ORDER)

    bn_wide = bn_wide.dropna(how="all")
    pct_wide = pct_wide.reindex(bn_wide.index)

    for formula in FORMULA_ORDER:
        if formula not in bn_wide.columns:
            bn_wide[formula] = np.nan
        if formula not in pct_wide.columns:
            pct_wide[formula] = np.nan

    bn_wide = bn_wide[FORMULA_ORDER] / 1000
    pct_wide = pct_wide[FORMULA_ORDER]

    bn_wide.index = [labels.get(idx, idx) for idx in bn_wide.index]
    pct_wide.index = bn_wide.index

    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    bn_wide.plot(kind="bar", ax=axes[0])
    axes[0].axhline(0, linewidth=1)
    axes[0].set_title("USD bn")
    axes[0].set_xlabel("")
    axes[0].set_ylabel("Change, USD bn")
    axes[0].tick_params(axis="x", rotation=25)
    axes[0].legend_.remove()

    pct_wide.plot(kind="bar", ax=axes[1])
    axes[1].axhline(0, linewidth=1)
    axes[1].set_title("% change")
    axes[1].set_xlabel("")
    axes[1].set_ylabel("Change, %")
    axes[1].tick_params(axis="x", rotation=25)
    axes[1].legend(title="Formula", bbox_to_anchor=(1.02, 1), loc="upper left")

    fig.suptitle(f"Figure {figure_no}. {title}", fontsize=14)
    fig.text(0.01, -0.05, caption, ha="left", va="top", fontsize=10, wrap=True)

    plt.tight_layout()

    chart_path = CHARTS_DIR / f"fig{figure_no}_{file_stub}.png"
    plt.savefig(chart_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Figure {figure_no} saved: {chart_path}")


def save_excel_summary(
    country_long_all,
    country_long_excl,
    income_gain_all,
    income_gain_excl,
    income_taxable_all,
    income_taxable_excl,
):
    _span = SPAN_LABEL.replace("_", "–")  # e.g. "2016–2022"
    excel_path = SUMMARY_OUTPUT_DIR / f"fa_summary_{SPAN_LABEL}.xlsx"

    captions = pd.DataFrame(
        {
            "figure": [
                "Figure 1",
                "Figure 2",
                "Figure 3",
                "Figure 4",
            ],
            "caption": [
                f"Change in taxable profits under formulary apportionment, by income group and formula, aggregated over {_span}. Panel A shows USD bn; Panel B shows the change as a percentage of current positive taxable profits.",
                f"Change in taxable profits under formulary apportionment, excluding COD, UGA, BFA, LBR, NGA, EGY and AGO ({_span}). Panel A shows USD bn; Panel B shows the change as a percentage of current positive taxable profits.",
                f"Net revenue gain/loss from formulary apportionment using the 25th percentile ETR for gains and CIT for losses, by income group and formula, aggregated over {_span}. Panel A shows USD bn; Panel B shows the change as a percentage of current positive tax paid.",
                f"Net revenue gain/loss from formulary apportionment using the minimum ETR for gains and CIT for losses, by income group and formula, aggregated over {_span}. Panel A shows USD bn; Panel B shows the change as a percentage of current positive tax paid.",
            ],
        }
    )

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        captions.to_excel(writer, sheet_name="figure_captions", index=False)
        country_long_all.to_excel(writer, sheet_name="country_all", index=False)
        country_long_excl.to_excel(writer, sheet_name="country_excl", index=False)
        income_gain_all.to_excel(writer, sheet_name="income_gain_all", index=False)
        income_gain_excl.to_excel(writer, sheet_name="income_gain_excl", index=False)
        income_taxable_all.to_excel(
            writer, sheet_name="income_taxable_all", index=False
        )
        income_taxable_excl.to_excel(
            writer, sheet_name="income_taxable_excl", index=False
        )

    print(f"Excel summary saved: {excel_path}")


# --------------------------------------------------------------------------------------
# Run block
# --------------------------------------------------------------------------------------

if "run_summary" not in globals():
    run_summary = pd.read_csv(OUTPUT_ROOT / "run_summary.csv")

selected_runs = read_selected_runs_from_summary(run_summary)
baselines_df = build_country_year_baselines(TARGET_SAMPLE)

country_long_all = build_country_long(selected_runs, baselines_df)
country_long_excl = country_long_all.loc[
    ~country_long_all["iso_partner"].isin(EXCLUDED_COUNTRIES)
].copy()

income_gain_all = build_income_gain_loss(country_long_all)
income_gain_excl = build_income_gain_loss(country_long_excl)

income_taxable_all = build_income_taxable(country_long_all)
income_taxable_excl = build_income_taxable(country_long_excl)

save_excel_summary(
    country_long_all,
    country_long_excl,
    income_gain_all,
    income_gain_excl,
    income_taxable_all,
    income_taxable_excl,
)

make_two_panel_figure(
    df=income_taxable_all.loc[
        income_taxable_all["income_group_bucket"] != "global"
    ].copy(),
    figure_no=1,
    title="Change in taxable profits, all countries",
    caption=(
        f"Note: Changes are aggregated over {SPAN_LABEL.replace('_', '–')}. "
        "Percent changes are only shown where current taxable profits are positive after aggregation."
    ),
    file_stub="taxable_all",
    value_bn_col="net_change_taxable_profits_musd",
    value_pct_col="net_change_taxable_profits_pct",
)

make_two_panel_figure(
    df=income_taxable_excl.loc[
        income_taxable_excl["income_group_bucket"] != "global"
    ].copy(),
    figure_no=2,
    title="Change in taxable profits, excluding selected resource-intensive countries",
    caption=(
        "Note: Excludes COD, UGA, BFA, LBR, NGA, EGY and AGO. "
        "Percent changes are only shown where current taxable profits are positive after aggregation."
    ),
    file_stub="taxable_excl",
    value_bn_col="net_change_taxable_profits_musd",
    value_pct_col="net_change_taxable_profits_pct",
)

make_two_panel_figure(
    df=income_gain_all,
    figure_no=3,
    title="Revenue gain/loss from formulary apportionment using the 25th percentile ETR",
    caption=(
        f"Note: Losses are valued at the CIT rate and gains at the 25th percentile ETR. "
        f"Percent changes are shown relative to current positive cash taxes paid, aggregated over {SPAN_LABEL.replace('_', '–')}."
    ),
    file_stub="gain_p25",
    value_bn_col="gain_loss_from_fa_musd",
    value_pct_col="gain_loss_pct_current_tax_paid",
    filter_etr_name="p25",
)

make_two_panel_figure(
    df=income_gain_all,
    figure_no=4,
    title="Revenue gain/loss from formulary apportionment using the minimum ETR",
    caption=(
        f"Note: Losses are valued at the CIT rate and gains at the minimum ETR. "
        f"Percent changes are shown relative to current positive cash taxes paid, aggregated over {SPAN_LABEL.replace('_', '–')}."
    ),
    file_stub="gain_min",
    value_bn_col="gain_loss_from_fa_musd",
    value_pct_col="gain_loss_pct_current_tax_paid",
    filter_etr_name="minimum",
)

print("\nSummary export block finished.")


# %% [6B] EU countries: net-misalignment evolution under US-MNE UT, 2016–2022.
#
# Splits the EU-27 into two groups by their net misalignment vis-à-vis US
# multinationals and shows how each country's net misalignment evolves over the
# panel. Sign convention (see calculate_misalignment):
#   net_misalignment = positive_misalignment − negative_misalignment
#     < 0  → the country is UNDER-allocated US-MNE profit today, so it GAINS
#            taxable profit under unitary taxation  → "benefits from UT"
#     > 0  → the country is a net destination for shifted US-MNE profit, so it
#            LOSES taxable profit under unitary taxation → "loses under UT"
# Net misalignment is a profit quantity: it is independent of the ETR
# definition and the loss/gain rate mode (the minimum-ETR threshold is off and
# the balancing rescale is skipped at etr_max = inf), so it depends only on the
# apportionment formula. We use the SOTJ-default `employees_payroll`.
# Group membership is assigned by each country's CUMULATIVE net misalignment
# over 2016–2022 (a country whose yearly line crosses zero is placed by its
# net direction over the whole period).

# EU27 is defined once at the top (section 1.1).
EU_FIG_FORMULA = "employees_payroll"

_eu_src = run_summary.loc[run_summary["formula_name"] == EU_FIG_FORMULA]
if _eu_src.empty:
    print(f"\n[EU figure] No '{EU_FIG_FORMULA}' run found; skipping EU figure.")
else:
    _eu_country_file = _eu_src.iloc[0]["country_file"]
    eu = pd.read_csv(_longpath(_eu_country_file))
    eu["year"] = pd.to_numeric(eu["year"], errors="coerce")
    eu = eu.loc[eu["iso_partner"].isin(EU27)].copy()

    eu["net_misalignment_musd"] = (
        pd.to_numeric(eu["positive_misalignment"], errors="coerce").fillna(0.0)
        - pd.to_numeric(eu["negative_misalignment"], errors="coerce").fillna(0.0)
    )

    # One row per (partner, year) already, but sum defensively.
    eu_panel = eu.groupby(
        ["iso_partner", "partner_jurisdiction", "year"], as_index=False
    )["net_misalignment_musd"].sum()
    eu_panel["net_misalignment_bn"] = eu_panel["net_misalignment_musd"] / 1000.0

    # Classify each country by cumulative net misalignment over the panel.
    eu_totals = (
        eu_panel.groupby(["iso_partner", "partner_jurisdiction"], as_index=False)[
            "net_misalignment_musd"
        ]
        .sum()
        .rename(columns={"net_misalignment_musd": "total_net_misalignment_musd"})
    )
    eu_totals["group"] = np.where(
        eu_totals["total_net_misalignment_musd"] < 0,
        "benefits_from_ut",   # net negative misalignment
        "loses_under_ut",     # net positive misalignment
    )
    eu_panel = eu_panel.merge(
        eu_totals[["iso_partner", "group", "total_net_misalignment_musd"]],
        on="iso_partner",
        how="left",
    )

    # Persist the underlying data + classification next to the other tables.
    eu_panel.sort_values(["group", "iso_partner", "year"]).to_csv(
        OUTPUT_TABLES / "eu_net_misalignment_by_year.csv", index=False
    )
    eu_totals.sort_values(["group", "total_net_misalignment_musd"]).to_csv(
        OUTPUT_TABLES / "eu_net_misalignment_classification.csv", index=False
    )

    _eu_years = sorted(int(y) for y in eu_panel["year"].dropna().unique())

    # Two aggregated lines: all "winners" (benefit / net-negative) summed into
    # one series and all "losers" (lose / net-positive) into another. Group
    # membership is fixed by each country's cumulative net misalignment over the
    # whole period; the line is the per-year SUM of net misalignment within the
    # group. Produced both for the full EU-27 and excluding Luxembourg (whose
    # −$87bn 2021 loss otherwise dominates the winners line).
    GROUP_META = {
        "benefits_from_ut": ("Winners — benefit from UT (net negative)", "#1b7837"),
        "loses_under_ut":   ("Losers — lose under UT (net positive)", "#b2182b"),
    }

    def _make_eu_group_lines(exclude=frozenset(), suffix="", title_extra=""):
        panel = eu_panel.loc[~eu_panel["iso_partner"].isin(exclude)].copy()
        agg = (
            panel.groupby(["group", "year"])["net_misalignment_bn"]
            .sum()
            .reset_index()
        )

        fig, ax = plt.subplots(figsize=(12, 7))
        for grp_key, (lbl, color) in GROUP_META.items():
            sub = agg.loc[agg["group"] == grp_key].sort_values("year")
            if sub.empty:
                continue
            n_members = panel.loc[panel["group"] == grp_key, "iso_partner"].nunique()
            ax.plot(
                sub["year"], sub["net_misalignment_bn"],
                marker="o", markersize=5, linewidth=2.4, color=color,
                label=f"{lbl} — {n_members} countries",
            )
            last = sub.dropna(subset=["net_misalignment_bn"]).tail(1)
            if not last.empty:
                ax.annotate(
                    f"{last['net_misalignment_bn'].iloc[0]:,.0f}",
                    (last["year"].iloc[0], last["net_misalignment_bn"].iloc[0]),
                    textcoords="offset points", xytext=(6, 0),
                    fontsize=9, color=color, fontweight="bold", va="center",
                )

        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Year")
        ax.set_ylabel("Aggregate net misalignment of " + HOME_LABEL + "-MNE profit, USD bn")
        ax.set_xticks(_eu_years)
        ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
        ax.set_title(
            "EU winners vs losers under unitary taxation of " + HOME_LABEL + " multinationals"
            f"{title_extra}, {min(_eu_years)}–{max(_eu_years)}",
            fontsize=13,
        )
        ax.legend(loc="best", fontsize=10)
        _excl_txt = f" (EU-27 excl. {', '.join(sorted(exclude))})" if exclude else " (EU-27)"
        fig.text(
            0.01, -0.02,
            "Note: Net misalignment summed within each group per year. Negative (winners) = profit a unitary "
            "(employees+payroll, 50/50) split would ADD to these EU countries; positive (losers) = profit they "
            f"would LOSE. Group membership fixed by cumulative net misalignment over the period{_excl_txt}. "
            "Baseline disaggregated CbCR; " + HOME_LABEL + " parents only.",
            ha="left", va="top", fontsize=9, wrap=True,
        )
        plt.tight_layout()
        p = OUTPUT_FIGURES / (
            f"eu_net_misalignment_aggregated{suffix}_{min(_eu_years)}_{max(_eu_years)}.png"
        )
        plt.savefig(_longpath(p), dpi=300, bbox_inches="tight")
        plt.close()
        return p

    _agg_all = _make_eu_group_lines()
    _agg_excl = _make_eu_group_lines(
        exclude=frozenset({"LUX"}), suffix="_excl_LUX",
        title_extra=" (excl. Luxembourg)",
    )

    _n_benefit = int((eu_totals["group"] == "benefits_from_ut").sum())
    _n_lose = int((eu_totals["group"] == "loses_under_ut").sum())
    print(
        f"\n[EU figure] aggregated winners/losers lines saved:\n"
        f"  {_agg_all}\n  {_agg_excl}\n"
        f"  Winners (net negative): {_n_benefit} EU countries | "
        f"Losers (net positive): {_n_lose} EU countries\n"
        f"  Data: eu_net_misalignment_by_year.csv + eu_net_misalignment_classification.csv"
    )


# %% [6C] CCCTB variant of the EU winners/losers line graph (item 3).
# The headline figure uses employees+payroll (50/50), which classifies
# Luxembourg as a "winner" because that formula ignores assets and sales.
# Rebuild the same aggregated winners/losers lines on the CCCTB formula
# (1/3 sales, 1/3 assets, 1/6 employees, 1/6 payroll) to test whether LUX
# reclassifies as a haven. Net misalignment is rate-independent → only the
# apportionment formula matters. Outputs carry a `_ccctb` suffix so they sit
# beside the employees+payroll versions without overwriting them.
def _build_eu_lines_for_formula(formula_name, file_suffix, formula_desc, title_suffix):
    src = run_summary.loc[run_summary["formula_name"] == formula_name]
    if src.empty:
        print(f"\n[EU figure{title_suffix}] No '{formula_name}' run; skipping.")
        return
    eu = pd.read_csv(_longpath(src.iloc[0]["country_file"]))
    eu["year"] = pd.to_numeric(eu["year"], errors="coerce")
    eu = eu.loc[eu["iso_partner"].isin(EU27)].copy()
    eu["net_misalignment_musd"] = (
        pd.to_numeric(eu["positive_misalignment"], errors="coerce").fillna(0.0)
        - pd.to_numeric(eu["negative_misalignment"], errors="coerce").fillna(0.0)
    )
    panel = eu.groupby(
        ["iso_partner", "partner_jurisdiction", "year"], as_index=False
    )["net_misalignment_musd"].sum()
    panel["net_misalignment_bn"] = panel["net_misalignment_musd"] / 1000.0
    totals = (
        panel.groupby(["iso_partner", "partner_jurisdiction"], as_index=False)[
            "net_misalignment_musd"
        ].sum().rename(columns={"net_misalignment_musd": "total_net_misalignment_musd"})
    )
    totals["group"] = np.where(
        totals["total_net_misalignment_musd"] < 0, "benefits_from_ut", "loses_under_ut"
    )
    panel = panel.merge(totals[["iso_partner", "group"]], on="iso_partner", how="left")
    panel.sort_values(["group", "iso_partner", "year"]).to_csv(
        OUTPUT_TABLES / f"eu_net_misalignment_by_year{file_suffix}.csv", index=False
    )
    totals.sort_values(["group", "total_net_misalignment_musd"]).to_csv(
        OUTPUT_TABLES / f"eu_net_misalignment_classification{file_suffix}.csv", index=False
    )
    years = sorted(int(y) for y in panel["year"].dropna().unique())
    meta = {
        "benefits_from_ut": ("Winners — benefit from UT (net negative)", "#1b7837"),
        "loses_under_ut":   ("Losers — lose under UT (net positive)", "#b2182b"),
    }

    def _plot(exclude=frozenset(), suffix="", extra=""):
        p2 = panel.loc[~panel["iso_partner"].isin(exclude)]
        agg = p2.groupby(["group", "year"])["net_misalignment_bn"].sum().reset_index()
        fig, ax = plt.subplots(figsize=(12, 7))
        for gk, (lbl, color) in meta.items():
            sub = agg.loc[agg["group"] == gk].sort_values("year")
            if sub.empty:
                continue
            n = p2.loc[p2["group"] == gk, "iso_partner"].nunique()
            ax.plot(sub["year"], sub["net_misalignment_bn"], marker="o", markersize=5,
                    linewidth=2.4, color=color, label=f"{lbl} — {n} countries")
            last = sub.tail(1)
            ax.annotate(f"{last['net_misalignment_bn'].iloc[0]:,.0f}",
                        (last["year"].iloc[0], last["net_misalignment_bn"].iloc[0]),
                        textcoords="offset points", xytext=(6, 0), fontsize=9,
                        color=color, fontweight="bold", va="center")
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Year")
        ax.set_ylabel("Aggregate net misalignment of " + HOME_LABEL + "-MNE profit, USD bn")
        ax.set_xticks(years)
        ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
        ax.set_title("EU winners vs losers under unitary taxation of " + HOME_LABEL + " multinationals"
                     f"{title_suffix}{extra}, {min(years)}-{max(years)}", fontsize=13)
        ax.legend(loc="best", fontsize=10)
        et = f" (EU-27 excl. {', '.join(sorted(exclude))})" if exclude else " (EU-27)"
        fig.text(0.01, -0.02,
                 "Note: Net misalignment summed within each group per year. Negative (winners) = profit a unitary "
                 f"({formula_desc}) split would ADD to these EU countries; positive (losers) = profit they would "
                 f"LOSE. Group membership fixed by cumulative net misalignment over the period{et}. Baseline "
                 "disaggregated CbCR; " + HOME_LABEL + " parents only.",
                 ha="left", va="top", fontsize=9, wrap=True)
        plt.tight_layout()
        out = OUTPUT_FIGURES / f"eu_net_misalignment_aggregated{file_suffix}{suffix}_{min(years)}_{max(years)}.png"
        plt.savefig(_longpath(out), dpi=300, bbox_inches="tight")
        plt.close()
        return out

    pa = _plot()
    pe = _plot(exclude=frozenset({"LUX"}), suffix="_excl_LUX", extra=" (excl. Luxembourg)")
    lux = totals.loc[totals["iso_partner"] == "LUX", "group"]
    print(f"\n[EU figure{title_suffix}] saved:\n  {pa}\n  {pe}\n"
          f"  Winners: {int((totals['group']=='benefits_from_ut').sum())} | "
          f"Losers: {int((totals['group']=='loses_under_ut').sum())} | "
          f"Luxembourg classified as: {lux.iloc[0] if not lux.empty else 'n/a'}")


_build_eu_lines_for_formula(
    "ccctb", "_ccctb",
    "CCCTB: 1/3 sales, 1/3 assets, 1/6 employees, 1/6 payroll",
    " — CCCTB formula",
)


# %% [7] Bilateral links
if not RUN_BILATERALS:
    print("\nSkipping bilateral calculations.")
else:
    from pandas.errors import EmptyDataError

    def add_loss_rate_to_misalignment(misalignment_df):
        df = misalignment_df.copy()

        if "loss_rate_col" not in df.columns:
            raise ValueError("misalignment_df must contain 'loss_rate_col'.")

        df["loss_rate"] = np.nan

        for rate_col in df["loss_rate_col"].dropna().unique():
            if rate_col not in df.columns:
                raise ValueError(
                    f"Loss-rate column '{rate_col}' listed in loss_rate_col is not present "
                    f"in the misalignment data."
                )
            mask = df["loss_rate_col"] == rate_col
            df.loc[mask, "loss_rate"] = pd.to_numeric(
                df.loc[mask, rate_col], errors="coerce"
            )

        df["loss_rate"] = df["loss_rate"].fillna(0)
        return df

    def estimate_bilateral_links_from_misalignment(misalignment_df):
        output_cols = [
            "year",
            "iso_responsible",
            "iso_affected",
            "shifted_profit_musd",
            "tax_loss_musd",
        ]

        if misalignment_df.empty:
            return pd.DataFrame(columns=output_cols)

        required_cols = [
            "year",
            "iso_parent",
            "iso_partner",
            "misaligned_profit",
            "loss_rate_col",
        ]
        missing_cols = [
            col for col in required_cols if col not in misalignment_df.columns
        ]
        if missing_cols:
            raise ValueError(
                f"Missing required columns for bilateral estimation: {missing_cols}"
            )

        df = misalignment_df.copy()
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df["misaligned_profit"] = pd.to_numeric(
            df["misaligned_profit"], errors="coerce"
        )

        df = df.loc[
            df["year"].notna()
            & df["iso_parent"].notna()
            & df["iso_partner"].notna()
            & df["misaligned_profit"].notna()
        ].copy()

        if df.empty:
            return pd.DataFrame(columns=output_cols)

        df = add_loss_rate_to_misalignment(df)

        df["positive_misalignment_musd_row"] = np.where(
            df["misaligned_profit"] > 0,
            df["misaligned_profit"] / 1e6,
            0.0,
        )
        df["suffered_shifted_profit_musd_row"] = np.where(
            df["misaligned_profit"] < 0,
            -df["misaligned_profit"] / 1e6,
            0.0,
        )
        df["suffered_tax_loss_musd_row"] = (
            df["suffered_shifted_profit_musd_row"] * df["loss_rate"]
        )

        parent_year_partner = df.groupby(
            ["year", "iso_parent", "iso_partner"], as_index=False
        ).agg(
            positive_misalignment_musd=("positive_misalignment_musd_row", "sum"),
            suffered_shifted_profit_musd=("suffered_shifted_profit_musd_row", "sum"),
            suffered_tax_loss_musd=("suffered_tax_loss_musd_row", "sum"),
        )

        bilateral_parts = []

        for (year, iso_parent), grp in parent_year_partner.groupby(
            ["year", "iso_parent"], sort=False
        ):
            harmers = grp.loc[
                grp["positive_misalignment_musd"] > 0,
                ["iso_partner", "positive_misalignment_musd"],
            ].copy()

            sufferers = grp.loc[
                (grp["suffered_shifted_profit_musd"] > 0)
                | (grp["suffered_tax_loss_musd"] > 0),
                [
                    "iso_partner",
                    "suffered_shifted_profit_musd",
                    "suffered_tax_loss_musd",
                ],
            ].copy()

            if harmers.empty or sufferers.empty:
                continue

            for sufferer in sufferers.itertuples(index=False):
                eligible_harmers = harmers.loc[
                    harmers["iso_partner"] != sufferer.iso_partner
                ].copy()

                total_positive_eligible = eligible_harmers[
                    "positive_misalignment_musd"
                ].sum()

                if total_positive_eligible <= 0:
                    continue

                eligible_harmers["share_of_harm"] = (
                    eligible_harmers["positive_misalignment_musd"]
                    / total_positive_eligible
                )

                eligible_harmers["year"] = int(year)
                eligible_harmers["iso_responsible"] = eligible_harmers["iso_partner"]
                eligible_harmers["iso_affected"] = sufferer.iso_partner
                eligible_harmers["shifted_profit_musd"] = (
                    sufferer.suffered_shifted_profit_musd
                    * eligible_harmers["share_of_harm"]
                )
                eligible_harmers["tax_loss_musd"] = (
                    sufferer.suffered_tax_loss_musd * eligible_harmers["share_of_harm"]
                )

                bilateral_parts.append(
                    eligible_harmers[
                        [
                            "year",
                            "iso_responsible",
                            "iso_affected",
                            "shifted_profit_musd",
                            "tax_loss_musd",
                        ]
                    ]
                )

        if not bilateral_parts:
            return pd.DataFrame(columns=output_cols)

        bilateral_df = pd.concat(bilateral_parts, ignore_index=True)

        bilateral_df = bilateral_df.groupby(
            ["year", "iso_responsible", "iso_affected"], as_index=False
        ).agg(
            shifted_profit_musd=("shifted_profit_musd", "sum"),
            tax_loss_musd=("tax_loss_musd", "sum"),
        )

        bilateral_df = bilateral_df.sort_values(
            ["year", "iso_responsible", "iso_affected"]
        ).reset_index(drop=True)

        return bilateral_df

    bilateral_file_paths = []
    n_bilateral_rows = []

    for row in run_summary.itertuples(index=False):
        misalignment_file = Path(row.misalignment_file)
        bilateral_file = misalignment_file.parent / misalignment_file.name.replace(
            "misalignment__", "bilateral_links__"
        )

        try:
            misalignment_df = pd.read_csv(_longpath(misalignment_file))
            bilateral_df = estimate_bilateral_links_from_misalignment(misalignment_df)
        except EmptyDataError:
            bilateral_df = pd.DataFrame(
                columns=[
                    "year",
                    "iso_responsible",
                    "iso_affected",
                    "shifted_profit_musd",
                    "tax_loss_musd",
                ]
            )

        bilateral_df = order_bilateral_columns(bilateral_df)
        bilateral_df.to_csv(_longpath(bilateral_file), index=False)

        bilateral_file_paths.append(str(bilateral_file))
        n_bilateral_rows.append(len(bilateral_df))

    run_summary["n_bilateral_rows"] = n_bilateral_rows
    run_summary["bilateral_file"] = bilateral_file_paths
    run_summary = order_run_summary_columns(run_summary)

    run_summary.to_csv(
        OUTPUT_ROOT / "run_summary.csv",
        index=False,
    )

    print("\n" + "=" * 100)
    print("BILATERAL LINK FILES CREATED")
    print("=" * 100)
    print(
        run_summary[
            [
                "sample_name",
                "formula_name",
                "etr_name",
                "rate_mode",
                "n_bilateral_rows",
                "bilateral_file",
            ]
        ].to_string(index=False)
    )


# %% [8] Profit missing from the EU (bilateral attribution).
#
# Uses the bilateral link logic to answer: of the US-MNE profit that EU
# countries are MISSING (their negative misalignment — profit that a unitary
# split would assign to them but is reported elsewhere), where is it booked
# instead? Each EU sufferer's missing profit is attributed across the
# jurisdictions that over-report US-MNE profit (the "harmers"), proportionally
# to how much each over-reports — exactly the allocation script 5's bilateral
# block uses, restricted here to one parent (USA) and one headline spec.
#
# shifted_profit is rate-independent, so we read a single misalignment file
# (employees_payroll, loss_cit_gain_etr). The chart stacks each year's total
# EU-missing profit by destination jurisdiction (top 8 + Other), so it shows
# both the scale of EU under-allocation and the EU-vs-non-EU haven split.

BIL_FORMULA = "employees_payroll"
BIL_RATE_MODE = "loss_cit_gain_etr"


def _bilateral_shifted_profit(misalignment_df):
    """Attribute each sufferer's missing profit across over-reporting partners,
    per (year, parent). Returns (year, iso_responsible, iso_affected,
    shifted_profit_musd). Profit-only (rate-independent) reduction of the
    canonical bilateral estimator."""
    df = misalignment_df.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["misaligned_profit"] = pd.to_numeric(df["misaligned_profit"], errors="coerce")
    df = df.loc[
        df["year"].notna()
        & df["iso_parent"].notna()
        & df["iso_partner"].notna()
        & df["misaligned_profit"].notna()
    ].copy()

    df["pos_musd"] = np.where(df["misaligned_profit"] > 0, df["misaligned_profit"] / 1e6, 0.0)
    df["suffered_musd"] = np.where(df["misaligned_profit"] < 0, -df["misaligned_profit"] / 1e6, 0.0)

    pyp = df.groupby(["year", "iso_parent", "iso_partner"], as_index=False).agg(
        pos_musd=("pos_musd", "sum"),
        suffered_musd=("suffered_musd", "sum"),
    )

    parts = []
    for (year, _parent), grp in pyp.groupby(["year", "iso_parent"], sort=False):
        harmers = grp.loc[grp["pos_musd"] > 0, ["iso_partner", "pos_musd"]]
        sufferers = grp.loc[grp["suffered_musd"] > 0, ["iso_partner", "suffered_musd"]]
        if harmers.empty or sufferers.empty:
            continue
        for suf in sufferers.itertuples(index=False):
            elig = harmers.loc[harmers["iso_partner"] != suf.iso_partner].copy()
            tot = elig["pos_musd"].sum()
            if tot <= 0:
                continue
            elig["shifted_profit_musd"] = suf.suffered_musd * elig["pos_musd"] / tot
            elig["year"] = int(year)
            elig["iso_responsible"] = elig["iso_partner"]
            elig["iso_affected"] = suf.iso_partner
            parts.append(elig[["year", "iso_responsible", "iso_affected", "shifted_profit_musd"]])

    if not parts:
        return pd.DataFrame(
            columns=["year", "iso_responsible", "iso_affected", "shifted_profit_musd"]
        )
    out = pd.concat(parts, ignore_index=True)
    return out.groupby(
        ["year", "iso_responsible", "iso_affected"], as_index=False
    )["shifted_profit_musd"].sum()


def eu_missing_share_chart(em, etr_by_iso, file_suffix, title_extra, top_n=15):
    """Top-N destinations of EU-missing profit, by SHARE of the cumulative total,
    with the ETR each destination charges. Restricts to the largest destinations
    (drops the long 'Other' tail); bars are coloured by ETR so the 'profit goes
    where the tax is lowest' pattern is visible."""
    from matplotlib.colors import Normalize
    from matplotlib.cm import ScalarMappable
    if em.empty:
        print(f"\n[EU-missing shares{title_extra}] no rows; skipping.")
        return
    years = sorted(int(y) for y in em["year"].dropna().unique())
    dest_tot = em.groupby("iso_responsible")["shifted_profit_musd"].sum().sort_values(ascending=False)
    grand = dest_tot.sum()
    top = dest_tot.head(top_n)
    covered = 100.0 * top.sum() / grand if grand else float("nan")

    order = list(top.index[::-1])                  # largest ends up at the top of barh
    shares = [100.0 * dest_tot[d] / grand for d in order]
    bn = [dest_tot[d] / 1000.0 for d in order]
    etrs = [etr_by_iso.get(d, np.nan) for d in order]
    labels = [f"{d} (EU)" if d in EU27 else d for d in order]

    norm = Normalize(vmin=0, vmax=25)              # ETR % colour scale
    cmap = plt.get_cmap("RdYlGn")                  # low ETR -> red, high -> green
    colors = [cmap(norm(e)) if pd.notna(e) else "#cccccc" for e in etrs]

    fig, ax = plt.subplots(figsize=(11.5, 8))
    bars = ax.barh(labels, shares, color=colors, edgecolor="white")
    for b, s, b_bn, e in zip(bars, shares, bn, etrs):
        etr_txt = f"ETR {e:.0f}%" if pd.notna(e) else "ETR n/a"
        ax.annotate(f"{s:.1f}%  (${b_bn:,.0f}bn, {etr_txt})",
                    (b.get_width(), b.get_y() + b.get_height() / 2),
                    textcoords="offset points", xytext=(4, 0), va="center", fontsize=8)
    ax.set_xlabel("Share of total profit missing from the EU, %")
    ax.set_title(f"Where the EU's missing profit is booked — and how little tax it pays there{title_extra}\n"
                 f"Top {top_n} destinations by share of {HOME_LABEL}-MNE profit shifted out of the EU, "
                 f"{min(years)}–{max(years)}", fontsize=12)
    ax.grid(True, axis="x", linewidth=0.3, alpha=0.5)
    ax.margins(x=0.24)
    sm = ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, pad=0.02, fraction=0.045)
    cb.set_label(f"ETR {HOME_LABEL} MNEs pay there, % (period mean, 5yr-rolling)", fontsize=9)
    fig.text(0.01, -0.02,
             f"Note: Top {top_n} destinations of profit a unitary (employees+payroll, 50/50) split would assign to EU "
             f"countries but that {HOME_LABEL} MNEs book elsewhere (bilateral attribution, cumulative "
             f"{min(years)}-{max(years)}); they cover {covered:.0f}% of all EU-missing profit (long tail omitted). "
             f"Bars coloured by the ETR {HOME_LABEL} MNEs pay in each destination; '(EU)' = EU member. "
             f"Baseline disaggregated CbCR; {HOME_LABEL} parents only.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    out = OUTPUT_FIGURES / f"eu_missing_profit_shares{file_suffix}_{min(years)}_{max(years)}.png"
    plt.savefig(_longpath(out), dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\n[EU-missing shares{title_extra}] saved: {out}\n  top {top_n} cover {covered:.0f}% | "
          + ", ".join(f"{d} {100.0*dest_tot[d]/grand:.0f}% (ETR {etr_by_iso.get(d, float('nan')):.0f}%)"
                      for d in top.head(6).index))

    # --- Companion: yearly distribution among the top 10 destinations ---
    # 100%-stacked bar per year (each bar = the 10 largest cumulative
    # destinations renormalised to 100%), so the year-to-year shift in WHERE the
    # EU's missing profit is booked is visible.
    top10 = list(dest_tot.head(10).index)
    yw = (em[em["iso_responsible"].isin(top10)]
          .groupby(["year", "iso_responsible"])["shifted_profit_musd"].sum()
          .unstack("iso_responsible").reindex(years).fillna(0.0))
    yw = yw[[d for d in top10 if d in yw.columns]]
    ysh = yw.div(yw.sum(axis=1).replace(0, np.nan), axis=0) * 100.0
    fig, ax = plt.subplots(figsize=(12.5, 7.5))
    bottoms = np.zeros(len(years))
    cmap = plt.get_cmap("tab20")
    for i, d in enumerate(top10):
        vals = ysh[d].fillna(0.0).to_numpy() if d in ysh.columns else np.zeros(len(years))
        etr_d = etr_by_iso.get(d, float("nan"))
        lbl = (f"{d} (EU, ETR {etr_d:.0f}%)" if d in EU27 else f"{d} (ETR {etr_d:.0f}%)")
        ax.bar(years, vals, bottom=bottoms, label=lbl, color=cmap(i % 20),
               edgecolor="white", linewidth=0.4, width=0.8)
        bottoms += vals
    ax.set_ylim(0, 100)
    ax.set_xlabel("Year")
    ax.set_ylabel("Share of top-10 EU-missing profit, %")
    ax.set_xticks(years)
    ax.set_title("Distribution of the EU's missing profit across its top-10 destinations, by year"
                 f"{title_extra}\n{HOME_LABEL}-MNE profit shifted out of the EU "
                 f"(each year = 100% of the top 10), {min(years)}–{max(years)}", fontsize=12)
    ax.legend(title="Booked in (ETR = period mean)", ncol=1, fontsize=8,
              loc="center left", bbox_to_anchor=(1.005, 0.5))
    fig.text(0.01, -0.02,
             "Note: Each bar is one year, normalised to 100% over the 10 largest cumulative destinations; a segment "
             "is that destination's share of the top-10 EU-missing profit that year. ETR = period mean of the "
             f"5yr-rolling partner ETR. Baseline disaggregated CbCR; {HOME_LABEL} parents only.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    out2 = OUTPUT_FIGURES / f"eu_missing_profit_shares_yearly{file_suffix}_{min(years)}_{max(years)}.png"
    plt.savefig(_longpath(out2), dpi=300, bbox_inches="tight")
    plt.close()
    print(f"  yearly distribution saved: {out2}")


_bil_src = run_summary.loc[
    (run_summary["formula_name"] == BIL_FORMULA)
    & (run_summary["rate_mode"] == BIL_RATE_MODE)
]
if _bil_src.empty:
    print(f"\n[EU-missing figure] No '{BIL_FORMULA}'/{BIL_RATE_MODE} run; skipping.")
else:
    _mis_file = _bil_src.iloc[0]["misalignment_file"]
    _mis = pd.read_csv(_longpath(_mis_file))
    bilateral = _bilateral_shifted_profit(_mis)

    # Profit MISSING from EU = bilateral flows whose sufferer (iso_affected) is
    # in the EU. iso_responsible is where US MNEs book it instead.
    eu_missing = bilateral.loc[bilateral["iso_affected"].isin(EU27)].copy()

    if eu_missing.empty:
        print("\n[EU-missing figure] No EU sufferers found; skipping.")
    else:
        eu_missing.sort_values(
            ["year", "shifted_profit_musd"], ascending=[True, False]
        ).to_csv(OUTPUT_TABLES / "eu_missing_profit_bilateral.csv", index=False)

        # ETR each destination charges = period mean of the 5yr-rolling partner
        # ETR (etr_partner_median_corrected), keyed by jurisdiction.
        etr_by_iso = (
            _mis.assign(_e=pd.to_numeric(_mis["etr_partner_median_corrected"],
                                         errors="coerce") * 100.0)
            .groupby("iso_partner")["_e"].mean().to_dict()
        )
        eu_missing_share_chart(eu_missing, etr_by_iso, "", "")


# %% [8b] excl-Luxembourg variant of the "profit missing from the EU" chart (item 2).
# The all-EU chart's 2021 spike is partly Luxembourg's anomalous -$87bn loss.
# Rebuild it excluding LUX as an affected (sufferer) country. Reuses the already
# computed module-level `bilateral` table (rate-independent, employees+payroll).
if "bilateral" in globals() and not bilateral.empty:
    def _build_eu_missing(exclude_affected, file_suffix, title_extra):
        affected = EU27 - set(exclude_affected)
        em = bilateral.loc[bilateral["iso_affected"].isin(affected)].copy()
        if em.empty:
            print(f"\n[EU-missing figure{title_extra}] no rows; skipping.")
            return
        em.sort_values(["year", "shifted_profit_musd"], ascending=[True, False]).to_csv(
            OUTPUT_TABLES / f"eu_missing_profit_bilateral{file_suffix}.csv", index=False
        )
        eu_missing_share_chart(em, etr_by_iso, file_suffix, title_extra)

    _build_eu_missing(frozenset({"LUX"}), "_excl_LUX", " (excl. Luxembourg)")


# %% [9] How US corporations exploit the EU (CURRENT profit-shifting framing).
#
# Reframed per request: this describes profit shifting under the STATUS QUO, not
# who gains/loses from a UT reform.
#   WINNERS = EU jurisdictions that RECEIVE illegitimate profit (report more
#             US-MNE profit than real activity warrants → net positive
#             misalignment). The few havens.
#   LOSERS  = EU jurisdictions whose profit is generated there but booked
#             elsewhere (net negative misalignment). The many.
# Net misalignment = reported − (employees+payroll 50/50) theoretical, the same
# quantity, read in profit-shifting terms. ETR = period mean of the 5-year
# rolling partner ETR (etr_partner_median_corrected), shown as %.
PS_FORMULA = "employees_payroll"
_ps_src = run_summary.loc[run_summary["formula_name"] == PS_FORMULA]
if _ps_src.empty:
    print(f"\n[EU exploitation figures] No '{PS_FORMULA}' run; skipping.")
else:
    ps = pd.read_csv(_longpath(_ps_src.iloc[0]["country_file"]))
    ps["year"] = pd.to_numeric(ps["year"], errors="coerce")
    ps = ps.loc[ps["iso_partner"].isin(EU27)].copy()
    for _c in ["positive_misalignment", "negative_misalignment", "reported_profit",
               "etr_partner_median_corrected"]:
        ps[_c] = pd.to_numeric(ps[_c], errors="coerce")
    ps["over_reported_bn"] = ps["positive_misalignment"].fillna(0.0) / 1000.0   # shifted IN
    ps["under_reported_bn"] = ps["negative_misalignment"].fillna(0.0) / 1000.0  # shifted OUT (magnitude)
    ps["net_bn"] = ps["over_reported_bn"] - ps["under_reported_bn"]
    ps_years = sorted(int(y) for y in ps["year"].dropna().unique())

    summ = ps.groupby(["iso_partner", "partner_jurisdiction"], as_index=False).agg(
        net_bn=("net_bn", "sum"),
        reported_bn=("reported_profit", lambda x: x.sum() / 1000.0),
        etr=("etr_partner_median_corrected", "mean"),
    )
    summ["etr_pct"] = summ["etr"] * 100.0
    summ["role"] = np.where(summ["net_bn"] > 0, "winner_haven", "loser_victim")
    summ.sort_values("net_bn", ascending=False).to_csv(
        OUTPUT_TABLES / "eu_profit_shifting_roles.csv", index=False
    )
    etr_by_iso = summ.set_index("iso_partner")["etr_pct"].to_dict()

    # ===== Figure 1: the widening gap — few havens (up) vs the many (down) =====
    haven_tot = ps.groupby("iso_partner")["over_reported_bn"].sum().sort_values(ascending=False)
    top_havens = [h for h in haven_tot.index if haven_tot[h] > 0][:5]
    up = (ps[ps["iso_partner"].isin(top_havens)]
          .pivot_table(index="year", columns="iso_partner",
                       values="over_reported_bn", aggfunc="sum")
          .reindex(ps_years).fillna(0.0))
    up = up[[h for h in top_havens if h in up.columns]]
    over_tot = ps.groupby("year")["over_reported_bn"].sum().reindex(ps_years).fillna(0.0)
    other_up = over_tot - up.sum(axis=1)
    down_total = -ps.groupby("year")["under_reported_bn"].sum().reindex(ps_years).fillna(0.0)

    yr_net = ps.groupby(["year", "iso_partner"])["net_bn"].sum().reset_index()
    n_win = yr_net[yr_net.net_bn > 0].groupby("year")["iso_partner"].nunique().reindex(ps_years).fillna(0)
    n_los = yr_net[yr_net.net_bn < 0].groupby("year")["iso_partner"].nunique().reindex(ps_years).fillna(0)

    fig, ax = plt.subplots(figsize=(13.5, 8))
    cmap = plt.get_cmap("autumn")
    bottoms = np.zeros(len(ps_years))
    for i, h in enumerate(up.columns):
        lbl = f"{h} (ETR {etr_by_iso.get(h, float('nan')):.0f}%)"
        ax.bar(ps_years, up[h].to_numpy(), bottom=bottoms, label=lbl,
               color=cmap(i / max(len(up.columns), 1) * 0.75), edgecolor="white", width=0.72)
        bottoms += up[h].to_numpy()
    ax.bar(ps_years, other_up.to_numpy(), bottom=bottoms, label="Other EU havens",
           color="#fdd0a2", edgecolor="white", width=0.72)
    ax.bar(ps_years, down_total.to_numpy(), label="Profit shifted OUT (the many EU countries)",
           color="#3182bd", edgecolor="white", width=0.72)
    ax.axhline(0, color="black", linewidth=0.9)
    for j, y in enumerate(ps_years):
        ax.annotate(f"+{over_tot.iloc[j]:,.0f}\n({int(n_win.iloc[j])} havens)",
                    (y, over_tot.iloc[j]), textcoords="offset points", xytext=(0, 4),
                    ha="center", fontsize=8, fontweight="bold", color="#b30000")
        ax.annotate(f"{down_total.iloc[j]:,.0f}\n({int(n_los.iloc[j])} countries)",
                    (y, down_total.iloc[j]), textcoords="offset points", xytext=(0, -18),
                    ha="center", fontsize=8, color="#08519c")
    ax.set_title("" + HOME_LABEL + " multinationals book EU profit in a few low-tax havens, not where it is earned\n"
                 f"Profit over-reported (up) vs shifted out (down), {min(ps_years)}–{max(ps_years)}",
                 fontsize=13)
    ax.set_xlabel("Year")
    ax.set_ylabel("" + HOME_LABEL + "-MNE profit misalignment, USD bn")
    ax.set_xticks(ps_years)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
    ax.legend(title="Profit over-reported in (ETR = period mean, 5yr-rolling)",
              ncol=2, fontsize=9, loc="upper left")
    fig.text(0.01, -0.02,
             "Note: 'Over-reported' = " + HOME_LABEL + "-MNE profit booked in a country beyond what an employees+payroll (50/50) "
             "split implies (shifted IN); 'shifted out' = profit a country generates but that is booked elsewhere. "
             "A handful of low-ETR havens absorb the over-reported profit while many EU countries are drained — and "
             "the haven total grows over the period. ETR = period mean of the 5-year-rolling partner ETR. "
             "Baseline disaggregated CbCR; " + HOME_LABEL + " parents only.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    _f1 = OUTPUT_FIGURES / f"eu_profit_shifting_gap_{min(ps_years)}_{max(ps_years)}.png"
    plt.savefig(_longpath(_f1), dpi=300, bbox_inches="tight")
    plt.close()

    # ===== Figure 2: profit follows the lowest tax rate (scatter) =====
    from matplotlib.lines import Line2D
    fig, ax = plt.subplots(figsize=(12, 8))
    for _, r in summ.iterrows():
        color = "#b2182b" if r["net_bn"] > 0 else "#2166ac"
        size = 30 + 25 * np.sqrt(abs(r["net_bn"]))
        ax.scatter(r["net_bn"], r["etr_pct"], s=size, color=color, alpha=0.65,
                   edgecolor="white", zorder=3)
        if abs(r["net_bn"]) >= 3 or r["etr_pct"] <= 6:
            ax.annotate(r["iso_partner"], (r["net_bn"], r["etr_pct"]),
                        textcoords="offset points", xytext=(5, 3), fontsize=8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.axhline(15, color="grey", linestyle="--", linewidth=1)
    ax.annotate("15% global minimum-tax reference", (ax.get_xlim()[0], 15),
                xytext=(5, 4), textcoords="offset points", fontsize=8, color="grey")
    ax.set_xlabel("Cumulative net misalignment, USD bn   "
                  "(→ profit shifted IN / haven    ← profit shifted OUT / victim)")
    ax.set_ylabel("Effective tax rate paid by " + HOME_LABEL + " MNEs, %  (period mean, 5yr-rolling)")
    ax.set_title("" + HOME_LABEL + "-MNE profit is booked where the tax rate is lowest\n"
                 f"EU jurisdictions: over/under-reporting vs ETR, {min(ps_years)}–{max(ps_years)}",
                 fontsize=13)
    ax.grid(True, linewidth=0.3, alpha=0.5)
    ax.legend(handles=[
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#b2182b", markersize=11,
               label="Winner — receives shifted-in profit (haven)"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#2166ac", markersize=11,
               label="Loser — profit generated here is shifted out"),
    ], loc="upper right", fontsize=9)
    fig.text(0.01, -0.02,
             "Note: x = cumulative (2016–2022) net misalignment (reported − employees+payroll-implied profit); "
             "right = profit shifted IN (haven), left = shifted OUT (victim). y = ETR US MNEs actually pay there. "
             "Havens cluster at low ETR. LUX and MLT sit on the left only because large 2021 book losses make their "
             "cumulative net negative — their very low ETR shows they are havens too. Bubble size ∝ √|net misalignment|. "
             "Baseline disaggregated CbCR; " + HOME_LABEL + " parents only.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    _f2 = OUTPUT_FIGURES / f"eu_profit_vs_etr_scatter_{min(ps_years)}_{max(ps_years)}.png"
    plt.savefig(_longpath(_f2), dpi=300, bbox_inches="tight")
    plt.close()

    print(f"\n[EU exploitation figures] saved:\n  {_f1}\n  {_f2}\n"
          f"  Over-reported in havens: {over_tot.iloc[0]:,.0f} bn ({ps_years[0]}) "
          f"-> {over_tot.iloc[-1]:,.0f} bn ({ps_years[-1]})\n"
          f"  Shifted out of the many: {-down_total.iloc[0]:,.0f} bn -> {-down_total.iloc[-1]:,.0f} bn\n"
          f"  Data: eu_profit_shifting_roles.csv")


# %% [9b] excl-Luxembourg & Malta variant of the gap chart.
# Removes the two low-ETR havens whose large 2021 book losses distort the
# "shifted out" side (and the 2021 spike), leaving a cleaner few-vs-many gap.
if "ps" in globals():
    _excl = frozenset({"LUX", "MLT"})
    ps2 = ps.loc[~ps["iso_partner"].isin(_excl)].copy()
    yrs = sorted(int(y) for y in ps2["year"].dropna().unique())
    etr2 = (ps2.groupby("iso_partner")["etr_partner_median_corrected"].mean() * 100).to_dict()
    haven_tot = ps2.groupby("iso_partner")["over_reported_bn"].sum().sort_values(ascending=False)
    top_havens = [h for h in haven_tot.index if haven_tot[h] > 0][:5]
    up = (ps2[ps2["iso_partner"].isin(top_havens)]
          .pivot_table(index="year", columns="iso_partner", values="over_reported_bn", aggfunc="sum")
          .reindex(yrs).fillna(0.0))
    up = up[[h for h in top_havens if h in up.columns]]
    over_tot = ps2.groupby("year")["over_reported_bn"].sum().reindex(yrs).fillna(0.0)
    other_up = over_tot - up.sum(axis=1)
    down_total = -ps2.groupby("year")["under_reported_bn"].sum().reindex(yrs).fillna(0.0)
    yr_net = ps2.groupby(["year", "iso_partner"])["net_bn"].sum().reset_index()
    n_win = yr_net[yr_net.net_bn > 0].groupby("year")["iso_partner"].nunique().reindex(yrs).fillna(0)
    n_los = yr_net[yr_net.net_bn < 0].groupby("year")["iso_partner"].nunique().reindex(yrs).fillna(0)

    fig, ax = plt.subplots(figsize=(13.5, 8))
    cmap = plt.get_cmap("autumn")
    bottoms = np.zeros(len(yrs))
    for i, h in enumerate(up.columns):
        ax.bar(yrs, up[h].to_numpy(), bottom=bottoms,
               label=f"{h} (ETR {etr2.get(h, float('nan')):.0f}%)",
               color=cmap(i / max(len(up.columns), 1) * 0.75), edgecolor="white", width=0.72)
        bottoms += up[h].to_numpy()
    ax.bar(yrs, other_up.to_numpy(), bottom=bottoms, label="Other EU havens",
           color="#fdd0a2", edgecolor="white", width=0.72)
    ax.bar(yrs, down_total.to_numpy(), label="Profit shifted OUT (the many EU countries)",
           color="#3182bd", edgecolor="white", width=0.72)
    ax.axhline(0, color="black", linewidth=0.9)
    for j, y in enumerate(yrs):
        ax.annotate(f"+{over_tot.iloc[j]:,.0f}\n({int(n_win.iloc[j])} havens)",
                    (y, over_tot.iloc[j]), textcoords="offset points", xytext=(0, 4),
                    ha="center", fontsize=8, fontweight="bold", color="#b30000")
        ax.annotate(f"{down_total.iloc[j]:,.0f}\n({int(n_los.iloc[j])} countries)",
                    (y, down_total.iloc[j]), textcoords="offset points", xytext=(0, -18),
                    ha="center", fontsize=8, color="#08519c")
    ax.set_title("" + HOME_LABEL + " multinationals book EU profit in a few low-tax havens, not where it is earned "
                 "(excl. Luxembourg & Malta)\n"
                 f"Profit over-reported (up) vs shifted out (down), {min(yrs)}–{max(yrs)}", fontsize=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("" + HOME_LABEL + "-MNE profit misalignment, USD bn")
    ax.set_xticks(yrs)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
    ax.legend(title="Profit over-reported in (ETR = period mean, 5yr-rolling)",
              ncol=2, fontsize=9, loc="upper left")
    fig.text(0.01, -0.02,
             "Note: As the main gap chart, excluding Luxembourg and Malta — two low-ETR havens whose large 2021 "
             "book losses otherwise distort the 'shifted out' side. The few-vs-many gap and its widening remain. "
             "Baseline disaggregated CbCR; " + HOME_LABEL + " parents only.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    _f1b = OUTPUT_FIGURES / f"eu_profit_shifting_gap_excl_LUX_MLT_{min(yrs)}_{max(yrs)}.png"
    plt.savefig(_longpath(_f1b), dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\n[EU exploitation figure excl LUX&MLT] saved: {_f1b}\n"
          f"  Over-reported: {over_tot.iloc[0]:,.0f} -> {over_tot.iloc[-1]:,.0f} bn | "
          f"Shifted out: {-down_total.iloc[0]:,.0f} -> {-down_total.iloc[-1]:,.0f} bn")


# %% [9c] Same exploitation analysis under a different formula (CCCTB).
# Generalises section [9]/[9b] so the gap chart, the ETR scatter and the
# excl-LUX&MLT gap variant can be produced on any apportionment formula. Called
# for CCCTB (1/3 sales, 1/3 assets, 1/6 employees, 1/6 payroll) so the
# profit-shifting story can be compared against the employees+payroll headline.
def build_exploitation_for_formula(formula_name, file_suffix, title_suffix):
    src = run_summary.loc[run_summary["formula_name"] == formula_name]
    if src.empty:
        print(f"\n[EU exploitation{title_suffix}] No '{formula_name}' run; skipping.")
        return
    pf = pd.read_csv(_longpath(src.iloc[0]["country_file"]))
    pf["year"] = pd.to_numeric(pf["year"], errors="coerce")
    pf = pf.loc[pf["iso_partner"].isin(EU27)].copy()
    for c in ["positive_misalignment", "negative_misalignment", "reported_profit",
              "etr_partner_median_corrected"]:
        pf[c] = pd.to_numeric(pf[c], errors="coerce")
    pf["over_reported_bn"] = pf["positive_misalignment"].fillna(0.0) / 1000.0
    pf["under_reported_bn"] = pf["negative_misalignment"].fillna(0.0) / 1000.0
    pf["net_bn"] = pf["over_reported_bn"] - pf["under_reported_bn"]
    years = sorted(int(y) for y in pf["year"].dropna().unique())

    summ = pf.groupby(["iso_partner", "partner_jurisdiction"], as_index=False).agg(
        net_bn=("net_bn", "sum"),
        reported_bn=("reported_profit", lambda x: x.sum() / 1000.0),
        etr=("etr_partner_median_corrected", "mean"),
    )
    summ["etr_pct"] = summ["etr"] * 100.0
    summ["role"] = np.where(summ["net_bn"] > 0, "winner_haven", "loser_victim")
    summ.sort_values("net_bn", ascending=False).to_csv(
        OUTPUT_TABLES / f"eu_profit_shifting_roles{file_suffix}.csv", index=False
    )

    def _gap(ps_in, suffix, extra):
        etr_iso = (ps_in.groupby("iso_partner")["etr_partner_median_corrected"].mean() * 100).to_dict()
        yrs = sorted(int(y) for y in ps_in["year"].dropna().unique())
        haven_tot = ps_in.groupby("iso_partner")["over_reported_bn"].sum().sort_values(ascending=False)
        top_h = [h for h in haven_tot.index if haven_tot[h] > 0][:5]
        up = (ps_in[ps_in["iso_partner"].isin(top_h)]
              .pivot_table(index="year", columns="iso_partner", values="over_reported_bn", aggfunc="sum")
              .reindex(yrs).fillna(0.0))
        up = up[[h for h in top_h if h in up.columns]]
        over_tot = ps_in.groupby("year")["over_reported_bn"].sum().reindex(yrs).fillna(0.0)
        other_up = over_tot - up.sum(axis=1)
        down_total = -ps_in.groupby("year")["under_reported_bn"].sum().reindex(yrs).fillna(0.0)
        yn = ps_in.groupby(["year", "iso_partner"])["net_bn"].sum().reset_index()
        nw = yn[yn.net_bn > 0].groupby("year")["iso_partner"].nunique().reindex(yrs).fillna(0)
        nl = yn[yn.net_bn < 0].groupby("year")["iso_partner"].nunique().reindex(yrs).fillna(0)
        fig, ax = plt.subplots(figsize=(13.5, 8))
        cmap = plt.get_cmap("autumn")
        bottoms = np.zeros(len(yrs))
        for i, h in enumerate(up.columns):
            ax.bar(yrs, up[h].to_numpy(), bottom=bottoms,
                   label=f"{h} (ETR {etr_iso.get(h, float('nan')):.0f}%)",
                   color=cmap(i / max(len(up.columns), 1) * 0.75), edgecolor="white", width=0.72)
            bottoms += up[h].to_numpy()
        ax.bar(yrs, other_up.to_numpy(), bottom=bottoms, label="Other EU havens",
               color="#fdd0a2", edgecolor="white", width=0.72)
        ax.bar(yrs, down_total.to_numpy(), label="Profit shifted OUT (the many EU countries)",
               color="#3182bd", edgecolor="white", width=0.72)
        ax.axhline(0, color="black", linewidth=0.9)
        for j, y in enumerate(yrs):
            ax.annotate(f"+{over_tot.iloc[j]:,.0f}\n({int(nw.iloc[j])} havens)", (y, over_tot.iloc[j]),
                        textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8,
                        fontweight="bold", color="#b30000")
            ax.annotate(f"{down_total.iloc[j]:,.0f}\n({int(nl.iloc[j])} countries)", (y, down_total.iloc[j]),
                        textcoords="offset points", xytext=(0, -18), ha="center", fontsize=8, color="#08519c")
        ax.set_title("" + HOME_LABEL + " multinationals book EU profit in a few low-tax havens, not where it is earned"
                     f"{title_suffix}{extra}\nProfit over-reported (up) vs shifted out (down), "
                     f"{min(yrs)}–{max(yrs)}", fontsize=12)
        ax.set_xlabel("Year")
        ax.set_ylabel("" + HOME_LABEL + "-MNE profit misalignment, USD bn")
        ax.set_xticks(yrs)
        ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
        ax.legend(title="Profit over-reported in (ETR = period mean, 5yr-rolling)",
                  ncol=2, fontsize=9, loc="upper left")
        fig.text(0.01, -0.02,
                 "Note: 'Over-reported' = " + HOME_LABEL + "-MNE profit booked beyond what the apportionment formula implies "
                 "(shifted IN); 'shifted out' = profit generated locally but booked elsewhere. A few low-ETR havens "
                 "absorb the over-reported profit while many EU countries are drained. ETR = period mean of the "
                 "5-year-rolling partner ETR. Baseline disaggregated CbCR; " + HOME_LABEL + " parents only.",
                 ha="left", va="top", fontsize=9, wrap=True)
        plt.tight_layout()
        out = OUTPUT_FIGURES / f"eu_profit_shifting_gap{file_suffix}{suffix}_{min(yrs)}_{max(yrs)}.png"
        plt.savefig(_longpath(out), dpi=300, bbox_inches="tight")
        plt.close()
        return out, over_tot, down_total

    def _scatter(summ_in, suffix, extra):
        from matplotlib.lines import Line2D
        fig, ax = plt.subplots(figsize=(12, 8))
        for _, r in summ_in.iterrows():
            color = "#b2182b" if r["net_bn"] > 0 else "#2166ac"
            size = 30 + 25 * np.sqrt(abs(r["net_bn"]))
            ax.scatter(r["net_bn"], r["etr_pct"], s=size, color=color, alpha=0.65,
                       edgecolor="white", zorder=3)
            if abs(r["net_bn"]) >= 3 or r["etr_pct"] <= 6:
                ax.annotate(r["iso_partner"], (r["net_bn"], r["etr_pct"]),
                            textcoords="offset points", xytext=(5, 3), fontsize=8)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.axhline(15, color="grey", linestyle="--", linewidth=1)
        ax.set_xlabel("Cumulative net misalignment, USD bn   "
                      "(→ profit shifted IN / haven    ← profit shifted OUT / victim)")
        ax.set_ylabel("Effective tax rate paid by " + HOME_LABEL + " MNEs, %  (period mean, 5yr-rolling)")
        ax.set_title("" + HOME_LABEL + "-MNE profit is booked where the tax rate is lowest"
                     f"{title_suffix}{extra}\nEU jurisdictions: over/under-reporting vs ETR, "
                     f"{min(years)}–{max(years)}", fontsize=12)
        ax.grid(True, linewidth=0.3, alpha=0.5)
        ax.legend(handles=[
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#b2182b", markersize=11,
                   label="Winner — receives shifted-in profit (haven)"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor="#2166ac", markersize=11,
                   label="Loser — profit generated here is shifted out"),
        ], loc="upper right", fontsize=9)
        fig.text(0.01, -0.02,
                 "Note: x = cumulative net misalignment (reported − formulary-implied profit); right = shifted IN "
                 "(haven), left = shifted OUT (victim). y = ETR US MNEs actually pay. Havens cluster at low ETR. "
                 "Bubble size ∝ √|net misalignment|. Baseline disaggregated CbCR; " + HOME_LABEL + " parents only.",
                 ha="left", va="top", fontsize=9, wrap=True)
        plt.tight_layout()
        out = OUTPUT_FIGURES / f"eu_profit_vs_etr_scatter{file_suffix}{suffix}_{min(years)}_{max(years)}.png"
        plt.savefig(_longpath(out), dpi=300, bbox_inches="tight")
        plt.close()
        return out

    g_all, over_tot, down_total = _gap(pf, "", "")
    s_all = _scatter(summ, "", "")
    g_excl, _, _ = _gap(pf.loc[~pf["iso_partner"].isin({"LUX", "MLT"})],
                        "_excl_LUX_MLT", " (excl. Luxembourg & Malta)")
    print(f"\n[EU exploitation{title_suffix}] saved:\n  {g_all}\n  {s_all}\n  {g_excl}\n"
          f"  Over-reported in havens: {over_tot.iloc[0]:,.0f} -> {over_tot.iloc[-1]:,.0f} bn | "
          f"Data: eu_profit_shifting_roles{file_suffix}.csv")


build_exploitation_for_formula("ccctb", "_ccctb", " — CCCTB formula")


# %% [9d] The same gap, but in TAX REVENUE rather than profit.
# Tax revenue LOST by a country = the profit shifted out of it (negative
# misalignment) × that country's statutory CIT. Tax revenue GAINED by a haven =
# the profit shifted into it × the ETR the MNEs actually pay there. These are
# exactly the tax_revenue_loss / tax_revenue_gain columns of the
# loss_cit_gain_etr country file. Because havens tax the shifted-in profit at a
# very low ETR, the tax gained is far smaller than the tax lost — the tax gap is
# even starker than the profit gap.
def build_tax_revenue_gap(formula_name, file_suffix, title_suffix):
    src = run_summary.loc[
        (run_summary["formula_name"] == formula_name)
        & (run_summary["rate_mode"] == "loss_cit_gain_etr")
    ]
    if src.empty:
        print(f"\n[tax-revenue gap{title_suffix}] No '{formula_name}'/loss_cit_gain_etr run; skipping.")
        return
    tg = pd.read_csv(_longpath(src.iloc[0]["country_file"]))
    tg["year"] = pd.to_numeric(tg["year"], errors="coerce")
    tg = tg.loc[tg["iso_partner"].isin(EU27)].copy()
    for c in ["tax_revenue_gain", "tax_revenue_loss", "etr_partner_median_corrected"]:
        tg[c] = pd.to_numeric(tg[c], errors="coerce")
    tg["gained_bn"] = tg["tax_revenue_gain"].fillna(0.0) / 1000.0   # haven gains (pos_mis × ETR)
    tg["lost_bn"] = tg["tax_revenue_loss"].fillna(0.0) / 1000.0     # victim losses (neg_mis × CIT)
    etr_iso = (tg.groupby("iso_partner")["etr_partner_median_corrected"].mean() * 100).to_dict()

    summ = tg.groupby(["iso_partner", "partner_jurisdiction"], as_index=False).agg(
        tax_gained_bn=("gained_bn", "sum"), tax_lost_bn=("lost_bn", "sum"))
    summ["net_tax_revenue_bn"] = summ["tax_gained_bn"] - summ["tax_lost_bn"]
    summ.sort_values("net_tax_revenue_bn").to_csv(
        OUTPUT_TABLES / f"eu_tax_revenue_roles{file_suffix}.csv", index=False)

    def _gap(df, suffix, extra, cumulative=False):
        yrs = sorted(int(y) for y in df["year"].dropna().unique())
        haven_tot = df.groupby("iso_partner")["gained_bn"].sum().sort_values(ascending=False)
        top_h = [h for h in haven_tot.index if haven_tot[h] > 0][:5]
        up = (df[df["iso_partner"].isin(top_h)]
              .pivot_table(index="year", columns="iso_partner", values="gained_bn", aggfunc="sum")
              .reindex(yrs).fillna(0.0))
        up = up[[h for h in top_h if h in up.columns]]
        gained_tot = df.groupby("year")["gained_bn"].sum().reindex(yrs).fillna(0.0)
        other_up = gained_tot - up.sum(axis=1)
        lost_tot = -df.groupby("year")["lost_bn"].sum().reindex(yrs).fillna(0.0)
        nh = df[df.gained_bn > 0].groupby("year")["iso_partner"].nunique().reindex(yrs).fillna(0)
        nl = df[df.lost_bn > 0].groupby("year")["iso_partner"].nunique().reindex(yrs).fillna(0)
        if cumulative:                       # running total since the first year
            up = up.cumsum()
            other_up = other_up.cumsum()
            gained_tot = gained_tot.cumsum()
            lost_tot = lost_tot.cumsum()
        fig, ax = plt.subplots(figsize=(13.5, 8))
        cmap = plt.get_cmap("autumn")
        bottoms = np.zeros(len(yrs))
        for i, h in enumerate(up.columns):
            ax.bar(yrs, up[h].to_numpy(), bottom=bottoms,
                   label=f"{h} (ETR {etr_iso.get(h, float('nan')):.0f}%)",
                   color=cmap(i / max(len(up.columns), 1) * 0.75), edgecolor="white", width=0.72)
            bottoms += up[h].to_numpy()
        ax.bar(yrs, other_up.to_numpy(), bottom=bottoms, label="Other EU havens",
               color="#fdd0a2", edgecolor="white", width=0.72)
        ax.bar(yrs, lost_tot.to_numpy(), label="Tax revenue LOST (the many EU countries)",
               color="#3182bd", edgecolor="white", width=0.72)
        ax.axhline(0, color="black", linewidth=0.9)
        for j, y in enumerate(yrs):
            if cumulative:
                ax.annotate(f"+{gained_tot.iloc[j]:,.0f}", (y, gained_tot.iloc[j]),
                            textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8,
                            fontweight="bold", color="#b30000")
                ax.annotate(f"{lost_tot.iloc[j]:,.0f}", (y, lost_tot.iloc[j]),
                            textcoords="offset points", xytext=(0, -12), ha="center", fontsize=8, color="#08519c")
            else:
                ax.annotate(f"+{gained_tot.iloc[j]:,.0f}\n({int(nh.iloc[j])} havens)", (y, gained_tot.iloc[j]),
                            textcoords="offset points", xytext=(0, 4), ha="center", fontsize=8,
                            fontweight="bold", color="#b30000")
                ax.annotate(f"{lost_tot.iloc[j]:,.0f}\n({int(nl.iloc[j])} countries)", (y, lost_tot.iloc[j]),
                            textcoords="offset points", xytext=(0, -18), ha="center", fontsize=8, color="#08519c")
        ax.set_title("EU tax revenue: gained in a few low-tax havens (up) vs lost by the many (down)"
                     f"{title_suffix}{extra}\nLost = shifted-out base × losing-country CIT; "
                     f"gained = shifted-in base × ETR paid in the haven, {min(yrs)}–{max(yrs)}", fontsize=11)
        ax.set_xlabel("Year")
        ax.set_ylabel("Tax revenue, USD bn")
        ax.set_xticks(yrs)
        ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
        ax.legend(title="Tax revenue gained in (ETR = period mean)", ncol=2, fontsize=9, loc="upper left")
        fig.text(0.01, -0.02,
                 f"Note: Tax revenue LOST = profit a unitary (employees+payroll, 50/50) split assigns to a country but "
                 f"that is booked elsewhere, × that country's statutory CIT. Tax revenue GAINED = profit a haven "
                 f"over-books × the ETR {HOME_LABEL} MNEs actually pay there. Because havens tax the shifted-in profit "
                 f"at a very low ETR, the tax gained is far smaller than the tax lost. Baseline disaggregated CbCR; "
                 f"{HOME_LABEL} parents only.",
                 ha="left", va="top", fontsize=9, wrap=True)
        plt.tight_layout()
        out = OUTPUT_FIGURES / f"eu_tax_revenue_gap{file_suffix}{suffix}_{min(yrs)}_{max(yrs)}.png"
        plt.savefig(_longpath(out), dpi=300, bbox_inches="tight")
        plt.close()
        return out, gained_tot, lost_tot

    g_all, gained_tot, lost_tot = _gap(tg, "", "")
    g_excl, _, _ = _gap(tg.loc[~tg["iso_partner"].isin({"LUX", "MLT"})],
                        "_excl_LUX_MLT", " (excl. Luxembourg & Malta)")
    # Cumulative (running total since the first year) — by the last year the bar
    # shows the whole-period total lost and gained.
    gc_all, cg, cl = _gap(tg, "_cumulative", " — cumulative since first year", cumulative=True)
    _gap(tg.loc[~tg["iso_partner"].isin({"LUX", "MLT"})],
         "_cumulative_excl_LUX_MLT", " — cumulative (excl. Luxembourg & Malta)", cumulative=True)
    print(f"\n[tax-revenue gap{title_suffix}] saved:\n  {g_all}\n  {g_excl}\n  {gc_all}\n"
          f"  Tax gained in havens: {gained_tot.iloc[0]:,.0f} -> {gained_tot.iloc[-1]:,.0f} bn/yr | "
          f"Tax lost by the many: {-lost_tot.iloc[0]:,.0f} -> {-lost_tot.iloc[-1]:,.0f} bn/yr\n"
          f"  CUMULATIVE by {tg['year'].max():.0f}: gained {cg.iloc[-1]:,.0f} bn | lost {-cl.iloc[-1]:,.0f} bn")


build_tax_revenue_gap("employees_payroll", "", "")
build_tax_revenue_gap("ccctb", "_ccctb", " — CCCTB formula")


# %% [10] Home-group share of real activity vs profit, over time.
# Shows where these MNEs' real activity actually sits: the home region's share of
# the group's worldwide employees, tangible assets, payroll and sales — versus
# its share of reported profit. Real-activity shares being high and flat while
# the profit share is lower/volatile is exactly the misalignment UT corrects.
HS_FORMULA = "employees_payroll"
_hs_src = run_summary.loc[run_summary["formula_name"] == HS_FORMULA]
if _hs_src.empty:
    print(f"\n[home-share figure] No '{HS_FORMULA}' run; skipping.")
else:
    hs = pd.read_csv(_longpath(_hs_src.iloc[0]["misalignment_file"]))
    hs["year"] = pd.to_numeric(hs["year"], errors="coerce")
    factor_cols = {
        "n_employees": "Employees",
        "tangible_assets_except_cash": "Tangible assets",
        "payroll": "Payroll",
        "unrelated_party_revenues": "Sales",
        PROFIT_VAR: "Reported profit",
    }
    for c in factor_cols:
        hs[c] = pd.to_numeric(hs[c], errors="coerce")
    rows = []
    for y, g in hs.groupby("year"):
        rec = {"year": int(y)}
        home = g["iso_partner"].isin(PARENT_SET)
        for c, name in factor_cols.items():
            if c == PROFIT_VAR:
                tot, num = g[c].sum(), g.loc[home, c].sum()
            else:
                tot, num = g[c].clip(lower=0).sum(), g.loc[home, c].clip(lower=0).sum()
            rec[name] = 100 * num / tot if tot else np.nan
        rows.append(rec)
    share = pd.DataFrame(rows).sort_values("year")
    share.to_csv(OUTPUT_TABLES / "home_share_activity_vs_profit.csv", index=False)
    hs_years = share["year"].tolist()

    styles = {
        "Employees":       ("#1b7837", "-", 2.6),
        "Tangible assets": ("#762a83", "-", 2.6),
        "Payroll":         ("#5aae61", "--", 1.8),
        "Sales":           ("#9970ab", "--", 1.8),
        "Reported profit": ("#b2182b", "-", 2.8),
    }
    fig, ax = plt.subplots(figsize=(12, 7))
    for name, (color, ls, lw) in styles.items():
        ax.plot(share["year"], share[name], marker="o", markersize=5, linewidth=lw,
                linestyle=ls, color=color, label=name)
        last = share[name].iloc[-1]
        ax.annotate(f"{last:.0f}%", (hs_years[-1], last), textcoords="offset points",
                    xytext=(6, 0), fontsize=8, color=color, va="center")
    ax.set_ylim(0, 100)
    ax.set_xlabel("Year")
    ax.set_ylabel(f"{HOME_LABEL} share of {HOME_LABEL}-MNE worldwide total, %")
    ax.set_xticks(hs_years)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
    ax.set_title(f"Real activity stays in the {HOME_LABEL} home base, but profit does not track it\n"
                 f"{HOME_LABEL} share of {HOME_LABEL}-MNE worldwide totals, "
                 f"{min(hs_years)}–{max(hs_years)}", fontsize=13)
    ax.legend(loc="center right", fontsize=9)
    fig.text(0.01, -0.02,
             f"Note: Each line is the {HOME_LABEL} home region's share of {HOME_LABEL}-MNE worldwide employees, "
             "tangible assets, payroll, sales and reported profit. Real-activity factors are high and flat while the "
             "profit share is lower / more volatile — the gap unitary taxation would close. Profit cells may be "
             "negative (kept); other factors clipped at 0. Baseline disaggregated CbCR.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    _hs_path = OUTPUT_FIGURES / f"home_share_activity_vs_profit_{min(hs_years)}_{max(hs_years)}.png"
    plt.savefig(_longpath(_hs_path), dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\n[home-share figure] saved: {_hs_path}\n  "
          + " | ".join(f"{name}: {share[name].iloc[0]:.0f}%->{share[name].iloc[-1]:.0f}%"
                       for name in factor_cols.values()))


# %% [10b] Tax revenue each EU country loses to <HOME> MNEs (+ Germany split).
# Per-EU-country tax revenue lost = profit shifted out of the country (negative
# misalignment) × that country's statutory CIT (the tax_revenue_loss column of
# the loss_cit_gain_etr country file). For Germany the loss is split across the
# three layers of government using the statutory composition of the ~30%
# combined corporate rate (see GERMANY_LEVEL_SHARES below).
TL_FORMULA = "employees_payroll"
_tl_src = run_summary.loc[
    (run_summary["formula_name"] == TL_FORMULA)
    & (run_summary["rate_mode"] == "loss_cit_gain_etr")
]
if _tl_src.empty:
    print("\n[EU country tax loss] No employees_payroll/loss_cit_gain_etr run; skipping.")
else:
    tl = pd.read_csv(_longpath(_tl_src.iloc[0]["country_file"]))
    tl["year"] = pd.to_numeric(tl["year"], errors="coerce")
    tl = tl.loc[tl["iso_partner"].isin(EU27)].copy()
    tl["tax_loss_bn"] = pd.to_numeric(tl["tax_revenue_loss"], errors="coerce").fillna(0.0) / 1000.0
    tl_years = sorted(int(y) for y in tl["year"].dropna().unique())

    by_country = (tl.groupby(["iso_partner", "partner_jurisdiction"], as_index=False)["tax_loss_bn"]
                  .sum().sort_values("tax_loss_bn", ascending=False))
    by_country.to_csv(OUTPUT_TABLES / "eu_country_tax_loss.csv", index=False)
    (tl.pivot_table(index=["iso_partner", "partner_jurisdiction"], columns="year",
                    values="tax_loss_bn", aggfunc="sum")
     .to_csv(OUTPUT_TABLES / "eu_country_tax_loss_by_year.csv"))

    # ---- Figure: tax lost per EU country (cumulative) ----
    bc = by_country[by_country["tax_loss_bn"] > 0].copy().iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, max(5.0, 0.42 * len(bc))))
    ax.barh(bc["iso_partner"], bc["tax_loss_bn"], color="#3182bd", edgecolor="white")
    for yi, v in enumerate(bc["tax_loss_bn"]):
        ax.annotate(f"${v:,.1f}bn", (v, yi), textcoords="offset points", xytext=(4, 0),
                    va="center", fontsize=8)
    ax.set_xlabel(f"Tax revenue lost, USD bn (cumulative {min(tl_years)}–{max(tl_years)})")
    ax.set_title(f"Tax revenue each EU country loses to {HOME_LABEL} multinationals' profit shifting\n"
                 f"Cumulative {min(tl_years)}–{max(tl_years)}", fontsize=12)
    ax.grid(True, axis="x", linewidth=0.3, alpha=0.5)
    ax.margins(x=0.12)
    fig.text(0.01, -0.02,
             f"Note: Tax revenue lost = profit a unitary (employees+payroll, 50/50) split would assign to the country "
             f"but that {HOME_LABEL} MNEs book elsewhere, × the country's statutory CIT rate. Baseline disaggregated "
             f"CbCR; {HOME_LABEL} parents only.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    _tl_path = OUTPUT_FIGURES / f"eu_country_tax_loss_{min(tl_years)}_{max(tl_years)}.png"
    plt.savefig(_longpath(_tl_path), dpi=300, bbox_inches="tight")
    plt.close()

    # ---- Germany: split across the three layers of government ----
    # Refined split: decompose Germany's ACTUAL combined corporate rate (from the
    # data) into its statutory components and assign each to the level(s) that
    # receive it. Because the modelled tax loss = base × combined rate, splitting
    # by the rate's composition (not by aggregate revenue shares) is the
    # internally consistent method.
    #   • Körperschaftsteuer (KSt) 15% → 50% Bund / 50% Länder (Art.106(3) GG)
    #   • Solidaritätszuschlag (SolZ) = 5.5% × KSt = 0.825pp → Bund
    #   • Gewerbesteuer = combined rate − 15.825pp → Kommunen, NET of the
    #     Gewerbesteuerumlage. At an average Hebesatz ~407% and Umlagesatz ~35%,
    #     the umlage is ~Umlagesatz/Hebesatz ≈ 8.6% of trade tax, redistributed
    #     to Bund/Länder ≈ 41%/59%.
    # Confidence: medium — the Gewerbesteuerumlage and average Hebesatz are
    # nationwide approximations; adjust the constants below for precision.
    _KST, _SOLZ = 0.15, 0.055 * 0.15
    _UMLAGE_FRAC, _UMLAGE_BUND = 0.086, 0.41
    _de_cit = pd.to_numeric(tl.loc[tl["iso_partner"] == "DEU", "cit"], errors="coerce").dropna()
    _r = float(_de_cit.median()) if not _de_cit.empty else 0.2982
    _gewerbe = max(_r - _KST - _SOLZ, 0.0)
    _bund = 0.5 * _KST + _SOLZ + _gewerbe * _UMLAGE_FRAC * _UMLAGE_BUND
    _laender = 0.5 * _KST + _gewerbe * _UMLAGE_FRAC * (1.0 - _UMLAGE_BUND)
    _kommunen = _gewerbe * (1.0 - _UMLAGE_FRAC)
    _lvl_tot = _bund + _laender + _kommunen
    GERMANY_LEVEL_SHARES = {
        "Federal (Bund)": _bund / _lvl_tot,
        "State (Länder)": _laender / _lvl_tot,
        "Municipal (Kommunen)": _kommunen / _lvl_tot,
    }
    de_by_year = tl.loc[tl["iso_partner"] == "DEU"].groupby("year")["tax_loss_bn"].sum()
    de_years = sorted(int(y) for y in de_by_year.index)
    de_total = float(de_by_year.sum())

    de_rows = []
    for lvl, sh in GERMANY_LEVEL_SHARES.items():
        row = {"level": lvl, "share": sh, "tax_loss_bn_total": de_total * sh}
        for y in de_years:
            row[str(int(y))] = float(de_by_year.get(y, 0.0)) * sh
        de_rows.append(row)
    de_split = pd.DataFrame(de_rows)
    de_split.to_csv(OUTPUT_TABLES / "germany_tax_loss_by_level.csv", index=False)

    fig, ax = plt.subplots(figsize=(10, 6))
    bottoms = np.zeros(len(de_years))
    lvl_colors = {"Federal (Bund)": "#08519c", "State (Länder)": "#6baed6",
                  "Municipal (Kommunen)": "#fdae6b"}
    for lvl, sh in GERMANY_LEVEL_SHARES.items():
        vals = np.array([float(de_by_year.get(y, 0.0)) * sh for y in de_years])
        ax.bar(de_years, vals, bottom=bottoms, label=f"{lvl} — {sh*100:.0f}%",
               color=lvl_colors[lvl], edgecolor="white", width=0.75)
        bottoms += vals
    for j, y in enumerate(de_years):
        tot = float(de_by_year.get(y, 0.0))
        ax.annotate(f"${tot:,.1f}bn", (y, tot), textcoords="offset points", xytext=(0, 3),
                    ha="center", fontsize=8, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Tax revenue lost, USD bn")
    ax.set_xticks(de_years)
    ax.grid(True, axis="y", linewidth=0.3, alpha=0.5)
    ax.set_title(f"Germany's tax revenue lost to {HOME_LABEL} multinationals, by level of government\n"
                 f"Total {min(de_years)}–{max(de_years)}: ${de_total:,.0f}bn", fontsize=12)
    ax.legend(title="Government level (share of corporate tax)", fontsize=9)
    _shares_txt = " / ".join(f"{lvl.split(' ')[0]} {sh*100:.0f}%"
                             for lvl, sh in GERMANY_LEVEL_SHARES.items())
    fig.text(0.01, -0.02,
             f"Note: Germany's loss split by the statutory make-up of its combined corporate rate "
             f"({_r*100:.1f}%) — Körperschaftsteuer 15% (50/50 Bund/Länder) + Solidaritätszuschlag (federal) + "
             f"Gewerbesteuer (municipal, net of the Gewerbesteuerumlage ≈8.6% redistributed to Bund/Länder) → "
             f"{_shares_txt}. Per-year bars; title shows the cumulative total. Baseline disaggregated CbCR; "
             f"{HOME_LABEL} parents only.",
             ha="left", va="top", fontsize=9, wrap=True)
    plt.tight_layout()
    _de_path = OUTPUT_FIGURES / f"germany_tax_loss_by_level_{min(de_years)}_{max(de_years)}.png"
    plt.savefig(_longpath(_de_path), dpi=300, bbox_inches="tight")
    plt.close()

    _de_top = ", ".join(f"{lvl.split(' ')[0]} ${de_total*sh:,.1f}bn"
                        for lvl, sh in GERMANY_LEVEL_SHARES.items())
    print(f"\n[EU country tax loss] saved: {_tl_path}\n"
          f"  Top losers (USD bn): "
          + ", ".join(f"{r.iso_partner}={r.tax_loss_bn:,.1f}"
                      for r in by_country.head(6).itertuples(index=False))
          + f"\n[Germany split] saved: {_de_path} | total ${de_total:,.1f}bn -> {_de_top}\n"
          f"  Data: eu_country_tax_loss.csv, germany_tax_loss_by_level.csv")


# %% [11] Mirror outputs to the TJN shared project folder.
# Copies this run's output/<topic>/ tree (figures + small summary tables) to the
# "2605 The quiet tax war" shared folder so colleagues see it without the repo.
# The heavy per-spec disaggregated/ dir is skipped (regenerable, ~120MB). Set
# MIRROR_TO_SHARED=0 to disable, or SHARED_OUTPUT_ROOT to redirect.
import shutil

SHARED_OUTPUT_ROOT = Path(os.environ.get(
    "SHARED_OUTPUT_ROOT",
    r"C:\Users\aliso\Tax Justice Network Ltd\TJN - Shared Documents"
    r"\Research team\Projects one-off\2605 The quiet tax war\3_output",
))
MIRROR_TO_SHARED = os.environ.get("MIRROR_TO_SHARED", "1") not in ("0", "false", "False", "")


def _mirror_outputs_to_shared():
    if not MIRROR_TO_SHARED:
        print("\n[mirror] MIRROR_TO_SHARED=0 — skipping shared-folder copy.")
        return
    if not SHARED_OUTPUT_ROOT.exists():
        print(f"\n[mirror] shared root not found, skipping: {SHARED_OUTPUT_ROOT}")
        return
    base = OUTPUT_TABLES.parent            # output/<topic>/  (has figures/ and tables/)
    # Mirror straight into 3_output/figures and 3_output/tables (no topic
    # subfolder). Prefix each file with the home group so US and EU runs don't
    # collide in the shared flat folder.
    prefix = f"{HOME_GROUP.lower()}_" + ("" if ETR_TAG == "inf" else f"{ETR_TAG}_")
    # -> 'usa_' / 'eu27_' for inf; 'usa_etr15_' / 'eu27_etr15_' for the 0.15 run
    n = 0
    for p in base.rglob("*"):
        rel = p.relative_to(base)
        if "disaggregated" in rel.parts:   # skip the heavy per-spec CSVs
            continue
        if p.is_file():
            fname = rel.name if rel.name.startswith(prefix) else prefix + rel.name
            parts = list(rel.parts)
            # shared folder names the subdirs 1_tables / 2_figures
            parts[0] = {"figures": "2_figures", "tables": "1_tables"}.get(parts[0], parts[0])
            parts[-1] = fname
            target = SHARED_OUTPUT_ROOT.joinpath(*parts)
            os.makedirs(_longpath(str(target.parent)), exist_ok=True)
            shutil.copy2(_longpath(str(p)), _longpath(str(target)))
            n += 1
    print(f"\n[mirror] copied {n} files to {SHARED_OUTPUT_ROOT} (prefix '{prefix}')")


try:
    _mirror_outputs_to_shared()
except Exception as _mirror_err:
    print(f"\n[mirror] failed (non-fatal): {_mirror_err}")
# %%
