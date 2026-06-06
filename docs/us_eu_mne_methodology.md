# US & EU multinationals — profit-shifting sub-project ("The quiet tax war")

Methodology and methodological choices for the home-group unitary-taxation
sub-project in `src/us_only/`. It runs the project's UT machinery on a single
home group of multinationals and produces the figures/tables in
`output/<topic>/` (mirrored to the TJN "2605 The quiet tax war" `3_output`
folder). This note documents every choice and advance made; it is the companion
to `docs/pcbcr_us_noncompliance.md` and `docs/eu_profit_shifting_us_mnes.md`.

## Scripts

- `src/us_only/estimate_us_multinationals.py` — self-contained sibling of
  `src/5_estimate_profit_shifting.py`. Same UT formulary-apportionment machinery,
  restricted to one home group; produces the full per-spec outputs plus the
  bespoke figures below.
- `src/us_only/combine_us_eu.py` — cross-group figures (US vs EU) and the German
  Kommunen-loss-vs-debt contrast.
- `src/us_only/pcbcr_compliance_chart.py` — Fair Tax Foundation pCbCR compliance
  chart (separate note).

## Run parameters (environment variables)

| Var | Values | Effect |
|---|---|---|
| `HOME_GROUP` | `USA` (default) / `EU27` | Parent jurisdictions kept (`PARENT_SET`); output topic (`us_multinationals` / `eu_multinationals`); figure label `HOME_LABEL` (US/EU). UK/GBR deliberately excluded — bad reporter 2017–2022. |
| `ETR_MAX` | `inf` (default) / `0.15` | Minimum-ETR threshold for counting over-reporting as shifting. `inf` → all misalignment captured, no rescale; `0.15` → only profit shifted to sub-15%-ETR destinations counts (haven-only), with balancing rescale on. `0.15` writes to an `_etr15`-suffixed topic so both coexist. |
| `REPORTED_ONLY` | `0` (default) / `1` | `0` keeps the disaggregated partner cells (the full footprint); `1` is a no-imputation sensitivity (`_reported` topic). Defaulted **off** here (unlike script 5) because the disaggregated dataset's purpose is to include those cells. |
| `RUN_DATASET` | `disaggregated` | Baseline disaggregated CbCR only. |
| `FIG_FORMULA` | `ccctb` (default) / `employees_payroll` | Apportionment formula the bespoke figures read and are labelled with. `ccctb` writes the established topics; `employees_payroll` (SOTJ: 50% employees, 50% payroll) writes a parallel `_sotj`-suffixed topic so both formula sets coexist for comparison. The UT loop computes every formula regardless — this only selects which spec the figures use. |

Run order for the full set:

```
HOME_GROUP=USA  python src/us_only/estimate_us_multinationals.py
HOME_GROUP=EU27 python src/us_only/estimate_us_multinationals.py
HOME_GROUP=USA  ETR_MAX=0.15 python src/us_only/estimate_us_multinationals.py
HOME_GROUP=EU27 ETR_MAX=0.15 python src/us_only/estimate_us_multinationals.py
python src/us_only/combine_us_eu.py                 # inf
ETR_MAX=0.15 python src/us_only/combine_us_eu.py    # 0.15
```

For the **SOTJ** (`employees_payroll`) parallel set, re-run the same six commands
with `FIG_FORMULA=employees_payroll` prefixed; outputs land in the
`*_sotj`-suffixed topics (`us_multinationals_sotj`, …, `combined_us_eu_sotj`,
plus the `_etr15_sotj` variants) alongside the CCCTB ones.

## Core method

- **Parent filter.** UT misalignment is computed per `iso_parent`, so keeping
  only `iso_parent ∈ PARENT_SET` yields a clean view of that group's MNEs.
- **Misalignment.** `misaligned_profit = reported − theoretical`, where
  theoretical = the partner's share of the parent's formula factors × the
  parent's worldwide profit pool (floored at 0). Positive = over-reported
  (profit shifted *in*, a haven); negative = under-reported (profit generated
  there but booked elsewhere).
- **Formulas.** Headline = `ccctb` (⅓ sales, ⅓ assets, ⅙ employees, ⅙ payroll);
  `employees_payroll` (SOTJ: 50% employees, 50% payroll) produced as a parallel
  set via `FIG_FORMULA=employees_payroll` (the `_sotj` topics) for comparison.
  Switching from SOTJ to CCCTB notably flattens the **2021 US-as-haven spike**
  for EU MNEs (EU→US bilateral inflow ≈ $4.7bn under SOTJ vs ≈ $0.5bn under
  CCCTB): CCCTB credits the US's large real sales/assets, so that 2021 profit
  reads as earned rather than shifted in.
