# %%
"""
3_35 — EITI payments panel by HQ × source country.

Bring EITI company payments-to-government to a (HQ country × source country)
level using the Orbis HQ map. `hq_iso3` = matched HQ iso3, or "UNMATCHED" /
"UNKNOWN_HQ" when the EITI company could not be tied to an Orbis company (or it
was but its HQ country is unknown); `hq_iso3_domestic` = same, but
UNMATCHED/UNKNOWN is replaced by the source country (treat unmatched companies
as domestic operators).

Extractive prep, stage 3_35 — after 3_34, before 3_36.

Reads:
  data/intermediate/extractive/eiti_company_payments_long.csv  — classified company payments (3_31)
  data/intermediate/extractive/eiti_company_hq_map.csv         — company→HQ Orbis map (3_33)

Writes:
  data/intermediate/extractive/eiti_payments_by_hq_source_yearly.csv   — one row per
    (source iso3, HQ iso3, commodity, fiscal year, revenue type): summed USD value, row count,
    and the assume-domestic HQ variant
  data/intermediate/extractive/eiti_payments_by_hq_source_summary.csv  — coarser
    (source iso3, HQ iso3, fiscal year) totals

Usage:
  python 3_35_eiti_payments_by_hq_source.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup
import csv
import sys
from collections import defaultdict
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

PAY = EXT_INT / "eiti_company_payments_long.csv"
HQMAP = EXT_INT / "eiti_company_hq_map.csv"
OUT_YEARLY = EXT_INT / "eiti_payments_by_hq_source_yearly.csv"
OUT_SUMMARY = EXT_INT / "eiti_payments_by_hq_source_summary.csv"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# %% MARK: 2. Main
def main():
    # ── HQ map: (source_iso3, company_name) -> (hq_iso3, match_method, match_score, matched_name) ──
    hqmap = {}
    with open(HQMAP, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            hqmap[(r["source_iso3"], r["company_name"])] = (
                r.get("hq_iso3", "") or "", r.get("match_method", ""), r.get("match_score", ""),
                r.get("matched_orbis_name", "") or r.get("matched_guo_name", ""))
    print(f"HQ map entries: {len(hqmap):,}")

    # ── join payments with HQ; aggregate ──
    # key: (source, hq, hq_dom, commodity, year, revenue_type) -> {value_usd, n_rows, n_rows_no_usd}
    agg = defaultdict(lambda: {"value_usd": 0.0, "n_rows": 0, "n_rows_no_usd": 0})
    summ = defaultdict(lambda: {"value_usd": 0.0, "n_rows": 0})
    n_in = 0
    method_val = defaultdict(float)
    with open(PAY, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            n_in += 1
            src = r["iso3"]
            comp = r["company_name"]
            hq, method, score, mname = hqmap.get((src, comp), ("", "unmatched", "", ""))
            if not hq:
                hq_lab = "UNMATCHED" if method == "unmatched" else "UNKNOWN_HQ"
            else:
                hq_lab = hq
            # GFS 1153* = "revenues from sale of the state's share of production":
            # the payer is a CUSTOMER of the state marketer (SOMO crude buyers -
            # UNIPEC/Indian Oil/Valero/TOTSA trading arms), not a producer paying
            # fiscal obligations. The revenue is the state's own oil income ->
            # attribute DOMESTIC, never to the buyer's HQ. (Materially this is
            # Iraq, $752bn - NGA $0.9bn also moves.)
            if str(r.get("gfs_code", "")).startswith("1153") or (
                    src == "IRQ" and r.get("revenue_type") == "equity"):
                hq_lab = src
            hq_dom = src if hq_lab in ("UNMATCHED", "UNKNOWN_HQ") else hq
            # eiti_company_payments_long.csv writes the year as `year` (not
            # fy_end_year). A fy_end_year-first lookup would return empty for
            # every row → all aggregations would collapse onto fy_end_year=NaN,
            # making COD/MDG/etc. invisible in the yearly panel.
            year = r.get("year", "") or r.get("fy_end_year", "") or r.get("fy_start_year", "")
            comm = r.get("commodity", "") or "other"
            rtype = r.get("revenue_type", "") or "other"
            v = _f(r.get("value_usd"))
            k = (src, hq_lab, hq_dom, comm, year, rtype)
            a = agg[k]
            a["n_rows"] += 1
            if v is not None:
                a["value_usd"] += v
                method_val[method] += v
                summ[(src, hq_lab, hq_dom, year)]["value_usd"] += v
            elif r.get("value_local"):
                a["n_rows_no_usd"] += 1
            summ[(src, hq_lab, hq_dom, year)]["n_rows"] += 1

    # ── write yearly granular ──
    OUT_YEARLY.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_YEARLY, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_iso3", "hq_iso3", "hq_iso3_domestic", "commodity", "fy_end_year",
                    "revenue_type", "value_usd", "n_payment_rows", "n_rows_value_no_usd"])
        for (src, hq, hqd, comm, yr, rt), a in sorted(agg.items()):
            w.writerow([src, hq, hqd, comm, yr, rt, f"{a['value_usd']:.2f}", a["n_rows"], a["n_rows_no_usd"]])
    # ── write summary ──
    with open(OUT_SUMMARY, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_iso3", "hq_iso3", "hq_iso3_domestic", "fy_end_year", "value_usd", "n_payment_rows"])
        for (src, hq, hqd, yr), a in sorted(summ.items()):
            w.writerow([src, hq, hqd, yr, f"{a['value_usd']:.2f}", a["n_rows"]])

    # ── report ──
    tot = sum(a["value_usd"] for a in agg.values())
    by_hqlab = defaultdict(float)
    foreign = domestic = unmatched_v = unknown_v = 0.0
    for (src, hq, hqd, comm, yr, rt), a in agg.items():
        v = a["value_usd"]
        by_hqlab[hq] += v
        if hq == "UNMATCHED":
            unmatched_v += v
        elif hq == "UNKNOWN_HQ":
            unknown_v += v
        elif hq == src:
            domestic += v
        else:
            foreign += v
    print(f"\nWrote {OUT_YEARLY} ({len(agg):,} rows) and {OUT_SUMMARY} ({len(summ):,} rows).")
    print(f"Input payment rows: {n_in:,}.  Total value (USD-converted): ${tot/1e9:,.1f} B")
    print(f"  foreign HQ:  ${foreign/1e9:,.1f} B   domestic (HQ == source): ${domestic/1e9:,.1f} B")
    print(f"  HQ unknown (matched, no country): ${unknown_v/1e9:,.1f} B   unmatched (no Orbis link): ${unmatched_v/1e9:,.1f} B")
    print(f"  → with the 'assume domestic' fallback, ${(domestic+unmatched_v+unknown_v)/1e9:,.1f} B is domestic, ${foreign/1e9:,.1f} B foreign.")
    print("  match-method shares of value ($B):", {m: round(v/1e9, 1) for m, v in sorted(method_val.items(), key=lambda kv: -kv[1])})
    # by revenue_type
    by_rt = defaultdict(float)
    for (src, hq, hqd, comm, yr, rt), a in agg.items():
        by_rt[rt] += a["value_usd"]
    print("  by revenue_type ($B):", {rt: round(v/1e9, 1) for rt, v in sorted(by_rt.items(), key=lambda kv: -kv[1])})
    # top foreign corridors
    corr = defaultdict(float)
    for (src, hq, hqd, comm, yr, rt), a in agg.items():
        if hq not in ("UNMATCHED", "UNKNOWN_HQ") and hq != src:
            corr[(hq, src)] += a["value_usd"]
    print("  top 20 foreign HQ→source corridors ($B):")
    for (hq, src), v in sorted(corr.items(), key=lambda kv: -kv[1])[:20]:
        print(f"    {hq} → {src}: {v/1e9:,.1f}")
    # top HQ countries (foreign)
    fh = defaultdict(float)
    for (hq, src), v in corr.items():
        fh[hq] += v
    print("  top foreign HQ countries ($B):", {h: round(v/1e9, 1) for h, v in sorted(fh.items(), key=lambda kv: -kv[1])[:15]})


if __name__ == "__main__":
    main()
