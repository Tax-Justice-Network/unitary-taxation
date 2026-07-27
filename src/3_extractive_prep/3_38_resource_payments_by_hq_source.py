"""
Resource-related government payments brought to a (source country × HQ country ×
commodity × year) level — the input that 4_correcting_cbcr_for_resource_payments.py
adds back to / removes from CbCR profits.

Per (source_iso3, hq_iso3, commodity ∈ {oil_gas, coal, minerals, unknown, other}, year):
    pre_profit_payments_usd   — royalties, licence/area/surface fees, signature & production
                                bonuses, production entitlements (expensed ⇒ NOT in CbCR profit)
    post_profit_payments_usd  — corporate income tax + special petroleum/mining taxes + windfall
                                (the profit-based take)
    equity_income_usd         — state dividends / state-participation income (out of post-tax profit)
    other_payments_usd        — anything classified "other" by 1_6 (kept for completeness)
    data_source               — provenance: eiti_bilateral | manual_distributed | grd_distributed |
                                {eiti,manual,grd}_extrapolated (a real tier's value imputed into a gap year)

Source-priority cascade per (source, year) cell:
  1. EITI bilateral  — matched company payments → HQ country (1_6 → 1_7).  Used for every
     country that files EITI; unmatched companies are DROPPED (treated as local, per the
     project decision — not redistributed).
  2. Manual          — data/raw/resources/manual_resource_revenue.csv: a curated country-total table
     with explicit pre/post/equity fractions, a domestic_share, and a commodity; the
     country totals are distributed to HQ countries by hq_share_<commodity>.
  3. GRD             — extractive_royalty_dataset_yearly.csv (UNU-WIDER GRD, USD): country
     resource-revenue totals split into pre/post/equity from the GRD tax breakdown, the
     commodity split taken from World-Bank rents, then distributed to HQs by hq_share.
     The domestic-vs-foreign split is read from the consolidated control table
     (resource_country_parameters.csv) where available, else the per-commodity default.
  4. Gap-year extrapolation (ALL tiers) — for any covered country (EITI, manual OR GRD)
     with a year in the window that has reported CbCR profit but no panel row, scale the
     country's covered-year-average take (kept at the same HQ/commodity/bucket structure)
     by that year's reported CbCR profit relative to the covered-year average. A missing
     year is treated as a data gap (e.g. GRD ending 2021 -> Brunei 2022), not stopped
     production. Replaces the old crude WB rent-proxy fallback, which is RETIRED.
The WB rent-proxy tier is gone: every included resource country now has a real source
(EITI / manual / GRD), and the consolidated control table's `include` flag filters the
output to the genuine resource economies (non-resource countries are dropped here, and
get no resource correction in script 4).

Foreign HQ-share cascade for distributed (manual/GRD) totals — 2026-07-21:
  EITI bilateral + operator P2G shares  >  manual_foreign_hq_shares.csv (hand-curated
  consortium/operator splits, e.g. SSD → CNPC/Petronas/ONGC)  >  generic global Orbis
  hq_shares table. Every output row carries `hq_share_basis` ∈ {domestic, eiti_bilateral,
  eiti_operator, manual_foreign, generic_global} so the share provenance is auditable.

Inputs : data/intermediate/extractive/eiti_company_payments_long.csv     (1_6)
         data/intermediate/extractive/eiti_company_hq_map.csv            (1_7)
         data/intermediate/extractive/extractive_royalty_dataset_yearly.csv  (GRD + WB rents, USD)
         data/intermediate/extractive/hq_shares_by_commodity_yearly.csv  (3_2)
         data/raw/resources/manual_resource_revenue.csv
         data/raw/resources/manual_foreign_hq_shares.csv                 (hand-curated)
Output : data/intermediate/extractive/resource_payments_by_hq_source_yearly.csv
         data/intermediate/extractive/resource_payments_by_hq_source_coverage.csv
"""
import sys
import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

DATA_RAW = (EXT_INT / ".." / ".." / "raw").resolve()
PAY_LONG = EXT_INT / "eiti_company_payments_long.csv"
HQ_MAP = EXT_INT / "eiti_company_hq_map.csv"
ROYALTY_DS = EXT_INT / "extractive_royalty_dataset_yearly.csv"
HQ_SHARES = EXT_INT / "hq_shares_by_commodity_yearly.csv"
MANUAL = DATA_RAW / "resources" / "manual_resource_revenue.csv"
MANUAL_FHQ = DATA_RAW / "resources" / "manual_foreign_hq_shares.csv"   # hand-curated foreign HQ splits
PARAMS = DATA_RAW / "resources" / "resource_country_parameters.csv"   # consolidated control table: include flag + domestic split
CBCR_DISAGG = (EXT_INT / ".." / ".." / "final" / "cbcr_main_disaggregated.csv").resolve()
OUT = EXT_INT / "resource_payments_by_hq_source_yearly.csv"
OUT_COV = EXT_INT / "resource_payments_by_hq_source_coverage.csv"

YEARS = list(range(2016, 2023))                       # the CbCR analysis window
DIST_COMMODITIES = ["oil_gas", "coal", "minerals"]    # commodities the HQ-share table covers
BUCKETS = ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd", "other_payments_usd"]
RTYPE_TO_BUCKET = {"royalty_like": "pre_profit_payments_usd", "cit": "post_profit_payments_usd",
                   "equity": "equity_income_usd", "other": "other_payments_usd"}
# default split / domestic share when nothing more specific is known, by commodity
DEFAULT_SPLIT = {"oil_gas": (0.45, 0.30, 0.25), "coal": (0.55, 0.40, 0.05), "minerals": (0.50, 0.40, 0.10)}
DEFAULT_DOMESTIC = {"oil_gas": 0.55, "coal": 0.40, "minerals": 0.40}
EITI_EXTRAP_SCALE_MIN = 0.2       # clip the gap-year/covered-year reported-profit scaler
EITI_EXTRAP_SCALE_MAX = 5.0
CASCADE_ORDER = ["eiti_bilateral", "manual", "grd", "eiti_extrapolated"]   # WB rent-proxy retired

