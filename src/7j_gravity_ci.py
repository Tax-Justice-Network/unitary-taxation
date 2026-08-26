# %%
"""
7j — Gravity confidence intervals (Appendix C).

Joins the per-jurisdiction bootstrap statistics from run_bootstrap.py
(mean / standard error / 2.5–97.5% confidence interval / draw count) onto the
gravity per-country net revenue gain, then (1) writes a per-country table grouped
by income group with the point estimate, SE, CI and a significance flag, and
(2) draws a horizontal error-bar figure of the largest-magnitude countries'
point estimates with their 2.5–97.5% CIs.

Uncertainty here is IMPUTATION uncertainty only (resampling the gravity model's
training cells). The bootstrap on disk is for the employees+payroll / average-ETR
spec; the headline destination spec needs its own (expensive) bootstrap run —
until then this exhibit is labelled with the spec it actually uses. Optional:
runs only if the bootstrap draws exist.

Exhibit script — consumes the script-6 estimation summaries. Produces the
Appendix C bootstrap-CI table (tableC_gravity_confidence_intervals) + CI figure
(figC_gravity_confidence_intervals) for the gravity-imputed sample.

Reads:
  output/checks/…/bootstrap statistics (run_bootstrap.py)              — per-jurisdiction mean/SE/CI/draw count
  output/estimates/with_imputed_rows/*/tables/…/country_estimates__*.csv — gravity per-country net revenue gain (script 5/6)

Writes:
  output/paper/appendix/tableC_gravity_confidence_intervals.csv/.tex   — Appendix C CI table
  output/paper/appendix/figC_gravity_confidence_intervals.png/.pdf     — Appendix C CI figure
  output/analysis/origin_vs_destination/with_imputed_rows/tables/…     — supporting CI tables

Usage:
  python 7j_gravity_ci.py [SPEC]     — SPEC optional (default employees_payroll__etrdef_average__etrmax_inf__loss_cit_gain_etr)

Author: Alison Schultz.
Last updated: 2026-07-25.
"""

# %% MARK: 1. Setup
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    pass

import config
from config import output_dirs
from _brand import apply_tjn_style, POSITIVE, NEGATIVE
import _exhibit_helpers as _eh
from _latex_table import csv_to_latex

apply_tjn_style()

# %% MARK: 2. Config and constants
YEARS = list(range(2016, 2023))
AVG_YEARS = [2016, 2017, 2018, 2019, 2021, 2022]   # paper window: 2020 excluded
DEFAULT_SPEC = "employees_payroll__etrdef_average__etrmax_inf__loss_cit_gain_etr"
# The bootstrap runs on the HEADLINE dataset (excl_resource, gravity sample), so
# the point estimate must come from the same topic — reading the uncorrected
# `disaggregated` topic put the point outside its own bootstrap CI.
GRAVITY_BASELINE_TOPIC = "unitary_taxation_excl_resource"
_SPEC_LABEL = {"employees_payroll": "employees + payroll", "average": "average ETR",
               "sales_employees_destmnedds": "employees + destination sales",
               "domfor": "domestic/foreign ETR"}


# %% MARK: 3. Loaders and helpers
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


def _spec_note(spec):
    formula = spec.split("__")[0]
    etr = spec.split("etrdef_")[1].split("__")[0]
    return (f"Imputation uncertainty from the gravity bootstrap on the "
            f"{_SPEC_LABEL.get(formula, formula)} / {_SPEC_LABEL.get(etr, etr)} "
            f"specification.")


# %% MARK: 4. CI table and figure
def _ci_table(merged, spec):
    """Per-country Appendix-C table (grouped by income group) with the point
    estimate, SE and 2.5–97.5% CI, in constant-year USD bn/yr."""
    df = merged.set_index("iso_partner")
    d = pd.DataFrame(index=df.index)
    d["net gain (USD bn/yr)"] = df["point_net_gain_musd"] / 1e3
    d["std. error (USD bn)"] = df["boot_se"] / 1e3
    d["CI 2.5% (USD bn)"] = df["ci_lo_2.5"] / 1e3
    d["CI 97.5% (USD bn)"] = df["ci_hi_97.5"] / 1e3
    d["distinguishable from zero"] = df["ci_excludes_zero"].astype(bool).astype(int)
    grpmap = df["wb_income_group"].to_dict()
    order_iso = pd.Index(sorted(d.index, key=lambda i: _eh.cname(i).lower()))
    out = _eh.finalise(d, order_iso, grpmap)
    # Group-heading rows: keep only the (additive) net-gain sum — summed standard
    # errors, quantile bounds and 0/1 flags are not meaningful aggregates.
    is_grp = out.iloc[:, 0].astype(str).str.strip().str.isupper()
    for col in ("std. error (USD bn)", "CI 2.5% (USD bn)",
                "CI 97.5% (USD bn)", "distinguishable from zero"):
        out.loc[is_grp, col] = np.nan
    td = _eh.tabledir("gravity")
    csv = os.path.join(td, "tableC_gravity_confidence_intervals__gravity.csv")
    out.to_csv(csv, index=False)
    csv_to_latex(csv, caption="Gravity-sample net revenue gain with bootstrap "
                 "confidence intervals (Appendix C)")
    print(f"  wrote {csv} ({len(out)} rows incl. group headings)")


