# %%
"""
Five-scenario × four-formula comparison report for the SOTJ profit-shifting
estimates.

Scenarios (each draws from its own UT sample):

  1. RESOURCES IGNORED        — disaggregated baseline (current SOTJ default)
  2. RESOURCES EXCLUDED       — excl_resource
  3. RESOURCES EXCL + FLOOR   — excl_resource_floored (IGF-ATAF Cat 1 floor
                                add-on counted as a separate government-revenue stream
                                on top of UT-derived revenue)
  4. 5-FACTOR WITH RESOURCES  — incl_resource, with a resource_factor weighted
                                30%. The formulary apportionment SUBSTITUTES for
                                existing royalty / CIT / equity capture, so the
                                "recovery" is net of the existing capture the
                                country would forgo.

For each scenario we sweep four formulas (and rate modes for diagnostics):

  Scenarios 1-3 use the 4-factor families:
    employees_payroll (SOTJ default), ccctb, three_factors, double_weighted_sales

  Scenario 4 uses their resource-augmented 5-factor variants:
    employees_payroll_resource_30pct, ccctb_with_resources_30pct,
    three_factors_with_resources_30pct, double_weighted_sales_with_resources_30pct

Per (country, scenario, formula) row, the output table carries:

  Identifiers
    scenario, scenario_label, formula_name, formula_label,
    iso_partner, partner_jurisdiction, wb_income_group

  Baselines / context
    previous_profits_musd            Σ reported_profit (the sample's baseline)
    tax_revenue_current_usd          country's total tax revenue (external)
    gvt_health_expenditure           country's govt health expenditure (external)

  Change in taxable profits (rate-mode invariant)
    delta_taxable_profits_musd       (Σ theoretical − Σ reported)
    delta_taxable_profits_pct        % of previous_profits_musd

  Change in tax revenue from UT — two rate-mode choices
    delta_tax_revenue_recCIT_forgETR_musd            losses × CIT, gains × ETR_average
    delta_tax_revenue_recCIT_forgETR_pct_revenue     % of tax_revenue_current_usd
    delta_tax_revenue_recETR_forgETR_musd            both at ETR_average (conservative)
    delta_tax_revenue_recETR_forgETR_pct_revenue

  Resource capture (per country, scenario-aware)
    resource_capture_actual_musd     pre + post + equity (existing state take)
    resource_capture_floor_musd      actual + floor add-on (under IGF-ATAF; non-floored scenarios = actual)
    resource_capture_addon_musd      floor_add_on_cat1 (nonzero only in scenario 3)
    resource_capture_addon_pct       addon as % of actual

  Change in total government revenue under each scenario
    (= Change in tax revenue + scenario-specific resource adjustment;
     scenario 3: + addon;  scenario 4: − actual capture;  others: same as Change in tax revenue)
    delta_total_gvt_revenue_recCIT_forgETR_musd
    delta_total_gvt_revenue_recCIT_forgETR_pct_revenue
    delta_total_gvt_revenue_recCIT_forgETR_pct_health
    delta_total_gvt_revenue_recETR_forgETR_musd
    delta_total_gvt_revenue_recETR_forgETR_pct_revenue
    delta_total_gvt_revenue_recETR_forgETR_pct_health

Denominators (`tax_revenue_current_usd`, `gvt_health_expenditure`) come from
the external columns already merged onto the country_estimates outputs.

Outputs (in output/five_scenarios/):
  tables/
    fivescenario_summary_long_<window>.csv      — one row per (country, scenario, formula)
    fivescenario_by_income_group_<window>.csv   — same columns, aggregated to (scenario, formula, income group)
  figures/
    fig_<scenario>_gvt_revenue_by_income_<window>.png    — one per scenario, 2 rate modes side-by-side
    fig_<scenario>_delta_profits_by_income_<window>.png  — one per scenario
    fig_<scenario>_pct_taxrev_by_income_<window>.png     — one per scenario, Change in gvt revenue as % tax revenue
    fig_<scenario>_pct_health_by_income_<window>.png     — one per scenario, Change in gvt revenue as % health exp

DATA QUALITY: LSO, FSM, GUF, BTN excluded from income-group aggregates and figures
(CbCR profit many orders of magnitude larger than the real economy — reporting anomaly).

Usage: python 8_five_scenario_report.py
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
from _brand import (apply_tjn_style, PALETTE, EARTH_GREEN, BLUE, GOLD, RED)

apply_tjn_style()

# When True, build_summary + the resource-capture loaders deflate each year's
# monetary values to constant BASE_YEAR US dollars before summing over years. Off
# by default (script 8/9/9c keep nominal); the paper-figure driver (9m) turns it on.
_DEFLATE_TO_BASE = False


def _deflate_col(df, col):
    """Multiply a per-year monetary column by the year→BASE_YEAR deflator, in place-safe."""
    if _DEFLATE_TO_BASE and "year" in df.columns:
        f = df["year"].map(deflator_to_base())
        return pd.to_numeric(df[col], errors="coerce") * f
    return df[col]

REPORT_TOPIC = "five_scenarios"

# Each scenario draws from one UT sample directory and one formula family.
# All UT analyses use reported-only data (is_distributed == 0). The former
# with-imputation (disaggregated) variant and its SCENARIOS_IMPUTED list
# were removed 2026-06-05 — reported-only is now the sole UT path.

# ── Reported-only sensitivity series (2026-05-14): identical scenario
# logic but the underlying UT runs are filtered to is_distributed == 0
# (directly-reported country rows only — no disaggregation imputation).
# Bad reporters whose non-domestic data is entirely in aggregates lose
# most of their contribution; per-country values become smaller and
# more conservative. Topics suffixed `_reported`.
SCENARIOS_REPORTED = [
    {
        "key": "ignorant_reported",
        "label": "Resources ignored (baseline)",
        "topic": "unitary_taxation_disaggregated_reported",
        "sample": "disaggregated",
        "formulas": [
            ("sales_employees", "Sales + employees"),
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
            ("sales_employees", "Sales + employees"),
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
            ("sales_employees", "Sales + employees"),
            ("ccctb", "CCCTB"),
            ("three_factors", "Three-factor"),
            ("double_weighted_sales", "Double-weighted sales"),
        ],
    },
    {
        "key": "five_factor_additive_reported",
        "label": "5-factor with resources (α, additive, 10%)",
        "topic": "unitary_taxation_disaggregated_reported",
        "sample": "disaggregated",
        # See `five_factor_additive` for rationale (α=10%, disaggregated sample).
        "formulas": [
            ("employees_payroll_resource_alpha_10pct", "Employees + payroll (SOTJ)"),
            ("ccctb_resource_alpha_10pct", "CCCTB"),
            ("three_factors_resource_alpha_10pct", "Three-factor"),
            ("double_weighted_sales_resource_alpha_10pct", "Double-weighted sales"),
        ],
    },
    {
        # Scenario 5: 5-factor with resources treated as a co-equal factor
        # (α-blended, additive — existing resource regime continues alongside
        # the UT yield). Reads the baseline reported-only UT sample.
        "key": "five_factor_equal_additive_reported",
        "label": "5-factor (resources as additional factor, additive)",
        "topic": "unitary_taxation_disaggregated_reported",
        "sample": "disaggregated",
        "formulas": [
            ("employees_payroll_resource_alpha_equal", "Employees + payroll (SOTJ)"),
            ("ccctb_resource_alpha_equal", "CCCTB"),
            ("three_factors_resource_alpha_equal", "Three-factor"),
            ("double_weighted_sales_resource_alpha_equal", "Double-weighted sales"),
        ],
    },
]

# Reported-only is the sole UT path (the disaggregated/with-imputation
# variant was removed). SCENARIOS kept for consumers that import it.
SCENARIOS = SCENARIOS_REPORTED

# (subfolder, scenarios) — drives the main loop. Each group writes to
# output/five_scenarios/<subfolder>/{tables,figures}/.
SCENARIO_GROUPS = [
    ("reported_only", SCENARIOS_REPORTED),
]

# A stable colour per formula slot so the same colour means "the SOTJ-equivalent
# formula" / "the CCCTB-equivalent formula" / etc. across all four scenarios.
# TJN brand palette (see _brand.py).
FORMULA_COLOURS = [EARTH_GREEN, BLUE, GOLD, RED]
# Extra colours appended for cross-scenario figures, where there are 5 scenarios.
SCENARIO_COLOURS = list(PALETTE)

# Diagnostic rate modes shown side-by-side. The first is the default.
RATE_MODES = [
    (
        "loss_cit_gain_etr",
        "Recovered base × home CIT, forgone base × haven ETR (default)",
    ),
    ("loss_etr_gain_etr", "Recovered & forgone bases × ETR (conservative)"),
    ("loss_cit_gain_cit", "Recovered & forgone bases × statutory CIT"),
]

# Single ETR family for headline numbers (loss/gain rate logic happens in the
# rate_mode column; the ETR family controls which etr_* column is the "gain" rate).
# 2026-07-12 (user): headline = "domfor" — the cell-matched domestic/foreign
# ETR (domestic rate on the domestic cell, foreign rate on foreign-MNE cells);
# "average" remains available in the long tables as the robustness family.
DEFAULT_ETR = "domfor"

YEARS_HEADLINE = [2021, 2022]
YEARS_RECENT = [2020, 2021, 2022]
YEARS_SUPPLEMENTARY = list(range(2016, 2023))
YEARS_PRE2022 = list(range(2016, 2022))  # 2016-2021 (excludes 2022)

# DATA_QUALITY_EXCLUSIONS = {"LSO", "FSM", "GUF", "BTN"}
DATA_QUALITY_EXCLUSIONS = {}

INCOME_GROUP_ORDER = [
    "low_income",
    "lower_middle_income",
    "upper_middle_income",
    "high_income",
    "investment_hub",
]
INCOME_GROUP_LABELS = {
    "low_income": "Low",
    "lower_middle_income": "Lower-mid",
    "upper_middle_income": "Upper-mid",
    "high_income": "High",
    "investment_hub": "Inv. hub",
}


# ─── Loading ─────────────────────────────────────────────────────────────────
def load_scenario(scenario, years_filter):
    """Load summary_country_year_long for `scenario`, keep all four formulas and
    both diagnostic rate modes (default ETR family).  Returns long DataFrame:
        scenario, formula_name, formula_label, rate_mode,
        iso_partner, partner_jurisdiction, wb_income_group, year,
        theoretical_profit, reported_profit, revenue_gain_from_ut,
        tax_revenue_current_usd, gvt_health_expenditure
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
        "tax_revenue_current_usd",
        "gvt_health_expenditure",
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
    equity) that the country *currently* collects.  For scenario 4 the country
    forgoes this under formulary substitution, so it is subtracted from the UT
    revenue gain to give the net change ("recovery")."""
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
    "loss_cit_gain_cit": "recCIT_forgCIT",
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


def build_summary(years_filter, scenarios=SCENARIOS, variant=""):
    """Build the (scenario × formula × country) summary.

    Rate-mode is pivoted out (each row carries both `recCIT_forgETR` and `recETR_forgETR`
    versions of the tax-revenue columns).  All monetary columns are in $ MUSD;
    `_pct_revenue` / `_pct_health` columns are unitless percentages.

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
                  "tax_revenue_current_usd", "gvt_health_expenditure",
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
    # the % denominator convention shared with the paper tables (9j) — loss years
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
        tax_revenue_current_usd=("tax_revenue_current_usd", "mean"),
        gvt_health_expenditure=("gvt_health_expenditure", "mean"),
    )

    # Paper deliverables report the PER-YEAR AVERAGE, not the multi-year sum: divide
    # the summed monetary columns by the number of years in the window (the denominator
    # columns above already use "mean", so they are per-year and consistent).
    _n_years = int(long_df["year"].nunique())
    for _c in ("previous_profits_musd", "posbase_musd",
               "delta_taxable_profits_musd", "delta_tax_revenue_musd"):
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
        "tax_revenue_current_usd",
        "gvt_health_expenditure",
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
    #   scenario 4 (five_factor):  Change in tax revenue − actual resource capture
    # Profit-base comparability is handled in Step 6 by adding the resource
    # profit base back into scenario_baseline_musd / scenario_outcome_musd for
    # excl-class scenarios. The revenue Change in stays unchanged because the resource
    # regime keeps collecting the same amount pre and post.
    for suffix in RATE_SUFFIX.values():
        col_in = f"delta_tax_revenue_{suffix}_musd"
        col_out = f"delta_total_gvt_revenue_{suffix}_musd"
        if col_in not in summary.columns:
            # Rate modes not present in the run (e.g. CIT-CIT, dropped from the
            # MINIMAL grid 2026-06-29) simply have no columns — skip them.
            continue
        summary[col_out] = summary[col_in].copy()
        floor_mask = summary["scenario"].str.startswith("excl_floored")
        five_mask = summary["scenario"].str.startswith("five_factor")
        summary.loc[floor_mask, col_out] += summary.loc[
            floor_mask, "resource_capture_addon_musd"
        ]
        summary.loc[five_mask, col_out] -= summary.loc[
            five_mask, "resource_capture_actual_musd"
        ]

    # Step 5 — derive all pct-of-something columns from the consolidated _musd
    # columns. Denominators stay in USD (mean), numerators in MUSD ⇒ × 1e6.
    for suffix in RATE_SUFFIX.values():
        if f"delta_tax_revenue_{suffix}_musd" not in summary.columns:
            continue   # rate mode not in this run (see Step 4 note)
        rev = summary[f"delta_tax_revenue_{suffix}_musd"]
        tot = summary[f"delta_total_gvt_revenue_{suffix}_musd"]
        summary[f"delta_tax_revenue_{suffix}_pct_revenue"] = _safe_pct(
            rev * 1e6, summary["tax_revenue_current_usd"]
        )
        summary[f"delta_total_gvt_revenue_{suffix}_pct_revenue"] = _safe_pct(
            tot * 1e6, summary["tax_revenue_current_usd"]
        )
        summary[f"delta_total_gvt_revenue_{suffix}_pct_health"] = _safe_pct(
            tot * 1e6, summary["gvt_health_expenditure"]
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
    #   five_factor*  : baseline = reported_incl           ; outcome = UT_theoretical_5fac
    #   five_factor_add: baseline = reported_full          ; outcome = UT_theoretical_disagg_5fac
    # Since the floored-baseline fix (2026-07-12), script 5's reported leg for
    # the floored datasets ALREADY is reported_excl (the pre-floor pool,
    # reconstructed via pool_var/PROFIT_VAR) — so previous_profits_musd needs
    # NO add-on compensation any more. (The old code added floor_add_on here
    # because the reported leg used to be the royalty-reduced pool; keeping it
    # would double-count and understate the floored %-of-base panel.)
    summary["scenario_baseline_musd"] = summary["previous_profits_musd"]
    # For excl-class scenarios we keep the excl_resource baseline (resources
    # excluded from both pre and post) so % comparisons are against the
    # non-resource profit pool that UT actually operates on. The resource
    # profit base is loaded and kept as a column for inspection but NOT
    # added to scenario_baseline_musd. (2026-05-15 trial of adding it back
    # was reverted — see git history.)
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
        "previous_profits_musd",
        "posbase_musd",
        "scenario_baseline_musd",
        "scenario_outcome_musd",
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
        "delta_total_gvt_revenue_recCIT_forgETR_pct_health",
        "delta_total_gvt_revenue_recETR_forgETR_musd",
        "delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
        "delta_total_gvt_revenue_recETR_forgETR_pct_health",
        "delta_total_gvt_revenue_recCIT_forgCIT_musd",
        "delta_total_gvt_revenue_recCIT_forgCIT_pct_revenue",
        "delta_total_gvt_revenue_recCIT_forgCIT_pct_health",
        "tax_revenue_current_usd",
        "gvt_health_expenditure",
    ]
    # Rate modes absent from the run (e.g. CIT-CIT, dropped 2026-06-29) have no
    # columns — select only what exists.
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
]
# Per-country denominators are means / per-country values; for the income-group
# aggregation we sum them (so the pct re-derives correctly as Σnumer / Σdenom).
SUM_DENOM_COLS = ["tax_revenue_current_usd", "gvt_health_expenditure"]


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
            continue   # rate mode not in this run (CIT-CIT dropped 2026-06-29)
        df[f"delta_tax_revenue_{suffix}_pct_revenue"] = _safe_pct(
            df[f"delta_tax_revenue_{suffix}_musd"] * 1e6, df["tax_revenue_current_usd"]
        )
        df[f"delta_total_gvt_revenue_{suffix}_pct_revenue"] = _safe_pct(
            df[f"delta_total_gvt_revenue_{suffix}_musd"] * 1e6,
            df["tax_revenue_current_usd"],
        )
        df[f"delta_total_gvt_revenue_{suffix}_pct_health"] = _safe_pct(
            df[f"delta_total_gvt_revenue_{suffix}_musd"] * 1e6,
            df["gvt_health_expenditure"],
        )
    return df


