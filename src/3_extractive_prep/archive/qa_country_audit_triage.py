"""
Phase-A triage for the A-Z resource-correction country audit (2026-07-22 plan).

One row per CbCR partner country (226): identity (include flag, rents, EITI),
panel metrics (take by bucket/tier, generic-share %, dropped $), CbCR-side
metrics (reported profit/tax, correction, negative excl_resource cells),
document availability (IMF Article IVs), flags (dossier + 9f + thin-coverage +
UT-loser), and a rule-based triage verdict:

  deep_read : include=yes; OR include=no with rents >= 0.5% GDP, correction-
              relevant flags, or a UT tax-base loss in the reported sample
              (user 2026-07-22: every UT loser gets a deep read)
  check     : borderline (rents 0.1-0.5, or minor flags only)
  clear     : include=no, no rents, no flags, no UT loss ("correctly uncorrected")

Output: data/intermediate/extractive/audit_country_triage.csv
Usage:  python qa_country_audit_triage.py
"""
import glob
import os
import sys

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import BASE, RAW, EXT_INT  # noqa: E402

OUT = EXT_INT / "audit_country_triage.csv"
AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]
BUCKETS = ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd"]


def main():
    # ── CbCR side ──
    cb = pd.read_csv(BASE / "data/final/cbcr_main_disaggregated.csv",
                     usecols=["iso_parent", "iso_partner", "year", "is_distributed",
                              "profit_loss_before_income_tax_corrected",
                              "income_tax_paid_on_cash_basis"], low_memory=False)
    rep = cb[(cb.is_distributed == 0) & cb.year.isin(AVG_YEARS)]
    prof = rep.groupby("iso_partner")["profit_loss_before_income_tax_corrected"].sum() / 1e6
    tax = rep.groupby("iso_partner")["income_tax_paid_on_cash_basis"].sum() / 1e6
    t = pd.DataFrame({"reported_profit_musd": prof, "reported_tax_musd": tax})
    t.index.name = "iso3"

    ex = pd.read_csv(BASE / "data/final/cbcr_main_excl_resource.csv",
                     usecols=["iso_partner", "year", "is_distributed",
                              "profit_loss_excl_resource", "resource_profit_base_usd"],
                     low_memory=False)
    exr = ex[(ex.is_distributed == 0) & ex.year.isin(AVG_YEARS)]
    t["resource_base_removed_musd"] = exr.groupby("iso_partner")["resource_profit_base_usd"].sum() / 1e6
    neg = exr[exr["profit_loss_excl_resource"] < 0]
    t["n_neg_exclres_cells"] = neg.groupby("iso_partner").size()
    t["neg_exclres_musd"] = neg.groupby("iso_partner")["profit_loss_excl_resource"].sum() / 1e6

    # ── control table ──
    p = pd.read_csv(RAW / "resources/resource_country_parameters.csv")
    p = p.set_index("iso3")
    for c in ["include", "drop_reason", "status", "commodity_main", "eiti",
              "extractive_rents_pct_gdp", "resource_rate", "domestic_share"]:
        t[c] = p[c] if c in p.columns else np.nan

    # ── payment panel ──
    pay = pd.read_csv(EXT_INT / "resource_payments_by_hq_source_yearly.csv")
    pay["total_usd"] = pay[BUCKETS].sum(axis=1)
    g = pay.groupby("source_iso3")
    t["panel_take_musd"] = g["total_usd"].sum() / 1e6
    t["panel_years"] = g["year"].nunique()
    t["panel_tiers"] = g["data_source"].agg(lambda s: "|".join(sorted(set(s))))
    for_ = pay[pay.hq_iso3 != pay.source_iso3]
    t["foreign_take_musd"] = for_.groupby("source_iso3")["total_usd"].sum() / 1e6
    gen = for_[for_.get("hq_share_basis", "") == "generic_global"]
    t["generic_share_pct_of_foreign"] = (
        100 * gen.groupby("source_iso3")["total_usd"].sum()
        / for_.groupby("source_iso3")["total_usd"].sum()).round(1)

    unm = pd.read_csv(EXT_INT / "resource_correction_unmatched_cells.csv")
    unm["tot"] = unm[["pre_profit_payments_usd", "post_profit_payments_usd",
                      "equity_income_usd"]].sum(axis=1)
    fu = unm[unm.iso_parent != unm.iso_partner]
    t["dropped_foreign_musd"] = fu.groupby("iso_partner")["tot"].sum() / 1e6

    # ── 9f + dossier flags ──
    f9 = pd.read_csv(BASE / "output/unitary_taxation/across_samples/resource_correction/"
                            "tables/resource_correction_by_country_2016_22.csv")
    f9 = f9.set_index("iso_partner")
    t["contribution_pct_profit"] = pd.to_numeric(f9.get("contribution_pct_profit"), errors="coerce")
    t["sanity_flag_9f"] = f9.get("sanity_flag")
    ds = pd.read_csv(BASE / "output/extractive/country_resource_info/_SUMMARY.csv").set_index("iso")
    t["dossier_flags"] = ds["flags"]
    t["dossier_severity"] = ds["severity"]

    # ── UT losers (reported sample, 9h) ──
    nb = pd.read_csv(BASE / "output/unitary_taxation/across_samples/country_overview/"
                            "tables/negative_by_formula_reported.csv")
    nb = nb.set_index("ISO3")
    t["ut_n_formulas_with_loss"] = pd.to_numeric(nb["# formulas with a loss"], errors="coerce")
    t["ut_worst_loss_musd"] = pd.to_numeric(nb["worst loss (any formula)"], errors="coerce")

    # ── coverage flag + IMF docs ──
    cov = pd.read_csv(BASE / "output/unitary_taxation/across_samples/country_overview/"
                             "tables/data_coverage_by_partner.csv").set_index("iso_partner")
    t["thin_data"] = cov["thin_data"]
    imf_dir = RAW / "resources/resource_profits_manual_sources/imf"
    def imf_docs(iso):
        fs = sorted(os.path.basename(x) for x in glob.glob(str(imf_dir / f"{iso}_IMF*")))
        return "|".join(fs)
    t["imf_docs"] = [imf_docs(i) for i in t.index]
    t["n_imf_docs"] = t["imf_docs"].str.count(r"\|") + (t["imf_docs"] != "").astype(int)

    # ── triage verdict ──
    rents = pd.to_numeric(t["extractive_rents_pct_gdp"], errors="coerce").fillna(0)
    inc = t["include"].astype(str).str.lower() == "yes"
    # 9f's sanity_flag is ALWAYS populated ("ok" / "no_resource_correction" are
    # benign states, not problems) — only other values count as flags.
    flags = (~t["sanity_flag_9f"].fillna("ok").astype(str)
             .isin(["ok", "no_resource_correction", ""])) | \
            (pd.to_numeric(t["dossier_severity"], errors="coerce").fillna(0) > 0)
    ut_loser = t["ut_n_formulas_with_loss"].fillna(0) > 0
    deep = inc | (rents >= 0.5) | flags | ut_loser
    check = ~deep & ((rents >= 0.1) | (t["panel_take_musd"].fillna(0) > 0))
    t["triage"] = np.where(deep, "deep_read", np.where(check, "check", "clear"))

    t = t.sort_index()
    t.to_csv(OUT)
    print(f"wrote {OUT}  ({len(t)} countries)")
    print(t["triage"].value_counts().to_string())
    print(f"deep_read & EITI (consult-first): "
          f"{((t.triage == 'deep_read') & (t.eiti.astype(str).str.lower().isin(['true', '1', 'yes']))).sum()}")
    print(f"deep_read with no IMF docs: "
          f"{((t.triage == 'deep_read') & (t.n_imf_docs == 0)).sum()}")


if __name__ == "__main__":
    main()
