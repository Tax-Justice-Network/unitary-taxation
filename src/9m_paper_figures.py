"""
9m — Paper figures (clean captions) for the Results section + Appendix E.

Reuses the machinery in `9_three_scenario_figures.py` (which itself builds on
`8_five_scenario_report.py`): `build_summary` → per-(scenario, formula, country)
rows; `build_by_income` → income-group aggregation with the positive-base %;
`make_figure` / `_scenario_comparison_fig` do the grouped-bar plotting. Here we
only supply PAPER-STYLE titles (metric-first bold line + a gray details subtitle;
no "Scenario:"/"S1/S2/S3"/"ignorant" in titles) and the exact figure set the paper
needs (author's Figure 1–11), on the REPORTED sample (main text) and a gravity
duplicate set (Appendix E).

Headline formula = sales_employees_destcfb ("Sales & employees", CFB destination); ETR family
= average; revenue at ETR-CIT (recCIT_forgETR) = gains at statutory CIT, losses at
ETR; ETR-ETR (recETR_forgETR) shown once for the revenue robustness panel. Window
2016–2022.

Outputs PNGs to  output/unitary_taxation/<sample>/paper_figures/figures/
  reported_only:  fig01…fig11   gravity:  fig01…fig10 (no country examples / consolidation)

Usage: python 9m_paper_figures.py
"""
import importlib.util
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

_SRC = Path(__file__).resolve().parent
_ROOT = _SRC.parent
from _brand import apply_tjn_style, HATCH_CYCLE, PALETTE  # noqa: E402

# ── Load script 9 (which loads script 8) so we reuse its plotting functions. ──
_spec = importlib.util.spec_from_file_location(
    "_three_scenario_figures", str(_SRC / "9_three_scenario_figures.py"))
_s9 = importlib.util.module_from_spec(_spec)
sys.modules["_three_scenario_figures"] = _s9
_spec.loader.exec_module(_s9)
_s8 = sys.modules["_five_scenario_report"]

apply_tjn_style()

# Express all multi-year aggregates in constant BASE_YEAR US dollars (per-year deflated).
_s8._DEFLATE_TO_BASE = True

build_summary = _s8.build_summary
build_by_income = _s9.build_by_income
make_figure = _s9.make_figure
scenario_comparison_fig = _s9._scenario_comparison_fig
FORMULA_COLOURS = _s8.FORMULA_COLOURS
INCOME_GROUP_ORDER = _s8.INCOME_GROUP_ORDER
INCOME_GROUP_LABELS = _s8.INCOME_GROUP_LABELS

# Paper deliverables report the PER-YEAR AVERAGE over these years (2020 excluded as
# the COVID outlier); build_summary divides the summed monetary columns by n years.
YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
WINDOW = "yearly avg 2016–2022 (excl. 2020)"
_s9.WINDOW_LABEL = WINDOW
# Paper-style footnote for the floored bars (script 9's default says "Scenario 3").
_s9.FLOOR_NOTE = (
    "The '+ minimum royalty' bars add the IGF-ATAF minimum-royalty floor (hatched portion) "
    "as a separate government-revenue stream on top of the unitary-taxation yield.")

# Headline destination concept (2026-07-12, user): the COMPLETE broadened
# measure — all destination-based sales by MNEs (all AAMNE sectors incl.
# finance) + digitally-DELIVERABLE services imports (BaTIS, Handbook def.) +
# the netted ad-funded ADS slice (x0.20).
HEADLINE = "sales_employees_destmnedds"

