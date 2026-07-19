"""
9j — Paper deliverable country tables (read-only over existing outputs).

For BOTH samples (reported_only = main text; gravity = Appendix E), country rows,
$bn per-year average over 2016-2022 excl. 2020 (6-year mean), headline formula
sales_employees_destcfb, revenues on the
ETR-CIT specification (rate_mode loss_cit_gain_etr: gains at CIT, losses at ETR):

  Table 1 (scenarios) — BOTH metrics per scenario, revenue-only for loss consolidation:
    Baseline (Δ taxable profit, Δ tax revenue)
    Excl. resource (Δ taxable profit, Δ tax revenue)
    + Minimum royalty (Δ taxable profit, Δ tax revenue = UT + floor royalty)
    Loss consolidation (Δ tax revenue only — it does not change the tax base)

  Table 2a — Δ taxable profit by formula (resources excluded)
  Table 2b — Δ tax revenue (ETR-CIT) by formula (resources excluded)
    formulas: sales_employees | sales_employees_destcombined | ccctb | three_factors | double_weighted_sales

No ISO / income-group columns in the deliverable tables (country name only).
Writes CSV + paste-ready markdown to output/unitary_taxation/across_samples/paper_tables/.
Usage: python 9j_paper_tables.py
"""
import os
import sys
import glob
import numpy as np
import pandas as pd

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC)
sys.path.insert(0, _SRC)
import config  # noqa: E402

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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

SAMPLES = ["reported_only", "gravity"]
SCEN_DIR = {"baseline": "baseline", "excl_resource": "excl_resource",
            "excl_resource_floored": "excl_resource_floored"}
# Paper deliverables report the PER-YEAR AVERAGE over these years (2020 excluded
# as the COVID outlier), not the aggregate sum. Monetary aggregates are divided by
# N_AVG_YEARS after the per-year(-deflated) sum.
AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
N_AVG_YEARS = len(AVG_YEARS)
YEARS = AVG_YEARS

# Headline destination concept (2026-07-12, user): all-MNE destination sales +
# the MNE share of BaTIS digitally-deliverable services imports. (The ADS-proxy
# third leg was retired the same day — paid ADS is already in the BaTIS leg.)
HEADLINE_FORMULA = "sales_employees_destmnedds"
ETR = "domfor"                           # cell-matched domestic/foreign ETR (headline 2026-07-12)
RATE = "loss_cit_gain_etr"               # ETR-CIT: gains at CIT, losses at ETR
THRESHOLD = "inf"

# All formulas use the complete destination measure — the headline — so the
# family comparison is like-for-like. (Destination concepts are compared
# separately in §5.4 / Figs 8–9, so no origin column here.)
FORMULAS = [
    ("sales_employees_destmnedds", "sales & employees"),
    ("ccctb_destmnedds", "CCCTB"),
    ("three_factors_destmnedds", "three-factor"),
    ("double_weighted_sales_destmnedds", "double-weighted sales"),
]
# Destination-concept comparison, all on the employees + sales base (§5.4 /
# Figs 8–9): destination (headline measure), + nexus, origin. The ablations
# (without digital services / consumer-facing only) remain as extra columns
# in this TABLE for robustness, though the figure shows only the three.
SALES_SPECS = [
    ("sales_employees_destmnedds", "destination (headline measure)"),
    ("sales_employees_destmnedds_nexus", "destination + nexus"),
    ("sales_employees", "origin-based"),
    ("sales_employees_destmne", "robustness: without digital services"),
    ("sales_employees_destcfb", "robustness: consumer-facing only"),
]
IG_ORDER = ["low_income", "lower_middle_income", "upper_middle_income",
            "high_income", "investment_hub"]

# Parallel geographic grouping (region_tjn column), so every income-group table
# also gets a "…_by_region" counterpart. Order + uppercase headings mirror the
# income-group machinery; investment hubs are NOT pulled out here (a haven is
# grouped with its geographic region), so regional aggregates include them.
REGION_ORDER = ["Africa", "Asia", "Latin America", "Caribbean/American isl.",
                "Northern America", "Europe", "Oceania"]
REGION_HEADING = {r: r.upper() for r in REGION_ORDER}


