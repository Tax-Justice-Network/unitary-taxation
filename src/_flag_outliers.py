"""
Flag countries with > 20% (absolute) change in total government revenue under
any (scenario, formula) combination, then investigate the drivers.

Reads:  output/five_scenarios/tables/fivescenario_summary_long_<window>.csv
        data/final/cbcr_main_disaggregated.csv      (for is_distributed / weight_source diagnostics)

Usage:  python _flag_outliers.py 2021_22
        python _flag_outliers.py 2016_22
"""
import sys
from pathlib import Path
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import output_dirs, data_final

WINDOW = sys.argv[1] if len(sys.argv) > 1 else "2021_22"
YEARS = {
    "2021_22": [2021, 2022],
    "2020_22": [2020, 2021, 2022],
    "2016_22": list(range(2016, 2023)),
    "2016_21": list(range(2016, 2022)),
}.get(WINDOW, [2021, 2022])
THRESHOLD_PCT = 20.0

tables_dir, _ = output_dirs("five_scenarios")
long_csv = tables_dir / f"fivescenario_summary_long_{WINDOW}.csv"
df = pd.read_csv(long_csv)

# Diagnostics from the disaggregated baseline (per-partner imputed-share metadata)
diag = pd.read_csv(
    Path(data_final) / "cbcr_main_disaggregated.csv",
    usecols=[
        "iso_partner", "year", "is_distributed",
        "n_reporters_for_partner_weight", "weight_source_for_partner",
        "profit_loss_before_income_tax_corrected",
    ],
    low_memory=False,
)
diag = diag[diag["year"].isin(YEARS)]
per_partner_diag = (
    diag.groupby("iso_partner", as_index=False)
        .agg(
            n_distributed_rows=("is_distributed", "sum"),
            n_total_rows=("is_distributed", "size"),
            n_reporters_median=("n_reporters_for_partner_weight", "max"),
            weight_source=("weight_source_for_partner",
                           lambda s: s.dropna().iloc[0] if s.dropna().size else "n/a"),
        )
)
per_partner_diag["pct_imputed"] = (
    100 * per_partner_diag["n_distributed_rows"] / per_partner_diag["n_total_rows"]
)

# Flag rows where the headline pct is large (either sign)
df["abs_pct"] = df["delta_total_gvt_revenue_recCIT_forgETR_pct_revenue"].abs()
flagged = df[df["abs_pct"] > THRESHOLD_PCT].copy()
flagged = flagged.merge(per_partner_diag, on="iso_partner", how="left")

# Order by scenario, formula, abs_pct desc
flagged = flagged.sort_values(["scenario", "formula_name", "abs_pct"], ascending=[True, True, False])

cols_out = [
    "scenario", "formula_name", "iso_partner", "partner_jurisdiction", "wb_income_group",
    "delta_total_gvt_revenue_recCIT_forgETR_musd", "delta_total_gvt_revenue_recCIT_forgETR_pct_revenue",
    "delta_total_gvt_revenue_recETR_forgETR_pct_revenue",
    "delta_taxable_profits_musd", "delta_taxable_profits_pct",
    "resource_capture_actual_musd",
    "tax_revenue_current_usd",
    "n_reporters_median", "weight_source", "pct_imputed",
]
out = flagged[cols_out].copy()
out_path = tables_dir / f"flagged_outliers_{WINDOW}.csv"
out.to_csv(out_path, index=False)
print(f"Wrote {out_path} ({len(out):,} rows)")

# Summary by scenario
print(f"\nFlagged rows by scenario (|pct| > {THRESHOLD_PCT}%):")
print(out.groupby("scenario").size().to_string())

# Top 20 with explanations
print(f"\nTop 20 flagged country-scenario-formula cells (by |pct|):")
for _, r in out.head(20).iterrows():
    tags = []
    if r["weight_source"] == "sum_share":
        tags.append("sum-share fallback (<3 reporters)")
    if r["pct_imputed"] > 80:
        tags.append(f"mostly imputed ({r['pct_imputed']:.0f}%)")
    elif r["pct_imputed"] > 40:
        tags.append(f"partly imputed ({r['pct_imputed']:.0f}%)")
    if pd.notna(r["tax_revenue_current_usd"]) and r["tax_revenue_current_usd"] < 5e9:
        tags.append(f"small tax-rev denom (${r['tax_revenue_current_usd']/1e9:.1f}B)")
    if r["scenario"] == "five_factor" and r["resource_capture_actual_musd"] > 0:
        rc_pct = 100 * r["resource_capture_actual_musd"] * 1e6 / (r["tax_revenue_current_usd"] or 1)
        if abs(rc_pct) > 10:
            tags.append(f"resource-capture substitution ({rc_pct:+.0f}% of revenue)")
    if abs(r["delta_taxable_profits_pct"] or 0) > 100:
        tags.append(f"huge profit delta ({r['delta_taxable_profits_pct']:+.0f}%)")
    explanation = "; ".join(tags) or "—"
    print(f"  {r['iso_partner']:<5} {(r['partner_jurisdiction'] or '')[:22]:<22} "
          f"{r['scenario']:<14} {r['formula_name'][:30]:<30} "
          f"pct {r['delta_total_gvt_revenue_recCIT_forgETR_pct_revenue']:+7.1f}% "
          f"(Δrev ${r['delta_total_gvt_revenue_recCIT_forgETR_musd']:>10,.0f} M)  | {explanation}")
