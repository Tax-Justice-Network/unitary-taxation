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

Inputs : data/intermediate/extractive/eiti_company_payments_long.csv     (1_6)
         data/intermediate/extractive/eiti_company_hq_map.csv            (1_7)
         data/intermediate/extractive/extractive_royalty_dataset_yearly.csv  (GRD + WB rents, USD)
         data/intermediate/extractive/hq_shares_by_commodity_yearly.csv  (3_2)
         data/raw/resources/manual_resource_revenue.csv
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


def distribute(source_iso3, commodity, year, amount_pre, amount_post, amount_eq, domestic_share, hq_tbl,
               eiti_share_override=None):
    """Split a source-country (commodity, year) total into (hq_iso3) rows.

    domestic_share lands on the source country itself (its NOC); the rest is spread over
    the *foreign* HQ shares for that commodity-year (the source country removed & renormalised).

    If `eiti_share_override` (a DataFrame with source_iso3, year, commodity, hq_iso3, share)
    has rows matching this (source, year, commodity), those shares replace the generic hq_tbl
    foreign-share weighting — used to anchor manual-distributed totals on the operator-level
    EITI bilateral data when both exist (Item A fix, 2026-05-15).

    Returns a list of dicts with hq_iso3 + the four buckets."""
    rows = []
    dom = float(np.clip(domestic_share, 0.0, 1.0))
    if dom > 0:
        rows.append({"hq_iso3": source_iso3, "pre_profit_payments_usd": amount_pre * dom,
                     "post_profit_payments_usd": amount_post * dom, "equity_income_usd": amount_eq * dom,
                     "other_payments_usd": 0.0})

    # Source-specific EITI-derived shares (if available) take precedence over generic Orbis hq_tbl.
    foreign = None
    if eiti_share_override is not None and len(eiti_share_override):
        ev = eiti_share_override[
            (eiti_share_override["source_iso3"] == source_iso3)
            & (eiti_share_override["year"] == year)
            & (eiti_share_override["commodity"] == commodity)
            & (eiti_share_override["hq_iso3"] != source_iso3)
        ]
        if len(ev):
            foreign = ev.copy()
    if foreign is None:
        foreign = hq_tbl[(hq_tbl.year == year) & (hq_tbl.commodity == commodity) & (hq_tbl.hq_iso3 != source_iso3)]

    fsum = foreign["share"].sum()
    if (1 - dom) > 0 and fsum > 0:
        for _, r in foreign.iterrows():
            w = (r["share"] / fsum) * (1 - dom)
            rows.append({"hq_iso3": r["hq_iso3"], "pre_profit_payments_usd": amount_pre * w,
                         "post_profit_payments_usd": amount_post * w, "equity_income_usd": amount_eq * w,
                         "other_payments_usd": 0.0})
    elif (1 - dom) > 0:
        # no foreign-share info → put the remainder on the source country too
        rows.append({"hq_iso3": source_iso3, "pre_profit_payments_usd": amount_pre * (1 - dom),
                     "post_profit_payments_usd": amount_post * (1 - dom), "equity_income_usd": amount_eq * (1 - dom),
                     "other_payments_usd": 0.0})
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
def manual_rows(year_set, hq_tbl):
    m = pd.read_csv(MANUAL, comment="#")
    m = m[m["year"].isin(year_set)]
    # Build hq-shares override merging EITI bilateral + operator-side P2G data.
    # Item A fix (2026-05-15): used to be COD/PER/MEX only (those have manual
    # totals overriding EITI). Extended (later same day) to ALL manual entries —
    # operator P2G data (TotalEnergies/Eni/BP/Glencore/Vale/Sasol/Galp/etc.)
    # anchors the hq-share for any (source, year, commodity) cell where it
    # exists, even for countries with no EITI presence (e.g. SAU/SDN/SSD/YEM/etc.).
    eiti_overrides = _eiti_hq_share_overrides()
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
                            eiti_share_override=override_df):
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


