"""
9n — Yearly aggregate tax-revenue gain and the scale-up to global corporate profit.

Our estimate covers only the multinationals in the OECD country-by-country reporting
sample (groups above €750M consolidated revenue that are reported). To gauge the full
population effect we scale the yearly aggregate revenue gain by the ratio of global
corporate profit to the profit covered in our reported sample. The sample series is
computed at runtime from the analysis file (see reported_sample_profit_tn); the
corresponding coverage table in the draft is "Table C4. Coverage of global corporate
profits, 2016-2022" (Appendix C — formerly "Table 1"), which should show the SAME
corrected series this script computes.

Everything is expressed in constant BASE_YEAR US dollars (per-year US-GDP deflator,
config.deflator_to_base()). The scale factor is a same-year ratio (global ÷ covered),
so it is inflation-invariant; only the revenue-gain dollar series is deflated.

Headline spec: reported sample, sales_employees_destcfb (CFB), average ETR, ETR-CIT
(loss_cit_gain_etr, inf threshold). "Aggregate revenue gain" = sum of the positive
country-year revenue gains (the gains accruing to winning jurisdictions).

Output: output/unitary_taxation/reported_only/paper_figures/{figures,tables}/
Usage: python 9n_scaleup_yearly.py
"""
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = Path(os.path.dirname(_SRC))
sys.path.insert(0, _SRC)
import config  # noqa: E402
from _brand import apply_tjn_style, PALETTE, HATCH_CYCLE  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
apply_tjn_style()

# 2020 excluded in the headline (COVID outlier: low CbCR coverage inflates the
# scale-up). A *_with2020 variant of the table + figures is also written so the
# author can check whether the corrected coverage series tamed the 2020 spike
# (user 2026-07-12).
YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
YEARS_WITH_2020 = [2016, 2017, 2018, 2019, 2020, 2021, 2022]
DEFL = config.deflator_to_base()
HEADLINE, ETR, RATE, THRESH = "sales_employees_destmnedds", "domfor", "loss_cit_gain_etr", "inf"

# ── Global benchmark: profits of large (>=EUR750M) MNE groups ────────────────
# HEADLINE construction (user 2026-07-13, "OECD-anchored route"): observed OECD
# levels wherever the OECD publishes them, extension only afterwards.
#   2016       OECD (2020) EIA global profit matrix:            US$6,180bn
#   2017-2020  OECD WP68 (Hugger et al. 2024), Figure B.1
#              (total profit of large MNEs, adjusted for losses;
#              read off the chart by the author, consistent with the paper's
#              printed growth rates and its 2017-2020 average of 5,929):
#              5,900 / 6,230 / 6,134 / 5,451 bn
#   2021-2022  sample profits / coverage held at the 2020 RATE — the only
#              consistent extension: the corrected sample alone (8.1tn in
#              2021) exceeds any mild growth of the 5.45tn 2020 level, because
#              MNE profits boomed post-COVID. Holding coverage constant
#              assumes CbCR reporting completeness plateaued by 2020.
# Both anchor sources cover CbCR-threshold groups, which per OECD ORBIS
# analysis hold >90% of ALL MNE profit — so as an "all MNEs" benchmark the
# series is conservative by at most ~10%.
# W&Z's foreign-profit series (the former dynamics source) and their corporate
# profits (all firms incl. domestic-only) are kept as reference columns.
OECD_MNE_TN = {2016: 6.18, 2017: 5.90, 2018: 6.23, 2019: 6.134, 2020: 5.451}
WZ_FOREIGN_TN = {2016: 1.841, 2017: 2.061, 2018: 2.655, 2019: 2.590,
                 # 2019 x world-GDP index (0.973 / 1.112 / 1.157):
                 2020: 2.520, 2021: 2.880, 2022: 2.996}
GLOBAL_CORP_PROFIT_TN = {2016: 12.3, 2017: 13.0, 2018: 14.1, 2019: 14.5,
                         2020: 14.11, 2021: 16.12, 2022: 16.78}  # reference only