def _summary_path(sample, scenario):
    return os.path.join(_ROOT, "output", "unitary_taxation", sample,
                        SCEN_DIR[scenario], "tables", "summary_country_year_long.csv")


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


def _rev_bn(sample, scenario, formula):
    """Δ tax revenue in constant BASE_YEAR US$bn (each year deflated before summing)."""
    d = _filtered(sample, scenario, formula)
    if d.empty:
        return pd.Series(dtype=float)
    d = d.assign(_v=d["revenue_gain_from_ut"] * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["_v"].sum() / 1e3 / N_AVG_YEARS   # per-year average


def _taxbase_bn(sample, scenario, formula):
    """Δ taxable profit in constant BASE_YEAR US$bn = Σ (theoretical − reported)·deflator, per country."""
    d = _filtered(sample, scenario, formula)
    if d.empty or "theoretical_profit" not in d.columns or "reported_profit" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(_tb=(d["theoretical_profit"] - d["reported_profit"]) * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["_tb"].sum() / 1e3 / N_AVG_YEARS   # per-year average


def _reported_bn(sample, scenario, formula=HEADLINE_FORMULA):
    """Currently-reported profit base (Σ reported_profit·deflator), BASE_YEAR US$bn per country —
    the reference for computing the taxable-profit % change."""
    d = _filtered(sample, scenario, formula)
    if d.empty or "reported_profit" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(v=d["reported_profit"] * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["v"].sum() / 1e3 / N_AVG_YEARS   # per-year average


def _current_rev_bn(sample, formula=HEADLINE_FORMULA):
    """Corporate tax currently paid by the sample MNEs (current_tax_paid_cash),
    BASE_YEAR US$bn per country — THE revenue-% denominator (user 2026-07-13:
    every revenue comparison is vs taxes on MNE profits, never total government
    tax revenue — the old tax_revenue_current_usd basis was the latter)."""
    d = _filtered(sample, "excl_resource", formula)
    if d.empty or "current_tax_paid_cash_musd" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(v=pd.to_numeric(d["current_tax_paid_cash_musd"], errors="coerce")
                 * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["v"].sum() / 1e3 / N_AVG_YEARS   # per-year average


def _posbase_bn(sample, formula=HEADLINE_FORMULA):
    """Positive reported profit base (yearly clip at 0), BASE_YEAR US$bn per
    country — the taxable-profit % denominator (positive-base convention,
    matching the figures' % panels)."""
    d = _filtered(sample, "excl_resource", formula)
    if d.empty or "reported_profit" not in d.columns:
        return pd.Series(dtype=float)
    d = d.assign(v=pd.to_numeric(d["reported_profit"], errors="coerce").clip(lower=0)
                 * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["v"].sum() / 1e3 / N_AVG_YEARS   # per-year average


def _with_pct(df_final, base_col, value_cols):
    """Append '<col> (%)' columns = 100 × col ÷ base_col (n.m. where the base is
    non-positive). Applied AFTER _finalise so the group heading rows get the
    correct ratio of group sums (not a mean of country ratios)."""
    base = pd.to_numeric(df_final[base_col], errors="coerce")
    for c in value_cols:
        df_final[f"{c} (%)"] = np.where(
            base > 0, 100 * pd.to_numeric(df_final[c], errors="coerce") / base, np.nan)
    return df_final.round(2)


# Tables are grouped by the income-group / tax-haven classification used in the
# figures (the wb_income_group column), not by continent. Uppercase heading labels:
IG_HEADING = {
    "low_income": "LOW-INCOME",
    "lower_middle_income": "LOWER-MIDDLE-INCOME",
    "upper_middle_income": "UPPER-MIDDLE-INCOME",
    "high_income": "HIGH-INCOME",
    "investment_hub": "TAX HAVENS",   # relabelled from "INVESTMENT HUB / TAX HAVEN" (user 2026-07-13)
}


def _etr_cit(sample):
    """Current average ETR (excl_resource) and statutory CIT per country, from a
    country_estimates file (formula-invariant), as fractions."""
    base = os.path.join(_ROOT, "output", "unitary_taxation", sample,
                        "excl_resource", "tables", "excl_resource")
    fs = [f for f in glob.glob(os.path.join(base, f"country_estimates__{HEADLINE_FORMULA}__*.csv"))
          if "average" in f and "loss_cit_gain_etr" in f and "etrmax_inf" in f]
    if not fs:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    c = pd.read_csv(fs[0], low_memory=False)
    return (c.groupby("iso_partner")["etr_average_excl_resource"].mean(),
            c.groupby("iso_partner")["cit"].mean())


# WB income groups for ex-representation-havens (the data column still says
# "investment_hub" for them until the 1_clean rerun propagates the 2026-07-11
# list change). Only needed for the stale-column overlay below.
_DEHUBBED_IG = {
    "HUN": "high_income", "EST": "high_income",
    "LVA": "high_income", "CRI": "upper_middle_income",
    "LBN": "lower_middle_income", "LBR": "low_income",
}


def _income_group(sample):
    p = _summary_path(sample, "excl_resource")
    d = pd.read_csv(p, usecols=["iso_partner", "wb_income_group"], low_memory=False)
    g = d.drop_duplicates("iso_partner").set_index("iso_partner")["wb_income_group"]
    # Overlay the CURRENT config haven list — the data column is stale until the
    # 1_clean rerun; this is a no-op once the files carry the new classification.
    hub = config.TAX_HAVENS_REPRESENTATION
    stale = g.index[(g == "investment_hub") & ~g.index.isin(hub)]
    g.loc[stale] = [_DEHUBBED_IG.get(i, "high_income") for i in stale]
    g[g.index.isin(hub)] = "investment_hub"
    return g


def _region(sample):
    """iso -> region_tjn (geographic grouping), from the same summary file."""
    p = _summary_path(sample, "excl_resource")
    d = pd.read_csv(p, usecols=["iso_partner", "region_tjn"], low_memory=False)
    return d.drop_duplicates("iso_partner").set_index("iso_partner")["region_tjn"]


def _floor_royalty_bn():
    """Minimum-royalty add-on in constant BASE_YEAR US$bn (per-year deflated)."""
    p = os.path.join(_ROOT, "data", "final", "cbcr_main_excl_resource_floored.csv")
    d = pd.read_csv(p, usecols=["iso_partner", "year", "floor_add_on_cat1_usd"], low_memory=False)
    d = d[d["year"].isin(AVG_YEARS)]
    d = d.assign(_v=pd.to_numeric(d["floor_add_on_cat1_usd"], errors="coerce")
                 * d["year"].map(_DEFL))
    return d.groupby("iso_partner")["_v"].sum() / 1e9 / N_AVG_YEARS   # per-year average


def _consolidation_rev_bn(sample):
    p = os.path.join(_ROOT, "output", "unitary_taxation", "across_samples",
                     "loss_consolidation_sensitivity", "tables",
                     "loss_consolidation_country_long.csv")
    if not os.path.exists(p):
        return pd.Series(dtype=float)
    d = pd.read_csv(p, low_memory=False)
    d = d[(d.get("sample") == sample) & (d["scenario"] == "excl_resource")
          & (d["formula"] == HEADLINE_FORMULA) & (d["rate_mode"] == RATE)
          & (d["etr_threshold"].astype(str) == THRESHOLD)]
    if "year" in d.columns:
        d = d[d["year"].isin(AVG_YEARS)]
    # 9i already emits per-year averages, so do NOT divide again here.
    return d.groupby("iso_partner")["revenue_gain_loss_consolidated_musd"].sum() / 1e3


def _finalise(df, order_iso, grp, group_order=IG_ORDER, headings=IG_HEADING,
              other_label="OTHER / UNCLASSIFIED"):
    """Group countries by a classification (income-group / tax-haven class by
    default, or region_tjn when `grp`/`group_order`/`headings` are the region
    variants). Each group is led by an UPPERCASE heading row carrying the
    aggregate (sum for absolute/USD columns, mean for any % column), followed by
    its countries alphabetically. `grp` maps iso → the grouping value."""
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
        rows.append(agg)                       # group heading + aggregate, ABOVE the group
        for i in isos:
            rec = {"country": cname(i)}
            rec.update(df.loc[i].to_dict())
            rows.append(rec)
    out = pd.DataFrame(rows, columns=["country"] + list(df.columns))
    return out.round(2)


def _cap_first(s):
    """Capitalise the first alphabetic character of a header (leaves the rest, so
    'baseline — …' → 'Baseline — …', 'of which: royalty' → 'Of which: royalty',
    '+ min. royalty …' → '+ Min. royalty …', 'CCCTB' unchanged)."""
    s = str(s)
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
    return s


def _write(df, sample, name, tables_dir):
    df = df.rename(columns={c: _cap_first(c) for c in df.columns})
    csv = os.path.join(tables_dir, f"{name}__{sample}.csv")
    df.to_csv(csv, index=False)
    md = os.path.join(tables_dir, f"{name}__{sample}.md")
    with open(md, "w", encoding="utf-8") as fh:
        cols = list(df.columns)
        fh.write("| " + " | ".join(str(c) for c in cols) + " |\n")
        fh.write("| " + " | ".join("---" for _ in cols) + " |\n")
        for _, r in df.iterrows():
            cells = [f"{v:,.2f}" if isinstance(v, float) else ("" if pd.isna(v) else str(v))
                     for v in r]
            fh.write("| " + " | ".join(cells) + " |\n")
    print(f"  wrote {csv}  ({len(df)} countries)")


def _emit(df, order_iso, grp, grp_reg, sample, name, tables_dir,
          pct_base=None, pct_cols=None):
    """Write the income-group table (unchanged name) AND a `…_by_region`
    counterpart from the same raw dataframe."""
    def _fin(g, order, headings, other):
        out = _finalise(df, order_iso, g, order, headings, other)
        return _with_pct(out, pct_base, pct_cols) if pct_base else out
    _write(_fin(grp, IG_ORDER, IG_HEADING, "OTHER / UNCLASSIFIED"),
           sample, name, tables_dir)
    _write(_fin(grp_reg, REGION_ORDER, REGION_HEADING, "OTHER"),
           sample, name + "_by_region", tables_dir)


def build_for_sample(sample, royalty, tables_dir):
    # common country set (regrouped by income group / tax-haven class in _finalise)
    excl_rev = _rev_bn(sample, "excl_resource", HEADLINE_FORMULA)
    order_iso = pd.Index(sorted(excl_rev.index, key=lambda i: cname(i).lower()))
    grp = _income_group(sample).to_dict()
    grp_reg = _region(sample).to_dict()

    # Table 1 — scenarios × {Δ taxable profit, Δ tax revenue}. The minimum-royalty
    # revenue is split into the UT yield, the separate royalty revenue, and the
    # combined total; loss consolidation adjusts revenue only.
    ut_floored = _rev_bn(sample, "excl_resource_floored", HEADLINE_FORMULA)
    t1 = pd.DataFrame(index=order_iso)
    # Reference bases (constant BASE_YEAR $) so readers can compute any % change: taxable-profit change
    # ÷ reported profit base, and tax-revenue change ÷ current tax revenue.
    t1["reported profit base"] = _reported_bn(sample, "excl_resource")
    t1["current tax revenue from MNEs"] = _current_rev_bn(sample)
    t1["baseline — Δ taxable profit"] = _taxbase_bn(sample, "baseline", HEADLINE_FORMULA)
    t1["baseline — Δ tax revenue"] = _rev_bn(sample, "baseline", HEADLINE_FORMULA)
    t1["excl. resource — Δ taxable profit"] = _taxbase_bn(sample, "excl_resource", HEADLINE_FORMULA)
    t1["excl. resource — Δ tax revenue"] = _rev_bn(sample, "excl_resource", HEADLINE_FORMULA)
    t1["+ min. royalty — Δ tax revenue (total)"] = ut_floored.add(royalty, fill_value=0.0)
    t1["of which: royalty"] = royalty
    t1["loss consolidation — Δ tax revenue"] = _consolidation_rev_bn(sample)
    _emit(t1, order_iso, grp, grp_reg, sample, "table1_scenarios", tables_dir)

    # Table 2a / 2b — by formula, resources excluded. Each carries its % base
    # column (positive profit base / current MNE tax) plus per-formula % columns
    # (user 2026-07-13: tables need the % changes too).
    posbase = _posbase_bn(sample)
    cashtax = _current_rev_bn(sample)
    tb = pd.DataFrame(index=order_iso)
    rev = pd.DataFrame(index=order_iso)
    tb["current profit base"] = posbase
    rev["current tax revenue from MNEs"] = cashtax
    for fk, flab in FORMULAS:
        tb[flab] = _taxbase_bn(sample, "excl_resource", fk)
        rev[flab] = _rev_bn(sample, "excl_resource", fk)
    _flabs = [flab for _, flab in FORMULAS]
    _emit(tb, order_iso, grp, grp_reg, sample, "table2a_taxbase_by_formula",
          tables_dir, pct_base="current profit base", pct_cols=_flabs)
    _emit(rev, order_iso, grp, grp_reg, sample, "table2b_revenue_by_formula",
          tables_dir, pct_base="current tax revenue from MNEs", pct_cols=_flabs)

    # Table 3 — sales-measure comparison (employees + sales), taxbase & revenue, excl_resource
    tb3 = pd.DataFrame(index=order_iso)
    rev3 = pd.DataFrame(index=order_iso)
    tb3["current profit base"] = posbase
    rev3["current tax revenue from MNEs"] = cashtax
    for fk, flab in SALES_SPECS:
        tb3[flab] = _taxbase_bn(sample, "excl_resource", fk)
        rev3[flab] = _rev_bn(sample, "excl_resource", fk)
    _slabs = [flab for _, flab in SALES_SPECS]
    _emit(tb3, order_iso, grp, grp_reg, sample, "table3a_taxbase_by_sales",
          tables_dir, pct_base="current profit base", pct_cols=_slabs)
    _emit(rev3, order_iso, grp, grp_reg, sample, "table3b_revenue_by_sales",
          tables_dir, pct_base="current tax revenue from MNEs", pct_cols=_slabs)

    # Table 5 — break-even ETR for the INVESTMENT-HUB / haven losers: the effective rate
    # such a jurisdiction would need to keep its current MNE-tax revenue on its smaller UT
    # taxable-profit base.  required_ETR = current_ETR × reported / theoretical(formula)
    # (n.m. where the UT base is non-positive). Restricted to investment-hub losers — the
    # rate-raising strategy applies to profit-shifting hubs, not to home-bias non-haven
    # losers (Japan/China/Canada), whose lost profit relocates to genuine foreign activity
    # and for which only the domestic ETR (≈ statutory CIT) would be relevant.
    # REPORTED sample only: break-even rates only make sense against actually
    # reported tax (gravity's imputed rows carry no tax), and the paper embeds no
    # gravity variant of this table.
    if sample == "reported_only":
        etr, cit = _etr_cit(sample)
        rep_excl = _reported_bn(sample, "excl_resource")
        d_head = _taxbase_bn(sample, "excl_resource", HEADLINE_FORMULA)
        losers = pd.Index([i for i in order_iso
                           if pd.notna(d_head.get(i)) and d_head.get(i, 0) < 0
                           and grp.get(i) == "investment_hub"])
        t5 = pd.DataFrame(index=losers)
        t5["current ETR (%)"] = etr.reindex(losers) * 100
        t5["statutory CIT (%)"] = cit.reindex(losers) * 100
        for fk, flab in FORMULAS:
            theo = rep_excl.add(_taxbase_bn(sample, "excl_resource", fk), fill_value=0.0)
            req = etr.reindex(losers) * rep_excl.reindex(losers) / theo.reindex(losers) * 100
            t5[f"break-even ETR — {flab} (%)"] = req.where(theo.reindex(losers) > 0)
        _write(_finalise(t5, losers, grp), sample, "table5_breakeven_etr", tables_dir)

    # verification: income-group sums of excl-resource revenue
    ig = _income_group(sample)
    chk = excl_rev.groupby(excl_rev.index.map(ig)).sum().reindex(IG_ORDER)
    print(f"  [{sample}] excl-resource Δrevenue by income group ($bn): "
          + ", ".join(f"{k[:3]}={v:,.0f}" for k, v in chk.items()))


def main():
    tables_dir, _ = config.output_dirs("deliverables/paper_tables")
    royalty = _floor_royalty_bn()
    for sample in SAMPLES:
        if not os.path.exists(_summary_path(sample, "excl_resource")):
            print(f"== {sample} == [skip] no summary tables yet "
                  f"(rerun the {sample} passes, then this script)")
            continue
        print(f"== {sample} ==")
        build_for_sample(sample, royalty, tables_dir)
    print(f"\nAll paper tables written to {tables_dir}")


if __name__ == "__main__":
    main()
