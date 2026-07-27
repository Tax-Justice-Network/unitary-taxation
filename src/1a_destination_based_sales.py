# %%
"""
1a — Destination-based sales: the market-side sales allocation key.

Builds, per market jurisdiction and year, the destination-based measures of
multinationals' sales used as the sales factor in the apportionment formulas.
The output is merged into the disaggregated CbCR dataset in script 2, *after*
disaggregation, because that step introduces partner jurisdictions that do not
exist after script 1 and destination-based sales are a property of the market
jurisdiction.

HEADLINE MEASURE (Part 1; formula tag `destmnedds` — the paper's preferred
sales measure): destination-based sales of multinationals in a market =
  (i)  LOCAL SALES of MNE entities across ALL sectors — turnover minus exports
       of foreign-owned (F) and domestic-owned-MNE (D_MNE) entities, from the
       OECD Analytical AMNE database — plus
  (ii) the MNE share of the market's imports of digitally DELIVERABLE services
       (raw OECD-WTO BaTIS; IMF-OECD-UNCTAD-WTO Handbook category set, excluding
       SH charges for the use of intellectual property): services consumed in
       the market but supplied remotely, which never appear as local turnover.
The local-sales proxy (turnover minus exports) follows OECD (2020, "Tax
Challenges Arising from Digitalisation — Economic Impact Assessment", ch. 2).
We deviate in one respect: the OECD restricts the proxy to CONSUMER-FACING
sectors (its Pillar-One scope), whereas our headline measure keeps ALL sectors
— including finance, mining and B2B services — because the destination key
replaces the CbCR unrelated-party-revenues variable, which covers all sectors.

COMPARISON MEASURES (Part 2), the OECD's own narrower constructions, computed
alongside so outcomes can be compared: CFB, consumer-facing business (OECD
para. 92-99) — the same turnover-minus-exports proxy restricted to consumer-
facing sectors; ADS, automated digital services (OECD para. 103-104) —
internet penetration x household consumption (relative terms only).

Coverage: markets not observed in a source are extrapolated by regression (log
GDP, log GDP per capita, log trade openness) with a remittances/aid adjustment;
the 2026 AAMNE edition covers 2008-2023 (missing country-years reuse each
country's own 2019 ratio — 2020 is COVID-distorted); markets with population
< 250k and no data are set to 0. A coverage check guarantees every real CbCR
partner-year carries the headline share and that shares sum to 1 per year.
See docs/destination_based_sales.md.

Pipeline step 1a — after 1 (clean), before 2 (disaggregate).

Reads:
  {data_final}/cbcr_main_allsubgroupsonly.csv               — cleaned CbCR panel, for GDP/population (script 1)
  {data_raw}macro_variables/wb_gdp_current_usd_2026-07.csv   — canonical WB GDP snapshot (fallback fill)
  {data_raw}macro_variables/wb_gdp_population_2026-02.csv     — WB GDP & population (DataBank export, last-resort backfill)
  {data_raw}macro_variables/wb_trade_pct_gdp_2026-06.csv      — WB trade openness (regression covariate)
  {data_raw}macro_variables/wb_remittances_received_2026-06.csv — WB remittances received (coverage adjustment)
  {data_raw}context/wb_oda_received_2026-06.csv               — WB ODA received (coverage adjustment)
  {data_raw}destination_based_sales/wto_dds_imports_2026-06.csv — WTO digitally-delivered services imports (fallback)
  {data_raw}destination_based_sales/oecd_aamne_mne_xvem_2026-07.csv — OECD Analytical AMNE F+D_MNE turnover/exports
  {data_raw}destination_based_sales/oecd_aamne_xvem_2026-06.csv     — OECD Analytical AMNE totals (denominators)
  {data_raw}destination_based_sales/itu_internet_users_2026-06.csv  — ITU internet penetration (ADS proxy)
  {data_raw}destination_based_sales/un_household_consumption_2026-06.csv — UN household consumption (ADS proxy)
  {data_raw}macro_variables/wb_fx_official_rate_2026-02.csv   — WB official exchange rates

Writes:
  {data_intermediate}/destination_based_sales.csv           — per (iso_partner, year) shares: mne_plus_dds_share (headline), cfb_share, ads_share, …

Usage:
  python 1a_destination_based_sales.py

Author: Alison Schultz (based on Javier Garcia-Bernardo's work).
Last updated: 2026-07-25.
"""

# %%
from pathlib import Path

import os
import numpy as np
import pandas as pd
import pycountry

from config import *

analysis_years = list(range(first_year, first_year + n_years))
year_str = [str(y) for y in analysis_years]
formatted_years = [f"{y} [YR{y}]" for y in analysis_years]

# %% [markdown] MARK: Part 1. Shared inputs
# Part 0. Shared inputs: the (market x year) macro frame — GDP, population,
# trade openness, remittances, aid — plus the WTO digitally-delivered services
# imports (reference series; also the loud fallback when the BaTIS download is
# absent). Everything downstream (headline and comparison measures alike)
# draws on this frame.
# %% MARK: 1.1 GDP and population from script 1's filled…
# 0.1 GDP and population from script 1's filled output (inherits the manual
# fills for havens / territories that the raw World Bank file misses).
g1 = pd.read_csv(
    f"{data_final}/cbcr_main_allsubgroupsonly.csv",
    usecols=["iso_partner", "year", "gdp_current_usd", "population"],
)
g1 = g1.drop_duplicates(["iso_partner", "year"])
macro = g1.rename(columns={"iso_partner": "iso", "gdp_current_usd": "gdp"})
macro["gdp"] = pd.to_numeric(macro["gdp"], errors="coerce")
macro["population"] = pd.to_numeric(macro["population"], errors="coerce")

# 0.1.1 FULL (iso × year) grid. The output must cover EVERY partner in EVERY
# analysis year: building the table only from observed partner-years would
# silently drop markets from the years they don't appear in the reporting
# sample (e.g. Burundi appears in just 1 of 7 years), NaN-poisoning those
# cells — and with them the whole row's activity — in every destination
# formula downstream.
_grid = pd.MultiIndex.from_product(
    [sorted(macro["iso"].unique()), analysis_years], names=["iso", "year"]
).to_frame(index=False)
macro = _grid.merge(macro, on=["iso", "year"], how="left")

# 0.1.2 GDP-snapshot fallback FIRST (config.canonical_gdp_data, the repo-wide
# WB WDI snapshot): fills any grid cell script 1 left NaN, and covers
# countries the DataBank export misses entirely (BHS). Runs BEFORE the
# DataBank backfill so a stale-vintage DataBank GDP (pre-rebasing Nigeria /
# Angola etc.) can never win over the newer snapshot.
_canon = pd.read_csv(canonical_gdp_data, comment="#").rename(
    columns={"iso3": "iso", "gdp_current_usd": "_gdp_canon"}
)
macro = macro.merge(_canon, on=["iso", "year"], how="left")
macro["gdp"] = macro["gdp"].where(macro["gdp"].notna(), macro["_gdp_canon"])
macro = macro.drop(columns=["_gdp_canon"])