# The four apportionment formulas shown in the by-income figures, all on the
# complete destination measure so the family comparison is like-for-like.
PAPER_4FORMULAS = [
    ("sales_employees_destmnedds", "Sales & employees"),
    ("ccctb_destmnedds", "CCCTB"),
    ("three_factors_destmnedds", "Three-factor"),
    ("double_weighted_sales_destmnedds", "Double-weighted sales"),
]
# Destination-concept comparison (Fig 8/9), all on the sales+employees base.
# Final set (user 2026-07-12): destination (the complete headline measure),
# its nexus variant, and origin — the classic three-way comparison, now on the
# corrected destination measure. The ablations (without ADS / without digital
# services) stay available in the tables/robustness, not in the figure.
FIG8_MEASURES = [
    ("sales_employees_destmnedds", "Destination-based"),
    ("sales_employees_destmnedds_nexus", "Destination + nexus"),
    ("sales_employees", "Origin-based"),
]
FIG9_MEASURES = list(FIG8_MEASURES)
# Ablation of the destination measure (user 2026-07-12): the headline measure
# (MNE sales + MNE share of digitally-deliverable imports), then stripping all
# digital services, then the old consumer-facing-only concept. (The ADS-proxy
# bar disappeared with the leg's retirement the same day.)
ABLATION_MEASURES = [
    ("sales_employees_destmnedds", "Complete measure"),
    ("sales_employees_destmne", "Without digital services"),
    ("sales_employees_destcfb", "Consumer-facing only"),
]
# (The old Fig 10 — CFB digital-measure variants — was dropped 2026-07-12: the
# destination-concept comparison now lives in Figs 8–9.)
# All formula keys build_summary must load so every figure can select what it needs.
_ALL_KEYS = []
for _lst in (PAPER_4FORMULAS, FIG8_MEASURES, FIG9_MEASURES, ABLATION_MEASURES):
    for k, _l in _lst:
        if k not in _ALL_KEYS:
            _ALL_KEYS.append(k)
ALL_FORMULAS = [(k, k) for k in _ALL_KEYS]   # labels overridden per figure

# Paper scenario legend labels (no "S1/S2/S3").
SCEN_LABEL_PAPER = {
    "ignorant_reported": "Ignore resource rights",
    "excl_reported": "Resource rights prior to taxing rights",
    "excl_floored_reported": "+ Minimum royalty",
    "ignorant_gravity": "Ignore resource rights",
    "excl_gravity": "Resource rights prior to taxing rights",
    "excl_floored_gravity": "+ Minimum royalty",
}

# Written-out, capitalised income-group tick labels (two lines to avoid overlap).
IG_LABELS_LC = {
    "low_income": "Low\nincome", "lower_middle_income": "Lower middle\nincome",
    "upper_middle_income": "Upper middle\nincome", "high_income": "High\nincome",
    "investment_hub": "Tax\nhavens",   # relabelled from "Investment hub" (user 2026-07-13)
}
_s9.INCOME_GROUP_LABELS = IG_LABELS_LC
INCOME_GROUP_LABELS = IG_LABELS_LC

# Scenario dicts (reused from 8/9c but with the wide formula set loaded).
SCN_REPORTED = [dict(s, formulas=ALL_FORMULAS)
                for s in _s8.SCENARIOS_REPORTED[:3]]
SCN_GRAVITY = [
    {"key": "ignorant_gravity", "label": "Resources ignored (baseline)",
     "topic": "unitary_taxation_disaggregated", "sample": "disaggregated",
     "formulas": ALL_FORMULAS},
    {"key": "excl_gravity", "label": "Profits corrected for resource rent capture",
     "topic": "unitary_taxation_excl_resource", "sample": "excl_resource",
     "formulas": ALL_FORMULAS},
    {"key": "excl_floored_gravity",
     "label": "Profits corrected for resource rent capture + min. royalty floor",
     "topic": "unitary_taxation_excl_resource_floored", "sample": "excl_resource_floored",
     "formulas": ALL_FORMULAS},
]

REV_CIT = "delta_total_gvt_revenue_recCIT_forgETR_musd"      # gains at CIT, losses at ETR
REV_ETR = "delta_total_gvt_revenue_recETR_forgETR_musd"      # both at ETR
REV_CIT_PCT = "delta_total_gvt_revenue_recCIT_forgETR_pct_revenue"
REV_ETR_PCT = "delta_total_gvt_revenue_recETR_forgETR_pct_revenue"


def _figdir(sample):
    d = _ROOT / "output" / "unitary_taxation" / sample / "paper_figures" / "figures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _scen(scn_list, key, formulas, label=None):
    base = next(s for s in scn_list if s["key"] == key)
    return dict(base, formulas=formulas, label=label or base["label"])


