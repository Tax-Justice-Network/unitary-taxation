# Tax-haven lists

Two lists, defined in `src/config.py`, for two distinct purposes:

1. **`TAX_HAVENS_CLEANING`** (17) — García-Bernardo list, drives the cleaning correction.
2. **`TAX_HAVENS_REPRESENTATION`** (29) — GB list ∪ (CTHI-2024 Haven Score > 65 AND
   net profit-shifting recipient) ∪ manual {Guernsey, Cook Islands, BIOT}
   (presentational).

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

**Rule (adopted 2026-07-11, replacing the old "CTHI ≥ 67 ∪ GB ∪ substance" rule):**
a jurisdiction is presented as a tax haven iff

1. it is on the **GB cleaning list** (list 1 above), **OR**
2. it has a **CTHI-2024 Haven Score > 65**
   (`data/raw/cthi_unilateral_cross_scores.csv`, `cthi_2024_score`) **AND** is a
   **net profit-shifting recipient** in our results — pooled net misalignment > 0
   over 2016–2022 excl 2020 on the headline spec (reported-only / excl_resource /
   `sales_employees_destcfb` / average ETR / etrmax_inf), **OR**
3. it is one of the **manual additions** (`_EXTRA_MANUAL`):
   - **Guernsey** — CTHI 100 but a small net *loser* in our results (−$5.0bn),
     kept as a classic haven regardless of its outcome sign.
   - **Cook Islands / BIOT** — not scored by CTHI (COK FSI 72), kept on
     substance as under the old rule.

   No general FSI fallback is applied to unscored jurisdictions (e.g. New
   Zealand 66, Chile 66, Malaysia 73 stay out). **Saudi Arabia was considered
   and rejected** (2026-07-11): it is unscored by CTHI, has FSI secrecy score 69
   (2022) / 70.7 (2025) (`data/raw/portal_unilateral_cross.csv`) and is a large
   net recipient (+$64.5bn) — but that excess profit is ~98% **home-booked**
   (Saudi MNEs' domestic over-booking, largely resource-related), so it is
   classified as a **home-bias** country (Table 6 set), not a haven.

The outcome condition (2) makes the list self-consistent with the estimates: every
listed haven except the Bahamas actually *receives* shifted profit in our results
(the Bahamas nets ≈ $0 in the reported sample and stays only via the GB union).
All 17 GB members were checked against condition 2: 14 pass on CTHI directly;
Puerto Rico and Barbados are unscored by CTHI-2024 (they'd pass an FSI fallback at
76/73) and stay via the GB union; only the Bahamas fails the net-recipient leg.

`_EXTRA_CTHI_GT_65_NET_RECIPIENT` (condition-2 jurisdictions not already GB):

| ISO3 | Jurisdiction | CTHI-2024 Haven Score | Net misalignment (bn USD, excl 2020) |
|---|---|--:|--:|
| AIA | Anguilla | 100 | +0.01 |
| ARE | United Arab Emirates | 82 | +10.6 |
| CYP | Cyprus | 79 | +17.4 |
| PAN | Panama | 72 | +36.4 |
| CUW | Curaçao | 72 | +3.5 |
| ABW | Aruba | 71 | +0.2 |
| SYC | Seychelles | 70 | +0.2 |
| LIE | Liechtenstein | 67 | +0.3 |
| MCO | Monaco | 66 | +2.4 |

**Dropped vs the old ≥67 rule** (CTHI-scored above the cutoff but net *losers* in
our results, so presenting them as havens contradicted the estimates): Hungary
(−29.8bn), Costa Rica (−8.9bn), Latvia (−3.3bn), Lebanon (−2.9bn), Estonia
(−2.8bn), Liberia (−0.3bn). **Added vs the old rule:** Monaco (CTHI 66, below the
old ≥67 cutoff but above 65). Guernsey, Cook Islands and BIOT stay via the manual
set despite failing the outcome/score gates.

`TAX_HAVENS_REPRESENTATION_NARROW` is a **deprecated alias** of the main list: its
purpose (dropping debatable Costa Rica / Latvia / Lebanon) is subsumed by the
net-recipient condition, which excludes all three.

Freezing note: the net-recipient flags were evaluated once (2026-07 headline run)
and frozen into `config.py` — safe because the list feeds no estimate. If a future
data-year rerun materially changes who is a net recipient, re-derive with the
session scratchpad logic (score gate + pooled net misalignment) and update
`_EXTRA_CTHI_GT_65_NET_RECIPIENT`.

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
