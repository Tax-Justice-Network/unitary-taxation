"""
Shared machinery for the paper-exhibit (7-series) scripts.

Technical helpers only — no exhibit is produced here. Each concept script
(7d main results, 7b formula results, 7c break-even & leakage,
7f destination sales, …) imports from this module to load the estimation
summaries and render its own figures and tables in the paper style.

Contents:
  1. Paper conventions (window, headline spec, labels)
  2. Estimation-summary loaders (per-country metric series)
  3. Table formatting (income-group/region grouping, % columns, CSV+markdown)
  4. Figure panel helpers (two-panel income-group / scenario / country layouts)

Shared helpers for the 7-series paper-exhibit scripts.
"""
import glob
import os
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

import config
import _scenario_machinery as _sc
from _brand import HATCH_CYCLE, PALETTE

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC)


# ── 1. Paper conventions ─────────────────────────────────────────────────────
# Paper deliverables report the PER-YEAR AVERAGE over these years (2020
# excluded as the COVID outlier); monetary aggregates are divided by
# N_AVG_YEARS after the per-year(-deflated) sum.
AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
N_AVG_YEARS = len(AVG_YEARS)
YEARS = AVG_YEARS
WINDOW = "yearly avg 2016–2022 (excl. 2020)"

# Headline destination concept: all-MNE destination sales + the MNE share of
# BaTIS digitally-deliverable services imports.
HEADLINE_FORMULA = "sales_employees_destmnedds"
ETR = "domfor"                 # cell-matched domestic/foreign ETR (headline spec)
RATE = "loss_cit_gain_etr"     # ETR-CIT: gains at CIT, losses at ETR
THRESHOLD = "inf"

REV_CIT = "delta_total_gvt_revenue_recCIT_forgETR_musd"   # gains at CIT, losses at ETR
REV_ETR = "delta_total_gvt_revenue_recETR_forgETR_musd"   # both at ETR
REV_CIT_PCT = "delta_total_gvt_revenue_recCIT_forgETR_pct_revenue"
REV_ETR_PCT = "delta_total_gvt_revenue_recETR_forgETR_pct_revenue"

# All formulas on the complete destination measure — the headline — so the
# family comparison is like-for-like.
PAPER_4FORMULAS = [
    ("sales_employees_destmnedds", "Sales & employees"),
    ("ccctb_destmnedds", "CCCTB"),
    ("three_factors_destmnedds", "Three-factor"),
    ("double_weighted_sales_destmnedds", "Double-weighted sales"),
]
# Destination-concept comparison, all on the employees + sales base:
# destination (headline), + physical-establishment requirement, origin;
# ablations kept for the tables.
FIG_DEST_MEASURES = [
    ("sales_employees_destmnedds", "Destination-based"),
    ("sales_employees_destmnedds_nexus", "Destination + nexus"),
    ("sales_employees", "Origin-based"),
]
ABLATION_MEASURES = [
    ("sales_employees_destmnedds", "Complete measure"),
    ("sales_employees_destmne", "Without digital services"),
    ("sales_employees_destcfb", "Consumer-facing only"),
]
SALES_SPECS = [
    ("sales_employees_destmnedds", "destination (headline measure)"),
    ("sales_employees_destmnedds_nexus", "destination + nexus"),
    ("sales_employees", "origin-based"),
    ("sales_employees_destmne", "robustness: without digital services"),
    ("sales_employees_destcfb", "robustness: consumer-facing only"),
]

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
IG_LABELS_PAPER = {
    "low_income": "Low\nincome", "lower_middle_income": "Lower middle\nincome",
    "upper_middle_income": "Upper middle\nincome", "high_income": "High\nincome",
    "tax_haven": "Tax\nhavens",   # display label
}

# Panel titles (the ONLY text baked into the figure image; the overall title
# and the explanatory note live in the Word caption).
TP_ABS = "Change in taxable profit (USD bn)"
TP_PCT = "% of current profit base"
RV_ABS = "Change in tax revenue (USD bn)"
RV_PCT = "% of current corporate tax paid"

