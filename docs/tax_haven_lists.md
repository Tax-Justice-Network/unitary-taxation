# Tax-haven lists

Two lists, defined in `src/config.py`, for two distinct purposes:

1. **`TAX_HAVENS_CLEANING`** (17) — García-Bernardo list, drives the cleaning correction.
2. **`TAX_HAVENS_REPRESENTATION`** (30) — GB list ∪ (CTHI-2025 Haven Score ≥ 65 AND
   inward-shifted profit in ≥1 year) ∪ manual {BIOT} (presentational).

A third, ETR-threshold definition was **explored but not adopted**; its candidate
jurisdictions are documented at the bottom for reference.

## 1. Cleaning list — `TAX_HAVENS_CLEANING` (17)

The **exact** tax-haven list of **García-Bernardo, Janský & Zucman (2026)**, *"Did
the Tax Cuts and Jobs Act Reduce Profit Shifting by US Multinational Companies?"*,
IMF Economic Review, §4 — grouped (following Reurink & García-Bernardo 2020) into:

- **Profit centres (11)** — `_GB_PROFIT_CENTRES`: BMU, CYM, PRI, JEY, IMN, GIB, BRB, MUS, VGB, BHS, MLT
- **Coordination centres (6)** — `_GB_COORDINATION_CENTRES`: SGP, NLD, CHE, IRL, LUX, HKG

Drives the GB dividend double-counting correction in `1_clean.py` (10% of haven
profits, non-US MNCs, 2016–2019). **Changing it changes the cleaned profit
figures.** (`tax_havens` is a backward-compatible alias.)

## 2. Representation list — `TAX_HAVENS_REPRESENTATION` (30)

Used for the `investment_hub` income-group classification shown in figures/tables.
Feeds **no** cleaning correction — purely presentational, no effect on estimates.

