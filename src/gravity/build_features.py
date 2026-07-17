# %% [markdown]
# Assemble the (reporter=parent, partner, year) feature matrix for the
# García-Bernardo & Janský (2024) gravity/ML imputation. Targets are the
# CbCR-reported employees / unrelated-party sales / tangible assets (observed on
# good-reporter foreign cells); features come from the cached gravity sources.
#
# First pass: CEPII gravity (incl. trade flows) + World Bank unilateral (both
# sides) + WGI governance PCA (both sides) + IMF CDIS FDI + CPIS portfolio
# (bilateral, both directions). BIS banking claims and the in-repo unilaterals
# (GRD/FSI/CTHI/ILO/WHO/CIT/Orbis) are a documented second pass.

# %%
import glob
import os

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

from _ifs_iso3 import IFS_TO_ISO3

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "data", "raw", "gravity")
OUT = os.path.join(ROOT, "data", "intermediate", "gravity")
os.makedirs(OUT, exist_ok=True)
YEARS = list(range(2014, 2023))

# %%
# 1. CbCR targets — reported foreign country cells. Read from the
# "Total (All sub-groups)" subset (cbcr_main_allsubgroupsonly.csv, the same
# grouping the disaggregation uses); cbcr_main.csv carries three grouping rows
# per cell (Total / positive / negative subgroups) which must NOT be summed.
cb = pd.read_csv(
    os.path.join(ROOT, "data", "final", "cbcr_main_allsubgroupsonly.csv"),
    usecols=["iso_parent", "iso_partner", "year", "n_employees",
             "unrelated_party_revenues", "tangible_assets_except_cash"],
)
AGG = {"W", "A", "E", "F", "S", "WXD", "A_O", "E_O", "F_O", "S_O", "W_O", "X"}
cb = cb[~cb["iso_partner"].isin(AGG) & ~cb["iso_parent"].isin(AGG)]
cb = cb[cb["iso_parent"] != cb["iso_partner"]]
for c in ["n_employees", "unrelated_party_revenues", "tangible_assets_except_cash"]:
    cb[c] = pd.to_numeric(cb[c], errors="coerce")
cb = cb.groupby(["iso_parent", "iso_partner", "year"], as_index=False).sum(min_count=1)
print(f"CbCR target cells: {len(cb)}")

# %%
# 2. CEPII gravity backbone (o=parent, d=partner), year>=2014.
GRAV_BI = ["distw_harmonic", "dist", "contig", "comlang_off", "comlang_ethno",
           "comcol", "comrelig", "col45", "comleg_pretrans", "comleg_posttrans",
           "fta_wto", "tradeflow_comtrade_o", "tradeflow_comtrade_d",
           "tradeflow_baci", "tradeflow_imf_o", "tradeflow_imf_d"]
GRAV_UNI = ["gdp_o", "gdp_d", "gdpcap_o", "gdpcap_d", "pop_o", "pop_d",
            "heg_o", "heg_d", "gatt_o", "gatt_d", "wto_o", "wto_d",
            "entry_cost_o", "entry_cost_d", "entry_proc_o", "entry_proc_d"]
usec = ["year", "iso3_o", "iso3_d"] + GRAV_BI + GRAV_UNI
g = pd.read_csv(os.path.join(RAW, "Gravity_V202211.csv"), usecols=usec)
g = g[g["year"] >= 2014].rename(columns={"iso3_o": "iso_parent", "iso3_d": "iso_partner"})
g = g.drop_duplicates(["iso_parent", "iso_partner", "year"])
print(f"CEPII gravity pairs (>=2014): {len(g)}")

# %%
# 3. World Bank unilateral indicators -> wide (iso3, year, <ind>), merge o & d.
wb_files = glob.glob(os.path.join(RAW, "wb_*.csv"))
wb_wide = None
for f in wb_files:
    code = os.path.basename(f)[3:-4]
    d = pd.read_csv(f).rename(columns={"value": f"wb_{code}"})
    d = d[["iso3", "year", f"wb_{code}"]]
    d = d.drop_duplicates(["iso3", "year"])
    wb_wide = d if wb_wide is None else wb_wide.merge(d, on=["iso3", "year"], how="outer")
