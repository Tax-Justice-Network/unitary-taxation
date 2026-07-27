# %%
"""
3_37 — Build per-source-country HQ shares by commodity.

Build the per-(source_country, commodity, year) HQ-share table — the bilateral
ownership base for script 4's minimum-royalty floor and the exploratory resource
factor. For each (entity_country=S, guo_country=H, commodity=C, year=Y), sum
'Operating revenue Y' across matching entities and normalise within each (S, C,
Y) group (share sums to 1.0). Entities without revenue in year Y fall back to
peak_operating_revenue_th_usd / n_years_with_revenue (per-bvd_id); entities with
missing HQ (guo_country, entity_country fallback) or proxy revenue < $100k are
dropped. If a (source, commodity, year) group has < 3 distinct entities OR
aggregate revenue < $10M USD, fall back to the GLOBAL HQ share from
hq_shares_by_commodity_yearly.csv (flagged fallback=True). Reuses the
NACE→commodity mapping and segment-overrides logic from 3_36 (oil_gas | minerals
| coal).

Extractive prep, stage 3_37 — after 3_36, before 3_38.

Reads:
  data/raw/extractive/orbis_extractives_broad{1,2}.csv            — broad Orbis extractive pull
  data/raw/orbis/company_segment_overrides.csv                    — commodity-segment overrides
  data/intermediate/extractive/hq_shares_by_commodity_yearly.csv  — global HQ shares (3_36; small-market fallback)

Writes:
  data/intermediate/extractive/hq_shares_by_source_commodity_yearly.csv
    columns: source_iso3, hq_iso3, commodity, year, share, fallback

Usage:
  python 3_37_build_hq_shares_by_source.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import os
import sys
import csv
import re
from collections import defaultdict

import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT  # noqa: E402

INPUT_FILES = ["orbis_extractives_broad1.csv", "orbis_extractives_broad2.csv"]
OVERRIDES_FILE = os.path.join(RAW, "orbis/company_segment_overrides.csv")
GLOBAL_HQ_SHARES = os.path.join(EXT_INT, "hq_shares_by_commodity_yearly.csv")
OUTPUT = os.path.join(EXT_INT, "hq_shares_by_source_commodity_yearly.csv")

YEARS = list(range(2016, 2023))

EXTRACTIVE_CODE_PREFIXES = ("05", "06", "07", "08", "09")
EXTRACTIVE_SPECIAL_CODES = {"1920", "4671"}

SOE_PARENT_PREFIXES = [
    "CHINA NATIONAL PETROLEUM CORPORATION",
    "CHINA PETROLEUM & CHEMICAL CORPORATION",
    "SINOPEC",
    "PETROCHINA",
    "CNOOC",
]

MIN_ENTITY_REV_USD = 100_000.0       # drop rows below this proxy revenue
SMALL_MARKET_MIN_ENTITIES = 3
SMALL_MARKET_MIN_REV_USD = 10_000_000.0

ISO2_TO_ISO3 = {
    "AE":"ARE","AF":"AFG","AG":"ATG","AL":"ALB","AM":"ARM","AO":"AGO","AR":"ARG","AT":"AUT","AU":"AUS","AZ":"AZE",
    "BA":"BIH","BB":"BRB","BD":"BGD","BE":"BEL","BF":"BFA","BG":"BGR","BH":"BHR","BI":"BDI","BJ":"BEN","BM":"BMU",
    "BN":"BRN","BO":"BOL","BR":"BRA","BS":"BHS","BT":"BTN","BW":"BWA","BY":"BLR","BZ":"BLZ","CA":"CAN","CD":"COD",
    "CF":"CAF","CG":"COG","CH":"CHE","CI":"CIV","CL":"CHL","CM":"CMR","CN":"CHN","CO":"COL","CR":"CRI","CU":"CUB",
    "CV":"CPV","CW":"CUW","CY":"CYP","CZ":"CZE","DE":"DEU","DJ":"DJI","DK":"DNK","DM":"DMA","DO":"DOM","DZ":"DZA",
    "EC":"ECU","EE":"EST","EG":"EGY","ER":"ERI","ES":"ESP","ET":"ETH","FI":"FIN","FJ":"FJI","FR":"FRA","GA":"GAB",
    "GB":"GBR","GE":"GEO","GH":"GHA","GM":"GMB","GN":"GIN","GQ":"GNQ","GR":"GRC","GT":"GTM","GW":"GNB","GY":"GUY",
    "HK":"HKG","HN":"HND","HR":"HRV","HT":"HTI","HU":"HUN","ID":"IDN","IE":"IRL","IL":"ISR","IN":"IND","IQ":"IRQ",
    "IR":"IRN","IS":"ISL","IT":"ITA","JM":"JAM","JO":"JOR","JP":"JPN","KE":"KEN","KG":"KGZ","KH":"KHM","KM":"COM",
    "KR":"KOR","KW":"KWT","KY":"CYM","KZ":"KAZ","LA":"LAO","LB":"LBN","LK":"LKA","LR":"LBR","LS":"LSO","LT":"LTU",
    "LU":"LUX","LV":"LVA","LY":"LBY","MA":"MAR","MC":"MCO","MD":"MDA","ME":"MNE","MG":"MDG","MK":"MKD","ML":"MLI",
    "MM":"MMR","MN":"MNG","MO":"MAC","MR":"MRT","MT":"MLT","MU":"MUS","MV":"MDV","MW":"MWI","MX":"MEX","MY":"MYS",
    "MZ":"MOZ","NA":"NAM","NE":"NER","NG":"NGA","NI":"NIC","NL":"NLD","NO":"NOR","NP":"NPL","NZ":"NZL","OM":"OMN",
    "PA":"PAN","PE":"PER","PG":"PNG","PH":"PHL","PK":"PAK","PL":"POL","PR":"PRI","PS":"PSE","PT":"PRT","PY":"PRY",
    "QA":"QAT","RO":"ROU","RS":"SRB","RU":"RUS","RW":"RWA","SA":"SAU","SC":"SYC","SD":"SDN","SE":"SWE","SG":"SGP",
    "SI":"SVN","SK":"SVK","SL":"SLE","SN":"SEN","SO":"SOM","SR":"SUR","SS":"SSD","SV":"SLV","SY":"SYR","SZ":"SWZ",
    "TD":"TCD","TG":"TGO","TH":"THA","TJ":"TJK","TM":"TKM","TN":"TUN","TR":"TUR","TT":"TTO","TW":"TWN","TZ":"TZA",
    "UA":"UKR","UG":"UGA","US":"USA","UY":"URY","UZ":"UZB","VE":"VEN","VG":"VGB","VN":"VNM","YE":"YEM","ZA":"ZAF",
    "ZM":"ZMB","ZW":"ZWE",
}


# %% MARK: 2. Helpers
# ── Helpers (mirrored from 3_36_compute_hq_shares_yearly.py) ──

def _normalise_code(raw):
    if raw is None:
        return ""
    if isinstance(raw, float):
        if pd.isna(raw):
            return ""
        raw = int(raw)
    s = str(raw).strip()
    if not s or s.lower() in ("n.a.", "nan", "none", ""):
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    s = re.sub(r"\D", "", s)
    if not s:
        return ""
    return s.zfill(4)


def parse_codes(s):
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    if isinstance(s, (int, float)):
        c = _normalise_code(s)
        return [c] if c else []
    raw = str(s).strip()
    if not raw or raw.lower() in ("n.a.", "nan", "none"):
        return []
    parts = re.split(r"[,;\s]+", raw)
    out = []
    for p in parts:
        c = _normalise_code(p)
        if c:
            out.append(c)
    return out


def is_extractive(codes):
    for c in codes:
        if c in EXTRACTIVE_SPECIAL_CODES:
            return True
        if len(c) >= 2 and c[:2] in EXTRACTIVE_CODE_PREFIXES:
            return True
    return False


def _bucket_for_codes(codes):
    for c in codes:
        if c.startswith("06") or c == "1920" or c == "4671" or c.startswith("09"):
            return "oil_gas"
    for c in codes:
        if c.startswith("05"):
            return "coal"
    for c in codes:
        if c.startswith("07") or c.startswith("08"):
            return "minerals"
    return None


def codes_to_commodity(primary_codes, secondary_codes):
    bucket = _bucket_for_codes(primary_codes)
    if bucket is None:
        bucket = _bucket_for_codes(secondary_codes)
    return bucket or "unknown"


def parse_num(v):
    if pd.isna(v):
        return None
    s = str(v).strip()
    if not s or s.lower() in ("n.a.", "nan", "none", "-"):
        return None
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def load_overrides(path):
    if not os.path.exists(path):
        return []
    overrides = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = next(csv.reader([line]))
            if parts and parts[0] == "bvd_id":
                continue
            if len(parts) < 5:
                continue
            bvd_id, name_contains, og, mi, co = parts[0], parts[1], parts[2], parts[3], parts[4]
            try:
                og_s = float(og) if og else 0.0
                mi_s = float(mi) if mi else 0.0
                co_s = float(co) if co else 0.0
            except ValueError:
                continue
            overrides.append({
                "bvd_id": bvd_id.strip(),
                "name_upper": name_contains.strip().upper(),
                "oil_gas": og_s, "minerals": mi_s, "coal": co_s,
            })
    return overrides


def match_override(bvd_id, name, overrides):
    name_u = (name or "").upper()
    for ov in overrides:
        if ov["bvd_id"] and ov["bvd_id"] == bvd_id:
            return ov
    for ov in overrides:
        if ov["name_upper"] and ov["name_upper"] in name_u:
            return ov
    return None


# %% MARK: 3. Load and prepare data
# ── Main ──

print("Loading Orbis broad export CSVs...")
dfs = []
for fname in INPUT_FILES:
    path = os.path.join(RAW, "extractive", fname)
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False,
                     na_values=["n.a.", "n.s.", "-"], keep_default_na=True)
    print(f"  {fname}: {len(df):,} rows")
    dfs.append(df)

df = pd.concat(dfs, ignore_index=True)
df.columns = [c.strip() for c in df.columns]
for dup in ["Country ISO code.1", "Consolidation code.1", "Unnamed: 0"]:
    if dup in df.columns:
        df = df.drop(columns=[dup])
print(f"  Combined: {len(df):,} rows")

# Parse NACE codes
df["_primary_codes"] = df["NACE Rev. 2, primary code(s)"].apply(parse_codes)
df["_secondary_codes"] = df["NACE Rev. 2, secondary code(s)"].apply(parse_codes)
core_col = "NACE Rev. 2, core code (4 digits)"
if core_col in df.columns:
    df["_core_code"] = df[core_col].apply(parse_codes)
else:
    df["_core_code"] = [[] for _ in range(len(df))]
df["_all_codes"] = df.apply(lambda r: r["_primary_codes"] + r["_secondary_codes"] + r["_core_code"], axis=1)

before = len(df)
df = df[df["_all_codes"].apply(is_extractive)].copy()
print(f"Extractive filter: {before:,} → {len(df):,} rows")


def _commodity(r):
    primary = r["_primary_codes"] + r["_core_code"]
    return codes_to_commodity(primary, r["_secondary_codes"])
df["_commodity"] = df.apply(_commodity, axis=1)

df["_bvd_id"] = df["BvD ID number"].astype(str).str.strip()
df["_guo_id"] = df["GUO - BvD ID number"].astype(str).str.strip().replace({"nan": "", "None": ""})
df["_guo_country"] = df["GUO - Country ISO code"].astype(str).str.strip().replace({"nan": "", "None": ""})
df["_entity_country"] = df["Country ISO code"].astype(str).str.strip()
df["_name_upper"] = df["Company name"].astype(str).str.upper().str.strip()

overrides = load_overrides(OVERRIDES_FILE)
print(f"Loaded {len(overrides)} segment overrides")

# Pre-compute HQ ISO3 per row (GUO country, fallback to entity country)
def _hq_iso3(row):
    guo = row["_guo_country"]
    if guo.lower() in ("n.a.", "nan", "none", "", "ww", "yy", "zz"):
        guo = ""
    iso2 = guo if guo else row["_entity_country"]
    if not iso2:
        return ""
    return ISO2_TO_ISO3.get(iso2, iso2)
df["_hq_iso3"] = df.apply(_hq_iso3, axis=1)

# Source ISO3 = entity_country
df["_source_iso3"] = df["_entity_country"].map(lambda x: ISO2_TO_ISO3.get(x, x) if x else "")

# Parse all year revenues once
rev_cols = {}
for y in YEARS:
    c = f"Operating revenue (Turnover) th USD {y}"
    if c in df.columns:
        df[f"_rev_{y}"] = df[c].apply(parse_num)
        rev_cols[y] = f"_rev_{y}"

# Build proxy revenue for entities missing year-specific data:
#   proxy = peak_th_usd over all years / number_of_years_with_revenue
# peak_th_usd = max of revenue across all years; n_years = count years with rev > 0
rev_matrix = df[[rev_cols[y] for y in YEARS if y in rev_cols]]
df["_peak_th_usd"] = rev_matrix.max(axis=1)
df["_n_years_rev"] = (rev_matrix > 0).sum(axis=1)
df["_proxy_th_usd"] = df.apply(
    lambda r: (r["_peak_th_usd"] / r["_n_years_rev"]) if r["_n_years_rev"] > 0 else None,
    axis=1,
)

# Effective per-year revenue: year-specific if present, else proxy
def _effective_rev(year):
    col = rev_cols.get(year)
    if col is None:
        return df["_proxy_th_usd"]
    return df[col].where(df[col].notna() & (df[col] > 0), df["_proxy_th_usd"])

# %% MARK: 4. Per-source HQ shares
print("\nProcessing years...")
out_rows = []
year_summaries = []

# Load global per-(hq, commodity) shares for the small-market fallback
print(f"Loading global HQ shares from {os.path.basename(GLOBAL_HQ_SHARES)}...")
global_hq = pd.read_csv(GLOBAL_HQ_SHARES)
# columns: year, hq_iso3, commodity, revenue_usd, share

for year in YEARS:
    rev_eff = _effective_rev(year)
    sub = df[rev_eff.notna() & (rev_eff > 0)].copy()
    sub["_rev_eff_usd"] = rev_eff[rev_eff.notna() & (rev_eff > 0)] * 1000.0

    # GUO dedup per year (keep largest row per group)
    sub["_group_key"] = sub.apply(
        lambda r: r["_guo_id"] if r["_guo_id"] and r["_guo_id"].lower() not in ("n.a.", "") else r["_bvd_id"],
        axis=1,
    )
    n_before = len(sub)
    sub = sub.sort_values("_rev_eff_usd", ascending=False).drop_duplicates(subset="_group_key", keep="first").copy()

    # SOE branch dedup
    soe_mask = pd.Series(False, index=sub.index)
    for prefix in SOE_PARENT_PREFIXES:
        m = sub["_name_upper"].str.startswith(prefix)
        if m.sum() <= 1:
            continue
        idx = sub.index[m]
        parent = sub.loc[idx, "_rev_eff_usd"].idxmax()
        soe_mask.loc[[i for i in idx if i != parent]] = True
    sub = sub[~soe_mask].copy()

    # Drop missing source or HQ
    sub = sub[(sub["_source_iso3"] != "") & (sub["_hq_iso3"] != "")]
    # Drop tiny entities
    sub = sub[sub["_rev_eff_usd"] >= MIN_ENTITY_REV_USD]

    # Aggregate revenue by (source, hq, commodity), applying overrides
    #   commodity weighting: overrides split a row across commodities
    src_hq_com_rev = defaultdict(float)
    for _, row in sub.iterrows():
        rev = row["_rev_eff_usd"]
        bvd_id = row["_bvd_id"]
        name = str(row.get("Company name", "")).strip()
        nace_com = row["_commodity"]
        src = row["_source_iso3"]
        hq = row["_hq_iso3"]
        ov = match_override(bvd_id, name, overrides)
        if ov is not None:
            parts = [("oil_gas", rev * ov["oil_gas"]),
                     ("minerals", rev * ov["minerals"]),
                     ("coal", rev * ov["coal"])]
        else:
            parts = [(nace_com, rev)] if nace_com in ("oil_gas", "minerals", "coal") else []
        for com, v in parts:
            if v > 0:
                src_hq_com_rev[(src, com, hq)] += v

    # Compute (source, commodity) totals + entity counts
    src_com_total = defaultdict(float)
    src_com_entity_count = defaultdict(set)
    for (src, com, hq), v in src_hq_com_rev.items():
        src_com_total[(src, com)] += v
        src_com_entity_count[(src, com)].add(hq)
    # We also need entity count from raw rows (not HQs), so re-derive:
    # number of distinct bvd_ids per (source, commodity)
    src_com_n_entities = defaultdict(set)
    for _, row in sub.iterrows():
        nace_com = row["_commodity"]
        # apply override commodity split into ANY positive bucket
        bvd_id = row["_bvd_id"]
        name = str(row.get("Company name", "")).strip()
        ov = match_override(bvd_id, name, overrides)
        coms = []
        if ov is not None:
            for cn in ("oil_gas", "minerals", "coal"):
                if ov[cn] > 0:
                    coms.append(cn)
        elif nace_com in ("oil_gas", "minerals", "coal"):
            coms = [nace_com]
        for c in coms:
            src_com_n_entities[(row["_source_iso3"], c)].add(bvd_id)

    # Build global fallback share dict for this year
    g_year = global_hq[global_hq["year"] == year]
    global_share = defaultdict(dict)  # commodity -> hq -> share
    for _, gr in g_year.iterrows():
        global_share[gr["commodity"]][gr["hq_iso3"]] = float(gr["share"])

    # Emit rows
    all_src_com = set(src_com_total.keys())
    # Also include source/commodity combos that exist but had revenue 0 (none if total=0; skip)
    n_normal = 0
    n_fallback = 0
    for (src, com) in all_src_com:
        total = src_com_total[(src, com)]
        n_ent = len(src_com_n_entities.get((src, com), set()))
        use_fallback = (n_ent < SMALL_MARKET_MIN_ENTITIES) or (total < SMALL_MARKET_MIN_REV_USD)

        if use_fallback and com in global_share and global_share[com]:
            # Use global per-commodity HQ shares
            gs = global_share[com]
            tot_share = sum(gs.values()) or 1.0
            for hq, sh in gs.items():
                out_rows.append({
                    "source_iso3": src, "hq_iso3": hq, "commodity": com,
                    "year": year, "share": sh / tot_share, "fallback": True,
                })
            n_fallback += 1
        else:
            if total <= 0:
                continue
            for (s2, c2, hq), v in src_hq_com_rev.items():
                if s2 == src and c2 == com:
                    out_rows.append({
                        "source_iso3": src, "hq_iso3": hq, "commodity": com,
                        "year": year, "share": v / total, "fallback": False,
                    })
            n_normal += 1

    year_summaries.append({
        "year": year, "entities_after_dedup": len(sub),
        "src_com_groups": len(all_src_com),
        "normal_groups": n_normal, "fallback_groups": n_fallback,
        "total_revenue_bn": sum(src_hq_com_rev.values()) / 1e9,
    })
    print(f"  {year}: {n_before:,} rows w/ rev → {len(sub):,} post-dedup; "
          f"{len(all_src_com):,} (src,com) groups ({n_normal} direct, {n_fallback} fallback); "
          f"${sum(src_hq_com_rev.values())/1e9:.0f}B")

# %% MARK: 5. Write and validate
# Write output
print(f"\nWriting {OUTPUT} ...")
with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["source_iso3", "hq_iso3", "commodity", "year", "share", "fallback"])
    w.writeheader()
    for r in out_rows:
        w.writerow({
            "source_iso3": r["source_iso3"],
            "hq_iso3": r["hq_iso3"],
            "commodity": r["commodity"],
            "year": r["year"],
            "share": f"{r['share']:.6f}",
            "fallback": "True" if r["fallback"] else "False",
        })

print(f"Wrote {len(out_rows):,} rows to {OUTPUT}")
file_size = os.path.getsize(OUTPUT)
print(f"File size: {file_size/1024:.1f} KB")

# Validation: shares sum to 1 within each (source, commodity, year)
print("\nValidating share sums...")
out_df = pd.DataFrame(out_rows)
sums = out_df.groupby(["source_iso3", "commodity", "year"])["share"].sum()
bad = sums[(sums - 1.0).abs() > 1e-6]
print(f"  {len(sums):,} (source, commodity, year) groups")
print(f"  {len(bad):,} groups with sum != 1.0 ± 1e-6")
if len(bad):
    print("  Examples of bad groups:")
    print(bad.head(5))

# Sanity checks for SAU, AUS, NOR, BRA
print("\n" + "=" * 72)
print("SANITY CHECKS (year=2021)")
print("=" * 72)
checks = [
    ("SAU", "oil_gas"),
    ("AUS", "minerals"),
    ("NOR", "oil_gas"),
    ("BRA", "oil_gas"),
]
for src, com in checks:
    sel = out_df[(out_df["source_iso3"] == src) & (out_df["commodity"] == com) & (out_df["year"] == 2021)]
    if sel.empty:
        print(f"\n{src} {com}: no data")
        continue
    is_fb = bool(sel["fallback"].iloc[0])
    sel = sel.sort_values("share", ascending=False).head(6)
    print(f"\n{src} {com} (fallback={is_fb}):")
    for _, r in sel.iterrows():
        print(f"  {r['hq_iso3']:<5} {r['share']*100:>6.1f}%")

# Yearly summary
print("\n" + "=" * 72)
print("YEARLY SUMMARY")
print("=" * 72)
print(f"{'Year':<6} {'Entities':>10} {'Groups':>8} {'Direct':>8} {'Fallback':>10} {'Rev $B':>10}")
for s in year_summaries:
    print(f"  {s['year']:<4} {s['entities_after_dedup']:>10,} {s['src_com_groups']:>8,} "
          f"{s['normal_groups']:>8,} {s['fallback_groups']:>10,} {s['total_revenue_bn']:>10,.0f}")
