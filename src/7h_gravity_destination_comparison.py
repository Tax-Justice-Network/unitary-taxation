# %%
"""
7h — Gravity-sample results (Appendix C).

Extends the main-results story to the gravity-imputed sample, where the OECD's
aggregate ("other Africa", "other Asia", …) reporting lines are disaggregated to
individual countries by the García-Bernardo & Janský (2024) machine-learning
model (the single disaggregation method). Part 1 reproduces the three-scenario
income-group figures on that sample; Part 3 compares origin vs destination sales
and flags which low-income countries still lose under a destination measure
(persistent LIC destination losers: NER, MWI, BFA).

Headline specification: gravity-imputed full sample, resources excluded, employees + destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at statutory CIT and losses at ETR, per-year average over 2016–2022 (2020 excluded), constant 2025 US$.

Exhibit script — consumes the script-6 estimation summaries. Produces the
Appendix C gravity-sample figures and tables (three-scenario income-group +
origin-vs-destination on the imputed full sample).

Reads:
  output/estimates/with_imputed_rows/{1_resources_ignored,2_resources_excluded,3_minimum_royalty_added}/tables/…/country_estimates__*.csv — gravity-sample specs (script 5/6)

Writes:
  output/analysis/scenario_comparison/with_imputed_rows/…              — three-scenario income-group figures
  output/analysis/origin_vs_destination/with_imputed_rows/…            — origin-vs-destination comparison + LIC loser flags

Usage:
  python 7h_gravity_destination_comparison.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from config import output_dirs
from _brand import apply_tjn_style, ORIGIN_DEST_NEXUS

apply_tjn_style()


import _scenario_machinery as _sc
# (the report machinery lives in _scenario_machinery; the module-level display
# settings — SCENARIOS, SCEN_SHORT, DATA_BANNER, DATA_NOTE — are set on _sc
# below so the figure functions see them)

INCOME_GROUP_ORDER = _sc.INCOME_GROUP_ORDER
INCOME_GROUP_LABELS = _sc.INCOME_GROUP_LABELS

# %% MARK: 2. Config and constants
REPORT_TOPIC = "three_scenarios"
YEARS = list(range(2016, 2023))
WINDOW_LABEL = "2016–2022"
# Headline ETR family — must match Parts 1/3c, which inherit _scenario_machinery's
# DEFAULT_ETR ("domfor"): keeping Parts 3/3b on the same family ensures no
# panel of the deliverable silently mixes ETR families.
ETR = "domfor"
RATE = "loss_cit_gain_etr"

# (key, label, full_topic, full_topic, sample). The gravity-imputed full sample
# is the single full-mode sample, carried by the plain topics; the third and
# fourth tuple slots both hold the plain topic so existing unpacking holds.
SCENARIOS = [
    ("baseline", "Resources ignored",
     "unitary_taxation_disaggregated", "unitary_taxation_disaggregated",
     "disaggregated"),
    ("excl", "Resources excluded",
     "unitary_taxation_excl_resource", "unitary_taxation_excl_resource",
     "excl_resource"),
    ("floored", "Resources excluded + min. royalty floor",
     "unitary_taxation_excl_resource_floored",
     "unitary_taxation_excl_resource_floored",
     "excl_resource_floored"),
]

FORMULA_4FAM = [
    ("employees_payroll", "Employees + payroll"),
    ("ccctb", "CCCTB"),
    ("three_factors", "Three-factor"),
    ("double_weighted_sales", "Double-weighted sales"),
]

# Sales-using families and their origin / destination / destination+nexus
# variants, for the per-formula origin-vs-destination percentage figures.
SALES_FAMILIES = [
    ("ccctb", "CCCTB"),
    ("double_weighted_sales", "Double-weighted sales"),
    ("sales_employees", "Sales + employees"),
    ("three_factors", "Three-factor"),
]
DEST_VARIANTS = [
    ("", "Origin"),
    ("_destcombined", "Destination"),
    ("_destcombined_nexus", "Destination + nexus"),
]
# Destination measures available (combined = CFB + digital; cfb = consumer-facing
# only). Each is shown as origin / destination / destination+nexus.
DEST_MEASURES = [("destcombined", "CFB + digital"), ("destcfb", "CFB only")]
# All sales-factor variants to load into build_summary (origin + both measures
# × {plain, nexus}), so every figure can select what it needs.
DEST_VARIANTS_ALL = [("", "Origin")] + [
    (f"_{mc}{nx}", f"{ml} {'(+nexus)' if nx else ''}".strip())
    for mc, ml in DEST_MEASURES
    for nx in ("", "_nexus")
]
DEST_FORMULA_LIST = [
    (fk + vs, f"{fl} — {vl}")
    for fk, fl in SALES_FAMILIES
    for vs, vl in DEST_VARIANTS_ALL
]

# Gravity scenarios in the script-9 scenario dict format (full sample).
GRAVITY_SCENARIOS = [
    {"key": "ignorant_gravity", "label": "Resources ignored",
     "topic": "unitary_taxation_disaggregated",
     "sample": "disaggregated", "formulas": FORMULA_4FAM},
    {"key": "excl_gravity", "label": "Profits corrected for resource rent capture",
     "topic": "unitary_taxation_excl_resource",
     "sample": "excl_resource", "formulas": FORMULA_4FAM},
    {"key": "excl_floored_gravity",
     "label": "Profits corrected for resource rent capture + min. royalty floor",
     "topic": "unitary_taxation_excl_resource_floored",
     "sample": "excl_resource_floored", "formulas": FORMULA_4FAM},
]

# Same scenarios but with the full origin/destination/nexus formula list, for the
# per-formula origin-vs-destination percentage figures (Part 3c).
GRAVITY_SCENARIOS_DEST = [dict(s, formulas=DEST_FORMULA_LIST) for s in GRAVITY_SCENARIOS]

# Short scenario labels reused for figure titles / panels.
SCEN_SHORT_GRAVITY = {
    "ignorant_gravity": "S1: resources ignored",
    "excl_gravity": "S2: corrected for capture",
    "excl_floored_gravity": "S3: + min. royalty floor",
}

# Heading banner + explanatory footnotes shared across the gravity figures.
IMPUTED_BANNER = "gravity-imputed (full) sample"
IMPUTATION_NOTE = (
    "Imputed (full) sample: jurisdictions that report only via continent/rest-of-world "
    "aggregates are filled with the Garcia-Bernardo & Jansky (2024) gravity/ML model — "
    "gradient-boosted predictions of employees, sales and tangible assets from public "
    "gravity variables (GDP, distance, bilateral trade, FDI, governance); profit is then "
    "imputed from each country's reported productivity per factor. Imputed cells carry "
    "more uncertainty than directly-reported ones (quantified by the bootstrap SEs)."
)
DEST_NOTE = (
    "Destination-based sales reallocate the sales factor from where revenue is booked "
    "(origin) to the market where customers are — consumer-facing-business turnover plus "
    "digitally-delivered-services imports (OECD 2020). The nexus variant down-weights the "
    "market share by the covered fraction of each cell's MNE groups."
)


# %% MARK: 3. Loaders and helpers
def _footnote(fig, text):
    fig.text(0.5, 0.005, text, ha="center", va="bottom", fontsize=7.0,
             color="#444444", wrap=True)


# ─── Robust long-table loader (handles OneDrive dehydrated placeholders) ──────
def _read_csv_robust(path, **kw):
    path = str(path)
    try:
        return pd.read_csv(path, **kw)
    except (FileNotFoundError, OSError):
        # OneDrive placeholder did not hydrate on the Win32 open(); force a
        # byte copy via git-bash cp (a different file API), then read the copy.
        dst = os.path.join(tempfile.gettempdir(), "robust_" + os.path.basename(path))
        for cp in (r"C:\Program Files\Git\usr\bin\cp.exe", "cp"):
            try:
                subprocess.run([cp, path, dst], check=True)
                return pd.read_csv(dst, **kw)
            except Exception:
                continue
        raise


def load_long(topic):
    tables_dir, _ = output_dirs(topic)
    p = tables_dir / "summary_country_year_long.csv"
    if not p.exists():
        print(f"  [warn] no summary_country_year_long.csv for {topic}")
        return pd.DataFrame()
    return _read_csv_robust(p, low_memory=False)


def net_gain_by_country(topic, formula, etr=ETR, rate=RATE, years=YEARS):
    """PER-YEAR AVERAGE revenue_gain_from_ut per country for one
    (formula, etr, rate) — Σ over the window ÷ number of window years, so
    Parts 3/3b sit on the same per-year scale as the Part-1 scenario figures
    (build_summary divides by n_years too; a raw window sum would be ×7 the
    Part-1 scale)."""
    df = load_long(topic)
    if df.empty or formula not in set(df.get("formula_name", [])):
        return pd.DataFrame(
            columns=["iso_partner", "partner_jurisdiction", "wb_income_group",
                     "region_tjn", "net_gain_musd"]
        )
    df = df[
        (df["formula_name"] == formula)
        & (df["etr_name"] == etr)
        & (df["rate_mode"] == rate)
        & (df["year"].isin(years))
    ]
    g = (
        df.groupby(["iso_partner", "partner_jurisdiction", "wb_income_group",
                    "region_tjn"],
                   as_index=False, dropna=False)["revenue_gain_from_ut"]
        .sum()
        .rename(columns={"revenue_gain_from_ut": "net_gain_musd"})
    )
    g["net_gain_musd"] = g["net_gain_musd"] / len(years)
    return g


def by_income(country_df):
    s = (country_df.groupby("wb_income_group")["net_gain_musd"].sum()
         .reindex(INCOME_GROUP_ORDER))
    return s


REGION_ORDER = ["Africa", "Asia", "Latin America", "Caribbean/American isl.",
                "Northern America", "Europe", "Oceania"]


def by_region(country_df):
    return (country_df.groupby("region_tjn")["net_gain_musd"].sum()
            .reindex(REGION_ORDER))


# ─── Grouped-bar helper ───────────────────────────────────────────────────────
def grouped_income_bars(ax, series_by_label, colors, ylabel, title, scale=1e3):
    """series_by_label: dict label -> Series indexed by INCOME_GROUP_ORDER.
    Values are divided by `scale` (1e3 = musd→USD bn; pass 1 for percentages)."""
    labels = list(series_by_label)
    groups = [g for g in INCOME_GROUP_ORDER
              if any(pd.notna(series_by_label[l].get(g)) for l in labels)]
    x = np.arange(len(groups))
    n = len(labels)
    bw = 0.82 / max(n, 1)
    for i, lab in enumerate(labels):
        vals = [(series_by_label[lab].get(g) or 0) / scale for g in groups]
        ax.bar(x + (i - (n - 1) / 2) * bw, vals, width=bw, color=colors[i], label=lab)
    ax.axhline(0, color="grey", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([INCOME_GROUP_LABELS.get(g, g) for g in groups], fontsize=9)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontsize=12)
    ax.legend(fontsize=8, framealpha=0.85)


# %% MARK: 4. Part 1 — gravity scenario figures
# ─── PART 1 — gravity per-scenario standard figures ───────────────────────────
def part1_gravity_scenario_figures():
    _, figures_dir = output_dirs(f"{REPORT_TOPIC}/gravity")
    tables_dir, _ = output_dirs(f"{REPORT_TOPIC}/gravity")
    print("\nPART 1 — gravity per-scenario figures (full imputed sample)…")
    # Flag every script-9-built figure as the gravity-imputed sample + explain it.
    _sc.DATA_BANNER = IMPUTED_BANNER
    _sc.DATA_NOTE = IMPUTATION_NOTE
    summary = _sc.build_summary(YEARS, GRAVITY_SCENARIOS, variant="")
    if summary is None or summary.empty:
        print("  [skip] no gravity summary returned by build_summary")
        return
    by_inc = _sc.build_by_income(summary)
    summary.to_csv(tables_dir / "gravity_three_scenario_summary_long_2016_22.csv",
                   index=False)
    by_inc.to_csv(tables_dir / "gravity_three_scenario_by_income_group_2016_22.csv",
                  index=False)
    # region-breakdown counterpart
    _sc.build_by_income(summary, gcol="region_tjn").to_csv(
        tables_dir / "gravity_three_scenario_by_region_2016_22.csv", index=False)
    for n, scenario in enumerate(GRAVITY_SCENARIOS, start=1):
        print(f"  Scenario {n}: {scenario['label']} [{scenario['key']}]")
        _sc.make_scenario_figures(by_inc, scenario, figures_dir, n)

    # Three-scenario comparison per income group, for EACH formula family
    # (gravity sample). Reuse the _scenario_machinery comparison-figure machinery by pointing
    # its module-level SCENARIOS / SCEN_SHORT at the gravity scenarios (the
    # helpers key legend labels and bar order off those globals; FLOORED
    # detection is startswith).
    _sc.SCENARIOS = GRAVITY_SCENARIOS
    _sc.SCEN_SHORT = SCEN_SHORT_GRAVITY
    print("  Three-scenario comparison per formula (gravity)…")
    for fkey, flabel in FORMULA_4FAM:
        _sc.make_formula_scenario_machinery(by_inc, fkey, flabel, figures_dir)


# %% MARK: 5. Part 3 — origin vs destination
# ─── PART 3 — origin vs destination (gravity) ─────────────────────────────────
ORIGIN_F = "sales_employees"
DEST_F = "sales_employees_destmnedds"
DEST_NEXUS_F = "sales_employees_destmnedds_nexus"


def part3_origin_vs_destination():
    _, figures_dir = output_dirs(f"{REPORT_TOPIC}/comparison")
    tables_dir, _ = output_dirs(f"{REPORT_TOPIC}/comparison")
    print("\nPART 3 — origin vs destination sales (gravity sample)…")

    # 3a — by income group, one panel per scenario. Three series: origin /
    # destination / destination + nexus.
    inc_rows, reg_rows = [], []
    fig, axes = plt.subplots(1, 3, figsize=(18, 5.6), sharey=True)
    for ax, (key, label, _, grav_topic, _) in zip(axes, SCENARIOS):
        cg_o = net_gain_by_country(grav_topic, ORIGIN_F)
        cg_d = net_gain_by_country(grav_topic, DEST_F)
        cg_dn = net_gain_by_country(grav_topic, DEST_NEXUS_F)
        orig, dest, destnx = by_income(cg_o), by_income(cg_d), by_income(cg_dn)
        grouped_income_bars(
            ax, {"Origin sales": orig, "Destination sales": dest,
                 "Destination + nexus": destnx},
            ORIGIN_DEST_NEXUS,
            ylabel="Change in net UT revenue gain (USD bn per year)",
            title=label,
        )
        for ig in INCOME_GROUP_ORDER:
            inc_rows.append({"scenario": key, "wb_income_group": ig,
                             "origin_musd": orig.get(ig), "destination_musd": dest.get(ig),
                             "destination_nexus_musd": destnx.get(ig)})
        # region-breakdown counterpart of the same origin/destination comparison
        ro, rd, rdn = by_region(cg_o), by_region(cg_d), by_region(cg_dn)
        for rg in REGION_ORDER:
            reg_rows.append({"scenario": key, "region_tjn": rg,
                             "origin_musd": ro.get(rg), "destination_musd": rd.get(rg),
                             "destination_nexus_musd": rdn.get(rg)})
    fig.suptitle(
        "Origin vs destination sales — Change in net UT revenue gain by income group "
        f"({WINDOW_LABEL} per-year average, sales+employees, {ETR} ETR)   "
        f"[{IMPUTED_BANNER}]",
        fontsize=11.5, fontweight="bold",
    )
    _footnote(fig, DEST_NOTE + "  " + IMPUTATION_NOTE)
    plt.tight_layout(rect=[0, 0.09, 1, 0.94])
    f = figures_dir / "compare_origin_vs_destination_by_income.png"
    plt.savefig(f, dpi=130)
    plt.close()
    print(f"  wrote {f}")
    pd.DataFrame(inc_rows).to_csv(
        tables_dir / "compare_origin_vs_destination_by_income.csv", index=False)
    pd.DataFrame(reg_rows).to_csv(
        tables_dir / "compare_origin_vs_destination_by_region.csv", index=False)

    # 3b — low-income country-level table across all scenarios + a figure for the
    # baseline scenario showing which low-income countries lose under destination.
    lic_frames = []
    for key, label, _, grav_topic, _ in SCENARIOS:
        o = net_gain_by_country(grav_topic, ORIGIN_F)
        d = net_gain_by_country(grav_topic, DEST_F)
        dn = net_gain_by_country(grav_topic, DEST_NEXUS_F)
        o = o[o["wb_income_group"] == "low_income"][
            ["iso_partner", "partner_jurisdiction", "net_gain_musd"]
        ].rename(columns={"net_gain_musd": f"origin_{key}_musd"})
        d = d[d["wb_income_group"] == "low_income"][
            ["iso_partner", "net_gain_musd"]
        ].rename(columns={"net_gain_musd": f"dest_{key}_musd"})
        dn = dn[dn["wb_income_group"] == "low_income"][
            ["iso_partner", "net_gain_musd"]
        ].rename(columns={"net_gain_musd": f"destnexus_{key}_musd"})
        m = o.merge(d, on="iso_partner", how="outer").merge(
            dn, on="iso_partner", how="outer")
        lic_frames.append(m.set_index(["iso_partner", "partner_jurisdiction"]))
    lic = pd.concat(lic_frames, axis=1).reset_index()
    # Loser flags under destination per scenario.
    for key, *_ in [(s[0],) for s in SCENARIOS]:
        lic[f"dest_{key}_loses"] = lic[f"dest_{key}_musd"] < 0
    dest_cols = [f"dest_{k}_loses" for k, *_ in [(s[0],) for s in SCENARIOS]]
    lic["n_scenarios_lose_dest"] = lic[dest_cols].sum(axis=1)
    lic = lic.sort_values("dest_baseline_musd")
    lic.to_csv(tables_dir / "lic_origin_vs_destination.csv", index=False)
    print(f"  wrote {tables_dir / 'lic_origin_vs_destination.csv'}")

    # Figure: baseline scenario, low-income countries, origin vs destination.
    plot = lic.dropna(subset=["origin_baseline_musd", "dest_baseline_musd"], how="all").copy()
    plot = plot.sort_values("dest_baseline_musd")
    names = plot["partner_jurisdiction"].fillna(plot["iso_partner"]).astype(str)
    y = np.arange(len(plot))
    fig, ax = plt.subplots(figsize=(10, max(5, 0.42 * len(plot))))
    h = 0.27
    ax.barh(y + h, plot["origin_baseline_musd"] / 1e3, height=h,
            color=ORIGIN_DEST_NEXUS[0], label="Origin sales")
    ax.barh(y, plot["dest_baseline_musd"] / 1e3, height=h,
            color=ORIGIN_DEST_NEXUS[1], label="Destination sales")
    ax.barh(y - h, plot["destnexus_baseline_musd"] / 1e3, height=h,
            color=ORIGIN_DEST_NEXUS[2], label="Destination + nexus")
    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=8)
    ax.axvline(0, color="grey", linewidth=0.5)
    ax.set_xlabel("Change in net UT revenue gain (USD bn per year)")
    ax.set_title(
        "Low-income countries: origin vs destination sales (gravity-imputed, baseline)\n"
        "negative = country loses profit to other jurisdictions under unitary taxation",
        fontsize=11,
    )
    ax.legend(fontsize=9)
    _footnote(fig, DEST_NOTE + "  " + IMPUTATION_NOTE)
    plt.tight_layout(rect=[0, 0.06, 1, 1])
    f = figures_dir / "lic_origin_vs_destination_baseline.png"
    plt.savefig(f, dpi=130)
    plt.close()
    print(f"  wrote {f}")

    # Headline print: persistent destination losers among low-income countries.
    losers = lic[lic["n_scenarios_lose_dest"] == len(SCENARIOS)]
    print(f"\n  Low-income countries that LOSE under destination sales in all "
          f"{len(SCENARIOS)} scenarios:")
    for _, r in losers.iterrows():
        name = r["partner_jurisdiction"] or r["iso_partner"]
        print(f"    {r['iso_partner']} {str(name)[:28]:<30} "
              f"dest baseline {r['dest_baseline_musd']/1e3:+.2f} | "
              f"excl {r['dest_excl_musd']/1e3:+.2f} | "
              f"floored {r['dest_floored_musd']/1e3:+.2f} (USD bn)")


# %% MARK: 6. Part 3c — destination % figures
# ─── PART 3c — origin vs destination vs destination+nexus, % metrics, per formula
def part3c_destination_pct_figures():
    _, figures_dir = output_dirs(f"{REPORT_TOPIC}/comparison")
    tables_dir, _ = output_dirs(f"{REPORT_TOPIC}/comparison")
    print("\nPART 3c — origin/destination/nexus % figures, per formula (gravity)…")
    summ = _sc.build_summary(YEARS, GRAVITY_SCENARIOS_DEST, variant="")
    if summ is None or summ.empty:
        print("  [skip] no destination summary returned")
        return
    by_inc = _sc.build_by_income(summ)
    by_inc.to_csv(tables_dir / "gravity_destination_by_income_group_2016_22.csv",
                  index=False)
    _sc.build_by_income(summ, gcol="region_tjn").to_csv(
        tables_dir / "gravity_destination_by_region_2016_22.csv", index=False)

    scen_keys = [s["key"] for s in GRAVITY_SCENARIOS_DEST]
    # (metric column, axis label, filename tag)
    metrics = [
        ("delta_taxable_profits_pct",
         "Change in taxable profit (% of pre-UT reported profit base)", "pct_taxable_profits"),
        ("delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
         "Change in tax revenue (% of current total tax revenue)", "pct_revenue"),
    ]
    # origin / destination / destination+nexus colours.
    colors = ORIGIN_DEST_NEXUS

    for meas, meas_lbl in DEST_MEASURES:
        variants = [("", "Origin"), (f"_{meas}", "Destination"),
                    (f"_{meas}_nexus", "Destination + nexus")]
        for fkey, flabel in SALES_FAMILIES:
            for mcol, mlabel, mtag in metrics:
                fig, axes = plt.subplots(1, 3, figsize=(18, 5.6), sharey=True)
                for ax, skey in zip(axes, scen_keys):
                    series = {}
                    for vs, vl in variants:
                        sub = by_inc[(by_inc["scenario"] == skey)
                                     & (by_inc["formula_name"] == fkey + vs)]
                        series[vl] = (sub.set_index("wb_income_group")[mcol]
                                      .reindex(INCOME_GROUP_ORDER))
                    grouped_income_bars(ax, series, colors, ylabel=mlabel,
                                        title=SCEN_SHORT_GRAVITY.get(skey, skey), scale=1)
                fig.suptitle(
                    f"{flabel}: origin vs destination vs destination+nexus "
                    f"({meas_lbl}) — {mlabel.split('(')[0].strip()} "
                    f"({WINDOW_LABEL})   [{IMPUTED_BANNER}]",
                    fontsize=11.5, fontweight="bold",
                )
                _footnote(
                    fig,
                    "Percentages re-derived as Σnumerator / Σdenominator per income "
                    "group. " + DEST_NOTE + "  " + IMPUTATION_NOTE,
                )
                plt.tight_layout(rect=[0, 0.10, 1, 0.94])
                f = figures_dir / f"dest_{mtag}_{fkey}_{meas}.png"
                plt.savefig(f, dpi=130)
                plt.close()
                print(f"  wrote {f}")
    return by_inc


# %% MARK: 7. Part 4 — destination scenarios
# ─── PART 4 — three-scenario comparison on DESTINATION sales (no nexus), gravity
def part4_gravity_destination_scenarios(by_inc_dest):
    """Per formula family: compare the three resource scenarios using
    destination-based sales (no nexus) on the gravity sample. Reuses _scenario_machinery's
    make_formula_scenario_machinery on the *_destcombined formula variant, so
    the output mirrors the origin formula_comparison_* figures but on the
    destination key. Writes to output/analysis/scenario_comparison/with_imputed_rows/figures/."""
    if by_inc_dest is None or by_inc_dest.empty:
        print("\nPART 4 — [skip] no destination summary")
        return
    _, figures_dir = output_dirs(f"{REPORT_TOPIC}/gravity")
    _sc.SCENARIOS = GRAVITY_SCENARIOS
    _sc.SCEN_SHORT = SCEN_SHORT_GRAVITY
    print("\nPART 4 — three-scenario comparison on destination sales (no nexus, gravity)…")
    for mcol, mlbl in DEST_MEASURES:
        for fkey, flabel in SALES_FAMILIES:
            _sc.make_formula_scenario_machinery(
                by_inc_dest, f"{fkey}_{mcol}",
                f"{flabel} (destination, {mlbl})", figures_dir)


# %% MARK: 8. Part 5 — S2 origin vs destination
# ─── PART 5 — S2-only origin vs destination, USD + % side by side, per formula ─
def part5_s2_origin_vs_dest(by_inc_dest):
    """For the S2 (resources-excluded) gravity scenario only: per formula family
    and per destination measure (CFB+digital, CFB-only), one figure with Change in by
    income group in USD (left) and in % (right). Two figures per (family,
    measure): taxable profits and tax revenue. Series = origin / destination /
    destination + nexus."""
    if by_inc_dest is None or by_inc_dest.empty:
        print("\nPART 5 — [skip] no destination summary")
        return
    _, figures_dir = output_dirs(f"{REPORT_TOPIC}/comparison")
    print("\nPART 5 — S2 origin vs destination, USD + % (gravity)…")
    skey = "excl_gravity"
    colors = ORIGIN_DEST_NEXUS
    # (tag, USD musd col, USD axis label, pct col, pct axis label)
    specs = [
        ("taxable_profits", "delta_taxable_profits_musd",
         "Change in taxable profit (USD bn)", "delta_taxable_profits_pct",
         "Change in taxable profit (% of reported profit base)"),
        ("revenue", "delta_total_gvt_revenue_recCIT_forgETR_musd",
         "Change in tax revenue (USD bn)", "delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
         "Change in tax revenue (% of current tax revenue)"),
    ]
    for mcol, mlbl in DEST_MEASURES:
        variants = [("", "Origin"), (f"_{mcol}", "Destination"),
                    (f"_{mcol}_nexus", "Destination + nexus")]
        for fkey, flabel in SALES_FAMILIES:
            for tag, ucol, ulbl, pcol, plbl in specs:
                def ser(col):
                    out = {}
                    for vs, vl in variants:
                        sub = by_inc_dest[(by_inc_dest["scenario"] == skey)
                                          & (by_inc_dest["formula_name"] == fkey + vs)]
                        out[vl] = (sub.set_index("wb_income_group")[col]
                                   .reindex(INCOME_GROUP_ORDER))
                    return out
                fig, (axu, axp) = plt.subplots(1, 2, figsize=(14, 5.6))
                grouped_income_bars(axu, ser(ucol), colors, ylabel=ulbl,
                                    title="Absolute (USD bn)", scale=1e3)
                grouped_income_bars(axp, ser(pcol), colors, ylabel=plbl,
                                    title="As %", scale=1)
                fig.suptitle(
                    f"{flabel}: origin vs destination ({mlbl}) — "
                    f"{tag.replace('_', ' ')}, S2 resources excluded   "
                    f"[{IMPUTED_BANNER}]",
                    fontsize=11.5, fontweight="bold",
                )
                _footnote(fig, DEST_NOTE + "  " + IMPUTATION_NOTE)
                plt.tight_layout(rect=[0, 0.09, 1, 0.93])
                f = figures_dir / f"s2_origin_vs_dest_{tag}_{fkey}_{mcol}.png"
                plt.savefig(f, dpi=130)
                plt.close()
                print(f"  wrote {f}")


# %% MARK: 9. Run
def main():
    part1_gravity_scenario_figures()
    part3_origin_vs_destination()
    by_inc_dest = part3c_destination_pct_figures()
    part4_gravity_destination_scenarios(by_inc_dest)
    part5_s2_origin_vs_dest(by_inc_dest)
    print("\nDone.")


if __name__ == "__main__":
    main()
