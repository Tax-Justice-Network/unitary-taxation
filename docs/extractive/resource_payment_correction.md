# Resource-payment correction of CbCR profit — pipeline

Produces three CbCR datasets that net out, or gross up, the resource payments
governments already collect. Together with the untouched
`cbcr_main_disaggregated.csv` baseline, they form the **four parallel
deliverables** the unitary-taxation analysis can run on:

| Dataset (CSV) | Conceptual meaning |
|---|---|
| `cbcr_main_disaggregated.csv` *(unchanged baseline)* | **Resources ignored** — reported figures, extractive activity treated like any other sector. |
| `cbcr_main_excl_resource.csv` | **Resources excluded** — strip the resource-profit base from profit and the post-profit resource tax from cash tax. UT on the non-extractive corporate income only. Ships with the recomputed `etr_*_excl_resource` family. |
| `cbcr_main_incl_resource.csv` | **Resources included** — gross profit & tax up by actual pre-profit resource payments (royalties, surface fees, bonuses, PSA profit-oil). Compare UT yield to the diagnostic `actual_resource_contribution_usd` for the "what would UT have yielded vs. what governments actually collected via resource flows" story. |
| `cbcr_main_excl_resource_floored.csv` | **Resources excluded + IGF-ATAF flexible-royalty floor enforced** — strip the resource-profit base **and** the floor add-on (the extra royalty the IGF-ATAF schedule would have compelled where actual capture fell short) from the UT profit pool. The tax line is unchanged from `excl_resource` (the floor is a hypothetical royalty, not a CIT counterfactual). Total state recovery = UT-derived revenue on the smaller pool + Σ `floor_add_on_<cat>_usd`. Default = Cat 1 (price-based); Cat 2 & Cat 3 alternatives are emitted in parallel. No `cbcr_main_incl_resource_floored.csv` is emitted — the 5-factor UT in scenario 4 substitutes for the resource regime entirely, so a minimum-royalty floor on top of it is meaningless. |

**Main vs. alternative specification.** The **three-scenario data-correction
route** is the headline deliverable: it uses `cbcr_main_disaggregated.csv`
(resources ignored), `cbcr_main_excl_resource.csv` (resources excluded) and
`cbcr_main_excl_resource_floored.csv` (excluded + minimum royalty). The fourth
file, `cbcr_main_incl_resource.csv`, feeds the **alternative / backup
resource-factor route** (5-factor scenarios 4 & 5) — kept as a sensitivity
framing, not the main specification. See
[`../scenarios_methodology.md`](../scenarios_methodology.md).

The three `_resource` files all carry the **same non-resource ETR family**
(`etr_average_excl_resource`, `etr_partner_median_excl_resource`,
`etr_partner_p25_excl_resource`, `etr_partner_min_excl_resource`, and the
diagnostic `etr_parent_partner_excl_resource`). It is computed once on the
`(profit_loss_excl_resource, income_tax_paid_on_cash_basis_excl_resource)`
pair via the shared `_etr_construction.py` module — the rate at which
non-resource corporate income is actually taxed — and carried over to the
`incl_resource` and `excl_resource_floored` files so script 5 can read
consistent ETRs regardless of which dataset is active.

`cbcr_main_resource_corrected.csv` (the previous composite output) is
**retired**: each of the three new files is self-contained for its UT view,
and the four-dataset scheme avoids the column-naming overlap that made the
old composite file confusing.

## Pipeline

