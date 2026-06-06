# How US multinationals shift profit within the EU (current system)

Supporting analysis and figures for the argument that US multinationals book
their EU profit in a handful of low-tax havens rather than where it is earned,
and that this gap has widened over 2016–2022. All figures are produced by
`src/us_only/estimate_us_multinationals.py` (sections [6B]–[9c]) on the baseline
disaggregated CbCR, **US parents only**.

## Framing (status quo, not the UT counterfactual)

We describe **current** profit shifting, not who would gain/lose from a unitary
taxation reform:

- **Winners = havens.** EU jurisdictions that *receive* illegitimate profit —
  they report more US-MNE profit than real activity warrants (**net positive
  misalignment** = reported − formulary-implied profit > 0). The few.
- **Losers = victims.** EU jurisdictions whose profit is *generated there but
  booked elsewhere* (**net negative misalignment** < 0). The many.

Net misalignment is the same quantity used throughout the project, read in
profit-shifting terms. Headline formula = employees+payroll (50/50); a CCCTB
variant (1/3 sales, 1/3 assets, 1/6 employees, 1/6 payroll) is produced
alongside and tells the same story (havens even more concentrated in IRL/NLD).

## Headline findings (employees+payroll, 2016–2022)

- **A handful of havens absorb the over-reported profit.** Ireland (period ETR
  ≈ 8%) and the Netherlands (≈ 5%) dominate; Belgium, Cyprus, Hungary are minor.
- **The many lose.** Germany, France, Italy, Spain, Poland, Sweden are
  under-reported, and they pay **normal ~17–21% ETRs** — i.e. real, normally
  taxed profit is what gets drained.
- **The gap has widened:** profit over-reported in EU havens **$60bn → $121bn**;
  profit shifted out of the many **$14bn → $74bn** (2016 → 2022). Excluding the
  two loss-distorted havens (LUX, MLT): **$60bn → $116bn** up, **$11bn → $64bn**
  down.
- **Profit follows the lowest rate.** The ETR scatter shows the big haven
  bubbles (IRL, NLD) sit at the *bottom* (lowest ETR) while victims cluster at
  normal ETRs — a clear "book it where the tax is lowest" pattern.

## The US is normally an *origin*, not a destination

A related finding (answers "why is the US not a 2022 destination?"): under
employees+payroll the **US domestic row is net-negative in every year except
2021** — US MNEs persistently report *less* profit at home than their US
employees+payroll imply, leaking it to havens:

| Year | US reported $bn | US formulary-implied $bn | Net |
|---|---|---|---|
| 2016 | 226 | 488 | −262 |
| 2017 | 532 | 900 | −368 |
| 2018 | 387 | 602 | −215 |
| 2019 | 337 | 613 | −275 |
| 2020 | 875 | 1,176 | −301 |
| **2021** | **1,854** | 1,770 | **+84** (only year as destination) |
| 2022 | 1,349 | 1,546 | −197 |

2021 is a one-off (post-COVID profit surge + TCJA repatriation timing) when
reported US profit briefly exceeded its formulary share. So the "US destination"
seen in the all-years bilateral chart is essentially a 2021 artefact; by 2022 the
US reverts to being a net origin.

## Caveat: Luxembourg & Malta

Under any formula, **LUX and MLT classify as net-negative ("losers") only
because of large 2021 reported book losses** — their 2–4% ETRs show they are
havens. They are annotated as such in the scatter, and excl-LUX&MLT variants of
the gap chart are provided so the 2021 spike and misclassification disappear
without changing the few-vs-many conclusion.

## Figures (in `output/us_multinationals/figures/`)

- `eu_profit_shifting_gap_2016_2022.png` — the widening gap (few havens up, many
  down), haven ETRs in the legend. Plus `_excl_LUX_MLT` and `_ccctb[_excl_LUX_MLT]`.
- `eu_profit_vs_etr_scatter_2016_2022.png` — over/under-reporting vs ETR. Plus
  `_ccctb`.
- `eu_net_misalignment_aggregated_2016_2022.png` (+ `_excl_LUX`, `_ccctb[_excl_LUX]`)
  — the same data as winners/losers lines (originally framed as the UT
  counterfactual; see code comments).
- `eu_missing_profit_bilateral_2016_2022.png` (+ `_excl_LUX`) — bilateral
  attribution of EU-missing profit to destination jurisdictions.

Data tables: `eu_profit_shifting_roles.csv` (+ `_ccctb`),
`eu_net_misalignment_by_year.csv` / `_classification.csv` (+ `_ccctb`),
`eu_missing_profit_bilateral.csv` (+ `_excl_LUX`).

## Method note

ETR = period mean of the 5-year-rolling partner ETR
(`etr_partner_median_corrected`, built by `src/_etr_construction.py`). Net
misalignment is rate-independent, so the profit-shifting figures depend only on
the apportionment formula, not the ETR spec or tax-rate mode.
