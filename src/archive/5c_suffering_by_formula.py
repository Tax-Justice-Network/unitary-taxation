# %% [markdown]
# Winners & losers under carve-out + UT, by apportionment formula and income group.
#
# Builds on 5b_carveout_then_ut.py (same carve-out cascade). Runs UT for three
# formulas:
#   SOTJ          50% employees + 50% payroll
#   three-factor  1/3 employees + 1/3 sales + 1/3 assets
#   CCCTB         1/6 employees + 1/3 sales + 1/3 assets + 1/6 payroll
# and two scenarios:
#   A  UT only          — vs current NON-resource CIT only
#   B  carve-out + UT    — vs all current resource revenue + current non-resource CIT
#
# A producing country/year "suffers" when its scenario-B net revenue gain < 0.
#
# NOTE on "non-resource CIT": we deduct the *whole* GRD/EITI resource government
# revenue (`captured_total_usd`) from the CbCR income tax paid in the country —
# not just EITI's CIT line — because for big resource economies the CbCR income
# tax IS mostly resource CIT (Aramco/Equinor/Pemex), already inside GRD's total;
# deducting only EITI's (badly under-counted) CIT line would double-count it.
# Floored at 0.
#
# Reads:  data/final/cbcr_main_with_carveout.csv
# Writes: output/extractive/tables/carveout_then_ut/suffering_countries_by_formula.csv
#         output/extractive/tables/carveout_then_ut/income_group_winners_losers.csv
#         output/extractive/figures/income_group_winners_losers.png  (+ scenario-A panel)
import sys
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import data_final, output_dirs

INP = Path(data_final) / "cbcr_main_with_carveout.csv"
TABLES_DIR, FIG_DIR = output_dirs("extractive")
OUT_DIR = TABLES_DIR / "carveout_then_ut"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROFIT_REPORTED = "profit_loss_before_income_tax_corrected"
MIN_ROYALTY = "expected_royalty_usd"
DED_ALLOC = "captured_deductible_allocated_usd"
CAP_TOTAL = "captured_total_usd"
CAP_DEDUCTIBLE = "captured_deductible_usd"
CAP_CIT = "captured_cit_usd"
CAP_EQUITY = "captured_equity_usd"
RENT_TOTAL = "rent_total_usd"
ALLOC_W = "alloc_weight_usd"
CIT_RATE = "cit"
TAX_PAID = "income_tax_paid_on_cash_basis"
INCOME_GRP = "wb_income_group"

FORMULA_VARS = ["n_employees", "unrelated_party_revenues", "tangible_assets_except_cash", "payroll"]
FORMULAS = {
    "SOTJ (50% emp / 50% payroll)": [0.5, 0.0, 0.0, 0.5],
    "three-factor (emp/sales/assets)": [1/3, 1/3, 1/3, 0.0],
    "CCCTB (1/6 emp, 1/3 sales, 1/3 assets, 1/6 payroll)": [1/6, 1/3, 1/3, 1/6],
}
INCOME_ORDER = ["high_income", "upper_middle_income", "lower_middle_income", "low_income", "investment_hub"]
INCOME_LABEL = {
    "high_income": "High income", "upper_middle_income": "Upper-middle", "lower_middle_income": "Lower-middle",
    "low_income": "Low income", "investment_hub": "Investment hub",
}

print(f"Loading {INP}...")
df = pd.read_csv(INP, low_memory=False)
_ny = df["year"].nunique()

# ── Carve-out cascade (identical to 5b §3) ─────────────────────────────────
_w = df[ALLOC_W].fillna(0.0)
_w_sum = _w.groupby([df["iso_partner"], df["year"]]).transform("sum")
_alloc_share = np.where(_w_sum > 0, _w / _w_sum, 0.0)
# CbCR-attributable fraction of the country's modelled rent (Σ alloc_weight /
# rent, capped at 1) — the complement is non-multinational/invisible domestic
# extraction, in EITI/GRD but with no CbCR profit counterpart → scaled out.
_rent_py = df[RENT_TOTAL].fillna(0.0)
_attr = (_w_sum.div(_rent_py.where(_rent_py > 0))).fillna(0.0).clip(upper=1.0).to_numpy()
cap_total_alloc = df[CAP_TOTAL].fillna(0.0) * _attr * _alloc_share          # CbCR-attributable resource revenue, allocated
rent_alloc = df[RENT_TOTAL].fillna(0.0) * _alloc_share
ded = df[DED_ALLOC].fillna(0.0) * _attr
# "Other" captured revenue (GRD residual, not royalty-like / CIT / equity) is
# treated as already out of pre-tax profit (like expensed royalties) — NOT
# carved out of CbCR profit again.
other_alloc = ((df[CAP_TOTAL].fillna(0.0) - df[CAP_DEDUCTIBLE].fillna(0.0)
                - df[CAP_CIT].fillna(0.0) - df[CAP_EQUITY].fillna(0.0)).clip(lower=0.0)) * _attr * _alloc_share