def _ci_figure(merged, spec):
    """Horizontal error bars: the 25 largest-magnitude countries' point net gain
    with their 2.5–97.5% bootstrap CI (green = gain, red = loss)."""
    m = merged.dropna(subset=["boot_se"]).copy()
    if m.empty:
        print("  [skip CI figure] no countries with SEs")
        return
    m["absv"] = m["point_net_gain_musd"].abs()
    top = m.nlargest(25, "absv").sort_values("point_net_gain_musd")
    y = np.arange(len(top))
    pt = top["point_net_gain_musd"].to_numpy() / 1e3
    lo = top["ci_lo_2.5"].to_numpy() / 1e3
    hi = top["ci_hi_97.5"].to_numpy() / 1e3
    err = np.abs(np.vstack([pt - lo, hi - pt]))
    colours = [POSITIVE if v >= 0 else NEGATIVE for v in pt]
    fig, ax = plt.subplots(figsize=(9, 9))
    ax.errorbar(pt, y, xerr=err, fmt="none", ecolor="#9A9A9A", elinewidth=1.2,
                capsize=2.5, zorder=1)
    ax.scatter(pt, y, c=colours, s=34, zorder=2, edgecolor="white", linewidth=0.5)
    ax.axvline(0, color="grey", linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels([_eh.cname(i) for i in top["iso_partner"]], fontsize=8)
    ax.set_xlabel("Change in tax revenue (USD bn per year), gravity sample")
    ax.margins(y=0.01)
    fig.tight_layout()
    fd = _eh.figdir("gravity")
    plt.savefig(fd / "figC_gravity_confidence_intervals.png", dpi=130)
    plt.close()
    print(f"  wrote {fd / 'figC_gravity_confidence_intervals.png'}")


# %% MARK: 5. Main and run
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
            f"Run: python gravity/run_bootstrap.py  (BOOT_SPEC={spec})  first."
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
    # Point estimate on the PAPER basis: deflated yearly average, 2020 excluded.
    defl = config.deflator_to_base()
    df["_v25"] = df["revenue_gain_from_ut"] * df["year"].map(defl)
    point = (
        df.groupby(["iso_partner", "partner_jurisdiction", "wb_income_group"],
                   as_index=False, dropna=False)
        .agg(point_net_gain_musd=("_v25", lambda s: s[df.loc[s.index, "year"]
                                                      .isin(AVG_YEARS)].sum() / len(AVG_YEARS)),
             point_sum_nominal=("revenue_gain_from_ut", "sum"))
    )

    merged = point.merge(se, on="iso_partner", how="left")
    # The bootstrap draws are NOMINAL SUMS over all years (2016–2022 incl 2020,
    # collapsed at capture). Rescale SE/CI to the paper basis with the per-country
    # factor point_avg/point_sum from the same summary (global median fallback
    # where the nominal sum is tiny or sign-flipping).
    f = merged["point_net_gain_musd"] / merged["point_sum_nominal"]
    f_glob = f[(merged["point_sum_nominal"].abs() > 50) & (f > 0)].median()
    f = f.where((merged["point_sum_nominal"].abs() > 50) & (f > 0), f_glob)
    for c in ("boot_se", "ci_lo_2.5", "ci_hi_97.5"):
        merged[c] = merged[c] * f
    merged["ci_excludes_zero"] = (
        (merged["ci_lo_2.5"] > 0) | (merged["ci_hi_97.5"] < 0)
    )
    merged = merged.sort_values("point_net_gain_musd")

    # Analysis CSVs (kept for inspection).
    tables_dir, _ = output_dirs("three_scenarios/comparison")
    merged.to_csv(tables_dir / "headline_country_with_ses.csv", index=False)
    lic = merged[merged["wb_income_group"] == "low_income"]
    lic.to_csv(tables_dir / "headline_lic_with_ses.csv", index=False)

    # Appendix-C deliverables.
    print(f"  {_spec_note(spec)}")
    _ci_table(merged, spec)
    _ci_figure(merged, spec)

    n_draws = int(se["n_draws"].max()) if "n_draws" in se.columns and len(se) else 0
    print(f"  bootstrap draws: {n_draws}; "
          f"countries with SE: {merged['boot_se'].notna().sum()}/{len(merged)}")


if __name__ == "__main__":
    main()
