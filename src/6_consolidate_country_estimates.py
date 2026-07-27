"""
6 — Consolidate country-level estimation results into per-scenario summaries.

Concatenates the per-specification country estimates written by script 5 into
one long summary per scenario — plus a compact per-country totals-by-spec file.
The stale-spec gate keeps only files listed in the topic's current
run_summary.csv. This is the pipeline's final DATA stage; it deliberately writes
NO figures and NO rankings, because every ranking / income-group / winners-losers
exhibit is produced downstream as a paper deliverable by the 7-series scripts.
A quick winners/losers ranking is built in memory only, to print a stdout sanity
check (dropping the config DATA_QUALITY_EXCLUSIONS).

Pipeline step 6 — after 5 (estimation); final consolidation, feeds the 7-series exhibits.

Reads (per topic; <topic> remapped by config.output_dirs into
output/estimates/{reported_only,with_imputed_rows}/<scenario folder>/):
  output/<topic>/tables/<sample>/country_estimates__*.csv     — per-spec country estimates (script 5)
  output/<topic>/tables/<sample>/run_summary.csv              — current run's specs (gates which files are concatenated)

Writes (two DATA files only — both keep every country):
  output/<topic>/tables/summary_country_year_long.csv         — all (iso_partner, year, spec) rows concatenated; the file every 7-series script reads
  output/<topic>/tables/summary_country_totals_by_spec.csv    — Σ over years per (country, spec): net UT gain ($M)

Usage:
  python 6_consolidate_country_estimates.py                                 — all default topics
  python 6_consolidate_country_estimates.py unitary_taxation_excl_resource  — just that one topic

Author: Alison Schultz.
Last updated: 2026-07-25.
"""
# %% MARK: 1. Setup (imports, technical path helper)
import os
import sys
import re
from pathlib import Path
import numpy as np
import pandas as pd


def _longpath(p):
    """On Windows, prefix paths > 240 chars with \\\\?\\ so open() bypasses
    the 260-char MAX_PATH limit. The OneDrive + Arabic-character project root
    pushes some country_estimates filenames over the limit."""
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import output_dirs, DATA_QUALITY_EXCLUSIONS

# Topics to analyse (each = the output_topic configured in script 5's
# DATASET_CONFIGS). The user can override on the command line.
# %% MARK: 2. Run settings (topics, headline spec, ranking sizes)
# One topic per dataset × sample; the reported-only ("_reported") variants are
# the paper's headline sample.
_BASE_TOPICS = [
    "unitary_taxation_disaggregated",
    "unitary_taxation_excl_resource",
    "unitary_taxation_excl_resource_floored",
    "unitary_taxation_excl_resource_floored_allrowsalloc",
    "unitary_taxation_incl_resource",
]
DEFAULT_TOPICS = [t + s for t in _BASE_TOPICS for s in ("_reported", "")]

# CbCR data-quality outliers (LSO/FSM/GUF/BTN) are defined ONCE in
# config.py (DATA_QUALITY_EXCLUSIONS, imported above) and applied to the
# ranking / sensitivity / income-group PRESENTATION outputs below — the
# per-country data files (summary_country_year_long, summary_country_totals_
# by_spec) keep all countries for inspection / QA.

# The number of countries listed in the stdout winners/losers sanity check.
TOP_N = 25


# %% MARK: 3. Technical helpers (file listing, spec parsing)
def _country_files(tables_dir):
    """Return all country_estimates_*.csv files under a topic's tables folder.

    Script 5 puts them in a per-sample subfolder; with one sample per run,
    that subfolder takes the RUN_DATASET name. We glob across all subfolders
    so the script doesn't have to know it."""
    files = list(tables_dir.glob("**/country_estimates__*.csv"))
    return files


def _parse_spec_from_filename(path):
    """The filename encodes the spec:
        country_estimates__{formula}__etrdef_{etr_name}__etrmax_{...}__{rate_mode}.csv
    """
    name = path.stem
    m = re.match(
        r"country_estimates__(?P<formula>.+?)__etrdef_(?P<etr>.+?)__etrmax_(?P<thr>.+?)__(?P<rate>.+)$",
        name,
    )
    if not m:
        return None
    return m.groupdict()


