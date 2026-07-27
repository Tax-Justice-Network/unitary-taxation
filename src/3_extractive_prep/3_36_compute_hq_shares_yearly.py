# %%
"""
3_36 — Compute global HQ shares by commodity, yearly.

Compute HQ shares by commodity for each year 2016-2022 to match the CbCR
reporting window. The revenue column and the per-GUO deduplication are applied
PER YEAR: companies with no revenue reported in a given year are excluded that
year; GUO dedup picks the biggest-revenue subsidiary in each year separately (a
different subsidiary may dominate in different years); SOE branch dedup is also
applied per year.

Extractive prep, stage 3_36 — after 3_35, before 3_37.

Reads:
  data/raw/extractive/orbis_extractives_broad{1,2}.csv  — broad Orbis extractive pull
  data/raw/orbis/company_segment_overrides.csv          — commodity-segment overrides

Writes (data/intermediate/extractive/):
  hq_shares_by_commodity_yearly.csv  — THE pipeline-consumed global HQ shares (read by 3_38,
    script 4, config.py); long: year, hq_iso3, commodity, revenue_usd, share
  hq_shares_by_commodity_orbis_broad_yearly_long.csv  — provenance alias (identical long format)
  hq_shares_by_commodity_orbis_broad_yearly_wide.csv  — wide: one row per (hq_iso3, commodity),
    columns share_2016..share_2022

Usage:
  python 3_36_compute_hq_shares_yearly.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import pandas as pd
import csv
import os
import re
import sys
from collections import defaultdict

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT  # noqa: E402

INPUT_FILES = ["orbis_extractives_broad1.csv", "orbis_extractives_broad2.csv"]
OVERRIDES_FILE = os.path.join(RAW, "orbis/company_segment_overrides.csv")

YEARS = list(range(2016, 2023))  # 2016..2022 inclusive

EXTRACTIVE_CODE_PREFIXES = ("05", "06", "07", "08", "09")
EXTRACTIVE_SPECIAL_CODES = {"1920", "4671"}

SOE_PARENT_PREFIXES = [
    "CHINA NATIONAL PETROLEUM CORPORATION",
    "CHINA PETROLEUM & CHEMICAL CORPORATION",
    "SINOPEC",
    "PETROCHINA",
    "CNOOC",
]

# ISO2 → ISO3
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
# ── Helpers (mirrored from archive/3_41_process_orbis_broad.py) ──

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
print(f"  Combined: {len(df):,} rows, {len(df.columns)} columns")

# Parse NACE codes once (same for all years)
df["_primary_codes"] = df["NACE Rev. 2, primary code(s)"].apply(parse_codes)
df["_secondary_codes"] = df["NACE Rev. 2, secondary code(s)"].apply(parse_codes)
core_col = "NACE Rev. 2, core code (4 digits)"
if core_col in df.columns:
    df["_core_code"] = df[core_col].apply(parse_codes)
else:
    df["_core_code"] = [[] for _ in range(len(df))]
df["_all_codes"] = df.apply(lambda r: r["_primary_codes"] + r["_secondary_codes"] + r["_core_code"], axis=1)

# Extractive filter (same across years)
before = len(df)
df = df[df["_all_codes"].apply(is_extractive)].copy()
print(f"\nExtractive filter: {before:,} -> {len(df):,} rows")

# Commodity (uses primary codes + core; secondary fallback)
def _commodity(r):
    primary = r["_primary_codes"] + r["_core_code"]
    return codes_to_commodity(primary, r["_secondary_codes"])
df["_commodity"] = df.apply(_commodity, axis=1)

# IDs and country
df["_bvd_id"] = df["BvD ID number"].astype(str).str.strip()
df["_guo_id"] = df["GUO - BvD ID number"].astype(str).str.strip().replace({"nan": "", "None": ""})
df["_guo_country"] = df["GUO - Country ISO code"].astype(str).str.strip().replace({"nan": "", "None": ""})
df["_entity_country"] = df["Country ISO code"].astype(str).str.strip()
df["_name_upper"] = df["Company name"].astype(str).str.upper().str.strip()

# Load overrides
overrides = load_overrides(OVERRIDES_FILE)
print(f"Loaded {len(overrides)} segment overrides")

# %% MARK: 4. Per-year HQ shares
# ── Per-year loop ──
long_rows = []
summary_rows = []

for year in YEARS:
    rev_col = f"Operating revenue (Turnover) th USD {year}"
    if rev_col not in df.columns:
        print(f"\n  [skip {year}] column not found")
        continue
    # Year-specific revenue in USD
    df[f"_rev_{year}"] = df[rev_col].apply(parse_num)
    sub = df[df[f"_rev_{year}"].notna() & (df[f"_rev_{year}"] > 0)].copy()
    sub["_revenue_usd"] = sub[f"_rev_{year}"] * 1000.0

    # Dedupe by GUO within this year (keep max-revenue row per group)
    sub["_group_key"] = sub.apply(
        lambda r: r["_guo_id"] if r["_guo_id"] and r["_guo_id"].lower() not in ("n.a.", "") else r["_bvd_id"],
        axis=1,
    )
    n_before_dedup = len(sub)
    sub = sub.sort_values("_revenue_usd", ascending=False).drop_duplicates(subset="_group_key", keep="first").copy()

    # SOE branch dedup — within this year, keep only top-revenue row per SOE prefix
    soe_subs = pd.Series(False, index=sub.index)
    for prefix in SOE_PARENT_PREFIXES:
        match = sub["_name_upper"].str.startswith(prefix)
        if match.sum() <= 1:
            continue
        idx = sub.index[match]
        parent_idx = sub.loc[idx, "_revenue_usd"].idxmax()
        soe_subs.loc[[i for i in idx if i != parent_idx]] = True

    # Aggregate revenue per HQ × commodity
    hq_rev = defaultdict(lambda: defaultdict(float))
    total_rev = 0.0
    for idx, row in sub.iterrows():
        rev = row["_revenue_usd"]
        name = str(row.get("Company name", "")).strip()
        bvd_id = row["_bvd_id"]
        nace_commodity = row["_commodity"]

        if soe_subs.loc[idx]:
            # SOE branch — zero-weight (already in parent's consolidated accounts)
            continue

        ov = match_override(bvd_id, name, overrides)
        if ov is not None:
            rev_og = rev * ov["oil_gas"]
            rev_mi = rev * ov["minerals"]
            rev_co = rev * ov["coal"]
        else:
            rev_og = rev if nace_commodity == "oil_gas" else 0.0
            rev_mi = rev if nace_commodity == "minerals" else 0.0
            rev_co = rev if nace_commodity == "coal" else 0.0

        guo_country = row["_guo_country"]
        if guo_country.lower() in ("n.a.", "nan", "none", "", "ww", "yy", "zz"):
            guo_country = ""
        hq_iso2 = guo_country if guo_country else row["_entity_country"]
        hq_iso3 = ISO2_TO_ISO3.get(hq_iso2, hq_iso2) if hq_iso2 else ""
        if not hq_iso3:
            continue

        for com, v in [("oil_gas", rev_og), ("minerals", rev_mi), ("coal", rev_co)]:
            if v > 0:
                hq_rev[com][hq_iso3] += v
                total_rev += v

    # Compute shares and emit long rows
    for com in ("oil_gas", "minerals", "coal"):
        total_com = sum(hq_rev[com].values())
        for hq, rev in hq_rev[com].items():
            share = (rev / total_com) if total_com > 0 else 0.0
            long_rows.append({
                "year": year,
                "hq_iso3": hq,
                "commodity": com,
                "revenue_usd": rev,
                "share": share,
            })

    n_groups = len(sub) - int(soe_subs.sum())
    print(f"  {year}: {n_before_dedup:,} rows with revenue → {len(sub):,} after GUO dedup "
          f"→ {n_groups:,} excl. {int(soe_subs.sum())} SOE branches; total extractive rev ${total_rev/1e9:.0f}B")
    summary_rows.append({
        "year": year,
        "n_groups": n_groups,
        "extractive_revenue_bn": round(total_rev / 1e9, 1),
        "oil_gas_bn": round(sum(hq_rev["oil_gas"].values()) / 1e9, 1),
        "minerals_bn": round(sum(hq_rev["minerals"].values()) / 1e9, 1),
        "coal_bn": round(sum(hq_rev["coal"].values()) / 1e9, 1),
    })

# %% MARK: 5. Write outputs
# ── Write long format ──
long_path = os.path.join(EXT_INT, "hq_shares_by_commodity_orbis_broad_yearly_long.csv")
with open(long_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["year", "hq_iso3", "commodity", "revenue_usd", "share"])
    w.writeheader()
    for r in long_rows:
        w.writerow({
            "year": r["year"],
            "hq_iso3": r["hq_iso3"],
            "commodity": r["commodity"],
            "revenue_usd": f"{r['revenue_usd']:.0f}",
            "share": f"{r['share']:.6f}",
        })
print(f"\nSaved long format:  {long_path}  ({len(long_rows):,} rows)")

# Also write under the name the pipeline actually consumes: 3_38, script 4 and
# config.py read `hq_shares_by_commodity_yearly.csv` (the global per-commodity HQ
# shares). It is the same long format; the descriptive
# `..._orbis_broad_yearly_long.csv` above is kept as a provenance alias. Writing
# both here means re-running 3_2 always refreshes the file the pipeline reads
# (writing only the alias would let the consumed copy drift out of date).
consumed_path = os.path.join(EXT_INT, "hq_shares_by_commodity_yearly.csv")
with open(consumed_path, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["year", "hq_iso3", "commodity", "revenue_usd", "share"])
    w.writeheader()
    for r in long_rows:
        w.writerow({
            "year": r["year"],
            "hq_iso3": r["hq_iso3"],
            "commodity": r["commodity"],
            "revenue_usd": f"{r['revenue_usd']:.0f}",
            "share": f"{r['share']:.6f}",
        })
print(f"Saved (pipeline-consumed): {consumed_path}  ({len(long_rows):,} rows)")

# ── Write wide format: (hq_iso3, commodity) × year ──
wide = {}
for r in long_rows:
    key = (r["hq_iso3"], r["commodity"])
    wide.setdefault(key, {})[r["year"]] = r["share"]

wide_path = os.path.join(EXT_INT, "hq_shares_by_commodity_orbis_broad_yearly_wide.csv")
with open(wide_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    header = ["hq_iso3", "commodity"] + [f"share_{y}" for y in YEARS]
    w.writerow(header)
    for (hq, com) in sorted(wide.keys()):
        row = [hq, com] + [f"{wide[(hq,com)].get(y, 0):.6f}" for y in YEARS]
        w.writerow(row)
print(f"Saved wide format:  {wide_path}  ({len(wide):,} rows)")

# ── Console summary ──
print(f"\n{'='*80}")
print("YEARLY SUMMARY")
print(f"{'='*80}")
print(f"{'Year':<6} {'Groups':>8} {'Total $B':>10} {'Oil&gas $B':>12} {'Minerals $B':>13} {'Coal $B':>10}")
for s in summary_rows:
    print(f"  {s['year']:<4} {s['n_groups']:>8,} {s['extractive_revenue_bn']:>10,.0f} "
          f"{s['oil_gas_bn']:>12,.0f} {s['minerals_bn']:>13,.0f} {s['coal_bn']:>10,.0f}")

# Spot check: top-5 HQ countries for oil_gas in a few reference years
print(f"\nTop 5 HQ in OIL_GAS — trajectory 2016 vs 2022:")
from collections import defaultdict
og_2016 = {r["hq_iso3"]: r["share"] for r in long_rows if r["year"] == 2016 and r["commodity"] == "oil_gas"}
og_2022 = {r["hq_iso3"]: r["share"] for r in long_rows if r["year"] == 2022 and r["commodity"] == "oil_gas"}
hq_both = set(og_2016.keys()) | set(og_2022.keys())
by_2022 = sorted(hq_both, key=lambda h: -og_2022.get(h, 0))[:10]
print(f"  {'HQ':<5} {'2016 share':>11} {'2022 share':>11} {'Δ':>8}")
for hq in by_2022:
    s16 = og_2016.get(hq, 0)
    s22 = og_2022.get(hq, 0)
    print(f"  {hq:<5} {s16*100:>10.1f}% {s22*100:>10.1f}% {(s22-s16)*100:>+7.1f}pp")