# Countries where the manual table should OVERRIDE EITI bilateral.
# Used when SUNAT-style tax-authority data is judged more comprehensive than the
# (potentially incomplete) EITI bilateral disclosures from the same country.
# PER: SUNAT covers 2016-2022 and ~65% larger than EITI for 2016-20 overlap;
#      EITI Peru is missing 2021-2022 entirely.
# MEX: Mexico EITI bilateral data is very thin (Pemex doesn't report to EITI).
#      Manual table now includes Pemex fiscal contribution (SHCP/20-F sourced).
MANUAL_OVERRIDES_EITI = {"PER", "MEX", "COD", "ECU"}
# COD (DRC) added 2026-05-14: EITI API pull covers only 2016/2017/2019;
# 2018, 2020-22 are in EITI national reports but not yet in the
# machine-readable /revenue endpoint. User-supplied national-report figures
# land in the manual table; this override lets them replace the partial EITI.
# ECU (Ecuador) added 2026-06: EITI bilateral is broken/thin — the raw company
# payments total only ~$4.2B for 2016-22 (vs ~$30-40B of actual oil revenue) and
# collapse to $0 in the panel (companies unmatched to an HQ). A manual figure
# (state oil revenue + sector CIT + Petroecuador surplus) replaces it.


# a few non-ISO3 codes that appear in hq_shares_by_commodity_yearly.csv
ISO2_FIX = {"MH": "MHL", "LI": "LIE", "WS": "WSM", "KV": "XKX", "KN": "KNA", "AC": "ATG"}


# ── HQ-share distribution helpers ────────────────────────────────────────────
def _hq_share_table():
    h = pd.read_csv(HQ_SHARES)
    h["hq_iso3"] = h["hq_iso3"].replace(ISO2_FIX)
    bad = h[h.hq_iso3.astype(str).str.len() != 3]
    if len(bad):
        print(f"  [warn] dropping {len(bad)} hq-share rows with non-ISO3 codes: {sorted(bad.hq_iso3.unique())}")
        h = h[h.hq_iso3.astype(str).str.len() == 3]
    h = h[h.year.isin(YEARS) & h.commodity.isin(DIST_COMMODITIES)].copy()
    # renormalise within (year, commodity) to be safe
    h["share"] = h["share"] / h.groupby(["year", "commodity"])["share"].transform("sum")
    return h


def _eiti_hq_share_overrides():
    """Build source-specific hq-share overrides from the EITI bilateral panel
    PLUS the operator-side P2G data, keyed by (source_iso3, commodity, year).

    Item A fix (2026-05-15): for manual_distributed countries (esp. COD/PER/MEX
    where EITI bilateral is dropped via MANUAL_OVERRIDES_EITI), the user-curated
    total magnitudes are preserved but the WHO-PAID attribution within each
    total is anchored to operator-level data wherever it exists for the
    (source, commodity, year) cell. Falls back to the generic Orbis-derived
    hq_tbl when neither EITI nor operator data is available.

    Sources merged in priority order:
      1. EITI bilateral panel (eiti_payments_by_hq_source_yearly.csv)
      2. Operator P2G panel (operator_payments_by_hq_source_yearly.csv;
         TotalEnergies / Eni / BP / Glencore / Vale / Sasol / Galp etc.)
    Operator data EXTENDS the EITI panel — for (source, year, hq) cells where
    EITI has data, EITI wins; for cells where only operator data exists, the
    operator number contributes to the share denominator.

    Returns DataFrame with columns: source_iso3, year, commodity, hq_iso3, share.
    """
    eiti_path = EXT_INT / "eiti_payments_by_hq_source_yearly.csv"
    op_path = EXT_INT / "operator_payments_by_hq_source_yearly.csv"
    parts = []
    if eiti_path.exists():
        e = pd.read_csv(eiti_path, low_memory=False)
        e = e.dropna(subset=["fy_end_year", "hq_iso3"])
        e = e[e["hq_iso3"].astype(str).str.len() == 3]
        e = e[~e["hq_iso3"].isin(["UNMATCHED", "UNKNOWN_HQ"])]
        e["year"] = pd.to_numeric(e["fy_end_year"], errors="coerce").astype("Int64")
        e = e.dropna(subset=["year"])
        e["commodity"] = e["commodity"].where(e["commodity"].isin(DIST_COMMODITIES), "minerals")
        e["value_usd"] = pd.to_numeric(e["value_usd"], errors="coerce").fillna(0.0).clip(lower=0)
        e_g = e.groupby(["source_iso3", "year", "commodity", "hq_iso3"], as_index=False)["value_usd"].sum()
        e_g["source"] = "eiti"
        parts.append(e_g)
    if op_path.exists():
        o = pd.read_csv(op_path, low_memory=False)
        o = o.dropna(subset=["year", "hq_iso3", "source_iso3"])
        o = o[o["hq_iso3"].astype(str).str.len() == 3]
        # Assume oil_gas for now (all major operators in the panel are upstream oil/gas);
        # commodity-aware extraction is a future refinement.
        # Default DIST_COMMODITIES is ["oil_gas", "coal", "minerals"] — assigning oil_gas
        # by default; Glencore (mining) gets minerals; CMOC/Vale get minerals.
        mineral_ops = {"Glencore", "CMOC", "Vale", "Sasol mining"}
        o["commodity"] = o["operator_name"].apply(lambda op: "minerals" if op in mineral_ops else "oil_gas")
        o["value_usd"] = pd.to_numeric(o["value_usd"], errors="coerce").fillna(0.0).clip(lower=0)
        o["year"] = pd.to_numeric(o["year"], errors="coerce").astype("Int64")
        o = o.dropna(subset=["year"])
        o_g = o.groupby(["source_iso3", "year", "commodity", "hq_iso3"], as_index=False)["value_usd"].sum()
        o_g["source"] = "operator"
        parts.append(o_g)
    if not parts:
        return pd.DataFrame(columns=["source_iso3", "year", "commodity", "hq_iso3", "share"])

    # Merge: take EITI value where available, else operator value
    combined = pd.concat(parts, ignore_index=True)
    # Within each (source, year, commodity, hq) cell, prefer EITI > operator
    combined["priority"] = combined["source"].map({"eiti": 0, "operator": 1}).fillna(2)
    combined = (combined.sort_values(["source_iso3", "year", "commodity", "hq_iso3", "priority"])
                        .drop_duplicates(["source_iso3", "year", "commodity", "hq_iso3"], keep="first"))
    tot = combined.groupby(["source_iso3", "year", "commodity"])["value_usd"].transform("sum")
    combined = combined[tot > 0].copy()
    combined["share"] = combined["value_usd"] / tot[tot > 0]
    return combined[["source_iso3", "year", "commodity", "hq_iso3", "share"]]


