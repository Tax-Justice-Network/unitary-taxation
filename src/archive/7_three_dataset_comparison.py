"""
Cross-dataset comparison: who gains / loses under UT across three scenarios:

  1. disaggregated         — "Resources ignored" (current SOTJ baseline)
  2. excl_resource         — "Resources excluded" (state's resource take stripped
                              before UT runs on the residual non-resource profit)
  3. excl_resource_floored — "Resources excluded + minimum royalty enforced"
                              (state captures actual resource take PLUS the gap
                              between actual royalty and the IGF-ATAF Cat 1 floor;
                              UT runs on the residual; total state recovery under
                              this regime = UT-derived revenue + floor_add_on)

Outputs are based on **misalignment (tax base in profit $)** rather than on
revenue gains, so they are independent of any CIT / ETR / rate-mode choice.
Misalignment varies only with formula choice, so we use the default formula
(employees_payroll) for the headline figures and average across formulas in
sensitivity tables.

Net tax-base impact per country, per formula, per year:
  net_tax_base = negative_misalignment − positive_misalignment   (in $ profit)

Positive = country gains tax base under UT (had profit shifted out, would
recapture it). Negative = country loses tax base (had profit shifted in
beyond its formula share, would surrender it under UT).

For the floored scenario, the country additionally receives `floor_add_on`
as extra royalty revenue if the resource is sourced in that country (it
adds to the country's *as iso_partner* recovery). We carry it as a
separate stream so the table shows the two components.

Per-share figures: net tax-base shown as % of three different anchors:
  - tax_revenue_current_usd  (World Bank, country's total tax revenue)
  - gvt_health_expenditure   (WHO, government health spending)
  - existing CbCR cash tax   (income_tax_paid_on_cash_basis, sum across parents)

Outputs:
  output/comparison/tables/
    comparison_country_net_misalignment.csv          (long: country × scenario × formula × year)
    comparison_country_summary_default_formula.csv   (one row per country × scenario, default formula)
    comparison_top_gainers.csv / comparison_top_losers.csv
    comparison_per_share.csv
  output/comparison/figures/
    fig_three_scenarios_top_gainers.png
    fig_three_scenarios_top_losers.png
    fig_three_scenarios_by_income_group.png
    fig_per_share_tax_revenue.png
    fig_per_share_health_expenditure.png

Usage:
  python 7_three_dataset_comparison.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import output_dirs, data_final

# The three scenarios.
SCENARIOS = [
    {"key": "ignorant",       "topic": "unitary_taxation_disaggregated",            "sample": "disaggregated",       "label": "Resources ignored",                     "color": "#666666"},
    {"key": "excl_resource",  "topic": "unitary_taxation_excl_resource",            "sample": "excl_resource",        "label": "Resources excluded",                    "color": "#4c72b0"},
    {"key": "excl_floored",   "topic": "unitary_taxation_excl_resource_floored",    "sample": "excl_resource_floored","label": "Resources excluded + min. royalty",     "color": "#2a9d8f"},
]

DEFAULT_FORMULA = "sales_employees_destmnedds"   # paper headline (2026-07-12)
TOP_N = 20

COMPARISON_TOPIC = "comparison"
FOCUS_YEARS_HEADLINE = list(range(2016, 2023))   # 2016–22 by default
TWO_YEAR_HEADLINE = [2021, 2022]


def load_scenario_long(scenario):
    """Read summary_country_year_long.csv for the scenario's topic and filter
    to a single representative spec (misalignment is independent of ETR/rate
    so any spec gives the same misalignment values)."""
    tables_dir, _ = output_dirs(scenario["topic"])
    p = tables_dir / "summary_country_year_long.csv"
    if not p.exists():
        print(f"  [skip] {scenario['key']} — no long table at {p}")
        return pd.DataFrame()
    df = pd.read_csv(p)
    if "sample_name" in df.columns:
        df = df[df["sample_name"] == scenario["sample"]]
    # Misalignment is independent of ETR/rate but does depend on formula.
    df = df[(df["etr_name"] == "average") & (df["rate_mode"] == "loss_cit_gain_etr")]
    df["scenario"] = scenario["key"]
    return df[[
        "scenario", "iso_partner", "partner_jurisdiction", "wb_income_group",
        "region_tjn", "formula_name", "year",
        "positive_misalignment", "negative_misalignment",
        "tax_revenue_current_usd", "gvt_health_expenditure",
        "current_tax_paid_cash_musd",
    ]]


def load_floor_add_on():
    """Per (iso_partner, year), Σ floor_add_on_cat1_usd across all parents.
    This is the additional royalty revenue that the floor would compel for
    countries hosting the resource activity (treated as *iso_partner* in CbCR
    cells — the source country)."""
    p = Path(data_final) / "cbcr_main_excl_resource_floored.csv"
    if not p.exists():
        print(f"  [skip] floor_add_on — no file at {p}")
        return pd.DataFrame()
    df = pd.read_csv(p, usecols=["iso_partner", "year", "floor_add_on_cat1_usd"])
    agg = (
        df.groupby(["iso_partner", "year"], as_index=False)
        .agg(floor_add_on_usd=("floor_add_on_cat1_usd", "sum"))
    )
    return agg


def build_comparison(years_filter):
    parts = []
    for s in SCENARIOS:
        parts.append(load_scenario_long(s))
    long_df = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    if long_df.empty:
        return None

    long_df = long_df[long_df["year"].isin(years_filter)]
    long_df["net_misalignment"] = (
        long_df["negative_misalignment"] - long_df["positive_misalignment"]
    )

    # Aggregate per (scenario, country, formula) summed over years.
    summary = (
        long_df.groupby(
            ["scenario", "iso_partner", "partner_jurisdiction",
             "wb_income_group", "region_tjn", "formula_name"],
            as_index=False, dropna=False,
        )
        .agg(
            positive_misalignment=("positive_misalignment", "sum"),
            negative_misalignment=("negative_misalignment", "sum"),
            net_misalignment=("net_misalignment", "sum"),
            tax_revenue_current_usd=("tax_revenue_current_usd", "mean"),
            gvt_health_expenditure=("gvt_health_expenditure", "mean"),
            current_tax_paid_cash_musd=("current_tax_paid_cash_musd", "sum"),
        )
    )

    # Floor add-on per country (single number summed over years in the filter).
    floor = load_floor_add_on()
    if not floor.empty:
        floor = floor[floor["year"].isin(years_filter)]
        floor_country = (
            floor.groupby("iso_partner", as_index=False)
            .agg(floor_add_on_usd_total=("floor_add_on_usd", "sum"))
        )
        # Floor add-on only relevant for the excl_floored scenario (and we
        # report it as a separate stream alongside UT-derived gain).
        summary["floor_add_on_usd_total"] = (
            summary["iso_partner"].map(floor_country.set_index("iso_partner")["floor_add_on_usd_total"])
            .where(summary["scenario"] == "excl_floored", 0)
            .fillna(0)
        )
    else:
        summary["floor_add_on_usd_total"] = 0

    # Convert misalignment columns to USD billions for readability.
    for c in ["positive_misalignment", "negative_misalignment", "net_misalignment"]:
        summary[c + "_usd_bn"] = summary[c] / 1000   # the long-table values are in musd
    summary["floor_add_on_usd_bn"] = summary["floor_add_on_usd_total"] / 1e9
    # Combined "total recovery" for the floored scenario: net UT-implied tax base
    # gain (in $) + floor add-on royalty. For other scenarios it equals the UT-only piece.
    summary["total_recovery_usd_bn"] = (
        summary["net_misalignment_usd_bn"] + summary["floor_add_on_usd_bn"]
    )

    return summary


def write_tables(summary, out_dir, suffix):
    summary.to_csv(out_dir / f"comparison_country_summary_{suffix}.csv", index=False)
    print(f"  wrote {out_dir / f'comparison_country_summary_{suffix}.csv'}")

    default = summary[summary["formula_name"] == DEFAULT_FORMULA].copy()
    if default.empty:
        return None

    # Pivot to wide: rows = (country), cols = scenario, value = total_recovery_usd_bn
    wide = default.pivot_table(
        index=["iso_partner", "partner_jurisdiction", "wb_income_group"],
        columns="scenario",
        values="total_recovery_usd_bn",
        aggfunc="first",
    ).reset_index()
    wide["max_abs"] = wide[[s["key"] for s in SCENARIOS if s["key"] in wide.columns]].abs().max(axis=1)
    wide = wide.sort_values("max_abs", ascending=False)

    # Top gainers (rank by ignorant baseline)
    gainers = wide.sort_values("ignorant", ascending=False).head(TOP_N)
    losers = wide.sort_values("ignorant", ascending=True).head(TOP_N)

    gainers.to_csv(out_dir / f"comparison_top_gainers_{suffix}.csv", index=False)
    losers.to_csv(out_dir / f"comparison_top_losers_{suffix}.csv", index=False)
    print(f"  wrote {out_dir / f'comparison_top_gainers_{suffix}.csv'}")
    print(f"  wrote {out_dir / f'comparison_top_losers_{suffix}.csv'}")
    return wide, gainers, losers


def fig_three_scenarios(wide, gainers_or_losers, title, fname, figures_dir):
    sub = gainers_or_losers.copy()
    if sub.empty:
        print(f"  [skip] {fname} — no rows")
        return

    labels = sub["partner_jurisdiction"].fillna(sub["iso_partner"]).astype(str)
    n = len(sub)
    fig, ax = plt.subplots(figsize=(11, max(5, 0.40 * n)))
    bar_h = 0.27
    y = np.arange(n)
    for i, s in enumerate(SCENARIOS):
        key = s["key"]
        if key not in sub.columns:
            continue
        vals = sub[key].values
        ax.barh(y + (i - 1) * bar_h, vals, height=bar_h,
                color=s["color"], label=s["label"])
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Net tax-base gain (negative − positive misalignment), USD bn — "
                  "plus floor add-on for the floored scenario")
    ax.set_title(title, fontsize=11)
    ax.axvline(0, color="grey", linewidth=0.5)
    ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=120)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def fig_income_group(summary, title, fname, figures_dir):
    default = summary[summary["formula_name"] == DEFAULT_FORMULA].copy()
    if default.empty:
        print(f"  [skip] {fname} — empty")
        return

    group_order = ["low_income", "lower_middle_income", "middle_income",
                   "upper_middle_income", "high_income",
                   "investment_hub", "other_or_missing"]
    agg = (
        default.groupby(["scenario", "wb_income_group"], as_index=False, dropna=False)
        .agg(total_recovery_usd_bn=("total_recovery_usd_bn", "sum"))
    )
    pivot = agg.pivot_table(
        index="wb_income_group", columns="scenario",
        values="total_recovery_usd_bn", aggfunc="first",
    )
    pivot = pivot.reindex([g for g in group_order if g in pivot.index])

    fig, ax = plt.subplots(figsize=(11, 5))
    pivot.plot.bar(
        ax=ax, width=0.85,
        color=[s["color"] for s in SCENARIOS if s["key"] in pivot.columns],
    )
    ax.set_ylabel("Net tax-base gain (USD bn)")
    ax.set_title(title, fontsize=11)
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.legend(fontsize=8, loc="best")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=120)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def fig_per_share(summary, anchor_col, anchor_label, fname, figures_dir, top_n=20,
                   focus_income_groups=None):
    """For each country, show net tax-base gain (+ floor add-on) as a percentage
    of an anchor (existing tax revenue / health expenditure / current CbCR
    cash tax). One bar per scenario per country, ordered by the magnitude under
    the ignorant baseline."""
    default = summary[summary["formula_name"] == DEFAULT_FORMULA].copy()
    if default.empty:
        return

    if focus_income_groups is not None:
        default = default[default["wb_income_group"].isin(focus_income_groups)]

    anchor_unit = 1e6 if "musd" in anchor_col else 1e9
    default["recovery_usd"] = default["total_recovery_usd_bn"] * 1e9
    # anchor_col is in USD if it's tax_revenue_current_usd etc.; in musd if cash_tax
    if "musd" in anchor_col:
        default["anchor_usd"] = default[anchor_col] * 1e6
    else:
        default["anchor_usd"] = default[anchor_col]
    default["pct"] = 100 * default["recovery_usd"] / default["anchor_usd"]
    default = default[default["anchor_usd"].notna() & (default["anchor_usd"] > 0)]
    default = default[default["pct"].notna() & np.isfinite(default["pct"])]

    pivot = default.pivot_table(
        index=["iso_partner", "partner_jurisdiction"],
        columns="scenario", values="pct", aggfunc="first",
    ).reset_index()
    pivot["max_abs"] = pivot[[s["key"] for s in SCENARIOS if s["key"] in pivot.columns]].abs().max(axis=1)
    pivot = pivot.sort_values("ignorant", ascending=False).head(top_n)

    if pivot.empty:
        print(f"  [skip] {fname} — no rows after anchor filter")
        return

    labels = pivot["partner_jurisdiction"].fillna(pivot["iso_partner"]).astype(str)
    n = len(pivot)
    fig, ax = plt.subplots(figsize=(11, max(5, 0.40 * n)))
    bar_h = 0.27
    y = np.arange(n)
    for i, s in enumerate(SCENARIOS):
        key = s["key"]
        if key not in pivot.columns:
            continue
        vals = pivot[key].values
        ax.barh(y + (i - 1) * bar_h, vals, height=bar_h,
                color=s["color"], label=s["label"])
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(f"Net tax-base gain (+ floor add-on) as % of {anchor_label}")
    ax.set_title(f"Top {top_n} gainers — UT impact as % of {anchor_label}",
                 fontsize=11)
    ax.axvline(0, color="grey", linewidth=0.5)
    ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=120)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def main():
    tables_dir, figures_dir = output_dirs(COMPARISON_TOPIC)
    for years_filter, suffix, label in [
        (FOCUS_YEARS_HEADLINE, "2016_22", "2016–2022"),
        (TWO_YEAR_HEADLINE,    "2021_22", "2021–2022"),
    ]:
        print(f"\n=== building comparison for {label} ===")
        summary = build_comparison(years_filter)
        if summary is None:
            print(f"  [skip] {label}: no data")
            continue
        result = write_tables(summary, tables_dir, suffix)
        if result is None:
            continue
        wide, gainers, losers = result

        fig_three_scenarios(
            wide, gainers,
            title=f"Top {TOP_N} net gainers from UT across three scenarios ({label})\n"
                  f"(formula = {DEFAULT_FORMULA}; misalignment-based, independent of CIT/ETR)",
            fname=f"fig_three_scenarios_top_gainers_{suffix}.png",
            figures_dir=figures_dir,
        )
        fig_three_scenarios(
            wide, losers,
            title=f"Top {TOP_N} net losers from UT across three scenarios ({label})\n"
                  f"(formula = {DEFAULT_FORMULA}; misalignment-based, independent of CIT/ETR)",
            fname=f"fig_three_scenarios_top_losers_{suffix}.png",
            figures_dir=figures_dir,
        )
        fig_income_group(
            summary,
            title=f"Net tax-base gain by WB income group, three scenarios ({label})\n"
                  f"(formula = {DEFAULT_FORMULA})",
            fname=f"fig_three_scenarios_by_income_group_{suffix}.png",
            figures_dir=figures_dir,
        )
        fig_per_share(
            summary,
            anchor_col="tax_revenue_current_usd",
            anchor_label="existing tax revenue (WB)",
            fname=f"fig_per_share_tax_revenue_{suffix}.png",
            figures_dir=figures_dir,
        )
        fig_per_share(
            summary,
            anchor_col="gvt_health_expenditure",
            anchor_label="govt health expenditure (WHO)",
            fname=f"fig_per_share_health_expenditure_{suffix}.png",
            figures_dir=figures_dir,
        )
        fig_per_share(
            summary,
            anchor_col="current_tax_paid_cash_musd",
            anchor_label="existing CbCR corporate cash tax",
            fname=f"fig_per_share_corp_tax_{suffix}.png",
            figures_dir=figures_dir,
        )


if __name__ == "__main__":
    main()