# %% MARK: 4. Spec-file gate (method)
# The protection against script 5's append-only output folders: only files
# accounted for in the current run_summary are concatenated, and extras are
# admitted only when they cannot double-count an admitted spec.
def load_country_long(tables_dir, allowed_names=None):
    """Concatenate per-spec country files into one long frame.

    `allowed_names` (the basenames listed in the current run_summary.csv's
    `country_file` column) gates which files are read: script 5's output
    folders are append-only, so without this gate a stale file from a retired
    spec or an old ETR-threshold run would be silently concatenated — and a
    same-spec duplicate double-counted — into every downstream summary."""
    files = _country_files(tables_dir)
    if not files:
        print(f"  [WARN] no country_estimates files under {tables_dir}")
        return pd.DataFrame()

    if allowed_names is not None:
        in_rs = [fp for fp in files if fp.name in allowed_names]
        extras = sorted(
            (fp for fp in files if fp.name not in allowed_names),
            # Prefer the no-threshold (etrmax_inf) variant when an extra spec
            # exists at several thresholds — inf is the current default grid.
            key=lambda fp: (0 if "etrmax_inf" in fp.name else 1, fp.name),
        )
        # run_summary accumulates specs across passes (script 5 merge-writes
        # it), but files from passes whose run_summary was later replaced can
        # legitimately be missing from it. Admit such extras UNLESS they
        # collide with an already-admitted (formula, etr, rate) spec — e.g. an
        # old ETR-threshold variant — which would silently double-count.
        seen = set()
        for fp in in_rs:
            spec = _parse_spec_from_filename(fp)
            if spec:
                seen.add((spec["formula"], spec["etr"], spec["rate"]))
        kept_extras, skipped = [], []
        for fp in extras:
            spec = _parse_spec_from_filename(fp)
            key = (spec["formula"], spec["etr"], spec["rate"]) if spec else None
            if key is not None and key not in seen:
                kept_extras.append(fp)
                seen.add(key)
            else:
                skipped.append(fp)
        files = in_rs + kept_extras
        if kept_extras:
            print(
                f"  [spec gate] admitted {len(kept_extras)} file(s) outside the "
                f"current run_summary (no spec collision; e.g. {kept_extras[0].name})"
            )
        if skipped:
            print(
                f"  [spec gate] SKIPPED {len(skipped)} file(s) colliding with an "
                f"admitted spec (would double-count; e.g. {skipped[0].name})"
            )

    parts = []
    for fp in files:
        spec = _parse_spec_from_filename(fp)
        if spec is None:
            continue
        df = pd.read_csv(_longpath(fp))
        if df.empty:
            continue
        for k, v in spec.items():
            if k not in df.columns:
                df[k] = v
        parts.append(df)

    if not parts:
        print(f"  [WARN] no readable country_estimates files under {tables_dir}")
        return pd.DataFrame()

    long_df = pd.concat(parts, ignore_index=True)
    long_df["year"] = pd.to_numeric(long_df["year"], errors="coerce")
    return long_df


# %% MARK: 5. Summary tables (totals, loss sensitivity, income groups)
def country_totals_by_spec(long_df):
    """Σ over years per (iso_partner, formula, etr_name, rate_mode)."""
    grp = (
        long_df.groupby(
            ["iso_partner", "partner_jurisdiction", "wb_income_group", "region_tjn",
             "formula_name", "etr_name", "rate_mode"],
            as_index=False, dropna=False,
        )
        .agg(
            net_revenue_gain_musd=("revenue_gain_from_ut", "sum"),
            tax_revenue_loss_musd=("tax_revenue_loss", "sum"),
            tax_revenue_gain_musd=("tax_revenue_gain", "sum"),
            negative_misalignment_musd=("negative_misalignment", "sum"),
            positive_misalignment_musd=("positive_misalignment", "sum"),
            current_tax_paid_cash_musd=("current_tax_paid_cash_musd", "sum"),
        )
    )
    grp["revenue_gain_pct_of_current_tax"] = (
        100 * grp["net_revenue_gain_musd"] / grp["current_tax_paid_cash_musd"]
    ).replace([np.inf, -np.inf], np.nan)
    return grp


def loss_sensitivity_table(country_totals):
    """For each country, count in how many of the spec combos it loses
    (net_revenue_gain_musd < 0) and how many it gains. Plus min/median/max
    net gain across specs."""
    n_specs = country_totals.groupby("iso_partner")["formula_name"].count().rename("n_specs")
    agg = country_totals.groupby(
        ["iso_partner", "partner_jurisdiction", "wb_income_group", "region_tjn"],
        as_index=False, dropna=False,
    ).agg(
        min_net_gain_musd=("net_revenue_gain_musd", "min"),
        median_net_gain_musd=("net_revenue_gain_musd", "median"),
        max_net_gain_musd=("net_revenue_gain_musd", "max"),
        n_specs_losing=("net_revenue_gain_musd", lambda x: int((x < 0).sum())),
        n_specs_gaining=("net_revenue_gain_musd", lambda x: int((x > 0).sum())),
    )
    agg = agg.merge(n_specs, on="iso_partner", how="left")
    agg["share_specs_losing"] = (agg["n_specs_losing"] / agg["n_specs"]).round(3)
    return agg.sort_values("median_net_gain_musd")


