# %%
"""
Scenario × formula comparison machinery for the unitary-taxation estimates —
the shared summary machinery behind the three-scenario deliverables (scripts
the 7-series exhibit scripts import build_summary and the aggregation helpers from here).

Scenarios (each draws from its own UT sample):

  1. RESOURCES IGNORED        — disaggregated baseline (reported figures as-is)
  2. RESOURCES EXCLUDED       — excl_resource
  3. RESOURCES EXCL + FLOOR   — excl_resource_floored (IGF-ATAF Cat 1 floor
                                add-on counted as a separate government-revenue stream
                                on top of UT-derived revenue)

For each scenario we sweep the 4-factor formula families (and rate modes for
diagnostics): employees_payroll, ccctb, three_factors,
double_weighted_sales — plus the destination-sales variants where loaded.

Per (country, scenario, formula) row, the output table carries:

  Identifiers
    scenario, scenario_label, formula_name, formula_label,
    iso_partner, partner_jurisdiction, wb_income_group

  Baselines / context
    previous_profits_musd            Σ reported_profit (the sample's baseline)
    current_tax_paid_cash_musd       corporate tax the sample MNEs currently pay

  Change in taxable profits (rate-mode invariant)
    delta_taxable_profits_musd       (Σ theoretical − Σ reported)
    delta_taxable_profits_pct        % of previous_profits_musd

  Change in tax revenue from UT — two rate-mode choices
    delta_tax_revenue_recCIT_forgETR_musd            losses × CIT, gains × ETR_average
    delta_tax_revenue_recCIT_forgETR_pct_revenue     % of current_tax_paid_cash_musd
    delta_tax_revenue_recETR_forgETR_musd            both at ETR_average (conservative)
    delta_tax_revenue_recETR_forgETR_pct_revenue

  Resource capture (per country, scenario-aware)
    resource_capture_actual_musd     pre + post + equity (existing state take)
    resource_capture_floor_musd      actual + floor add-on (under IGF-ATAF; non-floored scenarios = actual)
    resource_capture_addon_musd      floor_add_on_cat1 (nonzero only in scenario 3)
    resource_capture_addon_pct       addon as % of actual

  Change in total government revenue under each scenario
    (= Change in tax revenue + scenario-specific resource adjustment;
     scenario 3: + floor add-on;  others: same as Change in tax revenue)
    delta_total_gvt_revenue_recCIT_forgETR_musd
    delta_total_gvt_revenue_recCIT_forgETR_pct_revenue
    delta_total_gvt_revenue_recETR_forgETR_musd
    delta_total_gvt_revenue_recETR_forgETR_pct_revenue

The % denominator (`current_tax_paid_cash_musd`) is the corporate income tax
the sample multinationals currently pay (CbCR cash basis).

Outputs (in output/analysis/scenario_comparison/detail/<subfolder>/):
  tables/
    scenario_summary_long_<window>.csv      — one row per (country, scenario, formula)
    scenario_by_income_group_<window>.csv   — same columns, aggregated to (scenario, formula, income group)
  figures/
    fig_<scenario>_gvt_revenue_by_income_<window>.png    — one per scenario, 2 rate modes side-by-side
    fig_<scenario>_delta_profits_by_income_<window>.png  — one per scenario
    fig_<scenario>_pct_taxrev_by_income_<window>.png     — one per scenario, Change in gvt revenue as % tax revenue

DATA QUALITY: LSO, FSM, GUF, BTN excluded from income-group aggregates and figures
(CbCR profit many orders of magnitude larger than the real economy — reporting anomaly).

Shared module — import `build_summary` etc.; the runnable report is 7c_resource_rights.py
"""

import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from config import output_dirs, data_final, deflator_to_base, BASE_YEAR
from _brand import (apply_tjn_style, PALETTE, HATCH_CYCLE, EARTH_GREEN, BLUE, GOLD, RED)

apply_tjn_style()

# %% MARK: 1. Run settings (deflation switch, windows, scenarios)
# When True, build_summary + the resource-capture loaders deflate each year's
# monetary values to constant BASE_YEAR US dollars before summing over years. Off
# by default (7d and the comparison scripts keep nominal); the paper-figure
# driver (7b) turns it on.
_DEFLATE_TO_BASE = False

# When set to a {year: factor} dict, every per-year monetary value is ALSO
# multiplied by that year's factor before aggregation. Used by 7c to build the
# grey "scaled to global multinational profit" ghost series behind the
# income-group bars (factors = 7b's scaleup_yearly.csv coverage scale-up).
_YEAR_SCALE_FACTORS = None


def _deflate_col(df, col):
    """Multiply a per-year monetary column by the year→BASE_YEAR deflator, in place-safe."""
    out = df[col]
    if _DEFLATE_TO_BASE and "year" in df.columns:
        f = df["year"].map(deflator_to_base())
        out = pd.to_numeric(out, errors="coerce") * f
    if _YEAR_SCALE_FACTORS is not None and "year" in df.columns:
        out = pd.to_numeric(out, errors="coerce") * df["year"].map(_YEAR_SCALE_FACTORS)
    return out

# consumed by 7c_resource_rights.py (Part B, the detail report) — kept here
# so the topic lives next to the machinery it describes
REPORT_TOPIC = "scenario_detail"

# Each scenario draws from one UT sample directory and one formula family.
# All UT analyses use reported-only data (is_distributed == 0).

# ── Reported-only scenarios: the underlying UT runs are filtered to
# is_distributed == 0 (directly-reported country rows only — no
# disaggregation imputation). Bad reporters whose non-domestic data is
# entirely in aggregates lose most of their contribution; per-country
# values become smaller and more conservative. Topics suffixed `_reported`.
SCENARIOS_REPORTED = [
    {
        "key": "ignorant_reported",
        "label": "Resources ignored",
        "topic": "unitary_taxation_disaggregated_reported",
        "sample": "disaggregated",
        "formulas": [
            ("sales_employees_destmnedds", "Sales (destination) + employees — headline"),
            ("sales_employees", "Sales (origin) + employees"),
            ("ccctb", "CCCTB"),
            ("three_factors", "Three-factor"),
            ("double_weighted_sales", "Double-weighted sales"),
        ],
    },
    {
        "key": "excl_reported",
        "label": "Profits corrected for resource rent capture",
        "topic": "unitary_taxation_excl_resource_reported",
        "sample": "excl_resource",
        "formulas": [
            ("sales_employees_destmnedds", "Sales (destination) + employees — headline"),
            ("sales_employees", "Sales (origin) + employees"),
            ("ccctb", "CCCTB"),
            ("three_factors", "Three-factor"),
            ("double_weighted_sales", "Double-weighted sales"),
        ],
    },
    {
        "key": "excl_floored_reported",
        "label": "Profits corrected for resource rent capture + min. royalty floor",
        "topic": "unitary_taxation_excl_resource_floored_reported",
        "sample": "excl_resource_floored",
        "formulas": [
            ("sales_employees_destmnedds", "Sales (destination) + employees — headline"),
            ("sales_employees", "Sales (origin) + employees"),
            ("ccctb", "CCCTB"),
            ("three_factors", "Three-factor"),
            ("double_weighted_sales", "Double-weighted sales"),
        ],
    },
]

# Reported-only is the sole UT path. SCENARIOS is the name consumers import.
SCENARIOS = SCENARIOS_REPORTED

# (subfolder, scenarios) — drives the main loop. Each group writes to
# output/analysis/scenario_comparison/detail/<subfolder>/{tables,figures}/.
SCENARIO_GROUPS = [
    ("reported_only", SCENARIOS_REPORTED),
]

