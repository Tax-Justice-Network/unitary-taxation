"""
Comprehensive sanity tests for the resource-extraction pipeline output.

Run after 3_resource_contribution.py + 4_carveout.py. Each test prints
PASS/FAIL with a short diagnostic. Tests are grouped by what they check:

  A. Schema and structural integrity
  B. Rent + captured-revenue invariants
  C. State-share routing & per-row allocation invariants
  D. Profit correction invariants
  E. African mineral producer coverage
  F. HQ shares
  G. Carve-out invariants

Reads:
  data/final/cbcr_main_with_extractives.csv
  data/final/cbcr_main_with_carveout.csv

Writes:
  output/extractive/tables/sanity_test_results.txt
"""

import sys
import warnings
from pathlib import Path

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Make src/ importable so we can use the output_dirs helper.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import output_dirs  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXTR = ROOT / "data/final/cbcr_main_with_extractives.csv"
CARV = ROOT / "data/final/cbcr_main_with_carveout.csv"
OUT_DIR, _ = output_dirs("extractive")
OUT_TXT = OUT_DIR / "sanity_test_results.txt"

results = []


def check(name, ok, detail=""):
    tag = "PASS" if ok else "FAIL"
    line = f"[{tag}] {name}\n        {detail}" if detail else f"[{tag}] {name}"
    print(line)
    results.append((name, ok, detail))


print("Loading datasets...")
df = pd.read_csv(EXTR, low_memory=False)
df_c = pd.read_csv(CARV, low_memory=False)
print(f"  extractives: {len(df):,} rows, {df.shape[1]} cols")
print(f"  carveout:    {len(df_c):,} rows, {df_c.shape[1]} cols\n")


# ─── A. Schema & structural integrity ─────────────────────────────────────
print("=== A. Schema & structural integrity ===")
required = [
    "iso_parent", "iso_partner", "year",
    "rent_total_usd", "captured_total_usd",
    "alloc_weight_ioc_usd", "alloc_weight_state_self_usd", "alloc_weight_usd",
    "state_share", "profit_extractive_corrected",
]
missing = [c for c in required if c not in df.columns]
check("A1: required columns present", not missing, f"missing: {missing}")

dups = df.duplicated(["year", "iso_parent", "iso_partner"]).sum()
check("A2: no duplicate (year, parent, partner) cells", dups == 0,
      f"{dups} duplicates found" if dups else "")


# ─── B. Rent + captured-revenue invariants ────────────────────────────────
print("\n=== B. Rent + captured invariants ===")

partner = df.groupby(["iso_partner", "year"]).agg(
    rent=("rent_total_usd", "first"),
    cap=("captured_total_usd", "first"),
    cap_cit=("captured_cit_usd", "first"),
).reset_index()
partner["cap_ex_cit"] = partner["cap"] - partner["cap_cit"].fillna(0.0)

# B1: all rents non-negative
neg_rent = (partner["rent"] < 0).sum()
check("B1: rents non-negative", neg_rent == 0,
      f"{neg_rent} rows with negative rent")

# B2: GBR is the only country allowed to have negative captured
neg_cap = partner[partner["cap"] < 0]
non_gbr_neg = neg_cap[neg_cap["iso_partner"] != "GBR"]
check("B2: only GBR has negative captured", len(non_gbr_neg) == 0,
      f"non-GBR negatives: {non_gbr_neg['iso_partner'].unique().tolist()}")

# B3: rent-scaling floor enforced — rent_total >= (captured_total - captured_cit).
# CIT is intentionally NOT part of the floor target (see §3d of script 3), so
# rent can legitimately sit below captured_total when there is resource CIT.
violations = partner[
    (partner["cap_ex_cit"] > 0)
    & (partner["rent"] > 0)
    & (partner["cap_ex_cit"] > partner["rent"] * 1.001)
]
check("B3: rent-scaling floor enforced (rent >= captured_total - captured_cit)", len(violations) == 0,
      f"{len(violations)} cells with (capture - CIT) > rent. Sample: "
      + str(violations.head(3)[['iso_partner','year','rent','cap_ex_cit']].to_dict('records')))


# ─── C. State-share routing & per-row allocation ──────────────────────────
print("\n=== C. State-share routing & per-row allocation ===")

# C1: state_share in [0, 1]
ss = df["state_share"].dropna()
out_of_range = ((ss < 0) | (ss > 1.0001)).sum()
check("C1: state_share in [0, 1]", out_of_range == 0,
      f"{out_of_range} rows out of range")

