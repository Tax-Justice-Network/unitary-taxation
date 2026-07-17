# ETR construction: negligible-profit guard, CIT substitution, fit-the-sample haven test

Recorded 2026-06-25. These changes fix spurious "winner" jurisdictions (thin-profit
low-income countries reading as sub-15% havens) in the minimum-ETR misalignment runs.

## 1. Negligible / non-positive profit base → undefined (NaN) ETR

`src/_etr_construction.py :: _aggregate_etr_per_partner` returns **NaN** for a
jurisdiction's pooled-window average ETR when the pooled profit base is **≤ a
minimum size**, not just when it is ≤ 0:

```python
ETR_MIN_PROFIT_BASE_USD = float(os.environ.get("ETR_MIN_PROFIT_BASE_USD", "1e8"))  # $100M
...
d[out_col] = ratio.where(d[profit_col] > ETR_MIN_PROFIT_BASE_USD, np.nan)
```

**Why.** The aggregate ETR is `Σtax / Σprofit` over a 5-year window. When the pooled
profit base is tiny (or negative), that ratio is dominated by noise, not by a
meaningful rate. Clipping a near-zero/negative-base ratio to `[0,1]` made several
thin-profit jurisdictions read as **sub-15% havens**, so the misalignment test kept
their (large, gravity-**imputation-driven**) *positive* misalignment — producing
implausible low-income "winners".

Concrete case: in the **excl_resource** sample, South Sudan's oil profit is stripped
out, leaving only ~$59M of non-resource pooled profit whose measured foreign ETR is
**4.9%** (< 15%) → it was wrongly flagged a haven and kept +$2.2bn of imputed inflow.
Threshold chosen as **$100M** (env-tunable via `ETR_MIN_PROFIT_BASE_USD`) — it is a
"is this rate reliably measurable" floor on the *non-resource* base, not a claim about
the size of the whole economy.

This guard lives in the **shared** `_etr_construction.py`, so it applies to **both**
the corrected family (built in `1_clean.py`) and the excl_resource family (rebuilt in
`4_correcting_cbcr_for_resource_payments.py`).

The pair ETR (`safe_nonnegative_etr`, a diagnostic) keeps the plain `profit <= 0`
guard — the negligible-size floor is only for the partner-level aggregate ETR used in
the haven test.

## 2. Undefined ETR → statutory CIT substitution

An undefined ETR means "rate not reliably measured", **not** "zero-tax haven". So a
NaN ETR falls back to the **partner's mean measured rate across years, then the
statutory CIT**:

- corrected family: `1_clean.py :: fill_missing_cit_and_corrected_etrs` (pre-existing).
- excl_resource family: `4_correcting_… :: _fill_excl_resource_etrs` (added 2026-06-25,
  mirrors the clean-script logic).

CIT substitution is **direction-aware**, which is exactly what we want:
- thin-profit low-income countries have CIT ≈ 25–35% → **> 15% → non-haven** → their
  imputation-driven positive misalignment is removed.
- genuine low-statutory havens have CIT **< 15%** (e.g. Ireland 12.5%) → **stay havens**.

Because the substitution happens upstream, the script-5 haven test and revenue legs
never see a NaN rate. The `df[threshold_rate_col].isna()` branch in
`_calculate_misalignment` is kept only as a defensive backstop.

## 3. Decisive "max" ETR fits the sample being run

