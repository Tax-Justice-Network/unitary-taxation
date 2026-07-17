# Formulary apportionment without ignoring the extractive sector

## Context / Purpose

Running unitary taxation estimates on CbCR data without considering that it includes the extractive sector results in poor estimates for those countries that are currently heavily dependent on resource revenue: for many of these countries, a large part of the reported profits is due to the resources extracted in the country. If profits are then allocated by a formula not considering the extractive-based profits, and allocated away from the resource-intensive country, the result is an inappropriate loss estimate.

These loss estimates are not the effect of a flawed policy proposal or flawed data — they are the result of a mismatch between the proposal (set up for the part of the business that is *not* generating value through resource extraction) and the data (including part of the profit and taxes related to that sector). To obtain valid estimates, we have two ways forward:

1. We correct the data, removing resource-driven value and tax payments, and run our usual formulary apportionment on that part of the multinational activity that is not driven by resources. Note that this includes resource-rich sectors, however only *after* deducting the profits that are based on resources and the associated taxes or other government payments.
2. We adjust the proposal to include value generation from resource extraction. This also requires correcting the CbCR data, since CbCR only includes the resource value that stays in reported profits and taxes after all resource-related pre-profit payments (mainly royalties and extraction licences) have been deducted.

We do both, and a combination thereof.

## Two routes, one main specification

The two routes above map onto the code as follows. Both start from the same
disaggregated CbCR panel and the same resource-payment panel; they differ only
in how the profit/tax columns are adjusted before the (identical) unitary-
taxation step is run.

- **Route A — correct the data (MAIN specification).** Three scenarios that
  *strip* resource value out of the profit pool before UT. This is the headline
  deliverable (scripts `7_three_dataset_comparison.py`,
  `9_three_scenario_figures.py`, `9b_country_examples.py`, output folders
  `output/three_scenarios/` and `output/comparison/`).
- **Route B — adjust the proposal (ALTERNATIVE / backup).** Two scenarios that
  *add a resource factor* to the apportionment formula instead. Kept as a
  sensitivity / backup framing — present in `8_five_scenario_report.py` and the
  `cbcr_main_incl_resource.csv` dataset, but **not** the main specification.

All five scenarios are computed together by `8_five_scenario_report.py`
(`output/five_scenarios/`); the focused three-scenario scripts reuse its
machinery and restrict to Route A.

## Main specification — three scenarios (Route A)

We compare three scenarios.

### Scenario 1: Baseline

- **Purpose:** comparison with our other estimates and the existing literature.
- **Method:** run the UT / FA estimates on CbCR data as-is, ignoring resource-related profits and taxes.

### Scenario 2: UTFA excluding resource-related profits and taxes

- **Purpose:** we acknowledge that each resource-rich country has its own institutional-specific way of capturing resource rents. We consider the resource capture as a step that has *happened before* UT, and remain agnostic about how, or how much, countries should capture. We just estimate the effects of UT on any profit that is not resource-related.
- **Method:** we deduct the part of the profits recorded in the resource country, and of taxes paid there, that is resource-driven. We get resource-related tax payments on profits from EITI data (and, where this is missing, manually obtained data) on resource-related payments to governments. We infer the resource-related profit base from the resource-related taxes on profit and the applicable rates (sourced from EITI documents or manually). For countries with equity participation, we deduct either the profit base inferred from resource-related CIT payments *or* the state-equity income — whichever is larger. We do *not* deduct both: if there are taxes on resource-related corporate income, these have usually already been paid on the state's equity share, so taking the implied tax-derived profit base *and* adding the equity income would double-count. We adjust all ETRs based on these new profit and tax data — specifically, the non-resource ETR family is recomputed once on the resource-corrected `(profit, tax)` pair and carried into scenarios 3 and 4 unchanged.

### Scenario 3: UTFA excluding resource-related profits and taxes with a minimum resource capture

- **Purpose:** like scenario 2, we assume that governments can capture whatever they are capturing already. However, we set a *minimum* resource-rent capture that each resource-rich country is allowed. That minimum is calculated from the IGF/ATAF (2022) "variable royalties" schedule.
- **Method:** we calculate corrected profits and taxes after resource capture as described for scenario 2. In addition to the existing capture, we calculate the minimum capture per country based on IGF/ATAF (2022). If that minimum exceeds the actual capture, we assign the top-up to the state with "too little" capture and deduct the additional royalty from the multinational's profit pool (treating it as a pre-profit cost; the tax line is unchanged). To construct the minimum capture, we use the IGF/ATAF "category 1" variable royalty — taxing gross resource revenues with progressive tax rates between 1% and 10% (`CAT1_FLOOR`/`CAT1_CAP` in `4_correcting_cbcr_for_resource_payments.py`), scaled to the resource-type-specific price level. (The cap was set to 10% so China's price-driven 2022 floor lands "a little positive" without a large overshoot; Burkina Faso and the other low-income "wins only with the floor" cases remain net revenue winners at these bounds.) The approach is configurable in rates and thresholds, and we also compute categories 2 and 3 from the paper in parallel for sensitivity. To assign the additional state capture to multinationals from a certain country, we use Orbis ownership data via the bilateral `(source country – HQ country – resource type)` share — the share of source country *S*'s commodity-*c* activity owned by parents in country *C* — with a global per-(HQ, commodity) fallback for source-commodity-year cells where Orbis under-represents the locally incorporated subsidiaries of foreign IOCs. In addition to the gains/losses from UT, we report the add-on revenue from the minimum capture for the countries where it is relevant, as a separate stream alongside UT-derived revenue.