# A stable colour per formula slot so the same colour means "the same
# formula" / "the CCCTB-equivalent formula" / etc. across all four scenarios.
# TJN brand palette (see _brand.py).
FORMULA_COLOURS = [EARTH_GREEN, BLUE, GOLD, RED, PALETTE[4]]  # 5 formulas incl. the destination headline
# Extra colours for cross-scenario figures (one colour per scenario).
SCENARIO_COLOURS = list(PALETTE)

# Diagnostic rate modes shown side-by-side. The first is the default.
RATE_MODES = [
    (
        "loss_cit_gain_etr",
        "Recovered base × home CIT, forgone base × haven ETR (default)",
    ),
    ("loss_etr_gain_etr", "Recovered & forgone bases × ETR (conservative)"),
    # Only the rate modes produced by 5_estimate's MINIMAL grid (no CIT-CIT).
]

# Single ETR family for headline numbers (loss/gain rate logic happens in the
# rate_mode column; the ETR family controls which etr_* column is the "gain" rate).
# Headline = "domfor" — the cell-matched domestic/foreign ETR (domestic rate
# on the domestic cell, foreign rate on foreign-MNE cells); "average" remains
# available in the long tables as the comparison family.
DEFAULT_ETR = "domfor"

# Paper window: per-year averages over 2016-2022 excluding 2020 (the COVID
# year distorts profitability); the full range incl. 2020 is the supplementary
# comparison window.
YEARS_PAPER = [2016, 2017, 2018, 2019, 2021, 2022]
YEARS_SUPPLEMENTARY = list(range(2016, 2023))

# Data-quality exclusions (LSO/FSM/GUF/BTN) — single source of truth in
# config.py. Scripts 7a / 7h / 7j import this name from here, so they follow
# automatically.
from config import DATA_QUALITY_EXCLUSIONS  # noqa: E402

INCOME_GROUP_ORDER = [
    "low_income",
    "lower_middle_income",
    "upper_middle_income",
    "high_income",
    "tax_haven",
]
INCOME_GROUP_LABELS = {
    "low_income": "Low",
    "lower_middle_income": "Lower-mid",
    "upper_middle_income": "Upper-mid",
    "high_income": "High",
    "tax_haven": "Inv. hub",
}


# ── Grouping context for the figure machinery ────────────────────────────────
# The bar figures group the x-axis by income group by default. For the paper's
# Appendix B (results by world region) the SAME figures are drawn grouped by
# region: a caller sets region mode with set_grouping(...), and the low-level
# pivots/labels below (_pivot, _grouped_bars, _scenario_machinery_panel) read the
# grouping column / order / labels through these accessors. Income mode always
# reads the LIVE INCOME_GROUP_LABELS/ORDER, so a script's paper-label override
# still applies.
_REGION_MODE = False
_REGION_COL = "region_tjn"
_REGION_ORDER = None
_REGION_LABELS = None


def _gcol():
    return _REGION_COL if _REGION_MODE else "wb_income_group"


def _gorder():
    return _REGION_ORDER if _REGION_MODE else INCOME_GROUP_ORDER


def _glabels():
    return _REGION_LABELS if _REGION_MODE else INCOME_GROUP_LABELS


def set_grouping(region=False, col="region_tjn", order=None, labels=None):
    """Switch the figure machinery between income-group (default) and region
    grouping. `set_grouping(region=True, order=REGION_ORDER, labels=REGION_LABELS)`
    for Appendix B; `set_grouping()` resets to income group."""
    global _REGION_MODE, _REGION_COL, _REGION_ORDER, _REGION_LABELS
    _REGION_MODE = bool(region)
    _REGION_COL, _REGION_ORDER, _REGION_LABELS = col, order, labels


# ─── Loading ─────────────────────────────────────────────────────────────────
# %% MARK: 2. Scenario loaders (method: which UT outputs feed each scenario)
def load_scenario(scenario, years_filter):
    """Load summary_country_year_long for `scenario`, keep all four formulas and
    both diagnostic rate modes (default ETR family).  Returns long DataFrame:
        scenario, formula_name, formula_label, rate_mode,
        iso_partner, partner_jurisdiction, wb_income_group, year,
        theoretical_profit, reported_profit, revenue_gain_from_ut,
    """
    tables_dir, _ = output_dirs(scenario["topic"])
    p = tables_dir / "summary_country_year_long.csv"
    if not p.exists():
        print(f"  [skip] {scenario['key']} — no long table at {p}")
        return pd.DataFrame()
    df = pd.read_csv(p, low_memory=False)
    if "sample_name" in df.columns:
        df = df[df["sample_name"] == scenario["sample"]]
    wanted_formulas = [f for f, _ in scenario["formulas"]]
    wanted_rates = [r for r, _ in RATE_MODES]
    df = df[
        df["formula_name"].isin(wanted_formulas)
        & (df["etr_name"] == DEFAULT_ETR)
        & df["rate_mode"].isin(wanted_rates)
        & df["year"].isin(years_filter)
    ].copy()
    label_map = dict(scenario["formulas"])
    df["scenario"] = scenario["key"]
    df["scenario_label"] = scenario["label"]
    df["formula_label"] = df["formula_name"].map(label_map)
    keep = [
        "scenario",
        "scenario_label",
        "formula_name",
        "formula_label",
        "rate_mode",
        "iso_partner",
        "partner_jurisdiction",
        "wb_income_group",
        "region_tjn",
        "year",
        "theoretical_profit",
        "reported_profit",
        "tax_revenue_loss",
        "tax_revenue_gain",
        "revenue_gain_from_ut",
    ]
    # Corporate income tax the CbCR MNEs currently pay (Σ income_tax_paid_on_cash_basis,
    # MUSD) — the "corporate tax revenue in our data", used as the % denominator.
    if "current_tax_paid_cash_musd" not in df.columns:
        df["current_tax_paid_cash_musd"] = np.nan
    keep.append("current_tax_paid_cash_musd")
    return df[keep]


def load_floor_add_on_by_partner(years_filter, variant=""):
    """The IGF-ATAF Cat 1 floor add-on (extra royalty revenue compelled by
    enforcing the floor) — a separate government-revenue stream added on top of UT
    revenue under scenario 3.

    `variant` appends a sample suffix (e.g. "_gravity") to the cbcr_main_* file
    so the resource columns are read from the matching disaggregation variant."""
    p = Path(data_final) / f"cbcr_main_excl_resource_floored{variant}.csv"
    if not p.exists():
        return pd.Series(dtype=float, name="floor_add_on_usd")
    df = pd.read_csv(p, usecols=["iso_partner", "year", "floor_add_on_cat1_usd"])
    df = df[df["year"].isin(years_filter)]
    df["floor_add_on_cat1_usd"] = _deflate_col(df, "floor_add_on_cat1_usd")
    g = (
        (df.groupby("iso_partner")["floor_add_on_cat1_usd"].sum()
         / max(1, df["year"].nunique()))   # per-year average
        .rename("floor_add_on_usd")
    )
    return g


def load_actual_resource_contribution_by_partner(years_filter, variant=""):
    """Actual existing capture (pre-profit royalties + post-profit CIT/special +
    equity) that the country *currently* collects. Carried in the output as
    context (`resource_capture_actual_musd`); no scenario subtracts it — the
    resource regime continues alongside the UT yield in every scenario."""
    p = Path(data_final) / f"cbcr_main_incl_resource{variant}.csv"
    if not p.exists():
        return pd.Series(dtype=float, name="actual_resource_contribution_usd")
    df = pd.read_csv(
        p, usecols=["iso_partner", "year", "actual_resource_contribution_usd"]
    )
    df = df[df["year"].isin(years_filter)]
    df["actual_resource_contribution_usd"] = _deflate_col(df, "actual_resource_contribution_usd")
    g = (
        (df.groupby("iso_partner")["actual_resource_contribution_usd"].sum()
         / max(1, df["year"].nunique()))   # per-year average
        .rename("actual_resource_contribution_usd")
    )
    return g