def _manual_foreign_hq_shares():
    """Hand-curated foreign-HQ splits (data/raw/resources/manual_foreign_hq_shares.csv):
    source_iso3, commodity, year (blank = every year), hq_iso3, share, confidence, source_note.
    Shares are weights within the FOREIGN slice only; renormalised per
    (source, commodity, year). Returns the same shape as the EITI override table."""
    if not MANUAL_FHQ.exists():
        return pd.DataFrame(columns=["source_iso3", "year", "commodity", "hq_iso3", "share"])
    f = pd.read_csv(MANUAL_FHQ, comment="#")
    rows = []
    for _, r in f.iterrows():
        yr = r.get("year")
        years = YEARS if (pd.isna(yr) or str(yr).strip() == "") else [int(yr)]
        for y in years:
            rows.append({"source_iso3": r["source_iso3"], "year": y, "commodity": r["commodity"],
                         "hq_iso3": r["hq_iso3"], "share": float(r["share"])})
    df = pd.DataFrame(rows)
    df["share"] = df["share"] / df.groupby(["source_iso3", "year", "commodity"])["share"].transform("sum")
    return df


def distribute(source_iso3, commodity, year, amount_pre, amount_post, amount_eq, domestic_share, hq_tbl,
               eiti_share_override=None, manual_fhq=None):
    """Split a source-country (commodity, year) total into (hq_iso3) rows.

    domestic_share lands on the source country itself (its NOC); the rest is spread over
    the *foreign* HQ shares for that commodity-year (the source country removed & renormalised).

    Foreign-share cascade (2026-07-21; each level used only when it has rows for this
    (source, year, commodity) cell):
      1. `eiti_share_override` — EITI bilateral + operator P2G derived shares
         (Item A fix, 2026-05-15): the observed who-paid attribution.
      2. `manual_fhq` — hand-curated foreign HQ shares (manual_foreign_hq_shares.csv)
         for countries with documented operator consortia but no EITI/operator data
         (e.g. SSD → CNPC/Petronas/ONGC, not the global average).
      3. generic global Orbis `hq_tbl` — last resort; tagged so the panel records
         which rows still rely on the global average.

    Each returned dict carries `hq_share_basis` ∈ {domestic, eiti_operator,
    manual_foreign, generic_global} for auditability."""
    rows = []
    dom = float(np.clip(domestic_share, 0.0, 1.0))
    if dom > 0:
        rows.append({"hq_iso3": source_iso3, "pre_profit_payments_usd": amount_pre * dom,
                     "post_profit_payments_usd": amount_post * dom, "equity_income_usd": amount_eq * dom,
                     "other_payments_usd": 0.0, "hq_share_basis": "domestic"})

    foreign, basis = None, "generic_global"
    if eiti_share_override is not None and len(eiti_share_override):
        ev = eiti_share_override[
            (eiti_share_override["source_iso3"] == source_iso3)
            & (eiti_share_override["year"] == year)
            & (eiti_share_override["commodity"] == commodity)
            & (eiti_share_override["hq_iso3"] != source_iso3)
        ]
        if len(ev):
            foreign, basis = ev.copy(), "eiti_operator"
    if foreign is None and manual_fhq is not None and len(manual_fhq):
        mv = manual_fhq[
            (manual_fhq["source_iso3"] == source_iso3)
            & (manual_fhq["year"] == year)
            & (manual_fhq["commodity"] == commodity)
            & (manual_fhq["hq_iso3"] != source_iso3)
        ]
        if len(mv):
            foreign, basis = mv.copy(), "manual_foreign"
    if foreign is None:
        foreign = hq_tbl[(hq_tbl.year == year) & (hq_tbl.commodity == commodity) & (hq_tbl.hq_iso3 != source_iso3)]

    fsum = foreign["share"].sum()
    if (1 - dom) > 0 and fsum > 0:
        for _, r in foreign.iterrows():
            w = (r["share"] / fsum) * (1 - dom)
            rows.append({"hq_iso3": r["hq_iso3"], "pre_profit_payments_usd": amount_pre * w,
                         "post_profit_payments_usd": amount_post * w, "equity_income_usd": amount_eq * w,
                         "other_payments_usd": 0.0, "hq_share_basis": basis})
    elif (1 - dom) > 0:
        # no foreign-share info → put the remainder on the source country too
        rows.append({"hq_iso3": source_iso3, "pre_profit_payments_usd": amount_pre * (1 - dom),
                     "post_profit_payments_usd": amount_post * (1 - dom), "equity_income_usd": amount_eq * (1 - dom),
                     "other_payments_usd": 0.0, "hq_share_basis": "domestic"})
    return rows