# 0.1.3 LAST-RESORT backfill from the (stale-vintage) World Bank DataBank
# file — population primarily (the snapshot file is GDP-only), GDP only
# for cells neither script 1 nor the GDP snapshot covers. NB: this
# left merge can only fill years for countries already on the grid — it
# cannot ADD missing jurisdictions (that is what the grid + canonical
# fallback above are for). Continent/ROW aggregate codes have no
# GDP here and stay missing (correctly excluded from destination sales).
wb_raw = pd.read_csv(gdp_population_data)
wb_raw = wb_raw.dropna(subset=["Country Code"])
wb_raw = wb_raw[["Series Name", "Country Code"] + formatted_years]
wb_long = wb_raw.melt(
    id_vars=["Series Name", "Country Code"], var_name="year_col", value_name="value"
)
wb_long["year"] = wb_long["year_col"].str[:4].astype(int)
wb_long["value"] = pd.to_numeric(
    wb_long["value"].replace("..", np.nan), errors="coerce"
)
wb_wide = wb_long.pivot_table(
    index=["Country Code", "year"], columns="Series Name", values="value"
).reset_index()
wb_wide = wb_wide.rename(
    columns={
        "Country Code": "iso",
        "GDP (current US$)": "gdp_wb",
        "Population total": "pop_wb",
    }
)
macro = macro.merge(
    wb_wide[["iso", "year", "gdp_wb", "pop_wb"]], on=["iso", "year"], how="left"
)
macro["gdp"] = macro["gdp"].where(macro["gdp"].notna(), macro["gdp_wb"])
macro["population"] = macro["population"].where(
    macro["population"].notna(), macro["pop_wb"]
)
macro = macro.drop(columns=["gdp_wb", "pop_wb"])

# 0.1.4 Last-resort within-country fill for grid years no source covers —
# GDP/population are slow-moving, and a one-year gap must not knock a market
# out of the destination key for that year.
macro = macro.sort_values(["iso", "year"]).reset_index(drop=True)
for _c in ("gdp", "population"):
    macro[_c] = macro.groupby("iso")[_c].transform(lambda s: s.ffill().bfill())

# 0.2 Trade openness (WB API CSV "API_*.csv"; metadata in the first 4 rows,
# year columns are plain strings like "2016").
trade_raw = pd.read_csv(trade_openness_data, skiprows=4)
trade_raw = trade_raw[["Country Code"] + year_str]
trade_long = trade_raw.melt(
    id_vars="Country Code", var_name="year", value_name="trade_openness"
)
trade_long["year"] = trade_long["year"].astype(int)
trade_long = trade_long.rename(columns={"Country Code": "iso"})
macro = macro.merge(trade_long, on=["iso", "year"], how="left")

# 0.3 Personal remittances received (WB API CSV, current US$).
remit_raw = pd.read_csv(remittances_data, skiprows=4)
remit_raw = remit_raw[["Country Code"] + year_str]
remit_long = remit_raw.melt(
    id_vars="Country Code", var_name="year", value_name="remittances"
)
remit_long["year"] = remit_long["year"].astype(int)
remit_long = remit_long.rename(columns={"Country Code": "iso"})
macro = macro.merge(remit_long, on=["iso", "year"], how="left")

# 0.4 Net ODA received (WB Databank export, current US$; wide format with year
# columns like "2016 [YR2016]" and ".." missing marker).
oda_raw = pd.read_csv(oda_data)
oda_raw = oda_raw.dropna(subset=["Country Code"])
oda_raw = oda_raw[["Country Code"] + formatted_years]
oda_long = oda_raw.melt(id_vars="Country Code", var_name="year_col", value_name="oda")
oda_long["year"] = oda_long["year_col"].str[:4].astype(int)
oda_long["oda"] = pd.to_numeric(oda_long["oda"].replace("..", np.nan), errors="coerce")
oda_long = oda_long[["Country Code", "year", "oda"]].rename(
    columns={"Country Code": "iso"}
)
macro = macro.merge(oda_long, on=["iso", "year"], how="left")

# 0.5 GDP per capita.
macro["gdp"] = pd.to_numeric(macro["gdp"], errors="coerce")
macro["population"] = pd.to_numeric(macro["population"], errors="coerce")
macro["gdp_per_capita"] = macro["gdp"] / macro["population"]


# 0.6 Log covariates used by all extrapolation regressions below.
macro["ln_gdp"] = np.log(macro["gdp"].where(macro["gdp"] > 0))
macro["ln_gdp_pc"] = np.log(macro["gdp_per_capita"].where(macro["gdp_per_capita"] > 0))
macro["ln_trade"] = np.log(macro["trade_openness"].where(macro["trade_openness"] > 0))

# 0.7 Remittances/aid adjustment (OECD para. 98): consumption in a market is
# financed by GDP + remittances + aid; applied to extrapolated ratios only.
# Missing remittances and aid count as zero.
macro["remittances"] = macro["remittances"].fillna(0)
macro["oda"] = macro["oda"].fillna(0)
macro["aid_adjustment"] = (macro["gdp"] + macro["remittances"] + macro["oda"]) / macro[
    "gdp"
]

# %%
# WTO digitally-delivered services imports (total "DDS", import flow "M") —
# the published cross-border digital-trade reference series. Used (a) as a
# comparison series for the BaTIS deliverable aggregate and (b) as the LOUD
# fallback for the headline DDS leg when the BaTIS bulk file is absent.
# 0.8 Remote digital value = WTO digitally-delivered services imports (total
# "DDS", import flow "M"), reporter ISO2 -> ISO3, million USD -> USD.
ddt = pd.read_csv(ddt_data, low_memory=False)
ddt = ddt[(ddt["FLOW"] == "M") & (ddt["INDICATOR"] == "DDS")]
ddt = ddt[["REPORTER_CODE", "YEAR", "VALUE"]].copy()
ddt["year"] = pd.to_numeric(ddt["YEAR"], errors="coerce")
ddt["digital_imports_usd"] = pd.to_numeric(ddt["VALUE"], errors="coerce") * 1e6
ddt = ddt[ddt["year"].isin(analysis_years)]

iso2_to_iso3 = {}
for code in ddt["REPORTER_CODE"].dropna().unique():
    c = pycountry.countries.get(alpha_2=code)
    if c is not None:
        iso2_to_iso3[code] = c.alpha_3
ddt["iso"] = ddt["REPORTER_CODE"].map(iso2_to_iso3)
ddt = ddt.dropna(subset=["iso"])
ddt = ddt.groupby(["iso", "year"], as_index=False)["digital_imports_usd"].sum()
macro = macro.merge(ddt, on=["iso", "year"], how="left")