def load_resource_profit_base_by_partner(years_filter, variant=""):
    """Resource profit base (= the profit pool stripped out of `excl_resource`
    samples to leave only non-resource profit). For the cross-scenario
    comparison we add this back into the excl_* baselines AND outcomes so that
    profit pre/post is reported on the same (resources-included) basis as the
    ignorant baseline — the Change in is unchanged but the levels become comparable."""
    p = Path(data_final) / f"cbcr_main_excl_resource{variant}.csv"
    if not p.exists():
        return pd.Series(dtype=float, name="resource_profit_base_usd")
    df = pd.read_csv(p, usecols=["iso_partner", "year", "resource_profit_base_usd"])
    df = df[df["year"].isin(years_filter)]
    df["resource_profit_base_usd"] = _deflate_col(df, "resource_profit_base_usd")
    g = (
        (df.groupby("iso_partner")["resource_profit_base_usd"].sum()
         / max(1, df["year"].nunique()))   # per-year average
        .rename("resource_profit_base_usd")
    )
    return g


# ─── Summary build ────────────────────────────────────────────────────────────
RATE_SUFFIX = {
    "loss_cit_gain_etr": "recCIT_forgETR",
    "loss_etr_gain_etr": "recETR_forgETR",
}


def _safe_pct(numer, denom):
    return (100 * numer / denom).replace([np.inf, -np.inf], np.nan)


def _safe_pct_positive_base(numer, denom):
    """Like _safe_pct but returns NaN when denom is not strictly positive.

    A pct against a negative base flips sign and reads as a loss when it's
    really a gain (and vice versa). Reserve % numbers for when the denominator
    has a meaningful positive interpretation (e.g. previous_profits > 0).
    """
    numer = pd.to_numeric(numer, errors="coerce")
    denom = pd.to_numeric(denom, errors="coerce")
    out = 100 * numer / denom
    out = out.where(denom > 0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan)


# Stashed by build_summary for build_by_income: the clean "total over total"
# income-group revenue % — Σrevenue / Σ(current corporate cash tax paid) over
# (country, year) cells that HAVE cash-tax data, and the group cash-tax denominator.
GROUP_REV_PCT = None
GROUP_CASHTAX_MUSD = None


