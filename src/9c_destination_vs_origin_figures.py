# %%
"""
Destination- vs origin-based sales — with and without nexus.

Three-scenario-style comparison for the SALES factor (mirrors
9_three_scenario_figures.py, but the axis is the sales measure instead of the
resource scenario). For each of the four sales-using formula families
(ccctb, double_weighted_sales, sales_employees, three_factors) we compare:

  - ORIGIN              : the base family (sales = unrelated_party_revenues)
  - DESTINATION         : sales reallocated to the market (no nexus)
  - DESTINATION + NEXUS : destination share down-weighted by nexus coverage
                          (fraction of the HQ's CbCR groups with a subsidiary
                          in the market — cbcr_universe_presence.csv, the
                          all-sector CbCR universe built from the Orbis flatfiles)

× three destination measures, shown as separate figures:
  combined (cfb_plus_digital), cfb (consumer-facing only), ads (digital users).

Reads the per-spec country_estimates written by 5_estimate_profit_shifting.py
on the disaggregated (reported-only) sample. Window 2016-2022, ETR=average.
  - Change in taxable profits  (Σ theoretical − Σ reported)   — rate-mode invariant
  - Change in tax revenue      (Σ revenue_gain_from_ut)        — rate mode loss_cit_gain_etr

Outputs to output/destination_vs_origin/{tables,figures}/.

Usage: python 9c_destination_vs_origin_figures.py
"""
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

# Go through output_dirs() so the nested-layout remap applies (reported-only
# UT runs now live under output/unitary_taxation/reported_only/<base>/).
EST_DIR = output_dirs("unitary_taxation_disaggregated_reported")[0] / "disaggregated"
TABLES_DIR, FIGURES_DIR = output_dirs("destination_vs_origin")

# The three resource SCENARIOS (reported-only sample), for the per-formula
# scenario-comparison figure. Each maps to its UT output directory + the
# per-sample subfolder script 5 writes into.
SCENARIOS = [
    ("S1 ignored", "Resources ignored",
     output_dirs("unitary_taxation_disaggregated_reported")[0] / "disaggregated"),
    ("S2 excl", "Resources excluded",
     output_dirs("unitary_taxation_excl_resource_reported")[0] / "excl_resource"),
    ("S3 floored", "Resources excluded + min. royalty floor",
     output_dirs("unitary_taxation_excl_resource_floored_reported")[0]
     / "excl_resource_floored"),
]
SCEN_COLOURS = [_OC, _DC, _NC]

FAMILIES = [
    ("ccctb", "CCCTB"),
    ("double_weighted_sales", "Double-weighted sales"),
    ("sales_employees", "Sales + employees"),
    ("three_factors", "Three-factor"),
]
MEASURES = [("combined", "destcombined", "CFB + digital (combined)"),
            ("cfb", "destcfb", "Consumer-facing (CFB)"),
            ("ads", "destads", "Digital services (ADS)")]
RATE_MODES = [("loss_cit_gain_etr", "rec CIT / forg ETR"),
              ("loss_etr_gain_etr", "both legs at ETR")]   # revenue metric only (profits are rate-invariant)
ETR = "average"
# CbCR reporting anomalies excluded from income-group aggregates (per script 8).
EXCLUDE = {"LSO", "FSM", "GUF", "BTN"}
INCOME_ORDER = ["low", "middle", "high", "hub", "global"]
INCOME_LABEL = {"low": "Low", "middle": "Middle", "high": "High",
                "hub": "Inv. hubs", "global": "Global"}


def _igs(is_tax_base):
    """Income-group x-axis. The tax-BASE change (Change in taxable profit) is a pure
    reallocation that sums to ~0 across all groups by construction, so the
    'global' bar is meaningless there and is dropped; revenue metrics (which do
    not net to zero) keep it."""
    return [g for g in INCOME_ORDER if g != "global"] if is_tax_base else list(INCOME_ORDER)


def bucket(g):
    s = str(g).strip().lower()
    if s == "low_income":
        return "low"
    if s in {"lower_middle_income", "upper_middle_income", "middle_income"}:
        return "middle"
    if s == "high_income":
        return "high"
    if s == "investment_hub":
        return "hub"
    return "other"   # missing -> excluded


