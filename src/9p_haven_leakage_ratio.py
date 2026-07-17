# %% [0] Haven leakage ratio — world revenue loss havens CAUSE per $1 they COLLECT
"""
Haven-attributable "world-loss-per-dollar-collected" ratio.

For each $1 of tax a tax haven collects on the profit shifted into it, how many
dollars of tax revenue does the rest of the world lose? Computed ONLY for the part
tax havens are really responsible for — NOT the home-bias domestic over-booking of
high-tax countries (Japan/China/Canada), which the old "hub multiplier ≈14×"
wrongly lumped in.

    ratio = Σ_havens tax_revenue_loss_caused_musd   (world revenue loss havens CAUSE)
            ────────────────────────────────────
            Σ_havens tax_revenue_gain               (revenue havens COLLECT on shifted-in profit)

Both quantities come straight from the per-country UT estimates written by
5_estimate_profit_shifting.py. `tax_revenue_loss_caused_musd` is built inside
adjust_misalignment PER iso_parent (HQ) group — each sufferer's loss is valued at
that sufferer's own tax rate before being split across the HQ group's harmers — so
the harm is already taken per country / per HQ and rate-weighted. No bilateral step
and no 15% ETR gate are needed: havens are identified by the LIST
(wb_income_group == "investment_hub", i.e. TAX_HAVENS_REPRESENTATION), and the UT
estimates use the full-reapportionment (etrmax_inf) specs.

Headline spec: reported-only, excl_resource, sales_employees_destcfb, etrmax_inf,
loss_cit_gain_etr, 2016-2022 excluding 2020. The ratio is a ratio of two same-unit
dollar sums, so it is deflator-invariant.

Outputs (via output_dirs("deliverables/haven_leakage") ->
output/unitary_taxation/across_samples/haven_leakage/):
  - haven_leakage_ratio_summary.csv   (headline + sensitivity grid)
  - haven_leakage_ratio_by_haven.csv  (per-haven breakdown, headline spec)

Usage: python 9p_haven_leakage_ratio.py
"""
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from config import output_dirs

# ── Fixed choices ────────────────────────────────────────────────────────────
SAMPLE = "reported_only"           # no imputed rows
FORMULA = "sales_employees_destmnedds"  # headline destination formula (MNE sales + MNE-share DDS, 2026-07-12)
ETRMAX = "inf"                      # full reapportionment, no 15% haven gate
EXCLUDE_YEARS = {2020}             # COVID-distorted low-coverage year
HAVEN_GROUP = "investment_hub"     # == TAX_HAVENS_REPRESENTATION classification

# Datasets (name -> the /tables/<sub>/ folder script 5 writes into for this sample).
DATASETS = {
    "baseline": "disaggregated",            # resources ignored
    "excl_resource": "excl_resource",        # HEADLINE
    "excl_resource_floored": "excl_resource_floored",
}
RATE_MODES = {
    "loss_cit_gain_etr": "ETR-CIT (gains@CIT, losses@ETR)",   # HEADLINE
    "loss_etr_gain_etr": "both legs @ ETR",
}
HEADLINE = ("excl_resource", "loss_cit_gain_etr")

_ROOT = str(Path(__file__).resolve().parent.parent / "output" / "unitary_taxation")


def _country_estimates_path(dataset, rate):
    sub = DATASETS[dataset]
    pat = (f"{_ROOT}/{SAMPLE}/{dataset}/tables/{sub}/"
           f"country_estimates__{FORMULA}__etrdef_domfor__etrmax_{ETRMAX}__{rate}.csv")
    hits = glob.glob(pat)
    return hits[0] if hits else None


def _load(dataset, rate):
    fp = _country_estimates_path(dataset, rate)
    if fp is None:
        print(f"  [missing] {dataset} / {rate}")
        return None
    d = pd.read_csv(fp)
    d = d[~d["year"].isin(EXCLUDE_YEARS)].copy()
    for c in ("tax_revenue_loss_caused_musd", "tax_revenue_gain",
              "revenue_gain_from_ut"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def _ratio_row(dataset, rate):
    d = _load(dataset, rate)
    if d is None:
        return None
    hav = d[d["wb_income_group"] == HAVEN_GROUP]
    loss_caused = hav["tax_revenue_loss_caused_musd"].sum()   # numerator (musd)
    collected = hav["tax_revenue_gain"].sum()                 # denominator (musd)
    net_ut_loss = -hav["revenue_gain_from_ut"].sum()          # havens' net UT loss (musd)
    total_loss_caused = d["tax_revenue_loss_caused_musd"].sum()
    return {
        "dataset": dataset,
        "rate_mode": rate,
        "rate_mode_label": RATE_MODES[rate],
        "world_loss_havens_cause_bn": loss_caused / 1e3,
        "revenue_havens_collect_bn": collected / 1e3,
        "ratio_loss_per_dollar_collected": (loss_caused / collected
                                            if collected else np.nan),
        "havens_net_ut_loss_bn": net_ut_loss / 1e3,
        "ratio_vs_net_ut_loss": (loss_caused / net_ut_loss
                                 if net_ut_loss else np.nan),
        "haven_share_of_total_loss_caused_pct": (100 * loss_caused / total_loss_caused
                                                 if total_loss_caused else np.nan),
        "is_headline": (dataset, rate) == HEADLINE,
    }


def _by_haven(dataset, rate):
    """Per-haven breakdown for one spec: what each haven causes vs collects."""
    d = _load(dataset, rate)
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


def main():
    tables_dir, _ = output_dirs("deliverables/haven_leakage")

    # Full sensitivity grid (datasets x rate modes).
    rows = [r for ds in DATASETS for rt in RATE_MODES
            if (r := _ratio_row(ds, rt)) is not None]
    summary = pd.DataFrame(rows)
    summary_fp = tables_dir / "haven_leakage_ratio_summary.csv"
    summary.to_csv(summary_fp, index=False)

    # Per-haven breakdown on the headline spec.
    by_haven = _by_haven(*HEADLINE)
    by_haven_fp = tables_dir / "haven_leakage_ratio_by_haven.csv"
    if by_haven is not None:
        by_haven.to_csv(by_haven_fp, index=False)

    # ── Report ───────────────────────────────────────────────────────────────
    hl = summary[summary["is_headline"]].iloc[0]
    print("=" * 78)
    print("HAVEN LEAKAGE RATIO — world revenue loss havens CAUSE per $1 they COLLECT")
    print("=" * 78)
    print(f"Spec: {SAMPLE} / {HEADLINE[0]} / {FORMULA} / etrmax_{ETRMAX} / {HEADLINE[1]}")
    print(f"Window: 2016-2022 excl {sorted(EXCLUDE_YEARS)}; havens = {HAVEN_GROUP} list\n")
    print(f"  world revenue loss havens CAUSE  = ${hl.world_loss_havens_cause_bn:,.0f} bn")
    print(f"  revenue havens COLLECT           = ${hl.revenue_havens_collect_bn:,.0f} bn")
    print(f"  >>> RATIO = {hl.ratio_loss_per_dollar_collected:.2f}  "
          f"(for each $1 a haven collects, the world loses "
          f"~${hl.ratio_loss_per_dollar_collected:.1f})")
    print(f"  havens cause {hl.haven_share_of_total_loss_caused_pct:.0f}% of ALL "
          f"UT-reallocated loss (rest = home-bias over-booking)\n")

    print("Sensitivity (ratio = loss caused / revenue collected):")
    show = summary[["dataset", "rate_mode_label",
                    "ratio_loss_per_dollar_collected",
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


if __name__ == "__main__":
    main()
