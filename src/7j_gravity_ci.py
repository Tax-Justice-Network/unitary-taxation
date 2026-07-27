# %%
"""
Attach gravity bootstrap standard errors to the headline country table.

`run_bootstrap.py` writes per-jurisdiction bootstrap statistics
(boot_mean / boot_se / 2.5–97.5% CI / n_draws) for the headline spec to
output/destination_sales/tables/gravity_bootstrap_SEs__<spec>.csv. This script
joins those onto the gravity baseline per-country net UT gain so the headline
deliverable carries uncertainty bands.

Output:
  output/three_scenarios/comparison/headline_country_with_ses.csv
  output/three_scenarios/comparison/headline_lic_with_ses.csv   (low-income only)

Usage: python 9e_attach_bootstrap_ses.py [SPEC]
  SPEC default: employees_payroll__etrdef_average__etrmax_inf__loss_cit_gain_etr
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
DEFAULT_SPEC = "employees_payroll__etrdef_average__etrmax_inf__loss_cit_gain_etr"
GRAVITY_BASELINE_TOPIC = "unitary_taxation_disaggregated"


def _read_csv_robust(path, **kw):
    path = str(path)
    try:
        return pd.read_csv(path, **kw)
    except (FileNotFoundError, OSError):
        dst = os.path.join(tempfile.gettempdir(), "se_" + os.path.basename(path))
        for cp in (r"C:\Program Files\Git\usr\bin\cp.exe", "cp"):
            try:
                subprocess.run([cp, path, dst], check=True)
                return pd.read_csv(dst, **kw)
            except Exception:
                continue
        raise


def main():
    spec = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SPEC
    formula = spec.split("__")[0]
    etr = spec.split("etrdef_")[1].split("__")[0]
    rate = spec.split("__")[-1]

    se_path = (Path(output_dirs("destination_sales")[0])
               / f"gravity_bootstrap_SEs__{spec}.csv")
    if not se_path.exists():
        raise SystemExit(
            f"No bootstrap SE file at {se_path}.\n"
            f"Run: python run_bootstrap.py  (BOOT_SPEC={spec})  first."
        )
    se = _read_csv_robust(se_path)

    long_p = output_dirs(GRAVITY_BASELINE_TOPIC)[0] / "summary_country_year_long.csv"
    df = _read_csv_robust(long_p, low_memory=False)
    df = df[
        (df["formula_name"] == formula)
        & (df["etr_name"] == etr)
        & (df["rate_mode"] == rate)
        & (df["year"].isin(YEARS))
    ]
    point = (
        df.groupby(["iso_partner", "partner_jurisdiction", "wb_income_group"],
                   as_index=False, dropna=False)["revenue_gain_from_ut"]
        .sum()
        .rename(columns={"revenue_gain_from_ut": "point_net_gain_musd"})
    )

    merged = point.merge(se, on="iso_partner", how="left")
    # Significance flag: CI excludes zero.
    merged["ci_excludes_zero"] = (
        (merged["ci_lo_2.5"] > 0) | (merged["ci_hi_97.5"] < 0)
    )
    merged = merged.sort_values("point_net_gain_musd")

    tables_dir, _ = output_dirs("three_scenarios/comparison")
    f1 = tables_dir / "headline_country_with_ses.csv"
    merged.to_csv(f1, index=False)
    print(f"  wrote {f1} ({len(merged)} countries, spec={spec})")

    lic = merged[merged["wb_income_group"] == "low_income"]
    f2 = tables_dir / "headline_lic_with_ses.csv"
    lic.to_csv(f2, index=False)
    print(f"  wrote {f2} ({len(lic)} low-income countries)")

    n_draws = int(se["n_draws"].max()) if "n_draws" in se.columns and len(se) else 0
    print(f"\n  Bootstrap draws available: {n_draws}")
    print(f"  Countries with SE attached: {merged['boot_se'].notna().sum()}/{len(merged)}")


if __name__ == "__main__":
    main()
