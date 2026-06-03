# %%
"""
Focused three-scenario figure deliverable for the SOTJ profit-shifting estimates.

This is a trimmed, self-contained view built on top of the machinery in
`8_five_scenario_report.py` (its `build_summary` does the heavy lifting:
Δ taxable profits, Δ tax revenue under each rate mode, the IGF-ATAF floor
add-on for scenario 3, and all the pct denominators). Here we restrict to
exactly what was requested:

  * THREE scenarios, all on the RAW (reported-only, is_distributed == 0) data —
    no disaggregation imputation:
       1. Resources ignored      — disaggregated baseline
       2. Resources excluded      — excl_resource
       3. Resources excluded + minimum-royalty floor — excl_resource_floored
  * ETR family: AVERAGE only.
  * Two rate modes for the revenue figures:
       - both gains & losses at ETR              (loss_etr_gain_etr → recETR_forgETR)
       - UT gains at statutory CIT, losses at ETR (loss_cit_gain_etr → recCIT_forgETR)
  * Window: 2016–2022, summed.
  * All four formula families (SOTJ employees+payroll, CCCTB, three-factor,
    double-weighted sales) shown as bars, broken down by World Bank income group.

THREE figures per scenario, each with a USD-billions panel (left) and a
percentage panel (right):
  fig1  Δ taxable profits        (% of pre-UT reported profit base)
  fig2  Δ tax revenue, both ETR  (% of current total tax revenue)
  fig3  Δ tax revenue, gains×CIT / losses×ETR (% of current total tax revenue)

For scenario 3 the revenue figures plot total government revenue =
UT-derived revenue + minimum-royalty floor add-on; the add-on portion is
hatched so the split is visible.

Outputs to output/three_scenarios/{tables,figures}/.

Usage: python 9_three_scenario_figures.py
"""

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

# ── Import the report machinery from 8_five_scenario_report.py. The module
# name starts with a digit, so a plain `import` is impossible — load it by path.
_spec = importlib.util.spec_from_file_location(
    "_five_scenario_report",
    str(Path(__file__).resolve().parent / "8_five_scenario_report.py"),
)
_s8 = importlib.util.module_from_spec(_spec)
sys.modules["_five_scenario_report"] = _s8
_spec.loader.exec_module(_s8)

build_summary = _s8.build_summary
SUM_MUSD_COLS = _s8.SUM_MUSD_COLS
SUM_DENOM_COLS = _s8.SUM_DENOM_COLS
_add_pct_columns = _s8._add_pct_columns
INCOME_GROUP_ORDER = _s8.INCOME_GROUP_ORDER
INCOME_GROUP_LABELS = _s8.INCOME_GROUP_LABELS
FORMULA_COLOURS = _s8.FORMULA_COLOURS
DATA_QUALITY_EXCLUSIONS = _s8.DATA_QUALITY_EXCLUSIONS

REPORT_TOPIC = "three_scenarios"
YEARS = list(range(2016, 2023))  # 2016–2022 inclusive
WINDOW_LABEL = "2016–2022"

# The three reported-only scenarios, in display order.
SCENARIOS = [
    s
    for key in ("ignorant_reported", "excl_reported", "excl_floored_reported")
    for s in _s8.SCENARIOS_REPORTED
    if s["key"] == key
]
FLOORED_KEY = "excl_floored_reported"

# Standard footnote on every figure that carries a % panel.
PCT_NOTE = (
    "Percentages are omitted (no bar) where the denominator is not strictly positive. "
    "Δ taxable profit % is relative to the pre-UT reported profit base; Δ tax revenue % "
    "is relative to the country's current total tax revenue. A percentage against a "
    "non-positive base would flip sign and mislead, so it is left blank by design."
)
FLOOR_NOTE = (
    "Scenario 3 revenue = UT-derived revenue + IGF-ATAF minimum-royalty floor add-on "
    "(hatched portion). The floor is a hypothetical minimum royalty, counted as a "
    "separate government-revenue stream on top of the UT yield."
)


# ─── Aggregate the per-country summary to income groups ───────────────────────
def build_by_income(summary):
    """Replicates the income-group aggregation in 8_five_scenario_report.write_tables
    so percentages re-derive correctly as Σnumerator / Σdenominator."""
    sub = summary[~summary["iso_partner"].isin(DATA_QUALITY_EXCLUSIONS)]
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
            {c: "sum" for c in SUM_MUSD_COLS + SUM_DENOM_COLS}
            | {"iso_partner": "nunique"}
        )
        .rename(columns={"iso_partner": "n_countries"})
    )
    return _add_pct_columns(by_inc)


# ─── Plotting ─────────────────────────────────────────────────────────────────
def _pivot(by_inc, scenario, value_col, formula_keys):
    sub = by_inc[by_inc["scenario"] == scenario["key"]]
    pivot = sub.pivot_table(
        index="wb_income_group",
        columns="formula_name",
        values=value_col,
        aggfunc="first",
    )
    pivot = pivot.reindex([g for g in INCOME_GROUP_ORDER if g in pivot.index])
    pivot = pivot[[f for f in formula_keys if f in pivot.columns]]
    return pivot