- **ETR.** "ETR a group pays in a jurisdiction" = the partner's average ETR
  (`etr_average_corrected`, 5-year rolling, built by `src/_etr_construction.py`).
  This is the column used for both the <`ETR_MAX` haven test and the ETR shown in
  the figures. Net misalignment (profit) is ETR/rate-independent.
  - **US-domestic-ETR override (US sample only).** For `HOME_GROUP=USA`, the US
    jurisdiction's ETR is overridden at load time to its **domestic** ETR
    (`etr_domestic_corrected` — the rate US MNEs pay on their US operations)
    instead of the blended average, which also reflects foreign-owned firms in
    the US. The US domestic ETR is actually *higher* (≈27% vs ≈23% period mean;
    both above 15% every year, so the US is not a sub-15% haven either way) — the
    override mainly raises the ETR shown for the US in the figures. Applied to
    the US partner rows, so it flows into both the haven test and the figures.
- **Tax revenue.** From the `loss_cit_gain_etr` country file: tax revenue **lost**
  = under-reported base × the losing country's statutory **CIT**; tax revenue
  **gained** = over-reported base × the **ETR** the MNEs pay in the gaining
  jurisdiction.
- **Bilateral attribution.** Each sufferer's missing profit is attributed across
  the jurisdictions that over-report, in proportion to their over-reporting
  (the canonical bilateral method), restricted here to one parent group.

## Framing choice (winners/losers)

Reframed in **current-profit-shifting** terms, not the UT-reform counterfactual:
**winner = haven** receiving illegitimate profit (net-positive misalignment);
**loser = victim** whose earned profit is booked elsewhere (net-negative). Same
quantity, read in status-quo terms.

## Figures (per home group, both ETR configs)

- **Winners/losers aggregated lines** (`eu_net_misalignment_aggregated*`) — two
  lines, group totals over time; all-EU and excl-Luxembourg; employees_payroll
  and CCCTB.
- **Profit-shifting gap** (`eu_profit_shifting_gap*`) — few havens over-report
  (up, labelled with ETR) vs the many drained (down); excl-LUX/MLT and CCCTB.
- **ETR scatter** (`eu_profit_vs_etr_scatter*`) — net misalignment vs ETR;
  havens cluster at low ETR.
- **Missing-from-EU shares** (`eu_missing_profit_shares*`) — top-15 destinations
  by share of EU-missing profit, **bars coloured by the ETR each destination
  charges** (the long "Other" tail is dropped); plus a **yearly 100%-stacked
  top-10 distribution** (`eu_missing_profit_shares_yearly*`).
- **Tax-revenue gap** (`eu_tax_revenue_gap*`) — same gap in tax terms (loss ×
  CIT vs gain × ETR); per-year and a **cumulative** running-total variant; both
  excl-LUX/MLT and CCCTB.
- **Per-EU-country tax loss** (`eu_country_tax_loss*`) — tax revenue each EU
  country loses, cumulative. **Luxembourg & Malta are kept but flagged (amber)
  and explained** in the note: they top the list only because of large 2021
  reported book losses, not genuine draining (they are really low-ETR havens).
- **Tax loss over time** (`eu_tax_loss_cumulative*`) — the EU tax-revenue loss
  just aggregated over time: per-year bars + cumulative running-total line, with
  the 2022 cumulative total in the title and the TCJA marker.
- **Germany by government level** (`germany_tax_loss_by_level*`) — see below.
- **Kommunen loss vs daycare** (`germany_kommunen_loss_vs_daycare*`) and **Länder
  loss vs schools** (`germany_laender_loss_vs_schools*`) — per-level benchmark
  contrasts; see "Per-level benchmark figures" below.
- **Home-share / EU-share** (`home_share_activity_vs_profit*`,
  `eu_share_activity*`) — home region's (or EU-27's) share of worldwide
  employees / tangible assets / payroll / sales over time. Real economic
  activity. Restyled to the house style: The Left palette, **y-axis fitted to
  the data** (non-zero start, so the change is legible), and the single **"Tax
  Cuts and Jobs Act" 2017 marker** (shared `add_tcja_marker` helper).

Combined (`output/combined_us_eu*/`): US-vs-EU total profit shifted + as a share
of profit; US-vs-EU home-share; the Germany Kommunen-loss-vs-needs (daycare) and
all-MNE Kommunen-loss-vs-debt contrasts.

## Germany federal / Länder / Kommunen split

