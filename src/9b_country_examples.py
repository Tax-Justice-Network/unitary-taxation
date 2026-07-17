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
from _brand import apply_tjn_style, EARTH_GREEN, BLUE, GOLD, RED, POSITIVE, NEGATIVE

apply_tjn_style()

TABLES_DIR, FIGURES_DIR = output_dirs("three_scenarios")
SUMMARY = TABLES_DIR / "three_scenario_summary_long_2016_22.csv"

EXAMPLES = [
    ("TCD", "Chad", "Corrected for resource rent capture"),
    ("SSD", "South Sudan", "Corrected for resource rent capture"),
    ("BFA", "Burkina Faso", "Minimum royalty"),
]
SCEN = {"ignorant_reported": "S1: ignore", "excl_reported": "S2: corrected",
        "excl_floored_reported": "S3: + floor"}
SCEN_ORDER = ["S1: ignore", "S2: corrected", "S3: + floor"]
HEADLINE_FORMULA = "sales_employees_destmnedds"   # paper headline (2026-07-12)

# Self-explanatory x-axis labels so each slide is readable on its own, without a
# separate scenario legend / S1-S2-S3 key. Keyed by scenario.
SCEN_KEY_ORDER = ["ignorant_reported", "excl_reported", "excl_floored_reported"]
SCEN_DESC = {
    "ignorant_reported": "Resources ignored\n(current system)",
    "excl_reported": "Resource profits\nexcluded",
    "excl_floored_reported": "+ Minimum\nroyalty floor",
}
# Which scenarios each per-country slide shows. South Sudan and Chad illustrate the
# effect of EXCLUDING resource profits, so they show baseline vs resources-excluded
# only (the minimum-royalty floor is Burkina Faso's example, not theirs).
SLIDE_SCENARIOS = {
    "SSD": ["ignorant_reported", "excl_reported"],
    "TCD": ["ignorant_reported", "excl_reported"],
}

# Progressive-reveal "build-up" slides: focus countries + the revenue metric
# each one is shown with. South Sudan uses CIT/CIT (both UT gains & losses at
# statutory CIT) because its effective tax rate is degenerate (sign-flipping
# profit base → ETR clipped to 0), which otherwise decouples the revenue sign
# from the tax-base sign. Burkina Faso keeps the conservative ETR/ETR view.
BUILDUP = [
    ("SSD", "South Sudan", "Corrected for resource rent capture"),
    ("TCD", "Chad", "Corrected for resource rent capture"),
    ("BFA", "Burkina Faso", "Minimum royalty"),
]
BUILDUP_BASE_METRIC = ("delta_taxable_profits_musd", "Change in taxable profit\n(tax base, $m)")
BUILDUP_REVENUE_BY_COUNTRY = {
    "SSD": ("delta_total_gvt_revenue_recCIT_forgCIT_musd", "Change in tax revenue\n(CIT/CIT, $m)"),
    "TCD": ("delta_total_gvt_revenue_recCIT_forgCIT_musd", "Change in tax revenue\n(CIT/CIT, $m)"),
    "BFA": ("delta_total_gvt_revenue_recETR_forgETR_musd", "Change in tax revenue\n(ETR/ETR, $m)"),
}
_DEFAULT_REVENUE = ("delta_total_gvt_revenue_recCIT_forgETR_musd", "Change in tax revenue\n($m)")

METRICS = [
    ("delta_taxable_profits_musd", "Change in taxable profit\n(taxing rights, $m)"),
    ("delta_total_gvt_revenue_recCIT_forgETR_musd", "Change in tax revenue\ngains×CIT / losses×ETR ($m)"),
    ("delta_total_gvt_revenue_recETR_forgETR_musd", "Change in tax revenue\nboth×ETR ($m)"),
]

# Four formula families shown as grouped bars on the per-country slides.
FORMULAS = [
    ("sales_employees", "Sales + employees"),
    ("ccctb", "CCCTB"),
    ("three_factors", "Three-factor"),
    ("double_weighted_sales", "Double-weighted sales"),
]
FORMULA_COLOURS = [EARTH_GREEN, BLUE, GOLD, RED]

POS, NEG = POSITIVE, NEGATIVE


def fig_country_slide(df, iso, name, role):
    """One slide per country: 3 metric rows, x = scenarios, 4 formula bars/group.
    The scenarios shown (and their self-explanatory x labels) come from
    SLIDE_SCENARIOS / SCEN_DESC, so the figure reads without a separate key."""
    sub = df[df["iso_partner"] == iso]
    scen_keys = SLIDE_SCENARIOS.get(iso, SCEN_KEY_ORDER)
    xlabels = [SCEN_DESC[k] for k in scen_keys]
    fkeys = [f for f, _ in FORMULAS]
    flabels = [lab for _, lab in FORMULAS]
    n_f = len(fkeys)
    bar_w = 0.8 / n_f
    x = np.arange(len(scen_keys))

    fig, axes = plt.subplots(len(METRICS), 1, figsize=(9, 10), sharex=True)
    for r, (mcol, mlabel) in enumerate(METRICS):
        ax = axes[r]
        piv = sub.pivot_table(index="scenario", columns="formula_name", values=mcol,
                              aggfunc="first").reindex(scen_keys)
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
    axes[-1].set_xticklabels(xlabels, fontsize=9)
    axes[0].legend(fontsize=8, ncol=2, loc="best", framealpha=0.85)
    fig.suptitle(f"{name} ({iso}) — {role}\nraw (reported-only) data, 2016–2022, four formulas",
                 fontsize=12)
    note = {
        "TCD": "Chad already wins taxing rights under most formulas even before the correction; excluding resource-related profits lifts all of them.",
        "SSD": "South Sudan gains taxing rights once resource-related profits are excluded (right group vs left), with proportional tax-revenue gains under both rate specifications; its effective tax rate is ~20–30%.",
        "BFA": "Never wins on taxable profit (the floor adds revenue, not profit base). Flips to a net revenue winner only once the minimum-royalty floor is added, under all four formulas.",
    }.get(iso, "")
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=8, wrap=True, color="#444444")
    plt.tight_layout(rect=[0, 0.04, 1, 0.93])
    fname = f"fig_country_example_{iso}.png"
    plt.savefig(FIGURES_DIR / fname, dpi=130)
    plt.close()
    print(f"  wrote {FIGURES_DIR / fname}")