def _grouped_bars(ax, pivot, formula_labels, colors, ylabel, title, addon_pivot=None):
    """Grouped bars: income groups on x, one bar per formula. If addon_pivot is
    given, the top (hatched) layer = addon, base (solid) = pivot − addon."""
    if pivot.empty or pivot.dropna(how="all").empty:
        ax.set_axis_off()
        ax.set_title(f"{title}\n(no data)", fontsize=9)
        return
    n_formulas = len(pivot.columns)
    n_groups = len(pivot.index)
    bar_width = 0.82 / max(n_formulas, 1)
    x = np.arange(n_groups)
    if addon_pivot is not None:
        addon = addon_pivot.reindex(index=pivot.index, columns=pivot.columns).fillna(0)
    else:
        addon = None
    for i, col in enumerate(pivot.columns):
        offset = (i - (n_formulas - 1) / 2) * bar_width
        vals = pivot[col].values
        if addon is None:
            ax.bar(x + offset, vals, width=bar_width, color=colors[i])
        else:
            addon_vals = addon[col].values
            base_vals = vals - addon_vals
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
    ax.set_xticklabels(
        [INCOME_GROUP_LABELS.get(g, g) for g in pivot.index],
        rotation=0,
        ha="center",
        fontsize=9,
    )
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=10)
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[i]) for i in range(n_formulas)]
    labels = list(formula_labels[:n_formulas])
    if addon is not None and addon.abs().to_numpy().sum() > 0:
        handles.append(
            plt.Rectangle((0, 0), 1, 1, facecolor="white", hatch="///", edgecolor="black")
        )
        labels.append("Min.-royalty floor add-on")
    ax.legend(handles, labels, fontsize=8, loc="best", framealpha=0.85)


def make_figure(
    by_inc, scenario, figures_dir, fname, suptitle, abs_col, pct_col,
    abs_ylabel, pct_ylabel, addon_col=None, extra_note=None,
):
    formula_keys = [f for f, _ in scenario["formulas"]]
    formula_labels = [lab for _, lab in scenario["formulas"]]
    colors = FORMULA_COLOURS[: len(formula_keys)]

    pivot_abs = _pivot(by_inc, scenario, abs_col, formula_keys)
    pivot_pct = _pivot(by_inc, scenario, pct_col, formula_keys)
    addon_pivot = None
    if addon_col is not None and scenario["key"] == FLOORED_KEY:
        addon_pivot = _pivot(by_inc, scenario, addon_col, formula_keys) / 1e3

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    _grouped_bars(
        axes[0], pivot_abs / 1e3, formula_labels, colors,
        ylabel=abs_ylabel, title="Absolute (USD bn)", addon_pivot=addon_pivot,
    )
    _grouped_bars(
        axes[1], pivot_pct, formula_labels, colors,
        ylabel=pct_ylabel, title="As %",
    )
    fig.suptitle(suptitle, fontsize=12)

    note = PCT_NOTE + ("\n" + extra_note if extra_note else "")
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=7.5, wrap=True,
             color="#444444")
    plt.tight_layout(rect=[0, 0.10, 1, 0.95])
    plt.savefig(figures_dir / fname, dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def make_scenario_figures(by_inc, scenario, figures_dir, n):
    key = scenario["key"]
    label = scenario["label"]
    floor_note = FLOOR_NOTE if key == FLOORED_KEY else None

    # Fig 1 — Δ taxable profits
    make_figure(
        by_inc, scenario, figures_dir,
        fname=f"scenario{n}_{key}_1_delta_taxable_profits.png",
        suptitle=f"Scenario {n}: {label} — Δ taxable profits by income group ({WINDOW_LABEL})",
        abs_col="delta_taxable_profits_musd",
        pct_col="delta_taxable_profits_pct",
        abs_ylabel="Δ taxable profit (USD bn)",
        pct_ylabel="% of pre-UT reported profit base",
    )

    # Fig 2 — Δ tax revenue, both gains & losses at ETR
    make_figure(
        by_inc, scenario, figures_dir,
        fname=f"scenario{n}_{key}_2_delta_tax_revenue_bothETR.png",
        suptitle=(
            f"Scenario {n}: {label} — Δ tax revenue by income group ({WINDOW_LABEL})\n"
            "gains & losses valued at average ETR"
        ),
        abs_col="delta_total_gvt_revenue_recETR_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
        abs_ylabel="Δ tax revenue (USD bn)",
        pct_ylabel="% of current total tax revenue",
        addon_col="resource_capture_addon_musd",
        extra_note=floor_note,
    )

    # Fig 3 — Δ tax revenue, UT gains at statutory CIT, losses at ETR
    make_figure(
        by_inc, scenario, figures_dir,
        fname=f"scenario{n}_{key}_3_delta_tax_revenue_gainsCIT_lossesETR.png",
        suptitle=(
            f"Scenario {n}: {label} — Δ tax revenue by income group ({WINDOW_LABEL})\n"
            "UT gains valued at statutory CIT, losses at average ETR"
        ),
        abs_col="delta_total_gvt_revenue_recCIT_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
        abs_ylabel="Δ tax revenue (USD bn)",
        pct_ylabel="% of current total tax revenue",
        addon_col="resource_capture_addon_musd",
        extra_note=floor_note,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    tables_dir, figures_dir = output_dirs(REPORT_TOPIC)

    print(f"Building three-scenario summary ({WINDOW_LABEL}, reported-only, average ETR)…")
    summary = build_summary(YEARS, SCENARIOS)
    if summary is None or summary.empty:
        raise SystemExit("No data returned by build_summary — check UT outputs exist.")

    by_inc = build_by_income(summary)

    summary.to_csv(tables_dir / "three_scenario_summary_long_2016_22.csv", index=False)
    by_inc.to_csv(tables_dir / "three_scenario_by_income_group_2016_22.csv", index=False)
    print(f"  wrote {tables_dir / 'three_scenario_summary_long_2016_22.csv'}")
    print(f"  wrote {tables_dir / 'three_scenario_by_income_group_2016_22.csv'}")

    for n, scenario in enumerate(SCENARIOS, start=1):
        print(f"\nScenario {n}: {scenario['label']} [{scenario['key']}]")
        make_scenario_figures(by_inc, scenario, figures_dir, n)

    print("\nDone.")


if __name__ == "__main__":
    main()
