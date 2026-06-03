# %%
"""
Country examples for the three-scenario deliverable.

Three low-income illustrations, all on the RAW (reported-only) data, 2016-2022,
average ETR:

  RESOURCE-EXCLUSION CASES (win once resources are taken out of the UT pool):
    * Chad (TCD)        — oil. Loses taxing rights when resources are ignored
                          (S1) and wins once they are excluded (S2). The S1
                          loss holds under the SOTJ headline formula (under the
                          other three families Chad already wins in S1).
    * South Sudan (SSD) — oil. Robust taxing-rights flip S1->S2 across formulas.
                          NB: its ETR/ETR *revenue* figure is a data artifact
                          (degenerate, sign-flipping profit base => clipped-to-0
                          ETR), so its solid claim is taxing rights, not ETR/ETR
                          revenue.

  MINIMUM-ROYALTY CASE (wins only once the floor is applied):
    * Burkina Faso (BFA) — gold. Loses on both taxable profit and revenue when
                           resources are ignored (S1) and when excluded (S2);
                           turns into a net revenue winner only in S3, once the
                           IGF-ATAF minimum-royalty floor is enforced (Cat-1
                           schedule raised to 1.2%->12% so it flips under all
                           four formulas).

Reads the three-scenario summary produced by 9_three_scenario_figures.py.

Outputs to output/three_scenarios/{tables,figures}/:
  country_examples_2016_22.csv     — country x scenario x formula, all metrics
  fig_country_examples.png         — SOTJ headline overview: 3 metrics (rows) x 3 countries (cols)
  fig_country_example_<ISO>.png    — ONE PER COUNTRY (a slide each): 3 metrics (rows) x
                                     3 scenarios, with all four formula families as grouped bars

Usage: python 9b_country_examples.py
"""

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from config import output_dirs

TABLES_DIR, FIGURES_DIR = output_dirs("three_scenarios")
SUMMARY = TABLES_DIR / "three_scenario_summary_long_2016_22.csv"

EXAMPLES = [
    ("TCD", "Chad", "Resource exclusion"),
    ("SSD", "South Sudan", "Resource exclusion"),
    ("BFA", "Burkina Faso", "Minimum royalty"),
]
SCEN = {"ignorant_reported": "S1 ignore", "excl_reported": "S2 exclude",
        "excl_floored_reported": "S3 + floor"}
SCEN_ORDER = ["S1 ignore", "S2 exclude", "S3 + floor"]
HEADLINE_FORMULA = "employees_payroll"

METRICS = [
    ("delta_taxable_profits_musd", "Δ taxable profit\n(taxing rights, $m)"),
    ("delta_total_gvt_revenue_recCIT_forgETR_musd", "Δ tax revenue\ngains×CIT / losses×ETR ($m)"),
    ("delta_total_gvt_revenue_recETR_forgETR_musd", "Δ tax revenue\nboth×ETR ($m)"),
]

# Four formula families shown as grouped bars on the per-country slides.
FORMULAS = [
    ("employees_payroll", "Employees + payroll (SOTJ)"),
    ("ccctb", "CCCTB"),
    ("three_factors", "Three-factor"),
    ("double_weighted_sales", "Double-weighted sales"),
]
FORMULA_COLOURS = ["#4c72b0", "#dd8452", "#55a467", "#c44e52"]

POS, NEG = "#55a467", "#c44e52"


def fig_country_slide(df, iso, name, role):
    """One slide per country: 3 metric rows, x = scenarios, 4 formula bars/group."""
    sub = df[df["iso_partner"] == iso]
    fkeys = [f for f, _ in FORMULAS]
    flabels = [lab for _, lab in FORMULAS]
    n_f = len(fkeys)
    bar_w = 0.8 / n_f
    x = np.arange(len(SCEN_ORDER))

    fig, axes = plt.subplots(len(METRICS), 1, figsize=(9, 10), sharex=True)
    for r, (mcol, mlabel) in enumerate(METRICS):
        ax = axes[r]
        piv = sub.pivot_table(index="scen", columns="formula_name", values=mcol,
                              aggfunc="first").reindex(SCEN_ORDER)
        for i, fk in enumerate(fkeys):
            if fk not in piv.columns:
                continue
            vals = piv[fk].values
            offset = (i - (n_f - 1) / 2) * bar_w
            ax.bar(x + offset, vals, width=bar_w, color=FORMULA_COLOURS[i],
                   label=flabels[i] if r == 0 else None)
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_ylabel(mlabel, fontsize=9)
        ax.margins(y=0.18)
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(SCEN_ORDER, fontsize=9)
    axes[0].legend(fontsize=8, ncol=2, loc="best", framealpha=0.85)
    fig.suptitle(f"{name} ({iso}) — {role}\nraw (reported-only) data, 2016–2022, four formulas",
                 fontsize=12)
    note = {
        "TCD": "Loses taxing rights when resources are ignored only under the SOTJ formula; under the other three Chad already wins in S1. Resource exclusion (S2) lifts all formulas.",
        "SSD": "Robust taxing-rights flip S1→S2 across formulas (top). both×ETR revenue (bottom) is a data artifact of a sign-flipping profit base (ETR clipped to 0).",
        "BFA": "Never wins on taxable profit (floor adds revenue, not profit base). Flips to a net revenue winner only in S3, under all four formulas, with the raised Cat-1 royalty (1.2%–12%).",
    }.get(iso, "")
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=8, wrap=True, color="#444444")
    plt.tight_layout(rect=[0, 0.04, 1, 0.93])
    fname = f"fig_country_example_{iso}.png"
    plt.savefig(FIGURES_DIR / fname, dpi=130)
    plt.close()
    print(f"  wrote {FIGURES_DIR / fname}")


