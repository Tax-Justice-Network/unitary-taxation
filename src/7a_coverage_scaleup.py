# %%
"""
7a — Coverage and scale-up to all multinationals.

Aggregates the yearly net tax-revenue gain across all jurisdictions and scales
it from the reporting sample up to all multinationals worldwide, multiplying
each year by the ratio of global multinational profit to the profit the sample
covers. Global multinational profit is taken from OECD estimates wherever they
are published — the OECD (2020) EIA global-profit matrix for 2016 and OECD WP68
(Hugger et al., 2024, Figure B.1) for 2017–2020 — and extended to 2021–2022 by
holding the sample's coverage ratio at its 2020 level. The scale factor is a same-year ratio, so it is
inflation-invariant; only the dollar revenue series is deflated.

Headline specification: reported-only sample, resources excluded, employees + destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at statutory CIT and losses at ETR, per-year average over 2016–2022 (2020 excluded), constant 2025 US$.

Exhibit script — consumes the script-6 estimation summaries. Produces Figure 1
(global net revenue gains, per year) + the coverage / scale-up table (Appendix B,
Table B4) and the ghost-bar scale factors reused by 7b / 7c / 7e. Runs as first of the exhibits.

Reads:
  {data_final}/cbcr_main_disaggregated.csv                              — sample profit base (unrelated-party revenue, corrected profit)
  output/estimates/reported_only/2_resources_excluded/tables/summary_country_year_long.csv — per-country net revenue gain (script 6)
  output/estimates/reported_only/2_resources_excluded/tables/…/country_estimates__*.csv, misalignment__*.csv — per-spec detail for Figure 1

Writes:
  output/paper/main_text/scaleup_yearly.csv                             — per-year coverage + scale factors (feeds 7b/7c/7e ghost bars)
  output/paper/main_text/fig01_global_revenue_gains.png/.pdf            — Figure 1 (net, stacked ranges)
  output/paper/main_text/fig01b_global_revenue_gains_gainers.png/.pdf   — Figure 1b (gainers only)

Usage:
  python 7a_coverage_scaleup.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
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

# %% MARK: 2. Config and constants
# 2020 is EXCLUDED from every headline ESTIMATE (COVID outlier: low CbCR
# coverage inflates the scale-up) — that is the six-year window every other
# script averages over. Figure 1, however, is a per-YEAR series and always
# INCLUDES 2020: the headline coverage table (scaleup_yearly.csv) is written on
# YEARS_WITH_2020 so the yearly figure can show the whole 2016-2022 series and
# the 2020 dip. A *_excl2020 variant of the table is also written for reference.
YEARS_WITH_2020 = [
    2016,
    2017,
    2018,
    2019,
    2020,
    2021,
    2022,
]  # the per-year figure window
YEARS = [2016, 2017, 2018, 2019, 2021, 2022]  # the estimate window (2020 out)
DEFL = config.deflator_to_base()
HEADLINE, ETR, RATE, THRESH = (
    "sales_employees_destmnedds",
    "domfor",
    "loss_cit_gain_etr",
    "inf",
)

# ── Global benchmark: profits of large (>=EUR750M) MNE groups ────────────────
# HEADLINE construction (OECD-anchored route): observed OECD
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
# series is conservative by at most ~10%. Global MNE profit is the ONLY
# comparator used for coverage/scale-up (no total-corporate-profit reference).
OECD_MNE_TN = {2016: 6.18, 2017: 5.90, 2018: 6.23, 2019: 6.134, 2020: 5.451}


# %% MARK: 3. Sample loaders
def _load_frame():
    p = os.path.join(_ROOT, "data", "final", "cbcr_main_disaggregated.csv")
    return pd.read_csv(
        p,
        low_memory=False,
        usecols=[
            "year",
            "is_distributed",
            "iso_parent",
            "iso_partner",
            "profit_loss_before_income_tax_corrected",
            "unrelated_party_revenues",
        ],
    )


def _reported_estimate_sample(df):
    """Reproduce script 5's REPORTED_ONLY sample exactly, so the coverage
    numerator is the profit the estimation actually runs on:
      (1) partial-reporter rule — drop each (parent, year) whose foreign
          unrelated-party revenue is > 50% in aggregate (is_distributed==1) rows;
      (2) keep is_distributed == 0;
      (3) drop bad-reporter parents left with only their domestic row."""
    f = df[df["iso_partner"] != df["iso_parent"]]
    upr = pd.to_numeric(f["unrelated_party_revenues"], errors="coerce").fillna(0.0)
    agg = upr.where(f["is_distributed"] == 1, 0.0)
    tot = upr.groupby([f["iso_parent"], f["year"]]).sum()
    sh = agg.groupby([f["iso_parent"], f["year"]]).sum() / tot.where(tot > 0)
    flagged = set(sh[sh > 0.5].index)
    key = pd.MultiIndex.from_arrays([df["iso_parent"], df["year"]])
    df = df[~key.isin(flagged)].copy()
    df = df[df["is_distributed"] == 0].copy()
    cross = df.loc[df["iso_partner"] != df["iso_parent"], "iso_parent"].unique()
    return df[df["iso_parent"].isin(cross)].copy()


def reported_sample_profit_tn():
    """Per-year (sample_tn, foreign_share) of the ANALYSIS sample — the exact
    reported-only estimation sample (partial-reporter + bad-reporter filtered,
    2026-07-25), CORRECTED profit. The foreign share (iso_parent != iso_partner)
    is returned for reference only (no longer consumed)."""
    r = _reported_estimate_sample(_load_frame())
    r["v"] = pd.to_numeric(
        r["profit_loss_before_income_tax_corrected"], errors="coerce"
    )
    tot = r.groupby("year")["v"].sum()
    frn = r[r["iso_parent"] != r["iso_partner"]].groupby("year")["v"].sum()
    return (
        {int(y): float(x) / 1e12 for y, x in tot.items()},
        {int(y): float(frn[y] / tot[y]) for y in tot.index},
    )


def disaggregated_sample_profit_tn():
    """Per-year profit ($tn) of the DISAGGREGATED (gravity) sample the appendix
    runs on: all real-country rows, reported + imputed (is_distributed 0 and 1).
    Badly-reporting parents ARE covered here — their aggregate rows are imputed
    into individual countries — so, unlike the reported-only sample, no
    partial-reporter / bad-reporter drop applies."""
    d = _load_frame()
    v = pd.to_numeric(d["profit_loss_before_income_tax_corrected"], errors="coerce")
    g = v.groupby(d["year"]).sum()
    return {int(y): float(x) / 1e12 for y, x in g.items()}


# %% MARK: 4. Coverage scale-up table
def main(years=YEARS, suffix="", rate=RATE):
    """Global MNE profit = OECD observed levels 2016-2020 (EIA 2016; WP68
    Figure B.1 2017-2020), 2021-22 extended by holding coverage at the 2020
    rate (justified: reporting jurisdictions plateaued at 52/52/53 from 2020,
    so post-2020 sample growth is profit, not coverage)."""
    tables_dir, figures_dir = config.output_dirs("paper/main_text")

    p = os.path.join(
        str(config.estimates_dir("reported_only", "excl_resource")),
        "tables",
        "summary_country_year_long.csv",
    )
    d = pd.read_csv(p, low_memory=False)
    d = d[(d.formula_name == HEADLINE) & (d.etr_name == ETR) & (d.rate_mode == rate)]
    if d["etr_threshold"].astype(str).nunique() > 1:
        d = d[d["etr_threshold"].astype(str) == THRESH]
    d = d[d["year"].isin(years)]

    sample_tn, _ = reported_sample_profit_tn()
    # 2021-22 extension: coverage held at the 2020 rate.
    _cov2020 = sample_tn[2020] / OECD_MNE_TN[2020]
    rows = []
    for y in years:
        s = d[d["year"] == y]
        f = DEFL[y]
        winners = (
            s.loc[s["revenue_gain_from_ut"] > 0, "revenue_gain_from_ut"].sum() * f / 1e3
        )  # $bn, constant BASE_YEAR
        net = s["revenue_gain_from_ut"].sum() * f / 1e3
        global_mne_tn = OECD_MNE_TN[y] if y in OECD_MNE_TN else sample_tn[y] / _cov2020
        # scale/coverage are same-year nominal ratios (deflator cancels); the
        # PROFIT columns are reported in constant BASE_YEAR USD like every other
        # monetary value in the paper — hence the x f below.
        scale = global_mne_tn / sample_tn[y]
        rows.append(
            dict(
                year=y,
                revenue_gain_winners_bn=winners,
                revenue_gain_net_bn=net,
                global_mne_profit_tn=round(global_mne_tn * f, 2),
                reported_sample_tn=round(sample_tn[y] * f, 2),
                coverage=sample_tn[y] / global_mne_tn,
                scale_factor=scale,
                scaled_up_winners_bn=winners * scale,
                scaled_up_net_bn=net * scale,
            )
        )
    out = pd.DataFrame(rows).round(2)
    csv = tables_dir / f"scaleup_yearly{suffix}.csv"
    out.to_csv(csv, index=False)
    print(out.to_string(index=False))
    print(f"\nwrote {csv}")
    # main() writes ONLY the coverage/scale-up TABLE (scaleup_yearly.csv); the
    # per-year figures are Figure 1 / 1b, drawn by fig_global_range() below.


# %% MARK: 5. Figure 1 — global revenue gains
# ─── Paper Figure 1: global NET revenue gains, per year, stacked ranges ──────
def fig_global_range(mode="net"):
    """Figure 1 — 'Global revenue gains from unitary taxation'.

    mode="net"     → Figure 1  (fig01): the NET revenue gain (winners − losers).
    mode="winners" → Figure 1b (fig01b): only the countries that GAIN — the
                     gross revenue gain summed over gaining countries, with the
                     loss leg dropped from every series (headline, conservative,
                     optimistic). Useful when we want the size of the upside
                     alone, not netted against the havens' losses.

    Per year (2016-2022 incl. 2020), the estimate as ONE bar:
      headline bar   the headline specification (sample);
      whisker down   conservative (both legs at effective tax rates) — the firm floor;
      whisker up     optimistic (gains at max(CIT, ETR); for the net figure,
                     losses at the bottom-10% pair ETR) — the rate-assumption range;
      +scaled bar    the same, scaled to global MNE profit (7a scale factors).
    So the bar reports the in-estimate uncertainty PLUS the scale-up in one glyph."""
    import glob as _glob
    from _brand import BLUE, EARTH_GREEN

    tables_dir, figures_dir = config.output_dirs("paper/main_text")
    sc = pd.read_csv(tables_dir / "scaleup_yearly.csv").set_index("year")
    SF, COV = sc["scale_factor"].to_dict(), sc["coverage"].to_dict()
    years = YEARS_WITH_2020
    base = (
        str(
            config.estimates_dir("reported_only", "excl_resource")
            / "tables"
            / "excl_resource"
        )
        + "/"
    )

    def _net(stub):
        f = _glob.glob(base + f"country_estimates__{stub}.csv")
        h = pd.read_csv(f[0], usecols=["year", "revenue_gain_from_ut"])
        h = h[h.year.isin(years)]
        g = h["revenue_gain_from_ut"]
        if mode == "winners":  # gainers only: drop the losing countries
            g = g.where(g > 0, 0.0)
        w = g.groupby(h["year"]).sum()
        return (w * pd.Series(DEFL)).reindex(years) / 1e3  # $bn constant BASE_YEAR

    cons = _net(f"{HEADLINE}__etrdef_{ETR}__etrmax_{THRESH}__loss_etr_gain_etr")
    head = _net(f"{HEADLINE}__etrdef_{ETR}__etrmax_{THRESH}__loss_cit_gain_etr")
    mf = _glob.glob(
        base + f"misalignment__{HEADLINE}__etrdef_average"
        f"__etrmax_{THRESH}__losers_p10_gainers_avgetr.csv"
    )[0]
    d = pd.read_csv(
        mf,
        usecols=lambda c: c
        in [
            "year",
            "misaligned_profit",
            "cit",
            "etr_domfor_excl_resource",
            "etr_partner_p10_excl_resource",
        ],
        low_memory=False,
    )
    d = d[d.year.isin(years)]
    m = d.misaligned_profit / 1e6
    cit = pd.to_numeric(d["cit"], errors="coerce")
    domfor = pd.to_numeric(d["etr_domfor_excl_resource"], errors="coerce")
    p10 = pd.to_numeric(d["etr_partner_p10_excl_resource"], errors="coerce")
    v_gain = np.where(m < 0, -m, 0) * np.maximum(cit, domfor)  # the gain leg
    v = v_gain if mode == "winners" else v_gain - np.where(m > 0, m, 0) * p10
    opt = (pd.Series(v).groupby(d["year"].values).sum() * pd.Series(DEFL)).reindex(
        years
    ) / 1e3
    sf = pd.Series(SF).reindex(years)
    opt_sc = opt * sf

    x = np.arange(len(years))
    bw = 0.38
    fig, ax = plt.subplots(figsize=(11, 5.6))
    from matplotlib.patches import Patch

    # Cap the axis just above the tallest BAR so the headline bars set the
    # scale; whiskers reaching further are clipped and labelled with an arrow.
    _ymax = 1.30 * float(max(head.max(), (head * sf).max()))
    for mult, colour, hatch, lab, c, o, h in [
        (
            -0.5,
            PALETTE[3],
            HATCH_CYCLE[0],
            "Sample for which we have country-by-country reporting data",
            cons,
            opt,
            head,
        ),
        (
            +0.5,
            PALETTE[0],
            HATCH_CYCLE[1],
            "Scaled to global multinational profit",
            cons * sf,
            opt * sf,
            head * sf,
        ),
    ]:
        xs = x + mult * bw
        # THE bar = our (headline) estimate; the rate-assumption range around it
        # (down to conservative, up to optimistic) as a whisker.
        b = ax.bar(
            xs,
            h,
            width=bw,
            color=colour,
            hatch=hatch,
            edgecolor="white",
            linewidth=0.4,
            label=lab,
        )
        ax.errorbar(
            xs,
            h,
            yerr=[np.asarray(h - c), np.asarray(o - h)],
            fmt="none",
            ecolor="#b8b8b8",
            elinewidth=1.0,
            capsize=4,
            capthick=1.0,
            zorder=2,
        )
        for xi, (cv, ov, hv) in enumerate(zip(c, o, h)):
            ax.annotate(
                f"{hv:,.0f}",
                (xs[xi], hv),
                textcoords="offset points",
                xytext=(-4, 5),
                ha="right",
                fontsize=9,
                color="black",
                fontweight="bold",
            )
            ax.annotate(
                f"{cv:,.0f}",
                (xs[xi], cv),
                textcoords="offset points",
                xytext=(0, -11),
                ha="center",
                fontsize=7.5,
                color="white",
                bbox=dict(
                    boxstyle="round,pad=0.15", facecolor=colour, edgecolor="none"
                ),
            )
            if ov <= _ymax:
                ax.annotate(
                    f"{ov:,.0f}",
                    (xs[xi], ov),
                    textcoords="offset points",
                    xytext=(0, 4),
                    ha="center",
                    fontsize=7.5,
                    color="#8a8a8a",
                )
            else:  # whisker runs off the top of the capped axis
                ax.annotate(
                    f"↑{ov:,.0f}",
                    (xs[xi], _ymax),
                    textcoords="offset points",
                    xytext=(-3, -10),
                    ha="right",
                    fontsize=7.5,
                    color="#8a8a8a",
                )
    _h, _l = ax.get_legend_handles_labels()
    _h += [
        plt.Line2D([], [], color="#b8b8b8", linewidth=1.0, marker="_", markersize=8),
        Patch(facecolor="none", edgecolor="none"),
    ]  # blank handle: 2nd line
    _l += [
        "Range from conservative to optimistic assumptions about how",
        "the shifted profits are currently taxed and will be taxed (see Box 3)",
    ]
    ax.legend(
        _h,
        _l,
        fontsize=9,
        framealpha=0.85,
        loc="lower left",
        bbox_to_anchor=(0.0, 1.01),
        borderaxespad=0,
        ncol=2,
    )
    ax.set_xticks(x)
    ax.set_xticklabels([f"{y}\n({COV[y]:.0%} covered)" for y in years], fontsize=11)
    ax.set_ylabel(
        (
            "Revenue gain to gaining countries (USD bn)"
            if mode == "winners"
            else "Net revenue gain (USD bn)"
        ),
        fontsize=12,
    )
    ax.tick_params(axis="y", labelsize=11)
    ax.set_ylim(0, _ymax)
    plt.tight_layout()
    fname = (
        "fig01b_global_revenue_gains_gainers.png"
        if mode == "winners"
        else "fig01_global_revenue_gains.png"
    )
    fpath = figures_dir / fname
    plt.savefig(fpath, dpi=130, bbox_inches="tight")
    plt.close()
    print(f"wrote {fpath}")


# %% MARK: 6. Run
if __name__ == "__main__":
    # The coverage/scale-up TABLE (scaleup_yearly.csv). INCLUDES 2020 (the
    # per-year figures show the whole 2016-2022 series; 2020 stays EXCLUDED
    # from every other analysis).
    main(years=YEARS_WITH_2020)
    # The ONLY two figures: Figure 1 (net) and Figure 1b (gaining countries
    # only). Both read the headline scaleup_yearly.csv written above.
    fig_global_range(mode="net")
    fig_global_range(mode="winners")
