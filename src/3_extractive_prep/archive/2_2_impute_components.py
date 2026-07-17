"""
Impute missing CIT and deductible/equity components for countries that have only
total resource revenue (typically manual-fill countries lacking a fiscal-detail
breakdown).

Reads: data/final/extractive_royalty_dataset.csv
Writes: same file, with new columns:
  - actual_captured_cit_usd_imputed       (imputed value if original was empty)
  - actual_captured_cit_imputed_flag      (TRUE if imputed, FALSE if original)
  - actual_captured_deductible_usd_imputed
  - actual_captured_deductible_imputed_flag
  - imputation_method                     (which ratio source was used)

Method:
- Compute median CIT/total ratio across countries with both populated, separately
  for GRD-sourced and EITI-sourced totals (they differ: GRD ~0.41, EITI ~0.18
  because EITI's total includes equity flows that GRD's resource_taxes excludes).
- For total-only countries, apply the source-matched ratio to total to impute CIT.
- For deductible: residual = total − imputed_cit − captured_equity (if available).
  If equity unknown, use median deductible/total ratio.

Limitation: imputation is country-invariant within each source category. Real-
world CIT/total varies a lot (Norway ring-fence regimes vs flat-CIT regimes).
For the top-rent imputation candidates (RUS, SAU, IRN, KWT, ARE, etc), manual
fiscal-regime research would be more accurate — see Task 5 (effective rate
lookup) for a planned upgrade.
"""

import csv
import statistics
from _paths import FINAL


def f(s):
    try: return float(s) if s else 0.0
    except: return 0.0