# 0.9 Extrapolate remote digital imports on log(GDP) for full market coverage.
dreg = macro[(macro["digital_imports_usd"] > 0) & (macro["gdp"] > 0)].copy()
dreg["ln_di"] = np.log(dreg["digital_imports_usd"])
dreg["ln_gdp"] = np.log(dreg["gdp"])
Xd = np.column_stack([np.ones(len(dreg)), dreg["ln_gdp"]])
dbeta, _, _, _ = np.linalg.lstsq(Xd, dreg["ln_di"].values, rcond=None)
macro["digital_imports_pred"] = np.exp(dbeta[0] + dbeta[1] * macro["ln_gdp"])
macro["digital_imports_filled"] = macro["digital_imports_usd"].where(
    macro["digital_imports_usd"].notna(), macro["digital_imports_pred"]
)
macro["digital_imports0"] = macro["digital_imports_filled"].fillna(0)

# %% [markdown] MARK: Part 2. Headline destination-based sales
# Part 1. Headline destination-based sales (`destmnedds`): all-sector MNE
# local sales + the MNE share of BaTIS digitally-deliverable services imports
# (ex-IP). This is the sales measure of the paper's preferred formula.

# %% [markdown] MARK: 2.1 All-sector MNE local sales
# 1.1 All-sector MNE local sales (AAMNE).
# Turnover minus exports of F + D_MNE entities over ALL AAMNE ISIC sections —
# including finance (K64T66), mining and B2B services — matching the scope of
# the CbCR unrelated-party-revenues variable this key replaces in the
# apportionment formulas (the OECD restricts to consumer-facing sectors; the
# CFB comparison measure in Part 2 reproduces that choice).
# %%
# 1.1.1 All-sector MNE sales level (turnover - exports) and observed
# ratio to GDP.
if Path(aamne_dmne_data).exists():
    a2 = pd.read_csv(aamne_dmne_data)
    a2 = a2[a2["year"].isin(analysis_years)]
    a2 = a2[a2["cou"] != "ROW"]
    a2 = a2[a2["own"].isin(["F", "D_MNE"])]
    a2["GO"] = pd.to_numeric(a2["GO"], errors="coerce")
    a2["EXGR"] = pd.to_numeric(a2["EXGR"], errors="coerce")
    a2["db_sales"] = a2["GO"] - a2["EXGR"]
    mne_wide = a2.groupby(["cou", "year"], as_index=False)["db_sales"].sum()
    mne_wide = mne_wide.rename(columns={"db_sales": "mne_sales_musd"})
    print("All-sector MNE sales = F + D_MNE from the AAMNE MNE-split file.")
else:
    aamne2 = pd.read_csv(aamne_data)
    aamne2 = aamne2[["year", "cou", "own", "isic", "GO", "EXP"]].copy()
    aamne2 = aamne2[aamne2["year"].isin(analysis_years)]
    aamne2 = aamne2[aamne2["cou"] != "ROW"]
    aamne2["GO"] = pd.to_numeric(aamne2["GO"], errors="coerce")
    aamne2["EXP"] = pd.to_numeric(aamne2["EXP"], errors="coerce")
    aamne2["db_sales"] = aamne2["GO"] - aamne2["EXP"]
    m_by_own = aamne2.groupby(["cou", "year", "own"], as_index=False)["db_sales"].sum()
    mne_wide = m_by_own.pivot_table(
        index=["cou", "year"], columns="own", values="db_sales"
    ).reset_index()
    mne_wide["mne_sales_musd"] = (
        mne_wide.get("F", pd.Series(0, index=mne_wide.index)).fillna(0)
        + 0.14 * mne_wide.get("D", pd.Series(0, index=mne_wide.index)).fillna(0)
    )
    print("All-sector MNE sales: AAMNE MNE-split file not found; XVEM + 14% fallback.")

mne_wide["mne_sales_aamne"] = mne_wide["mne_sales_musd"] * 1e6
mne_aamne = mne_wide[["cou", "year", "mne_sales_aamne"]].rename(columns={"cou": "iso"})
macro = macro.merge(mne_aamne, on=["iso", "year"], how="left")
macro["mne_ratio_actual"] = macro["mne_sales_aamne"] / macro["gdp"]

# 1.1.2 Extrapolation regressions — log GDP, log GDP per capita, log trade
# (the ln_* covariate columns exist on `macro` from Part 0).
mreg = macro[
    (macro["mne_ratio_actual"] > 0)
    & (macro["gdp"] > 0)
    & (macro["gdp_per_capita"] > 0)
    & (macro["trade_openness"] > 0)
].copy()
Xm = np.column_stack(
    [np.ones(len(mreg)), np.log(mreg["gdp"]), np.log(mreg["gdp_per_capita"]),
     np.log(mreg["trade_openness"])]
)
mbeta, _, _, _ = np.linalg.lstsq(Xm, np.log(mreg["mne_ratio_actual"]).values, rcond=None)
print(f"\nAll-sector MNE ratio regression: N = {len(mreg)} jurisdiction-years")
print(f"  constant / log GDP / log GDP p.c. / log trade: "
      f"{mbeta[0]:.4f} / {mbeta[1]:.4f} / {mbeta[2]:.4f} / {mbeta[3]:.4f}")

mreg2 = macro[
    (macro["mne_ratio_actual"] > 0) & (macro["gdp"] > 0) & (macro["gdp_per_capita"] > 0)
].copy()
Xm2 = np.column_stack(
    [np.ones(len(mreg2)), np.log(mreg2["gdp"]), np.log(mreg2["gdp_per_capita"])]
)
mbeta2, _, _, _ = np.linalg.lstsq(
    Xm2, np.log(mreg2["mne_ratio_actual"]).values, rcond=None
)

macro["mne_ratio_pred_full"] = np.exp(
    mbeta[0] + mbeta[1] * macro["ln_gdp"] + mbeta[2] * macro["ln_gdp_pc"]
    + mbeta[3] * macro["ln_trade"]
)
macro["mne_ratio_pred_reduced"] = np.exp(
    mbeta2[0] + mbeta2[1] * macro["ln_gdp"] + mbeta2[2] * macro["ln_gdp_pc"]
)
macro["mne_ratio_pred"] = macro["mne_ratio_pred_full"].where(
    macro["mne_ratio_pred_full"].notna(), macro["mne_ratio_pred_reduced"]
)
# Remittance/aid scaling (Part 0) applies to extrapolated ratios only.
macro["mne_ratio_pred_adj"] = macro["mne_ratio_pred"] * macro["aid_adjustment"]

# 1.1.3 Final ratio, level, tiny-market rule, per-year share — mirroring the
# CFB steps 2.1.8-2.1.12. The 2026 AAMNE edition covers 2021/2022 directly;
# the 2019 roll-forward below fills ONLY country-years the file misses (2020
# is COVID-distorted, so 2019 is the reference year, not 2020).
macro["mne_is_imputed"] = macro["mne_ratio_actual"].isna().astype(int)
macro["mne_ratio_final"] = macro["mne_ratio_actual"].where(
    macro["mne_ratio_actual"].notna(), macro["mne_ratio_pred_adj"]
)
mne_ratio_2019 = macro.loc[macro["year"] == 2019, ["iso", "mne_ratio_actual"]].dropna()
mne_ratio_2019 = dict(zip(mne_ratio_2019["iso"], mne_ratio_2019["mne_ratio_actual"]))
for yr in (2021, 2022):
    if yr not in analysis_years:
        continue
    mask = (
        (macro["year"] == yr)
        & (macro["iso"].isin(mne_ratio_2019))
        & macro["mne_ratio_actual"].isna()
    )
    macro.loc[mask, "mne_ratio_final"] = macro.loc[mask, "iso"].map(mne_ratio_2019)
    macro.loc[mask, "mne_is_imputed"] = 1
