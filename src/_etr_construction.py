"""Partner-year effective tax rate (ETR) construction.

Single source of truth for the rolling-window ETR statistics used in:
  - 1_clean.py (computes the canonical ETRs from reported profit/tax)
  - 4_correcting_cbcr_for_resource_payments.py (recomputes the same family
    on resource-corrected profit/tax for the excl_resource dataset)

Window is ±2 years (5-year span centred on the focal year), preserving the
behaviour of the pre-extraction main_etrs / alternative_corrected_etrs.

Outputs per call:
  partner_year_df: one row per (iso_partner, year) with columns
      etr_domestic_{suffix}
      etr_foreign_{suffix}
      etr_average_{suffix}
      etr_partner_median_{suffix}   (only when pair_stats=True)
      etr_partner_p25_{suffix}      (only when pair_stats=True)
      etr_partner_min_{suffix}      (only when pair_stats=True)

  pair_year_df: one row per (iso_parent, iso_partner, year) with
      etr_parent_partner_{suffix}
  (None when pair_stats=False.)
"""

import os

import numpy as np
import pandas as pd

# A jurisdiction's pooled-window profit base must exceed this (USD) for its
# aggregate ETR to be considered reliably measured. Below it, the tax/profit
# ratio is dominated by noise rather than a meaningful rate, so the ETR is
# returned as NaN (an UNDEFINED rate, distinct from a measured zero) and
# downstream consumers fall back to the statutory CIT. Default $100M; tunable
# via the ETR_MIN_PROFIT_BASE_USD env var.
ETR_MIN_PROFIT_BASE_USD = float(os.environ.get("ETR_MIN_PROFIT_BASE_USD", "1e8"))


def safe_nonnegative_etr(tax_paid, profit):
    """ETR = tax / profit, clipped to [0, 1]. NaN if profit <= 0 or inputs missing."""
    if pd.isna(tax_paid) or pd.isna(profit) or profit <= 0:
        return np.nan
    etr = tax_paid / profit
    if pd.isna(etr) or np.isinf(etr):
        return np.nan
    return float(min(max(etr, 0.0), 1.0))


def _with_suffix(base, suffix):
    return f"{base}_{suffix}" if suffix else base


def _aggregate_etr_per_partner(df, profit_col, tax_col, out_col):
    """Aggregate tax & profit at iso_partner level, then take the ratio.

    The ETR is UNDEFINED (NaN) when the pooled profit base is negligibly small or
    non-positive (<= ETR_MIN_PROFIT_BASE_USD): the tax/profit ratio on a near-zero
    or negative base is noise, not a meaningful rate. Returning NaN rather than
    clipping such a ratio into [0, 1] keeps a thin- or negative-profit
    jurisdiction from reading as a sub-threshold haven in the misalignment test
    and retaining its positive misalignment. Mirrors the profit<=0 -> NaN guard in
    safe_nonnegative_etr (used for the pair ETR)."""
    d = df.groupby("iso_partner", as_index=False)[[tax_col, profit_col]].sum()
    ratio = d[tax_col] / d[profit_col]
    d[out_col] = ratio.where(d[profit_col] > ETR_MIN_PROFIT_BASE_USD, np.nan)
    d[out_col] = d[out_col].replace([np.inf, -np.inf], np.nan).clip(lower=0, upper=1)
    return d[["iso_partner", out_col]]


