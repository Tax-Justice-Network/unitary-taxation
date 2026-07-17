# Disaggregation method change — single gravity + profitability method (2026-06-23)

## What changed

`src/2_disaggregate_aggregated_values.py` previously offered **several
interchangeable ways** to disaggregate a bad reporter's aggregate rows
(continent / `WXD` / `W_O` totals) onto specific partner countries. On 2026-06-23
these were collapsed to **one** method, by user decision.

### The retained (now sole) method

On distributed (`is_distributed == 1`) rows:

1. **Real economic activity** — `n_employees`, `unrelated_party_revenues`,
   `tangible_assets_except_cash` — is imputed by the **García-Bernardo & Janský
   (2024) gravity/ML model** (`data/intermediate/gravity/gravity_imputed_activity.csv`).
   `payroll` follows automatically (imputed employees × wage × 12).
2. **Profit** (`profit_loss_before_income_tax_corrected` and the raw
   `profit_loss_before_income_tax`) is imputed from each partner's **reported
   profitability** — `_impute_profit_multifactor`, per-partner yield
   = Σ reported profit ÷ Σ reported factor over `PROFIT_IMPUTATION_FACTORS`
   (sales, employees, tangible assets), **winsorized across partners at the
   1st/99th percentile** (`PROFIT_YIELD_WINSOR = 0.01` — clips only the explosive
   thin-denominator outliers; every other partner keeps its own yield), then
   rescaled per `(year, parent, source_aggregate_code)` group to conserve the
   reported aggregate profit. **Negative (loss-making) profitability is
   preserved** — sign is not clamped. (The earlier empirical-Bayes shrinkage
   toward the global yield was **removed** — pulling every yield toward the
   positive global mean flipped thin-activity loss-makers to a positive imputed
   profit.)
3. **`total_revenues`** is floored to the imputed `unrelated_party_revenues`
   (related-party revenue is not imputed), so the Route-B resource-α denominator
   stays populated in full mode.
4. **Every other variable is NOT imputed** — `related_party_revenues`,
   `stated_capital`, `n_entities`, `holding_or_managing_ip`, and both
   `income_tax_*` columns are left **blank** on distributed rows.

**Recipient set = broad**: each aggregate is spread across **all
structurally-eligible markets** (every real foreign country observed in the CbCR
panel), gravity-weighted, not just the partners good reporters happened to report.

### What was removed

- **Trimmed-mean activity weighting** — `compute_pooled_median_share_weights`,
  `_trimmed_mean_one_partner`, `MIN_REPORTERS_FOR_TRIMMED_MEAN`, `MIN_AFTER_TRIM`,
  and the `IMPUTE_METHOD` env toggle (`trimmed_mean` vs `gravity`). The structural
  eligibility / residual / conservation skeleton in
  `distribute_aggregates_per_reporter` is retained, but phase-1 weights are now a
  flat `build_uniform_recipient_weights` table (selects the broad recipient set +
  conserves each aggregate); the activity split is set entirely by the gravity
  predictions.
- **Weight-distributed profit** and the **sales-margin-only** profit variant —
  the `IMPUTE_PROFIT_FROM_MARGIN` toggle and the sales-only
  `PROFIT_IMPUTATION_FACTORS` option. Multi-factor profitability is now the only
  profit imputation.
- **`ALLOW_NEGATIVE_SIGNED_SHARES` toggle** — sign-preserving negative profit is
  now unconditional.
- **The `_gravity` file/topic duplication.** Gravity now writes the **canonical**
  `data/final/cbcr_main_disaggregated.csv` (bootstrap draws: `__boot{seed}`). The
  parallel `cbcr_main_disaggregated_gravity.csv` / `*_gravity` datasets, the
  `DISAGG_VARIANT` env in script 4, the `*_gravity` `DATASET_CONFIGS` entries in
  script 5, and the `archive/trimmed_full/*` output routing were all collapsed onto
  the plain names. The now-degenerate trimmed-mean-vs-gravity comparison
  (9c Part 2) was deleted.

## Why

The user chose to keep the one method where activity is gravity-imputed and profit
follows reported profitability (including negative profitability), and to retire the
trimmed-mean alternatives entirely so there is a single, unambiguous disaggregation.

## Conservation & validation notes

- Conservation is checked **only for the imputed variables** (the three activity
  factors + the two profit columns). `total_revenues` (floored) and the un-imputed
  variables are excluded by design. Small residual activity-variable diffs come from
  the pre-existing non-negative clipping of distributed activity values and from the
  per-country activity cap binding on micro-states — not from the method change.
- The **reported-only sample is unchanged**: it filters to `is_distributed == 0`, so
  the imputation method never touches it (verified: all reported rows identical to the
  prior gravity output).
- **Re-validation expected**: the broad recipient set changes which markets receive
  imputed rows, so the full gravity chain (script 2 → 4 → 5 × datasets/reported → 6 →
  8/9) must be re-run and headline numbers re-checked.

## Confidence intervals

Point estimates carry **no CIs by default**. CIs (gravity-imputation uncertainty
only, full mode) come from the separate `src/gravity/run_bootstrap.py` driver
(now wired to the canonical `cbcr_main_disaggregated__boot{s}.csv` / `RUN_DATASET=disaggregated`),
with `9e_attach_bootstrap_ses.py` joining mean / SE / 2.5–97.5% CI onto the headline
country table.

## Files touched

- `src/2_disaggregate_aggregated_values.py` (core rewrite)
- `src/4_correcting_cbcr_for_resource_payments.py` (drop `DISAGG_VARIANT`)
- `src/5_estimate_profit_shifting.py` (drop `*_gravity` `DATASET_CONFIGS`)
- `src/config.py` (repoint full-mode topics to `unitary_taxation/gravity/…`; drop
  `_gravity` / `trimmed_full` entries)
- `src/gravity/run_bootstrap.py`, `src/9c_gravity_destination_comparison.py`
  (drop Part 2), `src/9d_gravity_overview.py`, `src/9e_attach_bootstrap_ses.py`,
  `src/9g_country_estimates_sheet.py`, `src/9h_negative_estimates_detail.py`
- `CLAUDE.md` (disaggregation / gravity / profit sections)