# %% MARK: 6. Per-topic consolidation driver
def analyse_topic(topic):
    print(f"\n=== topic: {topic} ===")
    tables_dir, _ = output_dirs(topic)   # script 6 writes tables only (no figures)

    run_summary_path = tables_dir / "run_summary.csv"
    if not run_summary_path.exists():
        print(f"  [skip] no run_summary.csv found at {run_summary_path}")
        return

    rs = pd.read_csv(run_summary_path)
    print(f"  ({len(rs)} spec combinations in run_summary)")

    allowed_names = (
        set(pd.Series(rs["country_file"]).dropna().map(lambda p: Path(p).name))
        if "country_file" in rs.columns
        else None
    )
    long_df = load_country_long(tables_dir, allowed_names=allowed_names)
    if long_df.empty:
        print(f"  [skip] no country files in {tables_dir}")
        return
    long_df.to_csv(tables_dir / "summary_country_year_long.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_country_year_long.csv'} ({len(long_df):,} rows)")

    totals = country_totals_by_spec(long_df)
    totals.to_csv(tables_dir / "summary_country_totals_by_spec.csv", index=False)
    print(f"  wrote {tables_dir / 'summary_country_totals_by_spec.csv'} ({len(totals):,} rows)")

    # Script 6 exists to produce the DATA layer (the two files above). Every
    # ranking / income-group / figure it used to write duplicated a 7-series
    # paper deliverable (top winners/losers → paper tables, income-group
    # aggregates → paper figures), so none of those are written any more. Below
    # we only build the loss-sensitivity ranking IN MEMORY to print a quick
    # winners/losers sanity check to stdout — nothing is saved. The ranking
    # drops the config-listed CbCR anomalies (the data files keep every country).
    totals_pres = totals[~totals["iso_partner"].isin(DATA_QUALITY_EXCLUSIONS)]
    if totals["iso_partner"].isin(DATA_QUALITY_EXCLUSIONS).any():
        print(
            f"  [note] the stdout ranking excludes data-quality anomalies: "
            f"{sorted(DATA_QUALITY_EXCLUSIONS)} (kept in the data files)"
        )
    sens = loss_sensitivity_table(totals_pres)
    top_gainers = sens.sort_values("median_net_gain_musd", ascending=False).head(TOP_N)
    top_losers = sens.sort_values("median_net_gain_musd", ascending=True).head(TOP_N)

    # Print headline diagnostics to stdout
    print()
    print(f"  Top 10 net gainers (median across specs, USD bn):")
    for _, r in top_gainers.head(10).iterrows():
        _name = "" if pd.isna(r["partner_jurisdiction"]) else str(r["partner_jurisdiction"])
        print(f"    {r['iso_partner']:>4} {_name[:30]:<32}  "
              f"median {r['median_net_gain_musd']/1000:>+9,.1f}  "
              f"min {r['min_net_gain_musd']/1000:>+9,.1f}  "
              f"max {r['max_net_gain_musd']/1000:>+9,.1f}  "
              f"loses in {r['n_specs_losing']}/{int(r['n_specs'])} specs")
    print()
    print(f"  Top 10 net losers (median across specs, USD bn):")
    for _, r in top_losers.head(10).iterrows():
        _name = "" if pd.isna(r["partner_jurisdiction"]) else str(r["partner_jurisdiction"])
        print(f"    {r['iso_partner']:>4} {_name[:30]:<32}  "
              f"median {r['median_net_gain_musd']/1000:>+9,.1f}  "
              f"min {r['min_net_gain_musd']/1000:>+9,.1f}  "
              f"max {r['max_net_gain_musd']/1000:>+9,.1f}  "
              f"loses in {r['n_specs_losing']}/{int(r['n_specs'])} specs")


# %% MARK: 7. main
def main():
    topics = sys.argv[1:] or DEFAULT_TOPICS
    for topic in topics:
        analyse_topic(topic)


if __name__ == "__main__":
    main()