already_out = ded + other_alloc
min_roy = df[MIN_ROYALTY].fillna(0.0)  # already CbCR-attributable (scaled in script 4)
P = pd.to_numeric(df[PROFIT_REPORTED], errors="coerce").fillna(0.0).clip(lower=0.0)
# No rent cap: capture = max(modelled minimum royalty, actual capture).
capture_alloc = np.maximum(min_roy, cap_total_alloc)
carveout_from_profit = np.minimum((capture_alloc - already_out).clip(lower=0.0), P)
df["profit_before_carveout"] = P                                   # UT-only base
df["profit_for_ut"] = (P - carveout_from_profit).clip(lower=0.0)   # carve-out + UT base
df["capture_allocated_usd"] = capture_alloc
df["captured_total_attr_usd"] = cap_total_alloc
df["cbcr_attributable_fraction"] = _attr
df["cit_rate"] = pd.to_numeric(df[CIT_RATE], errors="coerce").fillna(0.0)
df["tax_paid"] = pd.to_numeric(df[TAX_PAID], errors="coerce").fillna(0.0).clip(lower=0.0)

# ── partner-year scalars: resource revenue & income group ──
# "Current resource revenue" = the CbCR-attributable part of GRD/EITI capture;
# captured_cit_full = the raw EITI/GRD resource CIT, used as a floor on how much
# of CbCR income tax in the country is resource CIT (don't bucket oil-major
# resource CIT as non-resource CIT when attributable resource revenue is thin).
cap_py = (df.groupby(["iso_partner", "year"], as_index=False)
          .agg(resource_rev_total=("captured_total_attr_usd", "sum"),
               cbcr_attr_frac=("cbcr_attributable_fraction", "first")))
_cit_full = (df[["iso_partner", "year", CAP_CIT]].drop_duplicates(["iso_partner", "year"])
             .rename(columns={CAP_CIT: "captured_cit_full"}))
_cit_full["captured_cit_full"] = pd.to_numeric(_cit_full["captured_cit_full"], errors="coerce").fillna(0.0)
cap_py = cap_py.merge(_cit_full, on=["iso_partner", "year"], how="left")
cap_py["captured_cit_full"] = cap_py["captured_cit_full"].fillna(0.0)
_raw_rev = pd.to_numeric(df[["iso_partner", "year", CAP_TOTAL]].drop_duplicates(["iso_partner", "year"])[CAP_TOTAL],
                         errors="coerce").fillna(0.0).sum()
_attr_rev = df["captured_total_attr_usd"].sum()
print(f"Resource revenue: ${_raw_rev/1e9:,.0f}B raw (GRD/EITI) → ${_attr_rev/1e9:,.0f}B CbCR-attributable; "
      f"${(_raw_rev-_attr_rev)/1e9:,.0f}B (${(_raw_rev-_attr_rev)/1e9/_ny:,.0f}B/yr) non-multinational/domestic, out of scope")
ig_map = (df[["iso_partner", INCOME_GRP]].dropna().drop_duplicates("iso_partner")
          .set_index("iso_partner")[INCOME_GRP])


def ut_theoretical(d, profit_var, weights):
    activity = pd.Series(0.0, index=d.index)
    for var, wgt in zip(FORMULA_VARS, weights):
        if wgt <= 0 or var not in d.columns:
            continue
        v = pd.to_numeric(d[var], errors="coerce").fillna(0.0).clip(lower=0.0)
        tot = v.groupby(d["iso_parent"]).transform("sum")
        activity = activity + np.where(tot > 0, v / tot, 0.0) * wgt
    tot_act = activity.groupby(d["iso_parent"]).transform("sum")
    share = np.where(tot_act > 0, activity / tot_act, 0.0)
    return pd.Series(share * d.groupby("iso_parent")[profit_var].transform("sum"), index=d.index)


