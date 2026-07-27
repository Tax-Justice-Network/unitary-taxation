# %% [0] Bilateral profit-shifting links — optional post-step to script 5
"""
Bilateral profit-shifting links: who shifts profit FROM whom.

This is an OPTIONAL deliverable that runs AFTER `5_estimate_profit_shifting.py`.
It used to sit behind a `RUN_BILATERALS` toggle inside script 5; it now stands
alone, so the headline pipeline stays lean and bilateral links are produced only
when explicitly wanted.

For each spec in the run we are post-processing it reads that spec's per-country
misalignment file and, within each (year, reporting parent), splits every
sufferer's shifted profit / tax loss across the havens that harmed that parent's
MNEs — pro-rata to each haven's positive misalignment (a haven never shifts onto
itself). The result is written as `bilateral_links__<spec>.csv` next to the
misalignment file, and `run_summary.csv` gains `n_bilateral_rows` / `bilateral_file`.

Run it for the SAME sample you just ran script 5 on: it honours the same
`RUN_DATASET` / `REPORTED_ONLY` (and `RUN_OUTPUT_TOPIC`) environment settings to
find that sample's output folder and its `run_summary.csv`.
"""
import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from pandas.errors import EmptyDataError

# Match script 5: keep stdout UTF-8 so the long run_summary table (whose rows
# embed the Arabic-character project path) prints without crashing on Windows.
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from config import *

# Locate the output folder of the run we are post-processing. This mirrors the
# topic resolution at the top of 5_estimate_profit_shifting.py: every dataset's
# output topic is "unitary_taxation_<RUN_DATASET>", with a "_reported" suffix for
# the reported-only view. RUN_OUTPUT_TOPIC overrides the base (bootstrap driver).
RUN_DATASET = os.environ.get("RUN_DATASET", "disaggregated")
REPORTED_ONLY = os.environ.get("REPORTED_ONLY", "1") not in ("0", "false", "False", "")
_topic_base = os.environ.get("RUN_OUTPUT_TOPIC", f"unitary_taxation_{RUN_DATASET}")
_OUTPUT_TOPIC = _topic_base + ("_reported" if REPORTED_ONLY else "")
OUTPUT_ROOT, _ = output_dirs(_OUTPUT_TOPIC)

BILATERAL_COLS = [
    "year",
    "iso_responsible",
    "iso_affected",
    "shifted_profit_musd",
    "tax_loss_musd",
]


def _longpath(p):
    """On Windows, prefix paths > 240 chars with the \\\\?\\ long-path namespace
    so open() bypasses the legacy 260-char MAX_PATH limit. The OneDrive +
    Arabic-character project root pushes some misalignment filenames over the
    limit. A no-op on non-Windows."""
    s = os.fspath(p)
    if sys.platform == "win32" and len(s) > 240 and not s.startswith("\\\\?\\"):
        s = "\\\\?\\" + os.path.abspath(s)
    return s


def add_loss_rate_to_misalignment(misalignment_df):
    df = misalignment_df.copy()

    if "loss_rate_col" not in df.columns:
        raise ValueError("misalignment_df must contain 'loss_rate_col'.")

    df["loss_rate"] = np.nan

    for rate_col in df["loss_rate_col"].dropna().unique():
        if rate_col not in df.columns:
            raise ValueError(
                f"Loss-rate column '{rate_col}' listed in loss_rate_col is not present "
                f"in the misalignment data."
            )
        mask = df["loss_rate_col"] == rate_col
        df.loc[mask, "loss_rate"] = pd.to_numeric(
            df.loc[mask, rate_col], errors="coerce"
        )

    df["loss_rate"] = df["loss_rate"].fillna(0)
    return df


