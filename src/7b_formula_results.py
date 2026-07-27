# %%
"""
Formula results — the income-group figures and country tables comparing the
apportionment formula families (all on the complete destination measure).

Concept: how do the results differ across the formula families (sales &
employees — the headline —, CCCTB, three-factor, double-weighted sales)?
Everything this concept produces lives here, for BOTH samples (reported_only
= main text; gravity = appendix):

  Figures (paper style, untitled panels):
    fig02_taxable_profit_by_income.png   Δ taxable profit, 4 families
    fig03_tax_revenue.png                Δ tax revenue (statutory-rate gains),
                                         grey ghost bars = scaled to global
                                         multinational profit (needs 7b's
                                         scaleup_yearly.csv)
    figG3_tax_revenue_ETR_ETR.png        Δ tax revenue, both legs at ETR

  Tables (CSV + markdown, income-group + by-region variants):
    table2_taxable_profits_by_formula    Δ taxable profit by family (+%)
    table3_tax_revenue_by_formula        Δ tax revenue by family (+% of MNE tax)
    table3c_revenue_pct_of_cit           same, % of total CIT revenue (OECD
                                         Global Revenue Statistics T_1200)

Sections:
  0. Settings
  1. Figures
  2. Tables
  3. Main

Usage: python 7c_formula_results.py
"""

# %% MARK: 0. Settings
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

from _brand import apply_tjn_style
import _scenario_comparison as _sc
import _exhibit_helpers as _eh

apply_tjn_style()


# %% MARK: 1. Figures
def formula_figures(sample, by_inc, ghost_by_inc=None):
    figures_dir = _eh.figdir(sample)
    excl = _eh.SCEN_KEYS[sample]["excl"]
    _eh.ig_twopanel(by_inc, excl, _eh.PAPER_4FORMULAS, "delta_taxable_profits_musd",
                    "delta_taxable_profits_pct_posbase", _eh.TP_ABS, _eh.TP_PCT,
                    "fig02_taxable_profit_by_income.png", figures_dir, usd_decimals=0)
    _eh.ig_twopanel(by_inc, excl, _eh.PAPER_4FORMULAS, _eh.REV_CIT, _eh.REV_CIT_PCT,
                    _eh.RV_ABS, _eh.RV_PCT, "fig03_tax_revenue.png", figures_dir,
                    usd_decimals=0, ghost_by_inc=ghost_by_inc)
    _eh.ig_twopanel(by_inc, excl, _eh.PAPER_4FORMULAS, _eh.REV_ETR, _eh.REV_ETR_PCT,
                    _eh.RV_ABS, _eh.RV_PCT, "figG3_tax_revenue_ETR_ETR.png",
                    figures_dir, usd_decimals=0)


# %% MARK: 2. Tables
def formula_tables(sample, tables_dir):
    excl_rev = _eh.rev_musd(sample, "excl_resource", _eh.HEADLINE_FORMULA)
    if excl_rev.empty:
        print(f"  [skip formula tables] no {sample} summary")
        return
    order_iso = pd.Index(sorted(excl_rev.index, key=lambda i: _eh.cname(i).lower()))
    grp = _eh.income_group(sample).to_dict()
    grp_reg = _eh.region(sample).to_dict()

    posbase = _eh.posbase_musd(sample)
    netbase = _eh.reported_musd(sample, "excl_resource")
    cashtax = _eh.current_rev_musd(sample)
    tb = pd.DataFrame(index=order_iso)
    rev = pd.DataFrame(index=order_iso)
    # Net reported profits (losses included, can be negative) shown for honesty;
    # the POSITIVE-only base stays the % denominator (loss cells owe no tax).
    tb["net reported profits"] = netbase
    tb["taxable profits (positive profits only)"] = posbase
    rev["current tax revenue from MNEs"] = cashtax
    for fk, flab in _eh.PAPER_4FORMULAS:
        lab = flab.lower() if flab != "CCCTB" else flab
        tb[lab] = _eh.taxbase_musd(sample, "excl_resource", fk)
        rev[lab] = _eh.rev_musd(sample, "excl_resource", fk)
    _flabs = [flab.lower() if flab != "CCCTB" else flab
              for _, flab in _eh.PAPER_4FORMULAS]
    _eh.emit_table(tb, order_iso, grp, grp_reg, sample,
                   "table2_taxable_profits_by_formula", tables_dir,
                   pct_base="taxable profits (positive profits only)",
                   pct_cols=_flabs, drop_base_col=True)
    _eh.emit_table(rev, order_iso, grp, grp_reg, sample,
                   "table3_tax_revenue_by_formula", tables_dir,
                   pct_base="current tax revenue from MNEs", pct_cols=_flabs)

    # Table 3c — the SAME per-formula revenue effects as % of the country's
    # TOTAL corporate income tax revenue (OECD RSGLOBAL T_1200). Countries not
    # covered by RSGLOBAL (~90 of 226) show an empty denominator and no %.
    cit_total = _eh.oecd_cit_revenue_musd()
    rev_cit = pd.DataFrame(index=order_iso)
    rev_cit["total CIT revenue (OECD RSGLOBAL)"] = cit_total
    for lab in _flabs:
        rev_cit[lab] = rev[lab]
    _eh.emit_table(rev_cit, order_iso, grp, grp_reg, sample,
                   "table3c_revenue_pct_of_cit", tables_dir,
                   pct_base="total CIT revenue (OECD RSGLOBAL)", pct_cols=_flabs)

    # verification: income-group sums of excl-resource revenue
    ig = _eh.income_group(sample)
    chk = excl_rev.groupby(excl_rev.index.map(ig)).sum().reindex(_eh.IG_ORDER)
    print(f"  [{sample}] excl-resource revenue change by income group ($m/yr): "
          + ", ".join(f"{str(k)[:3]}={v:,.0f}" for k, v in chk.items()))


# %% MARK: 3. Main
def main():
    _sc.INCOME_GROUP_LABELS = _eh.IG_LABELS_PAPER
    for sample in _eh.SAMPLES:
        print(f"== {sample} ==")
        if not _eh.summary_exists(sample):
            print(f"  [skip] no {sample} summaries yet")
            continue
        summary = _eh.paper_summary(sample)
        if summary is not None:
            by_inc = _sc.build_by_income(summary)
            ghost = (_eh.ghost_by_income(sample)
                     if sample == "reported_only" else None)
            formula_figures(sample, by_inc, ghost_by_inc=ghost)
        formula_tables(sample, _eh.tabledir(sample))
    print("\nDone.")


if __name__ == "__main__":
    main()