# %% MARK: 3. build_summary (the shared backend all exhibit scripts reuse)
def build_summary(years_filter, scenarios=SCENARIOS, variant=""):
    """Build the (scenario × formula × country) summary.

    Rate-mode is pivoted out (each row carries both `recCIT_forgETR` and `recETR_forgETR`
    versions of the tax-revenue columns).  All monetary columns are in $ MUSD;
    `_pct_revenue` columns are unitless percentages.

    `variant` (e.g. "_gravity") selects which disaggregation-variant cbcr_main_*
    files the resource-capture columns are read from.
    """
    parts = [load_scenario(s, years_filter) for s in scenarios]
    long_df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    if long_df.empty:
        return None

    # Optional: express each year in constant BASE_YEAR USD before aggregating over years.
    # NB: the comparison denominators (current tax revenue, health expenditure) are
    # deflated too, so every % panel is real÷real (equivalently, computed per year) —
    # not a real-numerator over a nominal denominator.
    if _DEFLATE_TO_BASE:
        for c in ("theoretical_profit", "reported_profit", "revenue_gain_from_ut",
                  "tax_revenue_loss", "tax_revenue_gain",
                  "current_tax_paid_cash_musd"):
            if c in long_df.columns:
                long_df[c] = _deflate_col(long_df, c)

    long_df["delta_taxable_profits_musd"] = (
        long_df["theoretical_profit"] - long_df["reported_profit"]
    )

    # Clean "total over total" income-group tax-revenue %: sum revenue and current tax
    # revenue over the (country, year) cells that HAVE current tax data, then ratio —
    # excluding cells without reported current taxes from BOTH sums. Stashed for
    # build_by_income (fig 2/3). Computed from the per-year cells so it's a true
    # Σrevenue / Σcurrent, not skewed by unbalanced panels.
    # Denominator = corporate income tax the MNEs currently pay (current_tax_paid_cash),
    # pooled over years with inflation correction — "the corporate tax revenue in our
    # data", the right base for a corporate-tax change. Both numerator and denominator
    # are in deflated MUSD, so the % is Σrevenue / Σ cash tax paid.
    global GROUP_REV_PCT, GROUP_CASHTAX_MUSD
    _gt = long_df.copy()
    _gt["_cur"] = pd.to_numeric(_gt["current_tax_paid_cash_musd"], errors="coerce")
    _gt["_rev"] = pd.to_numeric(_gt["revenue_gain_from_ut"], errors="coerce")
    _gt = _gt[_gt["_cur"] > 0]
    _ga = _gt.groupby(
        ["scenario", "formula_name", "rate_mode", "wb_income_group"], dropna=False
    ).agg(_rev=("_rev", "sum"), _cur=("_cur", "sum")).reset_index()
    _ga["_pct"] = np.where(_ga["_cur"] > 0, _ga["_rev"] / _ga["_cur"] * 100.0, np.nan)
    GROUP_REV_PCT = (
        _ga.pivot_table(index=["scenario", "formula_name", "wb_income_group"],
                        columns="rate_mode", values="_pct", aggfunc="first")
        .rename(columns=RATE_SUFFIX)
        .add_prefix("delta_tax_revenue_")
        .add_suffix("_pct_revenue")
        .reset_index()
    )
    # Group corporate cash-tax denominator (MUSD, rate-mode-invariant), used by
    # build_by_income to turn the group USD sums into "% of current corporate tax
    # paid". Expressed PER-YEAR (divided by the window's year count) so it is in
    # the same units as the per-year-averaged monetary columns further down —
    # dividing a per-year numerator by a pooled multi-year denominator would
    # understate every revenue % by a factor of n_years.
    _n_years_cash = int(long_df["year"].nunique()) or 1
    GROUP_CASHTAX_MUSD = (
        _ga.groupby(["scenario", "formula_name", "wb_income_group"])["_cur"]
        .max().reset_index().rename(columns={"_cur": "grp_cashtax_musd"})
    )
    GROUP_CASHTAX_MUSD["grp_cashtax_musd"] /= _n_years_cash

    # Step 1 — aggregate per (scenario, formula, rate_mode, country) over years.
    # posbase = the YEAR-LEVEL-clipped positive profit base (Σ_y max(profit_y, 0)):
    # the % denominator convention shared with the paper tables (7f) — loss years
    # contribute no base, but no country is dropped from the numerator.
    long_df["_reported_pos"] = pd.to_numeric(
        long_df["reported_profit"], errors="coerce").clip(lower=0)
    agg = long_df.groupby(
        [
            "scenario",
            "scenario_label",
            "formula_name",
            "formula_label",
            "rate_mode",
            "iso_partner",
            "partner_jurisdiction",
            "wb_income_group",
            "region_tjn",
        ],
        as_index=False,
        dropna=False,
    ).agg(
        previous_profits_musd=("reported_profit", "sum"),
        posbase_musd=("_reported_pos", "sum"),
        delta_taxable_profits_musd=("delta_taxable_profits_musd", "sum"),
        delta_tax_revenue_musd=("revenue_gain_from_ut", "sum"),
        current_tax_paid_cash_musd=("current_tax_paid_cash_musd", "sum"),
    )

    # Paper deliverables report the PER-YEAR AVERAGE, not the multi-year sum: divide
    # the summed monetary columns by the number of years in the window (the denominator
    # columns above already use "mean", so they are per-year and consistent).
    _n_years = int(long_df["year"].nunique())
    for _c in ("previous_profits_musd", "posbase_musd",
               "delta_taxable_profits_musd", "delta_tax_revenue_musd",
               "current_tax_paid_cash_musd"):
        agg[_c] = agg[_c] / _n_years

    # Step 2 — pivot rate_mode → column suffix. Change in taxable profits is rate-mode
    # invariant so we keep the value from any row (first).
    invariant_cols = [
        "scenario",
        "scenario_label",
        "formula_name",
        "formula_label",
        "iso_partner",
        "partner_jurisdiction",
        "wb_income_group",
        "region_tjn",
        "previous_profits_musd",
        "posbase_musd",
        "delta_taxable_profits_musd",
        "current_tax_paid_cash_musd",
    ]
    invariant_cols = [c for c in invariant_cols if c in agg.columns]
    invariant = agg.drop_duplicates(["scenario", "formula_name", "iso_partner"])[
        invariant_cols
    ].reset_index(drop=True)
    rate_wide = (
        agg.pivot_table(
            index=["scenario", "formula_name", "iso_partner"],
            columns="rate_mode",
            values="delta_tax_revenue_musd",
            aggfunc="first",
        )
        .rename(columns=RATE_SUFFIX)
        .add_prefix("delta_tax_revenue_")
        .add_suffix("_musd")
        .reset_index()
    )
    summary = invariant.merge(
        rate_wide,
        on=["scenario", "formula_name", "iso_partner"],
        how="left",
    )

    # Step 3 — resource capture columns (per-country, all from cbcr_main_*).
    floor_usd = load_floor_add_on_by_partner(years_filter, variant)  # excl_resource_floored Cat1
    arc_usd = load_actual_resource_contribution_by_partner(years_filter, variant)
    rpb_usd = load_resource_profit_base_by_partner(
        years_filter, variant
    )  # for excl_* comparability
    summary["resource_capture_actual_musd"] = (
        summary["iso_partner"].map(arc_usd).fillna(0.0) / 1e6
    )
    summary["resource_capture_addon_musd"] = (
        summary["iso_partner"].map(floor_usd).fillna(0.0) / 1e6
    )
    summary["resource_profit_base_musd"] = (
        summary["iso_partner"].map(rpb_usd).fillna(0.0) / 1e6
    )
    summary["resource_capture_floor_musd"] = (
        summary["resource_capture_actual_musd"] + summary["resource_capture_addon_musd"]
    )
    summary["resource_capture_addon_pct"] = _safe_pct(
        summary["resource_capture_addon_musd"], summary["resource_capture_actual_musd"]
    )
    # Only the excl_floored scenario carries the floor add-on; for other
    # scenarios the columns describe the underlying capture (actual) — zero out
    # add-on / floor for non-floored scenarios so the meaning is unambiguous.
    # `startswith` so variant-suffixed keys (excl_floored_reported / _gravity) match.
    not_floored = ~summary["scenario"].str.startswith("excl_floored")
    summary.loc[not_floored, "resource_capture_addon_musd"] = 0.0
    summary.loc[not_floored, "resource_capture_floor_musd"] = summary.loc[
        not_floored, "resource_capture_actual_musd"
    ]
    summary.loc[not_floored, "resource_capture_addon_pct"] = 0.0

    # Step 4 — Change in total government revenue under each scenario. Two versions (one per
    # rate mode), each with pct-of-revenue and pct-of-health.
    #   scenario 1 (ignorant):     Change in tax revenue
    #   scenario 2 (excl):         Change in tax revenue   (resource regime continues
    #                              unchanged — cancels in the Change in; UT losses on
    #                              non-resource profit stay visible)
    #   scenario 3 (excl_floored): Change in tax revenue + floor add-on
    # Profit-base comparability is handled in Step 6 by adding the resource
    # profit base back into scenario_baseline_musd / scenario_outcome_musd for
    # excl-class scenarios. The revenue Change in stays unchanged because the resource
    # regime keeps collecting the same amount pre and post.
    for suffix in RATE_SUFFIX.values():
        col_in = f"delta_tax_revenue_{suffix}_musd"
        col_out = f"delta_total_gvt_revenue_{suffix}_musd"
        if col_in not in summary.columns:
            # Rate modes absent from the grid have no columns — skip them.
            continue
        summary[col_out] = summary[col_in].copy()
        floor_mask = summary["scenario"].str.startswith("excl_floored")
        summary.loc[floor_mask, col_out] += summary.loc[
            floor_mask, "resource_capture_addon_musd"
        ]

    # Step 5 — derive all pct-of-something columns from the consolidated _musd
    # columns. Denominators stay in USD (mean), numerators in MUSD ⇒ × 1e6.
    for suffix in RATE_SUFFIX.values():
        if f"delta_tax_revenue_{suffix}_musd" not in summary.columns:
            continue   # rate mode not in this run (see Step 4 note)
        rev = summary[f"delta_tax_revenue_{suffix}_musd"]
        tot = summary[f"delta_total_gvt_revenue_{suffix}_musd"]
        summary[f"delta_tax_revenue_{suffix}_pct_revenue"] = _safe_pct(
            rev, summary["current_tax_paid_cash_musd"]
        )
        summary[f"delta_total_gvt_revenue_{suffix}_pct_revenue"] = _safe_pct(
            tot, summary["current_tax_paid_cash_musd"]
        )
    # Step 6 — explicit per-scenario baseline / outcome columns so the
    # "what's being compared to what" is transparent in the output. The Change in
    # equals `delta_taxable_profits_musd` numerically (the floor add-on
    # cancels between baseline and outcome for excl_floored) — these columns
    # just make the comparison legible.
    #
    #   ignorant      : baseline = reported_full           ; outcome = UT_theoretical
    #   excl          : baseline = reported_excl           ; outcome = UT_theoretical_excl
    #   excl_floored  : baseline = reported_excl           ; outcome = UT_theoretical_excl_floored + floor_add_on
    #   incl          : baseline = reported_incl           ; outcome = UT_theoretical_incl
    # Script 5's reported leg for the floored datasets IS reported_excl (the
    # pre-floor pool, via pool_var/PROFIT_VAR), so previous_profits_musd needs
    # no add-on compensation here — adding it would double-count and understate
    # the floored %-of-base panel.
    summary["scenario_baseline_musd"] = summary["previous_profits_musd"]
    # For excl-class scenarios we keep the excl_resource baseline (resources
    # excluded from both pre and post) so % comparisons are against the
    # non-resource profit pool that UT actually operates on. The resource
    # profit base is loaded and kept as a column for inspection but NOT
    # added to scenario_baseline_musd.
    summary["scenario_outcome_musd"] = (
        summary["scenario_baseline_musd"] + summary["delta_taxable_profits_musd"]
    )
    # Convenience pct: Change in as % of the scenario-appropriate baseline.
    # For non-floored scenarios this equals delta / previous_profits; for the
    # excl_floored scenarios it correctly divides by reported_excl (pre-floor)
    # rather than reported_excl_floored. NaN when baseline ≤ 0.
    summary["delta_taxable_profits_pct"] = _safe_pct_positive_base(
        summary["delta_taxable_profits_musd"], summary["scenario_baseline_musd"]
    )

    # Final column ordering.
    cols = [
        "scenario",
        "scenario_label",
        "formula_name",
        "formula_label",
        "iso_partner",
        "partner_jurisdiction",
        "wb_income_group",
        "region_tjn",
        "previous_profits_musd",
        "posbase_musd",
        "scenario_baseline_musd",
        "scenario_outcome_musd",
        "current_tax_paid_cash_musd",
        "delta_taxable_profits_musd",
        "delta_taxable_profits_pct",
        "delta_tax_revenue_recCIT_forgETR_musd",
        "delta_tax_revenue_recCIT_forgETR_pct_revenue",
        "delta_tax_revenue_recETR_forgETR_musd",
        "delta_tax_revenue_recETR_forgETR_pct_revenue",
        "delta_tax_revenue_recCIT_forgCIT_musd",
        "delta_tax_revenue_recCIT_forgCIT_pct_revenue",
        "resource_capture_actual_musd",
        "resource_capture_floor_musd",
        "resource_capture_addon_musd",
        "resource_capture_addon_pct",
        "resource_profit_base_musd",
        "delta_total_gvt_revenue_recCIT_forgETR_musd",
        "delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
        "delta_total_gvt_revenue_recETR_forgETR_musd",
        "delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
        "delta_total_gvt_revenue_recCIT_forgCIT_musd",
        "delta_total_gvt_revenue_recCIT_forgCIT_pct_revenue",
    ]
    # Rate modes absent from the run (e.g. CIT-CIT) have no columns — select
    # only what exists.
    return summary[[c for c in cols if c in summary.columns]]