def fig_country_buildup(df, iso, name, role):
    """Progressive-reveal slides for one country: tax base (top) + revenue (bottom),
    four formula bars per scenario group. Step k reveals scenarios 1..k.

    The y-scales and bar positions are FIXED across all steps (computed over all
    three scenarios), and the figure width grows with the number of revealed
    scenarios — so the bars keep a constant physical size and step 1 is literally
    the left crop of the full three-scenario picture. Revenue metric is
    per-country (SSD = CIT/CIT, BFA = ETR/ETR; see BUILDUP_REVENUE_BY_COUNTRY)."""
    sub = df[df["iso_partner"] == iso]
    fkeys = [f for f, _ in FORMULAS]
    flabels = [lab for _, lab in FORMULAS]
    n_f = len(fkeys)
    bar_w = 0.8 / n_f
    x = np.arange(len(SCEN_ORDER))

    rev_col, rev_label = BUILDUP_REVENUE_BY_COUNTRY.get(iso, _DEFAULT_REVENUE)
    metrics = [BUILDUP_BASE_METRIC, (rev_col, rev_label)]

    # Per-metric pivots + fixed y-limits over ALL scenarios (so axes never
    # rescale between steps — that is what makes step 1 a true left-crop).
    pivots, ylims = [], []
    for mcol, _ in metrics:
        piv = sub.pivot_table(index="scen", columns="formula_name", values=mcol,
                              aggfunc="first").reindex(SCEN_ORDER)
        pivots.append(piv)
        finite = piv.values.astype(float)
        finite = finite[np.isfinite(finite)]
        lo = min(finite.min(), 0.0) if finite.size else -1.0
        hi = max(finite.max(), 0.0) if finite.size else 1.0
        pad = 0.18 * ((hi - lo) or 1.0)
        ylims.append((lo - pad, hi + pad))

    per_scen_w, left_pad = 2.8, 1.8
    for k in range(1, len(SCEN_ORDER) + 1):
        fig, axes = plt.subplots(
            len(metrics), 1, figsize=(left_pad + per_scen_w * k, 7.8),
            sharex=True, squeeze=False,
        )
        axes = axes[:, 0]
        for r, (mcol, mlabel) in enumerate(metrics):
            ax = axes[r]
            piv = pivots[r]
            for i, fk in enumerate(fkeys):
                if fk not in piv.columns:
                    continue
                vals = piv[fk].values.astype(float).copy()
                vals[k:] = np.nan          # hide not-yet-revealed scenarios
                offset = (i - (n_f - 1) / 2) * bar_w
                ax.bar(x + offset, vals, width=bar_w, color=FORMULA_COLOURS[i],
                       label=flabels[i] if r == 0 else None)
            ax.axhline(0, color="grey", lw=0.6)
            ax.set_ylabel(mlabel, fontsize=10)
            ax.set_ylim(*ylims[r])
            ax.set_xlim(-0.6, k - 0.4)
        axes[-1].set_xticks(x[:k])
        axes[-1].set_xticklabels(SCEN_ORDER[:k], fontsize=15, fontweight="bold")
        axes[0].legend(fontsize=7.5, ncol=1, loc="upper left", framealpha=0.9)
        # No in-figure title: the beamer frametitle carries the country name, and
        # an in-figure suptitle (centered per image) would shift between the
        # narrow and wide build-up steps. Keep the full height for the bars.
        plt.tight_layout(rect=[0, 0.02, 1, 0.98])
        fname = f"fig_buildup_{iso}_step{k}.png"
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
    _csv = TABLES_DIR / "country_examples_2016_22.csv"
    try:
        tbl.to_csv(_csv, index=False)
        print(f"  wrote {_csv}")
    except PermissionError:
        print(f"  [warn] could not write {_csv.name} (open in Excel / locked) — "
              f"skipping table, continuing with figures")

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
        "Low-income country examples — employees + destination-based sales formula, raw (reported-only) data, 2016–2022\n"
        "green = country gains, red = country loses",
        fontsize=12,
    )
    note = (
        "Chad & South Sudan win once resources are excluded (S1→S2); Burkina Faso wins only once the minimum-royalty floor is added (S2→S3).  "
        "Tax-revenue gains move with the change in taxable profit under both rate specifications."
    )
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=7.5, wrap=True, color="#444444")
    plt.tight_layout(rect=[0, 0.05, 1, 0.93])
    plt.savefig(FIGURES_DIR / "fig_country_examples.png", dpi=130)
    plt.close()
    print(f"  wrote {FIGURES_DIR / 'fig_country_examples.png'}")

    # ── Per-country slides (all four formulas) ───────────────────────────────
    for iso, name, role in EXAMPLES:
        fig_country_slide(df, iso, name, role)

    # ── Progressive-reveal build-up slides (SSD, BFA) ────────────────────────
    for iso, name, role in BUILDUP:
        fig_country_buildup(df, iso, name, role)

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
