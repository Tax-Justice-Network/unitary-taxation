"""
Apply manual corrections to EITI bucket classification (carried state participation).

Reads:
  data/final/extractive_royalty_dataset_yearly.csv
  data/raw/resources/carried_state_classification_fixes.csv

Writes:
  data/final/extractive_royalty_dataset_yearly.csv  (in-place)
  data/final/carried_state_classification_log.csv  (audit trail)

For each correction row, moves `value_usd` between the relevant captured_* columns.
captured_total_usd is invariant (just rebucketed). captured_deductible/cit/equity
are updated.

Bucket → captured-column mapping:
  production_ent, royalties, bonuses, licence_fees, other_rent,
  delivered_directly, ...                    → captured_deductible_usd
  cit, extraordinary_cit                     → captured_cit_usd
  soe_profits, from_soe, dividends,
  govt_participation, delivered_to_soe       → captured_equity_usd

Run AFTER 2_4_build_consolidated_yearly.py and BEFORE 4_3_approach1_carveout.py.
"""

import csv
import os
import sys
from collections import defaultdict
from _paths import RAW, EXT_INT

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

YEAR_PANEL = EXT_INT / "extractive_royalty_dataset_yearly.csv"
FIXES = RAW / "resources" / "carried_state_classification_fixes.csv"   # hand-curated
LOG = EXT_INT / "carried_state_classification_log.csv"

DEDUCTIBLE_BUCKETS = {
    "royalties", "bonuses", "production_ent", "licence_fees", "other_rent",
    "delivered_directly", "rent", "customs", "excise", "export_tax",
    "property_tax", "payroll_tax", "other_taxes_natres", "admin_fees",
    "compulsory_transfers", "fines", "emission_tax", "motor_vehicle",
}
CIT_BUCKETS = {"cit", "extraordinary_cit"}
EQUITY_BUCKETS = {
    "soe_profits", "from_soe", "dividends",
    "govt_participation", "delivered_to_soe", "quasi_corp",
}


def bucket_to_column(bucket):
    if bucket in DEDUCTIBLE_BUCKETS:
        return "captured_deductible_usd"
    if bucket in CIT_BUCKETS:
        return "captured_cit_usd"
    if bucket in EQUITY_BUCKETS:
        return "captured_equity_usd"
    return None


def _f(s):
    if s is None:
        return 0.0
    s = str(s).strip()
    if not s or s.lower() in ("n.a.", "nan", "none", "-"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def main():
    # Load fixes
    fixes = []
    if FIXES.exists():
        with open(FIXES, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = next(csv.reader([line]))
                if parts and parts[0] == "iso3":
                    continue
                if len(parts) < 5:
                    continue
                try:
                    val = float(parts[4])
                    yr = int(parts[1])
                except (ValueError, IndexError):
                    continue
                fixes.append({
                    "iso3": parts[0].strip(),
                    "year": yr,
                    "bucket_from": parts[2].strip(),
                    "bucket_to": parts[3].strip(),
                    "value_usd": val,
                    "eiti_year": parts[5].strip() if len(parts) > 5 else "",
                    "page_ref": parts[6].strip() if len(parts) > 6 else "",
                    "notes": parts[7].strip() if len(parts) > 7 else "",
                })

    print(f"Loaded {len(fixes)} carry-classification fixes")
    if not fixes:
        print("No fixes to apply — exiting cleanly")
        return

    # Validate buckets
    for fix in fixes:
        for side in ("from", "to"):
            b = fix[f"bucket_{side}"]
            if bucket_to_column(b) is None:
                print(f"ERROR: unknown bucket '{b}' in fix {fix['iso3']}/{fix['year']}")
                sys.exit(1)

    # Load year panel
    if not YEAR_PANEL.exists():
        print(f"ERROR: {YEAR_PANEL} not found. Run 2_4 first.")
        sys.exit(1)
    with open(YEAR_PANEL, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames)
        rows = list(reader)

    # Index by (iso3, year)
    row_index = {(r["iso3"], int(r["year"])): r for r in rows}

    # Apply fixes
    log_rows = []
    for fix in fixes:
        key = (fix["iso3"], fix["year"])
        row = row_index.get(key)
        if row is None:
            print(f"WARNING: no panel row for {fix['iso3']} {fix['year']} — skipping fix")
            continue
        col_from = bucket_to_column(fix["bucket_from"])
        col_to = bucket_to_column(fix["bucket_to"])
        before_from = _f(row.get(col_from))
        before_to = _f(row.get(col_to))
        new_from = max(0.0, before_from - fix["value_usd"])
        new_to = before_to + fix["value_usd"]
        row[col_from] = f"{new_from:.0f}" if new_from > 0 else ""
        row[col_to] = f"{new_to:.0f}" if new_to > 0 else ""
        # Source columns track that a manual fix was applied
        for c, src_col in ((col_from, f"{col_from.replace('_usd', '_source')}"),
                           (col_to, f"{col_to.replace('_usd', '_source')}")):
            if src_col in row:
                cur = (row[src_col] or "").strip()
                tag = "MANUAL_CARRY_FIX"
                if tag not in cur:
                    row[src_col] = (cur + ";" + tag).strip(";") if cur else tag

        log_rows.append({
            "iso3": fix["iso3"], "year": fix["year"],
            "bucket_from": fix["bucket_from"], "bucket_to": fix["bucket_to"],
            "value_usd": fix["value_usd"],
            f"{col_from}_before": before_from, f"{col_from}_after": new_from,
            f"{col_to}_before": before_to,    f"{col_to}_after": new_to,
            "eiti_year": fix["eiti_year"], "page_ref": fix["page_ref"],
            "notes": fix["notes"],
        })

    # Write back
    with open(YEAR_PANEL, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f"Updated {YEAR_PANEL}")

    # Audit log
    if log_rows:
        with open(LOG, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=log_rows[0].keys())
            writer.writeheader()
            writer.writerows(log_rows)
        print(f"Audit log: {LOG} ({len(log_rows)} fixes applied)")


if __name__ == "__main__":
    main()