def _path(spec, rate_mode, est_dir=EST_DIR):
    return est_dir / f"country_estimates__{spec}__etrdef_{ETR}__etrmax_inf__{rate_mode}.csv"


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
    d["dprofit"] = (pd.to_numeric(d["theoretical_profit"], errors="coerce")
                    - pd.to_numeric(d["reported_profit"], errors="coerce"))
    d["drev"] = pd.to_numeric(d["revenue_gain_from_ut"], errors="coerce")
    d["bkt"] = d["wb_income_group"].apply(bucket)
    d["taxrev"] = pd.to_numeric(d["tax_revenue_current_usd"], errors="coerce")
    out = {}
    def agg(sub):  # ($bn dprofit, $bn drev, raw-USD current tax revenue)
        return (sub["dprofit"].sum() / 1e3, sub["drev"].sum() / 1e3, sub["taxrev"].sum())
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
                    rows.append({"family": fam, "family_label": fam_lbl,
                                 "variant": vkey, "income_group": b, "rate_mode": rm,
                                 "delta_taxable_profits_bn": dp,
                                 "delta_tax_revenue_bn": dr,
                                 "pct_current_tax_revenue": pct})
    return pd.DataFrame(rows)


def fig_for_measure(df, mkey, mlbl, metric_col, metric_lbl, tag="", unit="$bn"):
    """2x2 family panels; per income group, 3 bars: origin / destination / dest+nexus."""
    series = [("origin", "Origin", _OC),
              (mkey, "Destination", _DC),
              (f"{mkey}_nexus", "Destination + nexus", _NC)]
    igs = _igs(metric_col == "delta_taxable_profits_bn")
    x = np.arange(len(igs)); w = 0.26
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for ax, (fam, fam_lbl) in zip(axes.flat, FAMILIES):
        sub = df[df["family"] == fam]
        for j, (vk, vlbl, col) in enumerate(series):
            vals = [sub[(sub["variant"] == vk) & (sub["income_group"] == ig)]
                    [metric_col].sum() for ig in igs]
            ax.bar(x + (j - 1) * w, vals, w, label=vlbl, color=col)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(fam_lbl, fontsize=11)
        ax.set_xticks(x); ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
        ax.grid(axis="y", alpha=0.3)
    axes.flat[0].legend(fontsize=9, loc="best")
    fig.suptitle(f"{metric_lbl} — {mlbl}\nOrigin vs destination-based sales, with/without nexus "
                 f"(2016-2022, {unit})", fontsize=13)
    fig.supylabel(f"{metric_lbl} ({unit})")
    fig.tight_layout(rect=[0.02, 0, 1, 0.96])
    out = FIGURES_DIR / f"fig_{metric_col}_{mkey}{tag}.png"
    fig.savefig(out, dpi=140); plt.close(fig)
    print(f"  wrote {out.name}")


def fig_series(df, series, metric_col, metric_lbl, subtitle, tag, unit="$bn"):
    """2x2 family panels; per income group, one bar per (variant, label, colour) in `series`.
    df should already be filtered to a single rate mode."""
    igs = _igs(metric_col == "delta_taxable_profits_bn")
    x = np.arange(len(igs)); w = 0.8 / max(len(series), 1)
    off = (len(series) - 1) / 2.0
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for ax, (fam, fam_lbl) in zip(axes.flat, FAMILIES):
        sub = df[df["family"] == fam]
        for j, (vk, vlbl, col) in enumerate(series):
            vals = [sub[(sub["variant"] == vk) & (sub["income_group"] == ig)]
                    [metric_col].sum() for ig in igs]
            ax.bar(x + (j - off) * w, vals, w, label=vlbl, color=col)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(fam_lbl, fontsize=11)
        ax.set_xticks(x); ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
        ax.grid(axis="y", alpha=0.3)
    axes.flat[0].legend(fontsize=9, loc="best")
    fig.suptitle(f"{metric_lbl} — {subtitle}\n(2016-2022, {unit})", fontsize=13)
    fig.supylabel(f"{metric_lbl} ({unit})")
    fig.tight_layout(rect=[0.02, 0, 1, 0.95])
    out = FIGURES_DIR / f"fig_{tag}.png"
    fig.savefig(out, dpi=140); plt.close(fig)
    print(f"  wrote {out.name}")


