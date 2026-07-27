"""
Data-quality checks for the resource-payment-correction pipeline (3_31 → 3_33 → 3_38 → 4_).

Checks the upstream artefacts and the three deliverable CbCR datasets:
  - data/intermediate/extractive/eiti_company_payments_long.csv          (3_31)
  - data/intermediate/extractive/eiti_company_hq_map.csv                 (3_33)
  - data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv (3_38)
  - data/final/cbcr_main_excl_resource.csv                               (4_)
  - data/final/cbcr_main_incl_resource.csv                               (4_)

Prints PASS/FAIL/WARN lines + a few informational tables. Non-zero exit if any FAIL.
"""
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

ROOT = (EXT_INT / ".." / ".." / "..").resolve()
PAY_LONG = EXT_INT / "eiti_company_payments_long.csv"
HQ_MAP = EXT_INT / "eiti_company_hq_map.csv"
RP = EXT_INT / "resource_payments_by_hq_source_yearly.csv"
CBCR_IN = ROOT / "data" / "final" / "cbcr_main_disaggregated.csv"
CBCR_EXCL = ROOT / "data" / "final" / "cbcr_main_excl_resource.csv"
CBCR_INCL = ROOT / "data" / "final" / "cbcr_main_incl_resource.csv"
CBCR_EXCL_FLOOR = ROOT / "data" / "final" / "cbcr_main_excl_resource_floored.csv"
PCOL = "profit_loss_before_income_tax_corrected"
TCOL = "income_tax_paid_on_cash_basis"
BUCKETS = ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd", "other_payments_usd"]
FLEX_VARIANTS = ("cat1", "cat2", "cat3")

n_fail = 0
n_warn = 0


