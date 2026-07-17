"""
Pull company-level payments-to-government from the EITI Open Data API and
classify each into pre-profit (royalty-like) / post-profit (CIT, equity) /
general (dropped, like VAT) buckets.

Source: https://eiti.org/api/v2.0/revenue  — a paged endpoint (25 records/page,
~246 k records), each record self-contained: type (company / agency), revenue
(USD), gfs.code + gfs.label (the standardised GFS category), organisation
(company name, id, declared commodities, …), government entity, sector,
project, in-kind fields, country iso2, year. We keep type == "company".

Improvements vs the earlier version:

  1. **summary_data cache pulled.** The full `/summary_data` endpoint (~663
     country-fiscal-year reports) is paged once into
     `eiti_summary_data_cache.jsonl`, keyed on the alphanumeric report id
     (e.g. `AF2009`).  Useful for downstream cross-referencing.

  2. **Resumable pagination + exponential backoff with jitter.** Both endpoints
     are paged into JSONL caches so a dropped run resumes from the highest
     page already written.  Retries on 5xx / network errors use
     `2**i + random.uniform(0, 1)` to spread retries; the script also checks
     and reports any page-number gaps in the final cache.

  3. **`country_year_source` column** on the output CSV. Values: `direct`
     (record carries its own `summary_data.iso2` / `.year` fields, the common
     case) or `summary_data` (recovered via the cache lookup — currently
     near-zero, see caveat below).

**Caveat on the ~98 k records that the older script dropped.** They split into:
  - **~93 k "minimal-stub" records** with only `id` / `self` / `gfs.*` / a few
    other primitives — no `organisation.summary_data` or any other ref back to
    a parent report. The country/year metadata is genuinely missing from the
    API.  Not recoverable from the public endpoints.
  - **~6 k records** that do carry an `organisation.summary_data` URL — but
    that URL uses the *organisation*'s numeric id (e.g.
    `https://eiti.org/api/v2.0/summary_data/131140` is the same id as
    `/organisation/131140`), which is an EITI-side URL-naming quirk.  The
    `/summary_data/<numeric_id>` endpoint returns an empty list; the
    `?filter[id]=<numeric_id>` parameter is silently ignored.  So this path
    cannot be resolved via the public API either.

Both caveats are reported in the final summary print so you can see exactly how
many rows ended up in each `country_year_source` bucket.  ~$540 B / 18 % of
EITI value remains unrecoverable from this pipeline pending an EITI data dump
with a cleaner numeric→alphanumeric id mapping.

Outputs:
  data/intermediate/extractive/eiti_summary_data_cache.jsonl   (parent reports — small, ~25 records/page × tens of pages)
  data/intermediate/extractive/eiti_revenue_company_raw.jsonl  (raw company records — re-process without re-pulling)
  data/intermediate/extractive/eiti_company_payments_long.csv  (one row per company payment, classified)

Run order: this → 1_7_match_eiti_companies_to_orbis.py → 1_8_resource_payments_by_hq_source.py.
The old Excel-parsing version is kept at 1_6_parse_eiti_company_payments.py (fallback / cross-check).

CLI flags:
  --process-only            Re-process from JSONL caches without re-hitting the API.
  --no-resume               Start the revenue pull from page 1 (overwrite).
  --refresh-summary-data    Re-pull /summary_data even if the cache exists.
"""
import csv
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

REVENUE_FIRST = "https://eiti.org/api/v2.0/revenue?page=1"
SUMMARY_FIRST = "https://eiti.org/api/v2.0/summary_data?page=1"
RAW_JSONL = EXT_INT / "eiti_revenue_company_raw.jsonl"
SUMMARY_JSONL = EXT_INT / "eiti_summary_data_cache.jsonl"
OUT_CSV = EXT_INT / "eiti_company_payments_long.csv"

# Regex to pull the numeric id out of `organisation.summary_data` URLs:
#   https://eiti.org/api/v2.0/summary_data/208835  →  "208835"
_SUMMARY_ID_RE = re.compile(r"/summary_data/(\d+)/?$")


# ── iso2 → iso3 ───────────────────────────────────────────────────────────
try:
    import pycountry
    def to_iso3(iso2):
        if not iso2:
            return ""
        iso2 = str(iso2).strip().upper()
        if len(iso2) == 3:
            return iso2
        c = pycountry.countries.get(alpha_2=iso2)
        return c.alpha_3 if c else ""