def cfb_vs_combined_figs(df):
    """Direct comparison: CFB only vs CFB + digital (combined), origin as reference."""
    rm = RATE_MODES[0][0]   # headline rate mode (rec CIT / forg ETR) for the revenue views
    for nexus, suf in [(False, ""), (True, "_nexus")]:
        lbl = "with nexus" if nexus else "no nexus"
        series = [("origin", "Origin", _OC),
                  (f"cfb{suf}", "CFB only", _DC),
                  (f"combined{suf}", "CFB + digital", _NC)]
        fig_series(df[df.rate_mode == RATE_MODES[0][0]], series,
                   "delta_taxable_profits_bn", "Change in taxable profits",
                   f"CFB only vs CFB + digital ({lbl})", f"cfbVScombined_profits{suf}")
        fig_series(df[df.rate_mode == rm], series, "delta_tax_revenue_bn",
                   "Change in tax revenue (rec CIT / forg ETR)",
                   f"CFB only vs CFB + digital ({lbl})", f"cfbVScombined_rev{suf}")
        fig_series(df[df.rate_mode == rm], series, "pct_current_tax_revenue",
                   "Change in tax revenue, % of current tax revenue",
                   f"CFB only vs CFB + digital ({lbl})", f"cfbVScombined_pct{suf}", unit="%")


def _metric_val(res, ig, mi):
    """mi: 0 = Change in taxable profits $bn, 1 = Change in tax revenue $bn, 2 = % of current tax."""
    dp, dr, tr = res[ig]
    if mi == 0:
        return dp
    if mi == 1:
        return dr
    return 100.0 * (dr * 1e9) / tr if (tr and tr > 0) else np.nan