# ─── Country-example helpers (Fig 5, Fig 7) ──────────────────────────────────
def _country_panel(ax, summary, iso, scen_keys, value_col, ylabel, title):
    """x = scenarios, grouped bars = the four paper formulas, one country+metric."""
    sub = summary[summary["iso_partner"] == iso]
    fkeys = [k for k, _ in PAPER_4FORMULAS]
    flabs = [l for _, l in PAPER_4FORMULAS]
    piv = (sub.pivot_table(index="scenario", columns="formula_name",
                           values=value_col, aggfunc="first")
           .reindex(scen_keys)[[k for k in fkeys]])
    x = np.arange(len(scen_keys))
    n = len(fkeys)
    bw = 0.82 / n
    for i, k in enumerate(fkeys):
        vals = piv[k].values / 1e3
        ax.bar(x + (i - (n - 1) / 2) * bw, vals, width=bw, color=FORMULA_COLOURS[i],
               hatch=HATCH_CYCLE[i % len(HATCH_CYCLE)],   # colour-blind redundancy
               edgecolor="white", linewidth=0.3)
    ax.axhline(0, color="grey", linewidth=0.5)
    # Headroom so all-positive panels (e.g. Mali) don't fill the frame to the top.
    _ymin, _ymax = ax.get_ylim()
    _rng = (_ymax - _ymin) or 1.0
    ax.set_ylim(_ymin - (0.06 * _rng if _ymin < 0 else 0.0), _ymax + 0.18 * _rng)
    ax.set_xticks(x)
    ax.set_xticklabels(["\n".join(textwrap.wrap(SCEN_LABEL_PAPER.get(k, k), 20))
                        for k in scen_keys], fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12)
    handles = [plt.Rectangle((0, 0), 1, 1, facecolor=FORMULA_COLOURS[i],
                             hatch=HATCH_CYCLE[i % len(HATCH_CYCLE)],
                             edgecolor="white", linewidth=0.3) for i in range(n)]
    ax.legend(handles, flabs, fontsize=8, loc="best", framealpha=0.85)


# Panel titles (the ONLY text baked into the figure image; the overall title and
# the explanatory note live in the Word caption).
TP_ABS = "Change in taxable profit (USD bn)"
TP_PCT = "% of current profit base"
RV_ABS = "Change in tax revenue (USD bn)"
RV_PCT = "% of current corporate tax paid"


