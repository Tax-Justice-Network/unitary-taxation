"""
Process the broad Orbis CSV export (NACE B + 1920 refining + 4671 fuel wholesale).

Input:  data/raw/resources/orbis_extractives_broad1.csv
        data/raw/resources/orbis_extractives_broad2.csv

Key differences vs. process_orbis_export.py:
  - Reads CSV (not XLSX)
  - Handles duplicate column names and trailing-space headers from Orbis
  - Filters on primary OR secondary NACE codes (catches integrated oil majors
    that code primary = 1920 refining, e.g. Exxon, BP, ConocoPhillips)
  - Deduplicates by GUO: one row per ultimate owner (largest-revenue row),
    to avoid double-counting parent + subsidiary revenues
  - Derives `ownership_class` from GUO - Type (listed / state_owned / private / other)
  - Flags `trader_only` for primary=4671 with no extraction code anywhere
  - Outputs broad variants to data/final/
"""

import pandas as pd
import csv
import os
import re
import sys
from collections import defaultdict, Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import RAW, EXT_INT  # noqa: E402

INPUT_FILES = ["orbis_extractives_broad1.csv", "orbis_extractives_broad2.csv"]  # raw Orbis extracts
OVERRIDES_FILE = RAW / "orbis/company_segment_overrides.csv"   # hand-curated, stays in raw/

# Extractive NACE codes: Section B (05xx–09xx) + 1920 (refining) + 4671 (fuel wholesale)
EXTRACTIVE_CODE_PREFIXES = ("05", "06", "07", "08", "09")
EXTRACTIVE_SPECIAL_CODES = {"1920", "4671"}

# ISO2 → ISO3 (extends the one in process_orbis_export.py with a few extras)
ISO2_TO_ISO3 = {
    "AE": "ARE", "AF": "AFG", "AG": "ATG", "AL": "ALB", "AM": "ARM",
    "AO": "AGO", "AR": "ARG", "AT": "AUT", "AU": "AUS", "AZ": "AZE",
    "BA": "BIH", "BB": "BRB", "BD": "BGD", "BE": "BEL", "BF": "BFA",
    "BG": "BGR", "BH": "BHR", "BI": "BDI", "BJ": "BEN", "BM": "BMU",
    "BN": "BRN", "BO": "BOL", "BR": "BRA", "BS": "BHS", "BT": "BTN",
    "BW": "BWA", "BY": "BLR", "BZ": "BLZ", "CA": "CAN", "CD": "COD",
    "CF": "CAF", "CG": "COG", "CH": "CHE", "CI": "CIV", "CL": "CHL",
    "CM": "CMR", "CN": "CHN", "CO": "COL", "CR": "CRI", "CU": "CUB",
    "CV": "CPV", "CW": "CUW", "CY": "CYP", "CZ": "CZE", "DE": "DEU",
    "DJ": "DJI", "DK": "DNK", "DM": "DMA", "DO": "DOM", "DZ": "DZA",
    "EC": "ECU", "EE": "EST", "EG": "EGY", "ER": "ERI", "ES": "ESP",
    "ET": "ETH", "FI": "FIN", "FJ": "FJI", "FR": "FRA", "GA": "GAB",
    "GB": "GBR", "GE": "GEO", "GH": "GHA", "GM": "GMB", "GN": "GIN",
    "GQ": "GNQ", "GR": "GRC", "GT": "GTM", "GW": "GNB", "GY": "GUY",
    "HK": "HKG", "HN": "HND", "HR": "HRV", "HT": "HTI", "HU": "HUN",
    "ID": "IDN", "IE": "IRL", "IL": "ISR", "IN": "IND", "IQ": "IRQ",
    "IR": "IRN", "IS": "ISL", "IT": "ITA", "JM": "JAM", "JO": "JOR",
    "JP": "JPN", "KE": "KEN", "KG": "KGZ", "KH": "KHM", "KM": "COM",
    "KR": "KOR", "KW": "KWT", "KY": "CYM", "KZ": "KAZ", "LA": "LAO",
    "LB": "LBN", "LK": "LKA", "LR": "LBR", "LS": "LSO", "LT": "LTU",
    "LU": "LUX", "LV": "LVA", "LY": "LBY", "MA": "MAR", "MC": "MCO",
    "MD": "MDA", "ME": "MNE", "MG": "MDG", "MK": "MKD", "ML": "MLI",
    "MM": "MMR", "MN": "MNG", "MO": "MAC", "MR": "MRT", "MT": "MLT",
    "MU": "MUS", "MV": "MDV", "MW": "MWI", "MX": "MEX", "MY": "MYS",
    "MZ": "MOZ", "NA": "NAM", "NE": "NER", "NG": "NGA", "NI": "NIC",
    "NL": "NLD", "NO": "NOR", "NP": "NPL", "NZ": "NZL", "OM": "OMN",
    "PA": "PAN", "PE": "PER", "PG": "PNG", "PH": "PHL", "PK": "PAK",
    "PL": "POL", "PR": "PRI", "PS": "PSE", "PT": "PRT", "PY": "PRY",
    "QA": "QAT", "RO": "ROU", "RS": "SRB", "RU": "RUS", "RW": "RWA",
    "SA": "SAU", "SC": "SYC", "SD": "SDN", "SE": "SWE", "SG": "SGP",
    "SI": "SVN", "SK": "SVK", "SL": "SLE", "SN": "SEN", "SO": "SOM",
    "SR": "SUR", "SS": "SSD", "SV": "SLV", "SY": "SYR", "SZ": "SWZ",
    "TD": "TCD", "TG": "TGO", "TH": "THA", "TJ": "TJK", "TM": "TKM",
    "TN": "TUN", "TR": "TUR", "TT": "TTO", "TW": "TWN", "TZ": "TZA",
    "UA": "UKR", "UG": "UGA", "US": "USA", "UY": "URY", "UZ": "UZB",
    "VE": "VEN", "VG": "VGB", "VN": "VNM", "YE": "YEM", "ZA": "ZAF",
    "ZM": "ZMB", "ZW": "ZWE",
}


