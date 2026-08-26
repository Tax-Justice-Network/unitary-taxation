# %%
"""
7d — Factor incidence: who gains from each apportionment factor.

Estimates, by income group, the change in tax revenue if multinational profits
were apportioned by each single factor alone — employees, payroll, tangible
assets and destination-based sales. Because the formulary allocation is linear
in the formula weights, these pure single-factor columns are recovered by least
squares across the formula variants that were actually run, and any real
formula's outcome is approximately their weight-average (the figure doubles as a
"build your own formula" explainer). Heavier employment weighting shifts taxing
rights toward labour-intensive economies, while profit-shifting hubs lose under
every factor (the argument of Loretz, 2026, made concrete on this data).

Headline specification: reported-only sample, resources excluded, employees + destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at statutory CIT and losses at ETR, per-year average over 2016–2022 (2020 excluded), constant 2025 US$.

Exhibit script — consumes the script-6 estimation summaries. Produces Figure 8
(single-factor incidence by income group) + region twin figB (Appendix B).

Reads:
  output/estimates/reported_only/2_resources_excluded/tables/excl_resource/country_estimates__*.csv — per-formula per-country revenue (script 5/6)

Writes:
  output/paper/main_text/fig08_*.png/.pdf                              — Figure 8 (factor incidence)
  output/analysis/factor_incidence/…                                  — single-factor revenue-effect tables

Usage:
  python 7d_factor_incidence.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import glob
import os
import sys

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import config
from config import output_dirs
import _exhibit_helpers as _eh
from _brand import apply_tjn_style, PALETTE, HATCH_CYCLE, DIVERGING_GAIN_LOSS

apply_tjn_style()

# %% MARK: 2. Config and constants
DEFL = config.deflator_to_base()
YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
MDIR = os.path.join(str(config.estimates_dir("reported_only", "excl_resource")),
                    "tables", "excl_resource")

FACTORS_ALL = ["Employees", "Payroll", "Tangible\nassets",
               "Sales\n(origin)", "Sales\n(destination)"]
# weights over [employees, payroll, assets, origin sales, destination sales]
WEIGHTS = {
    "employees_payroll":             [0.5, 0.5, 0.0, 0.0, 0.0],
    "sales_employees":               [0.5, 0.0, 0.0, 0.5, 0.0],
    "ccctb":                         [1/6, 1/6, 1/3, 1/3, 0.0],
    "three_factors":                 [1/3, 0.0, 1/3, 1/3, 0.0],
    "double_weighted_sales":         [0.25, 0.0, 0.25, 0.5, 0.0],
    # Destination leg = the headline measure (all-MNE sales + MNE share of
    # BaTIS deliverable imports).
    "sales_employees_destmnedds":       [0.5, 0.0, 0.0, 0.0, 0.5],
    "ccctb_destmnedds":                 [1/6, 1/6, 1/3, 0.0, 1/3],
    "three_factors_destmnedds":         [1/3, 0.0, 1/3, 0.0, 1/3],
    "double_weighted_sales_destmnedds": [0.25, 0.0, 0.25, 0.0, 0.5],
}
SHOW = ["Employees", "Payroll", "Tangible\nassets", "Sales\n(destination)"]
IG_ORDER = ["low_income", "lower_middle_income", "upper_middle_income",
            "high_income", "tax_haven"]
IG_LAB = {"low_income": "Low income", "lower_middle_income": "Lower middle income",
          "upper_middle_income": "Upper middle income", "high_income": "High income",
          "tax_haven": "Tax havens"}   # display label
# Parallel geographic grouping (region_tjn) for the region-breakdown matrix,
# using the paper's coarser merged regions (Asia & Oceania; Latin America &
# Caribbean) — same grouping as the other Appendix-B figures.
REGION_ORDER = list(_eh.REGION_ORDER)


# %% MARK: 3. Build factor matrices
def build_matrices(group_col="wb_income_group", group_order=IG_ORDER):
    rows, wmat, base = [], [], None
    for fk, w in WEIGHTS.items():
        fs = [f for f in glob.glob(os.path.join(MDIR, "country_estimates__*.csv"))
              if f"__{fk}__" in os.path.basename(f) and "etrdef_domfor" in f
              and "loss_cit_gain_etr" in f and "etrmax_inf" in f]
        if not fs:
            print(f"  [skip] no country_estimates for {fk}")
            continue
        d = pd.read_csv(fs[0], low_memory=False)
        d = d[d.year.isin(YEARS)].copy()
        if group_col == "region_tjn":   # coarser merged paper regions
            d[group_col] = d[group_col].replace(_eh.REGION_MERGE)
        f_defl = d.year.map(DEFL)
        # Δ tax revenue (net, ETR-CIT valuation; MUSD -> deflated).
        d["v"] = pd.to_numeric(d.revenue_gain_from_ut, errors="coerce") * f_defl
        g = d.groupby(group_col).v.sum() / 1e3 / len(YEARS)
        rows.append(g.reindex(group_order).values)
        wmat.append(w)
        if base is None:
            # Denominator = corporate cash tax currently paid by the group's
            # reporting MNEs (matches the paper's revenue % panels).
            d["b"] = pd.to_numeric(d.current_tax_paid_cash_musd,
                                   errors="coerce") * f_defl
            base = (d.groupby(group_col).b.sum() / 1e3 / len(YEARS)
                    ).reindex(group_order)
    Y, W = np.array(rows), np.array(wmat)
    beta, _, rank, _ = np.linalg.lstsq(W, Y, rcond=None)
    fit = W @ beta
    r2 = 1 - ((Y - fit) ** 2).sum() / ((Y - Y.mean(axis=0)) ** 2).sum()
    print(f"[{group_col}] linearity fit R2 = {r2:.4f} (rank {rank}, {len(wmat)} formulas)")
    B = pd.DataFrame(beta, index=FACTORS_ALL, columns=group_order)
    P = B.div(base, axis=1) * 100
    return B.loc[SHOW], P.loc[SHOW]


# %% MARK: 4. Figure panels
_CMAP = LinearSegmentedColormap.from_list("tjn_gainloss", DIVERGING_GAIN_LOSS)


def _heat_panel(ax, M, title, fmt, order=IG_ORDER, labels=IG_LAB):
    """Green = gain, red = loss; shading scaled WITHIN each group row (income
    group by default, world region for the Appendix-B twin), so every row shows
    its factor ranking instead of being washed out by the panel's single largest
    value. Colour-blind redundancy: every cell prints the signed value, so
    polarity never rides on the hue alone. The row's largest effect is bold."""
    V = M.values.T.astype(float)          # rows = groups, cols = factors
    row_max = np.maximum(np.abs(V).max(axis=1, keepdims=True), 1e-9)
    T = V / row_max                       # per-row scaling to [-1, 1]
    ax.imshow(T, cmap=_CMAP, vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(SHOW)), SHOW, fontsize=9)
    ax.set_yticks(range(len(order)), [labels[g] for g in order], fontsize=9)
    # white separators between cells; kill the style's y-grid, which would
    # otherwise draw streaks across the cells
    ax.set_xticks(np.arange(0.5, len(SHOW) - 1), minor=True)
    ax.set_yticks(np.arange(0.5, len(order) - 1), minor=True)
    ax.grid(which="major", visible=False)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(len(SHOW)):
        for j in range(len(order)):
            v, t = M.values[i, j], T[j, i]
            ax.text(i, j, fmt(v), ha="center", va="center", fontsize=10,
                    color="white" if abs(t) > 0.75 else "#222222",
                    fontweight="bold" if abs(t) > 0.999 else "normal")
    ax.set_title(title, fontsize=11, loc="left")