macro["mne_sales"] = macro["mne_ratio_final"] * macro["gdp"]
tiny_m = (macro["mne_sales"].isna()) & (macro["population"] < 250_000)
macro.loc[tiny_m, "mne_sales"] = 0.0
macro.loc[tiny_m, "mne_is_imputed"] = 1
macro["mne_share"] = macro["mne_sales"] / macro.groupby("year")["mne_sales"].transform(
    "sum"
)
# %% [markdown] MARK: 2.2 Digitally deliverable services imports
# 1.2 Digitally deliverable services imports (BaTIS) and their MNE share.
# The WTO "digitally DELIVERED" aggregate (Part 0) has an unclear definition
# that sits between the IMF-OECD-UNCTAD-WTO Handbook's broad "digitally
# DELIVERABLE" (deliverable using ICT) and the narrow ADS (produced AND
# delivered digitally):
#   ADS  <  digitally delivered (WTO)  <  digitally deliverable (Handbook/BaTIS).
# Following the team's G24 paper ("Options for a Protocol on Services under
# the UNFCITC"), the headline builds the DELIVERABLE aggregate directly and
# transparently from BaTIS EBOPS categories; it should come out HIGHER than
# the WTO digitally-delivered series. Falls back (loudly) to the WTO series
# while the BaTIS download is absent, so the pipeline never breaks.
# %%
# 1.2.1 BaTIS digitally-deliverable imports per (iso, year).
# Handbook category set (EBOPS 2010): SF insurance & pension, SG financial,
# SH charges for IP, SI telecom/computer/information (the aggregate — its
# sub-items SI1-SI3 would double-count), SJ other business services, SK1
# audiovisual & related (the digitally deliverable part of SK). The exact
# list used is `use` in the loader below.


def _load_batis_dds_imports(path):
    """BaTIS BPM6 bulk CSV -> (iso3, year, dds_imports_usd).

    Layout (December-2025 edition, verified): Reporter/Partner ISO2 with
    type_Reporter/type_Partner flags ("c" = country), Flow (M/X), Item_code
    (EBOPS 2010), Year, and Reported/Final/Balanced values in MILLION USD.
    The BALANCED value is the reconciled export/import series (codes-workbook
    notes) and is used here, with Final_value as row-level fallback. Imports
    (M) only, country reporters AND country partners only (region aggregates
    excluded), summed over partners, restricted to the Handbook digitally-
    deliverable set: SF, SG, SH, SI (aggregate, so SI1-3 excluded), SJ, SK1.
    Chunked — the bulk file is ~2.8 GB.
    """
    use = ["SF", "SG", "SH", "SI", "SJ", "SK1"]
    usecols = ["Reporter", "type_Reporter", "Partner", "type_Partner", "Flow",
               "Item_code", "Year", "Final_value", "Balanced_value"]
    parts = []
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=3_000_000):
        c = chunk[
            (chunk["Flow"] == "M")
            & (chunk["Year"].isin(analysis_years))
            & (chunk["Item_code"].isin(use))
            & (chunk["type_Reporter"] == "c")
            & (chunk["type_Partner"] == "c")
        ]
        if c.empty:
            continue
        v = pd.to_numeric(c["Balanced_value"], errors="coerce").fillna(
            pd.to_numeric(c["Final_value"], errors="coerce")
        )
        parts.append(pd.DataFrame({"iso2": c["Reporter"], "year": c["Year"],
                                   "item": c["Item_code"], "v": v}))
    if not parts:
        raise ValueError(f"BaTIS: no matching rows found in {path} — check layout.")
    b = pd.concat(parts, ignore_index=True)
    b = b.groupby(["iso2", "year", "item"], as_index=False)["v"].sum()
    iso_map = {}
    for code in b["iso2"].dropna().unique():
        cc = pycountry.countries.get(alpha_2=str(code))
        if cc is not None:
            iso_map[code] = cc.alpha_3
    b["iso"] = b["iso2"].map(iso_map)
    _dropped = b.loc[b["iso"].isna(), "iso2"].unique()
    b = b.dropna(subset=["iso"])
    # Full Handbook aggregate + the ex-IP sensitivity (drop SH, charges for the
    # use of intellectual property — ~15% of the aggregate and largely
    # INTRA-group royalty flows, at odds with the unrelated-party sales concept
    # the destination key replaces; also the most purely intra-MNE category).
    full = b.groupby(["iso", "year"])["v"].sum()
    exip = b[b["item"] != "SH"].groupby(["iso", "year"])["v"].sum()
    out = pd.DataFrame({"dds_imports_usd": full * 1e6,
                        "dds_imports_exip_usd": exip * 1e6}).reset_index()
    print(f"  BaTIS: {out['iso'].nunique()} reporter countries, categories {use} "
          f"(+ ex-IP variant without SH), balanced value (Final fallback); "
          f"unmapped ISO2 dropped: {list(_dropped)}.")
    return out


if Path(batis_data).exists():
    batis = _load_batis_dds_imports(batis_data)
    macro = macro.merge(batis, on=["iso", "year"], how="left")
    _b = macro.groupby("year")["dds_imports_usd"].sum() / 1e9
    _w = macro.groupby("year")["digital_imports_usd"].sum() / 1e9
    print("\nBaTIS digitally-DELIVERABLE vs WTO digitally-DELIVERED imports ($bn):")
    for y in sorted(_b.index):
        flag = "  <-- BaTIS < WTO: check category selection!" if _b[y] < _w[y] else ""
        print(f"  {int(y)}: BaTIS {_b[y]:,.0f} vs WTO {_w[y]:,.0f}{flag}")
else:
    # The headline measure is defined on the BaTIS "digitally deliverable"
    # aggregate; running without it silently changes the headline numbers. So a
    # missing BaTIS download is a HARD ERROR unless the narrower WTO series is
    # explicitly opted into with ALLOW_WTO_FALLBACK=1.
    if os.environ.get("ALLOW_WTO_FALLBACK", "") != "1":
        raise FileNotFoundError(
            f"BaTIS bulk file not found: {batis_data}. The headline destination "
            "measure requires the BaTIS digitally-deliverable imports (download: "
            "see data/guides/README.md). To knowingly use the narrower WTO "
            "digitally-delivered series instead, set ALLOW_WTO_FALLBACK=1."
        )
    print(
        "\n*** BaTIS file NOT FOUND — ALLOW_WTO_FALLBACK=1: using the WTO "
        "digitally-delivered series (ex-IP variant = full series here); "
        "headline numbers will differ from the BaTIS-based paper figures. ***"
    )
    macro["dds_imports_usd"] = macro["digital_imports_usd"]
    macro["dds_imports_exip_usd"] = macro["digital_imports_usd"]