except ImportError:
    _I = {"AF": "AFG", "AL": "ALB", "AO": "AGO", "AR": "ARG", "AM": "ARM", "AZ": "AZE",
          "BF": "BFA", "BH": "BHR", "BO": "BOL", "BR": "BRA", "CD": "COD", "CF": "CAF",
          "CG": "COG", "CI": "CIV", "CL": "CHL", "CM": "CMR", "CO": "COL", "DE": "DEU",
          "DO": "DOM", "EC": "ECU", "ET": "ETH", "GA": "GAB", "GB": "GBR", "GH": "GHA",
          "GN": "GIN", "GT": "GTM", "GY": "GUY", "HN": "HND", "ID": "IDN", "IQ": "IRQ",
          "KE": "KEN", "KG": "KGZ", "KZ": "KAZ", "LB": "LBN", "LR": "LBR", "MD": "MDA",
          "MG": "MDG", "ML": "MLI", "MM": "MMR", "MN": "MNG", "MR": "MRT", "MW": "MWI",
          "MX": "MEX", "MZ": "MOZ", "NE": "NER", "NG": "NGA", "NL": "NLD", "NO": "NOR",
          "PE": "PER", "PG": "PNG", "PH": "PHL", "SB": "SLB", "SC": "SYC", "SL": "SLE",
          "SN": "SEN", "SR": "SUR", "ST": "STP", "TD": "TCD", "TG": "TGO", "TJ": "TJK",
          "TL": "TLS", "TT": "TTO", "TZ": "TZA", "UA": "UKR", "UG": "UGA", "US": "USA",
          "YE": "YEM", "ZM": "ZMB"}
    def to_iso3(iso2):
        return _I.get(str(iso2).strip().upper(), str(iso2).strip().upper() if len(str(iso2 or "")) == 3 else "")


# ── classification: GFS category → bucket (royalty_like / cit / equity / general / other) ──
# `gfs.label` is one of ~30 standardised strings — map them directly. General
# (economy-wide, not peculiar to extractives, not profit-sharing) is DROPPED.
GFS_LABEL_TO_BUCKET = {
    # profit-sharing — kept (needed for CbCR correction)
    "Ordinary taxes on income, profits and capital gains": "cit",
    "Extraordinary taxes on income, profits and capital gains": "cit",
    # state equity / state-participation / production-share — kept (post-profit)
    "From government participation (equity)": "equity",
    "Dividends": "equity",
    "From state-owned enterprises": "equity",
    "Delivered/paid to state-owned enterprise(s)": "equity",
    "Withdrawals from income of quasi-corporations": "equity",
    "Profits of natural resource export monopolies": "equity",
    "Sales of state's share of production or other revenue collected in kind": "equity",
    # resource-specific, non-profit — kept (pre-profit; the carve-out / add-back base)
    "Royalties": "royalty_like",
    "Bonuses": "royalty_like",
    "Licence fees": "royalty_like",
    "Other taxes payable by natural resource companies": "royalty_like",
    "Other rent payments": "royalty_like",
    "Compulsory transfers to government (infrastructure and other)": "royalty_like",
    "Production entitlements (in-kind or cash)": "royalty_like",
    "Production entitlement": "royalty_like",
    "Delivered/paid directly to government": "royalty_like",
    "Rent": "royalty_like",
    "Administrative fees for government services": "royalty_like",
    "Mandatory social expenditures": "royalty_like",
    "Infrastructure provisions and barter arrangements": "royalty_like",
    # general / economy-wide — DROPPED
    "General taxes on goods and services (VAT, sales tax, turnover tax)": "general",
    "Customs and other import duties": "general",
    "Taxes on exports": "general",
    "Excise taxes": "general",
    "Taxes on property": "general",
    "Taxes on payroll and workforce": "general",
    "Social security employer contributions": "general",
    "Social security employee contributions": "general",
    "Social security contributions": "general",
    "Fines, penalties, and forfeits": "general",
    "Emission and pollution taxes": "general",
    "Motor vehicle taxes": "general",
    "Sales of goods and services by government units": "general",
    "Voluntary transfers to government (donations)": "general",
    "Interest": "general",
    "Stamp taxes": "general",
    "Other taxes": "general",
}
# keyword fallback when gfs.label is missing/unknown — checked in this order
_KW = [
    ("general", ("value added tax", "vat", "(tva)", "gst", "customs", "import dut", "douane", "excise",
                 "accise", "payroll", "social security", "social contribution", "personal income tax",
                 "pay as you earn", "(paye)", "property tax", "motor vehicle", "stamp dut", "fines", "penalt",
                 "amende", "co2 tax", "carbon tax", "emission tax", "pollution tax", "salaire", "sales tax",
                 "turnover tax", "registration fee", "trade tax")),
    ("cit", ("income, profits and capital", "income tax", "corporate tax", "corporation tax", "company tax",
             "profits tax", "profit tax", "petroleum profits tax", "supplemental petroleum tax", "windfall",
             "additional profit", "solidarity contribution", "impot sur les societes", "impuesto a las ganancias")),
    ("equity", ("dividend", "government participation", "state participation", "state-owned enterprise",
                "produced petroleum sold", "crude oil export sales", "profit oil", "share of profit",
                "production entitlement", "carried interest", "winstaandeel", "sdfi")),
    ("royalty_like", ("royalt", "redevance", "regalia", "bonus", "licence", "license", "permis", "permit",
                      "surface", "superficiaire", "rent", "loyers", "infrastructure", "training fund",
                      "redevance miniere", "ad valorem", "extraction tax", "severance", "exploration",
                      "exploitation", "administrative fee", "data fee")),
]