def _normalise_code(raw):
    """Turn one raw code (float '610.0', string '610', '0610') into zero-padded 4-digit str. '' if unparseable."""
    if raw is None:
        return ""
    if isinstance(raw, float):
        if pd.isna(raw):
            return ""
        raw = int(raw)
    s = str(raw).strip()
    if not s or s.lower() in ("n.a.", "nan", "none", ""):
        return ""
    # Strip trailing ".0" if present
    if s.endswith(".0"):
        s = s[:-2]
    # Only keep digits
    s = re.sub(r"\D", "", s)
    if not s:
        return ""
    return s.zfill(4)


def parse_codes(s):
    """Split an Orbis NACE code cell into a list of zero-padded 4-digit codes.

    Orbis returns a single code per row as a float (e.g. 610.0). If a future
    export has multiple codes per cell (comma/semicolon-separated), this handles
    that too.
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return []
    # Float case: single code
    if isinstance(s, (int, float)):
        c = _normalise_code(s)
        return [c] if c else []
    # String case: may contain multiple codes
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
    """True if any code is in Section B or 1920/4671."""
    for c in codes:
        if c in EXTRACTIVE_SPECIAL_CODES:
            return True
        if len(c) >= 2 and c[:2] in EXTRACTIVE_CODE_PREFIXES:
            return True
    return False


def _bucket_for_codes(codes):
    """Given a set of codes, return commodity bucket ('oil_gas'/'coal'/'minerals') or None."""
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
    """
    Classify commodity using PRIMARY codes first (primary + core);
    fall back to SECONDARY only if primary gives no extractive bucket.

    This prevents companies like Chevron (primary 1920 refining, secondary 0520 lignite)
    from being mis-tagged as coal because of a minor secondary code.

    Returns (commodity, is_trader_only).
    """
    all_codes = primary_codes + secondary_codes

    # trader_only: only 4671 matches anywhere, no upstream extraction/refining code
    has_extraction_any = any(
        c.startswith(("05", "06", "07", "08", "09")) or c == "1920"
        for c in all_codes
    )
    has_4671_any = "4671" in all_codes
    trader_only = has_4671_any and not has_extraction_any

    # Primary-first classification
    bucket = _bucket_for_codes(primary_codes)
    if bucket is None:
        bucket = _bucket_for_codes(secondary_codes)
    return (bucket or "unknown"), trader_only


def classify_ownership(guo_type):
    """Map Orbis GUO - Type to broader ownership_class."""
    if not guo_type or guo_type in ("n.a.", "nan", "none", ""):
        return "unknown"
    t = guo_type.lower()
    if "public authority" in t or "state" in t or "government" in t:
        return "state_owned"
    if "industrial compan" in t or "corporate" in t:
        # GUO Type "Industrial company" usually = listed group parent
        return "corporate"
    if "individual" in t or "family" in t or "one or more named" in t:
        return "private"
    if "bank" in t or "insurance" in t or "financial" in t or "fund" in t or "mutual" in t:
        return "financial"
    if "foundation" in t or "research" in t:
        return "foundation"
    return "other"


def load_overrides(path):
    """Load segment overrides. Returns list of dicts with name_contains (upper) and shares."""
    if not os.path.exists(path):
        return []
    overrides = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            # First non-comment line is header
            parts = next(csv.reader([line]))
            if parts and parts[0] == "bvd_id":
                continue  # header
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
                "oil_gas": og_s,
                "minerals": mi_s,
                "coal": co_s,
            })
    return overrides


def match_override(bvd_id, name, overrides):
    """Return matching override dict or None. BvD ID exact > name substring (first match)."""
    name_u = (name or "").upper()
    for ov in overrides:
        if ov["bvd_id"] and ov["bvd_id"] == bvd_id:
            return ov
    for ov in overrides:
        if ov["name_upper"] and ov["name_upper"] in name_u:
            return ov
    return None


def parse_num(v):
    """Parse an Orbis numeric cell ('n.a.', '-', comma decimals)."""
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


# ── 1. Load CSVs ──
print("Loading Orbis broad export CSVs...")
dfs = []
for fname in INPUT_FILES:
    path = os.path.join(RAW, "resources", fname)
    if not os.path.exists(path):
        print(f"  WARNING: {fname} not found, skipping")
        continue
    # BOM on first header ('﻿') handled via utf-8-sig
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False,
                     na_values=["n.a.", "n.s.", "-"], keep_default_na=True)
    print(f"  {fname}: {len(df):,} rows")
    dfs.append(df)

df = pd.concat(dfs, ignore_index=True)
print(f"\n  Combined: {len(df):,} rows, {len(df.columns)} columns")

# Normalise column names: strip trailing spaces, drop .1 duplicates
df.columns = [c.strip() for c in df.columns]
# The second 'Country ISO code' may have been renamed to 'Country ISO code.1' by pandas —
# in this export it's the same as the first, so just drop it
for dup in ["Country ISO code.1", "Consolidation code.1", "Unnamed: 0"]:
    if dup in df.columns:
        df = df.drop(columns=[dup])

# ── 2. Revenue columns (most recent first) ──
rev_cols_all = [c for c in df.columns if c.startswith("Operating revenue") and "th USD" in c and "Last avail" not in c]
rev_cols = sorted(rev_cols_all, reverse=True)  # 2025, 2024, ...
print(f"\n  Revenue columns: {rev_cols}")

# ── 3. Extractive filter on primary OR secondary NACE codes ──
before = len(df)
df["_primary_codes"] = df["NACE Rev. 2, primary code(s)"].apply(parse_codes)
df["_secondary_codes"] = df["NACE Rev. 2, secondary code(s)"].apply(parse_codes)
df["_all_codes"] = df.apply(lambda r: r["_primary_codes"] + r["_secondary_codes"], axis=1)
# Also include the 4-digit core code as fallback (if it's in our set)
core_col = "NACE Rev. 2, core code (4 digits)"
if core_col in df.columns:
    df["_core_code"] = df[core_col].apply(parse_codes)
    df["_all_codes"] = df.apply(lambda r: r["_all_codes"] + r["_core_code"], axis=1)

df["_is_extractive"] = df["_all_codes"].apply(is_extractive)
df = df[df["_is_extractive"]].copy()
print(f"\n  Extractive (NACE B + 1920 + 4671) filter: {before:,} -> {len(df):,} rows")

# ── 4. Best revenue per row ──
def best_rev_row(row):
    for col in rev_cols:
        v = parse_num(row.get(col))
        if v is not None and v > 0:
            yr = re.search(r"(\d{4})", col)
            return v, (yr.group(1) if yr else "")
    return None, ""

df[["_rev_th", "_rev_year"]] = df.apply(lambda r: pd.Series(best_rev_row(r)), axis=1)
before = len(df)
df = df[df["_rev_th"].notna() & (df["_rev_th"] > 0)].copy()
print(f"  With positive revenue (any year): {before:,} -> {len(df):,}")

df["_revenue_usd"] = df["_rev_th"] * 1000.0

# ── 5a. Deduplicate by GUO: one row per ultimate owner group ──
#    Strategy: group by GUO BvD ID (fallback: own BvD ID), keep highest-revenue row.
bvd_col = "BvD ID number"
guo_id_col = "GUO - BvD ID number"

df["_bvd_id"] = df[bvd_col].astype(str).str.strip()
df["_guo_id"] = df[guo_id_col].astype(str).str.strip().replace({"nan": "", "None": ""})
# If no GUO, treat company as its own group
df["_group_key"] = df.apply(lambda r: r["_guo_id"] if r["_guo_id"] and r["_guo_id"].lower() not in ("n.a.", "nan", "") else r["_bvd_id"], axis=1)

before = len(df)
df = df.sort_values("_revenue_usd", ascending=False).drop_duplicates(subset="_group_key", keep="first").copy()
print(f"  Deduplicated by GUO group (kept max-revenue row): {before:,} -> {len(df):,}")

# ── 5b. Deduplicate Chinese SOE branches by name prefix ──
# Many provincial branches of CNPC, Sinopec, CNOOC, PetroChina report to Orbis
# without a GUO linking them to their parent. Their revenue is already in the
# parent's consolidated accounts, so we zero-weight them here.
SOE_PARENT_PREFIXES = [
    "CHINA NATIONAL PETROLEUM CORPORATION",   # CNPC parent
    "CHINA PETROLEUM & CHEMICAL CORPORATION", # Sinopec parent
    "SINOPEC",                                # subsidiaries (no exact "SINOPEC" parent row)
    "PETROCHINA",                             # PetroChina subsidiaries
    "CNOOC",                                  # CNOOC subsidiaries
]
# For each prefix, keep only the top-revenue row (treated as the parent); zero the rest.
df["_name_upper"] = df["Company name"].astype(str).str.upper().str.strip()
soe_subs_mask = pd.Series(False, index=df.index)
for prefix in SOE_PARENT_PREFIXES:
    match = df["_name_upper"].str.startswith(prefix)
    if match.sum() <= 1:
        continue
    # The parent is the largest-revenue row in this prefix group
    matched_idx = df.index[match]
    parent_idx = df.loc[matched_idx, "_revenue_usd"].idxmax()
    sub_idx = [i for i in matched_idx if i != parent_idx]
    soe_subs_mask.loc[sub_idx] = True

n_soe_subs = int(soe_subs_mask.sum())
soe_sub_revenue = float(df.loc[soe_subs_mask, "_revenue_usd"].sum())
df["_soe_sub"] = soe_subs_mask
print(f"  Flagged Chinese SOE subsidiaries (double-counted with parent): "
      f"{n_soe_subs} rows, ${soe_sub_revenue/1e9:.0f}B — zero-weighted")

# ── 6. Classify commodity, ownership, HQ country ──
def classify_row(row):
    # "Primary" = explicit primary codes + the single core code (both represent main activity)
    primary = list(row["_primary_codes"]) + list(row.get("_core_code", []))
    secondary = list(row["_secondary_codes"])
    commodity, trader_only = codes_to_commodity(primary, secondary)
    ownership = classify_ownership(str(row.get("GUO - Type", "")))
    guo_country = str(row.get("GUO - Country ISO code", "")).strip()
    if guo_country.lower() in ("n.a.", "nan", "none", ""):
        guo_country = ""
    entity_country = str(row.get("Country ISO code", "")).strip()
    hq = guo_country if guo_country and guo_country not in ("WW", "YY", "ZZ") else entity_country
    return pd.Series({
        "commodity": commodity,
        "trader_only": trader_only,
        "ownership_class": ownership,
        "hq_iso2": hq,
        "entity_iso2": entity_country,
        "guo_iso2": guo_country,
    })

df[["commodity", "trader_only", "ownership_class", "hq_iso2", "entity_iso2", "guo_iso2"]] = df.apply(classify_row, axis=1)

# ── 7. Write full company list ──
total_assets_cols = sorted([c for c in df.columns if c.startswith("Total assets") and "th USD" in c], reverse=True)

def best_assets(row):
    for col in total_assets_cols:
        v = parse_num(row.get(col))
        if v is not None and v > 0:
            return v * 1000.0
    return None

df["_total_assets_usd"] = df.apply(best_assets, axis=1)

# Load manual segment overrides for diversified companies
overrides = load_overrides(OVERRIDES_FILE)
print(f"\n  Loaded {len(overrides)} segment overrides from {os.path.basename(OVERRIDES_FILE)}")

companies = []
override_hits = 0
for _, row in df.iterrows():
    name = str(row.get("Company name", "")).strip()
    bvd_id = row["_bvd_id"]
    rev = row["_revenue_usd"]
    nace_commodity = row["commodity"]

    is_soe_sub = bool(row.get("_soe_sub", False))
    if is_soe_sub:
        # Chinese SOE branch — zero-weight (revenue already in parent's consolidated accounts)
        rev_og = rev_mi = rev_co = 0.0
        override_label = "SOE_BRANCH"
    else:
        ov = match_override(bvd_id, name, overrides)
        if ov is not None:
            override_hits += 1
            rev_og = rev * ov["oil_gas"]
            rev_mi = rev * ov["minerals"]
            rev_co = rev * ov["coal"]
            override_label = f"{ov['oil_gas']:.2f}/{ov['minerals']:.2f}/{ov['coal']:.2f}"
        else:
            # Single-commodity assignment from NACE
            rev_og = rev if nace_commodity == "oil_gas" else 0.0
            rev_mi = rev if nace_commodity == "minerals" else 0.0
            rev_co = rev if nace_commodity == "coal" else 0.0
            override_label = ""

    companies.append({
        "bvd_id": bvd_id,
        "name": name,
        "entity_country": row["entity_iso2"],
        "guo_country": row["guo_iso2"],
        "hq_country": row["hq_iso2"],
        "commodity": nace_commodity,  # NACE-based primary bucket (for reference)
        "trader_only": int(bool(row["trader_only"])),
        "ownership_class": row["ownership_class"],
        "nace_primary": ";".join(row["_primary_codes"]),
        "nace_secondary": ";".join(row["_secondary_codes"]),
        "revenue_usd": rev,
        "revenue_year": row["_rev_year"],
        "total_assets_usd": row["_total_assets_usd"] if pd.notna(row["_total_assets_usd"]) else "",
        "rev_oil_gas_usd": rev_og,
        "rev_minerals_usd": rev_mi,
        "rev_coal_usd": rev_co,
        "override_shares": override_label,
        "consolidation": str(row.get("Consolidation code", "")).strip(),
        "guo_name": str(row.get("GUO - Name", "")).strip(),
        "guo_bvd_id": row["_guo_id"],
        "guo_type": str(row.get("GUO - Type", "")).strip(),
        "entity_type": str(row.get("Type of entity", "")).strip(),
    })

print(f"  Applied overrides to {override_hits} companies")

companies.sort(key=lambda x: -x["revenue_usd"])
out_companies = os.path.join(EXT_INT, "orbis_broad_extractive_companies.csv")
with open(out_companies, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=companies[0].keys())
    writer.writeheader()
    writer.writerows(companies)
print(f"\n  Saved company list: {out_companies}  ({len(companies):,} rows)")

# ── 8. Breakdowns ──
print(f"\n  By commodity:")
for k, v in Counter(c["commodity"] for c in companies).most_common():
    print(f"    {k}: {v:,}")

print(f"\n  By ownership_class:")
for k, v in Counter(c["ownership_class"] for c in companies).most_common():
    print(f"    {k}: {v:,}")

trader_count = sum(1 for c in companies if c["trader_only"])
print(f"\n  trader_only = 1: {trader_count:,}")

# ── 9. Top 30 ──
print(f"\n{'='*120}")
print(f"TOP 30 EXTRACTIVE GROUPS BY REVENUE (broad Orbis export)")
print(f"{'='*120}")
print(f"{'#':>3s}  {'Name':45s} {'HQ':4s} {'Rev($B)':>8s} {'Yr':4s} {'Commodity':10s} {'Owner':12s} {'Trade':>5s}  {'GUO':30s}")
print("-" * 120)
for i, c in enumerate(companies[:30], 1):
    print(f"{i:3d}  {c['name'][:45]:45s} {c['hq_country']:4s} "
          f"${c['revenue_usd']/1e9:>7.1f} {c['revenue_year']:4s} {c['commodity']:10s} "
          f"{c['ownership_class']:12s} {c['trader_only']:>5d}  {c['guo_name'][:30]}")

# ── 10. HQ shares (ISO3) — uses per-commodity revenue columns ──
hq_rev = defaultdict(lambda: defaultdict(float))
commodity_total = defaultdict(float)
for c in companies:
    iso3 = ISO2_TO_ISO3.get(c["hq_country"], c["hq_country"])
    for com, col in [("oil_gas", "rev_oil_gas_usd"), ("minerals", "rev_minerals_usd"), ("coal", "rev_coal_usd")]:
        v = c[col]
        if v > 0:
            hq_rev[com][iso3] += v
            commodity_total[com] += v

all_hqs = set()
for com in hq_rev:
    all_hqs.update(hq_rev[com].keys())

shares_path = os.path.join(EXT_INT, "hq_shares_by_commodity_orbis_broad.csv")
rows_out = []
for hq in all_hqs:
    og = hq_rev["oil_gas"].get(hq, 0)
    mi = hq_rev["minerals"].get(hq, 0)
    co = hq_rev["coal"].get(hq, 0)
    if (og + mi + co) < 1e6:
        continue
    og_s = og / commodity_total["oil_gas"] if commodity_total["oil_gas"] else 0
    mi_s = mi / commodity_total["minerals"] if commodity_total["minerals"] else 0
    co_s = co / commodity_total["coal"] if commodity_total["coal"] else 0
    rows_out.append((hq, og_s, mi_s, co_s, og/1e9, mi/1e9, co/1e9, og+mi+co))
rows_out.sort(key=lambda x: -x[7])

with open(shares_path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["hq_iso3", "oil_gas_share", "minerals_share", "coal_share",
                "oil_gas_revenue_bn", "minerals_revenue_bn", "coal_revenue_bn"])
    for hq, og_s, mi_s, co_s, og_bn, mi_bn, co_bn, _ in rows_out:
        w.writerow([hq, f"{og_s:.6f}", f"{mi_s:.6f}", f"{co_s:.6f}",
                    f"{og_bn:.1f}", f"{mi_bn:.1f}", f"{co_bn:.1f}"])
print(f"\n  Saved HQ shares: {shares_path}")

# ── 11. Print final HQ shares ──
print(f"\n{'='*70}")
print(f"HQ SHARES BY COMMODITY (Orbis broad export)")
print(f"{'='*70}")
for com in ["oil_gas", "minerals", "coal"]:
    total = commodity_total.get(com, 0)
    if total == 0:
        continue
    print(f"\n{com.upper()} (total: ${total/1e9:.0f}B)")
    items = sorted(hq_rev[com].items(), key=lambda x: -x[1])
    for hq, rev in items[:15]:
        print(f"  {hq}: ${rev/1e9:.1f}B = {rev/total*100:.1f}%")
    if len(items) > 15:
        print(f"  ... and {len(items)-15} more")

print(f"\nGrand total: ${sum(commodity_total.values())/1e9:.0f}B across {len(companies):,} groups")
