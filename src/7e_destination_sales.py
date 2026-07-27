# %%
"""
7e — Origin vs destination-based sales.

Holds the formula fixed and varies the sales factor: origin sales (booked where recorded) vs destination sales (reallocated
to the market) vs destination with the physical-establishment requirement (the
destination share down-weighted by the fraction of a group's activity with a
real subsidiary in the market). Produces the by-income-group comparison figures
and the origin-vs-destination country tables, plus a sales-measure ablation
figure (Figure F7).

Headline specification: reported-only sample, resources excluded, employees + destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at statutory CIT and losses at ETR, per-year average over 2016–2022 (2020 excluded), constant 2025 US$.

Exhibit script — consumes the script-6 estimation summaries. Produces Figure 9
(origin vs destination sales) + Appendix Figures F5/F7 + Tables 4a/4b + region twin figB.

Reads:
  output/estimates/reported_only/{1_resources_ignored,2_resources_excluded,3_minimum_royalty_added}/tables/…/country_estimates__*.csv — origin/destination/nexus specs (script 5/6)
  output/paper/main_text/scaleup_yearly.csv                             — ghost-bar scale factors (from 7a)

Writes:
  output/paper/main_text/fig09_*.png/.pdf                              — Figure 9 (origin vs destination)
  output/paper/appendix/figF5_*.png/.pdf, figF7_*.png/.pdf             — Appendix Figures F5, F7
  output/analysis/origin_vs_destination/…                             — Tables 4a/4b + origin-vs-destination country tables

Usage:
  python 7e_destination_sales.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import output_dirs
from _brand import apply_tjn_style, ORIGIN_DEST_NEXUS

apply_tjn_style()
_OC, _DC, _NC = ORIGIN_DEST_NEXUS  # origin / destination / destination+nexus

# %% MARK: 2. Config and constants
# Go through output_dirs() so the nested-layout remap applies (reported-only
# UT runs live under output/estimates/reported_only/<scenario folder>/).
EST_DIR = output_dirs("unitary_taxation_disaggregated_reported")[0] / "disaggregated"
TABLES_DIR, FIGURES_DIR = output_dirs("destination_vs_origin")

# The three resource SCENARIOS (reported-only sample), for the per-formula
# scenario-comparison figure. Each maps to its UT output directory + the
# per-sample subfolder script 5 writes into.
SCENARIOS = [
    (
        "S1 ignored",
        "Resources ignored",
        output_dirs("unitary_taxation_disaggregated_reported")[0] / "disaggregated",
    ),
    (
        "S2 excl",
        "Resources excluded",
        output_dirs("unitary_taxation_excl_resource_reported")[0] / "excl_resource",
    ),
    (
        "S3 floored",
        "Resources excluded + min. royalty floor",
        output_dirs("unitary_taxation_excl_resource_floored_reported")[0]
        / "excl_resource_floored",
    ),
]
SCEN_COLOURS = [_OC, _DC, _NC]

FAMILIES = [
    ("ccctb", "CCCTB"),
    ("double_weighted_sales", "Double-weighted sales"),
    ("sales_employees", "Sales + employees"),
    ("three_factors", "Three-factor"),
]
MEASURES = [
    ("combined", "destcombined", "CFB + digital (combined)"),
    ("cfb", "destcfb", "Consumer-facing (CFB)"),
    ("ads", "destads", "Digital services (ADS)"),
]
RATE_MODES = [
    ("loss_cit_gain_etr", "rec CIT / forg ETR"),
    ("loss_etr_gain_etr", "both legs at ETR"),
]  # revenue metric only (profits are rate-invariant)
ETR = "average"
# CbCR reporting anomalies excluded from income-group aggregates — single
# source of truth in config.py.
from config import DATA_QUALITY_EXCLUSIONS as EXCLUDE  # noqa: E402

INCOME_ORDER = ["low", "middle", "high", "hub", "global"]
INCOME_LABEL = {
    "low": "Low",
    "middle": "Middle",
    "high": "High",
    "hub": "Inv. hubs",
    "global": "Global",
}


# %% MARK: 3. Data loaders
def _igs(is_tax_base):
    """Income-group x-axis. The tax-BASE change (Change in taxable profit) is a pure
    reallocation that sums to ~0 across all groups by construction, so the
    'global' bar is meaningless there and is dropped; revenue metrics (which do
    not net to zero) keep it."""
    return (
        [g for g in INCOME_ORDER if g != "global"]
        if is_tax_base
        else list(INCOME_ORDER)
    )


def bucket(g):
    s = str(g).strip().lower()
    if s == "low_income":
        return "low"
    if s in {"lower_middle_income", "upper_middle_income", "middle_income"}:
        return "middle"
    if s == "high_income":
        return "high"
    if s == "tax_haven":
        return "hub"
    return "other"  # missing -> excluded


def _path(spec, rate_mode, est_dir=EST_DIR):
    return (
        est_dir
        / f"country_estimates__{spec}__etrdef_{ETR}__etrmax_inf__{rate_mode}.csv"
    )


def _read_csv_robust(fp):
    """OneDrive dehydrated placeholders intermittently fail to open on the Win32
    API; force a byte copy via git-bash cp (a different API) and read that."""
    import os
    import subprocess
    import tempfile

    try:
        return pd.read_csv(fp)
    except (FileNotFoundError, OSError):
        dst = os.path.join(tempfile.gettempdir(), "dvo_" + os.path.basename(fp))
        for cp in (r"C:\Program Files\Git\usr\bin\cp.exe", "cp"):
            try:
                subprocess.run([cp, os.fspath(fp), dst], check=True)
                return pd.read_csv(dst)
            except Exception:
                continue
        raise


def load_spec(spec, rate_mode, est_dir=EST_DIR):
    """Return per-income-group Change in taxable profits and Change in tax revenue ($bn) for a spec."""
    fp = _path(spec, rate_mode, est_dir)
    # Don't gate on fp.exists() — OneDrive dehydrated placeholders make exists()
    # flap to False even when the file is present. Just try the robust read.
    try:
        d = _read_csv_robust(fp)
    except (FileNotFoundError, OSError):
        print(f"  [missing] {fp.name}")
        return None
    d = d[~d["iso_partner"].isin(EXCLUDE)].copy()
    d["dprofit"] = pd.to_numeric(
        d["theoretical_profit"], errors="coerce"
    ) - pd.to_numeric(d["reported_profit"], errors="coerce")
    d["drev"] = pd.to_numeric(d["revenue_gain_from_ut"], errors="coerce")
    d["bkt"] = d["wb_income_group"].apply(bucket)
    d["taxrev"] = pd.to_numeric(d["current_tax_paid_cash_musd"], errors="coerce") * 1e6
    out = {}

    def agg(sub):  # ($bn dprofit, $bn drev, raw-USD current tax revenue)
        return (
            sub["dprofit"].sum() / 1e3,
            sub["drev"].sum() / 1e3,
            sub["taxrev"].sum(),
        )

    for b in ("low", "middle", "high", "hub"):
        out[b] = agg(d[d["bkt"] == b])
    out["global"] = agg(d[d["bkt"].isin(("low", "middle", "high", "hub"))])
    return out


def collect():
    rows = []
    for fam, fam_lbl in FAMILIES:
        variants = [("origin", fam)]
        for mkey, mcol, _ in MEASURES:
            variants.append((f"{mkey}", f"{fam}_{mcol}"))
            variants.append((f"{mkey}_nexus", f"{fam}_{mcol}_nexus"))
        for vkey, spec in variants:
            for rm, _rm_lbl in RATE_MODES:
                res = load_spec(spec, rm)
                if res is None:
                    continue
                for b in INCOME_ORDER:
                    dp, dr, tr = res[b]
                    pct = 100.0 * (dr * 1e9) / tr if (tr and tr > 0) else np.nan
                    rows.append(
                        {
                            "family": fam,
                            "family_label": fam_lbl,
                            "variant": vkey,
                            "income_group": b,
                            "rate_mode": rm,
                            "delta_taxable_profits_bn": dp,
                            "delta_tax_revenue_bn": dr,
                            "pct_current_tax_revenue": pct,
                        }
                    )
    return pd.DataFrame(rows)


# %% MARK: 4. Figure builders
def fig_for_measure(df, mkey, mlbl, metric_col, metric_lbl, tag="", unit="$bn"):
    """2x2 family panels; per income group, 3 bars: origin / destination / dest+nexus."""
    series = [
        ("origin", "Origin", _OC),
        (mkey, "Destination", _DC),
        (f"{mkey}_nexus", "Destination + nexus", _NC),
    ]
    igs = _igs(metric_col == "delta_taxable_profits_bn")
    x = np.arange(len(igs))
    w = 0.26
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for ax, (fam, fam_lbl) in zip(axes.flat, FAMILIES):
        sub = df[df["family"] == fam]
        for j, (vk, vlbl, col) in enumerate(series):
            vals = [
                sub[(sub["variant"] == vk) & (sub["income_group"] == ig)][
                    metric_col
                ].sum()
                for ig in igs
            ]
            ax.bar(x + (j - 1) * w, vals, w, label=vlbl, color=col)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(fam_lbl, fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
        ax.grid(axis="y", alpha=0.3)
    axes.flat[0].legend(fontsize=9, loc="best")
    fig.suptitle(
        f"{metric_lbl} — {mlbl}\nOrigin vs destination-based sales, with/without nexus "
        f"(2016-2022, {unit})",
        fontsize=13,
    )
    fig.supylabel(f"{metric_lbl} ({unit})")
    fig.tight_layout(rect=[0.02, 0, 1, 0.96])
    out = FIGURES_DIR / f"fig_{metric_col}_{mkey}{tag}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  wrote {out.name}")


def fig_series(df, series, metric_col, metric_lbl, subtitle, tag, unit="$bn"):
    """2x2 family panels; per income group, one bar per (variant, label, colour) in `series`.
    df should already be filtered to a single rate mode."""
    igs = _igs(metric_col == "delta_taxable_profits_bn")
    x = np.arange(len(igs))
    w = 0.8 / max(len(series), 1)
    off = (len(series) - 1) / 2.0
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for ax, (fam, fam_lbl) in zip(axes.flat, FAMILIES):
        sub = df[df["family"] == fam]
        for j, (vk, vlbl, col) in enumerate(series):
            vals = [
                sub[(sub["variant"] == vk) & (sub["income_group"] == ig)][
                    metric_col
                ].sum()
                for ig in igs
            ]
            ax.bar(x + (j - off) * w, vals, w, label=vlbl, color=col)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(fam_lbl, fontsize=11)
        ax.set_xticks(x)
        ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
        ax.grid(axis="y", alpha=0.3)
    axes.flat[0].legend(fontsize=9, loc="best")
    fig.suptitle(f"{metric_lbl} — {subtitle}\n(2016-2022, {unit})", fontsize=13)
    fig.supylabel(f"{metric_lbl} ({unit})")
    fig.tight_layout(rect=[0.02, 0, 1, 0.95])
    out = FIGURES_DIR / f"fig_{tag}.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  wrote {out.name}")


def cfb_vs_combined_figs(df):
    """Direct comparison: CFB only vs CFB + digital (combined), origin as reference."""
    rm = RATE_MODES[0][
        0
    ]  # headline rate mode (rec CIT / forg ETR) for the revenue views
    for nexus, suf in [(False, ""), (True, "_nexus")]:
        lbl = "with nexus" if nexus else "no nexus"
        series = [
            ("origin", "Origin", _OC),
            (f"cfb{suf}", "CFB only", _DC),
            (f"combined{suf}", "CFB + digital", _NC),
        ]
        fig_series(
            df[df.rate_mode == RATE_MODES[0][0]],
            series,
            "delta_taxable_profits_bn",
            "Change in taxable profits",
            f"CFB only vs CFB + digital ({lbl})",
            f"cfbVScombined_profits{suf}",
        )
        fig_series(
            df[df.rate_mode == rm],
            series,
            "delta_tax_revenue_bn",
            "Change in tax revenue (rec CIT / forg ETR)",
            f"CFB only vs CFB + digital ({lbl})",
            f"cfbVScombined_rev{suf}",
        )
        fig_series(
            df[df.rate_mode == rm],
            series,
            "pct_current_tax_revenue",
            "Change in tax revenue, % of current tax revenue",
            f"CFB only vs CFB + digital ({lbl})",
            f"cfbVScombined_pct{suf}",
            unit="%",
        )


def _metric_val(res, ig, mi):
    """mi: 0 = Change in taxable profits $bn, 1 = Change in tax revenue $bn, 2 = % of current tax."""
    dp, dr, tr = res[ig]
    if mi == 0:
        return dp
    if mi == 1:
        return dr
    return 100.0 * (dr * 1e9) / tr if (tr and tr > 0) else np.nan


def fig_scenarios_per_formula(
    measure_col="destcombined",
    measure_lbl="CFB + digital (combined)",
    rate_mode="loss_cit_gain_etr",
):
    """Per formula family + per metric: origin vs destination-based sales by
    income group (the bars), with the three resource scenarios as panels SIDE
    BY SIDE (resources ignored / excluded / + min-royalty floor). One figure per
    (family, metric). Reported-only sample, 2016-2022."""
    igs = INCOME_ORDER
    x = np.arange(len(igs))
    w = 0.26
    metrics = [
        (0, "Change in taxable profits", "$bn", "profits"),
        (1, "Change in tax revenue (rec CIT / forg ETR)", "$bn", "revenue"),
        (2, "Change in tax revenue, % of current tax", "%", "pct"),
    ]
    for fam, fam_lbl in FAMILIES:
        # Preload origin / destination / destination+nexus spec for each scenario.
        # variants: ("" → origin, "_destcombined", "_destcombined_nexus")
        variant_suffixes = ["", "_" + measure_col, "_" + measure_col + "_nexus"]
        # Use the descriptive scenario name (not the S1/S2/S3 code) as panel title.
        loaded = [
            (
                desc,
                [load_spec(fam + suf, rate_mode, est_dir) for suf in variant_suffixes],
            )
            for _slbl, desc, est_dir in SCENARIOS
        ]
        if all(all(r is None for r in res) for _, res in loaded):
            print(f"  [skip] scenarios {fam}: no data")
            continue
        labels = ["Origin", "Destination", "Destination + nexus"]
        colours = [_OC, _DC, _NC]
        for mi, mlbl, unit, mtag in metrics:
            igs = _igs(
                mi == 0
            )  # mi==0 is the tax-base (Change in taxable profit) metric
            x = np.arange(len(igs))
            fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
            for ax, (desc, res) in zip(axes, loaded):
                for j, (lab, col, r) in enumerate(zip(labels, colours, res)):
                    if r is None:
                        continue
                    ax.bar(
                        x + (j - 1) * w,
                        [_metric_val(r, ig, mi) for ig in igs],
                        w,
                        label=lab,
                        color=col,
                    )
                ax.axhline(0, color="k", lw=0.6)
                ax.set_xticks(x)
                ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
                ax.set_title(desc, fontsize=11)
                ax.grid(axis="y", alpha=0.3)
            axes[0].legend(fontsize=9, loc="best")
            axes[0].set_ylabel(f"{mlbl} ({unit})")
            fig.suptitle(
                f"{fam_lbl}: {mlbl} by income group — origin vs destination-based "
                f"sales ({measure_lbl})\nthe three resource scenarios shown side by "
                f"side · recorded profits only (no imputed rows) · 2016–2022",
                fontsize=13,
            )
            fig.tight_layout(rect=[0, 0, 1, 0.91])
            out = FIGURES_DIR / f"fig_scenarios_{fam}_{mtag}.png"
            fig.savefig(out, dpi=140)
            plt.close(fig)
            print(f"  wrote {out.name}")


def _load_df(spec, est_dir, rate_mode="loss_cit_gain_etr"):
    """Load a country_estimates spec into a frame with numeric metric columns +
    income bucket; None if unavailable."""
    fp = _path(spec, rate_mode, est_dir)
    try:
        d = _read_csv_robust(fp)
    except (FileNotFoundError, OSError):
        return None
    d = d[~d["iso_partner"].isin(EXCLUDE)].copy()
    d["bk"] = d["wb_income_group"].apply(bucket)
    for c in [
        "theoretical_profit",
        "reported_profit",
        "revenue_gain_from_ut",
        "current_tax_paid_cash_musd",
    ]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def _series_vals(d, metric):
    """Per income group (low/middle/high/hub/global) value for `metric` ∈
    {profit_usd ($bn), profit_pct (% reported base), rev_usd ($bn),
    rev_pct (% current tax)}."""
    out = {}
    for ig in INCOME_ORDER:
        sub = (
            d[d["bk"].isin(("low", "middle", "high", "hub"))]
            if ig == "global"
            else d[d["bk"] == ig]
        )
        dprofit = (sub["theoretical_profit"] - sub["reported_profit"]).sum()  # musd
        base = sub["reported_profit"].sum()  # musd
        drev = sub["revenue_gain_from_ut"].sum()  # musd
        tr = sub["current_tax_paid_cash_musd"].sum() * 1e6  # USD
        if metric == "profit_usd":
            out[ig] = dprofit / 1e3
        elif metric == "profit_pct":
            # NaN unless the profit base is strictly positive — a % against a
            # non-positive base flips sign and misleads (cf. _scenario_machinery's
            # _safe_pct_positive_base).
            out[ig] = 100.0 * dprofit / base if base > 0 else np.nan
        elif metric == "rev_usd":
            out[ig] = drev / 1e3
        else:  # rev_pct — denominator (current tax revenue) must be > 0
            out[ig] = 100.0 * (drev * 1e6) / tr if (tr and tr > 0) else np.nan
    return out


def fig_s2_origin_vs_dest():
    """S2 (resources excluded), RECORDED PROFITS ONLY: per formula family and
    destination measure (CFB+digital combined, CFB only), one figure with Change in by
    income group in USD (left) and in % (right). Series = origin / destination /
    destination + nexus. Two figures per (family, measure): taxable profits and
    tax revenue."""
    s2_dir = SCENARIOS[1][2]  # excl_resource (reported-only) est dir
    igs = INCOME_ORDER
    x = np.arange(len(igs))
    w = 0.26
    colors = [_OC, _DC, _NC]
    specs = [
        (
            "taxable_profits",
            "profit_usd",
            "Change in taxable profit (USD bn)",
            "profit_pct",
            "Change in taxable profit (% of reported profit base)",
        ),
        (
            "revenue",
            "rev_usd",
            "Change in tax revenue (USD bn)",
            "rev_pct",
            "Change in tax revenue (% of current tax revenue)",
        ),
    ]
    for meas_col, meas_lbl in [
        ("destcombined", "CFB + digital"),
        ("destcfb", "CFB only"),
    ]:
        variants = [
            ("", "Origin"),
            (f"_{meas_col}", "Destination"),
            (f"_{meas_col}_nexus", "Destination + nexus"),
        ]
        for fam, fam_lbl in FAMILIES:
            dfs = [(_load_df(fam + vs, s2_dir), vl) for vs, vl in variants]
            if all(d is None for d, _ in dfs):
                print(f"  [skip] s2 {fam} {meas_col}: no data")
                continue
            for tag, um, ul, pm, pl in specs:
                igs = _igs(tag == "taxable_profits")
                x = np.arange(len(igs))
                fig, (axu, axp) = plt.subplots(1, 2, figsize=(14, 5.6))
                for ax, metric, ylab in [(axu, um, ul), (axp, pm, pl)]:
                    for j, (d, vl) in enumerate(dfs):
                        if d is None:
                            continue
                        sv = _series_vals(d, metric)
                        ax.bar(
                            x + (j - 1) * w,
                            [sv[ig] for ig in igs],
                            w,
                            label=vl,
                            color=colors[j],
                        )
                    ax.axhline(0, color="k", lw=0.6)
                    ax.set_xticks(x)
                    ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
                    ax.set_ylabel(ylab)
                    ax.grid(axis="y", alpha=0.3)
                metric_name = (
                    "taxable profit" if tag == "taxable_profits" else "tax revenue"
                )
                pct_of = (
                    "reported profit base"
                    if tag == "taxable_profits"
                    else "current tax revenue"
                )
                axu.set_title("Change in USD (bn)", fontsize=11)
                axp.set_title(f"Change as % of {pct_of}", fontsize=11)
                axu.legend(fontsize=9, loc="best")
                fig.suptitle(
                    f"{fam_lbl}: change in {metric_name} by income group, under "
                    f"origin vs destination-based sales ({meas_lbl})\n"
                    f"Resources-excluded scenario · recorded profits only "
                    f"(no imputed rows) · 2016–2022",
                    fontsize=12,
                )
                fig.tight_layout(rect=[0, 0, 1, 0.91])
                out = FIGURES_DIR / f"fig_s2_origin_vs_dest_{tag}_{fam}_{meas_col}.png"
                fig.savefig(out, dpi=140)
                plt.close(fig)
                print(f"  wrote {out.name}")


def _profit_series_posbase(d, igs):
    """Per income group: (Δprofit $bn, % of reported profit base). For 'low', BOTH
    numerator and denominator are summed over the subsample of countries with a
    strictly positive reported profit base (country-level, over the period), so a %
    is defined even though the group's aggregate base is non-positive. Other groups
    use the full aggregate."""
    res = {}
    for ig in igs:
        sub = (
            d[d["bk"].isin(("low", "middle", "high", "hub"))]
            if ig == "global"
            else d[d["bk"] == ig]
        )
        dprofit = (sub["theoretical_profit"] - sub["reported_profit"]).sum()  # musd
        if ig == "low":
            g = sub.groupby("iso_partner")
            base_c = g["reported_profit"].sum()
            dp_c = g["theoretical_profit"].sum() - base_c
            keep = base_c > 0
            num, den = dp_c[keep].sum(), base_c[keep].sum()
        else:
            num, den = dprofit, sub["reported_profit"].sum()
        pct = 100.0 * num / den if den > 0 else np.nan
        res[ig] = (dprofit / 1e3, pct)
    return res


def cfb_vs_combined_profits_se():
    """V.5 deliverable: comparison of destination-sales MEASURES — origin vs
    consumer-facing (CFB) vs CFB + digital (combined) — under the SALES + EMPLOYEES
    formula only, resources-excluded (S2), recorded profits only. Two panels:
    change in taxable profit in USD bn (left) and as % of the reported profit base
    (right), the low-income % computed over positive-base countries (see note)."""
    s2_dir = SCENARIOS[1][2]
    fam = "sales_employees"
    series = [
        ("", "Origin", _OC),
        ("_destcfb", "Consumer-facing (CFB)", _DC),
        ("_destcombined", "CFB + digital (combined)", _NC),
    ]
    igs = _igs(True)  # taxable-profit reallocation → drop meaningless 'global'
    x = np.arange(len(igs))
    w = 0.26
    loaded = [(_load_df(fam + vs, s2_dir), lbl, col) for vs, lbl, col in series]
    if all(d is None for d, _, _ in loaded):
        print("  [skip] cfbVScombined sales_employees: no data")
        return
    fig, (axu, axp) = plt.subplots(1, 2, figsize=(14, 5.6))
    for j, (d, lbl, col) in enumerate(loaded):
        if d is None:
            continue
        res = _profit_series_posbase(d, igs)
        axu.bar(x + (j - 1) * w, [res[ig][0] for ig in igs], w, label=lbl, color=col)
        axp.bar(x + (j - 1) * w, [res[ig][1] for ig in igs], w, label=lbl, color=col)
    for ax, ylab, title in [
        (axu, "Change in taxable profit (USD bn)", "Change in USD (bn)"),
        (
            axp,
            "Change in taxable profit (% of reported profit base)",
            "Change as % of reported profit base",
        ),
    ]:
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xticks(x)
        ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
        ax.set_ylabel(ylab)
        ax.set_title(title, fontsize=11)
        ax.grid(axis="y", alpha=0.3)
    axu.legend(fontsize=9, loc="best")
    fig.suptitle(
        "Sales + employees: change in taxable profit by income group, under different "
        "sales measures (origin vs CFB vs CFB + digital)\nResources-excluded scenario · "
        "recorded profits only · 2016–2022",
        fontsize=12,
    )
    note = (
        "Right panel: change in taxable profit as a percentage of the reported profit "
        "base. For low-income countries the percentage is computed over the subsample "
        "of countries with a strictly positive reported profit base — summing the change "
        "and the base over the same countries — because the group's aggregate current "
        "profit base is otherwise non-positive (which would make a percentage flip sign "
        "and mislead). The absolute panel (left) covers all countries."
    )
    fig.text(
        0.5,
        0.005,
        note,
        ha="center",
        va="bottom",
        fontsize=7.5,
        wrap=True,
        color="#444444",
    )
    fig.tight_layout(rect=[0, 0.08, 1, 0.91])
    out = FIGURES_DIR / "fig_cfbVScombined_profits.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  wrote {out.name}  (sales+employees only, with % panel)")


# %% MARK: 5. Main
def main():
    df = collect()
    df.to_csv(TABLES_DIR / "destination_vs_origin_summary.csv", index=False)
    print(f"wrote {TABLES_DIR / 'destination_vs_origin_summary.csv'} ({len(df)} rows)")
    for mkey, _mcol, mlbl in MEASURES:
        # Change in taxable profits is rate-mode invariant → use one rate-mode subset.
        fig_for_measure(
            df[df.rate_mode == RATE_MODES[0][0]],
            mkey,
            mlbl,
            "delta_taxable_profits_bn",
            "Change in taxable profits",
        )
        for rm, rm_lbl in RATE_MODES:
            fig_for_measure(
                df[df.rate_mode == rm],
                mkey,
                mlbl,
                "delta_tax_revenue_bn",
                f"Change in tax revenue ({rm_lbl})",
                tag=f"_{rm}",
            )
            fig_for_measure(
                df[df.rate_mode == rm],
                mkey,
                mlbl,
                "pct_current_tax_revenue",
                f"Change in tax revenue, % of current tax revenue ({rm_lbl})",
                tag=f"_pct_{rm}",
                unit="%",
            )
    # CFB-only vs CFB+digital (combined) direct comparison
    cfb_vs_combined_figs(df)
    # Headline V.5 version: sales+employees only, S2, with a % panel (low-income
    # % over positive-base countries). Overwrites fig_cfbVScombined_profits.png.
    cfb_vs_combined_profits_se()

    # Per-formula comparison of the three resource scenarios under destination sales.
    print("Per-formula resource-scenario comparison (destination sales):")
    fig_scenarios_per_formula()

    # S2-only origin vs destination, USD + % side by side, recorded profits only.
    print("S2 origin vs destination, USD + % (recorded profits only):")
    fig_s2_origin_vs_dest()


# %% MARK: 6. paper exhibits — destination-concept figures and tables
# The destination-concept slices of the paper deliverable: origin vs
# destination vs physical-establishment
# figures, the sales-measure ablation, and the sales-measure tables — both
# samples, paper style (untitled panels).
import pandas as _pd

import _scenario_machinery as _sc
import _exhibit_helpers as _eh


def paper_destination_figures(sample, by_inc, ghost_by_inc=None, by_region=None):
    figures_dir = _eh.figdir(sample)
    excl = _eh.SCEN_KEYS[sample]["excl"]
    _eh.ig_twopanel(
        by_inc,
        excl,
        _eh.FIG_DEST_MEASURES,
        "delta_taxable_profits_musd",
        "delta_taxable_profits_pct_posbase",
        _eh.TP_ABS,
        _eh.TP_PCT,
        "figF5_origin_dest_nexus_taxbase.png",
        figures_dir,
        overall_title="Change in taxable profits by income group: "
        "origin vs destination-based sales",
    )
    _eh.ig_twopanel(
        by_inc,
        excl,
        _eh.FIG_DEST_MEASURES,
        _eh.REV_CIT,
        _eh.REV_CIT_PCT,
        _eh.RV_ABS,
        _eh.RV_PCT,
        "fig09_origin_dest_revenue.png",
        figures_dir,
        usd_decimals=0,
        overall_title="Change in tax revenue by income group: "
        "origin vs destination-based sales",
    )
    # Appendix B: by-world-region twin of Figure 9 (reported sample only).
    if by_region is not None:
        bdir = _eh.figdir_appendix_b()

        def _twin():
            _eh.ig_twopanel(by_region, excl, _eh.FIG_DEST_MEASURES, _eh.REV_CIT, _eh.REV_CIT_PCT,
                            _eh.RV_ABS, _eh.RV_PCT, "figB_origin_dest_revenue_by_region.png", bdir,
                            usd_decimals=0, overall_title="Change in tax revenue by world region: "
                            "origin vs destination-based sales")
        _eh.region_figures(_twin)
    _eh.ig_twopanel(
        by_inc,
        excl,
        _eh.ABLATION_MEASURES,
        "delta_taxable_profits_musd",
        "delta_taxable_profits_pct_posbase",
        _eh.TP_ABS,
        _eh.TP_PCT,
        "figF7_sales_measure_ablation.png",
        figures_dir,
    )
    if sample == "reported_only":
        _eh.ig_twopanel(
            by_inc,
            excl,
            _eh.FIG_DEST_MEASURES,
            _eh.REV_ETR,
            _eh.REV_ETR_PCT,
            _eh.RV_ABS,
            _eh.RV_PCT,
            "figE_origin_dest_revenue_etretr.png",
            figures_dir,
            usd_decimals=0,
        )


def paper_destination_tables(sample, tables_dir):
    excl_rev = _eh.rev_musd(sample, "excl_resource", _eh.HEADLINE_FORMULA)
    if excl_rev.empty:
        print(f"  [skip destination tables] no {sample} summary")
        return
    order_iso = _pd.Index(sorted(excl_rev.index, key=lambda i: _eh.cname(i).lower()))
    grp = _eh.income_group(sample).to_dict()
    grp_reg = _eh.region(sample).to_dict()
    posbase = _eh.posbase_musd(sample)
    netbase = _eh.reported_musd(sample, "excl_resource")
    cashtax = _eh.current_rev_musd(sample)
    tb3 = _pd.DataFrame(index=order_iso)
    rev3 = _pd.DataFrame(index=order_iso)
    tb3["net reported profits"] = netbase
    tb3["taxable profits (positive profits only)"] = posbase
    rev3["current tax revenue from MNEs"] = cashtax
    for fk, flab in _eh.SALES_SPECS:
        tb3[flab] = _eh.taxbase_musd(sample, "excl_resource", fk)
        rev3[flab] = _eh.rev_musd(sample, "excl_resource", fk)
    _slabs = [flab for _, flab in _eh.SALES_SPECS]
    _eh.emit_table(
        tb3,
        order_iso,
        grp,
        grp_reg,
        sample,
        "table4a_taxbase_by_sales",
        tables_dir,
        pct_base="taxable profits (positive profits only)",
        pct_cols=_slabs,
        drop_base_col=True,
    )
    _eh.emit_table(
        rev3,
        order_iso,
        grp,
        grp_reg,
        sample,
        "table4b_revenue_by_sales",
        tables_dir,
        pct_base="current tax revenue from MNEs",
        pct_cols=_slabs,
    )


def main_paper():
    _sc.INCOME_GROUP_LABELS = _eh.IG_LABELS_PAPER
    for sample in _eh.SAMPLES:
        print(f"== paper destination exhibits [{sample}] ==")
        if not _eh.summary_exists(sample):
            print(f"  [skip] no {sample} summaries yet")
            continue
        summary = _eh.paper_summary(sample)
        if summary is not None:
            by_inc = _sc.build_by_income(summary)
            ghost = _eh.ghost_by_income(sample) if sample == "reported_only" else None
            by_region = (_sc.build_by_income(summary, gcol="region_tjn")
                         if sample == "reported_only" else None)
            paper_destination_figures(sample, by_inc, ghost_by_inc=ghost, by_region=by_region)
        paper_destination_tables(sample, _eh.tabledir(sample))


# %% MARK: 7. Run
if __name__ == "__main__":
    main()
    main_paper()