# C2: state_self_pool only non-zero on parent==partner rows
self_rows = df["iso_parent"] == df["iso_partner"]
non_self_with_self_pool = ((~self_rows) & (df["alloc_weight_state_self_usd"].fillna(0) > 0)).sum()
check("C2: state_self_pool zero on non-self rows",
      non_self_with_self_pool == 0,
      f"{non_self_with_self_pool} non-self rows have state_self_pool > 0")

# C3: alloc_weight_usd = ioc + state_self
diff = (df["alloc_weight_usd"]
        - df["alloc_weight_ioc_usd"].fillna(0)
        - df["alloc_weight_state_self_usd"].fillna(0)).abs()
big_diff = (diff > 1.0).sum()
check("C3: alloc_weight = ioc_pool + state_self_pool",
      big_diff == 0, f"{big_diff} rows with |diff| > $1")

# C4: alloc_weight_ioc_usd is non-negative
neg_ioc = (df["alloc_weight_ioc_usd"].fillna(0) < 0).sum()
check("C4: alloc_weight_ioc_usd non-negative", neg_ioc == 0,
      f"{neg_ioc} negative IOC pool rows")


# ─── D. Profit correction invariants ──────────────────────────────────────
print("\n=== D. Profit correction invariants ===")

# D1: profit_extractive_corrected >= profit_loss_before_income_tax_corrected on rows with positive add-back
diff_profit = (df["profit_extractive_corrected"]
               - df["profit_loss_before_income_tax_corrected"].fillna(0))
expected_addback = (df["captured_deductible_allocated_usd"].fillna(0)
                    + df["captured_equity_allocated_usd"].fillna(0))
profit_gap = (diff_profit - expected_addback).abs()
big_diffs = (profit_gap > 1.0).sum()
check("D1: profit_extractive_corrected = profit + deductible_alloc + equity_alloc",
      big_diffs == 0, f"{big_diffs} rows with |diff| > $1")

# D2: With ADD_BACK_EQUITY=False, equity_alloc should be 0
eq_alloc_sum = df["captured_equity_allocated_usd"].fillna(0).sum()
check("D2: ADD_BACK_EQUITY=False → equity_allocated == 0",
      abs(eq_alloc_sum) < 1.0, f"sum = ${eq_alloc_sum/1e9:.2f}B")


# ─── E. African mineral producer coverage ─────────────────────────────────
print("\n=== E. African mineral producer 2022 coverage ===")

afr_minerals = ["GIN", "COD", "MRT", "MLI", "BFA", "GHA", "TZA", "ZAF",
                "ZMB", "MOZ", "LBR", "SLE", "BWA", "MDG", "ETH", "NER", "SEN"]
for iso in afr_minerals:
    sub = partner[(partner["iso_partner"] == iso) & (partner["year"] == 2022)]
    if sub.empty:
        check(f"E.{iso}: 2022 record exists", False, "no row found")
        continue
    rent22 = float(sub["rent"].iloc[0]) if len(sub) else 0
    has_rent = rent22 > 1e6
    check(f"E.{iso}: 2022 has rent > $1M",
          has_rent, f"rent_total_usd = ${rent22/1e6:.1f}M")


# ─── F. HQ shares ─────────────────────────────────────────────────────────
print("\n=== F. HQ shares ===")

for cat in ("oil_gas", "coal", "minerals"):
    col = f"hq_share_{cat}"
    # Sum hq_share across DISTINCT parents per year. The Orbis HQ-share file
    # only assigns shares to extractive parents; non-extractive parents in
    # the CbCR universe get 0. The sum is therefore the share of global
    # extractive revenue covered by CbCR-reporting parents -- typically
    # 0.85-0.95, never expected to be exactly 1.0.
    by_year = df.drop_duplicates(["iso_parent", "year"])[
        ["year", col]
    ].groupby("year")[col].sum()
    out_of_range = ((by_year < 0.50) | (by_year > 1.05)).sum()
    check(f"F.{cat}: hq_share sums (CbCR coverage of global)",
          out_of_range == 0,
          f"yearly sums: {by_year.round(3).to_dict()}")


# ─── G. Carve-out invariants (variable royalty, 3 categories) ─────────────
print("\n=== G. Carve-out invariants ===")

# Rate ranges — must match the constants in src/4_carveout.py.
CAT_RANGES = {
    "cat1": (0.01, 0.10),  # Cat 1 — price-based
    "cat2": (0.01, 0.10),  # Cat 2 — margin-based on gross revenue
    "cat3": (0.01, 0.12),  # Cat 3 — margin-based on rent
}

