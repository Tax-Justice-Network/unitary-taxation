"""
Winners / losers analysis for one or more UT datasets.

Reads the country_estimates_*.csv files written by 5_estimate_profit_shifting.py
under output/<topic>/tables/<sample>/, plus the headline run_summary.csv, and
produces for each dataset:

  output/<topic>/tables/
    summary_run_headlines.csv                 — pivoted run_summary by formula × etr × rate-mode
    summary_country_year_long.csv             — all (iso_partner, year, spec) rows concatenated
    summary_country_totals_by_spec.csv        — Σ over years per (country, spec): net UT gain ($M)
    summary_top_gainers.csv                   — top 25 net winners across specs (which countries gain most)
    summary_top_losers.csv                    — top 25 net losers across specs (which countries lose most)
    summary_loss_sensitivity.csv              — which countries lose in HOW MANY of the 60 (formula × etr × rate-mode) specs
    summary_by_income_group.csv               — net UT gain by WB income group × spec

  output/<topic>/figures/
    fig_top_gainers_default_spec.png          — bar chart, top 20 gainers under SOTJ formula × average ETR × loss_cit_gain_etr
    fig_top_losers_default_spec.png           — bar chart, top 20 losers under same default spec
    fig_gain_across_formulas.png              — for top 15 net-gainers, gain across all five formulas (small multiples)
    fig_loss_across_formulas.png              — same, but for losers
    fig_income_group_gains.png                — bar chart, net UT gain by WB income group × formula

Usage:
  python 6_winners_losers_analysis.py                                      # runs both excl_resource & incl_resource_floored
  python 6_winners_losers_analysis.py unitary_taxation_excl_resource       # just that topic
"""
import os
import sys
import re
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def _longpath(p):
    """On Windows, prefix paths > 240 chars with \\\\?\\ so open() bypasses
    the 260-char MAX_PATH limit. The OneDrive + Arabic-character project root
    pushes some country_estimates filenames over the limit."""
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import output_dirs
from _brand import apply_tjn_style, POSITIVE, NEGATIVE

apply_tjn_style()

# Topics to analyse (each = the output_topic configured in script 5's
# DATASET_CONFIGS). The user can override on the command line.
DEFAULT_TOPICS = [
    "unitary_taxation_disaggregated",
    "unitary_taxation_excl_resource",
    "unitary_taxation_excl_resource_floored",
    "unitary_taxation_incl_resource",
]

# CbCR data-quality outliers — countries with reported profit that is many
# orders of magnitude larger than the country's actual economy, indicating
# the CbCR data has a reporting error. Excluded from winner/loser tables
# and figures, but NOT removed from the raw data files (they remain visible
# for inspection / QA).
#   LSO: Lesotho — ~$38B/yr reported vs ~$2B GDP and ~$35M mining take.
#                  Two-pass extraction (May 2026) confirmed the anomaly.
#   FSM: Micronesia — ~$19B/yr reported with 22k employee-years.
#                     Likely flag-of-convenience / shipping-registry haven
#                     activity attributed to FSM.
#   GUF: French Guiana — ~$16B/yr with $0 resource activity. Likely a
#                        French-overseas-territory CbCR reporting artifact.
#   BTN: Bhutan — small economy with disproportionate reported profit.
DATA_QUALITY_EXCLUSIONS = {"LSO", "FSM", "GUF", "BTN"}

# The "default" spec used for headline winner/loser figures — kept in sync
# with the paper headline (2026-07-12): destination measure (all-MNE sales +
# MNE share of BaTIS deliverable imports) + the cell-matched dom/for ETR.
DEFAULT_FORMULA = "sales_employees_destmnedds"
DEFAULT_ETR_NAME = "domfor"
DEFAULT_RATE_MODE = "loss_cit_gain_etr"

TOP_N = 25
TOP_N_FIG = 20


def _country_files(tables_dir):
    """Return all country_estimates_*.csv files under a topic's tables folder.

    Script 5 puts them in a per-sample subfolder; with one sample per run,
    that subfolder takes the RUN_DATASET name. We glob across all subfolders
    so the script doesn't have to know it."""
    files = list(tables_dir.glob("**/country_estimates__*.csv"))
    return files


def _parse_spec_from_filename(path):
    """The filename encodes the spec:
        country_estimates__{formula}__etrdef_{etr_name}__etrmax_{...}__{rate_mode}.csv
    """
    name = path.stem
    m = re.match(
        r"country_estimates__(?P<formula>.+?)__etrdef_(?P<etr>.+?)__etrmax_(?P<thr>.+?)__(?P<rate>.+)$",
        name,
    )
    if not m:
        return None
    return m.groupdict()