def classify(gfs_label, fallback_text=""):
    b = GFS_LABEL_TO_BUCKET.get((gfs_label or "").strip())
    if b:
        return b
    t = " " + (str(gfs_label or "") + " " + str(fallback_text or "")).lower() + " "
    for bucket, kws in _KW:
        if any(k in t for k in kws):
            return bucket
    return "other"


# ── commodity from organisation.commodities (the API's revenue-level `sector` is usually null) ──
OIL_GAS_C = {"crude oil", "oil", "petroleum", "natural gas", "gas", "condensate", "lng", "ngl",
             "shale gas", "shale oil", "coal bed methane", "coalbed methane", "hydrocarbons", "petrole", "gaz"}
COAL_C = {"coal", "lignite", "anthracite", "thermal coal", "coking coal", "charbon"}
MIN_NONEXTRACTIVE = {"forestry", "timber", "wood", "agriculture", "fisheries", "fishing", "water"}


def commodity_of(org_commodities, sector):
    cs = [str(c).strip().lower() for c in (org_commodities or []) if c]
    if sector:
        s = str(sector).strip().lower()
        if any(k in s for k in ("oil", "gas", "petrol", "hydrocarb")):
            return "oil_gas"
        if "coal" in s or "charbon" in s:
            return "coal"
        if any(k in s for k in ("mining", "mineral", "minier", "metal")):
            return "minerals"
    if any(c in COAL_C for c in cs) and not any(c in OIL_GAS_C for c in cs):
        return "coal"
    if any(c in OIL_GAS_C or any(k in c for k in OIL_GAS_C) for c in cs):
        return "oil_gas"
    if any(c in MIN_NONEXTRACTIVE for c in cs):
        return "other"
    if cs:
        return "minerals"
    return "unknown"


# ── HTTP fetch with exponential backoff + jitter ─────────────────────────
def fetch(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"Accept": "application/json", "User-Agent": "sotj-research/1.0"},
            )
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                ConnectionError, json.JSONDecodeError) as e:
            if i == tries - 1:
                raise
            sleep = min(60, (2 ** i) + random.uniform(0, 1))
            print(f"  [warn] fetch {url} retry {i+1}/{tries-1} after {e!s}; sleeping {sleep:.1f}s")
            time.sleep(sleep)
    return None


# ── pagination → JSONL cache (revenue or summary_data) ─────────────────────
def _last_page_in_cache(jsonl_path):
    """Return the highest `_page` value already written to the cache, or 0."""
    if not jsonl_path.exists() or jsonl_path.stat().st_size == 0:
        return 0
    last = 0
    seen = set()
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            try:
                p = json.loads(line).get("_page", 0)
                last = max(last, p)
                seen.add(p)
            except Exception:
                pass
    if last and len(seen) < last:
        missing = sorted(set(range(1, last + 1)) - seen)
        print(f"  [warn] cache has gaps: {len(missing)} missing pages, e.g. {missing[:5]}...")
    return last