def main():
    df = pd.read_csv(SUMMARY)
    df["scen"] = df["scenario"].map(SCEN)
    df = df[df["iso_partner"].isin([i for i, _, _ in EXAMPLES])].copy()

    # ── Table: all formulas, key metrics, wide over scenarios ────────────────
    metric_cols = [m for m, _ in METRICS]
    long = df.melt(
        id_vars=["iso_partner", "partner_jurisdiction", "formula_name", "scen"],
        value_vars=metric_cols, var_name="metric", value_name="musd",
    )
    tbl = long.pivot_table(
        index=["iso_partner", "partner_jurisdiction", "formula_name", "metric"],
        columns="scen", values="musd", aggfunc="first",
    ).reset_index()
    tbl = tbl[["iso_partner", "partner_jurisdiction", "formula_name", "metric"] + SCEN_ORDER]
    tbl.to_csv(TABLES_DIR / "country_examples_2016_22.csv", index=False)
    print(f"  wrote {TABLES_DIR / 'country_examples_2016_22.csv'}")

    # ── Figure: SOTJ headline, metrics (rows) x countries (cols) ─────────────
    hl = df[df["formula_name"] == HEADLINE_FORMULA]
    fig, axes = plt.subplots(len(METRICS), len(EXAMPLES), figsize=(13, 9.5), sharex=True)
    for r, (mcol, mlabel) in enumerate(METRICS):
        for c, (iso, name, role) in enumerate(EXAMPLES):
            ax = axes[r, c]
            sub = hl[hl["iso_partner"] == iso].set_index("scen").reindex(SCEN_ORDER)
            vals = sub[mcol].values
            colors = [POS if (v is not None and v > 0) else NEG for v in vals]
            ax.bar(SCEN_ORDER, vals, color=colors, width=0.66)
            ax.axhline(0, color="grey", lw=0.6)
            for x, v in enumerate(vals):
                if pd.notna(v):
                    ax.annotate(f"{v:+,.0f}", (x, v), ha="center",
                                va="bottom" if v >= 0 else "top", fontsize=8)
            if r == 0:
                ax.set_title(f"{name} ({iso})\n[{role}]", fontsize=10)
            if c == 0:
                ax.set_ylabel(mlabel, fontsize=9)
            ax.margins(y=0.22)
            ax.tick_params(axis="x", labelsize=8)

    fig.suptitle(
        "Low-income country examples — SOTJ formula, raw (reported-only) data, 2016–2022\n"
        "green = country gains, red = country loses",
        fontsize=12,
    )
    note = (
        "Chad & South Sudan win once resources are excluded (S1→S2); Burkina Faso wins only once the minimum-royalty floor is added (S2→S3).  "
        "Caveats: Chad's S1 loss holds under the SOTJ formula only; South Sudan's both×ETR revenue (bottom row) is a data artifact of a sign-flipping "
        "profit base (ETR clipped to 0), so its robust claim is taxing rights (top row), not ETR/ETR revenue."
    )
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=7.5, wrap=True, color="#444444")
    plt.tight_layout(rect=[0, 0.05, 1, 0.93])
    plt.savefig(FIGURES_DIR / "fig_country_examples.png", dpi=130)
    plt.close()
    print(f"  wrote {FIGURES_DIR / 'fig_country_examples.png'}")

    # ── Per-country slides (all four formulas) ───────────────────────────────
    for iso, name, role in EXAMPLES:
        fig_country_slide(df, iso, name, role)

    # ── Console summary (SOTJ) ───────────────────────────────────────────────
    print("\nSOTJ headline, $m, summed 2016–2022:")
    for iso, name, role in EXAMPLES:
        sub = hl[hl["iso_partner"] == iso].set_index("scen").reindex(SCEN_ORDER)
        print(f"\n  {name} ({iso}) — {role}")
        for mcol, mlabel in METRICS:
            v = sub[mcol]
            print("    %-38s %s" % (
                mlabel.replace("\n", " "),
                "  ".join(f"{s}:{v[s]:+8.1f}" for s in SCEN_ORDER),
            ))


if __name__ == "__main__":
    main()
