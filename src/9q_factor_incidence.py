# %% [0] Factor incidence — who gains from each apportionment factor?
"""
Pure single-factor TAX-REVENUE incidence by income group.

For each apportionment factor f (employees, payroll, tangible assets,
destination-based sales) and income group g, estimate the change in TAX
REVENUE if multinational profits were apportioned by that factor ALONE
(user 2026-07-12, revised same day: revenue, not the base — the paper's
headline metric). Because the formulary allocation is linear in the formula
weights (and the ETR-CIT valuation of the gain/loss legs preserves that
linearity almost exactly at the group level — check the printed R2), any real
formula's group outcome is approximately the weight-average of these pure
columns — the matrix doubles as a "build your own formula" explainer.

Estimation: the pure columns are recovered by least squares across the nine
formula variants actually run (each a known weight vector over five factors;
origin sales is in the DESIGN for identification but not displayed — the
sales-measure comparison has its own section).

Spec: excl_resource (resource rights prior to taxing rights), REPORTED sample,
domfor ETR, ETR-CIT (loss_cit_gain_etr), etrmax_inf; per-year averages
2016-2022 excl 2020 in constant BASE_YEAR USD. The %-panel denominator is the
corporate cash tax the group's reporting multinationals currently pay
(current_tax_paid_cash_musd), matching the paper's revenue % panels.

Framing: this is the argument of Loretz (2026), "Unitary taxation and
formulary apportionment" (WIFO study commissioned by the Network of Unions for
Tax Justice and the Austrian Chamber of Labour) made concrete on our data —
heavier employment weighting shifts taxing rights toward labour-intensive
economies, while profit-shifting hubs lose under every factor.

Outputs (output_dirs("deliverables/factor_incidence")):
  tables/factor_incidence_matrix.csv          (USD bn/yr + % of current tax)
  figures/factor_incidence_heatmap.png        (two-panel annotated heatmap)
  figures/factor_incidence_bars.png           (two-panel grouped bars)
No titles baked into the images (the paper caption carries them).

Usage: python 9q_factor_incidence.py
"""
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
from _brand import apply_tjn_style, PALETTE, HATCH_CYCLE, DIVERGING_GAIN_LOSS

apply_tjn_style()

DEFL = config.deflator_to_base()
YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
MDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "output", "unitary_taxation", "reported_only",
                    "excl_resource", "tables", "excl_resource")

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
    # BaTIS deliverable imports), 2026-07-12.
    "sales_employees_destmnedds":       [0.5, 0.0, 0.0, 0.0, 0.5],
    "ccctb_destmnedds":                 [1/6, 1/6, 1/3, 0.0, 1/3],
    "three_factors_destmnedds":         [1/3, 0.0, 1/3, 0.0, 1/3],
    "double_weighted_sales_destmnedds": [0.25, 0.0, 0.25, 0.0, 0.5],
}
SHOW = ["Employees", "Payroll", "Tangible\nassets", "Sales\n(destination)"]
IG_ORDER = ["low_income", "lower_middle_income", "upper_middle_income",
            "high_income", "investment_hub"]
IG_LAB = {"low_income": "Low income", "lower_middle_income": "Lower middle income",
          "upper_middle_income": "Upper middle income", "high_income": "High income",
          "investment_hub": "Tax havens"}   # relabelled (user 2026-07-13)


def build_matrices():
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
        f_defl = d.year.map(DEFL)
        # Δ tax revenue (net, ETR-CIT valuation; MUSD -> deflated).
        d["v"] = pd.to_numeric(d.revenue_gain_from_ut, errors="coerce") * f_defl
        g = d.groupby("wb_income_group").v.sum() / 1e3 / len(YEARS)
        rows.append(g.reindex(IG_ORDER).values)
        wmat.append(w)
        if base is None:
            # Denominator = corporate cash tax currently paid by the group's
            # reporting MNEs (matches the paper's revenue % panels).
            d["b"] = pd.to_numeric(d.current_tax_paid_cash_musd,
                                   errors="coerce") * f_defl
            base = (d.groupby("wb_income_group").b.sum() / 1e3 / len(YEARS)
                    ).reindex(IG_ORDER)
    Y, W = np.array(rows), np.array(wmat)
    beta, _, rank, _ = np.linalg.lstsq(W, Y, rcond=None)
    fit = W @ beta
    r2 = 1 - ((Y - fit) ** 2).sum() / ((Y - Y.mean(axis=0)) ** 2).sum()
    print(f"linearity fit R2 = {r2:.4f} (rank {rank}, {len(wmat)} formulas)")
    B = pd.DataFrame(beta, index=FACTORS_ALL, columns=IG_ORDER)
    P = B.div(base, axis=1) * 100
    return B.loc[SHOW], P.loc[SHOW]