Earlier, `5_estimate_profit_shifting.py` **force-overrode** the 15% test to always use
`etr_average_excl_resource`. As of **2026-06-25** that override is removed: the
minimum-ETR test uses the average ETR **that fits the active sample** —
`etr_average_corrected` for the baseline/disaggregated sample,
`etr_average_excl_resource` for the excl_resource sample, etc. (`threshold_rate_col`
is taken as-passed, i.e. the dataset's own `etr_col`).

## 3b. Haven test: EITHER ETR OR CIT below the threshold (2026-06-25)

A jurisdiction is treated as a profit-shifting **destination** (keeps its positive
misalignment) if **EITHER** its effective ETR **OR** its statutory CIT is below the
minimum threshold. The positive is removed only when **both** rates are at/above it.
Implemented in `5_estimate_profit_shifting._calculate_misalignment`:

```python
_etr_eff  = df[threshold_rate_col].fillna(df["cit"])   # fit-the-sample ETR, CIT fallback
_cit_rate = df["cit"]
_both_above = (_etr_eff > etr_max) & (_cit_rate > etr_max)
df.loc[(df["misaligned_profit"] > 0) & _both_above, "misaligned_profit"] = 0
```

**Why.** The pooled CbCR ETR for low-*statutory* havens creeps just above 15% (the
aggregate-vs-marginal gap — see §4 on Ireland), so an ETR-only test drops them. Adding
the CIT leg captures Ireland (CIT 12.5%), Jersey (0%), Malta, Liechtenstein, Macau,
Cyprus, while genuine high-tax economies (high ETR AND high CIT: China, USA, Japan,
Saudi) are still excluded. The rule is strictly *more inclusive* than ETR-only — it
only ever adds havens.

**Effect** (excl_resource, `sales_employees_destcfb`, point): Ireland −35 → **+470bn**;
Jersey → +124, Macau → +33, Liechtenstein → +19, Malta → +17; haven group
+4172 → **+4717bn** (+$545bn, ~$414bn of it Ireland); low-income group unchanged at
**−8.8bn** (LIC statutory rates are high, so the CIT leg doesn't rescue them);
global total still nets to 0.

## 3c. Reported-direction sign guard (per partner-year)

The imputed (distributed) rows may **amplify** but must not **reverse** — nor, where
nothing is reported, **manufacture** — the profit-shifting direction implied by the
directly-reported rows alone. The constraint is applied **per (partner, year)**, not on
the across-year aggregate: a jurisdiction may legitimately be a recipient in one year and
a loser in another, so each year's full estimate is constrained to its own reported-only
direction. The across-year sum is free to net out however it does.

Implemented in `5_estimate_profit_shifting.calculate_misalignment` (which runs per year):
1. Compute this year's misalignment on the directly-reported rows alone
   (`is_distributed == 0`) — recursively, `reported_sign_guard=False` on the inner call —
   and take each partner's net sign. `|net| < REPORTED_SIGN_EPS_USD` ($5M default) or a
   partner absent from the reported rows counts as **no reported anchor** (sign 0).
2. **Before** the within-parent balancing, zero any full-sample misalignment that
   conflicts with that sign:
   - reported net < 0 → drop the partner's **positive** rows (cannot become a winner);
   - reported net > 0 → drop its **negative** rows (cannot become a loser);
   - no anchor (sign 0) → drop **both** (don't manufacture from nothing).
   The balancing then rescales as usual, so conservation to zero is preserved.

Env: `REPORTED_SIGN_GUARD` (default on; set 0 to disable), `REPORTED_SIGN_EPS_USD`
(default `5e6`). The $5M floor is small on purpose — it keeps genuinely-anchored thin-data
jurisdictions (e.g. a +$40M reported recipient) while clipping pure-imputation cases
(near-zero reported).

**Effect** (excl_resource, `sales_employees_destcfb`): per-(partner,year) reversals **0**;
no-anchor leaks **0**; conservation nets to 0. Across-year sign-reversal artifacts that the
guard removes include manufactured winners on diluted benchmarks (a bad reporter whose
reported rows say "loser" but whose imputed benchmark flips it positive). Jurisdictions
that remain net-positive across years (e.g. on a single reported-positive year) are
per-year-consistent by construction.

## 4. Ireland and other non-reporting havens

Ireland is on the **bad-reporter exclusion list (2016–2022)**, so it has **no
Irish-parent rows** — its `domestic` ETR is therefore n/a, and its `foreign`/`average`
ETR (~16–18%) is reconstructed from how *foreign* MNEs report their Irish operations.
That reconstructed rate is genuinely **> 15%** in CbCR (the well-known aggregate-vs-
marginal gap), so the ETR test classifies Ireland as a non-haven and the negligible-
profit/CIT fix does **not** change it (its ETR is reliably measured, just high).

Consequence: haven **classification** for presentation must use the **list**, not the
ETR test. The agreed country-group haven set is the outcome-based
`CTHI Haven Score > 65 AND net profit-shifting recipient` **∪ `TAX_HAVENS_CLEANING`**
(the García-Bernardo list used in `1_clean`'s dividend correction), which restores
Ireland, Malta, etc.