def load_country_long(tables_dir):
    """Concatenate all per-spec country files into one long frame."""
    files = _country_files(tables_dir)
    if not files:
        print(f"  [WARN] no country_estimates files under {tables_dir}")
        return pd.DataFrame()

    parts = []
    for fp in files:
        spec = _parse_spec_from_filename(fp)
        if spec is None:
            continue
        df = pd.read_csv(_longpath(fp))
        if df.empty:
            continue
        for k, v in spec.items():
            if k not in df.columns:
                df[k] = v
        parts.append(df)

    long_df = pd.concat(parts, ignore_index=True)
    long_df["year"] = pd.to_numeric(long_df["year"], errors="coerce")
    return long_df


def country_totals_by_spec(long_df):
    """Σ over years per (iso_partner, formula, etr_name, rate_mode)."""
    grp = (
        long_df.groupby(
            ["iso_partner", "partner_jurisdiction", "wb_income_group", "region_tjn",
             "formula_name", "etr_name", "rate_mode"],
            as_index=False, dropna=False,
        )
        .agg(
            net_revenue_gain_musd=("revenue_gain_from_ut", "sum"),
            tax_revenue_loss_musd=("tax_revenue_loss", "sum"),
            tax_revenue_gain_musd=("tax_revenue_gain", "sum"),
            negative_misalignment_musd=("negative_misalignment", "sum"),
            positive_misalignment_musd=("positive_misalignment", "sum"),
            current_tax_paid_cash_musd=("current_tax_paid_cash_musd", "sum"),
        )
    )
    grp["revenue_gain_pct_of_current_tax"] = (
        100 * grp["net_revenue_gain_musd"] / grp["current_tax_paid_cash_musd"]
    ).replace([np.inf, -np.inf], np.nan)
    return grp


def loss_sensitivity_table(country_totals):
    """For each country, count in how many of the spec combos it loses
    (net_revenue_gain_musd < 0) and how many it gains. Plus min/median/max
    net gain across specs."""
    n_specs = country_totals.groupby("iso_partner")["formula_name"].count().rename("n_specs")
    agg = country_totals.groupby(
        ["iso_partner", "partner_jurisdiction", "wb_income_group", "region_tjn"],
        as_index=False, dropna=False,
    ).agg(
        min_net_gain_musd=("net_revenue_gain_musd", "min"),
        median_net_gain_musd=("net_revenue_gain_musd", "median"),
        max_net_gain_musd=("net_revenue_gain_musd", "max"),
        n_specs_losing=("net_revenue_gain_musd", lambda x: int((x < 0).sum())),
        n_specs_gaining=("net_revenue_gain_musd", lambda x: int((x > 0).sum())),
    )
    agg = agg.merge(n_specs, on="iso_partner", how="left")
    agg["share_specs_losing"] = (agg["n_specs_losing"] / agg["n_specs"]).round(3)
    return agg.sort_values("median_net_gain_musd")


def by_income_group(country_totals):
    """Σ over countries per (formula × etr × rate-mode × income group)."""
    return (
        country_totals.groupby(
            ["formula_name", "etr_name", "rate_mode", "wb_income_group"],
            as_index=False, dropna=False,
        )
        .agg(
            net_revenue_gain_musd=("net_revenue_gain_musd", "sum"),
            n_countries=("iso_partner", "nunique"),
        )
    )