def _bar_panel(ax, M, ylabel, order=IG_ORDER, labels=IG_LAB):
    x = np.arange(len(SHOW))
    n = len(order)
    bw = 0.82 / n
    for j, g in enumerate(order):
        ax.bar(x + (j - (n - 1) / 2) * bw, M[g].values, width=bw,
               color=PALETTE[j % len(PALETTE)],
               hatch=HATCH_CYCLE[j % len(HATCH_CYCLE)],
               edgecolor="white", linewidth=0.3, label=labels[g])
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_xticks(x, SHOW, fontsize=9)
    ax.set_ylabel(ylabel)


# %% MARK: 5. Main and run
def main():
    tables_dir, figures_dir = output_dirs("deliverables/factor_incidence")
    # Paper-figure copies live with fig01-fig11; the heatmap occupies the
    # fig10 slot (7b writes no Fig 10).
    paper_dir = str(config.output_dirs("paper/main_text")[1])
    B, P = build_matrices()

    out = pd.concat({"usd_bn_per_year": B, "pct_of_current_tax_paid": P})
    out.index.names = ["unit", "factor"]
    out.to_csv(tables_dir / "factor_incidence_matrix.csv")

    # Region-breakdown counterpart (factor × geographic region).
    Br, Pr = build_matrices("region_tjn", REGION_ORDER)
    out_r = pd.concat({"usd_bn_per_year": Br, "pct_of_current_tax_paid": Pr})
    out_r.index.names = ["unit", "factor"]
    out_r.to_csv(tables_dir / "factor_incidence_matrix_by_region.csv")
    print(f"  wrote {tables_dir / 'factor_incidence_matrix_by_region.csv'}")

    T_ABS = "Change in tax revenue (USD bn per year)"
    T_PCT = "% of corporate tax currently paid"

    # Heatmap (panel titles only; the paper caption carries the figure title).
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 4.8))
    _heat_panel(axes[0], B, T_ABS, lambda v: f"{v:+.0f}")
    _heat_panel(axes[1], P, T_PCT, lambda v: f"{v:+.0f}%")
    axes[1].set_yticks([])
    plt.tight_layout()
    plt.savefig(figures_dir / "factor_incidence_heatmap.png", dpi=130)
    plt.savefig(os.path.join(paper_dir, "fig08_factor_incidence.png"), dpi=130)
    plt.close()

    # Appendix B: by-world-region twin of Figure 8 (same heatmap, region matrix).
    appb_dir = str(config.output_dirs("paper/appendix_b")[1])
    reg_lab = {r: r for r in REGION_ORDER}
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 4.8))
    _heat_panel(axes[0], Br, T_ABS, lambda v: f"{v:+.0f}", order=REGION_ORDER, labels=reg_lab)
    _heat_panel(axes[1], Pr, T_PCT, lambda v: f"{v:+.0f}%", order=REGION_ORDER, labels=reg_lab)
    axes[1].set_yticks([])
    plt.tight_layout()
    plt.savefig(os.path.join(appb_dir, "figB_factor_incidence_by_region.png"), dpi=130)
    plt.close()
    print(f"  wrote {os.path.join(appb_dir, 'figB_factor_incidence_by_region.png')}")

    # Grouped bars (slide variant; kept next to the paper figure).
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 5.2))
    _bar_panel(axes[0], B, "USD bn per year")
    _bar_panel(axes[1], P, "% of corporate tax currently paid")
    axes[0].set_title(T_ABS, fontsize=11, loc="left")
    axes[1].set_title(T_PCT, fontsize=11, loc="left")
    axes[0].legend(fontsize=8.5, framealpha=0.85)
    plt.tight_layout()
    plt.savefig(figures_dir / "factor_incidence_bars.png", dpi=130)
    plt.savefig(os.path.join(paper_dir, "factor_incidence_bars.png"), dpi=130)
    plt.close()

    print("\nPure-factor incidence, tax revenue (bn USD/yr, ETR-CIT, domfor):")
    print(B.round(1).to_string())
    print("\nAs % of corporate tax currently paid:")
    print(P.round(0).to_string())
    print(f"\nwrote {tables_dir / 'factor_incidence_matrix.csv'}")
    print(f"wrote {figures_dir / 'factor_incidence_heatmap.png'} "
          f"(+ paper copy fig08_factor_incidence.png)")
    print(f"wrote {figures_dir / 'factor_incidence_bars.png'}")


if __name__ == "__main__":
    main()