# 1.2.2 Extrapolate on log GDP (mirrors step 0.9) so coverage matches the MNE measure.
d2 = macro[(macro["dds_imports_usd"] > 0) & (macro["gdp"] > 0)].copy()
db2 = np.linalg.lstsq(
    np.column_stack([np.ones(len(d2)), np.log(d2["gdp"])]),
    np.log(d2["dds_imports_usd"]).values, rcond=None,
)[0]
macro["dds_imports_pred"] = np.exp(db2[0] + db2[1] * macro["ln_gdp"])
macro["dds_imports_filled"] = macro["dds_imports_usd"].where(
    macro["dds_imports_usd"].notna(), macro["dds_imports_pred"]
)
macro["dds_imports0"] = macro["dds_imports_filled"].fillna(0)

# 1.2.3 Ex-IP variant: same log-GDP extrapolation for the SH-free aggregate.
d3 = macro[(macro["dds_imports_exip_usd"] > 0) & (macro["gdp"] > 0)].copy()
db3 = np.linalg.lstsq(
    np.column_stack([np.ones(len(d3)), np.log(d3["gdp"])]),
    np.log(d3["dds_imports_exip_usd"]).values, rcond=None,
)[0]
macro["dds_exip_pred"] = np.exp(db3[0] + db3[1] * macro["ln_gdp"])
macro["dds_exip_filled"] = macro["dds_imports_exip_usd"].where(
    macro["dds_imports_exip_usd"].notna(), macro["dds_exip_pred"]
)
macro["dds_exip0"] = macro["dds_exip_filled"].fillna(0)

# 1.2.4 MNE share of digitally-deliverable-sector exports (AAMNE). The BaTIS
# imports are ALL-supplier trade flows, but the destination key replaces an MNE
# sales variable — only the MNE-supplied part belongs in the measure.
# Share = (F + D_MNE) / all-firm EXGR over the ISIC sectors that
# produce the Handbook categories (SF/SG -> K64T66; SI -> J58T60/J61/J62T63;
# SJ -> M69T75/N77T82; SK1 -> R90T93). Per-year (~53-58%, stable), with the
# last AAMNE year rolled forward to later analysis years.
DDS_MNE_ISIC = ["J58T60", "J61", "J62T63", "K64T66", "M69T75", "N77T82", "R90T93"]
if Path(aamne_dmne_data).exists():
    _am = pd.read_csv(aamne_dmne_data)
    _am = _am[_am["isic"].isin(DDS_MNE_ISIC)]
    _ms = (_am[_am["own"].isin(["F", "D_MNE"])].groupby("year")["EXGR"].sum()
           / _am.groupby("year")["EXGR"].sum())
    mne_dds_share = {int(y): float(v) for y, v in _ms.items()}
else:
    print("*** AAMNE MNE-split file missing — DDS leg left UNSCALED (share=1). ***")
    mne_dds_share = {}
_last_cov = max(mne_dds_share) if mne_dds_share else None
for _y in analysis_years:
    if _y not in mne_dds_share:
        mne_dds_share[_y] = mne_dds_share[_last_cov] if _last_cov else 1.0
print("\nMNE (F + D_MNE) share of digitally-deliverable-sector exports (AAMNE), %:")
print("  " + ", ".join(f"{y}: {mne_dds_share[y] * 100:.1f}"
                       for y in sorted(analysis_years)))
macro["dds_imports_mne"] = macro["dds_imports0"] * macro["year"].map(mne_dds_share)
macro["dds_exip_mne"] = macro["dds_exip0"] * macro["year"].map(mne_dds_share)

# 1.3 Broadened combined key (per-year re-shared): all-sector MNE local sales
# + the MNE share of digitally-deliverable imports EXCLUDING SH / charges for
# the use of IP (disjoint: local turnover vs cross-border imports). THE
# HEADLINE DESTINATION MEASURE. SH is excluded because it is ~15% of the
# Handbook aggregate and largely intra-group royalty payments
# (affiliate->parent), at odds with the unrelated-party sales
# concept the destination factor replaces.
# The key deliberately carries NO third ad-funded-ADS leg: every PAID automated
# digital service is
# already inside the BaTIS deliverable imports (ADS is a subset of the Handbook
# categories), and the ad-funded free slice has no trade counterpart and is
# bounded by global digital-ad revenue (~USD 0.6tn, <1% of the key), so it is
# excluded rather than proxied — a consumption-scaled proxy would give it ~14%
# of the key, an order of magnitude too much.
macro["mne_plus_dds_value"] = macro["mne_sales"] + macro["dds_exip_mne"]
macro["mne_plus_dds_share"] = macro["mne_plus_dds_value"] / macro.groupby("year")[
    "mne_plus_dds_value"
].transform("sum")

# 1.3.1 IP-INCLUSIVE sensitivity key: the full Handbook aggregate (SH kept in
# the deliverable-services leg). Same MNE-share scaling as the headline key.
macro["mne_plus_dds_inclip_value"] = macro["mne_sales"] + macro["dds_imports_mne"]
macro["mne_plus_dds_inclip_share"] = macro["mne_plus_dds_inclip_value"] / macro.groupby(
    "year"
)["mne_plus_dds_inclip_value"].transform("sum")

# 1.3.2 Ex-IP (headline) aggregate vs the WTO digitally-delivered series: the
# FULL Handbook aggregate exceeds the WTO series every year (G24 ordering); the
# ex-IP aggregate may dip below it in later years — print both for the paper.
_exip_g = macro.groupby("year")["dds_imports_exip_usd"].sum() / 1e9
_wto_g = macro.groupby("year")["digital_imports_usd"].sum() / 1e9
print("\nEx-IP deliverable (headline leg, unscaled) vs WTO delivered imports ($bn):")
for _y in sorted(_exip_g.index):
    print(f"  {int(_y)}: ex-IP {_exip_g[_y]:,.0f} vs WTO {_wto_g[_y]:,.0f}"
          + ("  (below WTO)" if _exip_g[_y] < _wto_g[_y] else ""))

# 1.3.3 Implied DDS weight in the broadened combined key (expect BELOW the CFB
# combined weight, since the local-sales base broadens).
_v2 = macro[macro["mne_plus_dds_value"].notna()]
_w2 = (_v2.groupby("year")["dds_exip_mne"].sum()
       / _v2.groupby("year")["mne_plus_dds_value"].sum() * 100).round(1)
print("\nImplied DDS weight (deliverable imports / [all-MNE + imports]) by year, %:")
print(_w2.to_string())

# %% [markdown] MARK: Part 3. Comparison measures
# Part 2. Comparison measures — the OECD (2020) constructions,
# computed alongside the headline so outcomes can be compared in scripts 5/9.