def _ig_twopanel(by_inc, scen_key, formulas, abs_col, pct_col, abs_title, pct_title,
                 fname, figures_dir, usd_decimals=1, overall_title=None):
    """Two panels (absolute | %), income groups on x, one bar per formula/measure.

    Always writes the untitled `fname` (the version the Word caption titles). If
    `overall_title` is given, ALSO writes a second `<stem>_titled.png` with that
    title baked in as a bold suptitle — a standalone version for slides / the web
    where no caption supplies the title."""
    fkeys = [k for k, _ in formulas]
    flabs = [l for _, l in formulas]
    # Full brand palette (6 colours) — the measure-comparison figures carry
    # five series, more than FORMULA_COLOURS holds.
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(fkeys))]
    scen = {"key": scen_key}
    pa = _s9._pivot(by_inc, scen, abs_col, fkeys)
    pp = _s9._pivot(by_inc, scen, pct_col, fkeys)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    _s9._grouped_bars(axes[0], pa / 1e3, flabs, colors, ylabel="", title=abs_title,
                      usd_decimals=usd_decimals)
    _s9._grouped_bars(axes[1], pp, flabs, colors, ylabel="", title=pct_title, is_pct=True)
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=130)
    if overall_title:
        fig.suptitle(overall_title, fontsize=14, fontweight="bold")
        fig.tight_layout(rect=[0, 0, 1, 0.93])
        titled = figures_dir / (Path(fname).stem + "_titled.png")
        plt.savefig(titled, dpi=130)
        print(f"  wrote {titled}")
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def _scen_twopanel(by_inc, formula_key, scen_keys, scen_labels, abs_col, pct_col,
                   abs_title, pct_title, with_addon, fname, figures_dir,
                   usd_decimals=1):
    """Two panels, income groups on x, one bar per resource treatment (scenario).
    with_addon hatches the minimum-royalty floor add-on on the floored bar."""
    sub = by_inc[by_inc["formula_name"] == formula_key]
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    _s9._scenario_comparison_panel(axes[0], sub, scen_keys, abs_col, "", False, with_addon,
                                   usd_decimals=usd_decimals)
    _s9._scenario_comparison_panel(axes[1], sub, scen_keys, pct_col, "", True, with_addon)
    axes[0].set_title(abs_title, fontsize=13)
    axes[1].set_title(pct_title, fontsize=13)
    colors = _s9.SCEN_COLOURS
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[i]) for i in range(len(scen_keys))]
    labels = list(scen_labels)
    if with_addon:
        handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="white", hatch="///",
                                      edgecolor="black"))
        labels.append("Minimum-royalty floor add-on")
    axes[0].legend(handles, labels, fontsize=8, loc="best", framealpha=0.85)
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def fig_country_examples(summary, figures_dir):
    # Fig 5 — Angola + Peru: tax revenue, two resource treatments (main spec first).
    # (Angola replaced Chad, which does not lose under the baseline; Peru replaced
    # South Sudan 2026-07-11 — SSD's former excl_resource "win" was an artifact of
    # its degenerate ETR, removed by the negligible-base CIT substitution, leaving
    # it ~0 in both scenarios. Peru: baseline −$3.7bn → excl_resource +$6.6bn.)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    # Narrative order (2026-07-11, user): first the status-quo-like "ignore
    # resource rights" (losses), THEN "resource rights prior" (gains) — the text
    # walks the reader left to right through the reversal.
    keys2 = ["ignorant_reported", "excl_reported"]
    _country_panel(axes[0], summary, "AGO", keys2, REV_CIT,
                   "Change in tax revenue (USD bn)", "Angola")
    _country_panel(axes[1], summary, "PER", keys2, REV_CIT,
                   "Change in tax revenue (USD bn)", "Peru")
    plt.tight_layout()
    plt.savefig(figures_dir / "fig05_country_angola_peru.png", dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / 'fig05_country_angola_peru.png'}")

    # Fig 7 — Guinea + Mali: revenue across the three resource treatments.
    # (Mali replaced Burkina Faso 2026-07-11: BFA no longer flips under the
    # headline formula — its old "wins only with the floor" story was built on
    # the pre-destination spec and the raised 1.2–12% Cat-1 rates. Guinea is the
    # one genuine flip (negative under ALL formulas without the royalty); Mali is
    # the emblematic gold under-capturer, whose gains the royalty lifts ~40%.)
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    # Narrative order (2026-07-11, user): ignore -> resource rights prior -> + minimum royalty.
    keys = ["ignorant_reported", "excl_reported", "excl_floored_reported"]
    _country_panel(axes[0], summary, "GIN", keys, REV_CIT,
                   "Change in tax revenue (USD bn)", "Guinea")
    _country_panel(axes[1], summary, "MLI", keys, REV_CIT,
                   "Change in tax revenue (USD bn)", "Mali")
    plt.tight_layout()
    plt.savefig(figures_dir / "fig07_country_gin_mli.png", dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / 'fig07_country_gin_mli.png'}")

    # ETR-ETR mirrors of both country-example figures (Appendix E set).
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    _country_panel(axes[0], summary, "AGO", keys2, REV_ETR,
                   "Change in tax revenue (USD bn)", "Angola")
    _country_panel(axes[1], summary, "PER", keys2, REV_ETR,
                   "Change in tax revenue (USD bn)", "Peru")
    plt.tight_layout()
    plt.savefig(figures_dir / "figE_country_angola_peru_etretr.png", dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / 'figE_country_angola_peru_etretr.png'}")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2))
    _country_panel(axes[0], summary, "GIN", keys, REV_ETR,
                   "Change in tax revenue (USD bn)", "Guinea")
    _country_panel(axes[1], summary, "MLI", keys, REV_ETR,
                   "Change in tax revenue (USD bn)", "Mali")
    plt.tight_layout()
    plt.savefig(figures_dir / "figE_country_gin_mli_etretr.png", dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / 'figE_country_gin_mli_etretr.png'}")


def _consol_panel(ax, d, x, bw, hvals, cvals, title):
    # Hatch redundancy for colour-blind readers (matches the other figures).
    ax.bar(x - bw / 2, hvals, width=bw, color=FORMULA_COLOURS[1],
           hatch=HATCH_CYCLE[1 % len(HATCH_CYCLE)], edgecolor="white",
           linewidth=0.3, label="Headline (excl. resource)")
    ax.bar(x + bw / 2, cvals, width=bw, color=FORMULA_COLOURS[0],
           hatch=HATCH_CYCLE[2 % len(HATCH_CYCLE)], edgecolor="white",
           linewidth=0.3, label="After loss consolidation (lower-bound revenue)")
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([INCOME_GROUP_LABELS.get(g, g) for g in d.index], fontsize=9)
    ax.set_title(title, fontsize=13)