# ─── Tables ───────────────────────────────────────────────────────────────────
SUM_MUSD_COLS = [
    "previous_profits_musd",
    "posbase_musd",
    "scenario_baseline_musd",
    "scenario_outcome_musd",
    "delta_taxable_profits_musd",
    "delta_tax_revenue_recCIT_forgETR_musd",
    "delta_tax_revenue_recETR_forgETR_musd",
    "delta_tax_revenue_recCIT_forgCIT_musd",
    "resource_capture_actual_musd",
    "resource_capture_floor_musd",
    "resource_capture_addon_musd",
    "resource_profit_base_musd",
    "delta_total_gvt_revenue_recCIT_forgETR_musd",
    "delta_total_gvt_revenue_recETR_forgETR_musd",
    "delta_total_gvt_revenue_recCIT_forgCIT_musd",
    "current_tax_paid_cash_musd",
]
# Per-country denominators are means / per-country values; for the income-group
# aggregation we sum them (so the pct re-derives correctly as Σnumer / Σdenom).
SUM_DENOM_COLS = ["current_tax_paid_cash_musd"]


def _add_pct_columns(df):
    # Use the scenario-appropriate baseline (scenario_baseline_musd is the
    # pre-floor reported pool for excl_floored, == previous_profits_musd elsewhere).
    denom_col = (
        "scenario_baseline_musd"
        if "scenario_baseline_musd" in df.columns
        else "previous_profits_musd"
    )
    df["delta_taxable_profits_pct"] = _safe_pct_positive_base(
        df["delta_taxable_profits_musd"], df[denom_col]
    )
    df["resource_capture_addon_pct"] = _safe_pct(
        df["resource_capture_addon_musd"], df["resource_capture_actual_musd"]
    )
    for suffix in RATE_SUFFIX.values():
        if f"delta_tax_revenue_{suffix}_musd" not in df.columns:
            continue   # rate mode not in this run
        df[f"delta_tax_revenue_{suffix}_pct_revenue"] = _safe_pct(
            df[f"delta_tax_revenue_{suffix}_musd"], df["current_tax_paid_cash_musd"]
        )
        df[f"delta_total_gvt_revenue_{suffix}_pct_revenue"] = _safe_pct(
            df[f"delta_total_gvt_revenue_{suffix}_musd"],
            df["current_tax_paid_cash_musd"],
        )
    return df


# %% MARK: 4. Report machinery
# Income-group aggregation + the grouped-bar figure machinery every
# exhibit script uses. Callers may override the module-level display
# settings (WINDOW_LABEL, FLOOR_NOTE, INCOME_GROUP_LABELS, DATA_BANNER,
# DATA_NOTE, SCENARIOS, SCEN_SHORT) before calling the figure functions.
WINDOW_LABEL = "2016–2022"
# Grey ghost bars: the scaled-to-global-MNE-profit value drawn BEHIND each
# in-sample bar (7c passes the scaled pivots; see 7b's scaleup_yearly.csv).
GHOST_GREY = "#cfcfcf"
GHOST_LABEL = "Scaled to global multinational profit"



# Human-readable name of the ETR family the summary is built on
# (_scenario_machinery's DEFAULT_ETR) — used in subtitles/notes so captions can never silently
# contradict the ETR family the data was actually built on.
ETR_LABEL = {
    "average": "average ETR",
    "domfor": "domestic/foreign (cell-matched) ETR",
}.get(DEFAULT_ETR, f"{DEFAULT_ETR} ETR")

# Standard footnote on every figure that carries a % panel.
PCT_NOTE = (
    "Percentages are omitted (no bar) where the denominator is not strictly positive. "
    "Change in taxable profit % is relative to the pre-UT reported profit base; Change in tax revenue % "
    "is relative to the corporate cash tax the MNEs in the income group currently pay "
    "(CbCR income tax paid, cash basis) — not total government tax revenue. A percentage against a "
    "non-positive base would flip sign and mislead, so it is left blank by design."
)
POSBASE_NOTE = (
    "Absolute panel (left): all countries. Percentage panel (right): the % change in "
    "taxable profit is computed over the SUBSAMPLE of countries that had a strictly "
    "positive profit base in the current system, summing the change and the current "
    "profit base over the same countries. This is done so a percentage change is "
    "defined for income groups — notably low-income countries — whose aggregate "
    "current-system profit base is otherwise non-positive (which would make a % flip "
    "sign and mislead). The number of countries in each group's positive-base "
    "subsample can be smaller than in the absolute panel."
)
FLOOR_NOTE = (
    "Scenario 3 revenue = UT-derived revenue + IGF-ATAF minimum-royalty floor add-on "
    "(hatched portion). The floor is a hypothetical minimum royalty, counted as a "
    "separate government-revenue stream on top of the UT yield."
)

# Optional heading banner + explanatory footnote, appended to every figure when
# set by a caller (e.g. 7j builds these figures on the gravity-IMPUTED sample and
# sets these so the heading/notes flag it). Empty by default → the reported-only
# deliverable is unchanged.
DATA_BANNER = ""   # short tag appended to the bold heading
DATA_NOTE = ""     # longer explanation appended to the footnote


def _banner_suffix():
    return f"   [{DATA_BANNER}]" if DATA_BANNER else ""