per_cy = []   # per country-year, per formula
for fname, weights in FORMULAS.items():
    theo_only = ut_theoretical(df, "profit_before_carveout", weights)
    theo_b = ut_theoretical(df, "profit_for_ut", weights)
    w = df[["iso_partner", "year"]].copy()
    w["min_roy"] = min_roy.to_numpy()
    w["capture_routable"] = df["capture_allocated_usd"].to_numpy()
    w["ut_only_cit_take"] = (df["cit_rate"] * theo_only.clip(lower=0.0)).to_numpy()
    w["ut_ext_cit_take"] = (df["cit_rate"] * theo_b.clip(lower=0.0)).to_numpy()
    w["tax_paid"] = df["tax_paid"].to_numpy()
    g = w.groupby(["iso_partner", "year"], as_index=False).agg(
        min_royalty_total=("min_roy", "sum"), capture_routable=("capture_routable", "sum"),
        ut_only_cit_take=("ut_only_cit_take", "sum"),
        ut_ext_cit_take=("ut_ext_cit_take", "sum"), cit_paid_cbcr_in_country=("tax_paid", "sum"),
    ).merge(cap_py, on=["iso_partner", "year"], how="left")
    g["resource_rev_total"] = g["resource_rev_total"].fillna(0.0)
    g["captured_cit_full"] = g["captured_cit_full"].fillna(0.0)
    g["cbcr_attr_frac"] = g["cbcr_attr_frac"].fillna(0.0)
    g["cit_paid_non_resource"] = (
        g["cit_paid_cbcr_in_country"] - np.maximum(g["resource_rev_total"], g["captured_cit_full"])
    ).clip(lower=0.0)
    # Fully-out-of-scope resource economies (no CbCR footprint for their resource
    # sector): the CbCR income tax there is overwhelmingly the out-of-scope
    # resource sector — don't count it as non-resource CIT either.
    g.loc[g["cbcr_attr_frac"] <= 0.01, "cit_paid_non_resource"] = 0.0
    # Resource take = larger of current take and modelled minimum royalty
    # (a country-year quantity — no row allocation needed). Never below current.
    g["resource_take_B"] = np.maximum(g["resource_rev_total"], g["min_royalty_total"])
    g["ut_only_net_gain"] = g["ut_only_cit_take"] - g["cit_paid_non_resource"]
    g["ut_ext_net_gain"] = (g["resource_take_B"] + g["ut_ext_cit_take"]) - (g["resource_rev_total"] + g["cit_paid_non_resource"])
    g["formula"] = fname
    g["income_group"] = g["iso_partner"].map(ig_map)
    per_cy.append(g)

allf = pd.concat(per_cy, ignore_index=True)

# ── (1) Suffering country-years (scenario B net gain < 0) ──────────────────
suffer = allf[allf["ut_ext_net_gain"] < -1e6].sort_values(["formula", "ut_ext_net_gain"]).copy()
out_cols = ["formula", "iso_partner", "year", "income_group", "ut_ext_net_gain", "resource_take_B",
            "min_royalty_total", "ut_ext_cit_take", "resource_rev_total", "cit_paid_non_resource",
            "cit_paid_cbcr_in_country"]
suffer_M = suffer[out_cols].copy()
for c in out_cols:
    if c not in ("formula", "iso_partner", "year", "income_group"):
        suffer_M[c] = (suffer_M[c] / 1e6).round(1)
SUF_OUT = OUT_DIR / "suffering_countries_by_formula.csv"
suffer_M.to_csv(SUF_OUT, index=False)
print(f"Wrote {SUF_OUT}")
for fname in FORMULAS:
    sub = suffer[suffer["formula"] == fname]
    byc = (sub.groupby("iso_partner")["ut_ext_net_gain"].agg(["count", "sum"]).sort_values("sum")
           / [1, 1e6]).round(1).reset_index()
    byc.columns = ["iso_partner", "n_losing_years", "total_loss_$M"]
    print(f"\n=== {fname}: {len(sub)} losing country-years; top losers (Σ over losing years, $M) ===")
    print(byc.head(25).to_string(index=False))

# ── (2) Income-group winners & losers ─────────────────────────────────────
ig = (allf.dropna(subset=["income_group"])
      .groupby(["formula", "income_group"], as_index=False)
      .agg(capture_routable=("capture_routable", "sum"), resource_take_B=("resource_take_B", "sum"),
           min_royalty_total=("min_royalty_total", "sum"),
           ut_only_cit_take=("ut_only_cit_take", "sum"),
           ut_ext_cit_take=("ut_ext_cit_take", "sum"), resource_rev_total=("resource_rev_total", "sum"),
           cit_paid_non_resource=("cit_paid_non_resource", "sum"),
           ut_only_net_gain=("ut_only_net_gain", "sum"), ut_ext_net_gain=("ut_ext_net_gain", "sum"),
           n_country_years_losing_B=("ut_ext_net_gain", lambda s: int((s < -1e6).sum())),
           n_country_years=("ut_ext_net_gain", "size")))
for c in ["capture_routable", "resource_take_B", "min_royalty_total", "ut_only_cit_take", "ut_ext_cit_take",
          "resource_rev_total", "cit_paid_non_resource", "ut_only_net_gain", "ut_ext_net_gain"]:
    ig[c + "_per_yr_Bn"] = (ig[c] / 1e9 / _ny).round(2)
