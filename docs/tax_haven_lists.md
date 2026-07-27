# Tax-haven lists

Two lists, defined in `src/config.py`, for two distinct purposes:

1. **`TAX_HAVENS_CLEANING`** (17) — García-Bernardo list, drives the cleaning correction.
2. **`TAX_HAVENS_REPRESENTATION`** (29) — GB list ∪ (CTHI-2025 Haven Score ≥ 65 AND
   inward-shifted profit in ≥2 years) ∪ manual {BIOT} (presentational).

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

## 2. Representation list — `TAX_HAVENS_REPRESENTATION` (29)

Used for the `investment_hub` income-group classification shown in figures/tables.
Feeds **no** cleaning correction — purely presentational, no effect on estimates.

**Rule (adopted 2026-07-18, replacing the 2026-07-11 "CTHI-2024>65 ∧ *pooled*
net-recipient" rule):** a jurisdiction is presented as a tax haven iff

1. it is on the **GB cleaning list** (list 1 above), **OR**
2. it has a **CTHI-2025 Haven Score ≥ 65**
   (`data/raw/country_info/tjn_cthi_2025_scores.csv`, `cthi_2025_score`) **AND** booked
   **inward-shifted profit** (`reported_profit − theoretical_profit > 0`) in
   **at least TWO years**, 2016–2022 excl 2020, on the current headline spec
   (reported-only / excl_resource / `sales_employees_destmnedds` / `domfor` ETR
   / etrmax_inf), **OR**
3. it is the **manual substance keep** (`_EXTRA_MANUAL = {IOT}`): British Indian
   Ocean Territory — unscored by CTHI, retained on substance.

   **Puerto Rico and Barbados** are GB profit centres (list 1), so the GB leg
   keeps them despite having no CTHI score. No general FSI fallback — **Saudi
   Arabia stays out** (unscored by CTHI; ~98% home-booked → **home-bias**, not a
   haven).

The "at least two years" test (condition 2) is more permissive than the old
*pooled* net-recipient test (a jurisdiction can net negative over the window and
still count) but the **2-year** threshold rejects single-year outliers — see the
Hungary note below.

`_EXTRA_CTHI_GE65_2YR_SHIFT` (condition-2 jurisdictions not already GB):

| ISO3 | Jurisdiction | CTHI-2025 Haven Score | # inward-shift years (of 6) | Max single-year shift (m USD) |
|---|---|--:|--:|--:|
| MCO | Monaco | 66 | 6 | +446 |
| PAN | Panama | 72 | 5 | +33,394 |
| CUW | Curaçao | 72 | 5 | +1,762 |
| SYC | Seychelles | 70 | 5 | +75 |
| CYP | Cyprus | 79 | 4 | +12,656 |
| ABW | Aruba | 71 | 4 | +144 |
| ARE | United Arab Emirates | 84 | 3 | +13,437 |
| LBR | Liberia | 67 | 3 | +526 |
| GGY | Guernsey | 100 | 3 | +311 |
| LIE | Liechtenstein | 67 | 3 | +253 |
| AIA | Anguilla | 100 | 2 | +35 |

**Vs the 2026-07-11 list (29):** **ADDS Liberia** (3 inward-shift years:
2018/2019/2022); **DROPS Cook Islands** (no CTHI score *and* no inward-shift
year). **Guernsey** now qualifies on outcome (CTHI 100, 3 years), no longer a
manual add. Net: 29 − COK + LBR = **29**.

**Hungary considered and EXCLUDED.** CTHI 69 with a single inward-shift year
(2016, +$4.2bn) but a large net *loser* in all five other window years
(2017 −12.4, 2018 −3.8, 2019 −0.6, 2021 −8.7, 2022 −7.1 bn; ≈ −$28bn pooled). The
2-year gate exists precisely to reject such single-year outliers — under a "≥1
year" test Hungary would enter (the only member with a single positive year);
under "≥2 years" it is the sole additional drop. **Anguilla** is the thinnest
keeper (exactly 2 years); a "≥3 years" gate would drop it next.

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