_CMAP = LinearSegmentedColormap.from_list("tjn_gainloss", DIVERGING_GAIN_LOSS)


def _heat_panel(ax, M, title, fmt):
    """Green = gain, red = loss; shading scaled WITHIN each income-group row
    (each group's own min→max spans light→dark), so every row shows its factor
    ranking instead of being washed out by the panel's single largest value
    (user 2026-07-12). Colour-blind redundancy: every cell prints the signed
    value, so polarity never rides on the hue alone. The row's largest effect
    is bold."""
    V = M.values.T.astype(float)          # rows = income groups, cols = factors
    row_max = np.maximum(np.abs(V).max(axis=1, keepdims=True), 1e-9)
    T = V / row_max                       # per-row scaling to [-1, 1]
    ax.imshow(T, cmap=_CMAP, vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(SHOW)), SHOW, fontsize=9)
    ax.set_yticks(range(len(IG_ORDER)), [IG_LAB[g] for g in IG_ORDER], fontsize=9)
    # white separators between cells; kill the style's y-grid, which would
    # otherwise draw streaks across the cells
    ax.set_xticks(np.arange(0.5, len(SHOW) - 1), minor=True)
    ax.set_yticks(np.arange(0.5, len(IG_ORDER) - 1), minor=True)
    ax.grid(which="major", visible=False)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    for i in range(len(SHOW)):
        for j in range(len(IG_ORDER)):
            v, t = M.values[i, j], T[j, i]
            ax.text(i, j, fmt(v), ha="center", va="center", fontsize=10,
                    color="white" if abs(t) > 0.75 else "#222222",
                    fontweight="bold" if abs(t) > 0.999 else "normal")
    ax.set_title(title, fontsize=11, loc="left")


def _bar_panel(ax, M, ylabel):
    x = np.arange(len(SHOW))
    n = len(IG_ORDER)
    bw = 0.82 / n
    for j, g in enumerate(IG_ORDER):
        ax.bar(x + (j - (n - 1) / 2) * bw, M[g].values, width=bw,
               color=PALETTE[j % len(PALETTE)],
               hatch=HATCH_CYCLE[j % len(HATCH_CYCLE)],
               edgecolor="white", linewidth=0.3, label=IG_LAB[g])
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_xticks(x, SHOW, fontsize=9)
    ax.set_ylabel(ylabel)


def main():
    tables_dir, figures_dir = output_dirs("deliverables/factor_incidence")
    # Paper-figure copies live with fig01-fig11 (user 2026-07-12); the heatmap
    # takes the fig10 slot freed by the dropped CFB-variants figure.
    paper_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "output", "unitary_taxation", "reported_only", "paper_figures", "figures")
    os.makedirs(paper_dir, exist_ok=True)
    B, P = build_matrices()

    out = pd.concat({"usd_bn_per_year": B, "pct_of_current_tax_paid": P})
    out.index.names = ["unit", "factor"]
    out.to_csv(tables_dir / "factor_incidence_matrix.csv")

    T_ABS = "Change in tax revenue (USD bn per year)"
    T_PCT = "% of corporate tax currently paid"

    # Heatmap (panel titles only; the paper caption carries the figure title).
    fig, axes = plt.subplots(1, 2, figsize=(14.5, 4.8))
    _heat_panel(axes[0], B, T_ABS, lambda v: f"{v:+.0f}")
    _heat_panel(axes[1], P, T_PCT, lambda v: f"{v:+.0f}%")
    axes[1].set_yticks([])
    plt.tight_layout()
    plt.savefig(figures_dir / "factor_incidence_heatmap.png", dpi=130)
    plt.savefig(os.path.join(paper_dir, "fig10_factor_incidence.png"), dpi=130)
    plt.close()

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
          f"(+ paper copy fig10_factor_incidence.png)")
    print(f"wrote {figures_dir / 'factor_incidence_bars.png'}")


if __name__ == "__main__":
    main()