def main():
    path = FINAL / "extractive_royalty_dataset.csv"
    with open(path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = list(reader.fieldnames)
        rows = list(reader)

    # ── Compute reference ratios from countries with both ──
    grd_cit_ratios, eiti_cit_ratios = [], []
    grd_ded_ratios, eiti_ded_ratios = [], []
    grd_eq_ratios, eiti_eq_ratios = [], []
    for r in rows:
        t = f(r.get("actual_captured_total_usd"))
        if t <= 0:
            continue
        cit = f(r.get("actual_captured_cit_usd"))
        ded = f(r.get("actual_captured_deductible_usd"))
        eq  = f(r.get("actual_captured_equity_usd"))
        is_grd = r.get("actual_captured_total_source") == "GRD"
        # Cap ratios at 1.5 to filter year-mismatch outliers
        if 0 < cit / t < 1.5:
            (grd_cit_ratios if is_grd else eiti_cit_ratios).append(cit / t)
        if 0 < ded / t < 1.5:
            (grd_ded_ratios if is_grd else eiti_ded_ratios).append(ded / t)
        if 0 < eq / t < 1.5:
            (grd_eq_ratios if is_grd else eiti_eq_ratios).append(eq / t)

    def med(xs, default):
        return statistics.median(xs) if xs else default

    cit_ratio_grd  = med(grd_cit_ratios, 0.40)
    cit_ratio_eiti = med(eiti_cit_ratios, 0.18)
    ded_ratio_grd  = med(grd_ded_ratios, 0.55)
    ded_ratio_eiti = med(eiti_ded_ratios, 0.50)
    eq_ratio_grd   = med(grd_eq_ratios, 0.0)   # GRD nontax mixes equity in; EITI cleaner
    eq_ratio_eiti  = med(eiti_eq_ratios, 0.20)

    print(f"Reference ratios (median across countries with both populated):")
    print(f"  CIT/total       — GRD: {cit_ratio_grd:.3f}  EITI: {cit_ratio_eiti:.3f}")
    print(f"  Deductible/total — GRD: {ded_ratio_grd:.3f}  EITI: {ded_ratio_eiti:.3f}")
    print(f"  Equity/total     — GRD: {eq_ratio_grd:.3f}   EITI: {eq_ratio_eiti:.3f}")
    print(f"  ({len(grd_cit_ratios)} GRD, {len(eiti_cit_ratios)} EITI countries with both)")

    # Add new columns if missing
    new_cols = [
        "actual_captured_cit_usd_imputed",
        "actual_captured_cit_imputed_flag",
        "actual_captured_deductible_usd_imputed",
        "actual_captured_deductible_imputed_flag",
        "actual_captured_equity_usd_imputed",
        "actual_captured_equity_imputed_flag",
        "imputation_method",
    ]
    for c in new_cols:
        if c not in cols:
            cols.append(c)

    n_imputed_cit = 0
    n_imputed_ded = 0
    n_imputed_eq = 0

    for r in rows:
        t = f(r.get("actual_captured_total_usd"))
        cit = f(r.get("actual_captured_cit_usd"))
        ded = f(r.get("actual_captured_deductible_usd"))
        eq  = f(r.get("actual_captured_equity_usd"))
        src = r.get("actual_captured_total_source", "")

        # Pick ratio source. For manual fills (source != GRD and != EITI), default to GRD ratios
        # since manual figures aim to be government-revenue-equivalent (closer to GRD scope).
        use_grd_ratio = (src == "GRD") or (src not in ("GRD", "EITI"))
        cit_ratio = cit_ratio_grd if use_grd_ratio else cit_ratio_eiti
        ded_ratio = ded_ratio_grd if use_grd_ratio else ded_ratio_eiti
        eq_ratio  = eq_ratio_grd  if use_grd_ratio else eq_ratio_eiti

        method = []
        # CIT imputation
        if cit > 0:
            r["actual_captured_cit_usd_imputed"] = f"{cit:.0f}"
            r["actual_captured_cit_imputed_flag"] = "FALSE"
        elif t > 0:
            imp = t * cit_ratio
            r["actual_captured_cit_usd_imputed"] = f"{imp:.0f}"
            r["actual_captured_cit_imputed_flag"] = "TRUE"
            n_imputed_cit += 1
            method.append(f"cit=ratio_{src}_{cit_ratio:.2f}")
        else:
            r["actual_captured_cit_usd_imputed"] = ""
            r["actual_captured_cit_imputed_flag"] = ""

        # Deductible imputation
        if ded > 0:
            r["actual_captured_deductible_usd_imputed"] = f"{ded:.0f}"
            r["actual_captured_deductible_imputed_flag"] = "FALSE"
        elif t > 0:
            imp = t * ded_ratio
            r["actual_captured_deductible_usd_imputed"] = f"{imp:.0f}"
            r["actual_captured_deductible_imputed_flag"] = "TRUE"
            n_imputed_ded += 1
            method.append(f"ded=ratio_{src}_{ded_ratio:.2f}")
        else:
            r["actual_captured_deductible_usd_imputed"] = ""
            r["actual_captured_deductible_imputed_flag"] = ""

        # Equity imputation (only meaningful for EITI-sourced or when SOE-rich pattern suspected)
        if eq > 0:
            r["actual_captured_equity_usd_imputed"] = f"{eq:.0f}"
            r["actual_captured_equity_imputed_flag"] = "FALSE"
        elif t > 0 and not use_grd_ratio:
            # Don't impute equity for GRD-source — GRD nontax already mixes equity in,
            # so a separate equity column for GRD-sourced countries is not meaningful.
            imp = t * eq_ratio
            r["actual_captured_equity_usd_imputed"] = f"{imp:.0f}"
            r["actual_captured_equity_imputed_flag"] = "TRUE"
            n_imputed_eq += 1
            method.append(f"eq=ratio_EITI_{eq_ratio:.2f}")
        else:
            r["actual_captured_equity_usd_imputed"] = ""
            r["actual_captured_equity_imputed_flag"] = ""

        r["imputation_method"] = ";".join(method)

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"\nImputed CIT for {n_imputed_cit} countries.")
    print(f"Imputed Deductible for {n_imputed_ded} countries.")
    print(f"Imputed Equity for {n_imputed_eq} countries.")
    print(f"Saved with new columns to: {path}")


if __name__ == "__main__":
    main()