wb_wide = wb_wide.drop_duplicates(["iso3", "year"])
print(f"WB indicators merged: {wb_wide.shape[1]-2} cols, {len(wb_wide)} rows")

# %%
# 4. WGI -> PCA(1) governance per (iso3, year).
wgi_parts = []
for f in glob.glob(os.path.join(RAW, "wgi_*.csv")):
    dim = os.path.basename(f)[4:-4]
    d = pd.read_csv(f)
    cols = {c.lower(): c for c in d.columns}
    iso = cols.get("ref_area") or cols.get("iso3") or list(d.columns)[0]
    d = d.rename(columns={iso: "iso3", "TIME_PERIOD": "year", "OBS_VALUE": dim})
    wgi_parts.append(d[["iso3", "year", dim]])
wgi = wgi_parts[0]
for p in wgi_parts[1:]:
    wgi = wgi.merge(p, on=["iso3", "year"], how="outer")
dims = [c for c in wgi.columns if c not in ("iso3", "year")]
wgi[dims] = wgi[dims].apply(pd.to_numeric, errors="coerce")
complete = wgi.dropna(subset=dims)
pca = PCA(n_components=1).fit(complete[dims])
wgi.loc[complete.index, "governance"] = pca.transform(complete[dims])[:, 0]
wgi = wgi[["iso3", "year", "governance"]].drop_duplicates(["iso3", "year"])
print(f"WGI governance PCA: explained var {pca.explained_variance_ratio_[0]:.2f}")

# %%
# 5. IMF CDIS FDI (bilateral). inward[REF<-CP]. Map IFS counterpart -> ISO3.
def _load_bilateral(fname):
    d = pd.read_csv(os.path.join(RAW, fname))
    d["cp_ifs"] = d["COMP_BREAKDOWN_1"].str.extract(r"(\d+)").astype(float)
    d["cp_iso"] = d["cp_ifs"].map(IFS_TO_ISO3)
    n_un = d["cp_iso"].isna().mean()
    d = d.dropna(subset=["cp_iso"])
    d = d.rename(columns={"REF_AREA": "ref_iso", "TIME_PERIOD": "year"})
    d["val"] = pd.to_numeric(d["OBS_VALUE"], errors="coerce")
    # Dedup to one value per (ref, cp, year): the data carries several internal
    # breakdown rows per pair-year; keep the largest-magnitude (= the total).
    d["_abs"] = d["val"].abs()
    d = d.sort_values("_abs").drop_duplicates(["ref_iso", "cp_iso", "year"], keep="last")
    return d[["ref_iso", "cp_iso", "year", "val"]], n_un

cdis, n_un = _load_bilateral("imf_cdis_inward.csv")
print(f"CDIS: {len(cdis)} rows, {n_un:.1%} counterpart codes unmapped")
# FDI origin->dest = parent invests in partner = partner inward from parent
fdi_od = cdis.rename(columns={"ref_iso": "iso_partner", "cp_iso": "iso_parent",
                              "val": "fdi_origin_to_dest"})
fdi_do = cdis.rename(columns={"ref_iso": "iso_parent", "cp_iso": "iso_partner",
                              "val": "fdi_dest_to_origin"})

cpis, n_unc = _load_bilateral("imf_cpis_assets.csv")
print(f"CPIS: {len(cpis)} rows, {n_unc:.1%} counterpart codes unmapped")
porti_od = cpis.rename(columns={"ref_iso": "iso_partner", "cp_iso": "iso_parent",
                                "val": "porti_origin_to_dest"})
porti_do = cpis.rename(columns={"ref_iso": "iso_parent", "cp_iso": "iso_partner",
                                "val": "porti_dest_to_origin"})