**Rule (adopted 2026-07-18, replacing the 2026-07-11 "CTHI-2024>65 ∧ *pooled*
net-recipient" rule):** a jurisdiction is presented as a tax haven iff

1. it is on the **GB cleaning list** (list 1 above), **OR**
2. it has a **CTHI-2025 Haven Score ≥ 65**
   (`data/raw/cthi_2025_scores.csv`, `cthi_2025_score`) **AND** booked
   **inward-shifted profit** (`reported_profit − theoretical_profit > 0`) in
   **at least ONE year**, 2016–2022 excl 2020, on the current headline spec
   (reported-only / excl_resource / `sales_employees_destmnedds` / `domfor` ETR
   / etrmax_inf), **OR**
3. it is the **manual substance keep** (`_EXTRA_MANUAL = {IOT}`): British Indian
   Ocean Territory — unscored by CTHI, retained on substance.

   **Puerto Rico and Barbados** are GB profit centres (list 1), so the GB leg
   keeps them despite having no CTHI score. No general FSI fallback — **Saudi
   Arabia stays out** (unscored by CTHI; ~98% home-booked → **home-bias**, not a
   haven).

The "at least one year" test (condition 2) is deliberately more permissive than
the old *pooled* net-recipient test: a jurisdiction that received shifted profit
in some year but nets negative over the whole window still counts.

`_EXTRA_CTHI_GE65_ANYYEAR_SHIFT` (condition-2 jurisdictions not already GB):

| ISO3 | Jurisdiction | CTHI-2025 Haven Score | Max single-year inward shift (m USD) |
|---|---|--:|--:|
| PAN | Panama | 72 | +33,394 |
| ARE | United Arab Emirates | 84 | +13,437 |
| CYP | Cyprus | 79 | +12,656 |
| HUN | Hungary | 69 | +4,189 |
| CUW | Curaçao | 72 | +1,762 |
| LBR | Liberia | 67 | +526 |
| MCO | Monaco | 66 | +446 |
| GGY | Guernsey | 100 | +311 |
| LIE | Liechtenstein | 67 | +253 |
| ABW | Aruba | 71 | +144 |
| SYC | Seychelles | 70 | +75 |
| AIA | Anguilla | 100 | +35 |

**Vs the 2026-07-11 list (29):** **ADDS Hungary and Liberia** — pooled net
*losers* under the old test, but each has a positive-shift year the any-year test
catches; **DROPS Cook Islands** — no CTHI score *and* no inward-shift year (the
one manual add that failed both gates). **Guernsey** now qualifies on the outcome
rule (CTHI 100 + a +$311m year), so it is no longer a manual add. Net: 29 − COK +
HUN + LBR = **30**.

`TAX_HAVENS_REPRESENTATION_NARROW` is a **deprecated alias** of the main list.

Freezing note: the inward-shift flags were evaluated once (current headline run)
and frozen into `config.py` — safe because the list feeds no estimate. Re-derive
with the CTHI-2025 swap check (score gate ≥ 65 + any-year `reported−theoretical
> 0`) and update `_EXTRA_CTHI_GE65_ANYYEAR_SHIFT` if the data year changes.

**Propagation:** `investment_hub` is set in `1_clean.py` from this list, so a
change relabels the `wb_income_group` column baked into every downstream file.
The estimates do not depend on the label (identical numbers), but figures/tables
grouped by income group must be regenerated (re-run `1_clean.py` onward, or the
relabel) to reflect the new membership.

### `TAX_HAVENS_FUNCTIONAL` — the frozen functional haven set

Two pipeline steps use a haven set **functionally** (they change numbers, not
display): the script-2 imputed-activity **cap exemption** (2×GDP / 0.5×pop caps
don't apply to recognised havens) and the script-4 resource-dominated **ETR-floor
haven exclusion**. Both now read `TAX_HAVENS_FUNCTIONAL`, which is **frozen at the
pre-2026-07-11 representation membership** (GB ∪ CTHI ≥ 67 ∪ Cook Is / BIOT). This
keeps the representation re-definition purely presentational — in particular:

- **Saudi Arabia** must stay off the functional set (it is off the representation
  list too), so it keeps the script-4 "Saudi fix" ETR floor — haven status in the
  functional set would silently disable it;
- the six jurisdictions dropped from the representation list (Hungary, Costa
  Rica, Latvia, Lebanon, Estonia, Liberia) stay functional, so the script-2 cap
  exemption and the script-4 floor gate behave exactly as before (`9h`'s
  inflation flag also uses the functional set).

## Explored but not adopted — ETR-threshold list

An **outcome-based** alternative was considered: classify a jurisdiction as a haven
if its **effective tax rate over the whole period is below a threshold**, rather
than by García-Bernardo membership (list 1) or CTHI score (list 2). **It was not
adopted** and there is **no corresponding constant in `config.py`** — this section
is kept only as a reference / sensitivity record.

**Why not adopted.** A pure ETR cut behaves unlike a curated haven list in two
unwanted ways:

- It **drops marquee havens** whose reported ETR is not ultra-low, or whose pooled
  corrected profit is non-positive (ETR undefined): **IRL (18.5%), MLT (29%), CHE
  (10.3%), HKG (10.5%), NLD (13.1%), MUS (11.4%)**, and **LUX, GGY, COK** (undefined).
- It **adds loss-year / tiny-profit economies** that are not really havens
  (**BOL, YEM, HTI, GUY, MTQ, WLF, NRU, …**), because the ratio cannot distinguish a
  haven from a country that simply paid little tax on a small or loss-making base.

**Definition used to produce the candidates.** Pooled period-average ETR =
Σ `income_tax_paid_on_cash_basis` ÷ Σ `profit_loss_before_income_tax_corrected`
over 2016–2022, clipped to [0, 1] — exactly the `etr_average_corrected`
construction (`_etr_construction.py`) but with the window = the **entire period**.
Computed on `data/final/cbcr_main_allsubgroupsonly.csv`; jurisdictions with
non-positive pooled profit are excluded. Per-jurisdiction values are saved to
`data/intermediate/etr_period_average_by_partner.csv`.

**The three debatable CTHI jurisdictions under this definition.** Of Costa Rica,
Latvia and Lebanon (excluded from the representation list by the net-recipient
condition), only
**Latvia (9.1%)** falls under the 10% cut; **Costa Rica (10.1%)** sits just above it.
**Lebanon is excluded entirely** — its pooled corrected profit is non-positive, so its
ETR is undefined and it carries no row in `etr_period_average_by_partner.csv`.

**Counts by threshold:** `<5% → 27`, `<10% → 42`, `<15% → 59`.

**Candidate jurisdictions, pooled ETR < 10% (42)** — the `< 5%` set (27) is the
subset marked ✓ in the last column. Derived 2026-06-23; reproduce with
`python src/_build_etr_haven_list.py [threshold]`.

| ISO | Jurisdiction | Pooled ETR | <5% |
|---|---|--:|:--:|
| AIA | Anguilla | 0.0% | ✓ |
| BOL | Bolivia | 0.0% | ✓ |
| NRU | Nauru | 0.0% | ✓ |
| MTQ | Martinique | 0.0% | ✓ |
| WLF | Wallis & Futuna | 0.0% | ✓ |
| YEM | Yemen | 0.0% | ✓ |
| PLW | Palau | 0.0% | ✓ |
| GIB | Gibraltar | 0.1% | ✓ |
| MHL | Marshall Islands | 0.2% | ✓ |
| IMN | Isle of Man | 0.5% | ✓ |
| CUW | Curaçao | 1.0% | ✓ |
| HTI | Haiti | 1.4% | ✓ |
| BHR | Bahrain | 1.4% | ✓ |
| VGB | British Virgin Islands | 1.4% | ✓ |
| ATG | Antigua & Barbuda | 1.5% | ✓ |
| BRB | Barbados | 1.6% | ✓ |
| CYM | Cayman Islands | 1.6% | ✓ |
| BHS | Bahamas | 2.0% | ✓ |
| BMU | Bermuda | 2.3% | ✓ |
| PRI | Puerto Rico | 2.7% | ✓ |
| GUY | Guyana | 3.2% | ✓ |
| PAN | Panama | 3.5% | ✓ |
| SYC | Seychelles | 3.5% | ✓ |
| IOT | British Indian Ocean Territory | 3.6% | ✓ |
| LCA | Saint Lucia | 3.7% | ✓ |
| LBR | Liberia | 4.2% | ✓ |
| CYP | Cyprus | 4.8% | ✓ |
| GEO | Georgia | 5.1% | |
| JEY | Jersey | 5.1% | |
| WSM | Samoa | 6.1% | |
| FRO | Faroe Islands | 7.1% | |
| BRN | Brunei | 7.4% | |
| KWT | Kuwait | 7.8% | |
| SWZ | Eswatini | 8.2% | |
| CUB | Cuba | 8.6% | |
| GTM | Guatemala | 8.8% | |
| SRB | Serbia | 8.9% | |
| LVA | Latvia | 9.1% | |
| SGP | Singapore | 9.4% | |
| KNA | Saint Kitts & Nevis | 9.5% | |
| LTU | Lithuania | 9.8% | |
| BGR | Bulgaria | 10.0% | |

## Misalignment haven ID (script 5)

Misalignment haven identification in `5_estimate_profit_shifting.py` is
**ETR-threshold-based (15%) per parent-group cell** (relative / balanced),
independent of both jurisdiction lists above.