def estimate_bilateral_links_from_misalignment(misalignment_df):
    output_cols = [
        "year",
        "iso_responsible",
        "iso_affected",
        "shifted_profit_musd",
        "tax_loss_musd",
    ]

    if misalignment_df.empty:
        return pd.DataFrame(columns=output_cols)

    required_cols = [
        "year",
        "iso_parent",
        "iso_partner",
        "misaligned_profit",
        "loss_rate_col",
    ]
    missing_cols = [
        col for col in required_cols if col not in misalignment_df.columns
    ]
    if missing_cols:
        raise ValueError(
            f"Missing required columns for bilateral estimation: {missing_cols}"
        )

    df = misalignment_df.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["misaligned_profit"] = pd.to_numeric(
        df["misaligned_profit"], errors="coerce"
    )

    df = df.loc[
        df["year"].notna()
        & df["iso_parent"].notna()
        & df["iso_partner"].notna()
        & df["misaligned_profit"].notna()
    ].copy()

    if df.empty:
        return pd.DataFrame(columns=output_cols)

    df = add_loss_rate_to_misalignment(df)

    df["positive_misalignment_musd_row"] = np.where(
        df["misaligned_profit"] > 0,
        df["misaligned_profit"] / 1e6,
        0.0,
    )
    df["suffered_shifted_profit_musd_row"] = np.where(
        df["misaligned_profit"] < 0,
        -df["misaligned_profit"] / 1e6,
        0.0,
    )
    df["suffered_tax_loss_musd_row"] = (
        df["suffered_shifted_profit_musd_row"] * df["loss_rate"]
    )

    parent_year_partner = df.groupby(
        ["year", "iso_parent", "iso_partner"], as_index=False
    ).agg(
        positive_misalignment_musd=("positive_misalignment_musd_row", "sum"),
        suffered_shifted_profit_musd=("suffered_shifted_profit_musd_row", "sum"),
        suffered_tax_loss_musd=("suffered_tax_loss_musd_row", "sum"),
    )

    bilateral_parts = []

    for (year, iso_parent), grp in parent_year_partner.groupby(
        ["year", "iso_parent"], sort=False
    ):
        harmers = grp.loc[
            grp["positive_misalignment_musd"] > 0,
            ["iso_partner", "positive_misalignment_musd"],
        ].copy()

        sufferers = grp.loc[
            (grp["suffered_shifted_profit_musd"] > 0)
            | (grp["suffered_tax_loss_musd"] > 0),
            [
                "iso_partner",
                "suffered_shifted_profit_musd",
                "suffered_tax_loss_musd",
            ],
        ].copy()

        if harmers.empty or sufferers.empty:
            continue

        for sufferer in sufferers.itertuples(index=False):
            eligible_harmers = harmers.loc[
                harmers["iso_partner"] != sufferer.iso_partner
            ].copy()

            total_positive_eligible = eligible_harmers[
                "positive_misalignment_musd"
            ].sum()

            if total_positive_eligible <= 0:
                continue

            eligible_harmers["share_of_harm"] = (
                eligible_harmers["positive_misalignment_musd"]
                / total_positive_eligible
            )

            eligible_harmers["year"] = int(year)
            eligible_harmers["iso_responsible"] = eligible_harmers["iso_partner"]
            eligible_harmers["iso_affected"] = sufferer.iso_partner
            eligible_harmers["shifted_profit_musd"] = (
                sufferer.suffered_shifted_profit_musd
                * eligible_harmers["share_of_harm"]
            )
            eligible_harmers["tax_loss_musd"] = (
                sufferer.suffered_tax_loss_musd * eligible_harmers["share_of_harm"]
            )

            bilateral_parts.append(
                eligible_harmers[
                    [
                        "year",
                        "iso_responsible",
                        "iso_affected",
                        "shifted_profit_musd",
                        "tax_loss_musd",
                    ]
                ]
            )

    if not bilateral_parts:
        return pd.DataFrame(columns=output_cols)

    bilateral_df = pd.concat(bilateral_parts, ignore_index=True)

    bilateral_df = bilateral_df.groupby(
        ["year", "iso_responsible", "iso_affected"], as_index=False
    ).agg(
        shifted_profit_musd=("shifted_profit_musd", "sum"),
        tax_loss_musd=("tax_loss_musd", "sum"),
    )

    bilateral_df = bilateral_df.sort_values(
        ["year", "iso_responsible", "iso_affected"]
    ).reset_index(drop=True)

    return bilateral_df


# %% [1] Build one bilateral_links file per spec listed in run_summary.csv
run_summary = pd.read_csv(_longpath(OUTPUT_ROOT / "run_summary.csv"))

bilateral_file_paths = []
n_bilateral_rows = []
for row in run_summary.itertuples(index=False):
    misalignment_file = Path(row.misalignment_file)
    bilateral_file = misalignment_file.parent / misalignment_file.name.replace(
        "misalignment__", "bilateral_links__"
    )

    try:
        misalignment_df = pd.read_csv(_longpath(misalignment_file))
        bilateral_df = estimate_bilateral_links_from_misalignment(misalignment_df)
    except EmptyDataError:
        bilateral_df = pd.DataFrame(columns=BILATERAL_COLS)

    bilateral_df.to_csv(_longpath(bilateral_file), index=False)
    bilateral_file_paths.append(str(bilateral_file))
    n_bilateral_rows.append(len(bilateral_df))

run_summary["n_bilateral_rows"] = n_bilateral_rows
run_summary["bilateral_file"] = bilateral_file_paths
run_summary.to_csv(_longpath(OUTPUT_ROOT / "run_summary.csv"), index=False)

print("\n" + "=" * 100)
print("BILATERAL LINK FILES CREATED")
print("=" * 100)
print(
    run_summary[
        [
            "sample_name",
            "formula_name",
            "etr_name",
            "rate_mode",
            "n_bilateral_rows",
            "bilateral_file",
        ]
    ].to_string(index=False)
)