# %%
# 5b. In-repo unilaterals: cleaned country-macro from cbcr_main (cit, wage,
# health, tax revenue) + FSI secrecy score (mean of the 20 KFSI indicators).
cm = pd.read_csv(os.path.join(ROOT, "data", "final", "cbcr_main.csv"),
                 usecols=["iso_partner", "year", "cit", "wage_monthly",
                          "gvt_health_expenditure", "tax_revenue_pct_gdp"])
cm = cm.rename(columns={"iso_partner": "iso3"}).groupby(["iso3", "year"], as_index=False).first()
fsi = pd.read_csv(os.path.join(ROOT, "data", "raw", "portal_fsi_results.csv"))
si = [c for c in fsi.columns if c.startswith("fsi_indicator_si")]
fsi["fsi_secrecy_score"] = fsi[si].apply(pd.to_numeric, errors="coerce").mean(axis=1)
repo_uni = cm.merge(fsi[["iso3", "year", "fsi_secrecy_score"]], on=["iso3", "year"], how="outer")
repo_uni = repo_uni.drop_duplicates(["iso3", "year"])
print(f"In-repo unilaterals: {repo_uni.shape[1]-2} cols")

# 5c. BIS LBS bilateral cross-border claims & liabilities (amounts outstanding,
# all instruments). Annual = Q4. Reporting/counterparty codes are ISO2 -> ISO3.
import pycountry
try:
    ycols = [f"{y}-Q4" for y in YEARS]
    bcols = ["Measure", "Type of instruments", "Position type",
             "Balance sheet position", "L_REP_CTY", "L_CP_COUNTRY"]
    bis = pd.read_csv(os.path.join(RAW, "WS_LBS_D_PUB_csv_col.csv"),
                      usecols=bcols + ycols, low_memory=False)
    bis = bis[(bis["Measure"] == "Amounts outstanding / Stocks")
              & (bis["Type of instruments"] == "All instruments")
              & (bis["Position type"] == "Cross-border")
              & (bis["Balance sheet position"].isin(["Total claims", "Total liabilities"]))]
    i2 = {c.alpha_2: c.alpha_3 for c in pycountry.countries}
    bis["o"] = bis["L_REP_CTY"].map(i2)
    bis["d"] = bis["L_CP_COUNTRY"].map(i2)
    bis = bis.dropna(subset=["o", "d"])
    bl = bis.melt(id_vars=["o", "d", "Balance sheet position"], value_vars=ycols,
                  var_name="yq", value_name="val")
    bl["year"] = bl["yq"].str[:4].astype(int)
    bl["val"] = pd.to_numeric(bl["val"], errors="coerce")
    bl = bl.dropna(subset=["val"])
    claims = (bl[bl["Balance sheet position"] == "Total claims"]
              .groupby(["o", "d", "year"], as_index=False)["val"].sum()
              .rename(columns={"o": "iso_parent", "d": "iso_partner", "val": "bis_claims"}))
    liab = (bl[bl["Balance sheet position"] == "Total liabilities"]
            .groupby(["o", "d", "year"], as_index=False)["val"].sum()
            .rename(columns={"o": "iso_parent", "d": "iso_partner", "val": "bis_liabilities"}))
    print(f"BIS bilateral: {len(claims)} claims, {len(liab)} liability cells")
except Exception as e:
    claims = liab = None
    print(f"BIS parse skipped: {type(e).__name__}: {str(e)[:70]}")

# %%
# 6. Assemble. Backbone = union of CEPII pairs and CbCR cells.
m = g.copy()
repo_val_cols = [c for c in repo_uni.columns if c not in ("iso3", "year")]
for side, key in [("_o", "iso_parent"), ("_d", "iso_partner")]:
    w = wb_wide.rename(columns={"iso3": key, **{c: c + side for c in wb_wide.columns if c.startswith("wb_")}})
    m = m.merge(w, on=[key, "year"], how="left")
    gov = wgi.rename(columns={"iso3": key, "governance": "governance" + side})
    m = m.merge(gov, on=[key, "year"], how="left")
    ru = repo_uni.rename(columns={"iso3": key, **{c: c + side for c in repo_val_cols}})
    m = m.merge(ru, on=[key, "year"], how="left")