def pull_paginated(first_url, jsonl_path, *, keep=None, resume=True, label=""):
    """Walk a paged JSON:API endpoint, appending each retained record to JSONL.

    `keep` is a predicate applied to each record (e.g. type=='company');
    if None, every record in `data` is kept.

    Resumes from `_page = last + 1` if the cache exists and `resume=True`.
    """
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    start_page = 1
    mode = "w"
    if resume:
        last = _last_page_in_cache(jsonl_path)
        if last:
            start_page, mode = last + 1, "a"
            print(f"[{label}] resuming from page {start_page} (cache has up to page {last}).")
    url = re.sub(r"page=\d+", f"page={start_page}", first_url)
    n_pages = n_kept = 0
    with open(jsonl_path, mode, encoding="utf-8") as out:
        page = start_page
        while url:
            d = fetch(url)
            for rec in d.get("data", []):
                if keep is None or keep(rec):
                    rec["_page"] = page
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    n_kept += 1
            n_pages += 1
            nxt = d.get("next") or d.get("links", {}).get("next")
            url = (nxt.get("href") if isinstance(nxt, dict) else nxt) if nxt else None
            page += 1
            if n_pages % 100 == 0:
                out.flush()
                print(f"  [{label}] ...{n_pages} pages, {n_kept:,} records kept (next page {page})")
    print(f"[{label}] pull done: {n_pages} pages this run, {n_kept:,} records written → {jsonl_path}")


def pull_summary_data(refresh=False):
    """Pull /summary_data into eiti_summary_data_cache.jsonl. Small endpoint
    (a few hundred records); usually a one-time pull."""
    if not refresh and SUMMARY_JSONL.exists() and SUMMARY_JSONL.stat().st_size > 0:
        n = sum(1 for _ in open(SUMMARY_JSONL, encoding="utf-8"))
        print(f"[summary_data] cache exists ({n:,} records); skip (use --refresh-summary-data to re-pull)")
        return
    pull_paginated(SUMMARY_FIRST, SUMMARY_JSONL, keep=None, resume=False, label="summary_data")


