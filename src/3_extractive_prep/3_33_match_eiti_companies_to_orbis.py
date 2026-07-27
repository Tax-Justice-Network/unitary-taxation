# %%
"""
3_33 — Match EITI companies to Orbis (attach HQ country).

Attach an HQ (global-ultimate-owner) country to every EITI company by matching
the EITI company name against the full Orbis extractive-entity universe
(orbis_entity_universe.csv, built by 3_32 — ~600k entities including local
operating subsidiaries, each carrying its GUO bvd-id / name / type / country).
An EITI payment in country C is made by an entity operating in C, almost always
incorporated in C, so the EITI name is matched against the Orbis entities with
entity_country == C first, falling back to a global match. For a matched entity:
HQ country = its guo_country; in_cbcr_universe flag (a multi-entity extractive
group above the €750M turnover threshold) is carried through, used in 3_38 to
decide whether the domestic portion of a payment lands on a CbCR cell. A
hand-curated override list (major operators / NOCs) is applied first as a fast
path.

Extractive prep, stage 3_33 — after 3_32, before 3_34.

Reads:
  data/intermediate/extractive/eiti_company_payments_long.csv  — classified company payments (3_31)
  data/intermediate/extractive/orbis_entity_universe.csv       — Orbis entity→GUO universe (3_32)
  data/raw/extractive/eiti_company_hq_overrides.csv            — hand-curated company→HQ overrides

Writes:
  data/intermediate/extractive/eiti_company_hq_map.csv  — one row per (source iso3, EITI company):
    matched Orbis entity + bvd_id, GUO name/type, hq_iso3, in_cbcr_universe, match method & score,
    payment value & row count.

Usage:
  python 3_33_match_eiti_companies_to_orbis.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import csv
import re
import sys
import unicodedata
from collections import defaultdict

from rapidfuzz import process, fuzz
import pycountry

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT, RAW

EITI_PAY = EXT_INT / "eiti_company_payments_long.csv"
UNIVERSE = EXT_INT / "orbis_entity_universe.csv"
OUT = EXT_INT / "eiti_company_hq_map.csv"

FUZZY_THRESHOLD = 90

# %% MARK: 2. Overrides and lookups
# Hand-curated company -> HQ overrides (major operators / NOCs + the ~$300B unmatched-value
# audit), applied before any automatic matching. Curated in
# data/raw/extractive/eiti_company_hq_overrides.csv — see that file's header for the
# column semantics (match_substring / canonical_name / hq_iso2 / is_cbcr_filer / group).
OVR_FILE = RAW / "extractive" / "eiti_company_hq_overrides.csv"
OVERRIDES = []   # (match_substring, canonical_name, hq_iso2, is_cbcr_filer|None)
with open(OVR_FILE, encoding="utf-8-sig", newline="") as _f:
    for _r in csv.DictReader(_l for _l in _f if not _l.lstrip().startswith("#")):
        _flag = {"true": True, "false": False}.get(_r["is_cbcr_filer"].strip().lower())
        OVERRIDES.append((_r["match_substring"], _r["canonical_name"], _r["hq_iso2"], _flag))

LEGAL_TOKENS = {
    "sa", "sas", "sasu", "sarl", "sarlu", "sau", "spa", "srl", "ltd", "limited", "plc", "llc", "llp",
    "inc", "incorporated", "corp", "corporation", "co", "company", "cia", "gmbh", "ag", "kg", "nv", "bv",
    "ab", "as", "asa", "oy", "oyj", "ojsc", "pjsc", "jsc", "oao", "zao", "pao", "pty", "pvt", "ltda",
    "eurl", "gie", "sca", "scs", "snc", "se", "kk", "kgaa", "lp", "ulc", "unltd", "pc", "pllc",
    "doo", "dd", "ad", "ead", "tov", "too", "ip", "pe", "fze", "fzco", "wll", "lda", "scarl", "scrl",
    "the", "of", "and", "for", "de", "du", "des", "la", "le", "les", "el", "der", "die", "das", "y",
}
GENERIC_WORDS = {
    "mining", "mines", "mine", "minerals", "mineral", "oil", "gas", "petroleum", "petrole", "petroleos",
    "energy", "energie", "energia", "resources", "resource", "exploration", "production", "development",
    "international", "group", "holdings", "holding", "company", "industries", "industrial", "metals",
    "metal", "gold", "copper", "iron", "coal", "diamond", "diamonds", "national", "africa", "african",
    "global", "ventures", "venture", "trading", "trade", "general", "limited", "societe",
    "compania", "compagnie", "enterprises", "enterprise", "services", "operations", "joint",
}


# Cyrillic → Latin transliteration table (GOST 7.79-2000 System B / common scientific).
# Applied before NFKD/ASCII-ignore so Russian/Ukrainian/Kazakh names survive normalisation.
# Without this step EITI rows from TJK/KAZ/KGZ/UKR/RUS in Cyrillic-only get dropped.
_CYRILLIC_MAP = {
    "А":"A","Б":"B","В":"V","Г":"G","Д":"D","Е":"E","Ё":"E","Ж":"ZH","З":"Z",
    "И":"I","Й":"I","К":"K","Л":"L","М":"M","Н":"N","О":"O","П":"P","Р":"R",
    "С":"S","Т":"T","У":"U","Ф":"F","Х":"KH","Ц":"TS","Ч":"CH","Ш":"SH","Щ":"SHCH",
    "Ъ":"","Ы":"Y","Ь":"","Э":"E","Ю":"YU","Я":"YA",
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z",
    "и":"i","й":"i","к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r",
    "с":"s","т":"t","у":"u","ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
    "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
    # Additional letters used in Kazakh / Tajik / Kyrgyz / Ukrainian
    "Ә":"AE","Ғ":"GH","Қ":"Q","Ң":"NG","Ө":"OE","Ұ":"U","Ү":"UE","Һ":"H","І":"I","Ї":"I","Є":"YE","Ҷ":"J","Ҳ":"H","Ӣ":"I","Ӯ":"U","Қ":"Q",
    "ә":"ae","ғ":"gh","қ":"q","ң":"ng","ө":"oe","ұ":"u","ү":"ue","һ":"h","і":"i","ї":"i","є":"ye","ҷ":"j","ҳ":"h","ӣ":"i","ӯ":"u",
}
_CYRILLIC_TRANS = str.maketrans(_CYRILLIC_MAP)


# %% MARK: 3. Name normalisation
def normalise(name):
    if not name:
        return ""
    s = str(name).translate(_CYRILLIC_TRANS)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").upper()
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return " ".join(t for t in s.split() if t.lower() not in LEGAL_TOKENS).strip()


def to_iso3(iso2):
    if not iso2:
        return ""
    iso2 = str(iso2).strip().upper()
    if len(iso2) == 3:
        return iso2
    fix = {"XK": "XKX", "KV": "XKX"}
    if iso2 in fix:
        return fix[iso2]
    try:
        c = pycountry.countries.get(alpha_2=iso2)
        return c.alpha_3 if c else ""
    except Exception:
        return ""


def is_anchor(norm):
    words = norm.split()
    ng = [w for w in words if w.lower() not in GENERIC_WORDS]
    return (len(words) >= 2 and len(ng) >= 1) or (len(words) == 1 and len(words[0]) >= 5 and words[0].lower() not in GENERIC_WORDS)


# %% MARK: 4. Main
def main():
    # ── 1. load Orbis universe; index by entity country ──
    # rows: bvd_id,name,entity_country,nace_core,n_subsidiaries,guo_bvd_id,guo_name,guo_type,guo_country,peak_operating_revenue_th_usd,in_cbcr_universe
    by_country_norm = defaultdict(lambda: defaultdict(list))   # iso3 -> norm -> [cand]
    global_norm = defaultdict(list)                            # norm -> [cand]   (only in_cbcr_universe entities, for the global fallback)
    n_ent = 0
    with open(UNIVERSE, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            nm = normalise(r["name"])
            if not nm:
                continue
            n_ent += 1
            ec3 = to_iso3(r["entity_country"]) or r["entity_country"].strip().upper()
            gc2 = (r["guo_country"] or r["entity_country"] or "").strip()
            cand = {"bvd_id": r["bvd_id"], "orbis_name": r["name"], "guo_name": r.get("guo_name", ""),
                    "guo_type": r.get("guo_type", ""), "hq_iso3": to_iso3(gc2),
                    "in_cbcr_universe": (str(r.get("in_cbcr_universe", "")).strip() in ("1", "True", "true")),
                    "n_subs": r.get("n_subsidiaries", ""), "rev": r.get("peak_operating_revenue_th_usd", "")}
            by_country_norm[ec3][nm].append(cand)
            if cand["in_cbcr_universe"]:
                global_norm[nm].append(cand)
    # per-country anchor lists (longest first) for substring matching
    country_anchors = {c: sorted((n for n in norms if is_anchor(n)), key=lambda s: (-len(s.split()), -len(s)))
                       for c, norms in by_country_norm.items()}
    global_anchors = sorted((n for n in global_norm if is_anchor(n)), key=lambda s: (-len(s.split()), -len(s)))
    print(f"Orbis universe: {n_ent:,} named entities in {len(by_country_norm)} countries; {len(global_norm):,} distinct in-CbCR-universe names for the global fallback")

    def pick(cands):
        # prefer an in-CbCR-universe candidate (the real MNE parent), then the one with most subsidiaries
        mne = [c for c in cands if c["in_cbcr_universe"]]
        pool = mne or cands
        def nsub(c):
            try:
                return int(c["n_subs"])
            except (ValueError, TypeError):
                return -1
        return max(pool, key=nsub)

    # ── 2. distinct EITI (source iso3, company) with value weight ──
    eiti = defaultdict(lambda: {"n_rows": 0, "value_usd": 0.0})
    with open(EITI_PAY, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            k = (r["iso3"], r["company_name"])
            eiti[k]["n_rows"] += 1
            v = r.get("value_usd", "")
            if v:
                try:
                    eiti[k]["value_usd"] += float(v)
                except ValueError:
                    pass
    print(f"Distinct (source country, EITI company): {len(eiti):,}")

    ovr = sorted(((normalise(k), name, hq, flag) for k, name, hq, flag in OVERRIDES if normalise(k)), key=lambda t: -len(t[0]))

    # ── 3. match ──
    out_rows = []
    counts = defaultdict(int)
    norm_cache = {}
    for (iso3, company), w in sorted(eiti.items()):
        q = norm_cache.get(company)
        if q is None:
            q = normalise(company)
            norm_cache[company] = q
        q_pad = " " + q + " " if q else " "
        m = None   # dict: bvd_id, orbis_name, guo_name, guo_type, hq_iso3, in_cbcr_universe, score, method
        if not q:
            pass
        elif (oh := next(((kn, name, hq, flag) for kn, name, hq, flag in ovr if " " + kn + " " in q_pad), None)):
            kn, name, hq, flag = oh
            hq3 = to_iso3(hq)
            # if the override didn't fix the filer flag, try to learn it from the Orbis universe by the canonical name
            in_u = flag
            if in_u is None:
                gn = normalise(name)
                cl = global_norm.get(gn) or by_country_norm.get(hq3, {}).get(gn)
                if cl:
                    # canonical name found in Orbis: TRUST its in_cbcr_universe
                    # flag (a False here is a real sub-threshold/domestic vehicle)
                    in_u = bool(pick(cl)["in_cbcr_universe"])
                else:
                    # not in Orbis at all: overrides are major operators → True
                    in_u = True
            m = {"bvd_id": "", "orbis_name": name, "guo_name": name, "guo_type": "", "hq_iso3": hq3,
                 "in_cbcr_universe": bool(in_u), "score": 99.0, "method": "override"}
            counts["override"] += 1
        else:
            cn = by_country_norm.get(iso3, {})
            ca = country_anchors.get(iso3, [])
            if q in cn:
                c = pick(cn[q]); m = dict(c, score=100.0, method="exact_norm_country")
            elif (hit := next((g for g in ca if " " + g + " " in q_pad), None)):
                c = pick(cn[hit]); m = dict(c, score=95.0, method="substring_country")
            elif cn and (res := process.extractOne(q, list(cn.keys()), scorer=fuzz.token_sort_ratio, score_cutoff=FUZZY_THRESHOLD)):
                c = pick(cn[res[0]]); m = dict(c, score=float(res[1]), method="fuzzy_country")
            elif q in global_norm:
                c = pick(global_norm[q]); m = dict(c, score=100.0, method="exact_norm_global")
            elif (hit := next((g for g in global_anchors if " " + g + " " in q_pad), None)):
                c = pick(global_norm[hit]); m = dict(c, score=95.0, method="substring_global")
            if m is not None:
                counts[m["method"]] += 1
        if m is None:
            counts["unmatched"] += 1
            out_rows.append({"source_iso3": iso3, "company_name": company, "company_norm": q, "n_payment_rows": w["n_rows"],
                             "total_value_usd": f"{w['value_usd']:.2f}", "matched_orbis_name": "", "matched_bvd_id": "",
                             "matched_guo_name": "", "guo_type": "", "hq_iso3": "", "in_cbcr_universe": "",
                             "match_score": "", "match_method": "unmatched"})
        else:
            out_rows.append({"source_iso3": iso3, "company_name": company, "company_norm": q, "n_payment_rows": w["n_rows"],
                             "total_value_usd": f"{w['value_usd']:.2f}", "matched_orbis_name": m.get("orbis_name", ""),
                             "matched_bvd_id": m.get("bvd_id", ""), "matched_guo_name": m.get("guo_name", ""), "guo_type": m.get("guo_type", ""),
                             "hq_iso3": m.get("hq_iso3", ""), "in_cbcr_universe": int(bool(m.get("in_cbcr_universe", False))),
                             "match_score": f"{m['score']:.0f}", "match_method": m["method"]})

    cols = ["source_iso3", "company_name", "company_norm", "n_payment_rows", "total_value_usd",
            "matched_orbis_name", "matched_bvd_id", "matched_guo_name", "guo_type", "hq_iso3", "in_cbcr_universe", "match_score", "match_method"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w_ = csv.DictWriter(f, fieldnames=cols)
        w_.writeheader()
        for r in out_rows:
            w_.writerow(r)

    # ── 4. coverage report ──
    def vf(rows):
        return sum(float(r["total_value_usd"]) for r in rows)
    tot_v = vf(out_rows)
    matched = [r for r in out_rows if r["match_method"] != "unmatched"]
    mne = [r for r in matched if str(r["in_cbcr_universe"]) == "1"]
    dom = [r for r in matched if r["hq_iso3"] and r["hq_iso3"] == r["source_iso3"]]
    dom_mne = [r for r in dom if str(r["in_cbcr_universe"]) == "1"]
    n = len(out_rows); nm = len(matched)
    print(f"\nWrote {OUT}: {n:,} (source, company) rows.")
    print(f"  matched: {nm:,} ({100*nm/n:.0f}% of names) — " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"  value matched to an Orbis entity: ${vf(matched)/1e9:,.1f} B of ${tot_v/1e9:,.1f} B ({100*vf(matched)/tot_v:.0f}% by value)")
    print(f"  of matched value: in CbCR universe ${vf(mne)/1e9:,.1f} B | not ${ (vf(matched)-vf(mne))/1e9:,.1f} B")
    print(f"  domestic (hq==source): ${vf(dom)/1e9:,.1f} B, of which in CbCR universe ${vf(dom_mne)/1e9:,.1f} B (the rest of the domestic slice is dropped in 3_38)")
    fhq = defaultdict(float)
    for r in matched:
        if r["hq_iso3"] and r["hq_iso3"] != r["source_iso3"]:
            fhq[r["hq_iso3"]] += float(r["total_value_usd"])
    print("  top foreign-HQ countries by matched value ($B): " + ", ".join(f"{k} {v/1e9:,.0f}" for k, v in sorted(fhq.items(), key=lambda kv: -kv[1])[:15]))


if __name__ == "__main__":
    main()
