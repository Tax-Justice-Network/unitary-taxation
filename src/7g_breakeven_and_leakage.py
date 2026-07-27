# %%
"""
7g — Break-even effective tax rates and haven leakage.

Part A — Break-even ETRs. For the countries that lose taxable profit under
unitary taxation, computes the effective tax rate each would need to keep its
current multinational-tax revenue on its smaller unitary-taxation base. Two
groups: the tax-haven losers (the rate-raising strategy that applies to
profit-shifting hubs) and the headquarter-bias losers (Japan, Saudi Arabia,
Denmark, …), whose own multinationals book far more profit at home than their
domestic activity warrants — here the relevant lever is the domestic rate. All
four formula families are shown, on the headline destination measure.

Part B — Haven leakage. For each $1 of tax a haven collects on profit shifted
into it, how many dollars of tax revenue does the rest of the world lose? The
numerator is the world revenue loss havens cause and the denominator is the
revenue havens collect on shifted-in profit, both taken straight from the
per-country estimates. Computed only for the part havens are really responsible
for — not the headquarter-bias over-booking of high-tax countries, which a naive
hub multiplier would wrongly include. Havens are identified by the representation
list. Reported as a headline ratio (~3) with an optimistic–conservative band
across the rate-assumption specs (both-legs-ETR, gains-at-CIT, and
bottom-10%-ETR losses); the optimistic spec credits havens with collecting
almost nothing on the shifted-in profit, lifting the ratio sharply (to ~17).

Headline specification: reported-only sample, resources excluded, employees + destination-based sales (sales_employees_destmnedds), domestic/foreign ETR, gains at statutory CIT and losses at ETR, per-year average over 2016–2022 (2020 excluded), constant 2025 US$.

Exhibit script — consumes the script-6 estimation summaries. Produces Table 5
(break-even ETRs: haven losers + headquarter-bias domestic losers) + the
haven-leakage ratio quoted in the main text (a single figure, not a numbered exhibit).

Reads:
  output/estimates/reported_only/*/tables/summary_country_year_long.csv   — per-country loser estimates (script 6)
  output/estimates/reported_only/*/tables/…/misalignment__*.csv           — per-spec detail for the leakage ratio

Writes:
  output/paper/main_text/table5_breakeven_etrs.csv/.tex                    — Table 5, haven losers
  output/paper/main_text/table5_breakeven_domestic.csv/.tex               — Table 5, headquarter-bias domestic losers
  output/analysis/haven_leakage/…                                          — haven-leakage ratio (world $ lost per $1 a haven collects)

Usage:
  python 7g_breakeven_and_leakage.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import glob
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC)
sys.path.insert(0, _SRC)
import config  # noqa: E402
from config import output_dirs, estimates_dir  # noqa: E402
import _exhibit_helpers as _eh  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    import pycountry
    _NAME_OVR = getattr(config, "COUNTRY_NAME_OVERRIDES", {})
    def cname(i):
        if str(i) in _NAME_OVR:
            return _NAME_OVR[str(i)]
        c = pycountry.countries.get(alpha_3=str(i))
        return c.name if c else str(i)
except Exception:
    def cname(i):
        return str(i)


# %% MARK: 2. Part A config and helpers
# ── Part A: break-even ETRs ──────────────────────────────────────────────────
DEFL = config.deflator_to_base()
AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]   # 2020 excluded (COVID outlier)
HEADLINE = "sales_employees_destmnedds"
# All formulas on the headline destination measure (all-MNE sales + MNE share
# of BaTIS deliverable imports) so the two break-even tables are like-for-like.
FORMULAS = [
    ("sales_employees_destmnedds", "sales & employees"),
    ("ccctb_destmnedds", "CCCTB"),
    ("three_factors_destmnedds", "three-factor"),
    ("double_weighted_sales_destmnedds", "double-weighted sales"),
]
_MDIR = os.path.join(str(config.estimates_dir("reported_only", "excl_resource")),
                     "tables", "excl_resource")


def _mfile(fk):
    # exact-family match ("<fk>__") so e.g. sales_employees_destcfb does not
    # also match destcfbdig25/50/75 or destcfb_nexus variants
    fs = [f for f in glob.glob(os.path.join(_MDIR, "misalignment__*.csv"))
          if f"{fk}__" in os.path.basename(f) and "etrdef_domfor" in f
          and "loss_cit_gain_etr" in f and "etrmax_inf" in f]
    return fs[0] if fs else None


def _domestic(df, iso):
    d = df[(df["iso_parent"] == iso) & (df["iso_partner"] == iso)].copy()
    d["f"] = d["year"].map(DEFL)
    return d


# %% MARK: 3. Break-even domestic table
def main_breakeven_domestic():
    """Table 6 companion: headquarter-bias domestic-ETR break-even."""
    tables_dir, _ = config.output_dirs("deliverables/paper_tables")

    # net REVENUE loss (headline spec: excl_resource / sales_employees_destmnedds /
    # domfor ETR / etrmax_inf / ETR-CIT, excl 2020) to pick the headquarter-bias set.
    # Revenue, not tax base: a base loser whose recoveries at CIT outweigh its
    # give-ups at ETR (e.g. China) is a net revenue WINNER and does not belong
    # in a table about keeping revenue on a smaller base.
    ce_fp = [f for f in glob.glob(os.path.join(_MDIR, "country_estimates__*.csv"))
             if f"{HEADLINE}__" in os.path.basename(f) and "etrdef_domfor" in f
             and "loss_cit_gain_etr" in f and "etrmax_inf" in f][0]
    ce = pd.read_csv(ce_fp, low_memory=False)
    ce = ce[ce.year.isin(AVG_YEARS)]   # 2020 excluded (COVID)
    # Deflate to constant BASE_YEAR USD before summing — same convention as Table 4
    # and every other deliverable. Nominal sums put knife-edge cases (e.g. Norway,
    # positive early years and negative late years) on the wrong side of zero.
    net = (ce.assign(_v=ce["revenue_gain_from_ut"] * ce["year"].map(DEFL))
             .groupby("iso_partner")["_v"].sum() / 1e3)   # $bn, constant BASE_YEAR (sign is what matters)
    cit = ce.groupby("iso_partner")["cit"].mean()

    # domestic ETR + domestic reported profit from cbcr_main_excl_resource
    c = pd.read_csv(os.path.join(_ROOT, "data", "final", "cbcr_main_excl_resource.csv"),
                    low_memory=False)
    if "is_distributed" in c.columns:
        c = c[c["is_distributed"] == 0]
    dom = c[c.iso_parent == c.iso_partner].copy()
    dom = dom[dom["year"].isin(AVG_YEARS)]   # 2020 excluded
    dom["f"] = dom["year"].map(DEFL)
    dom_prof = (pd.to_numeric(dom.profit_loss_excl_resource, errors="coerce") * dom.f)
    dom_tax = (pd.to_numeric(dom.income_tax_paid_on_cash_basis_excl_resource, errors="coerce") * dom.f)
    dp = dom.assign(p=dom_prof, t=dom_tax).groupby("iso_parent").agg(p=("p", "sum"), t=("t", "sum"))
    detr = (dp["t"] / dp["p"]).rename("dom_etr")
    drep = (dp["p"] / 1e9).rename("dom_reported_bn")   # $bn

    # headquarter-bias set: non-haven net REVENUE losers with domestic profit > $50bn. Haven
    # membership comes from the CURRENT config list (not the possibly-stale
    # wb_income_group column). Saudi Arabia is deliberately classified headquarter-bias
    # (not a haven — its excess profit is ~98% home-booked), so it belongs HERE,
    # not in the hub table. NB the revenue criterion excludes China and Chile (base
    # losers but small net revenue winners under ETR-CIT).
    hb = [i for i in net.index if net[i] < 0
          and i not in config.TAX_HAVENS_REPRESENTATION
          and drep.get(i, 0) > 50]
    hb = sorted(hb, key=lambda i: net[i])   # most negative first

    # whole-base break-even per formula: the rate on ALL profit UT leaves in the
    # country (own MNEs' domestic base + foreign MNEs' allocated base) that keeps
    # ALL current MNE tax revenue — the policy-relevant rate, since a statutory
    # rate cannot be ring-fenced to the domestic cell. = sum(current tax) / sum(theoretical).
    whole_be, whole_cur = {}, None
    for fk, _ in FORMULAS:
        fp = [f for f in glob.glob(os.path.join(_MDIR, "country_estimates__*.csv"))
              if f"{fk}__" in os.path.basename(f) and "etrdef_domfor" in f
              and "loss_cit_gain_etr" in f and "etrmax_inf" in f][0]
        c2 = pd.read_csv(fp, low_memory=False)
        c2 = c2[c2.year.isin(AVG_YEARS)]
        g2 = c2.groupby("iso_partner").agg(tax=("current_tax_paid_cash_musd", "sum"),
                                           rep=("reported_profit", "sum"),
                                           theo=("theoretical_profit", "sum"))
        whole_be[fk] = g2.tax / g2.theo
        if whole_cur is None:
            whole_cur = g2.tax / g2.rep   # current effective rate on all MNE profit

    # domestic theoretical per formula (from misalignment files)
    dom_theo = {}
    for fk, _ in FORMULAS:
        d = pd.read_csv(_mfile(fk), low_memory=False)
        dd = d[d.iso_parent == d.iso_partner].copy()
        dd["f"] = dd["year"].map(DEFL)
        g = (pd.to_numeric(dd.theoretical_profit, errors="coerce") * dd.f).groupby(dd.iso_parent).sum() / 1e9
        dom_theo[fk] = g   # $bn (misalignment theoretical_profit is in USD)

    # Table shows ONLY the whole-base break-even rates (the rate on the ENTIRE
    # base UT allocates to the country, not the illustrative
    # domestic-cell-only rate, which cannot be ring-fenced in practice). The
    # domestic ETR appears as a descriptive column (it explains WHY the country
    # loses); no domestic-only break-even block is shown.
    rows = []
    for iso in hb:
        rec = {"country": cname(iso),
               "domestic ETR (%)": round(100 * detr.get(iso, float("nan")), 1),
               "current effective rate, all MNE profit (%)": round(
                   100 * whole_cur.get(iso, float("nan")), 1),
               "statutory CIT (%)": round(100 * cit.get(iso, float("nan")), 1)}
        for fk, flab in FORMULAS:
            rec[f"break-even rate — {flab} (%)"] = round(
                100 * whole_be[fk].get(iso, float("nan")), 1)
        rows.append(rec)
    out = pd.DataFrame(rows)

    def _cap_first(s):
        s = str(s)
        for i, ch in enumerate(s):
            if ch.isalpha():
                return s[:i] + ch.upper() + s[i + 1:]
        return s
    out = out.rename(columns={c: _cap_first(c) for c in out.columns})

    csv = os.path.join(tables_dir, "table5_breakeven_domestic__reported_only.csv")
    out.to_csv(csv, index=False)
    md = csv[:-4] + ".md"
    with open(md, "w", encoding="utf-8") as fh:
        cols = list(out.columns)
        fh.write("| " + " | ".join(cols) + " |\n| " + " | ".join("---" for _ in cols) + " |\n")
        for _, r in out.iterrows():
            fh.write("| " + " | ".join(str(v) for v in r) + " |\n")
    print(out.to_string(index=False))
    print(f"\nwrote {csv}")


# %% MARK: 4. paper exhibit — break-even ETR for tax-haven losers (table)
# The companion table: the effective rate a
# tax-haven loser would need to keep its current MNE-tax revenue on its
# smaller UT taxable-profit base. required_ETR = current_ETR x reported /
# theoretical(formula) (not meaningful where the UT base is non-positive).
# Restricted to tax-haven losers: the rate-raising strategy applies to
# profit-shifting hubs, not to headquarter-bias non-haven losers (their lost
# profit relocates to genuine foreign activity — see the domestic table
# above). Reported sample only: break-even rates only make sense against
# actually reported tax.
def build_table_breakeven_hubs():
    sample = "reported_only"
    if not _eh.summary_exists(sample):
        print("  [skip hub break-even] no reported summaries yet")
        return
    tables_dir = _eh.tabledir(sample)
    excl_rev = _eh.rev_musd(sample, "excl_resource", _eh.HEADLINE_FORMULA)
    order_iso = pd.Index(sorted(excl_rev.index, key=lambda i: _eh.cname(i).lower()))
    grp = _eh.income_group(sample).to_dict()
    etr, cit = _eh.etr_cit(sample)
    rep_excl = _eh.reported_musd(sample, "excl_resource")
    d_head = _eh.taxbase_musd(sample, "excl_resource", _eh.HEADLINE_FORMULA)
    losers = pd.Index([i for i in order_iso
                       if pd.notna(d_head.get(i)) and d_head.get(i, 0) < 0
                       and grp.get(i) == "tax_haven"])
    t5 = pd.DataFrame(index=losers)
    t5["current ETR (%)"] = etr.reindex(losers) * 100
    t5["statutory CIT (%)"] = cit.reindex(losers) * 100
    for fk, flab in _eh.PAPER_4FORMULAS:
        lab = flab.lower() if flab != "CCCTB" else flab
        theo = rep_excl.add(_eh.taxbase_musd(sample, "excl_resource", fk),
                            fill_value=0.0)
        req = (etr.reindex(losers) * rep_excl.reindex(losers)
               / theo.reindex(losers) * 100)
        t5[f"break-even ETR — {lab} (%)"] = req.where(theo.reindex(losers) > 0)
    fin = _eh.finalise(t5, losers, grp)
    # Break-even rates cannot be averaged across countries — blank them in the
    # TAX HAVENS aggregate heading row (finalise means %-named columns).
    be_cols = [c for c in fin.columns if c.startswith("break-even ETR")]
    fin = _eh.blank_group_headings(fin, be_cols)
    _eh.write_table(fin, sample, "table5_breakeven_etrs", tables_dir)


# %% MARK: 5. Part B: haven leakage
# ── Part B: haven-leakage ratio ──────────────────────────────────────────────
SAMPLE = "reported_only"           # no imputed rows
FORMULA = "sales_employees_destmnedds"  # headline destination formula (MNE sales + MNE-share DDS)
ETRMAX = "inf"                      # full reapportionment, no 15% haven gate
EXCLUDE_YEARS = {2020}             # COVID-distorted low-coverage year
HAVEN_GROUP = "tax_haven"     # == TAX_HAVENS_REPRESENTATION classification

# Datasets (name -> the /tables/<sub>/ folder script 5 writes into for this sample).
DATASETS = {
    "baseline": "disaggregated",            # resources ignored
    "excl_resource": "excl_resource",        # HEADLINE
    "excl_resource_floored": "excl_resource_floored",
}

# Optimistic–conservative band, mirroring Figure 1's rate-assumption range. The
# ratio's inputs (world loss havens cause / revenue havens collect) genuinely
# vary across these specs — unlike the break-even ETRs, which are rate-mode
# invariant. Each tier is (etr definition, rate mode, label):
#   conservative  both legs valued at the effective tax rate;
#   headline      gains at statutory CIT, losses at ETR;
#   optimistic    losses valued at the bottom-10% pair ETR — havens are credited
#                 with collecting almost nothing on the profit shifted into them,
#                 so the ratio (loss per $ collected) is at its highest.
RATE_SPECS = {
    "conservative": ("domfor", "loss_etr_gain_etr", "conservative (both legs @ ETR)"),
    "headline": ("domfor", "loss_cit_gain_etr", "headline (gains @ CIT, losses @ ETR)"),
    "optimistic": ("average", "losers_p10_gainers_avgetr", "optimistic (losses @ bottom-10% ETR)"),
}
_TIER_ORDER = ["conservative", "headline", "optimistic"]
LEAK_HEADLINE_DATASET = "excl_resource"


def _country_estimates_path(dataset, etrdef, rate):
    sub = DATASETS[dataset]
    pat = (f"{estimates_dir(SAMPLE, dataset)}/tables/{sub}/"
           f"country_estimates__{FORMULA}__etrdef_{etrdef}__etrmax_{ETRMAX}__{rate}.csv")
    hits = glob.glob(pat)
    return hits[0] if hits else None


def _load(dataset, etrdef, rate):
    fp = _country_estimates_path(dataset, etrdef, rate)
    if fp is None:
        print(f"  [missing] {dataset} / {etrdef} / {rate}")
        return None
    d = pd.read_csv(fp)
    d = d[~d["year"].isin(EXCLUDE_YEARS)].copy()
    # Deflate the monetary columns to constant BASE_YEAR USD so the leakage ratio
    # and its absolute $bn columns match the rest of the paper's 2025-USD figures.
    w = d["year"].map(DEFL).fillna(1.0)
    for c in ("tax_revenue_loss_caused_musd", "tax_revenue_gain",
              "revenue_gain_from_ut"):
        d[c] = pd.to_numeric(d[c], errors="coerce") * w
    return d


def _ratio_row(dataset, tier):
    etrdef, rate, label = RATE_SPECS[tier]
    d = _load(dataset, etrdef, rate)
    if d is None:
        return None
    hav = d[d["wb_income_group"] == HAVEN_GROUP]
    loss_caused = hav["tax_revenue_loss_caused_musd"].sum()   # numerator (musd)
    collected = hav["tax_revenue_gain"].sum()                 # denominator (musd)
    net_ut_loss = -hav["revenue_gain_from_ut"].sum()          # havens' net UT loss (musd)
    total_loss_caused = d["tax_revenue_loss_caused_musd"].sum()
    return {
        "dataset": dataset,
        "tier": tier,
        "rate_spec_label": label,
        "etrdef": etrdef,
        "rate_mode": rate,
        "world_loss_havens_cause_bn": loss_caused / 1e3,
        "revenue_havens_collect_bn": collected / 1e3,
        "ratio_loss_per_dollar_collected": (loss_caused / collected
                                            if collected else np.nan),
        "havens_net_ut_loss_bn": net_ut_loss / 1e3,
        "ratio_vs_net_ut_loss": (loss_caused / net_ut_loss
                                 if net_ut_loss else np.nan),
        "haven_share_of_total_loss_caused_pct": (100 * loss_caused / total_loss_caused
                                                 if total_loss_caused else np.nan),
        "is_headline": (dataset == LEAK_HEADLINE_DATASET and tier == "headline"),
    }


def _by_haven(dataset, tier):
    """Per-haven breakdown for one spec: what each haven causes vs collects."""
    etrdef, rate, _ = RATE_SPECS[tier]
    d = _load(dataset, etrdef, rate)
    if d is None:
        return None
    hav = d[d["wb_income_group"] == HAVEN_GROUP]
    g = hav.groupby("iso_partner", as_index=False).agg(
        partner_jurisdiction=("partner_jurisdiction", "first"),
        world_loss_caused_bn=("tax_revenue_loss_caused_musd", lambda x: x.sum() / 1e3),
        revenue_collected_bn=("tax_revenue_gain", lambda x: x.sum() / 1e3),
    )
    g["ratio_loss_per_dollar_collected"] = np.where(
        g["revenue_collected_bn"] > 0,
        g["world_loss_caused_bn"] / g["revenue_collected_bn"],
        np.nan,
    )
    return g.sort_values("world_loss_caused_bn", ascending=False).reset_index(drop=True)


def main_leakage():
    tables_dir, _ = output_dirs("deliverables/haven_leakage")

    # Full grid: datasets x rate-assumption tiers.
    rows = [r for ds in DATASETS for tier in _TIER_ORDER
            if (r := _ratio_row(ds, tier)) is not None]
    summary = pd.DataFrame(rows)
    summary_fp = tables_dir / "haven_leakage_ratio_summary.csv"
    summary.to_csv(summary_fp, index=False)

    # Per-haven breakdown on the headline spec.
    by_haven = _by_haven(LEAK_HEADLINE_DATASET, "headline")
    by_haven_fp = tables_dir / "haven_leakage_ratio_by_haven.csv"
    if by_haven is not None:
        by_haven.to_csv(by_haven_fp, index=False)

    # ── Report: headline + optimistic-conservative band on the headline dataset ─
    hd = summary[summary["dataset"] == LEAK_HEADLINE_DATASET]
    hl = hd[hd["tier"] == "headline"].iloc[0]
    band = hd.set_index("tier")["ratio_loss_per_dollar_collected"]
    lo, hi = band.min(), band.max()
    print("=" * 78)
    print("HAVEN LEAKAGE RATIO — world revenue loss havens CAUSE per $1 they COLLECT")
    print("=" * 78)
    print(f"Dataset: {SAMPLE} / {LEAK_HEADLINE_DATASET} / {FORMULA} / etrmax_{ETRMAX}")
    print(f"Window: 2016-2022 excl {sorted(EXCLUDE_YEARS)}; havens = {HAVEN_GROUP} list\n")
    print(f"  >>> HEADLINE RATIO = {hl.ratio_loss_per_dollar_collected:.2f}  "
          f"(each $1 a haven collects → the world loses "
          f"~${hl.ratio_loss_per_dollar_collected:.1f})")
    print(f"  >>> RANGE across rate assumptions = {lo:.1f} to {hi:.1f}\n")
    for tier in _TIER_ORDER:
        r = hd[hd["tier"] == tier].iloc[0]
        print(f"    {RATE_SPECS[tier][2]:38s}: ratio {r.ratio_loss_per_dollar_collected:5.2f}  "
              f"(loss ${r.world_loss_havens_cause_bn:,.0f}bn / collect "
              f"${r.revenue_havens_collect_bn:,.0f}bn)")
    print(f"\n  havens cause {hl.haven_share_of_total_loss_caused_pct:.0f}% of ALL "
          f"UT-reallocated loss (rest = headquarter-bias over-booking)\n")

    print("Dataset sensitivity (headline tier, ratio = loss caused / revenue collected):")
    show = summary[summary["tier"] == "headline"][
        ["dataset", "ratio_loss_per_dollar_collected",
         "world_loss_havens_cause_bn", "revenue_havens_collect_bn"]]
    print(show.to_string(index=False,
          formatters={"ratio_loss_per_dollar_collected": "{:.2f}".format,
                      "world_loss_havens_cause_bn": "{:,.0f}".format,
                      "revenue_havens_collect_bn": "{:,.0f}".format}))

    if by_haven is not None:
        print(f"\nTop havens by world loss caused (headline spec):")
        print(by_haven.head(12).to_string(index=False,
              formatters={"world_loss_caused_bn": "{:,.0f}".format,
                          "revenue_collected_bn": "{:,.0f}".format,
                          "ratio_loss_per_dollar_collected": "{:.1f}".format}))

    print(f"\nwrote {summary_fp}")
    print(f"wrote {by_haven_fp}")


# %% MARK: 6. Orchestration and run
def main():
    # Part A — break-even ETR tables (headquarter-bias domestic + tax-haven hubs)
    main_breakeven_domestic()
    build_table_breakeven_hubs()
    # Part B — haven-leakage ratio
    main_leakage()


if __name__ == "__main__":
    main()
