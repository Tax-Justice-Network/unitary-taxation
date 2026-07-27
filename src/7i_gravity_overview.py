# %%
"""
7i — Gravity-sample overview grid.

For every (scenario × formula × ETR × rate-mode) available in the gravity
estimation outputs, reports the net revenue gain, the low-income gain, the count
of low-income losers and DR Congo's net gain, in one CSV plus a printed headline
view. A quick way to see how the gravity-sample results move across the whole
specification grid (supporting analysis, not a numbered exhibit).

Exhibit script — consumes the script-6 estimation summaries. Produces the
consolidated Appendix C gravity-sample overview grid across the full spec grid.

Reads:
  output/estimates/with_imputed_rows/*/tables/…/country_estimates__*.csv — every gravity-sample spec (script 5/6)

Writes:
  output/analysis/origin_vs_destination/with_imputed_rows/gravity_full_overview.csv — one row per (scenario × formula × ETR × rate-mode)

Usage:
  python 7i_gravity_overview.py

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

from config import output_dirs

# %% MARK: 2. Config and constants
YEARS = list(range(2016, 2023))

SCENARIOS = [
    ("baseline", "unitary_taxation_disaggregated"),
    ("excl", "unitary_taxation_excl_resource"),
    ("floored", "unitary_taxation_excl_resource_floored"),
]


# %% MARK: 3. Overview builder
def _read_csv_robust(path, **kw):
    path = str(path)
    try:
        return pd.read_csv(path, **kw)
    except (FileNotFoundError, OSError):
        dst = os.path.join(tempfile.gettempdir(), "ov_" + os.path.basename(path))
        for cp in (r"C:\Program Files\Git\usr\bin\cp.exe", "cp"):
            try:
                subprocess.run([cp, path, dst], check=True)
                return pd.read_csv(dst, **kw)
            except Exception:
                continue
        raise


def overview_rows(key, topic):
    tables_dir, _ = output_dirs(topic)
    p = tables_dir / "summary_country_year_long.csv"
    if not p.exists():
        print(f"  [skip] {key}: no long table")
        return pd.DataFrame()
    df = _read_csv_robust(p, low_memory=False)
    df = df[df["year"].isin(YEARS)]
    # Per-country net gain per spec.
    per_country = (
        df.groupby(["formula_name", "etr_name", "rate_mode",
                    "iso_partner", "wb_income_group"],
                   as_index=False, dropna=False)["revenue_gain_from_ut"].sum()
    )
    lic = per_country["wb_income_group"] == "low_income"

    def agg(g):
        return pd.Series({
            "net_gain_musd": g["revenue_gain_from_ut"].sum(),
            "lic_gain_musd": g.loc[g["wb_income_group"] == "low_income",
                                   "revenue_gain_from_ut"].sum(),
            "n_lic_losers": int((g.loc[g["wb_income_group"] == "low_income",
                                       "revenue_gain_from_ut"] < 0).sum()),
            "drc_musd": g.loc[g["iso_partner"] == "COD",
                              "revenue_gain_from_ut"].sum(),
        })

    out = (per_country.groupby(["formula_name", "etr_name", "rate_mode"])
           .apply(agg, include_groups=False).reset_index())
    out.insert(0, "scenario", key)
    out["is_destination"] = out["formula_name"].str.contains("dest")
    out["is_nexus"] = out["formula_name"].str.endswith("_nexus")
    return out


# %% MARK: 4. Main and run
def main():
    _, _ = output_dirs("three_scenarios/comparison")  # ensure dirs exist
    tables_dir, _ = output_dirs("three_scenarios/comparison")
    print("Building gravity full overview (all formula × etr × rate)…")
    parts = [overview_rows(k, t) for k, t in SCENARIOS]
    parts = [p for p in parts if not p.empty]
    if not parts:
        raise SystemExit("No gravity long tables found — run scripts 5+6 first.")
    ov = pd.concat(parts, ignore_index=True)
    ov = ov.sort_values(["scenario", "formula_name", "etr_name", "rate_mode"])
    f = tables_dir / "gravity_full_overview.csv"
    ov.to_csv(f, index=False)
    print(f"  wrote {f} ({len(ov)} spec rows)")

    # Overview print: average-ETR family + loss_cit_gain_etr (a robustness view,
    # not the domfor headline).
    hl = ov[(ov["etr_name"] == "average") & (ov["rate_mode"] == "loss_cit_gain_etr")]
    print("\nOverview (average-ETR family, loss_cit_gain_etr), net / LIC / #LIC-losers / DRC (musd):")
    print(f"  {'scenario':10s} {'formula':40s} {'net':>10s} {'LIC':>8s} "
          f"{'losers':>6s} {'DRC':>8s}")
    for _, r in hl.iterrows():
        print(f"  {r['scenario']:10s} {r['formula_name'][:40]:40s} "
              f"{r['net_gain_musd']:>10.0f} {r['lic_gain_musd']:>8.0f} "
              f"{int(r['n_lic_losers']):>6d} {r['drc_musd']:>8.0f}")


if __name__ == "__main__":
    main()