## Alternative / backup specification — resource-factor scenarios (Route B)

These two scenarios are kept as a sensitivity and backup framing, **not** the
main specification. Instead of stripping resource value out of the pool, they
*add a resource factor* to the apportionment formula and let UT substitute for
the existing royalty / CIT / equity capture. Both run on
`cbcr_main_incl_resource.csv` (where pre-profit resource payments are added back
to profit) and use the per-parent α-blend so the resource factor only bites to
the extent a multinational is actually resource-intensive.

### Scenario 4: Adding a resource factor to UT / FA (30% within the 5-factor formula)

- **Purpose:** we treat resources as an input factor / economic-activity factor on the same footing as sales, assets, or employment. The resource factor is, however, included only to the extent the multinational is actually resource-intensive — non-extractive industries effectively keep their usual formula, and resource-intensive multinationals get the resource factor in proportion to how resource-intensive they are. For the resource share, we assign 30% to resource use and allocate the remaining 70% with the usual formula factors. All other resource-related payments to governments are substituted by the revenue generated through the formula. The percentage allocation between resource and non-resource can be calibrated such that most countries get a similar state capture as before.
- **Method:** we first create a CbCR profit variable *before* resource-related payments — i.e., we add back all payments made to governments before profit (royalties etc.). We calculate a resource factor as the gross revenues of extracted resources by source country and commodity, multiplied by the source-specific Orbis HQ share (the bilateral `(source, HQ, commodity, year)` share, with a global per-(HQ, commodity) fallback where Orbis is thin). We then determine, per multinational parent *P*, the share α[*P*] of *P*'s reported CbCR revenue that is resource-driven, using `α[P] = Σ resource_factor[P, ·, ·] / Σ total_revenues[P, ·, ·]` (capped at 1). Each parent's profit is allocated as a weighted blend: a share α[*P*] is allocated by the 5-factor formula (with the resource factor at 30% within that formula), and the remaining (1 − α[*P*]) is allocated by the conventional 4-factor formula. Non-extractive MNEs get α ≈ 0 and remain on the 4-factor formula; resource-intensive MNEs pick up the resource factor in proportion to α. We compare the revenue impact against the previously captured tax and resource payments per country.

  Note: even at α = 1 and the resource weight = 1 (the entire profit pool of resource MNEs allocated by the resource factor), the new system can only capture *profit × CIT* (~25% of the apportioned profit pool). Royalties, equity income, and corporate income tax in the current regime together extract a much larger share of resource value, much of it *pre-profit*. The new system therefore cannot mechanically replicate every dollar of current resource capture in revenue terms; in the calibration table we report this ceiling explicitly, alongside the recovered amount per source country.

### Scenario 5: Resource as an additional equal-weight factor

- **Purpose:** a variant of scenario 4 that, instead of fixing the resource weight at 30% within the 5-factor formula, treats resources as simply *one more factor* on equal footing with the family's existing factors. This is the most generous treatment of resource source countries within the resource-factor route.
- **Method:** identical α-blend machinery as scenario 4, but the primary 5-factor weights give the resource factor an equal share alongside the others, calibrated to each formula family — e.g. for the SOTJ default, three equal factors (employees, payroll, resources) at 1/3 each; for CCCTB, four equal factor groups at 25% each; for three-factor, four equal factors at 25%; for double-weighted sales, sales stays double-weighted (0.2 / 0.4 / 0.2 / 0 / 0.2). As in scenario 4, the blend is applied only to the extractive share α[*P*] of each parent's profit. See the `*_resource_alpha_equal` formulas in `5_estimate_profit_shifting.py`.

## Where each scenario is produced

| Scenario | Route | UT dataset (`RUN_DATASET`) | Formula family used |
|---|---|---|---|
| 1 — Resources ignored (baseline) | A (main) | `disaggregated` | 4-factor (SOTJ / CCCTB / three-factor / double-weighted sales) |
| 2 — Resources excluded | A (main) | `excl_resource` | 4-factor |
| 3 — Resources excluded + minimum-royalty floor | A (main) | `excl_resource_floored` (+ `floor_add_on_cat1` reported separately) | 4-factor |
| 4 — Resource factor, 30% in 5-factor | B (alternative) | `incl_resource` | 5-factor `*_with_resources_30pct` / `*_resource_alpha_*` |
| 5 — Resource as equal-weight factor | B (alternative) | `incl_resource` | 5-factor `*_resource_alpha_equal` |

