"""
9o — Break-even DOMESTIC ETR for the home-bias losers.

Companion to Table 5 (break-even ETR for investment-hub losers). Home-bias non-haven
losers (Japan, China, Canada, …) lose taxable profit because their own multinationals
book far more profit at home than their domestic activity would warrant; under unitary
taxation that profit relocates to the firms' genuine foreign activity. Here we ask: what
DOMESTIC effective tax rate would such a country need to keep its current domestic
MNE-tax revenue on its (smaller) UT-allocated domestic base?

    break-even domestic ETR = domestic_ETR × domestic_reported / domestic_theoretical(formula)

  domestic_ETR   = tax on domestically-booked profit ÷ that profit (cbcr_main_excl_resource,
                   domestic cell iso_parent==iso_partner, reported rows)
  domestic_reported / domestic_theoretical = the domestic cell's reported profit and its
                   UT allocation, from the per-formula misalignment files.

Home-bias set = non-investment-hub net REVENUE losers on the headline spec
(excl_resource / sales_employees_destcfb / average ETR / ETR-CIT, 2016-2022 excl
2020) with domestic reported profit above $50 bn. Break-even columns show the
four formula families, all on CFB destination sales (matching Table 5), in TWO
blocks: (a) the DOMESTIC-cell break-even (illustrates how concentrated the
home-bias excess is — no real statutory rate can be ring-fenced to that cell)
and (b) the WHOLE-BASE break-even = sum(current MNE tax) / sum(theoretical UT
base over ALL MNEs in the country) — the policy-relevant rate, lower because
foreign MNEs' under-booked bases grow under UT.
All values constant BASE_YEAR USD, reported sample.
Output: table6_breakeven_domestic_etr__reported_only.csv (+ .md)
Usage: python 9o_breakeven_domestic.py
"""
import os
import sys
import glob
import pandas as pd

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SRC)
sys.path.insert(0, _SRC)
import config  # noqa: E402

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

DEFL = config.deflator_to_base()
AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]   # 2020 excluded (COVID outlier)
HEADLINE = "sales_employees_destmnedds"
# All formulas on the headline destination measure (all-MNE sales + MNE share
# of BaTIS deliverable imports) — matching Table 5 (9j), so the two break-even
# tables are like-for-like.
FORMULAS = [
    ("sales_employees_destmnedds", "sales & employees"),
    ("ccctb_destmnedds", "CCCTB"),
    ("three_factors_destmnedds", "three-factor"),
    ("double_weighted_sales_destmnedds", "double-weighted sales"),
]
_MDIR = os.path.join(_ROOT, "output", "unitary_taxation", "reported_only",
                     "excl_resource", "tables", "excl_resource")


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


def main():
    tables_dir, _ = config.output_dirs("deliverables/paper_tables")

    # net REVENUE loss (headline spec: excl_resource / sales_employees_destcfb /
    # average ETR / etrmax_inf / ETR-CIT, excl 2020) to pick the home-bias set.
    # Revenue, not tax base: a base loser whose recoveries at CIT outweigh its
    # give-ups at ETR (e.g. China) is a net revenue WINNER and does not belong
    # in a table about keeping revenue on a smaller base.
    ce_fp = [f for f in glob.glob(os.path.join(_MDIR, "country_estimates__*.csv"))
             if f"{HEADLINE}__" in os.path.basename(f) and "etrdef_domfor" in f
             and "loss_cit_gain_etr" in f and "etrmax_inf" in f][0]
    ce = pd.read_csv(ce_fp, low_memory=False)
    ce = ce[ce.year.isin(AVG_YEARS)]   # 2020 excluded (COVID)
    net = ce.groupby("iso_partner")["revenue_gain_from_ut"].sum() / 1e3   # $bn (sign is what matters)
    cit = ce.groupby("iso_partner")["cit"].mean()

    # domestic ETR + domestic reported profit from cbcr_main_excl_resource
    c = pd.read_csv(os.path.join(_ROOT, "data", "final", "cbcr_main_excl_resource.csv"),
                    low_memory=False)
    if "is_distributed" in c.columns:
        c = c[c["is_distributed"] == 0]
    dom = _domestic(c, None) if False else c[c.iso_parent == c.iso_partner].copy()
    dom = dom[dom["year"].isin(AVG_YEARS)]   # 2020 excluded
    dom["f"] = dom["year"].map(DEFL)
    dom_prof = (pd.to_numeric(dom.profit_loss_excl_resource, errors="coerce") * dom.f)
    dom_tax = (pd.to_numeric(dom.income_tax_paid_on_cash_basis_excl_resource, errors="coerce") * dom.f)
    dp = dom.assign(p=dom_prof, t=dom_tax).groupby("iso_parent").agg(p=("p", "sum"), t=("t", "sum"))
    detr = (dp["t"] / dp["p"]).rename("dom_etr")
    drep = (dp["p"] / 1e9).rename("dom_reported_bn")   # $bn

    # home-bias set: non-hub net REVENUE losers with domestic profit > $50bn. Hub
    # membership comes from the CURRENT config list (not the possibly-stale
    # wb_income_group column). Saudi Arabia is deliberately classified home-bias
    # (not a haven — its excess profit is ~98% home-booked), so it belongs HERE,
    # not in Table 5. NB the revenue criterion drops China and Chile (base losers
    # but small net revenue winners under ETR-CIT), which earlier base-selected
    # versions of this table included.
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

    # Table shows ONLY the whole-base break-even rates (user 2026-07-13: the
    # rate on the ENTIRE base UT allocates to the country, not the illustrative
    # domestic-cell-only rate, which cannot be ring-fenced in practice). The
    # domestic ETR is kept as a descriptive column (it explains WHY the country
    # loses); the domestic-only break-even block was dropped.
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

    csv = os.path.join(tables_dir, "table6_breakeven_domestic_etr__reported_only.csv")
    out.to_csv(csv, index=False)
    md = csv[:-4] + ".md"
    with open(md, "w", encoding="utf-8") as fh:
        cols = list(out.columns)
        fh.write("| " + " | ".join(cols) + " |\n| " + " | ".join("---" for _ in cols) + " |\n")
        for _, r in out.iterrows():
            fh.write("| " + " | ".join(str(v) for v in r) + " |\n")
    print(out.to_string(index=False))
    print(f"\nwrote {csv}")


if __name__ == "__main__":
    main()