# ---- income-group aggregation ----
def build_by_income(summary, gcol="wb_income_group"):
    """Replicates the income-group aggregation in `write_tables` (Part B)
    so percentages re-derive correctly as Σnumerator / Σdenominator.
    `gcol` selects the grouping dimension — "wb_income_group" (default) or
    "region_tjn" for the geographic-region counterpart."""
    sub = summary[~summary["iso_partner"].isin(DATA_QUALITY_EXCLUSIONS)]
    # Rate modes absent from the run (e.g. CIT-CIT, not in the MINIMAL grid)
    # have no columns — aggregate only what exists.
    _sum_cols = [c for c in SUM_MUSD_COLS + SUM_DENOM_COLS if c in sub.columns]
    by_inc = (
        sub.groupby(
            [
                "scenario",
                "scenario_label",
                "formula_name",
                "formula_label",
                gcol,
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            {c: "sum" for c in _sum_cols}
            | {"iso_partner": "nunique"}
        )
        .rename(columns={"iso_partner": "n_countries"})
    )
    by_inc = _add_pct_columns(by_inc)

    # Revenue % panels (fig 2/3): income-group % against the CORPORATE tax the MNEs
    # currently pay. NUMERATOR = the SAME full group sum shown in the USD panel
    # (all countries), so the two panels always order identically — a numerator
    # summed over only the restricted cash-tax cell set would be internally
    # clean but differ in composition from the USD panel and could FLIP bar
    # orderings between the panels. DENOMINATOR = Σ(cash tax paid) over the
    # (country, year) cells that HAVE cash-tax data (inflation-corrected;
    # stashed in GROUP_CASHTAX_MUSD per scenario, so the "resources
    # ignored" % is still measured against its own, uncorrected tax).
    # delta_total adds the floor addon on the same denominator (0 for
    # non-floored). Taxable-profit % is untouched by this block.
    gc = globals().get("GROUP_CASHTAX_MUSD", None)
    if gcol == "wb_income_group" and gc is not None and not gc.empty:
        _mk = ["scenario", "formula_name", "wb_income_group"]
        by_inc = by_inc.merge(gc, on=_mk, how="left")
        _cash = pd.to_numeric(by_inc.get("grp_cashtax_musd"), errors="coerce")
        for suffix in RATE_SUFFIX.values():
            tax_c = f"delta_tax_revenue_{suffix}_pct_revenue"
            tot_c = f"delta_total_gvt_revenue_{suffix}_pct_revenue"
            tot_m = f"delta_total_gvt_revenue_{suffix}_musd"
            rev_m = f"delta_tax_revenue_{suffix}_musd"
            if {tot_m, rev_m}.issubset(by_inc.columns):
                by_inc[tax_c] = np.where(
                    _cash > 0, pd.to_numeric(by_inc[rev_m], errors="coerce")
                    / _cash * 100.0, np.nan)
                by_inc[tot_c] = np.where(
                    _cash > 0, pd.to_numeric(by_inc[tot_m], errors="coerce")
                    / _cash * 100.0, np.nan)
        by_inc = by_inc.drop(columns=["grp_cashtax_musd"], errors="ignore")

    # ── Positive-base % for the taxable-profit panel ──────────────────────────
    # Numerator = the FULL group change (identical to the USD panel — never a
    # subsample, so the % can never flip sign against the USD bar); denominator
    # = the group's POSITIVE profit base (each country's current-system base
    # clipped at zero before summing — loss countries contribute their change
    # but no base). Restricting numerator AND denominator to the positive-base
    # subsample would sign-flip in samples (e.g. gravity) where negative-base
    # countries carry much of the group's gain — positive USD bar, negative %.
    pos = sub.copy()
    # Denominator = year-level-clipped positive base (posbase_musd, same
    # convention as the paper tables); fall back to clipping the pooled
    # baseline only for legacy summaries that predate the column.
    if "posbase_musd" in pos.columns and pos["posbase_musd"].notna().any():
        pos["_base_pos"] = pd.to_numeric(pos["posbase_musd"], errors="coerce")
    else:
        pos["_base_pos"] = pd.to_numeric(
            pos["scenario_baseline_musd"], errors="coerce").clip(lower=0)
    pos["_is_posbase"] = (pos["_base_pos"] > 0).astype(int)
    posagg = (
        pos.groupby(
            ["scenario", "formula_name", gcol],
            as_index=False, dropna=False,
        )
        .agg(
            _posbase_delta=("delta_taxable_profits_musd", "sum"),
            _posbase_base=("_base_pos", "sum"),
            n_countries_posbase=("_is_posbase", "sum"),
        )
    )
    posagg["delta_taxable_profits_pct_posbase"] = _safe_pct_positive_base(
        posagg["_posbase_delta"], posagg["_posbase_base"]
    )
    by_inc = by_inc.merge(
        posagg[[
            "scenario", "formula_name", gcol,
            "delta_taxable_profits_pct_posbase", "n_countries_posbase",
        ]],
        on=["scenario", "formula_name", gcol], how="left",
    )
    return by_inc


# ---- figure machinery ----
def _pivot(by_inc, scenario, value_col, formula_keys):
    sub = by_inc[by_inc["scenario"] == scenario["key"]]
    pivot = sub.pivot_table(
        index=_gcol(),
        columns="formula_name",
        values=value_col,
        aggfunc="first",
    )
    pivot = pivot.reindex([g for g in _gorder() if g in pivot.index])
    pivot = pivot[[f for f in formula_keys if f in pivot.columns]]
    return pivot


def _label_bars(ax, container, values, is_pct, usd_decimals=1):
    """Data labels on a bar container. USD → `usd_decimals` places ($bn); % → whole
    number. `values` gives the number to print (the stack TOTAL for stacked bars);
    NaN/None are left blank."""
    labels = []
    for v in values:
        try:
            if v is None or np.isnan(float(v)):
                labels.append("")
            elif is_pct:
                labels.append(f"{float(v):,.0f}%")               # whole %, thousands comma
            else:
                labels.append(f"{float(v):,.{usd_decimals}f}")   # $bn, thousands comma
        except (TypeError, ValueError):
            labels.append("")
    ax.bar_label(container, labels=labels, fontsize=7.5, padding=1, rotation=90)


def _pad_ylim(ax, bottom_frac=0.20, top_frac=0.12):
    """Expand the y-limits so rotated data labels on the tallest up/down bars aren't
    clipped at the figure edge (extra room below for negative bars)."""
    ymin, ymax = ax.get_ylim()
    rng = (ymax - ymin) or 1.0
    ax.set_ylim(ymin - bottom_frac * rng, ymax + top_frac * rng)


def _grouped_bars(ax, pivot, formula_labels, colors, ylabel, title, addon_pivot=None,
                  is_pct=False, usd_decimals=1, ghost_pivot=None):
    """Grouped bars: income groups on x, one bar per formula. If addon_pivot is
    given, the top (hatched) layer = addon, base (solid) = pivot − addon.
    Bars are data-labelled (1-dp USD / whole-number %). If ghost_pivot is given
    (same shape as pivot, e.g. the scaled-to-global-MNE-profit values), a grey
    unlabelled bar is drawn BEHIND each bar — showing what the sample misses
    without cluttering the figure."""
    if pivot.empty or pivot.dropna(how="all").empty:
        ax.set_axis_off()
        ax.set_title(f"{title}\n(no data)", fontsize=9)
        return
    n_formulas = len(pivot.columns)
    n_groups = len(pivot.index)
    bar_width = 0.82 / max(n_formulas, 1)
    x = np.arange(n_groups)
    if ghost_pivot is not None:
        gp = ghost_pivot.reindex(index=pivot.index, columns=pivot.columns)
        for i, col in enumerate(pivot.columns):
            offset = (i - (n_formulas - 1) / 2) * bar_width
            ax.bar(x + offset, gp[col].values, width=bar_width,
                   color=GHOST_GREY, edgecolor="none", zorder=1)
    if addon_pivot is not None:
        addon = addon_pivot.reindex(index=pivot.index, columns=pivot.columns).fillna(0)
    else:
        addon = None
    for i, col in enumerate(pivot.columns):
        offset = (i - (n_formulas - 1) / 2) * bar_width
        vals = pivot[col].values
        hh = HATCH_CYCLE[i % len(HATCH_CYCLE)]   # colour-blind redundancy
        if addon is None:
            c = ax.bar(x + offset, vals, width=bar_width, color=colors[i],
                       hatch=hh, edgecolor="white", linewidth=0.3)
            _label_bars(ax, c, vals, is_pct, usd_decimals)
        else:
            addon_vals = addon[col].values
            base_vals = vals - addon_vals
            ax.bar(x + offset, base_vals, width=bar_width, color=colors[i],
                   hatch=hh, edgecolor="white", linewidth=0.3)
            ctop = ax.bar(
                x + offset,
                addon_vals,
                width=bar_width,
                facecolor=colors[i],
                hatch="///",
                edgecolor="black",
                linewidth=0.4,
                bottom=base_vals,
            )
            _label_bars(ax, ctop, vals, is_pct, usd_decimals)   # label the stack total
    ax.set_xticks(x)
    ax.set_xticklabels(
        [_glabels().get(g, g) for g in pivot.index],
        rotation=0,
        ha="center",
        fontsize=9,
    )
    ax.axhline(0, color="grey", linewidth=0.5)
    _pad_ylim(ax)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=13)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=colors[i],
                             hatch=HATCH_CYCLE[i % len(HATCH_CYCLE)],
                             edgecolor="white", linewidth=0.3)
               for i in range(n_formulas)]
    labels = list(formula_labels[:n_formulas])
    if addon is not None and addon.abs().to_numpy().sum() > 0:
        handles.append(
            plt.Rectangle((0, 0), 1, 1, facecolor="white", hatch="///", edgecolor="black")
        )
        labels.append("Min.-royalty floor add-on")
    if ghost_pivot is not None:
        handles.append(plt.Rectangle((0, 0), 1, 1, facecolor=GHOST_GREY))
        _gt = np.nansum(ghost_pivot.reindex(index=pivot.index,
                                            columns=pivot.columns).values)
        _mt = np.nansum(pivot.values)
        _lbl = GHOST_LABEL
        if _mt and np.isfinite(_gt / _mt) and _gt / _mt > 1:
            _lbl += f" (+{100 * (_gt / _mt - 1):.0f}%)"
        labels.append(_lbl)
    ax.legend(handles, labels, fontsize=8, loc="best", framealpha=0.85)