`8_five_scenario_report.py` builds all five together (`output/five_scenarios/`).
The focused three-scenario deliverable (Route A only) is
`7_three_dataset_comparison.py` (tax-base view), `9_three_scenario_figures.py`
(figure deliverable), and `9b_country_examples.py` (Chad / South Sudan /
Burkina Faso examples). All UT runs use reported-only data
(`is_distributed == 0`).

## Additional sensitivity: loss consolidation (zero tax on reported losses)

This is an **additional estimate, not a change to the main specification**, produced
ex-post by `src/9i_loss_floored_sensitivity.py` (it reads the per-row `misalignment__*.csv`
outputs of script 5 and changes nothing in the pipeline).

**The issue.** The UT revenue gain is valued straight off the misalignment with no flooring
of reported profit at zero. A partner cell that currently reports a **loss** (`reported < 0`)
and is allocated positive profit under UT is credited
`(theoretical − reported) × loss_rate = (theoretical + |loss|) × loss_rate`. That treats the
reported loss as a **refund position**. In reality a loss generates **no tax** (rate on
negative profit is 0, not negative), so the correct gain is `theoretical × loss_rate` — the
`−X → 0` loss-recovery yields no revenue.

**The fix is on the rate, not the base.** The change in taxable profit
(`theoretical − reported`) is **left unchanged** (profit genuinely moves). Only the
**revenue** uses a zero tax rate on negative pre-UT profit. The correction is therefore
`Σ_cells(reported<0, gainer) |reported| × loss_rate`, subtracted from each country's
`revenue_gain_from_ut`. It lands **only on the loss-reporting countries** (the pool is
already net, so every country's allocation already reflects the smaller pool — no extra
haircut is needed elsewhere).

**Magnitude** (headline `sales_employees_destcombined`, reported, excl-resource,
loss-CIT/gain-ETR, 2016–2022): ≈ $215B, ≈10% of winners' gains, concentrated in investment
hubs (~$86B) and high income (~$73B) — including conduits (Luxembourg, NL, HK) that report
losses and otherwise appear as spurious UT *winners* — with low income only ≈ −$6B.

**Relation to WIFO (2026) — important caveat.** We label this **"loss consolidation"**
(the term readers ask about), but it is a **partial, static, CbCR-aggregate, zero-carry-
forward** view of the effect. WIFO measures the proper effect at the **firm/group level** and
**dynamically** (loss carry-forward across years). Our measure (a) misses losses netted away
inside net-positive aggregate cells and (b) ignores carry-forward value (under the current
system losses are carried forward/backward, so they are not truly worth zero) — so it is an
**upper bound** on the *permanent* effect; the gap to the headline is largely **transitory**.
The ≈10% proximity to WIFO's <10% of tax base is a coincidence of magnitude, not the same
construct. It is also **exact only for inf-threshold specs** (no `adjust_misalignment`
rescaling); for the 15%-haven-gated specs it is approximate. Every table note must carry this
caveat so the figure is not read as a firm-level loss-consolidation estimate.

Output: `output/unitary_taxation/across_samples/loss_consolidation_sensitivity/`.

## Sample exclusions (stateless entities and aggregate codes)

The pipeline drops partner rows in exactly one place — `1_clean.py`, right after
the OECD CbCR file is pivoted to wide form — for four counterpart codes:

| Code | Meaning | Why dropped |
|---|---|---|
| `STLS` | **Stateless entities** | Sub-entities the parent could not assign to any tax jurisdiction. Their profit/activity has no real location, so there is no geographic basis for reallocating it; the OECD flags it as a source of double counting with partner rows. |
| `W` | World (all partners) | The reporter's own grand total — keeping it would double-count every partner row. |
| `ANT_F` | Netherlands Antilles | Dissolved in 2010; no longer a jurisdiction. |
| `BVT` | Bouvet Island | Uninhabited dependency, not a real market. |

**Stateless entities are removed entirely and their profit and economic activity
are *not* redistributed to any country.** This is deliberate, and serves two
purposes. First, unlike the `WXD` / continent residual codes — which *are*
disaggregated to specific partners in `2_disaggregate_aggregated_values.py`
because they represent activity in real but unreported geographies — stateless
profit belongs to no jurisdiction, so there is no geographic basis on which to
reallocate it. Second, the OECD flags stateless income as a known source of
**double counting** with the partner rows (the same profit can appear both under
`STLS` and under a named partner), so dropping it is part of how the pipeline
deals with duplicate profits. The misalignment/UT method then operates only on
the profit booked in identifiable jurisdictions.