# %% [markdown] MARK: 3.1 CFB destination-based sales
# 2.1 CFB destination-based sales (OECD para. 92-99): the turnover-minus-
# exports proxy RESTRICTED to consumer-facing sectors — the OECD's own
# implementation choice, which the headline measure deliberately widens.
# %%
# 2.1.1 CFB sector classification.
# OECD identifies CFB sectors at the NACE Rev.2 4-digit level (Table 2.2,
# Panel B). Analytical AMNE only provides the aggregated ISIC Rev.4 sections
# below, so each section is flagged CFB when consumer-facing activities
# dominate it. This is a judgement mapping - edit freely.
cfb_sectors = [
    "C10T12",  # food, beverages, tobacco
    "C13T15",  # textiles, wearing apparel, leather (apparel/footwear)
    "C21",  # pharmaceuticals
    "C26",  # computers, electronics, optical (consumer electronics)
    "C29",  # motor vehicles
    "C31T33",  # furniture, other manufacturing (sports goods, games, ...)
    "D35_E36T39",  # utilities supplied to consumers, water, sewerage
    "G45T47",  # wholesale & retail trade (retail-heavy)
    "H53",  # postal & courier
    "I55T56",  # accommodation & food service
    "J58T60",  # publishing, audiovisual, broadcasting
    "J61",  # telecommunications
    "P85",  # education
    "Q86T88",  # human health & social work
    "R90T93",  # arts, entertainment & recreation
    "S94T96",  # repair of personal goods, other personal services
    "T97T98",  # activities of households
]

# %%
# 2.1.2 MNE CFB destination-based sales = turnover (GO) - exports, summed over
# CFB sectors, for MNE entities = foreign-owned (F) + domestic-owned MNEs
# (D_MNE). Primary source: the AAMNE MNE-split file (ownership F / D_MNE /
# D_OTH; exports column `EXGR`; million USD). Fallback if it is absent: the
# XVEM file (D / F only, exports `EXP`) with the OECD flat 14% domestic-MNE
# share (para. 95).
if Path(aamne_dmne_data).exists():
    a = pd.read_csv(aamne_dmne_data)
    a = a[a["isic"].isin(cfb_sectors)]
    a = a[a["year"].isin(analysis_years)]
    a = a[a["cou"] != "ROW"]
    a = a[a["own"].isin(["F", "D_MNE"])]
    a["GO"] = pd.to_numeric(a["GO"], errors="coerce")
    a["EXGR"] = pd.to_numeric(a["EXGR"], errors="coerce")
    a["db_sales"] = a["GO"] - a["EXGR"]
    cfb_wide = a.groupby(["cou", "year"], as_index=False)["db_sales"].sum()
    cfb_wide = cfb_wide.rename(columns={"db_sales": "cfb_sales_musd"})
    print("MNE CFB sales = F + D_MNE from the AAMNE MNE-split file.")
else:
    aamne = pd.read_csv(aamne_data)
    aamne = aamne[["year", "cou", "own", "isic", "GO", "EXP"]].copy()
    aamne = aamne[aamne["isic"].isin(cfb_sectors)]
    aamne = aamne[aamne["year"].isin(analysis_years)]
    aamne = aamne[aamne["cou"] != "ROW"]
    aamne["GO"] = pd.to_numeric(aamne["GO"], errors="coerce")
    aamne["EXP"] = pd.to_numeric(aamne["EXP"], errors="coerce")
    aamne["db_sales"] = aamne["GO"] - aamne["EXP"]
    cfb_by_own = aamne.groupby(["cou", "year", "own"], as_index=False)["db_sales"].sum()
    cfb_wide = cfb_by_own.pivot_table(
        index=["cou", "year"], columns="own", values="db_sales"
    ).reset_index()
    cfb_wide = cfb_wide.rename(columns={"F": "cfb_foreign", "D": "cfb_domestic"})
    for _c in ("cfb_foreign", "cfb_domestic"):
        if _c not in cfb_wide.columns:   # ownership class absent in the file
            cfb_wide[_c] = 0.0
        cfb_wide[_c] = cfb_wide[_c].fillna(0)
    cfb_wide["cfb_sales_musd"] = (
        cfb_wide["cfb_foreign"] + 0.14 * cfb_wide["cfb_domestic"]
    )
    print("AAMNE MNE-split file not found; using XVEM + flat 14% fallback.")

# Convert million USD to USD and rename the host country to `iso`.
cfb_wide["cfb_sales_aamne"] = cfb_wide["cfb_sales_musd"] * 1e6
cfb_aamne = cfb_wide[["cou", "year", "cfb_sales_aamne"]].rename(columns={"cou": "iso"})

print(
    f"AAMNE CFB sales computed for {cfb_aamne['iso'].nunique()} jurisdictions, "
    f"years {cfb_aamne['year'].min()}-{cfb_aamne['year'].max()}."
)

# %%
# 2.1.3 Attach the AAMNE CFB level and compute the observed CFB/GDP ratio.
macro = macro.merge(cfb_aamne, on=["iso", "year"], how="left")
macro["cfb_ratio_actual"] = macro["cfb_sales_aamne"] / macro["gdp"]

# %%
# 2.1.4 Regression to extrapolate the CFB/GDP ratio (OECD Table 2.4, column 1):
#   log(CFB sales / GDP) = b0 + b1 log GDP + b2 log GDP p.c. + b3 log trade.
# Estimated over the AAMNE-covered jurisdiction-years with positive values.
reg = macro[
    (macro["cfb_ratio_actual"] > 0)
    & (macro["gdp"] > 0)
    & (macro["gdp_per_capita"] > 0)
    & (macro["trade_openness"] > 0)
].copy()
reg["ln_ratio"] = np.log(reg["cfb_ratio_actual"])
reg["ln_gdp"] = np.log(reg["gdp"])
reg["ln_gdp_pc"] = np.log(reg["gdp_per_capita"])
reg["ln_trade"] = np.log(reg["trade_openness"])

X = np.column_stack(
    [np.ones(len(reg)), reg["ln_gdp"], reg["ln_gdp_pc"], reg["ln_trade"]]
)
y = reg["ln_ratio"].values
beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)

print(f"\nCFB ratio regression: N = {len(reg)} jurisdiction-years")
print(f"  constant        : {beta[0]:.4f}   (OECD -4.063)")
print(f"  log GDP         : {beta[1]:.4f}   (OECD  0.0874)")
print(f"  log GDP p.c.    : {beta[2]:.4f}   (OECD -0.0314)")
print(f"  log trade open. : {beta[3]:.4f}   (OECD  0.315)")

# 2.1.5 Reduced regression on log GDP + log GDP p.c. only, used for
# jurisdictions that have GDP but no trade-openness data (e.g. NGA, TWN, MMR,
# LBR, SSD), so they still get a CFB value.
reg2 = macro[
    (macro["cfb_ratio_actual"] > 0) & (macro["gdp"] > 0) & (macro["gdp_per_capita"] > 0)
].copy()
reg2["ln_ratio"] = np.log(reg2["cfb_ratio_actual"])
reg2["ln_gdp"] = np.log(reg2["gdp"])
reg2["ln_gdp_pc"] = np.log(reg2["gdp_per_capita"])
X2 = np.column_stack([np.ones(len(reg2)), reg2["ln_gdp"], reg2["ln_gdp_pc"]])
beta2, _, _, _ = np.linalg.lstsq(X2, reg2["ln_ratio"].values, rcond=None)

