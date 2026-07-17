"""
Sanity checks for the EITI-company-payments → HQ pipeline (scripts 1_6/1_7/1_8).

Run after 1_6/1_7/1_8. Pass/fail checks on structure + reconciliation; plus an
(informational) coverage report. Writes a small results file.
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _paths import EXT_INT

PAY = EXT_INT / "eiti_company_payments_long.csv"
HQMAP = EXT_INT / "eiti_company_hq_map.csv"
BYHQ = EXT_INT / "eiti_payments_by_hq_source_yearly.csv"
RESULTS = (EXT_INT / ".." / ".." / "output" / "extractive" / "tables" / "eiti_company_payments_sanity.txt").resolve()

VALID_RTYPE = {"royalty_like", "cit", "equity", "other"}
VALID_USD_STATUS = {"reported_usd", "fx_converted", "no_currency", "no_fx", "dropped_outlier", ""}
VALID_METHOD = {"override", "exact_norm", "substring", "fuzzy_sort", "fuzzy_set", "unmatched"}
# a sample of "general / economy-wide" stream hints that must NOT appear in the output
GENERAL_HINTS = ("value added tax", "value-added tax", " vat ", "(vat)", "general taxes on goods and services",
                 " gst ", "(gst)", "taxe sur la valeur ajoutee", " tva ", "(tva)", "impuesto al valor agregado",
                 "(iva)", " iva ", "sales tax", "turnover tax", "customs", "import dut", "import duties",
                 "social security", "social contribution", "payroll tax", "pay as you earn", "(paye)",
                 "personal income tax", "motor vehicle", "property tax", "co2 tax", "carbon tax")

results = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    line = f"  [{tag}] {name}" + (f" — {detail}" if detail else "")
    print(line)
    results.append((ok, line))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    # ── load ──
    pay = list(csv.DictReader(open(PAY, encoding="utf-8")))
    hq = list(csv.DictReader(open(HQMAP, encoding="utf-8")))
    byhq = list(csv.DictReader(open(BYHQ, encoding="utf-8")))
    print(f"payments rows: {len(pay):,}; hq-map rows: {len(hq):,}; by-hq-source rows: {len(byhq):,}\n")

    n_v = sum(1 for r in pay if r["value_usd"])
    # ── A. payments file ──
    print("=== A. payments file ===")
    bad_iso = sum(1 for r in pay if len(r["iso3"]) != 3)
    check("A1: iso3 is 3 chars", bad_iso == 0, f"{bad_iso} bad")
    bad_rt = sum(1 for r in pay if r["revenue_type"] not in VALID_RTYPE)
    check("A2: revenue_type in {royalty_like,cit,equity,other}", bad_rt == 0, f"{bad_rt} bad")
    # exact check: re-run the parser's classifier on every output row — nothing should classify as "general"
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location("_p6", Path(__file__).parent / "1_6_parse_eiti_company_payments.py")
        _p6 = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_p6)
        gen_leak = sum(1 for r in pay if _p6.classify_stream(r["gfs_classification"], r["revenue_stream"]) == "general")
        check("A3: no row classifies as general/economy-wide (re-run of the parser's classifier)", gen_leak == 0, f"{gen_leak} such rows")
    except Exception as e:
        # fallback heuristic
        gen_leak = sum(1 for r in pay if any(h in (" " + r["revenue_stream"].lower() + " || " + r["gfs_classification"].lower() + " ") for h in GENERAL_HINTS))
        check("A3: no general/economy-wide rows leaked (heuristic; classifier import failed)", gen_leak == 0, f"{gen_leak} such rows; import err: {e}")
    bad_us = sum(1 for r in pay if r.get("value_usd_status", "") not in VALID_USD_STATUS)
    check("A4: value_usd_status in known set", bad_us == 0, f"{bad_us} bad")
    bad_v = [r for r in pay if r["value_usd"] and _f(r["value_usd"]) is None]
    check("A5: value_usd blank or a number (negatives allowed — refunds/credits/adjustments)", len(bad_v) == 0, f"{len(bad_v)} unparseable")
    big = [r for r in pay if r["value_usd"] and _f(r["value_usd"]) is not None and abs(_f(r["value_usd"])) > 5e10]
    check("A6: no single |value_usd| > $50B", len(big) == 0, f"{len(big)}: " + ", ".join(f"{r['iso3']}/{r['company_name'][:25]}" for r in big[:3]))
    n_neg = sum(1 for r in pay if r["value_usd"] and (_f(r["value_usd"]) or 0) < 0)
    check("A6b: negative-value rows are a small minority (<3%)", n_neg / max(1, n_v) < 0.03, f"{n_neg} negatives ({100*n_neg/max(1,n_v):.1f}%)")
    check("A7: a majority of rows have a USD value", n_v / max(1, len(pay)) > 0.6, f"{100*n_v/max(1,len(pay)):.0f}%")

    # ── B. HQ map ──
    print("\n=== B. HQ map ===")
    bad_m = sum(1 for r in hq if r["match_method"] not in VALID_METHOD)
    check("B1: match_method in known set", bad_m == 0, f"{bad_m} bad")
    # every (iso3, company) in payments has a map entry
    map_keys = {(r["source_iso3"], r["company_name"]) for r in hq}
    pay_keys = {(r["iso3"], r["company_name"]) for r in pay}
    missing = pay_keys - map_keys
    check("B2: every (source, company) in payments is in the HQ map", len(missing) == 0, f"{len(missing)} missing")
    bad_hq3 = sum(1 for r in hq if r["match_method"] != "unmatched" and r["hq_iso3"] and len(r["hq_iso3"]) != 3)
    check("B3: matched rows have a 3-char (or blank) hq_iso3", bad_hq3 == 0, f"{bad_hq3} bad")
    bad_score = sum(1 for r in hq if r["match_method"] != "unmatched" and (_f(r["match_score"]) is None))
    check("B4: matched rows have a numeric match_score", bad_score == 0, f"{bad_score} bad")
    unmatched_with_hq = sum(1 for r in hq if r["match_method"] == "unmatched" and r["hq_iso3"])
    check("B5: unmatched rows have no hq_iso3", unmatched_with_hq == 0, f"{unmatched_with_hq} bad")

    # ── C. by-hq-source file & reconciliation ──
    print("\n=== C. by-HQ-source file ===")
    bad_v3 = sum(1 for r in byhq if r["value_usd"] and _f(r["value_usd"]) is None)
    check("C1: value_usd is a number (negatives allowed)", bad_v3 == 0, f"{bad_v3} unparseable")
    bad_dom = sum(1 for r in byhq if r["hq_iso3_domestic"] in ("UNMATCHED", "UNKNOWN_HQ"))
    check("C2: hq_iso3_domestic never UNMATCHED/UNKNOWN", bad_dom == 0, f"{bad_dom} bad")
    bad_rt2 = sum(1 for r in byhq if r["revenue_type"] not in VALID_RTYPE)
    check("C3: revenue_type in known set", bad_rt2 == 0, f"{bad_rt2} bad")
    tot_pay = sum(_f(r["value_usd"]) or 0.0 for r in pay)
    tot_byhq = sum(_f(r["value_usd"]) or 0.0 for r in byhq)
    check("C4: by-HQ totals reconcile with payments file (≤0.5% diff)", abs(tot_pay - tot_byhq) <= 0.005 * max(1.0, tot_pay),
          f"payments ${tot_pay/1e9:,.1f}B vs by-HQ ${tot_byhq/1e9:,.1f}B")
    # per (source, year) reconciliation
    p_sy = defaultdict(float)
    for r in pay:
        if r["value_usd"]:
            p_sy[(r["iso3"], r.get("fy_end_year", ""))] += _f(r["value_usd"])
    b_sy = defaultdict(float)
    for r in byhq:
        b_sy[(r["source_iso3"], r["fy_end_year"])] += _f(r["value_usd"]) or 0.0
    mism = sum(1 for k in set(p_sy) | set(b_sy) if abs(p_sy.get(k, 0) - b_sy.get(k, 0)) > 1.0)
    check("C5: per (source, year) totals reconcile", mism == 0, f"{mism} mismatched cells")

    # ── coverage (informational) ──
    print("\n=== Coverage (informational) ===")
    tot_v = sum(_f(r["total_value_usd"]) or 0.0 for r in hq)
    matched_v = sum(_f(r["total_value_usd"]) or 0.0 for r in hq if r["match_method"] != "unmatched")
    n = len(hq); nm = sum(1 for r in hq if r["match_method"] != "unmatched")
    print(f"  countries: {len({r['iso3'] for r in pay})}; (source, company) names: {n:,} ({nm:,} matched = {100*nm/n:.0f}%)")
    print(f"  payment value matched to an Orbis company: ${matched_v/1e9:,.1f}B of ${tot_v/1e9:,.1f}B ({100*matched_v/max(1,tot_v):.0f}% by value)")
    by_rt = defaultdict(float)
    for r in pay:
        if r["value_usd"]:
            by_rt[r["revenue_type"]] += _f(r["value_usd"])
    print("  value by revenue_type ($B):", {k: round(v / 1e9, 1) for k, v in sorted(by_rt.items(), key=lambda kv: -kv[1])})

    npass = sum(1 for ok, _ in results if ok)
    nfail = len(results) - npass
    print(f"\nResults: {npass}/{len(results)} passed, {nfail} failed")
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS, "w", encoding="utf-8") as f:
        f.write(f"EITI company-payments sanity: {npass}/{len(results)} passed, {nfail} failed\n\n")
        for ok, line in results:
            f.write(line + "\n")
    if nfail:
        sys.exit(1)


if __name__ == "__main__":
    main()