# ── 1. EITI bilateral ────────────────────────────────────────────────────────
def eiti_bilateral():
    pay = pd.read_csv(PAY_LONG, low_memory=False)
    hq = pd.read_csv(HQ_MAP, usecols=["source_iso3", "company_name", "hq_iso3", "match_method", "in_cbcr_universe"])
    pay = pay.merge(hq.rename(columns={"source_iso3": "iso3"}), on=["iso3", "company_name"], how="left")
    n_all = len(pay)
    pay = pay[pay["hq_iso3"].notna() & (pay["hq_iso3"].astype(str).str.len() == 3)]   # drop unmatched / no-HQ
    # gate the *domestic* portion: a payment by a company HQ'd in the producing country only lands on
    # that country's CbCR diagonal cell if the company is itself in the CbCR universe (a multi-entity
    # extractive group above the €750M threshold). Otherwise it's a pure-domestic operator → out of scope.
    in_u = pd.to_numeric(pay["in_cbcr_universe"], errors="coerce").fillna(0).astype(int)
    drop_domestic_nonmne = (pay["hq_iso3"] == pay["iso3"]) & (in_u != 1)
    n_dropped_dom = int(drop_domestic_nonmne.sum())
    v_dropped_dom = pd.to_numeric(pay.loc[drop_domestic_nonmne, "value_usd"], errors="coerce").fillna(0).sum()
    pay = pay[~drop_domestic_nonmne]
    n_kept = len(pay)
    pay = pay[pay["year"].between(2010, 2025)].copy()
    pay["bucket"] = pay["revenue_type"].map(RTYPE_TO_BUCKET)
    pay = pay[pay["bucket"].notna()]
    pay["value_usd"] = pd.to_numeric(pay["value_usd"], errors="coerce").fillna(0.0)
    g = (pay.groupby(["iso3", "hq_iso3", "commodity", "year", "bucket"], as_index=False)["value_usd"].sum()
         .pivot_table(index=["iso3", "hq_iso3", "commodity", "year"], columns="bucket", values="value_usd", fill_value=0.0)
         .reset_index().rename(columns={"iso3": "source_iso3"}))
    for b in BUCKETS:
        if b not in g.columns:
            g[b] = 0.0
    g["data_source"] = "eiti_bilateral"
    eiti_countries = sorted(pay["iso3"].unique())
    print(f"  EITI bilateral: {n_all:,} payment rows → {n_kept:,} kept ({100*n_kept/n_all:.0f}%); "
          f"dropped {n_dropped_dom:,} domestic-non-MNE rows (${v_dropped_dom/1e9:,.1f} B out of scope); "
          f"{len(g):,} (source,hq,commodity,year) cells; {len(eiti_countries)} source countries")
    return g[["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"]], set(eiti_countries)


# ── 2./3./4. cascade fill for non-EITI countries ─────────────────────────────
def manual_rows(year_set, hq_tbl, manual_fhq=None, eiti_overrides=None):
    m = pd.read_csv(MANUAL, comment="#")
    m = m[m["year"].isin(year_set)]
    # Build hq-shares override merging EITI bilateral + operator-side P2G data.
    # Item A fix (2026-05-15): used to be COD/PER/MEX only (those have manual
    # totals overriding EITI). Extended (later same day) to ALL manual entries —
    # operator P2G data (TotalEnergies/Eni/BP/Glencore/Vale/Sasol/Galp/etc.)
    # anchors the hq-share for any (source, year, commodity) cell where it
    # exists, even for countries with no EITI presence (e.g. SAU/SDN/SSD/YEM/etc.).
    eiti_overrides = _eiti_hq_share_overrides() if eiti_overrides is None else eiti_overrides
    n_overridden = 0
    out = []
    for _, r in m.iterrows():
        tot = float(r["total_resource_revenue_usd_bn"]) * 1e9
        pre, post, eq = tot * r["frac_pre_profit"], tot * r["frac_post_profit"], tot * r["frac_equity"]
        comm = r["commodity"] if r["commodity"] in DIST_COMMODITIES else "minerals"
        # Apply the EITI+operator override to every manual entry; the override
        # is only used inside distribute() when it actually has data for the
        # (source, year, commodity) cell, so non-covered cells degrade to the
        # generic Orbis hq_tbl gracefully.
        override_df = eiti_overrides if len(eiti_overrides) else None
        if override_df is not None:
            has_override = ((eiti_overrides["source_iso3"] == r["source_iso3"])
                            & (eiti_overrides["year"] == int(r["year"]))
                            & (eiti_overrides["commodity"] == comm)).any()
            if has_override:
                n_overridden += 1
        for d in distribute(r["source_iso3"], comm, int(r["year"]), pre, post, eq, r["domestic_share"], hq_tbl,
                            eiti_share_override=override_df, manual_fhq=manual_fhq):
            d.update({"source_iso3": r["source_iso3"], "commodity": comm, "year": int(r["year"]), "data_source": "manual_distributed"})
            out.append(d)
    if n_overridden:
        print(f"  manual: {n_overridden} (source, year, commodity) cells used EITI+operator-derived hq-shares "
              f"instead of generic Orbis weights")
    return pd.DataFrame(out) if out else pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"]), set(m["source_iso3"].unique())


def _commodity_split_from_wb(row):
    """Fractions of a country-year resource total to assign to oil_gas / coal / minerals, from WB rents.

    Returns None when no usable WB rent split exists (all missing/zero) — including the
    NaN case: a year with a GRD total but missing WB rents (e.g. Brunei 2022, where the
    WB rent series ends in 2021). NaN must be coerced to 0 first, because `nan or 0`
    returns nan (nan is truthy) and `nan <= 0` is False, which would otherwise leak NaN
    commodity fractions into a phantom GRD row that blocks the gap-year extrapolation."""
    def v(k):
        x = pd.to_numeric(row.get(k, 0.0), errors="coerce")
        return 0.0 if pd.isna(x) else float(x)
    og = v("wb_oil_rents_usd") + v("wb_gas_rents_usd")
    co = v("wb_coal_rents_usd")
    mi = v("wb_mineral_rents_usd")
    s = og + co + mi
    if s <= 0:
        return None
    return {"oil_gas": og / s, "coal": co / s, "minerals": mi / s}