# %%
# 2.1.6 Predicted ratio for every jurisdiction-year. Use the full regression
# where trade openness is available, else the reduced (GDP + GDP p.c.) one.
macro["cfb_ratio_pred_full"] = np.exp(
    beta[0]
    + beta[1] * macro["ln_gdp"]
    + beta[2] * macro["ln_gdp_pc"]
    + beta[3] * macro["ln_trade"]
)
macro["cfb_ratio_pred_reduced"] = np.exp(
    beta2[0] + beta2[1] * macro["ln_gdp"] + beta2[2] * macro["ln_gdp_pc"]
)
macro["cfb_ratio_pred"] = macro["cfb_ratio_pred_full"].where(
    macro["cfb_ratio_pred_full"].notna(), macro["cfb_ratio_pred_reduced"]
)

# (aid adjustment built in Part 0)

# 2.1.7 CFB: apply the remittances/aid adjustment (built in Part 0) to the
# extrapolated ratios only.
macro["cfb_ratio_pred_adj"] = macro["cfb_ratio_pred"] * macro["aid_adjustment"]

# %%
# 2.1.8 Final ratio: observed AAMNE ratio where available, else the adjusted
# extrapolated ratio.
macro["cfb_is_imputed"] = macro["cfb_ratio_actual"].isna().astype(int)
macro["cfb_ratio_final"] = macro["cfb_ratio_actual"].where(
    macro["cfb_ratio_actual"].notna(), macro["cfb_ratio_pred_adj"]
)

# 2.1.9 Recent years: the 2026 AAMNE edition covers 2021/2022 directly, so
# the observed ratio is used where present; for country-years the file misses,
# the country's own 2019 ratio (2020 is COVID-distorted) is reused instead of
# the regression extrapolation.
ratio_2019 = macro.loc[macro["year"] == 2019, ["iso", "cfb_ratio_actual"]].dropna()
ratio_2019 = dict(zip(ratio_2019["iso"], ratio_2019["cfb_ratio_actual"]))
for yr in (2021, 2022):
    if yr not in analysis_years:
        continue
    mask = (
        (macro["year"] == yr)
        & (macro["iso"].isin(ratio_2019))
        & macro["cfb_ratio_actual"].isna()
    )
    macro.loc[mask, "cfb_ratio_final"] = macro.loc[mask, "iso"].map(ratio_2019)
    macro.loc[mask, "cfb_is_imputed"] = 1

# 2.1.10 Turn the ratio into a USD level.
macro["cfb_sales"] = macro["cfb_ratio_final"] * macro["gdp"]

# 2.1.11 Tiny-market rule: a market still missing after extrapolation with
# almost no population gets 0 (never overrides a real estimate).
tiny = (macro["cfb_sales"].isna()) & (macro["population"] < 250_000)
macro.loc[tiny, "cfb_sales"] = 0.0
macro.loc[tiny, "cfb_is_imputed"] = 1

# 2.1.12 Global share per year (the form actually consumed as an allocation key).
macro["cfb_share"] = macro["cfb_sales"] / macro.groupby("year")["cfb_sales"].transform(
    "sum"
)

n_actual = (macro["cfb_is_imputed"] == 0).sum()
n_imputed = ((macro["cfb_is_imputed"] == 1) & macro["cfb_sales"].notna()).sum()
n_missing = macro["cfb_sales"].isna().sum()
print(
    f"\nCFB sales: {n_actual} observed (AAMNE), {n_imputed} extrapolated/zeroed, "
    f"{n_missing} still missing."
)

# Diagnostic: the all-sector measure must be a superset of CFB.
_diag = macro[(macro["mne_sales"] > 0) & (macro["cfb_sales"] > 0)]
_ratio_by_year = (
    _diag.groupby("year")["mne_sales"].sum() / _diag.groupby("year")["cfb_sales"].sum()
)
print("\nGlobal all-sector MNE sales / CFB sales by year (expect > 1):")
print(_ratio_by_year.round(2).to_string())

# %% [markdown] MARK: 3.2 ADS destination-based sales
# 2.2 ADS destination-based sales (OECD para. 103-104):
# ads_sales = internet penetration x total household consumption (USD).
# %%
# 2.2.1 Internet penetration (ITU "Individuals using the Internet", % of pop;
# long format with entityIso, dataYear, dataValue).
itu = pd.read_csv(itu_internet_data)
itu = itu[itu["seriesCode"] == "i99H"]
itu = itu[["entityIso", "dataYear", "dataValue"]].copy()
itu = itu.rename(
    columns={"entityIso": "iso", "dataYear": "year", "dataValue": "internet_pct"}
)
itu["year"] = pd.to_numeric(itu["year"], errors="coerce")
itu["internet_pct"] = pd.to_numeric(itu["internet_pct"], errors="coerce")
itu = itu[itu["year"].isin(analysis_years)]
itu = itu.dropna(subset=["internet_pct"])
itu = itu.drop_duplicates(["iso", "year"], keep="last")
itu["internet_frac"] = itu["internet_pct"] / 100.0
macro = macro.merge(
    itu[["iso", "year", "internet_frac"]], on=["iso", "year"], how="left"
)

# %%
# 2.2.2 Total household consumption in USD (UN National Accounts, COICOP table;
# national currency). Take the household "Equals: Household final consumption
# expenditure" line, dedup vintages, map country name -> ISO3, convert to USD.
un = pd.read_csv(un_consumption_data, low_memory=False)
un = un[un["Sub Group"] == "Individual consumption expenditure of households"]
un = un[un["Item"] == "Equals: Household final consumption expenditure"]
un = un[un["Year"].isin(analysis_years)].copy()
un["Value"] = pd.to_numeric(un["Value"], errors="coerce")

# Vintage dedup: prefer SNA 2008, then the latest Series code.
un["sna_pref"] = (un["SNA System"] == 2008).astype(int)
un = un.sort_values(
    ["Country or Area", "Year", "sna_pref", "Series"],
    ascending=[True, True, False, False],
)
un = un.drop_duplicates(["Country or Area", "Year"], keep="first")


# Country name -> ISO3 via pycountry (fuzzy fallback); unmapped names dropped.
def name_to_iso3(name):
    try:
        return pycountry.countries.lookup(name).alpha_3
    except LookupError:
        try:
            return pycountry.countries.search_fuzzy(name)[0].alpha_3
        except Exception:
            return None


name_map = {n: name_to_iso3(n) for n in un["Country or Area"].unique()}
un["iso"] = un["Country or Area"].map(name_map)
un = un.dropna(subset=["iso"])
un = un.rename(columns={"Year": "year"})
_dup = un[un.duplicated(["iso", "year"], keep=False)]
if not _dup.empty:
    raise AssertionError(
        "UN consumption: multiple country names map to the same ISO3 — the "
        "merge below would duplicate rows. Offending names: "
        f"{sorted(_dup['Country or Area'].unique())}"
    )