def reported_sample_profit_tn():
    """Per-year (sample_tn, foreign_share) of the ANALYSIS sample: reported rows
    only (is_distributed == 0), CORRECTED profit (the OECD adjusted-profit
    series where available + the GBJZ dividend corrections) — the series the
    estimation actually runs on. The foreign share (iso_parent != iso_partner)
    feeds the Route-1 gross-up of the W&Z foreign profits."""
    p = os.path.join(_ROOT, "data", "final", "cbcr_main_disaggregated.csv")
    d = pd.read_csv(p, low_memory=False,
                    usecols=["year", "is_distributed", "iso_parent", "iso_partner",
                             "profit_loss_before_income_tax_corrected"])
    r = d[d["is_distributed"] == 0].copy()
    r["v"] = pd.to_numeric(r["profit_loss_before_income_tax_corrected"],
                           errors="coerce")
    tot = r.groupby("year")["v"].sum()
    frn = r[r["iso_parent"] != r["iso_partner"]].groupby("year")["v"].sum()
    return ({int(y): float(x) / 1e12 for y, x in tot.items()},
            {int(y): float(frn[y] / tot[y]) for y in tot.index})


def main(years=YEARS, suffix="", rate=RATE, benchmark="oecd"):
    """benchmark: 'oecd' = HEADLINE (user 2026-07-13): OECD observed levels
                           2016-2020 (EIA 2016; WP68 Figure B.1 2017-2020),
                           2021-22 extended by holding coverage at the 2020
                           rate (justified: reporting jurisdictions plateaued
                           at 52/52/53 from 2020, so post-2020 sample growth
                           is profit, not coverage);
                  'wz'   = former construction (OECD 2016 level x W&Z
                           foreign-profit growth) — kept as the _wzgrowth
                           reference variant."""
    tables_dir, figures_dir = config.output_dirs("unitary_taxation_excl_resource_reported")
    figures_dir = _ROOT / "output" / "unitary_taxation" / "reported_only" / "paper_figures" / "figures"
    tables_dir = _ROOT / "output" / "unitary_taxation" / "reported_only" / "paper_figures" / "tables"
    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(tables_dir, exist_ok=True)

    p = os.path.join(_ROOT, "output", "unitary_taxation", "reported_only",
                     "excl_resource", "tables", "summary_country_year_long.csv")
    d = pd.read_csv(p, low_memory=False)
    d = d[(d.formula_name == HEADLINE) & (d.etr_name == ETR) & (d.rate_mode == rate)]
    if d["etr_threshold"].astype(str).nunique() > 1:
        d = d[d["etr_threshold"].astype(str) == THRESH]
    d = d[d["year"].isin(years)]

    sample_tn, foreign_share = reported_sample_profit_tn()
    # 'oecd' benchmark 2021-22 extension: coverage held at the 2020 rate.
    _cov2020 = sample_tn[2020] / OECD_MNE_TN[2020]
    rows = []
    for y in years:
        s = d[d["year"] == y]
        f = DEFL[y]
        winners = s.loc[s["revenue_gain_from_ut"] > 0, "revenue_gain_from_ut"].sum() * f / 1e3  # $bn, constant BASE_YEAR
        net = s["revenue_gain_from_ut"].sum() * f / 1e3
        if benchmark == "oecd":
            global_mne_tn = (OECD_MNE_TN[y] if y in OECD_MNE_TN
                             else sample_tn[y] / _cov2020)
        else:   # headline: OECD 2016 level x W&Z foreign-profit dynamics
            global_mne_tn = (OECD_MNE_TN[2016]
                             * WZ_FOREIGN_TN[y] / WZ_FOREIGN_TN[2016])
        route1_tn = WZ_FOREIGN_TN[y] / foreign_share[y]      # reference (lower bound)
        # scale/coverage are same-year nominal ratios (deflator cancels); the
        # PROFIT columns are reported in constant BASE_YEAR USD like every other
        # monetary value in the paper (user 2026-07-12) — hence the x f below.
        scale = global_mne_tn / sample_tn[y]
        rows.append(dict(year=y,
                         revenue_gain_winners_bn=winners,
                         revenue_gain_net_bn=net,
                         global_mne_profit_tn=round(global_mne_tn * f, 2),
                         wz_foreign_profit_tn=round(WZ_FOREIGN_TN[y] * f, 2),
                         route1_mne_profit_tn=round(route1_tn * f, 2),    # reference
                         sample_foreign_share=round(foreign_share[y], 3),
                         global_corp_profit_tn=round(GLOBAL_CORP_PROFIT_TN[y] * f, 2),
                         reported_sample_tn=round(sample_tn[y] * f, 2),
                         coverage=sample_tn[y] / global_mne_tn,
                         scale_factor=scale,
                         scaled_up_winners_bn=winners * scale,
                         scaled_up_net_bn=net * scale))
    out = pd.DataFrame(rows).round(2)
    csv = tables_dir / f"scaleup_yearly{suffix}.csv"
    out.to_csv(csv, index=False)
    print(out.to_string(index=False))
    print(f"\nwrote {csv}")

    # ── two figures: (a) gross winners' gains, (b) net gain — each with the
    #    CBCR-sample and scaled-to-global versions. Colour + hatch (colour-blind safe). ──
    x = np.arange(len(years))

    def _two_series_fig(sample_col, scaled_col, ylabel, title, fname):
        bw = 0.38
        fig, ax = plt.subplots(figsize=(11, 5.4))
        for mult, col, colour, hatch, lab in [
            (-0.5, sample_col, PALETTE[3], HATCH_CYCLE[0],
             "Sample for which we have country-by-country reporting data"),
            (+0.5, scaled_col, PALETTE[0], HATCH_CYCLE[1], "Scaled to global multinational profit"),
        ]:
            b = ax.bar(x + mult * bw, out[col], width=bw, color=colour,
                       hatch=hatch, edgecolor="white", linewidth=0.4, label=lab)
            ax.bar_label(b, labels=[f"{v:,.0f}" for v in out[col]],   # whole $bn, thousands comma
                         fontsize=12, padding=2, rotation=90)
        ax.set_xticks(x)
        # Year + that year's sample coverage of global multinational profit —
        # makes the scale-up visible in the figure itself: low-coverage years
        # (2016: 18%) carry a larger multiplier (user 2026-07-12).
        ax.set_xticklabels([f"{y}\n({c:.0%} covered)"
                            for y, c in zip(years, out["coverage"])], fontsize=11)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.tick_params(axis="y", labelsize=11)
        ax.margins(y=0.12)          # headroom for the rotated bar labels
        # No title — added downstream in LaTeX/Overleaf.
        # Legend ABOVE the axes so it can never overlap the bars.
        ax.legend(fontsize=12, framealpha=0.85, loc="lower left",
                  bbox_to_anchor=(0.0, 1.01), borderaxespad=0)
        plt.tight_layout()
        fpath = figures_dir / fname
        plt.savefig(fpath, dpi=130, bbox_inches="tight")
        plt.close()
        print(f"wrote {fpath}")

    _two_series_fig("revenue_gain_winners_bn", "scaled_up_winners_bn",
                    "Aggregate revenue gain to winners (USD bn)",
                    f"Gross revenue gain to winners per year (constant {config.BASE_YEAR} USD)",
                    f"fig_scaleup_gross_yearly{suffix}.png")
    _two_series_fig("revenue_gain_net_bn", "scaled_up_net_bn",
                    "Aggregate NET revenue gain (winners − losers, USD bn)",
                    f"Net revenue gain per year (constant {config.BASE_YEAR} USD)",
                    f"fig_scaleup_net_yearly{suffix}.png")


if __name__ == "__main__":
    # HEADLINE figures INCLUDE 2020 (user 2026-07-13: with the OECD-anchored
    # benchmark the 2020 estimate is mid-range, and it now has an OECD-observed
    # 2020 anchor — shown for completeness with a caution note; 2020 remains
    # EXCLUDED from every other analysis).
    main(years=YEARS_WITH_2020)
    main(suffix="_excl2020")   # the former headline window, kept for reference
    # ETR-ETR mirror for the conservative-rates appendix (both legs at ETR).
    main(years=YEARS_WITH_2020, suffix="_etretr", rate="loss_etr_gain_etr")
    # Former benchmark (OECD 2016 level x W&Z foreign-profit growth) — kept as
    # a reference variant after the OECD-anchored series became the headline
    # (user 2026-07-13).
    main(years=YEARS_WITH_2020, suffix="_wzgrowth", benchmark="wz")
