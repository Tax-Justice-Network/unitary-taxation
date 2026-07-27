"""
Compute implied local profit from captured CIT and effective resource-CIT rate.

implied_profit_local_usd = captured_cit_usd / combined_effective_rate

Two uses:
1. Sanity check against Orbis subsidiary profit_before_tax in the same jurisdiction.
   Large divergence flags either profit shifting or Orbis under-coverage.
2. Fallback for the local-profit waterfall when Orbis is thin (Task 10).

Reads:
- data/final/extractive_royalty_dataset.csv (must have actual_captured_cit_usd_imputed)
- data/final/effective_resource_cit_rates.csv (manual rate lookup)

Writes back to extractive_royalty_dataset.csv:
- effective_resource_cit_rate
- implied_profit_local_usd
- implied_profit_source  (rate_lookup_iso3 / DEFAULT_general / DEFAULT_oil_ringfence)
"""

import csv
from _paths import FINAL


def f(s):
    try: return float(s) if s else 0.0
    except: return 0.0


def main():
    dataset_path = FINAL / "extractive_royalty_dataset.csv"
    rates_path = FINAL / "effective_resource_cit_rates.csv"

    # Load rates
    rates = {}
    default_general = 0.27
    default_oil = 0.50
    with open(rates_path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            iso = row["iso3"].strip()
            if iso.startswith("#") or not iso:
                continue
            try:
                rate = float(row["combined_effective_rate"])
            except:
                continue
            if iso == "DEFAULT_general":
                default_general = rate
            elif iso.startswith("PNG_DEFAULT") or "DEFAULT_oil" in iso:
                default_oil = rate
            else:
                rates[iso] = (rate, row.get("regime_type", "general"))

    print(f"Loaded {len(rates)} country-specific effective rates.")
    print(f"Defaults: general={default_general}, oil_ringfence={default_oil}")

    # Heuristic: which countries should default to oil_ringfence vs general?
    # Use WB rents composition: if oil+gas > 60% of total rents, oil regime applies.
    OIL_DOMINATED_FALLBACK = set()  # populated below

    with open(dataset_path, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = list(reader.fieldnames)
        rows = list(reader)

    # Pre-pass: classify oil-dominated for default selection
    for r in rows:
        oil = f(r.get("wb_oil_rents_usd")) + f(r.get("wb_gas_rents_usd"))
        total = f(r.get("wb_total_rents_usd"))
        if total > 0 and oil / total > 0.6:
            OIL_DOMINATED_FALLBACK.add(r["iso3"])

    new_cols = [
        "effective_resource_cit_rate",
        "effective_rate_source",
        "implied_profit_local_usd",
    ]
    for c in new_cols:
        if c not in cols:
            cols.append(c)

    n_with_lookup = 0
    n_default_oil = 0
    n_default_gen = 0

    for r in rows:
        iso = r["iso3"]
        if iso in rates:
            rate, regime = rates[iso]
            r["effective_resource_cit_rate"] = f"{rate:.3f}"
            r["effective_rate_source"] = f"lookup_{regime}"
            n_with_lookup += 1
        elif iso in OIL_DOMINATED_FALLBACK:
            r["effective_resource_cit_rate"] = f"{default_oil:.3f}"
            r["effective_rate_source"] = "default_oil_ringfence"
            n_default_oil += 1
        else:
            r["effective_resource_cit_rate"] = f"{default_general:.3f}"
            r["effective_rate_source"] = "default_general"
            n_default_gen += 1

        cit = f(r.get("actual_captured_cit_usd_imputed"))
        rate_val = f(r["effective_resource_cit_rate"])
        if cit > 0 and rate_val > 0:
            r["implied_profit_local_usd"] = f"{cit / rate_val:.0f}"
        else:
            r["implied_profit_local_usd"] = ""

    with open(dataset_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"\nApplied rates: {n_with_lookup} from lookup, {n_default_oil} default-oil, {n_default_gen} default-general")
    n_implied = sum(1 for r in rows if r.get("implied_profit_local_usd"))
    print(f"Implied profit computed for {n_implied} countries.")

    # Show top
    rows_with_implied = sorted(
        ((r["country_name"], r["iso3"], f(r["implied_profit_local_usd"]), f(r["actual_captured_cit_usd_imputed"]), float(r["effective_resource_cit_rate"]))
         for r in rows if r.get("implied_profit_local_usd")),
        key=lambda x: -x[2]
    )
    print(f"\nTop 15 by implied local profit:")
    print(f"{'iso':<4} {'country':<25} {'cit $bn':>10} {'rate':>6} {'implied $bn':>12}")
    for n, i, p, c, rt in rows_with_implied[:15]:
        flag = "*" if "imputed" in str(rows[next(idx for idx,row in enumerate(rows) if row['iso3']==i)].get("imputation_method","")) else " "
        print(f"{i:<4} {n:<25} {c/1e9:>9.1f}{flag} {rt:>6.2f} {p/1e9:>11.1f}")
    print("(* = CIT was imputed, not measured)")


if __name__ == "__main__":
    main()