IG_OUT = OUT_DIR / "income_group_winners_losers.csv"
ig.to_csv(IG_OUT, index=False)
print(f"\nWrote {IG_OUT}")
print("\n=== Net revenue change by income group ($B/yr) ===")
piv = (ig.assign(igl=ig["income_group"].map(INCOME_LABEL))
       .pivot(index="igl", columns="formula", values="ut_ext_net_gain_per_yr_Bn")
       .reindex([INCOME_LABEL[k] for k in INCOME_ORDER]))
print("Scenario B (carve-out + UT):")
print(piv.to_string())
pivA = (ig.assign(igl=ig["income_group"].map(INCOME_LABEL))
        .pivot(index="igl", columns="formula", values="ut_only_net_gain_per_yr_Bn")
        .reindex([INCOME_LABEL[k] for k in INCOME_ORDER]))
print("Scenario A (UT only):")
print(pivA.to_string())

# ── (3) Figure: grouped bars, income group × formula, two scenarios ───────
FIG_DIR.mkdir(parents=True, exist_ok=True)
fnames = list(FORMULAS.keys())
short = {fnames[0]: "SOTJ", fnames[1]: "three-factor", fnames[2]: "CCCTB"}
groups = [g for g in INCOME_ORDER if g in set(ig["income_group"])]
x = np.arange(len(groups))
width = 0.26
colors = ["#1b9e77", "#7570b3", "#d95f02"]

fig, axes = plt.subplots(1, 2, figsize=(15, 6), sharey=True)
for ax, scen, col in zip(axes, ["A — UT only", "B — carve-out + UT"], ["ut_only_net_gain_per_yr_Bn", "ut_ext_net_gain_per_yr_Bn"]):
    for i, fn in enumerate(fnames):
        sub = ig[ig["formula"] == fn].set_index("income_group").reindex(groups)
        vals = sub[col].fillna(0.0).to_numpy()
        ax.bar(x + (i - 1) * width, vals, width, label=short[fn], color=colors[i])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([INCOME_LABEL[g] for g in groups], rotation=20, ha="right")
    ax.set_title(f"Scenario {scen}")
    ax.set_ylabel("Net government-revenue change, $bn / yr (2016-2022 avg)")
    ax.grid(axis="y", alpha=0.3)
axes[0].legend(title="Apportionment formula", loc="best")
fig.suptitle("Winners & losers by World Bank income group — extractive carve-out + unitary taxation", fontsize=13)
fig.tight_layout(rect=[0, 0, 1, 0.96])
FIG_OUT = FIG_DIR / "income_group_winners_losers.png"
fig.savefig(FIG_OUT, dpi=150)
print(f"\nWrote {FIG_OUT}")

# Second figure: scenario B decomposition per income group (stacked: capture vs formulary CIT vs −baseline)
fig2, ax2 = plt.subplots(figsize=(13, 6.5))
gw = 0.8 / len(fnames)
for i, fn in enumerate(fnames):
    sub = ig[ig["formula"] == fn].set_index("income_group").reindex(groups)
    cap = (sub["resource_take_B"] / 1e9 / _ny).fillna(0).to_numpy()
    cit = (sub["ut_ext_cit_take"] / 1e9 / _ny).fillna(0).to_numpy()
    base = -((sub["resource_rev_total"] + sub["cit_paid_non_resource"]) / 1e9 / _ny).fillna(0).to_numpy()
    net = (sub["ut_ext_net_gain"] / 1e9 / _ny).fillna(0).to_numpy()
    xpos = x + (i - (len(fnames) - 1) / 2) * gw
    ax2.bar(xpos, cap, gw, color="#66c2a5", label="resource take (`capture`)" if i == 0 else None)
    ax2.bar(xpos, cit, gw, bottom=cap, color="#8da0cb", label="formulary CIT on residual" if i == 0 else None)
    ax2.bar(xpos, base, gw, color="#fc8d62", label="− current (resource rev + non-resource CIT)" if i == 0 else None)
    ax2.scatter(xpos, net, color="black", zorder=5, s=18, label="= net change" if i == 0 else None)
ax2.axhline(0, color="black", lw=0.8)
ax2.set_xticks(x)
ax2.set_xticklabels([f"{INCOME_LABEL[g]}\n(bars: SOTJ / 3-factor / CCCTB)" for g in groups])
ax2.set_ylabel("$bn / yr (2016-2022 avg)")
ax2.set_title("Scenario B decomposition by income group — carve-out + UT vs status quo")
ax2.legend(loc="best")
ax2.grid(axis="y", alpha=0.3)
fig2.tight_layout()
FIG2_OUT = FIG_DIR / "income_group_scenarioB_decomposition.png"
fig2.savefig(FIG2_OUT, dpi=150)
print(f"Wrote {FIG2_OUT}")
