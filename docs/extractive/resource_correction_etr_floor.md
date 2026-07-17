# Resource-dominated residual-ETR floor ("the Saudi fix, generalized")

**Added 2026-07-08** to `src/4_correcting_cbcr_for_resource_payments.py`.

## Problem

After the resource correction, several resource economies still showed a
**non-resource ETR well above their statutory CIT** — economically implausible
(a country's *non-resource* effective rate should not exceed statutory) and it
**inflates their UT losses**. The cause is that the payment panel under-removed the
resource tax: the assumed rate was too low, the manual/EITI figure too small, or
(the "two-leg" case) CIT and state-equity payments come from different companies so
`max(post/rate, equity)` under-sums. Examples (pre-fix residual ETR vs CIT):

| Country | Source | Reported ETR | Residual ETR | CIT |
|---|---|--:|--:|--:|
| Libya | manual ($5.6bn — too small vs $17bn tax) | 0.85 | **0.86** | 0.20 |
| Saudi Arabia | manual (Aramco AR) | 0.45 | 0.37 | 0.20 |
| Angola | GRD | 0.54 | 0.52 | 0.28 |
| Gabon | EITI+GRD | 0.50 | 0.64 | 0.30 |

## Fix

A **generalized residual-ETR floor**: for every **resource-dominated, non-haven**
cell whose residual non-resource ETR still exceeds statutory CIT, strip the residual
excess-over-CIT tax and the matching resource profit **in lockstep** at rate
`rr = max(resource_rate_partner, CIT + 0.05)`, so the residual non-resource ETR lands
at the statutory rate. This is the same logic as the primary ETR-gap strip, applied
as a final backstop regardless of the payment source (so it catches trusted
manual/EITI cells and cells with no curated rate that the gap gate skipped).

Implemented as `resource_correction_method == "resource_dominated_etr_floor"`.

### Who it applies to — resource-DOMINATED only

Gated so it does **not** touch diversified economies whose above-CIT ETR reflects
withholding/minimum taxes rather than resources. A cell qualifies iff:

- `iso_partner` **not** in `TAX_HAVENS_REPRESENTATION` (havens use list-based ID), **and**
- extractive rents **≥ 5% of GDP** (`resource_country_parameters.csv`), **OR**
  the country's resource share of its own CbCR profit **≥ 30%**.

**Correctly EXCLUDED** (validated): UK, Mexico, India, Turkey, Poland, South Africa,
Argentina, Ethiopia (0.70 ETR, ~0 resources), Kenya, Greece — their ETR>CIT is not
resource-driven, and blanket-capping them would misattribute hundreds of billions of
non-resource profit to resources.

**Affected (2016–2022, 39 economies, ~$236B extra profit / ~$115B extra tax stripped;
implied rate 0.49):** AGO, AUS, BFA, BHR, BRN, BWA, CHL, COD, COG, DZA, EGY, GAB, GHA,
GNQ, GUY, IRN, IRQ, KAZ, KGZ, KWT, LBY, MLI, MMR, MOZ, NGA, NOR, OMN, PER, PNG, QAT,
RUS, SAU, TKM, TLS, TTO, TUN, TZA, UZB, ZMB.

## Related change: Saudi effective rate

Saudi's curated `resource_rate` was raised **0.20 → 0.45** (its effective take:
royalties + special hydrocarbon tax + Zakat, matching its reported ETR). The 0.20
Aramco headline CIT under-removed. This makes Saudi's primary gap strip fire
correctly; the floor is then a no-op for it.

## Impact on results

- **Libya:** residual profit base $16.4bn → $0.2bn (ETR 0.86 → 0.17) — its
  robust-loser status was a correction artifact (unremoved oil).
- **Saudi:** UT loss −$76bn → ≈ −$14bn.
- Diversified economies unchanged; low-income group stays a net winner.

## Known limitation

The floor caps the per-cell residual, and the profit base is properly stripped. But
the **model `etr_average_excl_resource`** is a 5-year rolling partner-year construct
that can stay above CIT for small oil economies (Angola, Gabon, Algeria, Tunisia)
whose ETR is dominated by **loss / tiny-profit cells** — there is no positive profit
in those cells to strip, so no floor can move them. This is a diagnostic artifact on
a small base, **not** profit-base under-correction (the base *is* corrected). Losers
are valued at CIT in the headline ETR-CIT rate mode, so this residual does not inflate
their loss.