def write_tables(summary, tables_dir, suffix):
    summary.to_csv(tables_dir / f"fivescenario_summary_long_{suffix}.csv", index=False)
    print(f"  wrote {tables_dir / f'fivescenario_summary_long_{suffix}.csv'}")

    sub = summary[~summary["iso_partner"].isin(DATA_QUALITY_EXCLUSIONS)]
    # Aggregate only the monetary columns present in this run (rate modes absent
    # from the grid, e.g. CIT-CIT, have no columns).
    _sum_cols = [c for c in SUM_MUSD_COLS + SUM_DENOM_COLS if c in sub.columns]
    by_inc = (
        sub.groupby(
            [
                "scenario",
                "scenario_label",
                "formula_name",
                "formula_label",
                "wb_income_group",
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
    by_inc.to_csv(
        tables_dir / f"fivescenario_by_income_group_{suffix}.csv", index=False
    )
    print(f"  wrote {tables_dir / f'fivescenario_by_income_group_{suffix}.csv'}")

    # region-breakdown counterpart (geographic region instead of income group)
    if "region_tjn" in sub.columns:
        by_reg = (
            sub.groupby(
                ["scenario", "scenario_label", "formula_name", "formula_label",
                 "region_tjn"],
                as_index=False, dropna=False,
            )
            .agg({c: "sum" for c in _sum_cols}
                 | {"iso_partner": "nunique"})
            .rename(columns={"iso_partner": "n_countries"})
        )
        by_reg = _add_pct_columns(by_reg)
        by_reg.to_csv(
            tables_dir / f"fivescenario_by_region_{suffix}.csv", index=False
        )
        print(f"  wrote {tables_dir / f'fivescenario_by_region_{suffix}.csv'}")

    return by_inc


# ─── Figures ──────────────────────────────────────────────────────────────────
def _income_pivot(df, value_col, scenario_key, scenarios=SCENARIOS):
    """Return wb_income_group × formula_name pivot (income groups in canonical
    order; formulas in scenario order). `df` is `by_inc` (already aggregated)."""
    scen = next(s for s in scenarios if s["key"] == scenario_key)
    formula_keys = [f for f, _ in scen["formulas"]]
    formula_labels = [lab for _, lab in scen["formulas"]]
    sub = df[df["scenario"] == scenario_key]
    pivot = sub.pivot_table(
        index="wb_income_group",
        columns="formula_name",
        values=value_col,
        aggfunc="first",
    )
    pivot = pivot.reindex([g for g in INCOME_GROUP_ORDER if g in pivot.index])
    pivot = pivot[[f for f in formula_keys if f in pivot.columns]]
    return pivot, formula_keys, formula_labels


def _bar_panel(
    ax,
    pivot,
    formula_labels,
    ylabel,
    title,
    fmt="bn",
    addon_pivot=None,
    addon_legend="Royalty floor add-on",
    colors=None,
):
    """Grouped bar plot — income groups on x, one bar colour per formula.

    If `addon_pivot` is given (same index/columns as `pivot`), each bar is
    stacked: the base layer is `pivot - addon_pivot` (solid), and the add-on
    layer is `addon_pivot` (hatched), sitting on top of the base. So the
    visible bar height equals `pivot` and the user sees how much of the bar
    is UT-derived (solid) vs. royalty-floor-derived (hatched).
    """
    if pivot.empty:
        ax.set_axis_off()
        ax.set_title(f"{title} (no data)", fontsize=9)
        return
    n_formulas = len(pivot.columns)
    if colors is None:
        colors = FORMULA_COLOURS[:n_formulas]
    if addon_pivot is None:
        pivot.plot.bar(ax=ax, width=0.82, color=colors, legend=False)
    else:
        addon = addon_pivot.reindex(index=pivot.index, columns=pivot.columns).fillna(0)
        base = pivot - addon
        n_groups = len(pivot.index)
        bar_width = 0.82 / n_formulas
        x = np.arange(n_groups)
        for i, col in enumerate(pivot.columns):
            offset = (i - (n_formulas - 1) / 2) * bar_width
            base_vals = base[col].values
            addon_vals = addon[col].values
            ax.bar(x + offset, base_vals, width=bar_width, color=colors[i])
            ax.bar(
                x + offset,
                addon_vals,
                width=bar_width,
                facecolor=colors[i],
                hatch="///",
                edgecolor="black",
                linewidth=0.4,
                bottom=base_vals,
            )
        ax.set_xticks(x)
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    ax.set_xlabel("")
    ax.set_xticklabels(
        [INCOME_GROUP_LABELS.get(g, g) for g in pivot.index],
        rotation=0,
        ha="center",
        fontsize=9,
    )
    # Build legend with formula labels (not raw names)
    formula_map = dict(zip(pivot.columns, formula_labels[:n_formulas]))
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[i]) for i in range(n_formulas)]
    labels_h = [formula_map[c] for c in pivot.columns]
    if addon_pivot is not None and addon_pivot.abs().to_numpy().sum() > 0:
        handles.append(
            plt.Rectangle(
                (0, 0), 1, 1, facecolor="white", hatch="///", edgecolor="black"
            )
        )
        labels_h.append(addon_legend)
    ax.legend(handles, labels_h, fontsize=8, loc="best", framealpha=0.85)


_SUPTITLE_MAP = {
    "excl_floored": "  (incl. floor add-on as a separate royalty stream)",
    "excl_floored_reported": "  (incl. floor add-on as a separate royalty stream)",
    "five_factor": "  (UT yield minus existing resource capture)",
    "five_factor_reported": "  (UT yield minus existing resource capture)",
    "five_factor_additive": "  (UT yield on top of existing resource capture)",
    "five_factor_additive_reported": "  (UT yield on top of existing resource capture)",
}


def fig_per_scenario_delta_profits(by_inc, figures_dir, suffix, scenarios=SCENARIOS):
    """One paired figure per scenario: Change in taxable profit (USD bn) left,
    Change in taxable profit (% of previously reported) right."""
    for scen in scenarios:
        _, _, formula_labels = _income_pivot(
            by_inc, "delta_taxable_profits_musd", scen["key"], scenarios
        )
        pivot_abs, _, _ = _income_pivot(
            by_inc, "delta_taxable_profits_musd", scen["key"], scenarios
        )
        pivot_pct, _, _ = _income_pivot(
            by_inc, "delta_taxable_profits_pct", scen["key"], scenarios
        )
        fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
        _bar_panel(
            axes[0],
            pivot_abs / 1e3,
            formula_labels,
            ylabel="Change in taxable profit (USD bn)",
            title="Absolute (USD bn)",
        )
        _bar_panel(
            axes[1],
            pivot_pct,
            formula_labels,
            ylabel="% of previously reported profit",
            title="As % of previously reported profit",
        )
        fig.suptitle(
            f"Scenario: {scen['label']} — Change in taxable profits by income group "
            f"({suffix.replace('_','–')}){_SUPTITLE_MAP.get(scen['key'], '')}",
            fontsize=11,
        )
        plt.tight_layout(rect=[0, 0, 1, 0.95])
        fname = f"fig_{scen['key']}_delta_profits_by_income_{suffix}.png"
        plt.savefig(figures_dir / fname, dpi=120)
        plt.close()
        print(f"  wrote {figures_dir / fname}")


def fig_per_scenario_gvt_revenue(by_inc, figures_dir, suffix, scenarios=SCENARIOS):
    """Per scenario, two paired figures (one per rate-mode):
      - left panel: Change in total gvt revenue (USD bn)
      - right panel: same metric as % of existing tax revenue

    The excl_floored scenario decomposes each bar into UT yield (solid) +
    royalty floor add-on (hatched). Non-floored scenarios have addon = 0, so
    the hatched layer is invisible."""
    floored_keys = {"excl_floored", "excl_floored_reported"}
    for scen in scenarios:
        # Only the excl_floored scenarios decompose the bar into UT yield
        # (solid) + floor add-on (hatched). Other scenarios are single solid bars.
        is_floored = scen["key"] in floored_keys
        for rsuf, rlabel in zip(RATE_SUFFIX.values(), [r[1] for r in RATE_MODES]):
            col_abs = f"delta_total_gvt_revenue_{rsuf}_musd"
            col_pct = f"delta_total_gvt_revenue_{rsuf}_pct_revenue"
            pivot_abs, _, formula_labels = _income_pivot(
                by_inc, col_abs, scen["key"], scenarios
            )
            pivot_pct, _, _ = _income_pivot(by_inc, col_pct, scen["key"], scenarios)
            pivot_abs_bn = pivot_abs / 1e3
            addon_pivot = None
            addon_pct_pivot = None
            if is_floored:
                addon_abs, _, _ = _income_pivot(
                    by_inc, "resource_capture_addon_musd", scen["key"], scenarios
                )
                addon_pivot = addon_abs / 1e3
                addon_pct_pivot = _addon_pct_revenue_pivot(by_inc, scen, scenarios)
            fig, axes = plt.subplots(1, 2, figsize=(15, 5.5))
            _bar_panel(
                axes[0],
                pivot_abs_bn,
                formula_labels,
                ylabel="Change in total government revenue (USD bn)",
                title=f"Absolute (USD bn) — {rlabel}",
                addon_pivot=addon_pivot,
            )
            _bar_panel(
                axes[1],
                pivot_pct,
                formula_labels,
                ylabel="% of existing tax revenue",
                title=f"As % of existing tax revenue — {rlabel}",
                addon_pivot=addon_pct_pivot,
            )
            fig.suptitle(
                f"Scenario: {scen['label']} — Change in total gvt revenue by income group "
                f"({suffix.replace('_','–')}, {rsuf}){_SUPTITLE_MAP.get(scen['key'], '')}",
                fontsize=10,
            )
            plt.tight_layout(rect=[0, 0, 1, 0.95])
            fname = f"fig_{scen['key']}_gvt_revenue_{rsuf}_by_income_{suffix}.png"
            plt.savefig(figures_dir / fname, dpi=120)
            plt.close()
            print(f"  wrote {figures_dir / fname}")


def _addon_pct_revenue_pivot(by_inc, scen, scenarios):
    """For excl_floored: hatched portion in the % panel = (addon_musd × 1e6
    / tax_revenue_current) × 100. Returns wb_income_group × formula pivot."""
    sub = by_inc[by_inc["scenario"] == scen["key"]].copy()
    sub["addon_pct"] = np.where(
        sub["tax_revenue_current_usd"] > 0,
        sub["resource_capture_addon_musd"]
        * 1e6
        / sub["tax_revenue_current_usd"]
        * 100.0,
        0.0,
    )
    formula_keys = [f for f, _ in scen["formulas"]]
    pivot = sub.pivot_table(
        index="wb_income_group",
        columns="formula_name",
        values="addon_pct",
        aggfunc="first",
    )
    pivot = pivot.reindex([g for g in INCOME_GROUP_ORDER if g in pivot.index])
    pivot = pivot[[f for f in formula_keys if f in pivot.columns]]
    return pivot


def fig_family_across_scenarios(
    by_inc, figures_dir, suffix, scenarios, family_label="CCCTB"
):
    """One figure showing one formula family (e.g. CCCTB) across ALL scenarios
    per income group. Mirrors `fig_per_scenario_gvt_revenue` but pivots on
    scenario instead of formula. Each scenario has at most one formula with
    `family_label` as its display label; that's the row we plot per scenario.

    Two side-by-side panels (one per rate mode). Bar = scenario; group = income.
    """
    # For each scenario, find the (formula_name, formula_label) matching family_label.
    scen_to_formula = {}
    for scen in scenarios:
        match = next(
            ((fkey, flab) for fkey, flab in scen["formulas"] if flab == family_label),
            None,
        )
        if match is not None:
            scen_to_formula[scen["key"]] = match
    if not scen_to_formula:
        return

    scen_order = [s for s in scenarios if s["key"] in scen_to_formula]
    rate_labels = [
        (s, lab) for s, lab in zip(RATE_SUFFIX.values(), [r[1] for r in RATE_MODES])
    ]
    fig, axes = plt.subplots(1, len(rate_labels), figsize=(16, 5.8), sharey=True)
    if len(rate_labels) == 1:
        axes = [axes]
    floored_keys = {s["key"] for s in scen_order if s["key"].startswith("excl_floored")}
    for ax, (rsuf, rlabel) in zip(axes, rate_labels):
        col = f"delta_total_gvt_revenue_{rsuf}_musd"
        # Build wb_income_group × scenario pivots. `pivot` holds the total
        # height of each bar; `addon_pivot` carries the floor add-on portion
        # so we can hatch it on top (nonzero only for excl_floored scenarios).
        rows = []
        for scen in scen_order:
            fkey, _ = scen_to_formula[scen["key"]]
            sub = by_inc[
                (by_inc["scenario"] == scen["key"]) & (by_inc["formula_name"] == fkey)
            ]
            for _, r in sub.iterrows():
                rows.append(
                    {
                        "wb_income_group": r["wb_income_group"],
                        "scenario_key": scen["key"],
                        "value_bn": r[col] / 1e3,
                        "addon_bn": (
                            (r["resource_capture_addon_musd"] / 1e3)
                            if scen["key"] in floored_keys
                            else 0.0
                        ),
                    }
                )
        if not rows:
            ax.set_axis_off()
            ax.set_title(f"{rlabel} (no data)", fontsize=9)
            continue
        rdf = pd.DataFrame(rows)
        pivot = rdf.pivot_table(
            index="wb_income_group",
            columns="scenario_key",
            values="value_bn",
            aggfunc="first",
        )
        addon_pivot = rdf.pivot_table(
            index="wb_income_group",
            columns="scenario_key",
            values="addon_bn",
            aggfunc="first",
        )
        pivot = pivot.reindex([g for g in INCOME_GROUP_ORDER if g in pivot.index])
        pivot = pivot[[s["key"] for s in scen_order if s["key"] in pivot.columns]]
        addon_pivot = addon_pivot.reindex(
            index=pivot.index, columns=pivot.columns
        ).fillna(0)

        n_scen = len(pivot.columns)
        colors = SCENARIO_COLOURS[:n_scen]
        # Solid base = total − addon (UT yield for floored scenarios; full total
        # for the rest). Hatched layer = addon (only nonzero for floored).
        n_groups = len(pivot.index)
        bar_width = 0.84 / n_scen
        x = np.arange(n_groups)
        base = pivot - addon_pivot
        for i, col_key in enumerate(pivot.columns):
            offset = (i - (n_scen - 1) / 2) * bar_width
            base_vals = base[col_key].values
            addon_vals = addon_pivot[col_key].values
            face = colors[i] if colors else None
            ax.bar(x + offset, base_vals, width=bar_width, color=face)
            ax.bar(
                x + offset,
                addon_vals,
                width=bar_width,
                facecolor=face,
                hatch="///",
                edgecolor="black",
                linewidth=0.4,
                bottom=base_vals,
            )
        ax.set_xticks(x)
        ax.axhline(0, color="grey", linewidth=0.5)
        ax.set_ylabel("Change in total government revenue (USD bn)")
        ax.set_title(rlabel, fontsize=10)
        ax.set_xlabel("")
        ax.set_xticklabels(
            [INCOME_GROUP_LABELS.get(g, g) for g in pivot.index],
            rotation=0,
            ha="center",
            fontsize=9,
        )
        scen_label_map = {s["key"]: s["label"] for s in scen_order}
        handles = [plt.Rectangle((0, 0), 1, 1, color=colors[i]) for i in range(n_scen)]
        labels_h = [scen_label_map[c] for c in pivot.columns]
        if addon_pivot.abs().to_numpy().sum() > 0:
            handles.append(
                plt.Rectangle(
                    (0, 0), 1, 1, facecolor="white", hatch="///", edgecolor="black"
                )
            )
            labels_h.append("Royalty floor add-on")
        ax.legend(handles, labels_h, fontsize=7, loc="best", framealpha=0.85)

    fig.suptitle(
        f"{family_label} across all scenarios — Change in total gvt revenue by income group "
        f"({suffix.replace('_','–')})",
        fontsize=11,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    fname_tag = family_label.lower().replace(" ", "_").replace("+", "plus")
    fname = f"fig_{fname_tag}_across_scenarios_gvt_revenue_by_income_{suffix}.png"
    plt.savefig(figures_dir / fname, dpi=120)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def fig_per_scenario_pct(
    by_inc, figures_dir, suffix, pct_col, denom_label, fname_tag, scenarios=SCENARIOS
):
    """One figure per scenario — Change in total gvt revenue as % of {tax_revenue,
    health_expenditure}. Default rate-mode suffix only (recCIT_forgETR)."""
    for scen in scenarios:
        pivot, _, formula_labels = _income_pivot(
            by_inc, pct_col, scen["key"], scenarios
        )
        fig, ax = plt.subplots(figsize=(10, 5.5))
        _bar_panel(
            ax,
            pivot,
            formula_labels,
            ylabel=f"Change in total gvt revenue as % of {denom_label}",
            title=f"Change in total gvt revenue as % of {denom_label} — {scen['label']} "
            f"({suffix.replace('_','–')})",
        )
        plt.tight_layout()
        fname = f"fig_{scen['key']}_pct_{fname_tag}_by_income_{suffix}.png"
        plt.savefig(figures_dir / fname, dpi=120)
        plt.close()
        print(f"  wrote {figures_dir / fname}")


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    windows = [
        (YEARS_HEADLINE, "2021_22", "2021–2022"),
        (YEARS_RECENT, "2020_22", "2020–2022"),
        (YEARS_SUPPLEMENTARY, "2016_22", "2016–2022"),
        (YEARS_PRE2022, "2016_21", "2016–2021"),
    ]
    for group_name, group_scenarios in SCENARIO_GROUPS:
        tables_dir, figures_dir = output_dirs(f"{REPORT_TOPIC}/{group_name}")
        for years_filter, suffix, label in windows:
            print(
                f"\n=== five-scenario × four-formula report [{group_name}] — {label} ==="
            )
            summary = build_summary(years_filter, group_scenarios)
            if summary is None:
                print(f"  [skip] {label}: no data")
                continue
            by_inc = write_tables(summary, tables_dir, suffix)
            fig_per_scenario_delta_profits(by_inc, figures_dir, suffix, group_scenarios)
            fig_per_scenario_gvt_revenue(by_inc, figures_dir, suffix, group_scenarios)

            # Cross-scenario family comparison — one figure per family per
            # group per window. Each scenario's formula list pairs a unique
            # formula_name with one of these four display labels.
            for fam in (
                "Employees + payroll (SOTJ)",
                "CCCTB",
                "Three-factor",
                "Double-weighted sales",
            ):
                fig_family_across_scenarios(
                    by_inc, figures_dir, suffix, group_scenarios, family_label=fam
                )

            # Headline print (default rate-mode suffix = recCIT_forgETR, MUSD → USD bn)
            print(
                f"\n  Change in total gvt revenue by income group [{group_name}] ({label}, loss×CIT/gain×ETR):"
            )
            for scen in group_scenarios:
                sub = by_inc[by_inc["scenario"] == scen["key"]]
                if sub.empty:
                    continue
                print(f"    {scen['label']}:")
                for ig in INCOME_GROUP_ORDER:
                    rows = sub[sub["wb_income_group"] == ig]
                    if rows.empty:
                        continue
                    pieces = []
                    for fkey, flabel in scen["formulas"]:
                        r = rows[rows["formula_name"] == fkey]
                        if r.empty:
                            continue
                        v = (
                            r["delta_total_gvt_revenue_recCIT_forgETR_musd"].iloc[0]
                            / 1e3
                        )
                        pieces.append(f"{flabel[:16]} {v:+6.1f}")
                    print(
                        f"      {INCOME_GROUP_LABELS.get(ig, ig):>10}: "
                        + " | ".join(pieces)
                    )


if __name__ == "__main__":
    main()