def build_eiti_splits(eiti_df):
    """Per-(source, year) pre/post/equity FRACTIONS from the API bilateral EITI
    plus the folder Summary-Data splits (1_5b). Returns (by_year, by_country):
    by_year[(iso, yr)] and by_country[iso] = (pre_f, post_f, eq_f). Used by
    grd_rows to give a GRD-magnitude year the country's OWN EITI split instead of
    the GRD tax-field / resource_taxes fallback (year-specific if available, else
    the country average across its EITI years)."""
    recs = []
    if len(eiti_df):
        a = eiti_df.groupby(["source_iso3", "year"])[
            ["pre_profit_payments_usd", "post_profit_payments_usd", "equity_income_usd"]].sum()
        for (iso, y), r in a.iterrows():
            recs.append((iso, int(y), float(r.iloc[0]), float(r.iloc[1]), float(r.iloc[2])))
    fp = EXT_INT / "eiti_folder_summary_splits.csv"
    if fp.exists():
        f = pd.read_csv(fp)
        for _, r in f.iterrows():
            recs.append((r["iso3"], int(r["year"]), float(r["frac_pre_profit"]),
                         float(r["frac_post_profit"]), float(r["frac_equity"])))
    if not recs:
        return {}, {}
    df = pd.DataFrame(recs, columns=["iso", "year", "pre", "post", "eq"]).drop_duplicates(
        ["iso", "year"], keep="first")   # API (added first) wins over folder on the same cell
    df = df.assign(t=df["pre"] + df["post"] + df["eq"])
    df = df[df["t"] > 0]
    df = df.assign(pf=df["pre"] / df["t"], qf=df["post"] / df["t"], ef=df["eq"] / df["t"])
    by_year = {(r.iso, int(r.year)): (r.pf, r.qf, r.ef) for r in df.itertuples()}
    avg = df.groupby("iso")[["pf", "qf", "ef"]].mean()
    by_country = {i: (r.pf, r.qf, r.ef) for i, r in avg.iterrows()}
    return by_year, by_country