def make_figure(
    by_inc, scenario, figures_dir, fname, suptitle, abs_col, pct_col,
    abs_ylabel, pct_ylabel, addon_col=None, extra_note=None, pct_note=PCT_NOTE,
):
    formula_keys = [f for f, _ in scenario["formulas"]]
    formula_labels = [lab for _, lab in scenario["formulas"]]
    colors = FORMULA_COLOURS[: len(formula_keys)]

    pivot_abs = _pivot(by_inc, scenario, abs_col, formula_keys)
    pivot_pct = _pivot(by_inc, scenario, pct_col, formula_keys)
    addon_pivot_abs = None
    addon_pivot_pct = None
    if addon_col is not None and scenario["key"].startswith("excl_floored"):
        # Absolute panel: floor add-on in USD bn.
        addon_pivot_abs = _pivot(by_inc, scenario, addon_col, formula_keys) / 1e3
        # Percentage panel: hatched slice in % POINTS on the SAME denominator
        # as the bars — total % − tax-only % (both already computed by
        # build_by_income on the group's MNE cash-tax denominator). Dividing
        # the USD add-on by tax_revenue_current_usd instead (total government
        # tax revenue, a ~50× larger denominator than the bars use) would draw
        # the royalty slice ~49× too small; _scenario_machinery_panel uses
        # the same construction — this mirrors it.
        tax_pct_col = pct_col.replace(
            "delta_total_gvt_revenue_", "delta_tax_revenue_"
        )
        if tax_pct_col != pct_col and tax_pct_col in by_inc.columns:
            total_pct = _pivot(by_inc, scenario, pct_col, formula_keys)
            tax_pct = _pivot(by_inc, scenario, tax_pct_col, formula_keys)
            addon_pivot_pct = (total_pct - tax_pct).fillna(0.0)

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    _grouped_bars(
        axes[0], pivot_abs / 1e3, formula_labels, colors,
        ylabel=abs_ylabel, title="absolute (USD bn)", addon_pivot=addon_pivot_abs,
    )
    _grouped_bars(
        axes[1], pivot_pct, formula_labels, colors,
        ylabel=pct_ylabel, title="as %", addon_pivot=addon_pivot_pct,
        is_pct=True,
    )
    # First line = bold title; any further lines = normal-weight subtitle.
    # Shrink the heading when a DATA_BANNER is appended (it makes the line long).
    title_lines = str(suptitle).split("\n")
    fig.suptitle(title_lines[0] + _banner_suffix(),
                 fontsize=(13 if DATA_BANNER else 16),
                 fontweight="bold", y=0.99)
    subtitle = "\n".join(title_lines[1:]).strip()
    rect_top = 0.95
    if subtitle:
        fig.text(0.5, 0.915, subtitle, ha="center", va="top", fontsize=11,
                 fontweight="normal", color="#222222")
        rect_top = 0.87

    note = pct_note + ("\n" + extra_note if extra_note else "")
    if DATA_NOTE:
        note += "\n" + DATA_NOTE
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=7.5, wrap=True,
             color="#444444")
    plt.tight_layout(rect=[0, 0.10, 1, rect_top], w_pad=5)
    plt.savefig(figures_dir / fname, dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


# ---- per-scenario figures ----
def make_scenario_figures(by_inc, scenario, figures_dir, n):
    key = scenario["key"]
    label = scenario["label"]
    floor_note = FLOOR_NOTE if key.startswith("excl_floored") else None

    # Fig 1 — Change in taxable profits
    make_figure(
        by_inc, scenario, figures_dir,
        fname=f"scenario{n}_{key}_1_delta_taxable_profits.png",
        suptitle=f"Scenario {n}: {label} — Change in taxable profits by income group ({WINDOW_LABEL})",
        abs_col="delta_taxable_profits_musd",
        pct_col="delta_taxable_profits_pct_posbase",
        abs_ylabel="Change in taxable profit (USD bn)",
        pct_ylabel="% of current profit base (positive-base countries)",
        pct_note=POSBASE_NOTE,
    )

    # Fig 2 — Change in tax revenue, both gains & losses at ETR
    make_figure(
        by_inc, scenario, figures_dir,
        fname=f"scenario{n}_{key}_2_delta_tax_revenue_bothETR.png",
        suptitle=(
            f"Scenario {n}: {label} — Change in tax revenue by income group ({WINDOW_LABEL})\n"
            f"gains & losses valued at {ETR_LABEL}"
        ),
        abs_col="delta_total_gvt_revenue_recETR_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of MNE corporate cash tax currently paid",
        addon_col="resource_capture_addon_musd",
        extra_note=floor_note,
    )

    # Fig 3 — Change in tax revenue, UT gains at statutory CIT, losses at ETR
    make_figure(
        by_inc, scenario, figures_dir,
        fname=f"scenario{n}_{key}_3_delta_tax_revenue_gainsCIT_lossesETR.png",
        suptitle=(
            f"Scenario {n}: {label} — Change in tax revenue by income group ({WINDOW_LABEL})\n"
            f"UT gains valued at statutory CIT, losses at {ETR_LABEL}"
        ),
        abs_col="delta_total_gvt_revenue_recCIT_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of MNE corporate cash tax currently paid",
        addon_col="resource_capture_addon_musd",
        extra_note=floor_note,
    )


# ---- per-formula scenario comparison ----
SCEN_SHORT = {
    "ignorant_reported": "S1: resources ignored",
    "excl_reported": "S2: corrected for capture",
    "excl_floored_reported": "S3: + min. royalty floor",
}
SCEN_COLOURS = list(PALETTE[:3])


def _scenario_machinery_panel(ax, sub, scen_keys, value_col, ylabel, is_pct,
                               with_addon, usd_decimals=1, ghost_sub=None):
    """One panel: x = income groups, grouped bars = scenarios. If with_addon,
    the floored scenario's bar is split into a solid UT base + hatched
    minimum-royalty floor add-on (the add-on is nonzero only for that scenario).
    ghost_sub (same shape as sub, scaled-to-global values) draws a grey
    unlabelled bar behind each scenario bar."""
    piv = sub.pivot_table(index=_gcol(), columns="scenario",
                          values=value_col, aggfunc="first")
    piv = piv.reindex([g for g in _gorder() if g in piv.index])
    groups = list(piv.index)
    x = np.arange(len(groups))
    n_s = len(scen_keys)
    bw = 0.8 / max(n_s, 1)
    if ghost_sub is not None:
        gpiv = ghost_sub.pivot_table(index=_gcol(), columns="scenario",
                                     values=value_col, aggfunc="first").reindex(groups)
        for i, k in enumerate(scen_keys):
            if k not in gpiv.columns:
                continue
            gvals = gpiv[k].values if is_pct else gpiv[k].values / 1e3
            offset = (i - (n_s - 1) / 2) * bw
            ax.bar(x + offset, gvals, width=bw, color=GHOST_GREY,
                   edgecolor="none", zorder=1)
    addon = None
    if with_addon:
        if is_pct:
            # Addon in % POINTS on the SAME denominator as the bar values: the
            # total-% column already includes the royalty add-on (build_by_income
            # adds it as % of the group's corporate cash tax), so the hatched
            # slice = total % − tax-only %. (Dividing the USD add-on by
            # tax_revenue_current_usd — TOTAL government tax revenue — would use
            # a different, far larger denominator than the % bars.)
            tax_col = value_col.replace("delta_total_gvt_revenue_", "delta_tax_revenue_")
            if tax_col != value_col and tax_col in sub.columns:
                t = sub.pivot_table(index=_gcol(), columns="scenario",
                                    values=tax_col, aggfunc="first").reindex(groups)
                addon = (piv - t).fillna(0.0)
        else:
            a = sub.pivot_table(index=_gcol(), columns="scenario",
                                values="resource_capture_addon_musd",
                                aggfunc="first").reindex(groups)
            addon = a / 1e3
    for i, k in enumerate(scen_keys):
        if k not in piv.columns:
            continue
        vals = piv[k].values if is_pct else piv[k].values / 1e3
        offset = (i - (n_s - 1) / 2) * bw
        add = (addon[k].values if (addon is not None and k in addon.columns)
               else None)
        hh = HATCH_CYCLE[i % len(HATCH_CYCLE)]   # colour-blind redundancy
        if add is not None and np.nansum(np.abs(np.nan_to_num(add))) > 0:
            add = np.nan_to_num(add)
            base = vals - add
            ax.bar(x + offset, base, width=bw, color=SCEN_COLOURS[i],
                   hatch=hh, edgecolor="white", linewidth=0.3)
            ctop = ax.bar(x + offset, add, width=bw, bottom=base, facecolor=SCEN_COLOURS[i],
                          hatch="///", edgecolor="black", linewidth=0.4)
            _label_bars(ax, ctop, vals, is_pct, usd_decimals)   # label the stack total
        else:
            c = ax.bar(x + offset, vals, width=bw, color=SCEN_COLOURS[i],
                       hatch=hh, edgecolor="white", linewidth=0.3)
            _label_bars(ax, c, vals, is_pct, usd_decimals)
    ax.axhline(0, color="grey", linewidth=0.5)
    _pad_ylim(ax)
    ax.set_xticks(x)
    ax.set_xticklabels([_glabels().get(g, g) for g in groups], fontsize=9)
    ax.set_ylabel(ylabel)


def _scenario_machinery_fig(by_inc, formula_key, formula_label, figures_dir,
                             fname, title, subtitle, abs_col, pct_col,
                             abs_ylabel, pct_ylabel, with_addon, note):
    """A 2-panel (absolute USD bn + %) scenario comparison for one formula."""
    sub = by_inc[by_inc["formula_name"] == formula_key]
    scen_keys = [s["key"] for s in SCENARIOS]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    _scenario_machinery_panel(axes[0], sub, scen_keys, abs_col, abs_ylabel,
                               False, with_addon)
    _scenario_machinery_panel(axes[1], sub, scen_keys, pct_col, pct_ylabel,
                               True, with_addon)
    axes[0].set_title("absolute (USD bn)", fontsize=13)
    axes[1].set_title("as %", fontsize=13)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=SCEN_COLOURS[i],
                             hatch=HATCH_CYCLE[i % len(HATCH_CYCLE)],
                             edgecolor="white", linewidth=0.3)
               for i in range(len(scen_keys))]
    labels = [SCEN_SHORT[k] for k in scen_keys]
    if with_addon:
        handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="white", hatch="///",
                                      edgecolor="black"))
        labels.append("Min.-royalty floor add-on")
    axes[0].legend(handles, labels, fontsize=9, loc="best", framealpha=0.85)

    fig.suptitle(title + _banner_suffix(),
                 fontsize=(13 if DATA_BANNER else 16), fontweight="bold", y=0.99)
    rect_top = 0.95
    if subtitle:
        fig.text(0.5, 0.915, subtitle, ha="center", va="top", fontsize=11,
                 color="#222222")
        rect_top = 0.87
    if DATA_NOTE:
        note = note + "\n" + DATA_NOTE
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=7.5, wrap=True,
             color="#444444")
    plt.tight_layout(rect=[0, 0.10, 1, rect_top], w_pad=5)
    plt.savefig(figures_dir / fname, dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def make_formula_scenario_machinery(by_inc, formula_key, formula_label, figures_dir):
    """For a SINGLE formula, three scenario-comparison figures (each absolute +
    %): (1) tax base, (2) tax revenue valued ETR/ETR, (3) tax revenue valued
    gains-CIT / losses-ETR. x = income groups, grouped bars = the three scenarios."""
    base = f"{formula_label}"
    # 1 — tax base
    _scenario_machinery_fig(
        by_inc, formula_key, formula_label, figures_dir,
        fname=f"formula_comparison_{formula_key}_1_tax_base.png",
        title=f"{base}: Change in taxable profit by income group ({WINDOW_LABEL})",
        subtitle=None,
        abs_col="delta_taxable_profits_musd",
        pct_col="delta_taxable_profits_pct_posbase",
        abs_ylabel="Change in taxable profit (USD bn)",
        pct_ylabel="% of current profit base (positive-base countries)",
        with_addon=False, note=POSBASE_NOTE,
    )
    # 2 — revenue, both legs at ETR
    _scenario_machinery_fig(
        by_inc, formula_key, formula_label, figures_dir,
        fname=f"formula_comparison_{formula_key}_2_revenue_bothETR.png",
        title=f"{base}: Change in tax revenue by income group ({WINDOW_LABEL})",
        subtitle=f"gains & losses valued at {ETR_LABEL}",
        abs_col="delta_total_gvt_revenue_recETR_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of MNE corporate cash tax currently paid",
        with_addon=True, note=FLOOR_NOTE + " " + PCT_NOTE,
    )
    # 3 — revenue, gains at statutory CIT, losses at ETR
    _scenario_machinery_fig(
        by_inc, formula_key, formula_label, figures_dir,
        fname=f"formula_comparison_{formula_key}_3_revenue_gainsCIT.png",
        title=f"{base}: Change in tax revenue by income group ({WINDOW_LABEL})",
        subtitle=f"UT gains valued at statutory CIT, losses at {ETR_LABEL}",
        abs_col="delta_total_gvt_revenue_recCIT_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of MNE corporate cash tax currently paid",
        with_addon=True, note=FLOOR_NOTE + " " + PCT_NOTE,
    )


