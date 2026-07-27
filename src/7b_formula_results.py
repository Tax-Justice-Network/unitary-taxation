# %%
"""
7b — Results by apportionment formula family.

Compares the four apportionment formula families — sales + employees (the
headline), CCCTB, three-factor and double-weighted sales, all on the complete
destination measure — by income group. Produces the change-in-taxable-profit
and change-in-tax-revenue figures (Figure 3 carries grey ghost bars scaled to
global multinational profit, from 7a), an ETR-at-both-legs mirror (Figure G3),
and the by-formula country tables (a variant expresses the revenue change as a
share of total corporate income tax revenue, OECD Global Revenue Statistics).
Figure 4 shows the plausible ranges of the revenue gain under conservative /
headline / optimistic tax-rate assumptions (moved here 2026-07-25 from the
resource-rights script, where it never belonged). Everything is produced for
both the reported (main text) and gravity (appendix) samples.

Headline specification: reported-only sample, resources excluded, employees + destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at statutory CIT and losses at ETR, per-year average over 2016–2022 (2020 excluded), constant 2025 US$.

Exhibit script — consumes the script-6 estimation summaries. Produces Figures 2-4
+ Figure G3 (ETR-ETR mirror) + Tables 2-3 + the region twins (Appendix B).

Reads:
  output/estimates/{reported_only,with_imputed_rows}/*/tables/summary_country_year_long.csv — per-country estimates by formula (script 6)
  output/paper/main_text/scaleup_yearly.csv                             — ghost-bar scale factors (from 7a)

Writes:
  output/paper/main_text/fig02_taxable_profit_by_income.png/.pdf        — Figure 2 (Δ taxable profit)
  output/paper/main_text/fig03_tax_revenue.png/.pdf                     — Figure 3 (Δ revenue, ghost bars)
  output/paper/main_text/fig04_*.png/.pdf                               — Figure 4 (plausible revenue ranges)
  output/paper/main_text/table2_taxable_profits_by_formula.csv/.tex     — Table 2
  output/paper/main_text/table3_tax_revenue_by_formula.csv/.tex         — Table 3 (+ table3c CIT-share companion)

Usage:
  python 7b_formula_results.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Settings
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import glob as _glob

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _brand import apply_tjn_style, PALETTE
import _scenario_machinery as _sc
import _exhibit_helpers as _eh

apply_tjn_style()


# %% MARK: 2. Figures
def formula_figures(sample, by_inc, ghost_by_inc=None, by_region=None):
    figures_dir = _eh.figdir(sample)
    excl = _eh.SCEN_KEYS[sample]["excl"]
    _eh.ig_twopanel(by_inc, excl, _eh.PAPER_4FORMULAS, "delta_taxable_profits_musd",
                    "delta_taxable_profits_pct_posbase", _eh.TP_ABS, _eh.TP_PCT,
                    "fig02_taxable_profit_by_income.png", figures_dir, usd_decimals=0,
                    ghost_by_inc=ghost_by_inc)
    _eh.ig_twopanel(by_inc, excl, _eh.PAPER_4FORMULAS, _eh.REV_CIT, _eh.REV_CIT_PCT,
                    _eh.RV_ABS, _eh.RV_PCT, "fig03_tax_revenue.png", figures_dir,
                    usd_decimals=0, ghost_by_inc=ghost_by_inc)
    # Appendix B: by-world-region twins of Figs 2 & 3 (reported sample only).
    if by_region is not None:
        bdir = _eh.figdir_appendix_b()

        def _twins():
            _eh.ig_twopanel(by_region, excl, _eh.PAPER_4FORMULAS, "delta_taxable_profits_musd",
                            "delta_taxable_profits_pct_posbase", _eh.TP_ABS, _eh.TP_PCT,
                            "figB_taxable_profit_by_region.png", bdir, usd_decimals=0)
            _eh.ig_twopanel(by_region, excl, _eh.PAPER_4FORMULAS, _eh.REV_CIT, _eh.REV_CIT_PCT,
                            _eh.RV_ABS, _eh.RV_PCT, "figB_tax_revenue_by_region.png", bdir,
                            usd_decimals=0)
        _eh.region_figures(_twins)


# %% MARK: 3. Tables
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
                   pct_cols=_flabs, drop_base_col=True, pair_pct=True)
    _eh.emit_table(rev, order_iso, grp, grp_reg, sample,
                   "table3_tax_revenue_by_formula", tables_dir,
                   pct_base="current tax revenue from MNEs", pct_cols=_flabs,
                   pair_pct=True)

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
                   pct_base="total CIT revenue (OECD RSGLOBAL)", pct_cols=_flabs,
                   pair_pct=True)

    # verification: income-group sums of excl-resource revenue
    ig = _eh.income_group(sample)
    chk = excl_rev.groupby(excl_rev.index.map(ig)).sum().reindex(_eh.IG_ORDER)
    print(f"  [{sample}] excl-resource revenue change by income group ($m/yr): "
          + ", ".join(f"{str(k)[:3]}={v:,.0f}" for k, v in chk.items()))


def fig_revenue_ranges(figures_dir):
    """Fig 4 — plausible ranges of gains with different tax rates applied.

    Range per income group, reported sample, excl_resource, headline formula:
      conservative = both legs at effective tax rates (ETR-ETR, domfor);
      optimistic   = gains at max(CIT, ETR), losses valued at the bottom-10%
                     pair ETR — the rates of the most lightly taxed MNEs;
      diamond      = headline specification (gains at CIT/ETR-max, losses at ETR).
    The optimistic leg keeps the headline's gains pricing so the ladder is
    NESTED (conservative <= headline <= optimistic in every group).
    Built directly from script 5's spec files."""
    from _brand import RED, EARTH_GREEN, BLUE
    from config import deflator_to_base, estimates_dir
    YRS = _eh.AVG_YEARS
    DEFL = deflator_to_base()
    base = str(estimates_dir("reported_only", "excl_resource") / "tables" / "excl_resource") + "/"
    GRPL = {"low_income": "Low\nincome", "lower_middle_income": "Lower middle\nincome",
            "upper_middle_income": "Upper middle\nincome", "high_income": "High\nincome",
            "tax_haven": "Tax\nhavens"}
    ORDER = [GRPL[g] for g in ["low_income", "lower_middle_income",
                               "upper_middle_income", "high_income", "tax_haven"]]

    def _from_est(stub):
        f = _glob.glob(base + f"country_estimates__{stub}.csv")
        h = pd.read_csv(f[0], usecols=["iso_partner", "year", "revenue_gain_from_ut",
                                       "wb_income_group", "current_tax_paid_cash_musd"])
        h = h[h.year.isin(YRS)]
        g = h.wb_income_group.map(lambda v: GRPL.get(str(v), "other"))
        w = h.year.map(DEFL)
        rev = (h.revenue_gain_from_ut * w).groupby(g).sum().reindex(ORDER) / 1e3 / len(YRS)
        cash = (h.current_tax_paid_cash_musd * w).groupby(g).sum().reindex(ORDER) / 1e3 / len(YRS)
        return rev, cash

    try:
        cons, _ = _from_est("sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_etr_gain_etr")
        head, cash = _from_est("sales_employees_destmnedds__etrdef_domfor__etrmax_inf__loss_cit_gain_etr")
        mf = _glob.glob(base + "misalignment__sales_employees_destmnedds__etrdef_average"
                               "__etrmax_inf__losers_p10_gainers_avgetr.csv")[0]
    except (IndexError, FileNotFoundError) as e:
        print(f"  [skip Fig 4 ranges] spec file missing: {e}")
        return
    d = pd.read_csv(mf, usecols=lambda c: c in ["year", "misaligned_profit", "cit",
                    "wb_income_group", "etr_domfor_excl_resource",
                    "etr_partner_p10_excl_resource"], low_memory=False)
    d = d[d.year.isin(YRS)]
    m = d.misaligned_profit / 1e6
    g = d.wb_income_group.map(lambda v: GRPL.get(str(v), "other"))
    cit = pd.to_numeric(d["cit"], errors="coerce")
    domfor = pd.to_numeric(d["etr_domfor_excl_resource"], errors="coerce")
    p10 = pd.to_numeric(d["etr_partner_p10_excl_resource"], errors="coerce")
    v = (np.where(m < 0, -m, 0) * np.maximum(cit, domfor)
         - np.where(m > 0, m, 0) * p10) * d.year.map(DEFL)
    opt = v.groupby(g).sum().reindex(ORDER) / 1e3 / len(YRS)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.6))
    x = np.arange(len(ORDER))
    for ax, absolute in [(axes[0], True), (axes[1], False)]:
        den = 1.0 if absolute else cash / 100
        c, o, hd = cons / den, opt / den, head / den
        lo, hi = np.minimum(c, o), np.maximum(c, o)
        ax.bar(x, hi - lo, bottom=lo, width=0.55, color=PALETTE[0], alpha=0.6,
               edgecolor="none")
        ax.scatter(x, c, marker="_", s=650, color=RED, linewidths=3, zorder=3,
                   label="Conservative: gains and losses both at effective tax rates")
        ax.scatter(x, o, marker="_", s=650, color=EARTH_GREEN, linewidths=3, zorder=3,
                   label="Optimistic: losses valued at the bottom-10% effective rate "
                         "observed in each jurisdiction")
        ax.scatter(x, hd, marker="D", s=18, color=BLUE, zorder=4,
                   label="Headline: gains at statutory rates, losses at effective tax rates")
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels(ORDER, fontsize=9)
        ax.set_ylabel("Change in tax revenue (USD bn per year)" if absolute
                      else "% of MNE corporate cash tax currently paid")
        span = hi.max() - lo.min()
        ax.set_ylim(lo.min() - 0.18 * span, hi.max() + 0.22 * span)
        fmt = (lambda vv: f"{vv:,.0f}") if absolute else (lambda vv: f"{vv:,.0f}%")
        for xi in range(len(ORDER)):
            ax.annotate(fmt(c.iloc[xi]), (xi, c.iloc[xi]), textcoords="offset points",
                        xytext=(0, -13 if c.iloc[xi] <= o.iloc[xi] else 6),
                        ha="center", fontsize=8, color=RED)
            ax.annotate(fmt(o.iloc[xi]), (xi, o.iloc[xi]), textcoords="offset points",
                        xytext=(0, 6 if o.iloc[xi] >= c.iloc[xi] else -13),
                        ha="center", fontsize=8, color=EARTH_GREEN)
    axes[0].legend(fontsize=8, loc="upper left", framealpha=0.95)
    plt.tight_layout()
    plt.savefig(figures_dir / "fig04_tax_revenue_ranges.png", dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / 'fig04_tax_revenue_ranges.png'}")


# %% MARK: 4. Main
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
            by_region = (_sc.build_by_income(summary, gcol="region_tjn")
                         if sample == "reported_only" else None)
            formula_figures(sample, by_inc, ghost_by_inc=ghost, by_region=by_region)
            if sample == "reported_only":
                fig_revenue_ranges(_eh.figdir(sample))   # paper Figure 4
        formula_tables(sample, _eh.tabledir(sample))
    print("\nDone.")


if __name__ == "__main__":
    main()
