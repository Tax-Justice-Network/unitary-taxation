"""
9t — Putting the UT revenue gains in perspective: IMF debt and the Marshall Plan.

Two context comparisons for the headline unitary-taxation estimates (framed as
revenue GAINS from UT reform, not losses):

1. Global South vs outstanding IMF credit — for every World Bank IDS debtor
   country: how many years of its annual UT revenue gain would clear its
   outstanding IMF credit ("years to repay")? Debt source: WB indicator
   DT.DOD.DIMF.CD ("Use of IMF credit, DOD, current US$") — the same stock the
   IMF's "Total IMF Credit Outstanding" page shows, but scriptable. Cached in
   data/raw/imf_credit_outstanding_wb.csv (auto-refetched if deleted).

2. Marshall Plan recipients — the 16 recipient economies' cumulative UT gain
   over the six headline years vs their inflation-adjusted Marshall Plan aid.
   HEADLINE = the AGGREGATE across all recipients (haven-side losses net out
   inside the group): the group gains a full inflation-adjusted Marshall Plan
   (~$178bn) roughly every 2.6 years. Per-recipient ratios are detail.
   Aid source: CRS Report R45079 (2018), Table 2 (USAID 1971), hand-curated in
   data/raw/marshall_plan_aid.csv; grants-only carried as comparison. Aid is
   converted to 2025 USD with the US CPI-U (1950 mid-period anchor,
   data/raw/us_cpi_annual.csv) — the pipeline's own GDP deflator starts 2016.

Headline spec: reported-only sample, excl_resource dataset,
sales_employees_destmnedds formula, domfor ETR, ETR-CIT rate mode, years
2016-2022 excluding 2020; per-year average = deflated sum / 6, constant
BASE_YEAR (2025) USD. See docs/imf_marshall_comparison_sources.md.

Output: output/unitary_taxation/reported_only/context_comparisons/{tables,figures}/
Usage:  python 9t_ut_gains_vs_imf_debt_marshall.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_SRC = os.path.dirname(os.path.abspath(__file__))
_ROOT = Path(os.path.dirname(_SRC))
sys.path.insert(0, _SRC)
import config  # noqa: E402
from _brand import apply_tjn_style, PALETTE, POSITIVE, NEGATIVE  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
apply_tjn_style()

YEARS = [2016, 2017, 2018, 2019, 2021, 2022]   # 2020 excluded (headline window)
N_YEARS = len(YEARS)
DEFL = config.deflator_to_base()               # year -> factor to constant 2025 USD
HEADLINE, ETR, RATE, THRESH = "sales_employees_destmnedds", "domfor", "loss_cit_gain_etr", "inf"

IMF_CACHE = _ROOT / "data" / "raw" / "imf_credit_outstanding_wb.csv"
IMF_API = ("https://api.worldbank.org/v2/country/all/indicator/DT.DOD.DIMF.CD"
           "?format=json&per_page=20000&date=2019:2025")
MARSHALL_CSV = _ROOT / "data" / "raw" / "marshall_plan_aid.csv"
CPI_CSV = _ROOT / "data" / "raw" / "us_cpi_annual.csv"
CPI_ANCHOR_YEAR = 1950                          # mid-period of 1948-52 disbursement

TABLES, FIGURES = config.output_dirs("context_comparisons")


def cname(iso):
    over = getattr(config, "COUNTRY_NAME_OVERRIDES", {})
    if iso in over:
        return over[iso]
    try:
        import pycountry
        c = pycountry.countries.get(alpha_3=iso)
        return c.common_name if hasattr(c, "common_name") else c.name
    except Exception:
        return iso


# ── headline UT gains per country ────────────────────────────────────────────
def load_gains():
    """Per-country annual-average net UT revenue gain, bn constant 2025 USD."""
    p = (_ROOT / "output" / "unitary_taxation" / "reported_only" / "excl_resource"
         / "tables" / "summary_country_year_long.csv")
    d = pd.read_csv(p, low_memory=False)
    d = d[(d.formula_name == HEADLINE) & (d.etr_name == ETR) & (d.rate_mode == RATE)]
    if d["etr_threshold"].astype(str).nunique() > 1:
        d = d[d["etr_threshold"].astype(str) == THRESH]
    d = d[d["year"].isin(YEARS)]
    d = d.assign(_v=d["revenue_gain_from_ut"] * d["year"].map(DEFL))
    g = (d.groupby(["iso_partner", "wb_income_group"], as_index=False)["_v"].sum()
           .rename(columns={"iso_partner": "iso3", "_v": "gain_bn"}))
    g["gain_bn"] = g["gain_bn"] / 1e3 / N_YEARS          # mUSD -> bn, per-year avg
    return g


# ── part 1: outstanding IMF credit ───────────────────────────────────────────
def load_imf_credit():
    """Latest non-null IMF credit stock per country (current USD -> 2025 USD)."""
    if not IMF_CACHE.exists():
        print(f"cache missing — fetching {IMF_API}")
        with urllib.request.urlopen(IMF_API) as r:
            meta, rows = json.load(r)
        import pycountry
        iso_ok = {c.alpha_3 for c in pycountry.countries}
        recs = [(x["countryiso3code"], x["country"]["value"], int(x["date"]), x["value"])
                for x in rows if x["countryiso3code"] in iso_ok]
        recs.sort()
        hdr = ("# Use of IMF credit (DOD, current US$) — WB IDS DT.DOD.DIMF.CD; see\n"
               "# docs/imf_marshall_comparison_sources.md. Refetched by 9t.\n")
        with open(IMF_CACHE, "w", newline="", encoding="utf-8") as f:
            f.write(hdr)
            pd.DataFrame(recs, columns=["iso3", "country_name", "year", "imf_credit_usd"]
                         ).to_csv(f, index=False)
    d = pd.read_csv(IMF_CACHE, comment="#")
    d = d.dropna(subset=["imf_credit_usd"])
    d = d.sort_values("year").groupby("iso3", as_index=False).last()   # latest year
    # express the (nominal, stock-year) credit in constant 2025 USD
    d["imf_credit_bn"] = d.apply(
        lambda r: r["imf_credit_usd"] * DEFL.get(int(r["year"]), 1.0) / 1e9, axis=1)
    return d.rename(columns={"year": "credit_year"})[
        ["iso3", "country_name", "credit_year", "imf_credit_bn"]]


def part1_imf(gains):
    imf = load_imf_credit()
    m = imf.merge(gains, on="iso3", how="left")
    m["country"] = m["iso3"].map(cname)
    m["years_to_repay"] = np.where(m["gain_bn"] > 0,
                                   m["imf_credit_bn"] / m["gain_bn"], np.nan)
    m["gain_negative_or_zero"] = (m["gain_bn"] <= 0) | m["gain_bn"].isna()

    cols = ["country", "iso3", "wb_income_group", "credit_year",
            "imf_credit_bn", "gain_bn", "years_to_repay", "gain_negative_or_zero"]
    out = m[cols].sort_values("imf_credit_bn", ascending=False)

    # aggregates: all IDS debtors with estimates, and per income group
    agg_rows = []
    scope = m.dropna(subset=["gain_bn"])
    for label, sub in ([("ALL IDS debtor countries", scope)] +
                       [(f"income group: {g}", scope[scope.wb_income_group == g])
                        for g in sorted(scope.wb_income_group.dropna().unique())]):
        credit, gain = sub["imf_credit_bn"].sum(), sub["gain_bn"].sum()
        agg_rows.append(dict(country=label, iso3="", wb_income_group="",
                             credit_year="", imf_credit_bn=credit, gain_bn=gain,
                             years_to_repay=(credit / gain if gain > 0 else np.nan),
                             gain_negative_or_zero=gain <= 0))
    out = pd.concat([pd.DataFrame(agg_rows), out], ignore_index=True).round(2)
    f = TABLES / "ut_gains_vs_imf_credit.csv"
    out.to_csv(f, index=False)
    print(f"wrote {f}")
    print(out.head(8).to_string(index=False))

    # figure: the largest IMF debtors with a positive UT gain
    top = (m[(m.gain_bn > 0)].sort_values("imf_credit_bn", ascending=False)
           .head(15).sort_values("years_to_repay"))
    dropped = m[(m.gain_bn <= 0)].sort_values("imf_credit_bn", ascending=False)
    fig, ax = plt.subplots(figsize=(9, 6.5))
    bars = ax.barh(top["country"], top["years_to_repay"], color=POSITIVE)
    ax.bar_label(bars,
                 labels=[f" {y:,.1f} yrs  (owes ${c:,.1f}bn)"
                         for y, c in zip(top["years_to_repay"], top["imf_credit_bn"])],
                 fontsize=10, padding=2)
    ax.set_xlabel("Years of unitary-taxation revenue gains needed to repay the country's\n"
                  "entire outstanding IMF credit", fontsize=11)
    ax.margins(x=0.28)
    ax.invert_yaxis()
    all_credit = scope["imf_credit_bn"].sum()
    all_gain = scope["gain_bn"].sum()
    note = ("Note: the 15 countries with the largest outstanding IMF credit (World Bank "
            "International Debt Statistics,\nlatest year, mostly 2024) among those gaining "
            "from unitary taxation. Bars show outstanding IMF credit divided\nby the "
            "country's average yearly revenue gain under unitary taxation (2016–2022 excl. "
            "2020, 2025 USD).\nAcross all low- and middle-income debtor countries, "
            f"{all_credit / all_gain:,.1f} years of gains (${all_gain:,.0f}bn/yr) would "
            f"clear the\nentire ${all_credit:,.0f}bn owed to the IMF.")
    if len(dropped):
        note += ("\nNot shown (no net gain under unitary taxation): "
                 + ", ".join(dropped["country"].head(5)) + ".")
    fig.text(0.01, -0.02, note, fontsize=8.5, va="top")
    plt.tight_layout()
    f = FIGURES / "fig_ut_gains_vs_imf_credit.png"
    plt.savefig(f, dpi=130, bbox_inches="tight")
    plt.close()
    print(f"wrote {f}")


# ── part 2: the Marshall Plan ────────────────────────────────────────────────
def part2_marshall(gains):
    aid = pd.read_csv(MARSHALL_CSV, comment="#")
    cpi = pd.read_csv(CPI_CSV, comment="#").set_index("year")["cpi_u"]
    cpi_factor = cpi[config.BASE_YEAR] / cpi[CPI_ANCHOR_YEAR]

    by_iso = gains.set_index("iso3")["gain_bn"]

    def gain_for(iso3):
        if pd.isna(iso3) or iso3 == "":
            return np.nan                       # Regional row
        return sum(by_iso.get(p, np.nan) for p in str(iso3).split("+"))

    aid["gain_bn"] = aid["iso3"].apply(gain_for)          # annual avg, bn 2025 USD
    aid["cum_gain_bn"] = aid["gain_bn"] * N_YEARS
    for src, dst in [("aid_total_musd", "aid_total_2025bn"),
                     ("grants_musd", "aid_grants_2025bn")]:
        aid[dst] = aid[src] * cpi_factor / 1e3
    aid["marshall_plans_per_6yr"] = aid["cum_gain_bn"] / aid["aid_total_2025bn"]
    aid["years_per_marshall_plan"] = np.where(
        aid["gain_bn"] > 0, aid["aid_total_2025bn"] / aid["gain_bn"], np.nan)
    aid["years_per_marshall_plan_grants"] = np.where(
        aid["gain_bn"] > 0, aid["aid_grants_2025bn"] / aid["gain_bn"], np.nan)

    # aggregate: every recipient (Regional aid counts in the denominator)
    tot_aid, tot_grants = aid["aid_total_2025bn"].sum(), aid["aid_grants_2025bn"].sum()
    tot_gain = aid["gain_bn"].sum(skipna=True)            # Regional row is NaN
    agg = dict(recipient="ALL RECIPIENTS (aggregate)", iso3="",
               aid_total_musd=aid["aid_total_musd"].sum(),
               grants_musd=aid["grants_musd"].sum(),
               aid_total_2025bn=tot_aid, aid_grants_2025bn=tot_grants,
               gain_bn=tot_gain, cum_gain_bn=tot_gain * N_YEARS,
               marshall_plans_per_6yr=tot_gain * N_YEARS / tot_aid,
               years_per_marshall_plan=tot_aid / tot_gain,
               years_per_marshall_plan_grants=tot_grants / tot_gain)
    out = pd.concat([pd.DataFrame([agg]), aid], ignore_index=True)
    keep = ["recipient", "iso3", "aid_total_musd", "grants_musd", "loans_musd",
            "aid_total_2025bn", "aid_grants_2025bn", "gain_bn", "cum_gain_bn",
            "marshall_plans_per_6yr", "years_per_marshall_plan",
            "years_per_marshall_plan_grants", "confidence", "note"]
    out = out[[c for c in keep if c in out.columns]].round(2)
    f = TABLES / "ut_gains_vs_marshall_plan.csv"
    out.to_csv(f, index=False)
    print(f"wrote {f}")
    print(out.head(4).to_string(index=False))

    # ── figure 1 (headline): aggregate — the plan vs what UT delivers ────────
    fig, ax = plt.subplots(figsize=(8, 5))
    vals = [tot_aid, tot_gain * N_YEARS]
    labs = ["The entire Marshall Plan\n(1948–52, in 2025 USD)",
            f"Unitary-taxation gains of the same\ncountries over {N_YEARS} years"]
    bars = ax.bar(labs, vals, color=[PALETTE[5], POSITIVE], width=0.55)
    ax.bar_label(bars, labels=[f"${v:,.0f}bn" for v in vals], fontsize=13, padding=3)
    ax.set_ylabel("USD bn (constant 2025)", fontsize=11)
    ax.margins(y=0.15)
    note = ("Note: the Marshall Plan transferred $13.3bn to 16 European economies between "
            "April 1948 and June 1952 —\nabout "
            f"${tot_aid:,.0f}bn in 2025 dollars (US CPI). Under unitary taxation the same "
            f"countries would together gain\n${tot_gain:,.1f}bn per year "
            f"(average 2016–2022 excl. 2020) — a full Marshall Plan roughly every "
            f"{tot_aid / tot_gain:,.1f} years.\nCountry gains and losses (Ireland and the "
            "Netherlands lose) are netted within the group.")
    fig.text(0.01, -0.02, note, fontsize=8.5, va="top")
    plt.tight_layout()
    f = FIGURES / "fig_ut_gains_vs_marshall_aggregate.png"
    plt.savefig(f, dpi=130, bbox_inches="tight")
    plt.close()
    print(f"wrote {f}")

    # ── figure 2 (detail): per-recipient aid vs cumulative gain ──────────────
    d = aid.dropna(subset=["gain_bn"]).sort_values("cum_gain_bn")
    y = np.arange(len(d))
    bw = 0.4
    fig, ax = plt.subplots(figsize=(9, 7.5))
    ax.barh(y + bw / 2, d["aid_total_2025bn"], height=bw, color=PALETTE[5])
    colors = [POSITIVE if v >= 0 else NEGATIVE for v in d["cum_gain_bn"]]
    ax.barh(y - bw / 2, d["cum_gain_bn"], height=bw, color=colors)
    ax.set_yticks(y)
    ax.set_yticklabels(d["recipient"], fontsize=10)
    ax.axvline(0, color="0.4", linewidth=0.8)
    ax.set_xlabel("USD bn (constant 2025)", fontsize=11)
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(color=PALETTE[5], label="Marshall Plan aid received (2025 USD)"),
        Patch(color=POSITIVE, label=f"Unitary-taxation gain over {N_YEARS} years"),
        Patch(color=NEGATIVE, label=f"Unitary-taxation loss over {N_YEARS} years"),
    ], fontsize=10, loc="lower right")
    note = ("Note: per-recipient detail behind the aggregate comparison. Marshall aid per "
            "CRS R45079 Table 2 (USAID),\nconverted with the US CPI (mid-period 1950). "
            "Gains are cumulative over the six headline years (2016–2022\nexcl. 2020). "
            "Red bars: countries that lose revenue under unitary taxation. "
            "Belgium-Luxembourg is compared\nagainst the two countries' combined estimate "
            "(aid was reported jointly).")
    fig.text(0.01, -0.02, note, fontsize=8.5, va="top")
    plt.tight_layout()
    f = FIGURES / "fig_ut_gains_vs_marshall_by_recipient.png"
    plt.savefig(f, dpi=130, bbox_inches="tight")
    plt.close()
    print(f"wrote {f}")


def main():
    gains = load_gains()
    part1_imf(gains)
    part2_marshall(gains)


if __name__ == "__main__":
    main()