def grd_rows(non_eiti_with_manual, eiti_countries, year_set, hq_tbl, ds_tbl=None,
             eiti_by_year=None, eiti_by_country=None, eiti_share_override=None, manual_fhq=None):
    ds_tbl = ds_tbl or {}
    rd = pd.read_csv(ROYALTY_DS)
    rd = rd[rd["year"].isin(year_set)].copy()
    # Per-country commodity mix from WB rents across ALL available years — the fallback
    # split when a year has a GRD total but no year-specific WB split. The WB resource-
    # rent series ends in 2021, so EVERY 2022 GRD total (47 countries) otherwise lacks a
    # split; using the GRD total with the country's own historical mix keeps the real
    # magnitude instead of forcing a needless gap-year extrapolation of a number we have.
    _wbcols = ["wb_oil_rents_usd", "wb_gas_rents_usd", "wb_coal_rents_usd", "wb_mineral_rents_usd"]
    _wb = rd.copy()
    for _c in _wbcols:
        _wb[_c] = pd.to_numeric(_wb[_c], errors="coerce").fillna(0.0)
    _mix = _wb.groupby("iso3")[_wbcols].sum()
    country_split = {}
    for _iso, _r in _mix.iterrows():
        _og = _r["wb_oil_rents_usd"] + _r["wb_gas_rents_usd"]
        _co = _r["wb_coal_rents_usd"]; _mi = _r["wb_mineral_rents_usd"]
        _s = _og + _co + _mi
        if _s > 0:
            country_split[_iso] = {"oil_gas": _og / _s, "coal": _co / _s, "minerals": _mi / _s}
    out = []
    covered = set()
    skip = eiti_countries | non_eiti_with_manual
    for _, row in rd.iterrows():
        iso = row["iso3"]
        if iso in skip:
            continue
        tot = row.get("grd_total_resource_rev_usd")
        if not (isinstance(tot, (int, float)) and np.isfinite(tot) and tot > 0):
            continue
        csplit = _commodity_split_from_wb(row)
        if csplit is None:
            csplit = country_split.get(iso)   # carry the country's historical WB commodity mix
        if csplit is None:
            continue   # no WB rents in ANY year → leave to gap-year extrapolation
        # EITI split-carry: if this country has an EITI-derived split (API
        # bilateral or folder Summary Data, via build_eiti_splits), use it for
        # this GRD-magnitude year instead of the GRD tax-field / resource_taxes
        # fallback — year-specific if available, else the country's average EITI
        # split. Carries each country's own fiscal-regime split onto the years its
        # EITI report is missing (e.g. Kazakhstan 2018/2022, Gabon 2016-2020).
        _sp = None
        if eiti_by_year is not None:
            _sp = eiti_by_year.get((iso, int(row["year"]))) or (eiti_by_country or {}).get(iso)
        if _sp:
            pre_f, post_f, eq_f = _sp
            pre, post, eq = tot * pre_f, tot * post_f, tot * eq_f
        else:
            # pre/post/equity split from the GRD tax breakdown, with sane fallbacks
            post = row.get("grd_tax_income_profits_capgains_resource_usd")
            if not (isinstance(post, (int, float)) and np.isfinite(post)):
                post = row.get("grd_cit_resource_usd")
            if not (isinstance(post, (int, float)) and np.isfinite(post)):
                # No resource income/profit-tax line AND no EITI split: substitute
                # the aggregate `resource_taxes` (GRD tn2021-11: "mostly corporate
                # taxation of resource extraction"), a reasonable post-profit proxy.
                post = row.get("grd_resource_taxes_usd")
            post = float(post) if (isinstance(post, (int, float)) and np.isfinite(post)) else np.nan
            nontax = row.get("grd_nontax_rev_resource_usd")
            nontax = float(nontax) if (isinstance(nontax, (int, float)) and np.isfinite(nontax)) else np.nan
            if np.isnan(post) and np.isnan(nontax):
                pre_f, post_f, eq_f = 0.5, 0.3, 0.2
                pre, post, eq = tot * pre_f, tot * post_f, tot * eq_f
            else:
                post = 0.0 if np.isnan(post) else post
                eq = 0.4 * (0.0 if np.isnan(nontax) else nontax)
                post = min(post, tot); eq = min(eq, max(tot - post, 0.0))
                pre = max(tot - post - eq, 0.0)
        for comm, cf in csplit.items():
            if cf <= 0:
                continue
            # domestic/foreign split: prefer the researched value in the control
            # table; fall back to the per-commodity default.
            dom = ds_tbl.get(iso, DEFAULT_DOMESTIC[comm])
            for d in distribute(iso, comm, int(row["year"]), pre * cf, post * cf, eq * cf, dom, hq_tbl,
                                eiti_share_override=eiti_share_override, manual_fhq=manual_fhq):
                d.update({"source_iso3": iso, "commodity": comm, "year": int(row["year"]), "data_source": "grd_distributed"})
                out.append(d)
        covered.add(iso)
    return (pd.DataFrame(out) if out else pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"])), covered


def extrapolate_gap_years(real_df, covered_pairs, needed_partners, prof, oow_base=None):
    """Fill ANY covered country's missing years — whether the country is on the EITI,
    manual or GRD tier — when a year in the CbCR window has reported CbCR profit but no
    panel row.

    Principle (user, 2026-06): a missing year is almost never "production stopped" —
    it is a data gap (e.g. the GRD series ending in 2021, so Brunei has no 2022 row, or
    an EITI report not yet filed). Dropping the resource correction to zero for that year
    is wrong; instead impute it from the country's OTHER years.

    For each covered source country we take its covered-year-average take per
    (hq_iso3, commodity, bucket) — Σ over covered years ÷ number of covered years,
    preserving the who-paid / commodity structure the real data shows — and scale it for
    each gap year by that year's reported CbCR profit relative to the covered-year-average
    reported profit (clipped to a sane band). The imputed rows are tagged
    `<tier>_extrapolated` after the country's dominant real tier so coverage stays auditable.

    `oow_base` (2026-07-22, user request): OUT-OF-WINDOW EITI rows (2010–2015, 2023+).
    They never enter the output panel (script 4 has no CbCR cells for them), but they DO
    inform the gap-year imputation — EITI 2015 is a good guess for a missing 2016, and an
    EITI 2023 report is a good guess for a missing 2022. They join the take-average /
    structure base; the PROFIT scaler is anchored on in-window covered years only (the
    pre-2026-07-21 code averaged CbCR profit over ALL covered years, so out-of-window
    years entered that mean as zeros — deflating it and inflating the scaler). A country
    whose coverage is ENTIRELY out-of-window has no profit anchor: its take is carried
    unscaled, and only into gap years within OOW_CARRY_MAX_DIST of a covered year
    (e.g. AZE's 2013–2015 EITI → 2016, but never → 2022).

    `real_df` is the concatenated, shadow-filtered EITI+manual+GRD panel; `prof` is a dict
    {(source_iso3, year): reported CbCR profit}. Returns (DataFrame, set of filled pairs)."""
    empty = pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"])
    if not len(real_df):
        return empty, set()
    OOW_CARRY_MAX_DIST = 3   # max |gap year − nearest covered year| for the unscaled carry
    tier_tag = {"eiti_bilateral": "eiti_extrapolated",
                "manual_distributed": "manual_extrapolated",
                "grd_distributed": "grd_extrapolated"}
    if oow_base is not None and len(oow_base):
        base_df = pd.concat([real_df, oow_base], ignore_index=True)
    else:
        base_df = real_df
    out = []
    covered = set()
    for src in sorted(base_df["source_iso3"].dropna().unique()):
        if src not in needed_partners:
            continue
        sub = base_df[base_df["source_iso3"] == src]
        covered_years = sorted(sub["year"].unique())
        n_cov = len(covered_years)
        gap_years = [y for y in YEARS
                     if (src, y) not in covered_pairs and prof.get((src, y), 0.0) > 0]
        if not gap_years or n_cov == 0:
            continue
        agg = sub.groupby(["hq_iso3", "commodity",
                           sub.get("hq_share_basis", pd.Series("unknown", index=sub.index)).rename("hq_share_basis")])[BUCKETS].sum() / n_cov
        # Profit anchor: IN-WINDOW covered years only. Out-of-window years have no
        # CbCR profit, so including them (as the pre-2026-07-21 code did) pulls the
        # mean toward zero and inflates the scaler.
        inw_years = [y for y in covered_years if y in YEARS]
        mean_prof_cov = float(np.mean([prof.get((src, y), 0.0) for y in inw_years])) if inw_years else 0.0
        if inw_years and mean_prof_cov <= 0:
            continue
        tag = tier_tag.get(sub["data_source"].mode().iloc[0], "extrapolated")
        for gy in gap_years:
            if inw_years:
                scaler = float(np.clip(prof.get((src, gy), 0.0) / mean_prof_cov,
                                       EITI_EXTRAP_SCALE_MIN, EITI_EXTRAP_SCALE_MAX))
            else:
                # coverage entirely out-of-window (e.g. AZE: EITI 2013-2015 only):
                # no profit anchor — carry the take unscaled, and only into gap
                # years close to a covered year (2015→2016 yes; 2015→2022 no).
                if min(abs(gy - y) for y in covered_years) > OOW_CARRY_MAX_DIST:
                    continue
                scaler = 1.0
            for (hq, comm, basis), vals in agg.iterrows():
                rec = {b: float(vals[b]) * scaler for b in BUCKETS}
                if sum(abs(v) for v in rec.values()) <= 0:
                    continue
                rec.update({"source_iso3": src, "hq_iso3": hq, "commodity": comm,
                            "year": gy, "data_source": tag, "hq_share_basis": basis})
                out.append(rec)
            covered.add((src, gy))
    return (pd.DataFrame(out) if out else empty), covered


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    year_set = set(YEARS)
    hq_tbl = _hq_share_table()
    cb = pd.read_csv(CBCR_DISAGG, usecols=["iso_parent", "iso_partner", "year", "is_distributed",
                                           "profit_loss_before_income_tax_corrected"], low_memory=False)
    needed_partners = set(cb["iso_partner"].unique())
    # Reported (non-imputed) CbCR profit booked in each source country-year — the
    # scaler for the EITI gap-year extrapolation.
    cb_rep = cb[cb["is_distributed"] == 0]
    prof = (cb_rep.groupby(["iso_partner", "year"])["profit_loss_before_income_tax_corrected"]
            .sum().to_dict())

    # Consolidated control table: which countries are genuine resource economies
    # (drives the final filter) and their researched domestic-vs-foreign split.
    params = pd.read_csv(PARAMS)
    included_iso = set(params.loc[params["include"].astype(str).str.lower() == "yes", "iso3"])
    ds_tbl = pd.to_numeric(params.set_index("iso3")["domestic_share"], errors="coerce").dropna().to_dict()


    print("Building resource_payments_by_hq_source_yearly.csv ...")
    manual_fhq = _manual_foreign_hq_shares()
    if len(manual_fhq):
        print(f"  manual foreign-HQ shares loaded for {sorted(manual_fhq.source_iso3.unique())}")
    ovr = _eiti_hq_share_overrides()
    eiti_df, eiti_countries = eiti_bilateral()
    # Split off out-of-window years (EITI reaches back to 2010 and forward past the
    # window). They never enter the OUTPUT panel (script 4 has no CbCR cells for
    # them), but they DO feed the gap-year extrapolation below — EITI 2015 is a good
    # guess for a missing 2016, EITI 2023 for a missing 2022 (user, 2026-07-22).
    _oow_mask = ~eiti_df["year"].isin(year_set)
    # near-window only (±3y): EITI 2013-2015 / 2023-2025 may inform adjacent gap
    # years, but a 2008 report says little about 2016-2022 levels.
    eiti_oow = eiti_df[_oow_mask
                       & eiti_df["year"].between(min(YEARS) - 3, max(YEARS) + 3)].copy()
    if _oow_mask.any():
        eiti_df = eiti_df[~_oow_mask].copy()
        print(f"  EITI bilateral: {_oow_mask.sum():,} out-of-window rows excluded from the panel; "
              f"{len(eiti_oow):,} near-window rows ({min(YEARS)-3}-{min(YEARS)-1} / "
              f"{max(YEARS)+1}-{max(YEARS)+3}) kept as extrapolation base")
    eiti_df["hq_share_basis"] = "eiti_bilateral"
    eiti_oow["hq_share_basis"] = "eiti_bilateral"
    # Manual-overrides-EITI: drop EITI rows for the override countries so
    # the manual entry below replaces (rather than augments) them.
    if MANUAL_OVERRIDES_EITI:
        n_before = len(eiti_df)
        eiti_df = eiti_df[~eiti_df["source_iso3"].isin(MANUAL_OVERRIDES_EITI)].copy()
        eiti_oow = eiti_oow[~eiti_oow["source_iso3"].isin(MANUAL_OVERRIDES_EITI)].copy()
        eiti_countries = eiti_countries - MANUAL_OVERRIDES_EITI
        print(f"  manual override for {sorted(MANUAL_OVERRIDES_EITI)}: dropped {n_before - len(eiti_df)} EITI rows")

    # Per-(source, year) cascade (2026-05-14): rather than a per-country cascade
    # which would let an EITI-listed country with thin year-coverage block
    # better fallback layers from filling the gaps, we cascade at the
    # (source, year) cell level. EITI bilateral data wins on cells where it
    # has any rows; manual fills cells where EITI is empty for that year;
    # GRD fills where neither EITI nor manual have data; rent_proxy fills
    # the residual (rent > 0 but nothing else).
    #
    # EITI→GRD scale-up (2026-07-19, replacing the EITI_VS_GRD_MIN_RATIO drop):
    # rather than DROP EITI cells that under-capture the GRD total, SCALE the
    # EITI (source, year) rows up so their total matches the GRD total — keeping
    # EITI's HQ allocation and pre/post/equity split while adopting GRD's (more
    # complete) magnitude. Scale UP only (factor ≥ 1); cells where EITI already
    # meets/exceeds GRD keep their EITI total. Scaled rows are tagged
    # data_source="eiti_grdscaled" for auditability.
    grd_raw = pd.read_csv(ROYALTY_DS)
    grd_raw = grd_raw[grd_raw["year"].isin(year_set)].copy()
    grd_totals = (
        grd_raw.set_index(["iso3", "year"])["grd_total_resource_rev_usd"]
        .dropna()
    )
    grd_totals = grd_totals[grd_totals > 0]

    if len(eiti_df):
        eiti_totals_by_pair = (
            eiti_df.groupby(["source_iso3", "year"])[BUCKETS].sum().sum(axis=1)
        )  # Series indexed by (source, year)
        # Scale up only where EITI is representative enough (captures ≥ 1/MAX_SCALE
        # of the GRD total). Where EITI is too thin (factor > MAX_SCALE — it barely
        # captured any operators, so its HQ structure is noise), DROP the cell and
        # let GRD fill it. The factor distribution has an empty gap between ~10×
        # and ~50×, so 10× cleanly separates representative cells (median ~1.3×)
        # from noise (Nigeria 2019 ~100×, Colombia 2019 ~850×).
        MAX_SCALE = 10.0
        scale, drop_pairs = {}, set()
        for key, et in eiti_totals_by_pair.items():
            gt = grd_totals.get(key)
            if gt and et and et > 0 and gt > et:
                f = gt / et
                if f <= MAX_SCALE:
                    scale[key] = f
                else:
                    drop_pairs.add(key)
        if scale:
            fac = np.array([scale.get((s, y), 1.0)
                            for s, y in zip(eiti_df["source_iso3"], eiti_df["year"])])
            for b in BUCKETS:
                eiti_df[b] = eiti_df[b].to_numpy() * fac
            eiti_df["data_source"] = np.where(
                fac > 1.0, "eiti_grdscaled", eiti_df["data_source"].to_numpy())
            print(f"  EITI→GRD scale-up: scaled {len(scale)} (source, year) cells up to the "
                  f"GRD total (median {np.median(list(scale.values())):.1f}×, "
                  f"max {max(scale.values()):.1f}×).")
        if drop_pairs:
            _before = len(eiti_df)
            _keep = ~np.array([(s, y) in drop_pairs
                               for s, y in zip(eiti_df["source_iso3"], eiti_df["year"])])
            eiti_df = eiti_df[_keep].copy()
            print(f"  EITI too thin to scale (< {1 / MAX_SCALE:.0%} of GRD): dropped "
                  f"{_before - len(eiti_df):,} rows in {len(drop_pairs)} cells → GRD fills them "
                  f"({sorted(drop_pairs)[:8]}).")

    eiti_pairs = set(map(tuple, eiti_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))

    parts = [eiti_df]

    man_df, _ = manual_rows(year_set, hq_tbl, manual_fhq=manual_fhq, eiti_overrides=ovr)
    if len(man_df):
        man_pairs_before = set(map(tuple, man_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        man_df = man_df[~man_df[["source_iso3", "year"]].apply(tuple, axis=1).isin(eiti_pairs)].copy()
        manual_pairs = set(map(tuple, man_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        n_shadowed = len(man_pairs_before) - len(manual_pairs)
        parts.append(man_df)
        print(f"  manual_distributed: {len(man_df):,} cells across {len(manual_pairs)} (source, year) pairs "
              f"({n_shadowed} pairs shadowed by EITI)")
    else:
        manual_pairs = set()
        print(f"  manual_distributed: 0 cells")

    eiti_by_year, eiti_by_country = build_eiti_splits(eiti_df)
    print(f"  EITI splits available for split-carry: {len(eiti_by_country)} countries "
          f"({len(eiti_by_year)} country-years)")
    grd_df, _ = grd_rows(set(), set(), year_set, hq_tbl, ds_tbl=ds_tbl,
                         eiti_by_year=eiti_by_year, eiti_by_country=eiti_by_country,
                         eiti_share_override=ovr, manual_fhq=manual_fhq)
    if len(grd_df):
        grd_pairs_before = set(map(tuple, grd_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        grd_df = grd_df[
            ~grd_df[["source_iso3", "year"]].apply(tuple, axis=1).isin(eiti_pairs | manual_pairs)
        ].copy()
        grd_pairs = set(map(tuple, grd_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))
        n_shadowed = len(grd_pairs_before) - len(grd_pairs)
        parts.append(grd_df)
        print(f"  grd_distributed: {len(grd_df):,} cells across {len(grd_pairs)} (source, year) pairs "
              f"({n_shadowed} pairs shadowed by EITI/manual)")
    else:
        grd_pairs = set()
        print(f"  grd_distributed: 0 cells")

    covered_pairs = eiti_pairs | manual_pairs | grd_pairs
    # Gap-year imputation across ALL tiers (EITI / manual / GRD): a missing year with
    # reported CbCR profit is a data gap, not stopped production, so impute it from the
    # country's other years (e.g. GRD ending 2021 -> Brunei 2022).
    real_df = pd.concat([p for p in parts if len(p)], ignore_index=True)
    ext_df, ext_pairs = extrapolate_gap_years(real_df, covered_pairs, needed_partners, prof,
                                              oow_base=eiti_oow)
    if len(ext_df):
        parts.append(ext_df)
        by_tier = ext_df.groupby("data_source")["source_iso3"].nunique().to_dict()
        print(f"  extrapolated gap years: {len(ext_df):,} cells across {len(ext_pairs)} (source, year) pairs "
              f"(scaled by reported CbCR profit); by tier {by_tier}")
    else:
        print(f"  extrapolated gap years: 0 cells")

    df = pd.concat([p for p in parts if len(p)], ignore_index=True)
    # Keep only genuine resource economies (the control table's include flag).
    # Non-resource countries are dropped here and get no correction in script 4.
    n_src_before = df["source_iso3"].nunique()
    df = df[df["source_iso3"].isin(included_iso)].copy()
    print(f"  include filter: kept {df['source_iso3'].nunique()}/{n_src_before} source countries "
          f"(dropped non-resource economies per resource_country_parameters.csv)")
    for b in BUCKETS:
        df[b] = pd.to_numeric(df[b], errors="coerce").fillna(0.0)
    # pre-profit / equity / other can never be negative as a *base* to add back; net EITI refunds
    # recorded as negative payments are floored at 0 per cell.  post_profit is left signed so that a
    # net corporate-tax refund (e.g. UK decommissioning relief) flows through to a profit_after > reported.
    for b in ("pre_profit_payments_usd", "equity_income_usd", "other_payments_usd"):
        df[b] = df[b].clip(lower=0.0)
    # collapse any duplicate (source,hq,commodity,year,data_source) rows produced by distribute()
    df["hq_share_basis"] = df.get("hq_share_basis", pd.Series(index=df.index, dtype=object)).fillna("unknown")
    df = (df.groupby(["source_iso3", "hq_iso3", "commodity", "year", "data_source", "hq_share_basis"],
                     as_index=False)[BUCKETS].sum())
    # drop all-zero rows
    df = df[df[BUCKETS].abs().sum(axis=1) > 0].copy()
    df = df.sort_values(["source_iso3", "year", "commodity", "hq_iso3"]).reset_index(drop=True)
    df.to_csv(OUT, index=False)

    # coverage report
    cov = (df.groupby(["source_iso3", "data_source"], as_index=False)[BUCKETS].sum())
    cov["total_usd"] = cov[BUCKETS].sum(axis=1)
    cov = cov.sort_values(["data_source", "total_usd"], ascending=[True, False])
    cov.to_csv(OUT_COV, index=False)

    tot = df[BUCKETS].sum()
    print(f"\nWrote {OUT}  ({len(df):,} rows; {df.source_iso3.nunique()} source countries, {df.hq_iso3.nunique()} HQ countries, years {df.year.min()}-{df.year.max()})")
    print(f"  Σ pre_profit  ${tot['pre_profit_payments_usd']/1e9:,.0f} B")
    print(f"  Σ post_profit ${tot['post_profit_payments_usd']/1e9:,.0f} B")
    print(f"  Σ equity      ${tot['equity_income_usd']/1e9:,.0f} B")
    print(f"  Σ other       ${tot['other_payments_usd']/1e9:,.0f} B")
    print(f"  by data_source ($B):")
    for ds, v in df.groupby("data_source")[BUCKETS].sum().sum(axis=1).sort_values(ascending=False).items():
        print(f"    {ds:20s} {v/1e9:,.0f}")
    print(f"  by hq_share_basis ($B; foreign rows only):")
    fr = df[df.hq_iso3 != df.source_iso3]
    for bs, v in fr.groupby("hq_share_basis")[BUCKETS].sum().sum(axis=1).sort_values(ascending=False).items():
        print(f"    {bs:20s} {v/1e9:,.0f}")
    print(f"  Wrote {OUT_COV}")


if __name__ == "__main__":
    main()