def build_summary_id_map():
    """Read SUMMARY_JSONL → {summary_id_str: (iso3, year)}.

    Year is derived from the report `label` (e.g. "Afghanistan: 2009") or
    `year_end` (e.g. "2009-03-20" → 2009). iso3 comes from `country.iso3`."""
    out = {}
    if not SUMMARY_JSONL.exists():
        return out
    with open(SUMMARY_JSONL, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sid = str(r.get("id") or "")
            if not sid:
                continue
            iso3 = (r.get("country.iso3") or "").strip().upper()
            if not iso3:
                iso2 = (r.get("country.iso2") or "").strip().upper()
                if iso2:
                    iso3 = to_iso3(iso2)
            # Prefer the report-naming year embedded in the label; fall back to year_end.
            yr = None
            lbl = str(r.get("label") or "")
            m = re.search(r"\b(19|20)\d{2}\b", lbl)
            if m:
                yr = int(m.group(0))
            else:
                ye = str(r.get("year_end") or r.get("year_start") or "")
                if ye[:4].isdigit():
                    yr = int(ye[:4])
            if iso3 and yr:
                out[sid] = (iso3, yr)
    return out


def pull_revenue(resume=True):
    pull_paginated(
        REVENUE_FIRST, RAW_JSONL,
        keep=lambda rec: (rec.get("type") or "").lower() == "company",
        resume=resume, label="revenue",
    )


# ── processing: classify + backfill country/year from summary_data ────────
def process():
    """Read RAW_JSONL → classify → backfill (iso3, year) via summary_data → write OUT_CSV.

    Drops the `general` bucket and rows still missing iso3/year after backfill.
    """
    summary_map = build_summary_id_map()
    print(f"[process] summary_data map has {len(summary_map):,} entries")

    src_counts = {"direct": 0, "summary_data": 0, "missing": 0}
    rows = []
    dropped_general = dropped_noyear = 0

    with open(RAW_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)

            iso3 = to_iso3(r.get("summary_data.iso2"))
            yr = r.get("summary_data.year")
            try:
                yr = int(str(yr)[:4]) if yr else None
            except ValueError:
                yr = None
            source = "direct" if iso3 and yr else None

            if not (iso3 and yr):
                ref = r.get("organisation.summary_data") or ""
                m = _SUMMARY_ID_RE.search(str(ref))
                if m:
                    hit = summary_map.get(m.group(1))
                    if hit:
                        iso3, yr = hit
                        source = "summary_data"

            if not (iso3 and yr):
                source = "missing"
                src_counts[source] += 1
                dropped_noyear += 1
                continue
            src_counts[source] += 1

            org_comms = []
            for k in sorted(k for k in r if k.startswith("organisation.commodities.")):
                v = r.get(k)
                if v:
                    org_comms.append(v)
            gfs_label = r.get("gfs.label") or ""
            comm = commodity_of(org_comms, r.get("sector"))
            bucket = classify(
                gfs_label,
                " ".join([str(r.get("label") or ""), str(r.get("project_name") or ""), str(r.get("comments") or "")]),
            )
            if bucket == "general":
                dropped_general += 1
                continue
            val = r.get("revenue")
            try:
                val = float(val) if val not in (None, "") else None
            except (TypeError, ValueError):
                val = None
            ink_vol = r.get("in_kind_volume")
            try:
                ink_vol = float(ink_vol) if ink_vol not in (None, "") else None
            except (TypeError, ValueError):
                ink_vol = None
            if val is None and ink_vol is None:
                continue
            comp = (r.get("organisation.label") or "").strip()
            if not comp or len(comp) < 2:
                continue
            rows.append({
                "iso3": iso3, "year": yr,
                "country_year_source": source,
                "commodity": comm,
                "company_name": comp,
                "org_id": r.get("organisation.id") or "",
                "org_identification": r.get("organisation.identification") or "",
                "org_commodities": "; ".join(str(c) for c in org_comms),
                "org_company_type": r.get("organisation.company_type") or "",
                "org_stock_exchange": r.get("organisation.stock_exchange_listing") or "",
                "government_entity": (r.get("goverment_entity") or "").strip(),
                "sector": (r.get("sector") or "").strip(),
                "gfs_code": r.get("gfs.code") or "",
                "gfs_label": gfs_label.strip(),
                "revenue_type": bucket,                                  # royalty_like / cit / equity / other
                "value_usd": "" if val is None else f"{val:.2f}",
                "payment_in_kind": "Y" if str(r.get("payment_made_in_kind") or "").strip().lower() in ("yes", "y", "true", "1") else "",
                "in_kind_volume": "" if ink_vol is None else f"{ink_vol:.4f}",
                "in_kind_unit": (r.get("unit") or "").strip(),
                "project_name": (r.get("project_name") or "").strip(),
                "revenue_stream_label": (r.get("label") or "").strip(),
                "comments": (r.get("comments") or "").strip()[:200],
            })

    cols = [
        "iso3", "year", "country_year_source",
        "commodity", "company_name", "org_id", "org_identification", "org_commodities",
        "org_company_type", "org_stock_exchange", "government_entity", "sector", "gfs_code", "gfs_label",
        "revenue_type", "value_usd", "payment_in_kind", "in_kind_volume", "in_kind_unit",
        "project_name", "revenue_stream_label", "comments",
    ]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    # report
    import collections
    by_iso = collections.Counter(r["iso3"] for r in rows)
    by_yr = collections.Counter(r["year"] for r in rows)
    by_rt = collections.Counter(r["revenue_type"] for r in rows)
    by_cm = collections.Counter(r["commodity"] for r in rows)
    by_src = collections.Counter(r["country_year_source"] for r in rows)
    val = sum(float(r["value_usd"]) for r in rows if r["value_usd"])
    val_by_src = collections.defaultdict(float)
    for r in rows:
        if r["value_usd"]:
            val_by_src[r["country_year_source"]] += float(r["value_usd"])

    print(f"\nWrote {OUT_CSV}: {len(rows):,} company-payment rows; total ${val/1e9:,.1f} B")
    print(f"  dropped: {dropped_general:,} general/economy-wide; {dropped_noyear:,} missing iso/year (still unrecoverable)")
    print(f"  country_year_source: {dict(by_src)}")
    for s, v in sorted(val_by_src.items(), key=lambda x: -x[1]):
        print(f"    {s:<14} ${v/1e9:,.1f} B")
    print(f"  countries: {len(by_iso)}  {dict(sorted(by_iso.items()))}")
    print(f"  years: {dict(sorted(by_yr.items()))}")
    print(f"  revenue_type: {dict(by_rt)}  |  commodity: {dict(by_cm)}")


def main():
    args = set(sys.argv[1:])
    if "--process-only" not in args:
        pull_summary_data(refresh="--refresh-summary-data" in args)
        pull_revenue(resume="--no-resume" not in args)
    process()


if __name__ == "__main__":
    main()