def fig_consolidation(figures_dir, denom_cashtax_musd):
    """Loss-consolidation figure — headline vs loss-consolidated revenue by income
    group (reported, excl_resource), absolute (left) and as % of the corporate tax
    the group's MNEs currently pay (right) — the SAME denominator as the other
    revenue % panels (user 2026-07-13: comparisons are vs taxes on MNE profits
    everywhere, never total government revenue)."""
    p = (_ROOT / "output" / "unitary_taxation" / "across_samples"
         / "loss_consolidation_sensitivity" / "tables"
         / "loss_consolidation_by_income_group__reported_only__excl_resource.csv")
    if not p.exists():
        print(f"  [skip Fig 11] not found: {p}")
        return
    d = pd.read_csv(p, index_col=0)
    d = d.reindex([g for g in INCOME_GROUP_ORDER if g in d.index])
    x = np.arange(len(d))
    bw = 0.38
    den = denom_cashtax_musd.reindex(d.index).to_numpy()   # per-year MUSD
    hpct = 100.0 * d["revenue_gain_from_ut"].to_numpy() * 1e3 / den
    cpct = 100.0 * d["revenue_gain_loss_consolidated_musd"].to_numpy() * 1e3 / den
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2))
    _consol_panel(axes[0], d, x, bw, d["revenue_gain_from_ut"].to_numpy(),
                  d["revenue_gain_loss_consolidated_musd"].to_numpy(),
                  "Change in tax revenue (USD bn)")
    _consol_panel(axes[1], d, x, bw, hpct, cpct, "% of current corporate tax paid")
    axes[0].set_ylabel("Change in tax revenue (USD bn)")
    axes[1].set_ylabel("% of current corporate tax paid")
    axes[0].legend(fontsize=9, framealpha=0.85)
    plt.tight_layout()
    plt.savefig(figures_dir / "fig11_loss_consolidation.png", dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / 'fig11_loss_consolidation.png'}")


# ─── Income-group figure set (Fig 1–4, 6, 8–10) ──────────────────────────────
def build_income_figs(by_inc, sample, keys):
    """keys = dict with scenario keys for this sample (ignorant/excl/floored)."""
    figures_dir = _figdir(sample)
    excl = keys["excl"]
    # Bar order: the MAIN specification (resource rights prior to taxing rights)
    # first, then the minimum-royalty add-on, then the ignore-resource-rights
    # comparison.
    scen_keys = [keys["excl"], keys["floored"], keys["ignorant"]]
    scen_labels = [SCEN_LABEL_PAPER[k] for k in scen_keys]

    # Fig 1 — taxable profit, resources excluded, four formulas (USD with no decimals)
    _ig_twopanel(by_inc, excl, PAPER_4FORMULAS, "delta_taxable_profits_musd",
                 "delta_taxable_profits_pct_posbase", TP_ABS, TP_PCT,
                 "fig01_taxable_profit_by_income.png", figures_dir, usd_decimals=0)
    # Fig 2 — tax revenue, ETR-CIT (the preferred rate mode; keeps the general
    # revenue figure in line with the resource-treatment Fig 6 and all tables)
    _ig_twopanel(by_inc, excl, PAPER_4FORMULAS, REV_CIT, REV_CIT_PCT, RV_ABS, RV_PCT,
                 "fig02_tax_revenue_ETR_CIT.png", figures_dir, usd_decimals=0)
    # Fig 3 — tax revenue, both legs at ETR (robustness)
    _ig_twopanel(by_inc, excl, PAPER_4FORMULAS, REV_ETR, REV_ETR_PCT, RV_ABS, RV_PCT,
                 "fig03_tax_revenue_ETR_ETR.png", figures_dir, usd_decimals=0)
    # Fig 4 — taxable profit, preferred formula, three treatments
    _scen_twopanel(by_inc, HEADLINE, scen_keys, scen_labels,
                   "delta_taxable_profits_musd", "delta_taxable_profits_pct_posbase",
                   TP_ABS, TP_PCT, False, "fig04_taxbase_three_treatments.png", figures_dir)
    # Fig 6 — tax revenue, preferred formula, three treatments, hatched floor add-on
    _scen_twopanel(by_inc, HEADLINE, scen_keys, scen_labels, REV_CIT, REV_CIT_PCT,
                   RV_ABS, RV_PCT, True, "fig06_revenue_three_treatments.png", figures_dir,
                   usd_decimals=0)
    # Fig 8 — origin vs destination vs nexus, taxable profit
    _ig_twopanel(by_inc, excl, FIG8_MEASURES, "delta_taxable_profits_musd",
                 "delta_taxable_profits_pct_posbase", TP_ABS, TP_PCT,
                 "fig08_origin_dest_nexus_taxbase.png", figures_dir,
                 overall_title="Change in taxable profits by income group: "
                               "origin vs destination-based sales")
    # Fig 9 — origin vs destination, tax revenue (ETR-CIT)
    _ig_twopanel(by_inc, excl, FIG9_MEASURES, REV_CIT, REV_CIT_PCT, RV_ABS, RV_PCT,
                 "fig09_origin_dest_revenue.png", figures_dir, usd_decimals=0,
                 overall_title="Change in tax revenue by income group: "
                               "origin vs destination-based sales")
    # Ablation of the destination measure (taxable profit): complete -> without
    # ADS -> without digital services -> consumer-facing only. Reported version
    # feeds the main-text Figure 10 slot; gravity version the Appendix F7 slot.
    _ig_twopanel(by_inc, excl, ABLATION_MEASURES, "delta_taxable_profits_musd",
                 "delta_taxable_profits_pct_posbase", TP_ABS, TP_PCT,
                 "figA_sales_measure_ablation.png", figures_dir)

    # ── ETR-ETR appendix set (user 2026-07-13: EVERY revenue figure gets its
    # both-legs-at-ETR mirror, not just the by-formula one). Reported only —
    # the appendix presents the conservative rate specification. fig03 (by
    # formula) is the first of the set; these are its companions. ──
    if sample == "reported_only":
        _scen_twopanel(by_inc, HEADLINE, scen_keys, scen_labels, REV_ETR,
                       REV_ETR_PCT, RV_ABS, RV_PCT, True,
                       "figE_revenue_three_treatments_etretr.png", figures_dir,
                       usd_decimals=0)
        _ig_twopanel(by_inc, excl, FIG9_MEASURES, REV_ETR, REV_ETR_PCT, RV_ABS,
                     RV_PCT, "figE_origin_dest_revenue_etretr.png", figures_dir,
                     usd_decimals=0)