def grd_rows(non_eiti_with_manual, eiti_countries, year_set, hq_tbl, ds_tbl=None):
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
        # pre/post/equity split from the GRD tax breakdown, with sane fallbacks
        post = row.get("grd_tax_income_profits_capgains_resource_usd")
        if not (isinstance(post, (int, float)) and np.isfinite(post)):
            post = row.get("grd_cit_resource_usd")
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
            for d in distribute(iso, comm, int(row["year"]), pre * cf, post * cf, eq * cf, dom, hq_tbl):
                d.update({"source_iso3": iso, "commodity": comm, "year": int(row["year"]), "data_source": "grd_distributed"})
                out.append(d)
        covered.add(iso)
    return (pd.DataFrame(out) if out else pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"])), covered


def extrapolate_gap_years(real_df, covered_pairs, needed_partners, prof):
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

    `real_df` is the concatenated, shadow-filtered EITI+manual+GRD panel; `prof` is a dict
    {(source_iso3, year): reported CbCR profit}. Returns (DataFrame, set of filled pairs)."""
    empty = pd.DataFrame(columns=["source_iso3", "hq_iso3", "commodity", "year"] + BUCKETS + ["data_source"])
    if not len(real_df):
        return empty, set()
    tier_tag = {"eiti_bilateral": "eiti_extrapolated",
                "manual_distributed": "manual_extrapolated",
                "grd_distributed": "grd_extrapolated"}
    out = []
    covered = set()
    for src in sorted(real_df["source_iso3"].dropna().unique()):
        if src not in needed_partners:
            continue
        sub = real_df[real_df["source_iso3"] == src]
        covered_years = sorted(sub["year"].unique())
        n_cov = len(covered_years)
        gap_years = [y for y in YEARS
                     if (src, y) not in covered_pairs and prof.get((src, y), 0.0) > 0]
        if not gap_years or n_cov == 0:
            continue
        agg = sub.groupby(["hq_iso3", "commodity"])[BUCKETS].sum() / n_cov
        mean_prof_cov = float(np.mean([prof.get((src, y), 0.0) for y in covered_years]))
        if mean_prof_cov <= 0:
            continue
        tag = tier_tag.get(sub["data_source"].mode().iloc[0], "extrapolated")
        for gy in gap_years:
            scaler = float(np.clip(prof.get((src, gy), 0.0) / mean_prof_cov,
                                   EITI_EXTRAP_SCALE_MIN, EITI_EXTRAP_SCALE_MAX))
            for (hq, comm), vals in agg.iterrows():
                rec = {b: float(vals[b]) * scaler for b in BUCKETS}
                if sum(abs(v) for v in rec.values()) <= 0:
                    continue
                rec.update({"source_iso3": src, "hq_iso3": hq, "commodity": comm,
                            "year": gy, "data_source": tag})
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

    # Quality threshold for EITI-vs-GRD comparison (2026-05-14, per user):
    # when EITI bilateral total for (source, year) is below this fraction of
    # the GRD-reported total resource revenue for the same source-year, we
    # fall back to GRD instead. Captures the "EITI bilateral is materially
    # smaller than what GRD says" case (typical when EITI bilateral only
    # covers a subset of operators, e.g. payments from the largest mining
    # MNEs, while GRD captures the full government take). Threshold of 0.8
    # means: switch to GRD whenever EITI is less than 80% of GRD.
    EITI_VS_GRD_MIN_RATIO = 0.8

    print("Building resource_payments_by_hq_source_yearly.csv ...")
    eiti_df, eiti_countries = eiti_bilateral()
    # Manual-overrides-EITI: drop EITI rows for the override countries so
    # the manual entry below replaces (rather than augments) them.
    if MANUAL_OVERRIDES_EITI:
        n_before = len(eiti_df)
        eiti_df = eiti_df[~eiti_df["source_iso3"].isin(MANUAL_OVERRIDES_EITI)].copy()
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
    # Quality check: also drop EITI rows where the bilateral total for the
    # (source, year) is materially smaller than what GRD reports for the
    # same source-year (likely "EITI bilateral only captured a subset of
    # operators" pattern). The threshold EITI_VS_GRD_MIN_RATIO controls
    # the switch.
    if len(eiti_df):
        eiti_totals_by_pair = (
            eiti_df.groupby(["source_iso3", "year"])[BUCKETS].sum().sum(axis=1)
        )  # Series indexed by (source, year)
    else:
        eiti_totals_by_pair = pd.Series(dtype=float)

    grd_raw = pd.read_csv(ROYALTY_DS)
    grd_raw = grd_raw[grd_raw["year"].isin(year_set)].copy()
    grd_totals = (
        grd_raw.set_index(["iso3", "year"])["grd_total_resource_rev_usd"]
        .dropna()
    )
    grd_totals = grd_totals[grd_totals > 0]

    pairs_eiti_too_small = set()
    for key, eiti_total in eiti_totals_by_pair.items():
        grd_total = grd_totals.get(key)
        if grd_total and grd_total > 0 and eiti_total < EITI_VS_GRD_MIN_RATIO * grd_total:
            pairs_eiti_too_small.add(key)

    if pairs_eiti_too_small:
        before = len(eiti_df)
        eiti_df = eiti_df[
            ~eiti_df[["source_iso3", "year"]].apply(tuple, axis=1).isin(pairs_eiti_too_small)
        ].copy()
        print(f"  EITI-vs-GRD quality check: dropped {before - len(eiti_df):,} EITI rows in "
              f"{len(pairs_eiti_too_small)} (source, year) pairs where EITI bilateral "
              f"< {EITI_VS_GRD_MIN_RATIO:.0%} of GRD total. Affected pairs (sample): "
              f"{sorted(pairs_eiti_too_small)[:10]}")

    eiti_pairs = set(map(tuple, eiti_df[["source_iso3", "year"]].drop_duplicates().itertuples(index=False, name=None)))

    parts = [eiti_df]

    man_df, _ = manual_rows(year_set, hq_tbl)
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

    grd_df, _ = grd_rows(set(), set(), year_set, hq_tbl, ds_tbl=ds_tbl)
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
    ext_df, ext_pairs = extrapolate_gap_years(real_df, covered_pairs, needed_partners, prof)
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
    df = (df.groupby(["source_iso3", "hq_iso3", "commodity", "year", "data_source"], as_index=False)[BUCKETS].sum())
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
    print(f"  Wrote {OUT_COV}")


if __name__ == "__main__":
    main()