def chk(name, ok, detail="", warn=False):
    global n_fail, n_warn
    if ok:
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    elif warn:
        n_warn += 1
        print(f"  [WARN] {name}" + (f" — {detail}" if detail else ""))
    else:
        n_fail += 1
        print(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def b(x):  # $bn pretty
    return f"${x/1e9:,.1f}B"


# ───────────────────────── 1. EITI long payments ─────────────────────────────
print("\n=== 1. eiti_company_payments_long.csv ===")
pay = pd.read_csv(PAY_LONG, usecols=["iso3", "year", "commodity", "company_name", "revenue_type", "value_usd"], low_memory=False)
print(f"  rows: {len(pay):,}")
chk("iso3 all 3-char", (pay.iso3.astype(str).str.len() == 3).all(), f"{(pay.iso3.astype(str).str.len()!=3).sum()} bad")
chk("year numeric & in 1990-2025", pay.year.between(1990, 2025).all(), f"range {pay.year.min()}-{pay.year.max()}")
chk("revenue_type in {royalty_like,cit,equity,other}", set(pay.revenue_type.dropna()).issubset({"royalty_like", "cit", "equity", "other"}), str(set(pay.revenue_type.dropna())))
chk("commodity in {oil_gas,coal,minerals,unknown,other}", set(pay.commodity.dropna()).issubset({"oil_gas", "coal", "minerals", "unknown", "other"}), str(set(pay.commodity.dropna())))
v = pd.to_numeric(pay.value_usd, errors="coerce")
chk("value_usd parses", v.notna().all() or v.isna().mean() < 0.001, f"{v.isna().sum()} NaN")
chk("no |value_usd| > $50B (single row)", (v.abs() <= 5e10).all(), f"{(v.abs()>5e10).sum()} rows; max {b(v.abs().max())}")
chk("negatives are a minority (<3%)", (v < 0).mean() < 0.03, f"{(v<0).mean()*100:.1f}% negative", warn=(v < 0).mean() >= 0.03)
chk("no 'general' bucket leaked", "general" not in set(pay.revenue_type.dropna()))
print(f"  value by revenue_type: " + ", ".join(f"{k}={b(g)}" for k, g in v.groupby(pay.revenue_type).sum().sort_values(ascending=False).items()))
print(f"  value by commodity:    " + ", ".join(f"{k}={b(g)}" for k, g in v.groupby(pay.commodity).sum().sort_values(ascending=False).items()))
print(f"  countries: {pay.iso3.nunique()}; years: {pay.year.min()}-{pay.year.max()}; total {b(v.sum())}")

# ───────────────────────── 2. HQ map ─────────────────────────────────────────
print("\n=== 2. eiti_company_hq_map.csv ===")
hq = pd.read_csv(HQ_MAP)
print(f"  rows: {len(hq):,}")
chk("match_method in known set", set(hq.match_method).issubset({"override", "exact_norm_country", "exact_norm_global", "substring_country", "substring_global", "fuzzy_country", "fuzzy_global", "unmatched"}), str(set(hq.match_method)))
chk("matched rows have 3-char hq_iso3", ((hq.match_method == "unmatched") | (hq.hq_iso3.astype(str).str.len() == 3)).all())
chk("unmatched rows have blank hq_iso3", (hq[hq.match_method == "unmatched"].hq_iso3.fillna("") == "").all())
# every (iso3, company) in payments has exactly one map row
pk = pay[["iso3", "company_name"]].drop_duplicates()
mk = hq[["source_iso3", "company_name"]].rename(columns={"source_iso3": "iso3"})
chk("1:1 (source,company) coverage payments↔map", len(pk) == len(mk) == len(mk.drop_duplicates()) and len(pk.merge(mk, on=["iso3", "company_name"])) == len(pk),
    f"pay {len(pk)} / map {len(mk)} / map-dedup {len(mk.drop_duplicates())}")
tot_v = pd.to_numeric(hq.total_value_usd, errors="coerce")
matched_v = tot_v[hq.match_method != "unmatched"].sum()
print(f"  matched names: {(hq.match_method!='unmatched').sum():,}/{len(hq):,} ({100*(hq.match_method!='unmatched').mean():.0f}%); by value {b(matched_v)}/{b(tot_v.sum())} ({100*matched_v/tot_v.sum():.0f}%)")
dom = hq[(hq.match_method != "unmatched") & (hq.hq_iso3 == hq.source_iso3)]
chk("matched-by-value >= 60%", matched_v / tot_v.sum() >= 0.60, f"{100*matched_v/tot_v.sum():.0f}%", warn=matched_v / tot_v.sum() < 0.60)
print(f"  domestic (hq==source) value among matched: {b(pd.to_numeric(dom.total_value_usd,errors='coerce').sum())}")

# ───────────────────────── 3. resource_payments_by_hq_source ─────────────────
print("\n=== 3. resource_payments_by_hq_source_yearly.csv ===")
rp = pd.read_csv(RP)
print(f"  rows: {len(rp):,}")
chk("source_iso3 & hq_iso3 3-char", (rp.source_iso3.str.len() == 3).all() and (rp.hq_iso3.str.len() == 3).all(),
    f"bad source {sorted(rp[rp.source_iso3.str.len()!=3].source_iso3.unique())}, bad hq {sorted(rp[rp.hq_iso3.str.len()!=3].hq_iso3.unique())}")
chk("commodity in {oil_gas,coal,minerals,unknown,other}", set(rp.commodity).issubset({"oil_gas", "coal", "minerals", "unknown", "other"}), str(set(rp.commodity)))
chk("data_source in known set", set(rp.data_source).issubset({"eiti_bilateral", "manual_distributed", "grd_distributed", "eiti_grdscaled", "eiti_extrapolated", "manual_extrapolated", "grd_extrapolated"}), str(set(rp.data_source)))
chk("no NaN in bucket columns", rp[BUCKETS].notna().all().all())
# negatives can occur in EITI-bilateral cells (net refunds/credits recorded as negative payments); they should be tiny in aggregate
neg = rp[BUCKETS].clip(upper=0).sum().sum()
pos = rp[BUCKETS].clip(lower=0).sum().sum()
chk("net-negative bucket entries are negligible (<0.5% of positives)", abs(neg) < 0.005 * pos, f"Σ negatives {b(neg)} vs Σ positives {b(pos)}", warn=abs(neg) >= 0.005 * pos)
chk("no all-zero rows", (rp[BUCKETS].abs().sum(axis=1) > 0).all())
_ukey = ["source_iso3", "hq_iso3", "commodity", "year", "data_source"] + (["hq_share_basis"] if "hq_share_basis" in rp.columns else [])
chk("unique (source,hq,commodity,year,data_source[,hq_share_basis])", not rp.duplicated(_ukey).any())
# a source country should be served by exactly one data_source family (EITI countries -> eiti_bilateral only, etc.)
multi = rp.groupby("source_iso3").data_source.nunique()
chk("each source country has a single data_source", (multi == 1).all(), f"{(multi>1).sum()} with >1: {sorted(multi[multi>1].index)[:10]}", warn=(multi > 1).any())
# reconcile EITI-bilateral portion against the (matched, MNE-gated) long payments
eiti_rp = rp[rp.data_source == "eiti_bilateral"][BUCKETS].sum().sum()
pay2 = pay.merge(hq[["source_iso3", "company_name", "hq_iso3", "match_method", "in_cbcr_universe"]].rename(columns={"source_iso3": "iso3"}), on=["iso3", "company_name"], how="left")
keep = (pay2.hq_iso3.notna() & (pay2.hq_iso3.astype(str).str.len() == 3) & pay2.year.between(2010, 2025) & pay2.revenue_type.isin(["royalty_like", "cit", "equity", "other"]))
in_u = pd.to_numeric(pay2["in_cbcr_universe"], errors="coerce").fillna(0).astype(int)
keep = keep & ~((pay2.hq_iso3 == pay2.iso3) & (in_u != 1))   # mirror 3_38's domestic-non-MNE drop
pay_matched = pd.to_numeric(pay2.loc[keep, "value_usd"], errors="coerce").clip(lower=0).sum()   # 3_38 floors pre/eq/other at 0
chk("EITI-bilateral total reconciles with matched (MNE-gated) long payments (≤2%)", abs(eiti_rp - pay_matched) <= 0.02 * max(1, pay_matched), f"rp {b(eiti_rp)} vs payments {b(pay_matched)}", warn=abs(eiti_rp - pay_matched) > 0.02 * max(1, pay_matched))
print(f"  by data_source ($B): " + ", ".join(f"{k}={b(g)}" for k, g in rp.groupby('data_source')[BUCKETS].sum().sum(axis=1).sort_values(ascending=False).items()))
print(f"  source countries: {rp.source_iso3.nunique()}; HQ countries: {rp.hq_iso3.nunique()}; years {rp.year.min()}-{rp.year.max()}")
# top 12 source countries by total
top_src = rp.groupby("source_iso3")[BUCKETS].sum().sum(axis=1).sort_values(ascending=False).head(12)
print("  top source countries ($B): " + ", ".join(f"{k} {v/1e9:,.0f}" for k, v in top_src.items()))

# ───────────────────────── 4. cbcr_main_excl_resource.csv ────────────────────
print("\n=== 4. cbcr_main_excl_resource.csv ===")
EXCL_COLS = ["iso_parent", "iso_partner", "year", "is_distributed",
             PCOL, TCOL,
             "resource_profit_base_usd", "resource_tax_deduction_usd",
             "post_profit_payments_usd", "equity_income_usd",
             "profit_loss_excl_resource",
             "income_tax_paid_on_cash_basis_excl_resource",
             "total_profit_loss_excl_resource",
             "etr_average_excl_resource", "etr_partner_median_excl_resource",
             "etr_partner_p25_excl_resource", "etr_partner_min_excl_resource",
             "etr_parent_partner_excl_resource"]
ci = pd.read_csv(CBCR_IN, usecols=["iso_parent", "iso_partner", "year", PCOL, TCOL, "is_distributed"], low_memory=False)
ce = pd.read_csv(CBCR_EXCL, usecols=EXCL_COLS, low_memory=False)
print(f"  rows in: {len(ci):,}  out: {len(ce):,}")
chk("row count unchanged", len(ci) == len(ce))
chk("required columns present", all(c in ce.columns for c in EXCL_COLS))
P_excl = pd.to_numeric(ce[PCOL], errors="coerce").fillna(0.0)
T_excl = pd.to_numeric(ce[TCOL], errors="coerce").fillna(0.0)
chk("PCOL untouched", np.allclose(pd.to_numeric(ci[PCOL], errors="coerce").fillna(0), P_excl, atol=1.0))
chk("profit_loss_excl_resource == PCOL - resource_profit_base", np.allclose(ce["profit_loss_excl_resource"], P_excl - ce["resource_profit_base_usd"].fillna(0), atol=1.0))
chk("income_tax_..._excl_resource == TCOL - resource_tax_deduction", np.allclose(ce["income_tax_paid_on_cash_basis_excl_resource"].fillna(0),
    T_excl - ce["resource_tax_deduction_usd"].fillna(0), atol=1.0))
# The tax-side deduction is symmetric with the profit-side branch that won:
# tax_deduction ≥ post (equality when post / rate ≥ equity; strict when equity binds).
# Equity-binding case adds equity × rate ≥ 0 on top of post.
# (The old "deduction >= post" invariant belonged to the external-estimate method; under the
# ETR-gap decomposition the gap-based deduction is routinely below the external post estimate.)
chk("resource_tax_deduction <= reported cash tax where tax > 0 (per-cell cap)",
    (ce["resource_tax_deduction_usd"].fillna(0) <= np.maximum(T_excl, 0) + 1.0).all(),
    f"{(ce['resource_tax_deduction_usd'].fillna(0) > np.maximum(T_excl, 0) + 1.0).sum()} rows above cap")
recomputed_total = ce.groupby(["iso_parent", "year"])["profit_loss_excl_resource"].transform("sum")
chk("total_profit_loss_excl_resource == Σ per (parent,year)", np.allclose(ce["total_profit_loss_excl_resource"], recomputed_total, atol=1.0))
n_dist = (ce["is_distributed"] == 1).sum()
n_rep = (ce["is_distributed"] == 0).sum()
chk("etr_parent_partner_excl_resource is NaN on all distributed rows",
    ce.loc[ce["is_distributed"] == 1, "etr_parent_partner_excl_resource"].isna().all(),
    f"{ce.loc[ce['is_distributed'] == 1, 'etr_parent_partner_excl_resource'].notna().sum()} non-NaN")
n_rep_with_pair = ce.loc[ce["is_distributed"] == 0, "etr_parent_partner_excl_resource"].notna().sum()
chk("etr_parent_partner_excl_resource has values on some reported rows",
    n_rep_with_pair > 0, f"{n_rep_with_pair}/{n_rep} reported rows have a pair ETR")
print(f"  Σ reported profit:                  {b(P_excl.sum())}")
print(f"  Σ resource_profit_base:             {b(ce['resource_profit_base_usd'].fillna(0).sum())}")
print(f"  Σ profit_loss_excl_resource:        {b(ce['profit_loss_excl_resource'].sum())}")
print(f"  Σ post_profit_payments:             {b(ce['post_profit_payments_usd'].fillna(0).sum())}")
print(f"  Σ equity_income:                    {b(ce['equity_income_usd'].fillna(0).sum())}")
print(f"  Σ resource_tax_deduction (post + equity×rate when binding): {b(ce['resource_tax_deduction_usd'].fillna(0).sum())}")
print(f"  Σ income_tax_..._excl:              {b(ce['income_tax_paid_on_cash_basis_excl_resource'].fillna(0).sum())}")

# ───────────────────────── 5. cbcr_main_incl_resource.csv ────────────────────
print("\n=== 5. cbcr_main_incl_resource.csv ===")
INCL_COLS = ["iso_parent", "iso_partner", "year", "is_distributed",
             PCOL, TCOL,
             "pre_profit_payments_usd", "post_profit_payments_usd",
             "equity_income_usd", "actual_resource_contribution_usd",
             "profit_loss_incl_resource",
             "income_tax_paid_on_cash_basis_incl_resource",
             "total_profit_loss_incl_resource",
             "etr_average_excl_resource", "etr_partner_median_excl_resource",
             "etr_partner_p25_excl_resource", "etr_partner_min_excl_resource",
             "etr_parent_partner_excl_resource"]
ck = pd.read_csv(CBCR_INCL, usecols=INCL_COLS, low_memory=False)
print(f"  rows out: {len(ck):,}")
chk("row count unchanged", len(ci) == len(ck))
chk("required columns present", all(c in ck.columns for c in INCL_COLS))
P_incl = pd.to_numeric(ck[PCOL], errors="coerce").fillna(0.0)
T_incl = pd.to_numeric(ck[TCOL], errors="coerce").fillna(0.0)
chk("profit_loss_incl_resource == PCOL + pre_profit_payments", np.allclose(ck["profit_loss_incl_resource"], P_incl + ck["pre_profit_payments_usd"].fillna(0), atol=1.0))
chk("income_tax_..._incl_resource == TCOL + pre_profit_payments", np.allclose(ck["income_tax_paid_on_cash_basis_incl_resource"].fillna(0),
    T_incl + ck["pre_profit_payments_usd"].fillna(0), atol=1.0))
chk("profit_loss_incl_resource >= reported everywhere (pre-profit add-back >= 0)",
    (ck["profit_loss_incl_resource"] >= P_incl - 1e-3).all(),
    f"{(ck['profit_loss_incl_resource'] < P_incl - 1).sum()} rows below")
chk("actual_resource_contribution == pre + post + equity per row",
    np.allclose(ck["actual_resource_contribution_usd"],
                ck["pre_profit_payments_usd"].fillna(0)
                + ck["post_profit_payments_usd"].fillna(0)
                + ck["equity_income_usd"].fillna(0), atol=1.0))
chk("etr_parent_partner_excl_resource is NaN on all distributed rows",
    ck.loc[ck["is_distributed"] == 1, "etr_parent_partner_excl_resource"].isna().all())
# ETRs should match excl_resource file row-for-row (carried over, not recomputed)
ce_etr = ce[["iso_parent", "iso_partner", "year", "etr_average_excl_resource"]]
ck_etr = ck[["iso_parent", "iso_partner", "year", "etr_average_excl_resource"]]
merged_etr = ce_etr.merge(ck_etr, on=["iso_parent", "iso_partner", "year"], suffixes=("_excl", "_incl"))
chk("etr_average_excl_resource identical between excl & incl files",
    merged_etr["etr_average_excl_resource_excl"].equals(merged_etr["etr_average_excl_resource_incl"]))
print(f"  Σ profit_loss_incl_resource:        {b(ck['profit_loss_incl_resource'].sum())}")
print(f"  Σ income_tax_..._incl_resource:     {b(ck['income_tax_paid_on_cash_basis_incl_resource'].fillna(0).sum())}")
print(f"  Σ actual_resource_contribution_usd: {b(ck['actual_resource_contribution_usd'].sum())}")

# ───────────────────────── 6. cbcr_main_excl_resource_floored.csv ────────────
print("\n=== 6. cbcr_main_excl_resource_floored.csv ===")
EXCL_FLOOR_COLS = (
    ["iso_parent", "iso_partner", "year", "is_distributed",
     PCOL, TCOL,
     "resource_profit_base_usd", "resource_tax_deduction_usd",
     "post_profit_payments_usd", "equity_income_usd",
     "pre_profit_payments_usd", "actual_resource_contribution_usd",
     "profit_loss_excl_resource_floored",
     "income_tax_paid_on_cash_basis_excl_resource_floored",
     "total_profit_loss_excl_resource_floored",
     "etr_average_excl_resource", "etr_partner_median_excl_resource",
     "etr_partner_p25_excl_resource", "etr_partner_min_excl_resource",
     "etr_parent_partner_excl_resource"]
    + [f"flex_min_{v}_usd" for v in FLEX_VARIANTS]
    + [f"floor_add_on_{v}_usd" for v in FLEX_VARIANTS]
    + [f"profit_loss_excl_resource_floored_{v}" for v in FLEX_VARIANTS]
    + [f"income_tax_paid_on_cash_basis_excl_resource_floored_{v}" for v in FLEX_VARIANTS]
    + [f"total_profit_loss_excl_resource_floored_{v}" for v in FLEX_VARIANTS]
)
cef = pd.read_csv(CBCR_EXCL_FLOOR, usecols=EXCL_FLOOR_COLS, low_memory=False)
print(f"  rows out: {len(cef):,}")
chk("row count unchanged", len(ci) == len(cef))
chk("required columns present", all(c in cef.columns for c in EXCL_FLOOR_COLS))
P_ef = pd.to_numeric(cef[PCOL], errors="coerce").fillna(0.0)
T_ef = pd.to_numeric(cef[TCOL], errors="coerce").fillna(0.0)
chk("primary alias == cat1 (profit)",
    np.allclose(cef["profit_loss_excl_resource_floored"],
                cef["profit_loss_excl_resource_floored_cat1"], atol=1.0))
chk("primary alias == cat1 (tax)",
    np.allclose(cef["income_tax_paid_on_cash_basis_excl_resource_floored"],
                cef["income_tax_paid_on_cash_basis_excl_resource_floored_cat1"], atol=1.0))
for v in FLEX_VARIANTS:
    p_v = cef[f"profit_loss_excl_resource_floored_{v}"]
    t_v = cef[f"income_tax_paid_on_cash_basis_excl_resource_floored_{v}"]
    addon = cef[f"floor_add_on_{v}_usd"].fillna(0)
    # Profit equals profit_loss_excl_resource (= P - resource_profit_base) − floor_add_on
    profit_excl = P_ef - cef["resource_profit_base_usd"].fillna(0)
    chk(f"profit_loss_excl_resource_floored_{v} == (PCOL - resource_profit_base) - floor_add_on_{v}",
        np.allclose(p_v, profit_excl - addon, atol=1.0))
    # Tax equals income_tax_..._excl_resource (= TCOL - resource_tax_deduction). Floor doesn't touch tax.
    tax_excl = T_ef - cef["resource_tax_deduction_usd"].fillna(0)
    chk(f"income_tax_..._excl_resource_floored_{v} == (TCOL - resource_tax_deduction) [floor leaves tax untouched]",
        np.allclose(t_v.fillna(0), tax_excl, atol=1.0))
    chk(f"profit_loss_excl_resource_floored_{v} <= profit_loss_excl_resource (subtracting floor)",
        (p_v <= profit_excl + 1e-3).all())
    recomputed_t = cef.groupby(["iso_parent", "year"])[f"profit_loss_excl_resource_floored_{v}"].transform("sum")
    chk(f"total_profit_loss_excl_resource_floored_{v} == Σ per (parent,year)",
        np.allclose(cef[f"total_profit_loss_excl_resource_floored_{v}"], recomputed_t, atol=1.0))
chk("etr_parent_partner_excl_resource is NaN on all distributed rows",
    cef.loc[cef["is_distributed"] == 1, "etr_parent_partner_excl_resource"].isna().all())
print(f"  Σ reported profit:                   {b(P_ef.sum())}")
print(f"  Σ profit_loss_excl_resource_floored: {b(cef['profit_loss_excl_resource_floored'].sum())}")
for v in FLEX_VARIANTS:
    p_v = cef[f"profit_loss_excl_resource_floored_{v}"].sum()
    addon = cef[f"floor_add_on_{v}_usd"].sum()
    print(f"  {v}: profit {b(p_v)}, floor_add_on (extra royalty revenue) {b(addon)}")

print(f"\n{'='*60}\nRESULT: {n_fail} FAIL, {n_warn} WARN")
sys.exit(1 if n_fail else 0)
