# %%
"""
Focused three-scenario figure deliverable for the SOTJ profit-shifting estimates.

This is a trimmed, self-contained view built on top of the machinery in
`8_five_scenario_report.py` (its `build_summary` does the heavy lifting:
Change in taxable profits, Change in tax revenue under each rate mode, the IGF-ATAF floor
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
  fig1  Change in taxable profits        (% of pre-UT reported profit base)
  fig2  Change in tax revenue, both ETR  (% of current total tax revenue)
  fig3  Change in tax revenue, gains×CIT / losses×ETR (% of current total tax revenue)

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
from _brand import apply_tjn_style, PALETTE, HATCH_CYCLE

apply_tjn_style()

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
_safe_pct_positive_base = _s8._safe_pct_positive_base
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

# Per-formula three-scenario comparison covers ALL formula families (display order).
# The grouped-bar per-scenario figures keep the original 4 families; these extra
# sales families are loaded only so the per-formula comparison can cover them too.
SCEN_COMPARE_FORMULAS = [
    ("sales_employees", "Sales + employees"),
    ("sales_employees_destcombined", "Employees + destination-based sales"),
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
        (k, l) for k, l in SCEN_COMPARE_FORMULAS if k not in _have]
    SCENARIOS_EXT.append(_s2)

# Standard footnote on every figure that carries a % panel.
PCT_NOTE = (
    "Percentages are omitted (no bar) where the denominator is not strictly positive. "
    "Change in taxable profit % is relative to the pre-UT reported profit base; Change in tax revenue % "
    "is relative to the country's current total tax revenue. A percentage against a "
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
# set by a caller (e.g. 9c builds these figures on the gravity-IMPUTED sample and
# sets these so the heading/notes flag it). Empty by default → the reported-only
# deliverable is unchanged.
DATA_BANNER = ""   # short tag appended to the bold heading
DATA_NOTE = ""     # longer explanation appended to the footnote


def _banner_suffix():
    return f"   [{DATA_BANNER}]" if DATA_BANNER else ""


# ─── Aggregate the per-country summary to income groups ───────────────────────
def build_by_income(summary):
    """Replicates the income-group aggregation in 8_five_scenario_report.write_tables
    so percentages re-derive correctly as Σnumerator / Σdenominator."""
    sub = summary[~summary["iso_partner"].isin(DATA_QUALITY_EXCLUSIONS)]
    # Rate modes absent from the run (e.g. CIT-CIT, dropped from the MINIMAL
    # grid) have no columns — aggregate only what exists.
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

    # Revenue % panels (fig 2/3): income-group % against the CORPORATE tax the MNEs
    # currently pay. NUMERATOR = the SAME full group sum shown in the USD panel
    # (all countries), so the two panels always order identically; DENOMINATOR =
    # Σ(cash tax paid) over the (country, year) cells that HAVE cash-tax data
    # (inflation-corrected; stashed in _s8.GROUP_CASHTAX_MUSD per scenario, so the
    # "resources ignored" % is still measured against its own, uncorrected tax).
    # (The earlier construction summed the numerator over the restricted cash-tax
    # cell set only — internally clean, but its composition differed from the USD
    # panel and could FLIP bar orderings between the panels.) delta_total adds the
    # floor/five-factor addon on the same denominator (0 for non-floored).
    # Taxable-profit % is unchanged.
    gc = getattr(_s8, "GROUP_CASHTAX_MUSD", None)
    if gc is not None and not gc.empty:
        _mk = ["scenario", "formula_name", "wb_income_group"]
        by_inc = by_inc.merge(gc, on=_mk, how="left")
        _cash = pd.to_numeric(by_inc.get("grp_cashtax_musd"), errors="coerce")
        for suffix in _s8.RATE_SUFFIX.values():
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
    # but no base). The former positive-base SUBSAMPLE convention (numerator
    # and denominator both restricted) sign-flipped in the gravity sample,
    # where negative-base countries carry much of the group's gain (user
    # 2026-07-13: 'USD values are positive but % negative').
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
            ["scenario", "formula_name", "wb_income_group"],
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
            "scenario", "formula_name", "wb_income_group",
            "delta_taxable_profits_pct_posbase", "n_countries_posbase",
        ]],
        on=["scenario", "formula_name", "wb_income_group"], how="left",
    )
    return by_inc


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
                  is_pct=False, usd_decimals=1):
    """Grouped bars: income groups on x, one bar per formula. If addon_pivot is
    given, the top (hatched) layer = addon, base (solid) = pivot − addon.
    Bars are data-labelled (1-dp USD / whole-number %)."""
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
        [INCOME_GROUP_LABELS.get(g, g) for g in pivot.index],
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
        # Percentage panel: same add-on expressed as % of current total tax
        # revenue (the panel's denominator), so the hatched share matches.
        addon_musd = _pivot(by_inc, scenario, addon_col, formula_keys)
        rev_usd = _pivot(by_inc, scenario, "tax_revenue_current_usd", formula_keys)
        addon_pivot_pct = addon_musd * 1e6 / rev_usd * 100

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
            "gains & losses valued at average ETR"
        ),
        abs_col="delta_total_gvt_revenue_recETR_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of current total tax revenue",
        addon_col="resource_capture_addon_musd",
        extra_note=floor_note,
    )

    # Fig 3 — Change in tax revenue, UT gains at statutory CIT, losses at ETR
    make_figure(
        by_inc, scenario, figures_dir,
        fname=f"scenario{n}_{key}_3_delta_tax_revenue_gainsCIT_lossesETR.png",
        suptitle=(
            f"Scenario {n}: {label} — Change in tax revenue by income group ({WINDOW_LABEL})\n"
            "UT gains valued at statutory CIT, losses at average ETR"
        ),
        abs_col="delta_total_gvt_revenue_recCIT_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of current total tax revenue",
        addon_col="resource_capture_addon_musd",
        extra_note=floor_note,
    )


# ─── Per-formula scenario comparison (e.g. CCCTB) ─────────────────────────────
SCEN_SHORT = {
    "ignorant_reported": "S1: resources ignored",
    "excl_reported": "S2: corrected for capture",
    "excl_floored_reported": "S3: + min. royalty floor",
}
SCEN_COLOURS = list(PALETTE[:3])


def _scenario_comparison_panel(ax, sub, scen_keys, value_col, ylabel, is_pct,
                               with_addon, usd_decimals=1):
    """One panel: x = income groups, grouped bars = scenarios. If with_addon,
    the floored scenario's bar is split into a solid UT base + hatched
    minimum-royalty floor add-on (the add-on is nonzero only for that scenario)."""
    piv = sub.pivot_table(index="wb_income_group", columns="scenario",
                          values=value_col, aggfunc="first")
    piv = piv.reindex([g for g in INCOME_GROUP_ORDER if g in piv.index])
    groups = list(piv.index)
    x = np.arange(len(groups))
    n_s = len(scen_keys)
    bw = 0.8 / max(n_s, 1)
    addon = None
    if with_addon:
        if is_pct:
            # Addon in % POINTS on the SAME denominator as the bar values: the
            # total-% column already includes the royalty add-on (build_by_income
            # adds it as % of the group's corporate cash tax), so the hatched
            # slice = total % − tax-only %. (The old computation divided the USD
            # add-on by tax_revenue_current_usd — TOTAL government tax revenue —
            # a different, far larger denominator than the % bars use.)
            tax_col = value_col.replace("delta_total_gvt_revenue_", "delta_tax_revenue_")
            if tax_col != value_col and tax_col in sub.columns:
                t = sub.pivot_table(index="wb_income_group", columns="scenario",
                                    values=tax_col, aggfunc="first").reindex(groups)
                addon = (piv - t).fillna(0.0)
        else:
            a = sub.pivot_table(index="wb_income_group", columns="scenario",
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
    ax.set_xticklabels([INCOME_GROUP_LABELS.get(g, g) for g in groups], fontsize=9)
    ax.set_ylabel(ylabel)


def _scenario_comparison_fig(by_inc, formula_key, formula_label, figures_dir,
                             fname, title, subtitle, abs_col, pct_col,
                             abs_ylabel, pct_ylabel, with_addon, note):
    """A 2-panel (absolute USD bn + %) scenario comparison for one formula."""
    sub = by_inc[by_inc["formula_name"] == formula_key]
    scen_keys = [s["key"] for s in SCENARIOS]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8))
    _scenario_comparison_panel(axes[0], sub, scen_keys, abs_col, abs_ylabel,
                               False, with_addon)
    _scenario_comparison_panel(axes[1], sub, scen_keys, pct_col, pct_ylabel,
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


def make_formula_scenario_comparison(by_inc, formula_key, formula_label, figures_dir):
    """For a SINGLE formula, three scenario-comparison figures (each absolute +
    %): (1) tax base, (2) tax revenue valued ETR/ETR, (3) tax revenue valued
    gains-CIT / losses-ETR. x = income groups, grouped bars = the three scenarios."""
    base = f"{formula_label}"
    # 1 — tax base
    _scenario_comparison_fig(
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
    _scenario_comparison_fig(
        by_inc, formula_key, formula_label, figures_dir,
        fname=f"formula_comparison_{formula_key}_2_revenue_bothETR.png",
        title=f"{base}: Change in tax revenue by income group ({WINDOW_LABEL})",
        subtitle="gains & losses valued at average ETR",
        abs_col="delta_total_gvt_revenue_recETR_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of current total tax revenue",
        with_addon=True, note=FLOOR_NOTE + " " + PCT_NOTE,
    )
    # 3 — revenue, gains at statutory CIT, losses at ETR
    _scenario_comparison_fig(
        by_inc, formula_key, formula_label, figures_dir,
        fname=f"formula_comparison_{formula_key}_3_revenue_gainsCIT.png",
        title=f"{base}: Change in tax revenue by income group ({WINDOW_LABEL})",
        subtitle="UT gains valued at statutory CIT, losses at average ETR",
        abs_col="delta_total_gvt_revenue_recCIT_forgETR_musd",
        pct_col="delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
        abs_ylabel="Change in tax revenue (USD bn)",
        pct_ylabel="% of current total tax revenue",
        with_addon=True, note=FLOOR_NOTE + " " + PCT_NOTE,
    )


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    tables_dir, figures_dir = output_dirs(REPORT_TOPIC)

    print(f"Building three-scenario summary ({WINDOW_LABEL}, reported-only, average ETR)…")
    summary = build_summary(YEARS, SCENARIOS_EXT)
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

    # Per-formula three-scenario comparison — ALL formula families.
    print("\nFormula scenario comparison (all formulas):")
    present = set(by_inc["formula_name"].unique())
    for fkey, flabel in SCEN_COMPARE_FORMULAS:
        if fkey in present:
            make_formula_scenario_comparison(by_inc, fkey, flabel, figures_dir)
        else:
            print(f"  (skip {fkey} — not in summary)")

    print("\nDone.")


if __name__ == "__main__":
    main()