def fig_scenarios_per_formula(measure_col="destcombined",
                              measure_lbl="CFB + digital (combined)",
                              rate_mode="loss_cit_gain_etr"):
    """Per formula family + per metric: origin vs destination-based sales by
    income group (the bars), with the three resource scenarios as panels SIDE
    BY SIDE (resources ignored / excluded / + min-royalty floor). One figure per
    (family, metric). Reported-only sample, 2016-2022."""
    igs = INCOME_ORDER
    x = np.arange(len(igs))
    w = 0.26
    metrics = [(0, "Change in taxable profits", "$bn", "profits"),
               (1, "Change in tax revenue (rec CIT / forg ETR)", "$bn", "revenue"),
               (2, "Change in tax revenue, % of current tax", "%", "pct")]
    for fam, fam_lbl in FAMILIES:
        # Preload origin / destination / destination+nexus spec for each scenario.
        # variants: ("" → origin, "_destcombined", "_destcombined_nexus")
        variant_suffixes = ["", "_" + measure_col, "_" + measure_col + "_nexus"]
        # Use the descriptive scenario name (not the S1/S2/S3 code) as panel title.
        loaded = [(desc, [load_spec(fam + suf, rate_mode, est_dir)
                          for suf in variant_suffixes])
                  for _slbl, desc, est_dir in SCENARIOS]
        if all(all(r is None for r in res) for _, res in loaded):
            print(f"  [skip] scenarios {fam}: no data")
            continue
        labels = ["Origin", "Destination", "Destination + nexus"]
        colours = [_OC, _DC, _NC]
        for mi, mlbl, unit, mtag in metrics:
            igs = _igs(mi == 0)   # mi==0 is the tax-base (Change in taxable profit) metric
            x = np.arange(len(igs))
            fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)
            for ax, (desc, res) in zip(axes, loaded):
                for j, (lab, col, r) in enumerate(zip(labels, colours, res)):
                    if r is None:
                        continue
                    ax.bar(x + (j - 1) * w, [_metric_val(r, ig, mi) for ig in igs],
                           w, label=lab, color=col)
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
    for c in ["theoretical_profit", "reported_profit", "revenue_gain_from_ut",
              "tax_revenue_current_usd"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def _series_vals(d, metric):
    """Per income group (low/middle/high/hub/global) value for `metric` ∈
    {profit_usd ($bn), profit_pct (% reported base), rev_usd ($bn),
    rev_pct (% current tax)}."""
    out = {}
    for ig in INCOME_ORDER:
        sub = (d[d["bk"].isin(("low", "middle", "high", "hub"))] if ig == "global"
               else d[d["bk"] == ig])
        dprofit = (sub["theoretical_profit"] - sub["reported_profit"]).sum()  # musd
        base = sub["reported_profit"].sum()                                    # musd
        drev = sub["revenue_gain_from_ut"].sum()                               # musd
        tr = sub["tax_revenue_current_usd"].sum()                              # USD
        if metric == "profit_usd":
            out[ig] = dprofit / 1e3
        elif metric == "profit_pct":
            # NaN unless the profit base is strictly positive — a % against a
            # non-positive base flips sign and misleads (cf. script 8's
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
    s2_dir = SCENARIOS[1][2]   # excl_resource (reported-only) est dir
    igs = INCOME_ORDER
    x = np.arange(len(igs))
    w = 0.26
    colors = [_OC, _DC, _NC]
    specs = [
        ("taxable_profits", "profit_usd", "Change in taxable profit (USD bn)",
         "profit_pct", "Change in taxable profit (% of reported profit base)"),
        ("revenue", "rev_usd", "Change in tax revenue (USD bn)",
         "rev_pct", "Change in tax revenue (% of current tax revenue)"),
    ]
    for meas_col, meas_lbl in [("destcombined", "CFB + digital"), ("destcfb", "CFB only")]:
        variants = [("", "Origin"), (f"_{meas_col}", "Destination"),
                    (f"_{meas_col}_nexus", "Destination + nexus")]
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
                        ax.bar(x + (j - 1) * w, [sv[ig] for ig in igs], w,
                               label=vl, color=colors[j])
                    ax.axhline(0, color="k", lw=0.6)
                    ax.set_xticks(x)
                    ax.set_xticklabels([INCOME_LABEL[i] for i in igs])
                    ax.set_ylabel(ylab)
                    ax.grid(axis="y", alpha=0.3)
                metric_name = ("taxable profit" if tag == "taxable_profits"
                               else "tax revenue")
                pct_of = ("reported profit base" if tag == "taxable_profits"
                          else "current tax revenue")
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
        sub = (d[d["bk"].isin(("low", "middle", "high", "hub"))] if ig == "global"
               else d[d["bk"] == ig])
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
    series = [("", "Origin", _OC),
              ("_destcfb", "Consumer-facing (CFB)", _DC),
              ("_destcombined", "CFB + digital (combined)", _NC)]
    igs = _igs(True)   # taxable-profit reallocation → drop meaningless 'global'
    x = np.arange(len(igs)); w = 0.26
    loaded = [(_load_df(fam + vs, s2_dir), lbl, col) for vs, lbl, col in series]
    if all(d is None for d, _, _ in loaded):
        print("  [skip] cfbVScombined sales_employees: no data"); return
    fig, (axu, axp) = plt.subplots(1, 2, figsize=(14, 5.6))
    for j, (d, lbl, col) in enumerate(loaded):
        if d is None:
            continue
        res = _profit_series_posbase(d, igs)
        axu.bar(x + (j - 1) * w, [res[ig][0] for ig in igs], w, label=lbl, color=col)
        axp.bar(x + (j - 1) * w, [res[ig][1] for ig in igs], w, label=lbl, color=col)
    for ax, ylab, title in [
        (axu, "Change in taxable profit (USD bn)", "Change in USD (bn)"),
        (axp, "Change in taxable profit (% of reported profit base)",
         "Change as % of reported profit base"),
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
    fig.text(0.5, 0.005, note, ha="center", va="bottom", fontsize=7.5, wrap=True,
             color="#444444")
    fig.tight_layout(rect=[0, 0.08, 1, 0.91])
    out = FIGURES_DIR / "fig_cfbVScombined_profits.png"
    fig.savefig(out, dpi=140)
    plt.close(fig)
    print(f"  wrote {out.name}  (sales+employees only, with % panel)")


def main():
    df = collect()
    df.to_csv(TABLES_DIR / "destination_vs_origin_summary.csv", index=False)
    print(f"wrote {TABLES_DIR / 'destination_vs_origin_summary.csv'} ({len(df)} rows)")
    for mkey, _mcol, mlbl in MEASURES:
        # Change in taxable profits is rate-mode invariant → use one rate-mode subset.
        fig_for_measure(df[df.rate_mode == RATE_MODES[0][0]], mkey, mlbl,
                        "delta_taxable_profits_bn", "Change in taxable profits")
        for rm, rm_lbl in RATE_MODES:
            fig_for_measure(df[df.rate_mode == rm], mkey, mlbl,
                            "delta_tax_revenue_bn", f"Change in tax revenue ({rm_lbl})", tag=f"_{rm}")
            fig_for_measure(df[df.rate_mode == rm], mkey, mlbl,
                            "pct_current_tax_revenue",
                            f"Change in tax revenue, % of current tax revenue ({rm_lbl})",
                            tag=f"_pct_{rm}", unit="%")
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


if __name__ == "__main__":
    main()
