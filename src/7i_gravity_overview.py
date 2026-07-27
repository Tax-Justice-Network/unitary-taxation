# %%
"""
All-formula × all-ETR × all-rate-mode overview for the GRAVITY-imputed sample.

The grid table the user asked for ("all estimates for the gravity sample,
including resource exemptions, the resource floor and origin vs destination
sales"), in one consolidated CSV + a printed headline view.

For every (scenario × formula × etr_name × rate_mode) available in the gravity
UT outputs it reports:
  net_gain_musd        Σ revenue_gain_from_ut over all jurisdictions, 2016–2022
  lic_gain_musd        same, restricted to low_income jurisdictions
  n_lic_losers         # low_income jurisdictions with net loss
  drc_musd             DR Congo's net gain (a watched extractive case)
  is_destination       True if the formula uses the destination sales key
  is_nexus             True if the destination key is nexus-down-weighted

Scenarios: the three main gravity-imputed full-sample routes —
  baseline  (unitary_taxation_disaggregated)
  excl      (unitary_taxation_excl_resource)
  floored   (unitary_taxation_excl_resource_floored)

Output: output/three_scenarios/comparison/gravity_full_overview.csv

Usage: python 9d_gravity_overview.py
"""

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

YEARS = list(range(2016, 2023))

SCENARIOS = [
    ("baseline", "unitary_taxation_disaggregated"),
    ("excl", "unitary_taxation_excl_resource"),
    ("floored", "unitary_taxation_excl_resource_floored"),
]


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

    # Headline print: default ETR (average) + default rate (loss_cit_gain_etr).
    hl = ov[(ov["etr_name"] == "average") & (ov["rate_mode"] == "loss_cit_gain_etr")]
    print("\nHeadline (avg ETR, loss_cit_gain_etr), net / LIC / #LIC-losers / DRC (musd):")
    print(f"  {'scenario':10s} {'formula':40s} {'net':>10s} {'LIC':>8s} "
          f"{'losers':>6s} {'DRC':>8s}")
    for _, r in hl.iterrows():
        print(f"  {r['scenario']:10s} {r['formula_name'][:40]:40s} "
              f"{r['net_gain_musd']:>10.0f} {r['lic_gain_musd']:>8.0f} "
              f"{int(r['n_lic_losers']):>6d} {r['drc_musd']:>8.0f}")


if __name__ == "__main__":
    main()