# FX: official exchange rate, LCU per US$ (WB API CSV). consumption_usd in the
# same units as the UN Value (consistent per country, which is all the share
# computation needs).
fx_raw = pd.read_csv(exchange_rates_wb, skiprows=4)
fx_raw = fx_raw[["Country Code"] + year_str]
fx_long = fx_raw.melt(
    id_vars="Country Code", var_name="year", value_name="fx_lcu_per_usd"
)
fx_long["year"] = fx_long["year"].astype(int)
fx_long = fx_long.rename(columns={"Country Code": "iso"})

un = un.merge(fx_long, on=["iso", "year"], how="left")
un["consumption_usd"] = un["Value"] / un["fx_lcu_per_usd"]
un = un[un["consumption_usd"] > 0]
macro = macro.merge(
    un[["iso", "year", "consumption_usd"]], on=["iso", "year"], how="left"
)

# %%
# 2.2.3 Extrapolate total household consumption to all jurisdictions: consumption
# is ~ a stable share of GDP, so fit log(consumption_usd) = c0 + c1 log(GDP).
creg = macro[(macro["consumption_usd"] > 0) & (macro["gdp"] > 0)].copy()
creg["ln_cons"] = np.log(creg["consumption_usd"])
creg["ln_gdp"] = np.log(creg["gdp"])
Xc = np.column_stack([np.ones(len(creg)), creg["ln_gdp"]])
cbeta, _, _, _ = np.linalg.lstsq(Xc, creg["ln_cons"].values, rcond=None)
ss_res = float(np.sum((creg["ln_cons"].values - Xc @ cbeta) ** 2))
ss_tot = float(np.sum((creg["ln_cons"].values - creg["ln_cons"].mean()) ** 2))
print(
    f"\nConsumption-on-GDP regression: N = {len(creg)}, "
    f"R2 = {1 - ss_res / ss_tot:.3f}"
)

macro["consumption_pred"] = np.exp(cbeta[0] + cbeta[1] * macro["ln_gdp"])
macro["consumption_filled"] = macro["consumption_usd"].where(
    macro["consumption_usd"].notna(), macro["consumption_pred"]
)

# %%
# 2.2.4 Extrapolate internet penetration where missing on log(GDP per capita)
# (OECD para. 102-103: users correlate with income / penetration).
preg = macro[(macro["internet_frac"].notna()) & (macro["gdp_per_capita"] > 0)].copy()
preg["ln_gdp_pc"] = np.log(preg["gdp_per_capita"])
Xp = np.column_stack([np.ones(len(preg)), preg["ln_gdp_pc"]])
pbeta, _, _, _ = np.linalg.lstsq(Xp, preg["internet_frac"].values, rcond=None)
macro["internet_pred"] = (pbeta[0] + pbeta[1] * macro["ln_gdp_pc"]).clip(0, 1)
macro["internet_filled"] = macro["internet_frac"].where(
    macro["internet_frac"].notna(), macro["internet_pred"]
)

# %%
# 2.2.5 ADS level and imputation flag (imputed unless both inputs were observed).
macro["ads_sales"] = macro["internet_filled"] * macro["consumption_filled"]
macro["ads_is_imputed"] = (
    macro["internet_frac"].isna() | macro["consumption_usd"].isna()
).astype(int)

# 2.2.6 Tiny-market rule (same as CFB).
tiny_ads = (macro["ads_sales"].isna()) & (macro["population"] < 250_000)
macro.loc[tiny_ads, "ads_sales"] = 0.0
macro.loc[tiny_ads, "ads_is_imputed"] = 1

# 2.2.7 Global share per year.
macro["ads_share"] = macro["ads_sales"] / macro.groupby("year")["ads_sales"].transform(
    "sum"
)

n_ads_obs = (macro["ads_is_imputed"] == 0).sum()
n_ads_imp = ((macro["ads_is_imputed"] == 1) & macro["ads_sales"].notna()).sum()
print(f"ADS sales: {n_ads_obs} observed, {n_ads_imp} extrapolated/zeroed.")

# %%
# Write the destination-based-sales table (one row per market jurisdiction and
# year). Merged into cbcr_main_disaggregated in script 2.
cols = [
    "iso",
    "year",
    "cfb_sales",
    "cfb_is_imputed",
    "cfb_share",
    "ads_sales",
    "ads_is_imputed",
    "ads_share",
    "digital_imports_usd",
    # Broadened HEADLINE measure (all-sector MNE sales + the MNE share of BaTIS
    # digitally-deliverable imports EXCLUDING charges for IP) — the CFB/ADS
    # keys are kept alongside for comparison. (No ADS-proxy leg; ADS enters
    # only via BaTIS.)
    "mne_sales",
    "mne_is_imputed",
    "mne_share",
    "dds_imports_usd",
    "dds_imports_exip_usd",
    "mne_plus_dds_share",
    # IP-INCLUSIVE sensitivity (full Handbook aggregate, SH kept).
    "mne_plus_dds_inclip_share",
]
dest_sales = macro[cols].copy()
dest_sales = dest_sales.rename(columns={"iso": "iso_partner"})
dest_sales = dest_sales[
    dest_sales["cfb_sales"].notna()
    | dest_sales["ads_sales"].notna()
    | dest_sales["mne_sales"].notna()
]
dest_sales = dest_sales.sort_values(["iso_partner", "year"]).reset_index(drop=True)

# ── Coverage / integrity checks ──────────────────────────────────────────────
# 1. Every REAL CbCR partner must carry the headline share in every analysis
#    year — a NaN here would silently exclude the whole market from every
#    destination-formula estimate in script 5 (e.g. a missing BHS share would
#    drop ~$30bn of booked profit). Add a jurisdiction to the exception set
#    ONLY with a documented reason.
_real_isos = sorted(set(g1["iso_partner"].unique()) - set(non_countries))
_coverage_exceptions = set()  # none allowed at present
_expected = pd.MultiIndex.from_product(
    [[i for i in _real_isos if i not in _coverage_exceptions], analysis_years],
    names=["iso_partner", "year"],
).to_frame(index=False)
_have = _expected.merge(
    dest_sales[["iso_partner", "year", "mne_plus_dds_share"]],
    on=["iso_partner", "year"],
    how="left",
)
_gaps = _have[_have["mne_plus_dds_share"].isna()]
if not _gaps.empty:
    _gap_isos = _gaps.groupby("iso_partner")["year"].apply(list).to_dict()
    raise AssertionError(
        f"Headline destination share (mne_plus_dds_share) missing for "
        f"{len(_gaps)} real partner-years: {_gap_isos}"
    )

# 2. Each share column must still sum to 1 per year (within tolerance).
for _sc in ("cfb_share", "mne_share", "mne_plus_dds_share"):
    _sums = dest_sales.groupby("year")[_sc].sum()
    _bad = _sums[(_sums - 1.0).abs() > 1e-6]
    if not _bad.empty:
        raise AssertionError(f"{_sc} does not sum to 1 in years: {_bad.to_dict()}")
print("Coverage checks passed: all real partner-years share-covered; shares sum to 1.")

dest_sales.to_csv(f"{data_intermediate}/destination_based_sales.csv", index=False)
print(
    f"\nWrote {len(dest_sales)} rows to "
    f"data/intermediate/destination_based_sales.csv"
)