def fig_top_n_bar(country_totals, default_filter, n, value_col, ascending, title, fname, figures_dir):
    """Generic top-N bar chart for the default spec."""
    sub = country_totals
    for k, v in default_filter.items():
        sub = sub[sub[k] == v]
    sub = sub.sort_values(value_col, ascending=ascending).head(n)

    if sub.empty:
        print(f"  [skip] {fname} — no rows matching {default_filter}")
        return

    fig, ax = plt.subplots(figsize=(9, max(4, 0.32 * n)))
    labels = sub["partner_jurisdiction"].fillna(sub["iso_partner"]).astype(str)
    values = sub[value_col] / 1000  # musd → $bn
    # ascending=True is the losers chart, =False the gainers chart.
    bars = ax.barh(labels, values, color=(NEGATIVE if ascending else POSITIVE))
    ax.set_xlabel("Net UT revenue gain (USD bn)" if value_col == "net_revenue_gain_musd"
                  else value_col + " (USD bn)")
    ax.set_title(title, fontsize=11)
    ax.invert_yaxis()
    ax.axvline(0, color="grey", linewidth=0.5)
    for b, v in zip(bars, values):
        ax.text(b.get_width() + (1 if v >= 0 else -1), b.get_y() + b.get_height() / 2,
                f"{v:,.1f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=8)
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=120)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def fig_across_formulas(country_totals, top_countries_iso, etr_name, rate_mode,
                         title, fname, figures_dir):
    """Small multiples: per-formula bars for the supplied list of countries."""
    sub = country_totals[
        country_totals["iso_partner"].isin(top_countries_iso)
        & (country_totals["etr_name"] == etr_name)
        & (country_totals["rate_mode"] == rate_mode)
    ].copy()
    if sub.empty:
        print(f"  [skip] {fname} — no rows")
        return

    sub["label"] = sub["partner_jurisdiction"].fillna(sub["iso_partner"]).astype(str)
    # Pivot: rows = country (preserving the order of top_countries_iso), cols = formula
    pivot = sub.pivot_table(
        index="iso_partner", columns="formula_name",
        values="net_revenue_gain_musd", aggfunc="first",
    ).reindex(top_countries_iso)
    pivot = pivot / 1000   # → $bn
    label_map = sub.drop_duplicates("iso_partner").set_index("iso_partner")["label"]
    pivot.index = pivot.index.map(lambda i: label_map.get(i, i))

    fig, ax = plt.subplots(figsize=(11, max(4, 0.45 * len(pivot))))
    pivot.plot.barh(ax=ax, width=0.85)
    ax.set_xlabel("Net UT revenue gain (USD bn)")
    ax.set_title(title, fontsize=11)
    ax.invert_yaxis()
    ax.axvline(0, color="grey", linewidth=0.5)
    ax.legend(title="formula", fontsize=8, loc="lower right")
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=120)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def fig_income_group(by_ig, etr_name, rate_mode, title, fname, figures_dir):
    sub = by_ig[
        (by_ig["etr_name"] == etr_name) & (by_ig["rate_mode"] == rate_mode)
    ].copy()
    if sub.empty:
        print(f"  [skip] {fname} — no rows")
        return

    pivot = sub.pivot_table(
        index="wb_income_group", columns="formula_name",
        values="net_revenue_gain_musd", aggfunc="sum",
    )
    pivot = pivot / 1000   # → $bn
    order = ["low_income", "lower_middle_income", "middle_income",
             "upper_middle_income", "high_income", "investment_hub", "other_or_missing"]
    pivot = pivot.reindex([i for i in order if i in pivot.index])

    fig, ax = plt.subplots(figsize=(11, 5))
    pivot.plot.bar(ax=ax, width=0.85)
    ax.set_ylabel("Net UT revenue gain (USD bn)")
    ax.set_title(title, fontsize=11)
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.legend(title="formula", fontsize=8, loc="best")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=120)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def analyse_topic(topic):
    print(f"\n=== topic: {topic} ===")
    tables_dir, figures_dir = output_dirs(topic)

    run_summary_path = tables_dir / "run_summary.csv"
    if not run_summary_path.exists():
        print(f"  [skip] no run_summary.csv found at {run_summary_path}")
        return

    rs = pd.read_csv(run_summary_path)
    # Pivot a clean view of the headline numbers
    rs_view = rs[[
        "sample_name", "formula_name", "etr_name", "rate_mode",
        "total_shifted_musd_all_years", "total_tax_loss_musd_all_years",
        "total_tax_gain_musd_all_years", "total_revenue_gain_from_ut_musd_all_years",
        "total_current_tax_paid_cash_musd_all_years",
        "revenue_gain_from_ut_pct_of_current_tax_paid_all_years",
        "total_revenue_gain_from_ut_low_income_musd_all_years",
        "total_revenue_gain_from_ut_middle_income_musd_all_years",
    ]].copy()
    rs_view.to_csv(tables_dir / "summary_run_headlines.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_run_headlines.csv'}")
    print(f"  ({len(rs_view)} spec combinations in run_summary)")

    long_df = load_country_long(tables_dir)
    if long_df.empty:
        print(f"  [skip] no country files in {tables_dir}")
        return
    long_df.to_csv(tables_dir / "summary_country_year_long.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_country_year_long.csv'} ({len(long_df):,} rows)")

    totals = country_totals_by_spec(long_df)
    totals.to_csv(tables_dir / "summary_country_totals_by_spec.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_country_totals_by_spec.csv'} ({len(totals):,} rows)")

    # Top gainers / losers (median across specs, then full table)
    sens = loss_sensitivity_table(totals)
    sens.to_csv(tables_dir / "summary_loss_sensitivity.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_loss_sensitivity.csv'}")

    top_gainers = sens.sort_values("median_net_gain_musd", ascending=False).head(TOP_N)
    top_losers = sens.sort_values("median_net_gain_musd", ascending=True).head(TOP_N)
    top_gainers.to_csv(tables_dir / "summary_top_gainers.csv", index=False)
    top_losers.to_csv(tables_dir / "summary_top_losers.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_top_gainers.csv'}")
    print(f"  wrote {tables_dir / 'summary_top_losers.csv'}")

    by_ig = by_income_group(totals)
    by_ig.to_csv(tables_dir / "summary_by_income_group.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_by_income_group.csv'}")

    # Figures: default spec headline plus across-formula comparisons
    default_filter = {
        "formula_name": DEFAULT_FORMULA,
        "etr_name": DEFAULT_ETR_NAME,
        "rate_mode": DEFAULT_RATE_MODE,
    }
    short_topic = topic.replace("unitary_taxation_", "")

    fig_top_n_bar(
        totals, default_filter, TOP_N_FIG, "net_revenue_gain_musd", ascending=False,
        title=f"Top {TOP_N_FIG} net UT gainers — {short_topic}\n"
              f"({DEFAULT_FORMULA}, {DEFAULT_ETR_NAME} ETR, {DEFAULT_RATE_MODE})",
        fname="fig_top_gainers_default_spec.png", figures_dir=figures_dir,
    )
    fig_top_n_bar(
        totals, default_filter, TOP_N_FIG, "net_revenue_gain_musd", ascending=True,
        title=f"Top {TOP_N_FIG} net UT losers — {short_topic}\n"
              f"({DEFAULT_FORMULA}, {DEFAULT_ETR_NAME} ETR, {DEFAULT_RATE_MODE})",
        fname="fig_top_losers_default_spec.png", figures_dir=figures_dir,
    )

    top_gainer_iso = top_gainers["iso_partner"].head(15).tolist()
    top_loser_iso = top_losers["iso_partner"].head(15).tolist()
    fig_across_formulas(
        totals, top_gainer_iso, DEFAULT_ETR_NAME, DEFAULT_RATE_MODE,
        title=f"Top 15 net gainers — gain across formulas ({short_topic}, "
              f"{DEFAULT_ETR_NAME} ETR, {DEFAULT_RATE_MODE})",
        fname="fig_gain_across_formulas.png", figures_dir=figures_dir,
    )
    fig_across_formulas(
        totals, top_loser_iso, DEFAULT_ETR_NAME, DEFAULT_RATE_MODE,
        title=f"Top 15 net losers — loss across formulas ({short_topic}, "
              f"{DEFAULT_ETR_NAME} ETR, {DEFAULT_RATE_MODE})",
        fname="fig_loss_across_formulas.png", figures_dir=figures_dir,
    )
    fig_income_group(
        by_ig, DEFAULT_ETR_NAME, DEFAULT_RATE_MODE,
        title=f"Net UT gain by WB income group × formula — {short_topic}\n"
              f"({DEFAULT_ETR_NAME} ETR, {DEFAULT_RATE_MODE})",
        fname="fig_income_group_gains.png", figures_dir=figures_dir,
    )

    # Print headline diagnostics to stdout
    print()
    print(f"  Top 10 net gainers (median across specs, USD bn):")
    for _, r in top_gainers.head(10).iterrows():
        print(f"    {r['iso_partner']:>4} {(r['partner_jurisdiction'] or '')[:30]:<32}  "
              f"median {r['median_net_gain_musd']/1000:>+9,.1f}  "
              f"min {r['min_net_gain_musd']/1000:>+9,.1f}  "
              f"max {r['max_net_gain_musd']/1000:>+9,.1f}  "
              f"loses in {r['n_specs_losing']}/{int(r['n_specs'])} specs")
    print()
    print(f"  Top 10 net losers (median across specs, USD bn):")
    for _, r in top_losers.head(10).iterrows():
        print(f"    {r['iso_partner']:>4} {(r['partner_jurisdiction'] or '')[:30]:<32}  "
              f"median {r['median_net_gain_musd']/1000:>+9,.1f}  "
              f"min {r['min_net_gain_musd']/1000:>+9,.1f}  "
              f"max {r['max_net_gain_musd']/1000:>+9,.1f}  "
              f"loses in {r['n_specs_losing']}/{int(r['n_specs'])} specs")


def main():
    topics = sys.argv[1:] or DEFAULT_TOPICS
    for topic in topics:
        analyse_topic(topic)


if __name__ == "__main__":
    main()