# Scenario dicts with the full formula set loaded, per sample. Callers pass
# these to build_summary so every figure/table can select what it needs.
_ALL_KEYS = []
for _lst in (PAPER_4FORMULAS, FIG_DEST_MEASURES, ABLATION_MEASURES):
    for _k, _l in _lst:
        if _k not in _ALL_KEYS:
            _ALL_KEYS.append(_k)
ALL_FORMULAS = [(k, k) for k in _ALL_KEYS]   # labels overridden per figure

SCN_REPORTED = [dict(s, formulas=ALL_FORMULAS)
                for s in _sc.SCENARIOS_REPORTED[:3]]
SCN_GRAVITY = [
    {"key": "ignorant_gravity", "label": "Resources ignored",
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
SCEN_KEYS = {
    "reported_only": {"ignorant": "ignorant_reported", "excl": "excl_reported",
                      "floored": "excl_floored_reported"},
    "gravity": {"ignorant": "ignorant_gravity", "excl": "excl_gravity",
                "floored": "excl_floored_gravity"},
}
SAMPLES = ["reported_only", "gravity"]


def figdir(sample):
    """Reported-sample figures are the paper's main-text exhibits; the imputed
    (gravity) sample's figures belong to the Appendix document."""
    topic = "paper/main_text" if sample == "reported_only" else "paper/appendix"
    return config.output_dirs(topic)[1]


def tabledir(sample):
    topic = "paper/main_text" if sample == "reported_only" else "paper/appendix"
    return str(config.output_dirs(topic)[0])


def figdir_appendix_b():
    """Region-grouped figure twins for the paper's Appendix B (Results by world
    region). Reported sample only — Appendix B mirrors the main-text income-group
    figures, grouped by world region instead."""
    return config.output_dirs("paper/appendix_b")[1]


# Wrapped world-region tick labels for the Appendix-B figures (two lines for the
# long names, matching the IG_LABELS_PAPER convention).
REGION_LABELS_PAPER = {
    "Africa": "Africa", "Asia": "Asia", "Latin America": "Latin\nAmerica",
    "Caribbean/American isl.": "Caribbean\n& Am. isl.",
    "Northern America": "Northern\nAmerica", "Europe": "Europe", "Oceania": "Oceania",
}


def region_figures(build_fn):
    """Run build_fn() with the figure machinery switched to WORLD-REGION grouping,
    then reset to income group. build_fn should emit its figure(s) into
    figdir_appendix_b(). Region % panels use the generic Σrevenue/Σcash-tax
    denominator (the income-group cash-tax override does not apply to regions)."""
    _sc.set_grouping(region=True, order=REGION_ORDER, labels=REGION_LABELS_PAPER)
    try:
        build_fn()
    finally:
        _sc.set_grouping()   # reset to income group


def paper_summary(sample):
    """build_summary for one sample on the paper window with the full formula
    set, in constant BASE_YEAR USD. Returns None when the sample's estimation
    outputs are absent or predate the current formulas."""
    _sc._DEFLATE_TO_BASE = True
    scen = SCN_REPORTED if sample == "reported_only" else SCN_GRAVITY
    try:
        s = _sc.build_summary(YEARS, scen, variant="")
    except ValueError as e:
        print(f"  [skip] {sample} summaries lack the current formulas ({e}); "
              "rerun the estimation passes, then rerun this script.")
        return None
    if s is None or s.empty:
        return None
    return s


def ghost_by_income(sample="reported_only"):
    """The by-income table with each year's monetary values additionally
    multiplied by 7a's coverage scale factor (sample → global MNE profit) —
    the grey ghost bars behind the absolute panels. None when the scale-factor
    table has not been produced (run 7a first)."""
    _sf_csv = config.output_dirs("paper/main_text")[0] / "scaleup_yearly.csv"
    if not _sf_csv.exists():
        print(f"  [no ghost bars] scale-factor table missing: {_sf_csv} — run 7a first")
        return None
    _sc._YEAR_SCALE_FACTORS = (pd.read_csv(_sf_csv)
                               .set_index("year")["scale_factor"].to_dict())
    try:
        s = paper_summary(sample)
        return None if s is None else _sc.build_by_income(s)
    finally:
        _sc._YEAR_SCALE_FACTORS = None


# ── 2. Estimation-summary loaders ────────────────────────────────────────────
_NAME_OVR = getattr(config, "COUNTRY_NAME_OVERRIDES", {})
try:
    import pycountry

    def cname(iso):
        if str(iso) in _NAME_OVR:
            return _NAME_OVR[str(iso)]
        c = pycountry.countries.get(alpha_3=str(iso))
        return c.name if c else str(iso)
except Exception:
    def cname(iso):
        return _NAME_OVR.get(str(iso), str(iso))

# Thin-CbCR-coverage flag (footnote [2]): countries whose
# estimate rests on <10 reported cells, <3 reporting parents or <4 of 6 years.
from _data_coverage import thin_iso_set, coverage_table, FOOTNOTE_TEXT as THIN_FOOTNOTE  # noqa: E402
_THIN_ISO = None


def thin_isos():
    global _THIN_ISO
    if _THIN_ISO is None:
        _THIN_ISO = thin_iso_set(coverage_table(write=True))
        print(f"[coverage] thin-data flag [2] on {len(_THIN_ISO)} countries")
    return _THIN_ISO


def cname_flagged(iso):
    """Display name with the thin-coverage footnote marker appended."""
    return cname(iso) + (" [2]" if str(iso) in thin_isos() else "")


def _summary_path(sample, scenario):
    return os.path.join(str(config.estimates_dir(sample, scenario)),
                        "tables", "summary_country_year_long.csv")


def summary_exists(sample):
    return os.path.exists(_summary_path(sample, "excl_resource"))


def _filtered(sample, scenario, formula):
    p = _summary_path(sample, scenario)
    if not os.path.exists(p):
        return pd.DataFrame()
    d = pd.read_csv(p, low_memory=False)
    d = d[(d["formula_name"] == formula) & (d["etr_name"] == ETR)
          & (d["rate_mode"] == RATE)]
    if "etr_threshold" in d.columns and d["etr_threshold"].astype(str).nunique() > 1:
        d = d[d["etr_threshold"].astype(str) == THRESHOLD]
    if "year" in d.columns:
        d = d[d["year"].isin(YEARS)]
    return d


_DEFL = config.deflator_to_base()   # year → factor to constant BASE_YEAR USD


def rev_musd(sample, scenario, formula):
    """Δ tax revenue in constant BASE_YEAR US$ millions per year (each year
    deflated before summing, then divided by the year count)."""
    d = _filtered(sample, scenario, formula)
    if d.empty:
        return pd.Series(dtype=float)
    d = d.assign(_v=d["revenue_gain_from_ut"] * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["_v"].sum() / N_AVG_YEARS


def taxbase_musd(sample, scenario, formula):
    """Δ taxable profit (theoretical − reported), same units/convention."""
    d = _filtered(sample, scenario, formula)
    if d.empty or "theoretical_profit" not in d.columns or "reported_profit" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(_tb=(d["theoretical_profit"] - d["reported_profit"]) * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["_tb"].sum() / N_AVG_YEARS


def reported_musd(sample, scenario, formula=HEADLINE_FORMULA):
    """Currently-reported profit base — the reference for taxable-profit %."""
    d = _filtered(sample, scenario, formula)
    if d.empty or "reported_profit" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(v=d["reported_profit"] * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["v"].sum() / N_AVG_YEARS


def current_rev_musd(sample, formula=HEADLINE_FORMULA):
    """Corporate tax currently paid by the sample MNEs — THE revenue-%
    denominator (every revenue comparison is vs taxes on MNE profits, never
    total government tax revenue)."""
    d = _filtered(sample, "excl_resource", formula)
    if d.empty or "current_tax_paid_cash_musd" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(v=pd.to_numeric(d["current_tax_paid_cash_musd"], errors="coerce")
                 * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["v"].sum() / N_AVG_YEARS


def posbase_musd(sample, formula=HEADLINE_FORMULA):
    """Positive reported profit base (yearly clip at 0) — the taxable-profit %
    denominator (positive-base convention, matching the figures' % panels)."""
    d = _filtered(sample, "excl_resource", formula)
    if d.empty or "reported_profit" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(v=pd.to_numeric(d["reported_profit"], errors="coerce").clip(lower=0)
                 * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["v"].sum() / N_AVG_YEARS


def oecd_cit_revenue_musd():
    """Total corporate income tax revenue per country: OECD Global Revenue
    Statistics (DSD_REV_COMP_GLOBAL@DF_RSGLOBAL, category T_1200, consolidated
    general government S13, USD). Per-year average over AVG_YEARS in constant
    BASE_YEAR USD millions, indexed by ISO3 (~138 countries; others NaN)."""
    p = os.path.join(_ROOT, "data", "raw",
                     "tax_rates/oecd_rsglobal_cit_revenue_t1200_s13_usd_2026-07.csv")
    d = pd.read_csv(p)
    d = d[d["year"].isin(AVG_YEARS)].copy()
    d["v"] = d["cit_revenue_usd"] * d["year"].map(_DEFL)
    # average over the years the country actually has (not ÷6 blindly): RSGLOBAL
    # lags 1-2 years for some countries; a missing 2022 should not deflate the mean.
    return d.groupby("iso3")["v"].mean() / 1e6


def etr_cit(sample):
    """Current average ETR (excl_resource) and statutory CIT per country, from a
    country_estimates file (formula-invariant), as fractions."""
    base = os.path.join(str(config.estimates_dir(sample, "excl_resource")),
                        "tables", "excl_resource")
    fs = [f for f in glob.glob(os.path.join(base, f"country_estimates__{HEADLINE_FORMULA}__*.csv"))
          if "average" in f and "loss_cit_gain_etr" in f and "etrmax_inf" in f]
    if not fs:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    c = pd.read_csv(fs[0], low_memory=False)
    return (c.groupby("iso_partner")["etr_average_excl_resource"].mean(),
            c.groupby("iso_partner")["cit"].mean())


# WB income groups for ex-representation-havens (the data column still says
# "tax_haven" for them until a 1_clean rerun propagates the current
# TAX_HAVENS_REPRESENTATION list). Only needed for the stale-column overlay below.
_DEHUBBED_IG = {
    "HUN": "high_income", "EST": "high_income",
    "LVA": "high_income", "CRI": "upper_middle_income",
    "LBN": "lower_middle_income", "LBR": "low_income",
}


def income_group(sample):
    p = _summary_path(sample, "excl_resource")
    d = pd.read_csv(p, usecols=["iso_partner", "wb_income_group"], low_memory=False)
    g = d.drop_duplicates("iso_partner").set_index("iso_partner")["wb_income_group"]
    # Overlay the CURRENT config haven list — the data column is stale until the
    # 1_clean rerun; this is a no-op once the files carry the new classification.
    hub = config.TAX_HAVENS_REPRESENTATION
    stale = g.index[(g == "tax_haven") & ~g.index.isin(hub)]
    g.loc[stale] = [_DEHUBBED_IG.get(i, "high_income") for i in stale]
    g[g.index.isin(hub)] = "tax_haven"
    # COK fallback (WB non-member; high income since the FY2025 update). The
    # classification is set in 1_clean's manual_income_map; this guard covers
    # any estimate file that lacks it and is otherwise a no-op.
    if "COK" in g.index and not ("COK" in hub):
        g.loc["COK"] = "high_income"
    return g


def region(sample):
    """iso -> region_tjn (geographic grouping), from the same summary file."""
    p = _summary_path(sample, "excl_resource")
    d = pd.read_csv(p, usecols=["iso_partner", "region_tjn"], low_memory=False)
    return d.drop_duplicates("iso_partner").set_index("iso_partner")["region_tjn"]


def floor_royalty_musd(sample="reported_only"):
    """Minimum-royalty add-on in constant BASE_YEAR US$ millions per year. For
    the reported sample only is_distributed==0 rows count (script 4's
    _reallocate_floor_to_reported places each source's full add-on there, so
    the country totals are preserved)."""
    p = os.path.join(_ROOT, "data", "final", "cbcr_main_excl_resource_floored.csv")
    d = pd.read_csv(p, usecols=["iso_partner", "year", "is_distributed",
                                "floor_add_on_cat1_usd"], low_memory=False)
    if sample == "reported_only":
        d = d[d["is_distributed"] == 0]
    d = d[d["year"].isin(AVG_YEARS)]
    d = d.assign(_v=pd.to_numeric(d["floor_add_on_cat1_usd"], errors="coerce")
                 * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["_v"].sum() / 1e6 / N_AVG_YEARS


def consolidation_rev_musd(sample):
    p = os.path.join(
        str(config.output_dirs("deliverables/loss_consolidation_sensitivity")[0]),
        "loss_consolidation_country_long.csv")
    if not os.path.exists(p):
        return pd.Series(dtype=float)
    d = pd.read_csv(p, low_memory=False)
    # Note: the etr filter is essential — the long file carries BOTH the
    # "average" and "domfor" families for the same (sample, scenario, formula,
    # rate, threshold); without it the groupby-sum would silently DOUBLE every
    # country's consolidation revenue.
    d = d[(d.get("sample") == sample) & (d["scenario"] == "excl_resource")
          & (d["formula"] == HEADLINE_FORMULA) & (d["etr"] == ETR)
          & (d["rate_mode"] == RATE)
          & (d["etr_threshold"].astype(str) == THRESHOLD)]
    if "year" in d.columns:
        d = d[d["year"].isin(AVG_YEARS)]
    # 7g already emits per-year averages, in millions. Return as-is.
    return d.groupby("iso_partner")["revenue_gain_loss_consolidated_musd"].sum()


# ── 3. Table formatting ──────────────────────────────────────────────────────
IG_ORDER = ["low_income", "lower_middle_income", "upper_middle_income",
            "high_income", "tax_haven"]
IG_HEADING = {
    "low_income": "LOW-INCOME",
    "lower_middle_income": "LOWER-MIDDLE-INCOME",
    "upper_middle_income": "UPPER-MIDDLE-INCOME",
    "high_income": "HIGH-INCOME",
    "tax_haven": "TAX HAVENS",   # display label
}
# Parallel geographic grouping (region_tjn column): every income-group table
# gets a "…_by_region" counterpart. Tax havens are NOT pulled out here (a
# haven is grouped with its geographic region).
REGION_ORDER = ["Africa", "Asia", "Latin America", "Caribbean/American isl.",
                "Northern America", "Europe", "Oceania"]
REGION_HEADING = {r: r.upper() for r in REGION_ORDER}


def with_pct(df_final, base_col, value_cols):
    """Append '<col> (%)' columns = 100 × col ÷ base_col. Where base ≤ 0, mark
    as footnote [1]; extreme percentages (>1,000%) get footnote [3]. Applied
    AFTER finalise so the group heading rows get the ratio of group sums."""
    base = pd.to_numeric(df_final[base_col], errors="coerce")
    df_final["_has_negative_basis"] = (base <= 0)
    # Heading carries the denominator where it is the positive-only profit base
    # — "%" alone would suggest net reported profits.
    pct_suffix = (" (% of positive reported profits)" if "positive" in str(base_col)
                  else " (%)")
    for c in value_cols:
        pct = 100 * pd.to_numeric(df_final[c], errors="coerce") / base
        pct_r = np.round(pct, 1)
        pct_col = np.where(
            base > 0,
            np.where(np.abs(pct_r) > 1000,
                     pd.Series(pct_r).map(lambda v: f"{v:,.0f} [3]").to_numpy(),
                     pct_r.astype(object)),
            # NaN base = denominator not available -> blank, NOT "losses reported".
            np.where(base.isna(), "", "[1]"))
        df_final[c + pct_suffix] = pct_col
    numeric_cols = [c for c in df_final.columns
                    if c not in [v + pct_suffix for v in value_cols]
                    and c != "_has_negative_basis"]
    return df_final.round(1)


def finalise(df, order_iso, grp, group_order=IG_ORDER, headings=IG_HEADING,
             other_label="OTHER / UNCLASSIFIED"):
    """Group countries by a classification (income-group / tax-haven class by
    default, or region_tjn when the region variants are passed). Each group is
    led by an UPPERCASE heading row carrying the aggregate (sum for USD
    columns, mean for % columns), followed by its countries alphabetically."""
    df = df.reindex(order_iso)
    rows = []
    order = list(group_order) + ["__other__"]
    for g in order:
        if g == "__other__":
            isos = sorted([i for i in df.index if grp.get(i) not in group_order],
                          key=lambda i: cname(i).lower())
            heading = other_label
        else:
            isos = sorted([i for i in df.index if grp.get(i) == g],
                          key=lambda i: cname(i).lower())
            heading = headings.get(g, g.upper())
        if not isos:
            continue
        agg = {"country": heading}
        for col in df.columns:
            s = pd.to_numeric(df.loc[isos, col], errors="coerce")
            agg[col] = s.mean() if ("%" in col or "pct" in str(col).lower()) else s.sum()
        rows.append(agg)                       # heading + aggregate ABOVE the group
        for i in isos:
            rec = {"country": cname_flagged(i)}
            rec.update(df.loc[i].to_dict())
            rows.append(rec)
    out = pd.DataFrame(rows, columns=["country"] + list(df.columns))
    return out.round(1)


def _cap_first(s):
    """Capitalise the first alphabetic character of a header (leaves the rest)."""
    s = str(s)
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
    return s


def write_table(df, sample, name, tables_dir):
    """CSV + paste-ready markdown with the standard footnotes."""
    df = df.drop(columns=["_has_negative_basis"], errors="ignore")
    df = df.rename(columns={c: _cap_first(c) for c in df.columns})
    csv = os.path.join(tables_dir, f"{name}__{sample}.csv")
    df.to_csv(csv, index=False)
    from _latex_table import csv_to_latex   # brand-coloured Overleaf twin
    csv_to_latex(csv)
    md = os.path.join(tables_dir, f"{name}__{sample}.md")
    with open(md, "w", encoding="utf-8") as fh:
        cols = list(df.columns)
        fh.write("| " + " | ".join(str(c) for c in cols) + " |\n")
        fh.write("| " + " | ".join("---" for _ in cols) + " |\n")
        for _, r in df.iterrows():
            cells = ["" if pd.isna(v) else (f"{v:,.0f}" if isinstance(v, float) else str(v))
                     for v in r]
            fh.write("| " + " | ".join(cells) + " |\n")
        if "breakeven" in name:
            fh.write("\nA blank break-even rate means unitary taxation allocates the "
                     "jurisdiction essentially no — or negative — profit under that "
                     "formula, so no finite tax rate on the remaining base could "
                     "reproduce its current revenue (e.g. Luxembourg under sales & "
                     "employees, whose booked profit rests on assets rather than "
                     "employees or local sales). Aggregate rows omit a break-even rate "
                     "because rates cannot be meaningfully averaged across countries.\n")
        else:
            fh.write("\n[1] Percentage not calculated where the reported profit base is "
                     "zero or negative (countries with net losses). These countries are "
                     "reported as 'losses reported'.\n")
            fh.write("\n" + THIN_FOOTNOTE + "\n")
            fh.write("\n[3] Extreme percentage: the country's NET reported profit base is "
                     "close to zero (profit- and loss-making operations nearly cancel), so "
                     "the ratio is driven by the small denominator — read the absolute "
                     "change instead.\n")
        if "pct_of_cit" in name:
            fh.write("\nDenominator: total corporate income tax revenue (OECD Global "
                     "Revenue Statistics, category 1200, consolidated general government "
                     "S13), per-year average over the covered sample years, constant "
                     "2025 USD. Countries outside RSGLOBAL coverage (~90 of 226) show "
                     "no denominator and 'losses reported [1]' is not applicable to them.\n")
    print(f"  wrote {csv}  ({len(df)} countries)")


def blank_group_headings(df, cols):
    """Blank the given columns in the ALL-CAPS group-heading rows finalise
    inserts. Used for break-even ETRs, which cannot be averaged across
    countries (a mean of per-country rates is dominated by outliers and has no
    interpretation), so the aggregate row should carry no rate."""
    ctry = df["country"].astype(str)
    is_head = ctry.apply(lambda s: s == s.upper() and any(ch.isalpha() for ch in s))
    for c in cols:
        if c in df.columns:
            df.loc[is_head, c] = np.nan
    return df


def _pair_pct_columns(out, value_cols):
    """Reorder so each value column sits immediately next to its own '… (%)'
    column (USD, %, USD, %, …) instead of all-USD-then-all-%. Leading columns
    (country + reference bases) keep their position."""
    cols = list(out.columns)
    pct_map = {}
    for c in value_cols:
        for suf in (" (% of positive reported profits)", " (%)"):
            if c + suf in cols:
                pct_map[c] = c + suf
                break
    pct_display = set(pct_map.values())
    lead = [c for c in cols if c not in set(value_cols) and c not in pct_display]
    ordered = list(lead)
    for c in value_cols:
        if c in cols:
            ordered.append(c)
        if c in pct_map:
            ordered.append(pct_map[c])
    ordered += [c for c in cols if c not in ordered]   # safety net
    return out[ordered]


def emit_table(df, order_iso, grp, grp_reg, sample, name, tables_dir,
               pct_base=None, pct_cols=None, drop_base_col=False, pair_pct=False):
    """Write the income-group table AND a `…_by_region` counterpart from the
    same raw dataframe. drop_base_col=True removes the pct_base column from
    the OUTPUT after the % computation (the positive-only base is the %
    denominator but not shown as a column). pair_pct=True interleaves each
    value column with its own '… (%)' column (see _pair_pct_columns)."""
    def _fin(g, order, headings, other):
        out = finalise(df, order_iso, g, order, headings, other)
        out = with_pct(out, pct_base, pct_cols) if pct_base else out
        if drop_base_col and pct_base in out.columns:
            out = out.drop(columns=[pct_base])
        if pair_pct and pct_cols:
            out = _pair_pct_columns(out, pct_cols)
        return out
    write_table(_fin(grp, IG_ORDER, IG_HEADING, "OTHER / UNCLASSIFIED"),
                sample, name, tables_dir)
    write_table(_fin(grp_reg, REGION_ORDER, REGION_HEADING, "OTHER"),
                sample, name + "_by_region", tables_dir)


# ── 4. Figure panel helpers ──────────────────────────────────────────────────
def ig_twopanel(by_inc, scen_key, formulas, abs_col, pct_col, abs_title, pct_title,
                fname, figures_dir, usd_decimals=1, overall_title=None,
                ghost_by_inc=None):
    """Two panels (absolute | %), income groups on x, one bar per formula/measure.

    Always writes the untitled `fname` (the version the Word caption titles).
    If `overall_title` is given, ALSO writes `<stem>_titled.png` with the title
    baked in — a standalone version for slides / the web."""
    fkeys = [k for k, _ in formulas]
    flabs = [l for _, l in formulas]
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(fkeys))]
    scen = {"key": scen_key}
    pa = _sc._pivot(by_inc, scen, abs_col, fkeys)
    pp = _sc._pivot(by_inc, scen, pct_col, fkeys)
    # Grey ghost = scaled-to-global values, ABSOLUTE panel only (the % panel is
    # near-invariant to the scaling: numerator and denominator scale together).
    ghost_pa = (None if ghost_by_inc is None
                else _sc._pivot(ghost_by_inc, scen, abs_col, fkeys) / 1e3)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    _sc._grouped_bars(axes[0], pa / 1e3, flabs, colors, ylabel="", title=abs_title,
                      usd_decimals=usd_decimals, ghost_pivot=ghost_pa)
    _sc._grouped_bars(axes[1], pp, flabs, colors, ylabel="", title=pct_title, is_pct=True)
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


def scen_twopanel(by_inc, formula_key, scen_keys, scen_labels, abs_col, pct_col,
                  abs_title, pct_title, with_addon, fname, figures_dir,
                  usd_decimals=1, ghost_by_inc=None):
    """Two panels, income groups on x, one bar per resource treatment
    (scenario). with_addon hatches the minimum-royalty floor add-on."""
    sub = by_inc[by_inc["formula_name"] == formula_key]
    ghost_sub = (None if ghost_by_inc is None
                 else ghost_by_inc[ghost_by_inc["formula_name"] == formula_key])
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.4))
    _sc._scenario_machinery_panel(axes[0], sub, scen_keys, abs_col, "", False,
                                   with_addon, usd_decimals=usd_decimals,
                                   ghost_sub=ghost_sub)
    _sc._scenario_machinery_panel(axes[1], sub, scen_keys, pct_col, "", True, with_addon)
    axes[0].set_title(abs_title, fontsize=13)
    axes[1].set_title(pct_title, fontsize=13)
    colors = _sc.SCEN_COLOURS
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[i]) for i in range(len(scen_keys))]
    labels = list(scen_labels)
    if with_addon:
        handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="white", hatch="///",
                                      edgecolor="black"))
        labels.append("Minimum-royalty floor add-on")
    if ghost_sub is not None and not ghost_sub.empty:
        handles.append(plt.Rectangle((0, 0), 1, 1, facecolor=_sc.GHOST_GREY))
        labels.append(_sc.GHOST_LABEL)
    axes[0].legend(handles, labels, fontsize=8, loc="best", framealpha=0.85)
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=130)
    plt.close()
    print(f"  wrote {figures_dir / fname}")