The German loss is split by the **statutory composition** of its combined
corporate rate (the methodologically consistent way to split a rate × base
loss), computed from Germany's actual combined rate `r` in the data:

- Körperschaftsteuer 15% → 50% Bund / 50% Länder (Art.106(3) GG)
- Solidaritätszuschlag = 5.5% × KSt = 0.825pp → Bund
- Gewerbesteuer = `r − 15.825pp` → Kommunen, **net of the Gewerbesteuerumlage**
  (≈ Umlagesatz/Hebesatz ≈ 8.6% at avg Hebesatz ~407% / Umlagesatz ~35%),
  redistributed Bund/Länder ≈ 41/59.

→ ≈ **Federal 30% / Länder 28% / Kommunen 43%** (confidence: medium; constants
in `GERMANY_LEVEL_SHARES`/the decomposition are nationwide approximations).
Figures are **per-year** (bars) with the **cumulative** total in the title.

**Better data (optional):** exact by-level shares can be taken from Destatis
*Steuereinnahmen* (KSt 50/50) + *Realsteuervergleich* (GENESIS 71231, the
Gewerbesteuerumlage) or OECD Revenue Statistics (corporate income by level);
the Körperschaftsteuerstatistik does NOT carry a level split.

## Per-level benchmark figures (Kommunen vs daycare; Länder vs schools)

Produced **per home group** in the estimate script's Germany section, so the
all-MNE versions land in `output/all_multinationals/figures/` alongside the
US/EU ones. Both convert the modelled cumulative loss USD→EUR at
`USD_PER_EUR=1.10`. The matching tasks follow the German competence split —
**daycare is a municipal (Kommunen) task, school buildings/education a Länder
matter** — so each level is benchmarked against the spending need it owns:

- **`germany_kommunen_loss_vs_daycare*`** — cumulative **municipal (Kommunen)**
  loss vs the **daycare/Kita investment backlog** (€10.5bn, KfW Kommunalpanel) —
  the municipal spending need, as the headline comparison (bars). Total
  municipal debt (€154.6bn) is *not* drawn here (it would dwarf the bars); the
  debt contrast lives in the combined `germany_kommunen_all_loss_vs_debt*`.
  All-MNE loss ≈ €40bn ≈ 377% of the daycare backlog on the ∞ basis.
- **`germany_laender_loss_vs_schools*`** — cumulative **state (Länder)** loss vs
  the **school-building investment backlog** (€67.8bn, KfW Kommunalpanel).

The combined `germany_kommunen_loss_vs_needs*` (cross-group US/EU/All bars)
references the daycare backlog only; `germany_kommunen_all_loss_vs_debt*` remains
the cross-group all-MNE debt contrast.

## Data fix — Romania 2022 (in `1_clean.py`)

The raw OECD CbCR reports an impossible **492m employees** for Romanian MNEs in
2022 (incl. 105m in the US, 83m in Israel) and ~1,600× inflated payroll, with
collapsed/negative assets — the whole 2022 submission is corrupt (verified
against the raw file; not a pipeline artefact). `1_clean.py` now **drops Romania
2022** (treated as a non-report). This removed a spurious 2022 cliff in the EU
home-share and EU 2022 employees-based estimates.

## Output mirroring

Every run mirrors its `figures/` and `tables/` (excluding the heavy regenerable
`tables/disaggregated/` per-spec CSVs) into the shared
`…/2605 The quiet tax war/3_output/` under **`2_figures` / `1_tables`**, flat,
with a collision-proof prefix: `usa_` / `eu27_` (inf) and `usa_etr15_` /
`eu27_etr15_` (0.15); combined figures get `combined_` / `combined_etr15_`.

## Caveats

- **ETR max = ∞ vs 0.15.** ∞ counts all misalignment (any destination ETR); 0.15
  counts only sub-15%-ETR-haven shifting. Both are produced; ∞ is the headline.
- **Luxembourg & Malta** show as net-negative ("victims") under any formula
  because of large 2021 reported book losses (plausibly TCJA-driven
  repatriation/restructuring) — they are really low-ETR havens. Excl-LUX/MLT
  variants are provided; the per-EU-country tax-loss table lists LUX #1 for this
  reason (Germany is the real top victim).
- **2021** is anomalous for US MNEs (profit surge + repatriation): US profit
  share spikes to 72%, and the US is a profit *destination* only in 2021 (a net
  origin every other year).
- **Currency.** Model is USD; German debt is EUR — converted at a flat
  `USD_PER_EUR=1.10` for the Kommunen contrast (scale only).