# G1: per-category Cat 1 rate columns in [floor, cap]
floor1, cap1 = CAT_RANGES["cat1"]
for cat in ("oil_gas", "coal", "minerals"):
    col = f"cat1_rate_{cat}"
    if col in df_c.columns:
        rate = df_c[col].dropna()
        out_of_range = ((rate < floor1 - 1e-6) | (rate > cap1 + 1e-6)).sum()
        check(f"G1.{cat}: cat1_rate_{cat} in [{floor1:.0%}, {cap1:.0%}]",
              out_of_range == 0, f"{out_of_range} rows out of range")

# G2: cat2_rate and cat3_rate in their respective ranges
for variant in ("cat2", "cat3"):
    floor, cap = CAT_RANGES[variant]
    col = f"{variant}_rate"
    if col in df_c.columns:
        rate = df_c[col].dropna()
        out_of_range = ((rate < floor - 1e-6) | (rate > cap + 1e-6)).sum()
        check(f"G2.{variant}: {col} in [{floor:.0%}, {cap:.0%}]",
              out_of_range == 0, f"{out_of_range} rows out of range")

# G3: per-category per-variant royalty USD identities
#     cat1: gross_revenue × hq × (1-state) × cat1_rate
#     cat2: gross_revenue × hq × (1-state) × cat2_rate
#     cat3: rent          × hq × (1-state) × cat3_rate
state_factor = 1.0 - df_c["state_share"].fillna(0)
for cat in ("oil_gas", "coal", "minerals"):
    hq_col = f"hq_share_{cat}"
    gross_col = f"gross_revenue_{cat}_usd"
    rent_col = f"rent_{cat}_usd"
    if hq_col not in df_c.columns:
        continue
    # cat1
    royalty_col = f"expected_royalty_cat1_{cat}_usd"
    rate_col = f"cat1_rate_{cat}"
    if royalty_col in df_c.columns and gross_col in df_c.columns:
        expected = (
            df_c[gross_col].fillna(0) * df_c[hq_col].fillna(0)
            * state_factor * df_c[rate_col].fillna(0)
        )
        max_err = float((df_c[royalty_col].fillna(0) - expected).abs().max())
        check(f"G3.cat1.{cat}: matches gross × hq × (1-state) × cat1_rate",
              max_err < 1e-3, f"max abs diff: ${max_err:.6f}")
    # cat2
    royalty_col = f"expected_royalty_cat2_{cat}_usd"
    if royalty_col in df_c.columns and gross_col in df_c.columns:
        expected = (
            df_c[gross_col].fillna(0) * df_c[hq_col].fillna(0)
            * state_factor * df_c["cat2_rate"].fillna(0)
        )
        max_err = float((df_c[royalty_col].fillna(0) - expected).abs().max())
        check(f"G3.cat2.{cat}: matches gross × hq × (1-state) × cat2_rate",
              max_err < 1e-3, f"max abs diff: ${max_err:.6f}")
    # cat3
    royalty_col = f"expected_royalty_cat3_{cat}_usd"
    if royalty_col in df_c.columns and rent_col in df_c.columns:
        expected = (
            df_c[rent_col].fillna(0) * df_c[hq_col].fillna(0)
            * state_factor * df_c["cat3_rate"].fillna(0)
        )
        max_err = float((df_c[royalty_col].fillna(0) - expected).abs().max())
        check(f"G3.cat3.{cat}: matches rent × hq × (1-state) × cat3_rate",
              max_err < 1e-3, f"max abs diff: ${max_err:.6f}")

# G4: per-variant total = sum of per-category royalties
for variant in ("cat1", "cat2", "cat3"):
    total_col = f"expected_royalty_{variant}_usd"
    if total_col not in df_c.columns:
        continue
    total_check = sum(
        df_c[f"expected_royalty_{variant}_{c}_usd"].fillna(0)
        for c in ("oil_gas", "coal", "minerals")
        if f"expected_royalty_{variant}_{c}_usd" in df_c.columns
    )
    max_err = float((df_c[total_col].fillna(0) - total_check).abs().max())
    check(f"G4.{variant}: {total_col} = sum of per-category royalties",
          max_err < 1e-3, f"max abs diff: ${max_err:.6f}")


# ─── Summary ───────────────────────────────────────────────────────────────
print("\n=== Summary ===")
n_pass = sum(1 for _, ok, _ in results if ok)
n_fail = sum(1 for _, ok, _ in results if not ok)
print(f"  {n_pass} PASS, {n_fail} FAIL")

with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(f"Resource extraction sanity tests ({n_pass} PASS, {n_fail} FAIL)\n")
    f.write("=" * 70 + "\n\n")
    for name, ok, detail in results:
        tag = "PASS" if ok else "FAIL"
        f.write(f"[{tag}] {name}\n")
        if detail:
            f.write(f"        {detail}\n")
        f.write("\n")
print(f"\nWritten: {OUT_TXT}")