def compute_partner_year_etrs(
    df,
    profit_col,
    tax_col,
    *,
    suffix=None,
    grouping_col=None,
    grouping_value=None,
    window=2,
    pair_stats=True,
):
    """Compute rolling-window partner-year ETRs (and optionally pair-year ETRs).

    Parameters
    ----------
    df : DataFrame with columns iso_parent, iso_partner, year, profit_col, tax_col,
        and optionally grouping_col.
    profit_col, tax_col : str
        Names of the profit and tax columns to use in the (tax / profit) ratio.
    suffix : str or None
        Suffix appended to every output column (e.g. "corrected" produces
        "etr_average_corrected"). None / "" → no suffix.
    grouping_col, grouping_value : str or None
        If both are set, filter rows to df[grouping_col] == grouping_value.
    window : int
        Half-window in years; the rolling window is [year - window, year + window]
        inclusive. Default 2 → 5-year window.
    pair_stats : bool
        Whether to compute the pair-year ETR and the partner-level
        median/p25/min aggregations of pair ETRs. Skip for variants that
        don't need these (e.g. the original uncorrected ETR family).

    Returns
    -------
    partner_year_df : DataFrame
    pair_year_df : DataFrame or None
    """
    required = ["iso_parent", "iso_partner", "year", profit_col, tax_col]
    cols = list(required)
    if grouping_col is not None:
        cols = cols + [grouping_col]
    df = df[cols].copy()

    if grouping_col is not None and grouping_value is not None:
        df = df.loc[df[grouping_col] == grouping_value]

    df = df.dropna(subset=[tax_col])

    domestic_col = _with_suffix("etr_domestic", suffix)
    foreign_col = _with_suffix("etr_foreign", suffix)
    average_col = _with_suffix("etr_average", suffix)
    median_col = _with_suffix("etr_partner_median", suffix)
    p25_col = _with_suffix("etr_partner_p25", suffix)
    min_col = _with_suffix("etr_partner_min", suffix)
    pair_col = _with_suffix("etr_parent_partner", suffix)

    partner_results = []
    pair_results = []

    unique_years = sorted(df["year"].dropna().unique())

    for year in unique_years:
        start_year = year - window
        end_year = year + window
        window_df = df[(df["year"] >= start_year) & (df["year"] <= end_year)].copy()

        foreign_df = window_df[window_df["iso_parent"] != window_df["iso_partner"]]
        domestic_df = window_df[window_df["iso_parent"] == window_df["iso_partner"]]

        etr_domestic = _aggregate_etr_per_partner(
            domestic_df, profit_col, tax_col, domestic_col
        )
        etr_foreign = _aggregate_etr_per_partner(
            foreign_df, profit_col, tax_col, foreign_col
        )
        etr_average = _aggregate_etr_per_partner(
            window_df, profit_col, tax_col, average_col
        )

        partner_year = etr_domestic.merge(
            etr_foreign, on="iso_partner", how="outer"
        ).merge(etr_average, on="iso_partner", how="outer")

        if pair_stats:
            pair_window = (
                window_df.groupby(["iso_parent", "iso_partner"], as_index=False)[
                    [tax_col, profit_col]
                ]
                .sum(min_count=1)
                .copy()
            )

            pair_window[pair_col] = pair_window.apply(
                lambda r: safe_nonnegative_etr(r[tax_col], r[profit_col]), axis=1
            )
            pair_window[pair_col] = pair_window[pair_col].clip(lower=0, upper=1)
            pair_window["year"] = year

            pair_results.append(
                pair_window[
                    ["iso_parent", "iso_partner", "year", pair_col]
                ].copy()
            )

            valid_pairs = pair_window.dropna(subset=[pair_col]).copy()

            if valid_pairs.empty:
                partner_stats = pd.DataFrame(
                    columns=["iso_partner", median_col, p25_col, min_col]
                )
            else:
                partner_stats = (
                    valid_pairs.groupby("iso_partner", as_index=False)[pair_col]
                    .agg(**{median_col: "median", min_col: "min"})
                    .copy()
                )

                p25 = (
                    valid_pairs.groupby("iso_partner")[pair_col]
                    .quantile(0.25, interpolation="linear")
                    .reset_index(name=p25_col)
                )

                partner_stats = partner_stats.merge(
                    p25, on="iso_partner", how="left"
                )

                for c in [median_col, p25_col, min_col]:
                    partner_stats[c] = partner_stats[c].clip(lower=0, upper=1)

            partner_year = partner_year.merge(
                partner_stats, on="iso_partner", how="outer"
            )

        partner_year["year"] = year
        partner_results.append(partner_year)

    partner_year_df = pd.concat(partner_results, ignore_index=True)
    pair_year_df = (
        pd.concat(pair_results, ignore_index=True) if pair_stats else None
    )

    return partner_year_df, pair_year_df