| Step | Script | Output | Does |
|---|---|---|---|
| 1 | `src/3_extractive_prep/1_6_pull_eiti_company_payments_api.py` | `data/intermediate/extractive/eiti_revenue_company_raw.jsonl`, `eiti_company_payments_long.csv` | Pulls company-level payments-to-government from the EITI Open Data API `/revenue` endpoint (~246 k raw records → ~92 k usable, $2.84 T, 58 countries); classifies each into `royalty_like` / `cit` / `equity` / `other` from the GFS label; tags a commodity (oil_gas/coal/minerals/unknown/other). ~98 k raw records carry no country/year link (~$540 B / 18 %) and are dropped — recoverable later by dereferencing `organisation.summary_data`. |
| 1a | `src/3_extractive_prep/1_7a_build_orbis_entity_universe.py` | `orbis_entity_universe.csv` | Builds the full Orbis extractive-entity universe (~613 k entities) with `in_cbcr_universe = (n_subsidiaries ≥ 2) OR (peak revenue ≥ €750 M)`. |
| 2 | `src/3_extractive_prep/1_7_match_eiti_companies_to_orbis.py` | `eiti_company_hq_map.csv` | Country-blocked match of each EITI company string → Orbis entity → GUO HQ country. Match rate ≈ 24 % of names / **80 % by value**. Unmatched companies are dropped (treated as local). |
| 3 | `src/3_extractive_prep/1_8_resource_payments_by_hq_source.py` | `resource_payments_by_hq_source_yearly.csv` | Aggregates matched EITI payments to `(source_iso3, hq_iso3, commodity, year)` × {pre / post / equity / other}. Cascade-fills non-EITI source countries: **EITI > manual > GRD > rent-proxy**. Non-EITI country totals are distributed to HQs by `hq_share_<commodity>` with a `domestic_share` carving out the NOC. ≈ 82 k rows, 160 source countries. |
| 4 | `src/4_correcting_cbcr_for_resource_payments.py` | `data/final/cbcr_main_excl_resource.csv`, `data/final/cbcr_main_incl_resource.csv`, `data/final/cbcr_main_excl_resource_floored.csv` | Reads `cbcr_main_disaggregated.csv` + `resource_payments_by_hq_source_yearly.csv` + `data/raw/resources/resource_profit_tax_rate.csv` + `rents_combined_yearly.csv` + `rent_fractions_calibrated.csv` + `hq_shares_by_commodity_yearly.csv` (global per-(hq, commodity, year) — used by the floored file's flex-floor and by `1_8`) + `hq_shares_by_source_commodity_yearly.csv` (bilateral per-(source, hq, commodity, year) Orbis — used by the 5-factor `resource_factor_usd`) + `_reference_prices.py`. Computes `resource_profit_base = max(post_profit_take ÷ effective_resource_profit_tax_rate, equity_income)` per (source, commodity) — no zero-clip (a negative post → negative base → `excl_resource` profit > reported there). For the floored file, computes the IGF-ATAF flexible-royalty minimum in three parallel schedules (Cat 1 = price-based, Cat 2 = margin × gross revenue, Cat 3 = margin × rent) — each × `hq_share_<c>` — and adds `floor_add_on_<c>_usd = max(flex_min_<c> − actual_pre_<c>, 0)` **per (source, hq, commodity, year)** before summing to the cell, then *subtracts* this gap from `profit_loss_excl_resource` (so the UT pool shrinks by the hypothetical royalty; the tax line is unchanged). Aggregates to (hq, source, year), allocates onto each CbCR cell, computes the new profit & tax columns, recomputes the **non-resource ETR family** on the excl_resource pair via `_etr_construction.compute_partner_year_etrs`, and writes the three deliverable files. |
| QA | `src/3_extractive_prep/qa_resource_payment_correction.py` | stdout | ~60 PASS/FAIL/WARN checks across the upstream artefacts plus per-row identities, parent-year totals, alias-equals-cat1, ETR-NaN-on-distributed-rows, and the carry-over of ETRs from the excl_resource file. As of the 2026-06 re-run: **1 FAIL, 2 WARN** — the FAIL (`resource_tax_deduction ≥ post_profit_payments`) fires on ~6,600 **capped** rows where `base > reported profit`: the per-row cap scales the tax deduction down by `base_capped/base_raw`, which the assertion doesn't yet account for (structural cap-vs-check mismatch, broad across countries, not a data error). The WARNs are coverage/reconciliation (multi-`data_source` countries; EITI-vs-payments reconciliation ~12%). |

## Column naming

For each row, all four files share the original CbCR identifier + variable
columns (`iso_parent`, `iso_partner`, `year`, `is_distributed`,
`profit_loss_before_income_tax_corrected`, `income_tax_paid_on_cash_basis`,
`n_employees`, `unrelated_party_revenues`, `tangible_assets_except_cash`,
`payroll`, `cit`, `partner_jurisdiction`, …). The dataset-specific columns
are listed below.

### `cbcr_main_excl_resource.csv`

| Column | Meaning |
|---|---|
| `resource_profit_base_usd` | `max(post_profit ÷ effective_resource_rate, equity_income)` per (source, commodity), summed to the cell. The profit base the state has claimed. Signed (can be negative — net CIT refund). |
| `post_profit_payments_usd` | Resource-related corporate income tax + special petroleum/mining surtaxes + windfall levies attributed to the cell. Signed. |
| **`profit_loss_excl_resource`** | `profit_loss_before_income_tax_corrected − resource_profit_base_usd` — the **UT profit**. (≤ reported, except where `post < 0`.) |
| **`income_tax_paid_on_cash_basis_excl_resource`** | `income_tax_paid_on_cash_basis − post_profit_payments_usd` — the **UT cash tax** consistent with the UT profit. |
| `total_profit_loss_excl_resource` | `Σ profit_loss_excl_resource` over `(iso_parent, year)` — the UT pool. |
| `etr_average_excl_resource` / `etr_partner_median_excl_resource` / `etr_partner_p25_excl_resource` / `etr_partner_min_excl_resource` | Recomputed non-resource ETR family (5-year rolling window) — used as UT rates. |
| `etr_parent_partner_excl_resource` | Diagnostic pair ETR. NaN on `is_distributed == 1` rows by design (no real report for that (parent, partner, year) cell). |

The reported-profit ETRs (`etr_*_corrected`) from the disaggregated file are
**dropped** in the resource-corrected outputs: they were computed on reported
profit and have no methodological meaning once profit & tax are
resource-corrected.

### `cbcr_main_incl_resource.csv`

| Column | Meaning |
|---|---|
| `pre_profit_payments_usd` | Royalties / licence & area fees / signature & production bonuses / production entitlements attributed to the cell. Expensed ⇒ NOT in CbCR profit-before-tax. |
| `post_profit_payments_usd` | As above. |
| `equity_income_usd` | State dividends / state-participation income attributed to the cell. |
| **`actual_resource_contribution_usd`** | `pre + post + equity` per row — the total state take via resource channels (kept as a diagnostic for the "UT yield vs. actual capture" comparison). |
| **`profit_loss_incl_resource`** | `profit_loss_before_income_tax_corrected + pre_profit_payments_usd` — the **UT profit** (gross of pre-profit costs). (≥ reported everywhere.) |
| **`income_tax_paid_on_cash_basis_incl_resource`** | `income_tax_paid_on_cash_basis + pre_profit_payments_usd` — the **UT cash tax** consistent with grossing profit up by the pre-profit payments. |
| `total_profit_loss_incl_resource` | `Σ profit_loss_incl_resource` over `(iso_parent, year)`. |
| `etr_*_excl_resource` | Non-resource ETRs, carried over from the excl_resource computation (same values, same column names — they represent the rate at which non-resource corporate income is actually taxed and are the right rate to apply in UT regardless of profit base). |

### `cbcr_main_excl_resource_floored.csv`

| Column | Meaning |
|---|---|
| `resource_profit_base_usd`, `resource_tax_deduction_usd`, `post_profit_payments_usd`, `equity_income_usd`, `pre_profit_payments_usd`, `actual_resource_contribution_usd` | As in `excl_resource` / `incl_resource`. |
| `flex_min_cat1_usd` / `cat2` / `cat3` | IGF-ATAF flexible-royalty minimum per row, summed across commodities — Cat 1 price-based, Cat 2 margin × gross revenue, Cat 3 margin × rent (× `hq_share_<c>`). |
| **`floor_add_on_cat1_usd`** / `cat2` / `cat3` | `max(Σ_<commodity> flex_min_<c> − Σ_<commodity> total_capture_<c>, 0)` per `(source, hq, year)` cell, where `total_capture = pre_profit + post_profit + equity_income` — the extra royalty revenue the IGF-ATAF floor compels. The floor is a minimum on the state's **total** resource take, assessed on the whole resource sector **in aggregate** (summed across commodities) rather than commodity-by-commodity, so the add-on is zero wherever a jurisdiction's combined capture (royalties + profit-based taxes + equity, across all minerals) already meets its combined minimum. Cat 1 is the default; cat 2 & cat 3 are alternatives. |
| **`profit_loss_excl_resource_floored`** (= cat 1 alias) | `profit_loss_excl_resource − floor_add_on_cat1_usd` — the **UT profit** under the floored regime (the extra royalty is treated as a pre-profit cost, so it reduces the UT pool). |
| `profit_loss_excl_resource_floored_cat1` / `cat2` / `cat3` | Per-category variants. cat1 equals the unsuffixed alias. |
| **`income_tax_paid_on_cash_basis_excl_resource_floored`** (= `..._excl_resource`) | Identical to `income_tax_paid_on_cash_basis_excl_resource`. The floor is a hypothetical royalty, not a CIT counterfactual, so the tax line is left unchanged. |
| `total_profit_loss_excl_resource_floored` (= cat 1 alias) and `_cat1` / `_cat2` / `_cat3` | Parent-year totals. |
| `etr_*_excl_resource` | Non-resource ETRs, carried over. |

**Total state recovery under this regime** = (UT-derived revenue on the smaller pool, from script 5) + Σ `floor_add_on_cat1_usd` (counted as a separate royalty stream alongside the UT). Script 8 (`8_five_scenario_report.py`) makes this combination for scenario 3.

## Running it

```
python src/4_correcting_cbcr_for_resource_payments.py
python src/3_extractive_prep/qa_resource_payment_correction.py
```

Then in `src/5_estimate_profit_shifting.py` set `RUN_DATASET` to one of
`"disaggregated" | "excl_resource" | "incl_resource" |
"excl_resource_floored" | "excl_resource_floored_cat2" |
"excl_resource_floored_cat3"` and run. The script auto-picks the right
profit / tax / ETR / output-folder via the `DATASET_CONFIGS` dict at the top.

## Hand-curated reference tables (in `data/raw/`)

- `manual_resource_revenue.csv` — resource government revenue (USD bn, 2016–22) by `source_iso3 × commodity × year`, split into `frac_pre_profit / frac_post_profit / frac_equity` with a `domestic_share`. Sources in `manual_resource_data_sources.md`.
- `resource_profit_tax_rate.csv` — effective extractive profit-tax rate by `source_iso3 × commodity` (statutory CIT fallback). Sources in `manual_resource_data_sources.md`.
- `manual_foreign_hq_shares.csv` (2026-07-21) — hand-curated **foreign HQ-country splits** per `source_iso3 × commodity (× year)`, for countries whose foreign take would otherwise be spread by the generic global Orbis HQ-share table even though the actual operator consortium is documented (SSD/SDN → CNPC/Petronas/ONGC, GNQ → US majors, BWA → De Beers/Anglo (GBR), BRN → Shell/Total). Weights within the foreign slice only; `domestic_share` still carves out the NOC. Sources inline in the file's `source_note` column.

## HQ-share cascade & auditability (2026-07-21)

`1_8`'s foreign split of every distributed (manual/GRD) total now cascades
**EITI-bilateral + operator-P2G shares > `manual_foreign_hq_shares.csv` > generic
global Orbis table**, and every panel row carries `hq_share_basis`
∈ {`domestic`, `eiti_bilateral`, `eiti_operator`, `manual_foreign`, `generic_global`}.
The GRD tier now receives the EITI/operator override too (previously only the
manual tier did). EITI rows outside the 2016–2022 window are excluded from the
**panel** (they can never match a CbCR cell), but near-window rows (±3 years,
i.e. 2013–2015 / 2023–2025) still feed the **gap-year extrapolation** (2026-07-22,
user request: EITI 2015 is a good guess for a missing 2016, EITI 2023 for a
missing 2022). They join the take-average/structure base; the profit scaler is
anchored on in-window covered years only (previously out-of-window years entered
the profit mean as zeros, inflating the scaler). A country covered ONLY outside
the window (e.g. Solomon Is., EITI 2012–13) gets an unscaled carry into gap years
within 3 years of its coverage.

Script 4 writes `data/intermediate/extractive/resource_correction_unmatched_cells.csv`
— every `(iso_parent, iso_partner, year)` correction cell that found **no CbCR
line** and was therefore silently lost by the left merge (the "correction lands
on a non-existing line" failure mode). Watch its $ totals in the run log: foreign
volume there means the payment was attributed to an HQ with no line in that
source country while the HQs that actually book the resource profits keep them
uncorrected — fix by adding a row to `manual_foreign_hq_shares.csv`.

## Headline totals (2016–2022, $ bn — as of the 2026-06-30 re-run; rerun script 4 to refresh)

| Quantity | Total |
|---|---|
| Σ reported profit | 38 488 |
| Σ reported cash tax | 8 264 |
| Σ `profit_loss_excl_resource` | 35 211 (= reported − $3 277 base) |
| Σ `income_tax_paid_on_cash_basis_excl_resource` | 7 109 (= reported − $1 155 tax-dedn) |
| Σ `profit_loss_incl_resource` | 40 115 (= reported + $1 627 pre) |
| Σ `income_tax_paid_on_cash_basis_incl_resource` | 9 891 (= reported + $1 627 pre) |
| Σ `actual_resource_contribution_usd` (pre+post+equity) | 4 049 |
| Σ `profit_loss_excl_resource_floored_cat1` | 34 721 (= excl − $489 floor add-on) |
| Σ `profit_loss_excl_resource_floored_cat2` | 35 171 (= excl − $39 floor add-on) |
| Σ `profit_loss_excl_resource_floored_cat3` | 35 200 (= excl − $11 floor add-on) |

> The floor add-on is the shortfall of the state's **total** resource take
> (pre + post + equity), assessed on the whole resource sector **in aggregate**
> (summed across commodities per `(source, hq, year)`), below the IGF-ATAF
> minimum — not the shortfall of pre-profit royalties alone, and not
> commodity-by-commodity. It is an annual obligation (no netting across years),
> so a jurisdiction that over-collects in aggregate in some years can still
> show an add-on in shortfall years (e.g. China nets to ~$0 only if bumper and
> shortfall years are pooled; per-year it is ≈$120B under the price-based cat1).

## Known limitations / TODO

- **Gulf-NOC `frac_post_profit` retune (mostly done).** A high `frac_post` grosses up into a large `resource_profit_base = max(post/rate, equity)` and pushes `profit_loss_excl_resource` negative. ARE/KWT/IRN/LBY were retuned toward `frac_equity` in 2026-05; **SAU was retuned 2026-06 to 0.25/0.20/0.55 (pre/post/equity)** — its stripped base fell ~31% (≈$1,102B → $761B) and the SAU `excl_resource` aggregate rose from ≈$124B to ≈$464B. Remaining higher-`post` candidates to review: **OMN (0.30), DZA (0.30), QAT (0.25), BHR (0.25)**. Note the per-row cap (`base ≤ reported profit`) already prevents most positive-profit cells from going negative; the residual negatives are `P ≤ 0` cells the split can't fix.
- ~13 % of Orbis entities have no revenue figure (financials batches 33/35/36/38/39/42 missing from the pull) — the `in_cbcr_universe` flag falls back to the `n_subsidiaries ≥ 2` rule for those.
- ~98 k EITI raw records (≈ 18 % of value) dropped for lack of a country/year link — recoverable via `organisation.summary_data`.
- **Manual-table sourcing pass (2026-06):** Kuwait, UAE, Qatar, Algeria, Oman, Libya (IMF Article IV / national budgets), China (NBS resource tax + SOE income-tax + MoF dividends), South Africa (SARS MPRR + mining CIT), Australia (state royalties + ATO company tax + PRRT), Canada oil&gas (StatCan), Mexico (Pemex 20-F), Morocco (OCP IFRS), India coal (PIB/Coal India), and Russia equity (Gazprom/Rosneft dividends) are now sourced — see `manual_resource_data_sources.md`. **Still NOT sourceable (kept as estimates / flagged for manual):** Turkmenistan (no fiscal data), Venezuela 2019–22 (post-sanctions, untraceable), Bahrain, USA sector CIT (royalty sourced via ONRR, CIT not), Brazil oil&gas private-operator CIT, India non-fuel-mineral private-miner CIT + dead rent, China 2017 SOE dividends, Canada minerals annual series, Laos, Lesotho.