if claims is not None:
    m = m.merge(claims, on=["iso_parent", "iso_partner", "year"], how="left")
    m = m.merge(liab, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(fdi_od, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(fdi_do, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(porti_od, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(porti_do, on=["iso_parent", "iso_partner", "year"], how="left")
m = m.merge(cb, on=["iso_parent", "iso_partner", "year"], how="outer")

# %%
# 6b. Carry feature coverage forward into sparsely-covered latest year(s).
# The CEPII gravity backbone (Gravity_V202211) barely covers 2022 (released
# Nov 2022), so the 2022 prediction grid collapses (~2.7k pairs vs ~59k in 2021).
# Without this, 2_disaggregate finds no gravity prediction for most 2022 pairs and
# falls back to the deterministic uniform split → 2022 gets no gravity imputation
# and therefore no bootstrap variation. We carry the latest dense year's FEATURES
# forward into the sparse year for every pair missing it, so the model predicts
# 2022 like any other year. The CbCR TARGET columns are deliberately NOT carried
# (only genuinely-observed 2022 cells train the model — no fabricated labels).
TARGET_COLS = ["n_employees", "unrelated_party_revenues", "tangible_assets_except_cash"]
SRC_YEAR, CARRY_TO = 2021, 2022
_cnt = m.groupby("year").size()
if _cnt.get(CARRY_TO, 0) < 0.5 * _cnt.get(SRC_YEAR, 1):
    _have = set(map(tuple, m.loc[m["year"] == CARRY_TO,
                                 ["iso_parent", "iso_partner"]].to_numpy()))
    _src = m[m["year"] == SRC_YEAR].copy()
    _src = _src[[t not in _have for t in
                 map(tuple, _src[["iso_parent", "iso_partner"]].to_numpy())]]
    _src["year"] = CARRY_TO
    _src[TARGET_COLS] = np.nan          # carry features only, never labels
    m = pd.concat([m, _src], ignore_index=True)
    print(f"Carried {len(_src)} pairs forward {SRC_YEAR}->{CARRY_TO} "
          f"(sparse CEPII {CARRY_TO} coverage: {_cnt.get(CARRY_TO, 0)} -> "
          f"{int(m.groupby('year').size().get(CARRY_TO))} rows).")

# %%
# 7. Log-transform skewed level variables (keep dummies as-is).
LOG_VARS = (["tradeflow_comtrade_o", "tradeflow_comtrade_d", "tradeflow_baci",
             "tradeflow_imf_o", "tradeflow_imf_d", "distw_harmonic", "dist",
             "fdi_origin_to_dest", "fdi_dest_to_origin",
             "porti_origin_to_dest", "porti_dest_to_origin",
             "gdp_o", "gdp_d", "gdpcap_o", "gdpcap_d", "pop_o", "pop_d",
             "entry_cost_o", "entry_cost_d", "n_employees",
             "unrelated_party_revenues", "tangible_assets_except_cash",
             "bis_claims", "bis_liabilities",
             "wage_monthly_o", "wage_monthly_d",
             "gvt_health_expenditure_o", "gvt_health_expenditure_d",
             "tax_revenue_pct_gdp_o", "tax_revenue_pct_gdp_d"]
            + [c for c in m.columns if c.startswith("wb_")])
for v in LOG_VARS:
    if v in m.columns:
        m["ln_" + v] = np.log(pd.to_numeric(m[v], errors="coerce").clip(lower=0) + 1)

out = os.path.join(OUT, "gravity_feature_matrix.parquet")
try:
    m.to_parquet(out, index=False)
except Exception:
    out = out.replace(".parquet", ".csv")
    m.to_csv(out, index=False)
n_train = m["n_employees"].notna().sum()
print(f"\nFeature matrix: {m.shape[0]} rows x {m.shape[1]} cols")
print(f"  rows with CbCR target (training): {n_train}")
print(f"  saved -> data/intermediate/gravity/{os.path.basename(out)}")