def main():
    # ── Reported (main text) ──────────────────────────────────────────────
    print("== reported_only ==")
    summary_rep = build_summary(YEARS, SCN_REPORTED, variant="")
    if summary_rep is None or summary_rep.empty:
        raise SystemExit("no reported summary from build_summary")
    by_inc_rep = build_by_income(summary_rep)
    build_income_figs(
        by_inc_rep, "reported_only",
        {"ignorant": "ignorant_reported", "excl": "excl_reported",
         "floored": "excl_floored_reported"})
    fig_country_examples(summary_rep, _figdir("reported_only"))
    # income-group corporate tax currently paid by MNEs (per-year MUSD) — the
    # same denominator the other revenue % panels use (_s8.GROUP_CASHTAX_MUSD is
    # populated by build_by_income above; it can carry one row per scenario, so
    # restrict to the excl scenario and collapse to one value per group).
    _g = getattr(_s8, "GROUP_CASHTAX_MUSD", None)
    if _g is not None:
        if "scenario" in _g.columns and (_g["scenario"] == "excl_reported").any():
            _g = _g[_g["scenario"] == "excl_reported"]
        denom = _g.groupby("wb_income_group")["grp_cashtax_musd"].max()
        fig_consolidation(_figdir("reported_only"), denom)
    else:
        print("  [skip consolidation fig] GROUP_CASHTAX_MUSD not populated")

    # ── Gravity (Appendix E) ──────────────────────────────────────────────
    print("== gravity (Appendix E) ==")
    try:
        summary_grav = build_summary(YEARS, SCN_GRAVITY, variant="")
    except ValueError as e:
        # Gravity summaries predate the current headline formulas until the
        # full-sample rerun (stage 2d) lands — skip the appendix set cleanly.
        print(f"  [skip] gravity summaries lack the current formulas ({e}); "
              "rerun the full-sample passes, then rerun this script.")
        summary_grav = None
    if summary_grav is not None and not summary_grav.empty:
        by_inc_grav = build_by_income(summary_grav)
        build_income_figs(
            by_inc_grav, "gravity",
            {"ignorant": "ignorant_gravity", "excl": "excl_gravity",
             "floored": "excl_floored_gravity"})
    else:
        print("  [skip] no gravity summary")

    print("\nDone.")


if __name__ == "__main__":
    main()
