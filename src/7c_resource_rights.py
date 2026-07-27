# %%
"""
7c — The relevance of resource rights.

For the three resource treatments — resources ignored, resources excluded (the
baseline), and excluded plus the minimum-royalty floor — it builds, on the
reported-only sample, the per-treatment income-group figures, the
resource-treatment revenue figure (Figure 5), the Angola/Peru and
Guinea/Madagascar country examples (Figures 6–7), and the scenario table
(Table 4, with and without resource-rent correction). A second part writes the
wide scenario × formula detail tables and figure grid. The shared machinery —
scenario definitions, `build_summary`, income-group aggregation, grouped-bar
plotting, window and deflation conventions and the IGF-ATAF floor add-on — lives
in `_scenario_machinery.py`. (The plausible-range revenue figure, paper Figure 4,
is done in 7b_formula_results.)

Headline specification: reported-only sample, resources excluded, employees + destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at statutory CIT and losses at ETR, per-year average over 2016–2022 (2020 excluded), constant 2025 US$.

Exhibit script — consumes the script-6 estimation summaries. Produces Figures 5-7
+ Table 4 (the three resource treatments) + region twin figB + country slides;
needs 7g's loss-consolidation number, so the driver runs 7g first.

Reads:
  output/estimates/reported_only/{1_resources_ignored,2_resources_excluded,3_minimum_royalty_added}/tables/summary_country_year_long.csv — the three scenarios (script 6)
  output/paper/main_text/scaleup_yearly.csv                             — ghost-bar scale factors (from 7a)
  output/analysis/loss_consolidation/…                                 — loss-consolidation figure (from 7g)

Writes:
  output/paper/main_text/fig05_*.png/.pdf                              — Figure 5 (three-treatment revenue)
  output/paper/main_text/fig06_*.png/.pdf                              — Figure 6 (Angola + Peru)
  output/paper/main_text/fig07_*.png/.pdf                              — Figure 7 (Guinea + Madagascar)
  output/paper/main_text/table4_scenarios.csv/.tex                     — Table 4 (scenarios w/ & w/o resource correction)
  output/analysis/scenario_comparison/…                               — wide scenario × formula detail + country slides

Usage:
  python 7c_resource_rights.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Settings and shared machinery
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from config import output_dirs
from _brand import apply_tjn_style, PALETTE, HATCH_CYCLE, POSITIVE, NEGATIVE

apply_tjn_style()

# ── The comparison machinery lives in the shared module. ──
import _scenario_machinery as _sc

build_summary = _sc.build_summary
SUM_MUSD_COLS = _sc.SUM_MUSD_COLS
SUM_DENOM_COLS = _sc.SUM_DENOM_COLS
_add_pct_columns = _sc._add_pct_columns
_safe_pct_positive_base = _sc._safe_pct_positive_base
INCOME_GROUP_ORDER = _sc.INCOME_GROUP_ORDER
INCOME_GROUP_LABELS = _sc.INCOME_GROUP_LABELS
FORMULA_COLOURS = _sc.FORMULA_COLOURS
DATA_QUALITY_EXCLUSIONS = _sc.DATA_QUALITY_EXCLUSIONS
# Detail report (Part B) additionally uses:
RATE_MODES = _sc.RATE_MODES
RATE_SUFFIX = _sc.RATE_SUFFIX
SCENARIO_COLOURS = _sc.SCENARIO_COLOURS
SCENARIO_GROUPS = _sc.SCENARIO_GROUPS
YEARS_PAPER = _sc.YEARS_PAPER
YEARS_SUPPLEMENTARY = _sc.YEARS_SUPPLEMENTARY

REPORT_TOPIC = "three_scenarios"  # Part A → …/scenario_comparison/reported_only
DETAIL_TOPIC = _sc.REPORT_TOPIC  # Part B → …/scenario_comparison/detail
YEARS = list(range(2016, 2023))  # 2016–2022 inclusive

# The shared report machinery (income-group aggregation + figure functions)
# lives in _scenario_machinery — bind the names this script uses.
build_by_income = _sc.build_by_income
make_figure = _sc.make_figure
make_scenario_figures = _sc.make_scenario_figures
make_formula_scenario_machinery = _sc.make_formula_scenario_machinery
WINDOW_LABEL = _sc.WINDOW_LABEL
ETR_LABEL = _sc.ETR_LABEL

# The three reported-only scenarios, in display order.
SCENARIOS = [
    s
    for key in ("ignorant_reported", "excl_reported", "excl_floored_reported")
    for s in _sc.SCENARIOS_REPORTED
    if s["key"] == key
]
FLOORED_KEY = "excl_floored_reported"

# Per-formula three-scenario comparison covers ALL formula families (display order).
# The grouped-bar per-scenario figures keep the original 4 families; these extra
# sales families are loaded only so the per-formula comparison can cover them too.
SCEN_COMPARE_FORMULAS = [
    ("sales_employees", "Sales + employees"),
    # HEADLINE destination measure: all-MNE sales + MNE share of BaTIS
    # digitally-deliverable imports. 7i's country examples select this
    # formula from the summary this script writes — keep it in this list.
    ("sales_employees_destmnedds", "Employees + destination-based sales (headline)"),
    ("ccctb", "CCCTB"),
    ("three_factors", "Three-factor"),
    ("double_weighted_sales", "Double-weighted sales"),
]
# Scenario list with the formula set widened for build_summary (so by_income carries
# every family the comparison loop needs); the scenario grouped-bar figures still use
# the original SCENARIOS (4 families), so they are unchanged.
SCENARIOS_EXT = []
for _s in SCENARIOS:
    _s2 = dict(_s)
    _have = {f for f, _ in _s["formulas"]}
    _s2["formulas"] = list(_s["formulas"]) + [
        (k, l) for k, l in SCEN_COMPARE_FORMULAS if k not in _have
    ]
    SCENARIOS_EXT.append(_s2)


# %% MARK: 2. Detail report — tables
def write_tables(summary, tables_dir, suffix):
    summary.to_csv(tables_dir / f"scenario_summary_long_{suffix}.csv", index=False)
    print(f"  wrote {tables_dir / f'scenario_summary_long_{suffix}.csv'}")

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
        .agg({c: "sum" for c in _sum_cols} | {"iso_partner": "nunique"})
        .rename(columns={"iso_partner": "n_countries"})
    )
    by_inc = _add_pct_columns(by_inc)
    by_inc.to_csv(tables_dir / f"scenario_by_income_group_{suffix}.csv", index=False)
    print(f"  wrote {tables_dir / f'scenario_by_income_group_{suffix}.csv'}")

    # region-breakdown counterpart (geographic region instead of income group)
    if "region_tjn" in sub.columns:
        by_reg = (
            sub.groupby(
                [
                    "scenario",
                    "scenario_label",
                    "formula_name",
                    "formula_label",
                    "region_tjn",
                ],
                as_index=False,
                dropna=False,
            )
            .agg({c: "sum" for c in _sum_cols} | {"iso_partner": "nunique"})
            .rename(columns={"iso_partner": "n_countries"})
        )
        by_reg = _add_pct_columns(by_reg)
        by_reg.to_csv(tables_dir / f"scenario_by_region_{suffix}.csv", index=False)
        print(f"  wrote {tables_dir / f'scenario_by_region_{suffix}.csv'}")

    return by_inc


# %% MARK: 3. Detail report — figures
def _income_pivot(df, value_col, scenario_key, scenarios=SCENARIOS):
    """Return wb_income_group × formula_name pivot (income groups in canonical
    order; formulas in scenario order). `df` is `by_inc` (already aggregated)."""
    scen = next(s for s in scenarios if s["key"] == scenario_key)
    formula_keys = [f for f, _ in scen["formulas"]]
    formula_labels = [lab for _, lab in scen["formulas"]]
    sub = df[df["scenario"] == scenario_key]
    # Value column absent from the run (e.g. a dropped rate mode) → empty pivot.
    if value_col not in sub.columns:
        return pd.DataFrame(), formula_keys, formula_labels
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
            # Rate modes absent from the run (e.g. CIT-CIT) have no columns —
            # skip their figure.
            if col_abs not in by_inc.columns:
                continue
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
    """For excl_floored: hatched portion in the % panel = addon_musd as a % of
    the corporate tax the group's MNEs currently pay. Returns
    wb_income_group × formula pivot."""
    sub = by_inc[by_inc["scenario"] == scen["key"]].copy()
    sub["addon_pct"] = np.where(
        sub["current_tax_paid_cash_musd"] > 0,
        sub["resource_capture_addon_musd"] / sub["current_tax_paid_cash_musd"] * 100.0,
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


# %% MARK: 4. Main
def main_figures():
    """Part A — the focused three-scenario figure deliverable (reported-only)."""
    tables_dir, figures_dir = output_dirs(REPORT_TOPIC)

    print(
        f"Building three-scenario summary ({WINDOW_LABEL}, reported-only, {ETR_LABEL})…"
    )
    summary = build_summary(YEARS, SCENARIOS_EXT)
    if summary is None or summary.empty:
        raise SystemExit("No data returned by build_summary — check UT outputs exist.")

    by_inc = build_by_income(summary)

    summary.to_csv(tables_dir / "three_scenario_summary_long_2016_22.csv", index=False)
    by_inc.to_csv(
        tables_dir / "three_scenario_by_income_group_2016_22.csv", index=False
    )
    print(f"  wrote {tables_dir / 'three_scenario_summary_long_2016_22.csv'}")
    print(f"  wrote {tables_dir / 'three_scenario_by_income_group_2016_22.csv'}")

    for n, scenario in enumerate(SCENARIOS, start=1):
        print(f"\nScenario {n}: {scenario['label']} [{scenario['key']}]")
        make_scenario_figures(by_inc, scenario, figures_dir, n)

    # Per-formula three-scenario comparison — ALL formula families.
    print("\nFormula scenario comparison (all formulas):")
    present = set(by_inc["formula_name"].unique())
    for fkey, flabel in SCEN_COMPARE_FORMULAS:
        if fkey in present:
            make_formula_scenario_machinery(by_inc, fkey, flabel, figures_dir)
        else:
            print(f"  (skip {fkey} — not in summary)")


def main_detail():
    """Part B — the wide scenario × formula detail report, both windows."""
    windows = [
        (YEARS_PAPER, "2016_22ex20", "2016–2022 excl. 2020 (paper window)"),
        (YEARS_SUPPLEMENTARY, "2016_22", "2016–2022 incl. 2020 (supplementary)"),
    ]
    for group_name, group_scenarios in SCENARIO_GROUPS:
        tables_dir, figures_dir = output_dirs(f"{DETAIL_TOPIC}/{group_name}")
        for years_filter, suffix, label in windows:
            print(
                f"\n=== scenario × formula detail report [{group_name}] — {label} ==="
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
            # formula_name with one of these display labels.
            for fam in (
                "Sales (destination) + employees — headline",
                "Sales (origin) + employees",
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


# %% MARK: 5. Paper exhibits — scenario figures, country examples, Table 4
# The scenario-concept slices of the paper deliverable: the three-resource-
# treatment figures, the revenue-ranges figure, the country-example figures
# and the scenario table, in the
# paper style (untitled panels; the caption lives in the Word document).
import glob as _glob

import _exhibit_helpers as _eh

_PAPER_FLOOR_NOTE = (
    "The '+ minimum royalty' bars add the IGF-ATAF minimum-royalty floor (hatched portion) "
    "as a separate government-revenue stream on top of the unitary-taxation yield."
)


def paper_scenario_figures(sample, by_inc, ghost_by_inc=None, by_region=None):
    """figF3 (taxable profit) + fig05 (revenue, hatched floor add-on) across the
    three resource treatments; the reported sample adds the ETR-ETR mirror and
    (when by_region is given) the Appendix-B by-world-region twin of Figure 5."""
    figures_dir = _eh.figdir(sample)
    keys = _eh.SCEN_KEYS[sample]
    # Bar order: the MAIN specification (resource rights prior to taxing
    # rights) first, then the minimum-royalty add-on, then the ignore-
    # resource-rights comparison.
    scen_keys = [keys["excl"], keys["floored"], keys["ignorant"]]
    scen_labels = [_eh.SCEN_LABEL_PAPER[k] for k in scen_keys]
    _eh.scen_twopanel(
        by_inc,
        _eh.HEADLINE_FORMULA,
        scen_keys,
        scen_labels,
        "delta_taxable_profits_musd",
        "delta_taxable_profits_pct_posbase",
        _eh.TP_ABS,
        _eh.TP_PCT,
        False,
        "figF3_taxbase_three_treatments.png",
        figures_dir,
    )
    _eh.scen_twopanel(
        by_inc,
        _eh.HEADLINE_FORMULA,
        scen_keys,
        scen_labels,
        _eh.REV_CIT,
        _eh.REV_CIT_PCT,
        _eh.RV_ABS,
        _eh.RV_PCT,
        True,
        "fig05_revenue_three_treatments.png",
        figures_dir,
        usd_decimals=0,
    )
    if sample == "reported_only":
        _eh.scen_twopanel(
            by_inc,
            _eh.HEADLINE_FORMULA,
            scen_keys,
            scen_labels,
            _eh.REV_ETR,
            _eh.REV_ETR_PCT,
            _eh.RV_ABS,
            _eh.RV_PCT,
            True,
            "figE_revenue_three_treatments_etretr.png",
            figures_dir,
            usd_decimals=0,
        )
    # Appendix B: by-world-region twin of Figure 5 (reported sample only).
    if by_region is not None:
        bdir = _eh.figdir_appendix_b()

        def _twin():
            _eh.scen_twopanel(by_region, _eh.HEADLINE_FORMULA, scen_keys, scen_labels,
                              _eh.REV_CIT, _eh.REV_CIT_PCT, _eh.RV_ABS, _eh.RV_PCT, True,
                              "figB_revenue_three_treatments_by_region.png", bdir, usd_decimals=0)
        _eh.region_figures(_twin)


def paper_country_examples(summary, figures_dir):
    """Fig 6 — Angola + Peru (two resource treatments); Fig 7 — Guinea +
    Madagascar (three treatments incl. the floor); plus ETR-ETR mirrors.

    Country choice: Chad is not used (it does not lose under the baseline);
    South Sudan is not used (its apparent excl_resource "win" is an artifact of
    a degenerate ETR, removed by the negligible-base CIT substitution). Mali is
    not used for the floor (it clears the minimum ~2x, so it has no genuine
    top-up); Guinea is the genuine flip case and Madagascar shows the same
    pattern (mining = 49% of exports but <2% of government revenue)."""
    # Narrative order: first the status-quo-like "ignore resource rights"
    # (losses), THEN "resource rights prior" (gains).
    keys2 = ["ignorant_reported", "excl_reported"]
    keys3 = ["ignorant_reported", "excl_reported", "excl_floored_reported"]
    for fname, isos, keys, rev in [
        (
            "fig06_country_angola_peru.png",
            [("AGO", "Angola"), ("PER", "Peru")],
            keys2,
            _eh.REV_CIT,
        ),
        (
            "fig07_country_gin_mdg.png",
            [("GIN", "Guinea"), ("MDG", "Madagascar")],
            keys3,
            _eh.REV_CIT,
        ),
        (
            "figE_country_angola_peru_etretr.png",
            [("AGO", "Angola"), ("PER", "Peru")],
            keys2,
            _eh.REV_ETR,
        ),
        (
            "figE_country_gin_mdg_etretr.png",
            [("GIN", "Guinea"), ("MDG", "Madagascar")],
            keys3,
            _eh.REV_ETR,
        ),
    ]:
        fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
        for ax, (iso, name) in zip(axes, isos):
            _eh.country_panel(
                ax, summary, iso, keys, rev, "Change in tax revenue (USD bn)", name
            )
        plt.tight_layout()
        plt.savefig(figures_dir / fname, dpi=130)
        plt.close()
        print(f"  wrote {figures_dir / fname}")


def build_table_scenarios(sample, tables_dir):
    """Table of the scenarios x {taxable profit, tax revenue} per country
    (output name table4_scenarios = paper Table 4)."""
    excl_rev = _eh.rev_musd(sample, "excl_resource", _eh.HEADLINE_FORMULA)
    if excl_rev.empty:
        print(f"  [skip Table scenarios] no {sample} summary")
        return
    order_iso = pd.Index(sorted(excl_rev.index, key=lambda i: _eh.cname(i).lower()))
    grp = _eh.income_group(sample).to_dict()
    grp_reg = _eh.region(sample).to_dict()
    royalty = _eh.floor_royalty_musd(sample)
    ut_floored = _eh.rev_musd(sample, "excl_resource_floored", _eh.HEADLINE_FORMULA)
    t1 = pd.DataFrame(index=order_iso)
    # Reference bases (constant BASE_YEAR $) so readers can compute any % change.
    t1["reported profit base"] = _eh.reported_musd(sample, "excl_resource")
    t1["current tax revenue from MNEs"] = _eh.current_rev_musd(sample)
    # Our BASELINE is the resources-EXCLUDED scenario; the "resources ignored"
    # column is the naive comparison (extractive profit treated like any other
    # sector) and is NEVER called the baseline. Order = naive -> baseline ->
    # baseline + minimum royalty.
    t1["resources ignored — Δ taxable profit"] = _eh.taxbase_musd(
        sample, "baseline", _eh.HEADLINE_FORMULA
    )
    t1["resources ignored — Δ tax revenue"] = _eh.rev_musd(
        sample, "baseline", _eh.HEADLINE_FORMULA
    )
    t1["baseline (resources excluded) — Δ taxable profit"] = _eh.taxbase_musd(
        sample, "excl_resource", _eh.HEADLINE_FORMULA
    )
    t1["baseline (resources excluded) — Δ tax revenue"] = _eh.rev_musd(
        sample, "excl_resource", _eh.HEADLINE_FORMULA
    )
    t1["+ minimum royalty — Δ tax revenue (total)"] = ut_floored.add(
        royalty, fill_value=0.0
    )
    t1["of which: royalty"] = royalty
    # Loss consolidation is reported ONLY at the aggregate / income-group level
    # (7f_loss_consolidation writes fig10 + loss_consolidation_by_income_group_*.csv
    # and the world total), NOT per country — dropped from this country table
    # 2026-07-25 at the author's request.
    _eh.emit_table(t1, order_iso, grp, grp_reg, sample, "table4_scenarios", tables_dir)


def main_paper():
    """The scenario-concept paper exhibits, both samples."""
    _sc.INCOME_GROUP_LABELS = _eh.IG_LABELS_PAPER
    _sc.FLOOR_NOTE = _PAPER_FLOOR_NOTE
    for sample in _eh.SAMPLES:
        print(f"== paper exhibits [{sample}] ==")
        if not _eh.summary_exists(sample):
            print(f"  [skip] no {sample} summaries yet")
            continue
        summary = _eh.paper_summary(sample)
        if summary is None:
            continue
        by_inc = _sc.build_by_income(summary)
        ghost = _eh.ghost_by_income(sample) if sample == "reported_only" else None
        by_region = (_sc.build_by_income(summary, gcol="region_tjn")
                     if sample == "reported_only" else None)
        paper_scenario_figures(sample, by_inc, ghost_by_inc=ghost, by_region=by_region)
        if sample == "reported_only":
            paper_country_examples(summary, _eh.figdir(sample))
        build_table_scenarios(sample, _eh.tabledir(sample))


# %% MARK: 6. Country-example slides (analysis deliverable)
# Four low-income country examples on the RAW (reported-only) data — the
# slide-format deliverable (one figure per country, all four formula
# families), reading the summary Part A writes. Chad & South Sudan: resource
# exclusion; Guinea & Madagascar: the minimum-royalty floor.
SLIDE_EXAMPLES = [
    ("TCD", "Chad", "Corrected for resource rent capture"),
    ("SSD", "South Sudan", "Corrected for resource rent capture"),
    ("GIN", "Guinea", "Minimum royalty"),
    ("MDG", "Madagascar", "Minimum royalty"),
]
SLIDE_SCEN = {
    "ignorant_reported": "S1: ignore",
    "excl_reported": "S2: corrected",
    "excl_floored_reported": "S3: + floor",
}
SLIDE_SCEN_ORDER = ["S1: ignore", "S2: corrected", "S3: + floor"]
SLIDE_HEADLINE_FORMULA = "sales_employees_destmnedds"
SLIDE_KEY_ORDER = ["ignorant_reported", "excl_reported", "excl_floored_reported"]
SLIDE_SCEN_DESC = {
    "ignorant_reported": "Resources ignored\n(current system)",
    "excl_reported": "Resource profits\nexcluded",
    "excl_floored_reported": "+ Minimum\nroyalty floor",
}
# Which scenarios each per-country slide shows. South Sudan and Chad
# illustrate the effect of EXCLUDING resource profits, so they show baseline
# vs resources-excluded only (the floor cases are Guinea and Madagascar).
SLIDE_SCENARIOS = {
    "SSD": ["ignorant_reported", "excl_reported"],
    "TCD": ["ignorant_reported", "excl_reported"],
}
SLIDE_METRICS = [
    ("delta_taxable_profits_musd", "Change in taxable profit\n(taxing rights, $m)"),
    (
        "delta_total_gvt_revenue_recCIT_forgETR_musd",
        "Change in tax revenue\ngains×CIT / losses×ETR ($m)",
    ),
    (
        "delta_total_gvt_revenue_recETR_forgETR_musd",
        "Change in tax revenue\nboth×ETR ($m)",
    ),
]
SLIDE_FORMULAS = [
    ("sales_employees", "Sales + employees"),
    ("ccctb", "CCCTB"),
    ("three_factors", "Three-factor"),
    ("double_weighted_sales", "Double-weighted sales"),
]
SLIDE_COLOURS = list(_sc.FORMULA_COLOURS[:4])


def fig_country_slide(df, iso, name, role, figures_dir):
    """One slide per country: 3 metric rows, x = scenarios, 4 formula bars."""
    sub = df[df["iso_partner"] == iso]
    scen_keys = SLIDE_SCENARIOS.get(iso, SLIDE_KEY_ORDER)
    xlabels = [SLIDE_SCEN_DESC[k] for k in scen_keys]
    fkeys = [f for f, _ in SLIDE_FORMULAS]
    flabels = [lab for _, lab in SLIDE_FORMULAS]
    n_f = len(fkeys)
    bar_w = 0.8 / n_f
    x = np.arange(len(scen_keys))
    fig, axes = plt.subplots(len(SLIDE_METRICS), 1, figsize=(9, 10), sharex=True)
    for r, (mcol, mlabel) in enumerate(SLIDE_METRICS):
        ax = axes[r]
        piv = sub.pivot_table(
            index="scenario", columns="formula_name", values=mcol, aggfunc="first"
        ).reindex(scen_keys)
        for i, fk in enumerate(fkeys):
            if fk not in piv.columns:
                continue
            vals = piv[fk].values
            offset = (i - (n_f - 1) / 2) * bar_w
            ax.bar(
                x + offset,
                vals,
                width=bar_w,
                color=SLIDE_COLOURS[i],
                label=flabels[i] if r == 0 else None,
            )
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_ylabel(mlabel, fontsize=9)
        ax.margins(y=0.18)
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(xlabels, fontsize=9)
    axes[0].legend(fontsize=8, ncol=2, loc="best", framealpha=0.85)
    fig.suptitle(
        f"{name} ({iso}) — {role}\nraw (reported-only) data, 2016–2022, four formulas",
        fontsize=12,
    )
    note = {
        "TCD": "Chad already wins taxing rights under most formulas even before the correction; excluding resource-related profits lifts all of them.",
        "SSD": "South Sudan gains taxing rights once resource-related profits are excluded (right group vs left), with proportional tax-revenue gains under both rate specifications; its effective tax rate is ~20-30%.",
        "GIN": "Unitary taxation alone gives Guinea almost nothing (its taxing-rights change is slightly negative); the minimum-royalty floor delivers the revenue — the hatched add-on dwarfs the UT effect.",
        "MDG": "Madagascar already wins on taxing rights under unitary taxation; the minimum-royalty floor adds roughly two-thirds more revenue on top.",
    }.get(iso, "")
    fig.text(
        0.5,
        0.005,
        note,
        ha="center",
        va="bottom",
        fontsize=8,
        wrap=True,
        color="#444444",
    )
    plt.tight_layout(rect=[0, 0.04, 1, 0.93])
    fname = f"fig_country_example_{iso}.png"
    plt.savefig(figures_dir / fname, dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def main_slides():
    tables_dir, figures_dir = output_dirs(REPORT_TOPIC)
    summary_csv = tables_dir / "three_scenario_summary_long_2016_22.csv"
    if not summary_csv.exists():
        print(f"  [skip slides] {summary_csv} missing — run main_figures first")
        return
    df = pd.read_csv(summary_csv)
    df["scen"] = df["scenario"].map(SLIDE_SCEN)
    df = df[df["iso_partner"].isin([i for i, _, _ in SLIDE_EXAMPLES])].copy()

    # Table: all formulas, key metrics, wide over scenarios.
    metric_cols = [m for m, _ in SLIDE_METRICS]
    long = df.melt(
        id_vars=["iso_partner", "partner_jurisdiction", "formula_name", "scen"],
        value_vars=metric_cols,
        var_name="metric",
        value_name="musd",
    )
    tbl = long.pivot_table(
        index=["iso_partner", "partner_jurisdiction", "formula_name", "metric"],
        columns="scen",
        values="musd",
        aggfunc="first",
    ).reset_index()
    tbl = tbl[
        ["iso_partner", "partner_jurisdiction", "formula_name", "metric"]
        + SLIDE_SCEN_ORDER
    ]
    _csv = tables_dir / "country_examples_2016_22.csv"
    try:
        tbl.to_csv(_csv, index=False)
        print(f"  wrote {_csv}")
    except PermissionError:
        print(
            f"  [warn] could not write {_csv.name} (open in Excel / locked) — "
            f"skipping table, continuing with figures"
        )

    # Headline overview: metrics (rows) x countries (cols), green/red bars.
    hl = df[df["formula_name"] == SLIDE_HEADLINE_FORMULA]
    fig, axes = plt.subplots(
        len(SLIDE_METRICS),
        len(SLIDE_EXAMPLES),
        figsize=(3.3 + 3.3 * len(SLIDE_EXAMPLES), 9.5),
        sharex=True,
    )
    for r, (mcol, mlabel) in enumerate(SLIDE_METRICS):
        for c, (iso, name, role) in enumerate(SLIDE_EXAMPLES):
            ax = axes[r, c]
            sub = (
                hl[hl["iso_partner"] == iso].set_index("scen").reindex(SLIDE_SCEN_ORDER)
            )
            vals = sub[mcol].values
            colors = [POSITIVE if (v is not None and v > 0) else NEGATIVE for v in vals]
            ax.bar(SLIDE_SCEN_ORDER, vals, color=colors, width=0.66)
            ax.axhline(0, color="grey", lw=0.6)
            for xx, v in enumerate(vals):
                if pd.notna(v):
                    ax.annotate(
                        f"{v:+,.0f}",
                        (xx, v),
                        ha="center",
                        va="bottom" if v >= 0 else "top",
                        fontsize=8,
                    )
            if r == 0:
                ax.set_title(f"{name} ({iso})\n[{role}]", fontsize=10)
            if c == 0:
                ax.set_ylabel(mlabel, fontsize=9)
            ax.margins(y=0.22)
            ax.tick_params(axis="x", labelsize=8)
    fig.suptitle(
        "Low-income country examples — employees + destination-based sales formula, raw (reported-only) data, 2016–2022\n"
        "green = country gains, red = country loses",
        fontsize=12,
    )
    note = (
        "Chad and South Sudan win once resource profits are excluded (S1->S2); Guinea gains only once the minimum-royalty floor is added, which also lifts Madagascar's gain further (S2->S3).  "
        "Tax-revenue gains move with the change in taxable profit under both rate specifications."
    )
    fig.text(
        0.5,
        0.005,
        note,
        ha="center",
        va="bottom",
        fontsize=7.5,
        wrap=True,
        color="#444444",
    )
    plt.tight_layout(rect=[0, 0.05, 1, 0.93])
    plt.savefig(figures_dir / "fig_country_examples.png", dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / 'fig_country_examples.png'}")

    for iso, name, role in SLIDE_EXAMPLES:
        fig_country_slide(df, iso, name, role, figures_dir)


# %% MARK: 7. Main
def main():
    main_figures()
    main_detail()
    main_paper()
    main_slides()
    print("\nDone.")


if __name__ == "__main__":
    main()