def country_panel(ax, summary, iso, scen_keys, value_col, ylabel, title,
                  formulas=PAPER_4FORMULAS):
    """x = scenarios, grouped bars = the paper formulas, one country+metric.

    When any scenario is a minimum-royalty (``excl_floored*``) scenario, each of
    its bars is decomposed into the UT yield (solid base) plus the royalty floor
    add-on (hatched ``///`` top, black edge) — so the reader sees how much of the
    revenue is unitary taxation vs. the compelled minimum royalty. Non-floored
    scenarios have a zero add-on, so the hatched layer is invisible there. This
    mirrors the income-group split in Figure 5 (``_bar_panel``)."""
    from _scenario_machinery import FORMULA_COLOURS
    sub = summary[summary["iso_partner"] == iso]
    fkeys = [k for k, _ in formulas]
    flabs = [l for _, l in formulas]
    piv = (sub.pivot_table(index="scenario", columns="formula_name",
                           values=value_col, aggfunc="first")
           .reindex(scen_keys)[[k for k in fkeys]])
    # Royalty floor add-on (formula-independent; nonzero only in the floored
    # scenario). The total revenue already includes it, so the UT base is
    # total − add-on.
    addon_col = "resource_capture_addon_musd"
    has_floored = (any(str(k).startswith("excl_floored") for k in scen_keys)
                   and addon_col in sub.columns)
    if has_floored:
        addon_piv = (sub.pivot_table(index="scenario", columns="formula_name",
                                     values=addon_col, aggfunc="first")
                     .reindex(scen_keys).reindex(columns=fkeys).fillna(0.0))
    x = np.arange(len(scen_keys))
    n = len(fkeys)
    bw = 0.82 / n
    for i, k in enumerate(fkeys):
        vals = piv[k].values / 1e3
        pos = x + (i - (n - 1) / 2) * bw
        addon = (addon_piv[k].values / 1e3) if has_floored else np.zeros_like(vals)
        base = vals - addon
        ax.bar(pos, base, width=bw, color=FORMULA_COLOURS[i],
               hatch=HATCH_CYCLE[i % len(HATCH_CYCLE)],   # colour-blind redundancy
               edgecolor="white", linewidth=0.3)
        if has_floored:
            ax.bar(pos, addon, width=bw, bottom=base, facecolor=FORMULA_COLOURS[i],
                   hatch="///", edgecolor="black", linewidth=0.5)
    ax.axhline(0, color="grey", linewidth=0.5)
    # Headroom so all-positive panels don't fill the frame to the top.
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
    labs = list(flabs)
    if has_floored and float(np.nan_to_num(addon_piv.to_numpy()).sum()) != 0.0:
        handles.append(plt.Rectangle((0, 0), 1, 1, facecolor="white",
                                     hatch="///", edgecolor="black", linewidth=0.5))
        labs.append("of which: minimum royalty")
    ax.legend(handles, labs, fontsize=8, loc="best", framealpha=0.85)
