# US multinationals are under-reporting public CbCR — evidence for the report

This note backs the argument that **US multinationals are not reporting public
country-by-country (pCbCR) data as they should**, which is why granular
company-level disclosure cannot yet be used to locate US-MNE profit shifting and
the analysis must rely on the OECD aggregate CbCR + a unitary-apportionment
estimate. It combines (a) the Fair Tax Foundation's compliance analyses and
(b) two primary pCbCR filings held in `data/raw/cbcr/pcbcr/`.

## Background: why Romania filings exist at all

Romania was the first EU member state to transpose the EU public-CbCR Directive
(2021/2101) into national law (Order 2048/2022, amended by 1730/2023). Any MNE
group with consolidated revenue ≥ ~€747m (RON 3.7bn) for two consecutive years
and a subsidiary or branch in Romania must publish a country-by-country report
for financial years starting on/after 1 Jan 2023. For US-parented groups the
Romanian entity files it. The EU-wide mandate broadens from FY2025, until which
firms can use a five-year **safeguard ("safe-harbour") clause** to omit
commercially sensitive jurisdiction detail.

## Fair Tax Foundation findings (external; treat as cited secondary evidence)

The Fair Tax Foundation (Fair Tax Mark) reviews every pCbCR report filed under
the directive. US firms are both the largest cohort of filers and the worst
compliers, and their compliance is **deteriorating** across successive analyses:

| Metric | FTF Jul 2025 (137 reports) | FTF Jan 2026 (190 reports) |
|---|---|---|
| "Good application" — US | 43% | **40%** |
| "Good application" — UK | ~75% | 71% |
| "Good application" — Japan | ~75% | 72% |
| "Good application" — Switzerland | 44% | 43% |
| US firms filing "single-country / Romania-only" | 36% | **48%** |
| Overall solid compliance (all HQs) | 63% | **56%** |
| Parents refusing to share CbCR data with their RO/HR/ES subsidiary | 26% | 32% |

Key qualitative points from the FTF analyses:
- US-headquartered MNEs are explicitly described as **"laggards"**; their
  good-application rate (~40%) is roughly half the UK/Japan rate (~71–72%).
- By Jan 2026 the share of US firms taking the **single-country/Romania-only**
  route (48%) **exceeds** the share that comply solidly (40%) — i.e. more US
  firms dodge than comply.
- FTF names US firms restricting disclosure, including **Apple, Mondelez,
  Johnson & Johnson, Merck, Microsoft, Bristol Myers Squibb, Philip Morris**.
- Pharma is among the weakest sectors (≈4/12 firms compliant; half single-country).

**Confidence:** High on the headline percentages and the direction of travel
(figures taken directly from FTF's published analyses — see Sources). Medium on
exact cross-report comparability, because FTF's sample grows each round
(137 → 190 reports) and category definitions are FTF's own.

## Primary evidence in this repo (`data/raw/cbcr/pcbcr/`)

Two filings illustrate the **two distinct evasion routes** FTF documents:

1. **Apple Inc. — Romania CbCR FY24** (`apple_Romania-CbCR-FY24.pdf`).
   The report states it is *"limited to the Group's Romanian operations, as the
   Group's ultimate parent has not made available information with respect to
   the Group's worldwide operations."* Only the single Romania row is disclosed
   (Revenue $71.9m, profit before tax $31.7m, tax paid $4.7m, 23 employees). The
   Romanian entity is *"Apple Distribution International **Limited – IE** PE"* —
   an **Irish** company's Romanian permanent establishment, i.e. the Ireland-hub
   structure the misalignment estimates pick up. → **Single-country / Romania-only.**

2. **Alphabet Inc. (Google) — Romania tax-info FY24**
   (`romania-tax-info_2024-1-1_2024-12-31_ro_v1_google.pdf`).
   Alphabet files a fuller report but invokes the **safeguard clause
   (Art. 5929 §11)** to omit *all EU-jurisdiction data for five years*, citing
   competitive harm. It discloses Romania plus a handful of non-EU/non-cooperative
   jurisdictions (Croatia, Curaçao, Fiji, Guam, Malaysia, Panama, Turkey,
   Vietnam) individually, and collapses **US + Ireland + Luxembourg + Netherlands
   + everything else** into one *"All other tax jurisdictions (aggregated)"* line
   ($451.4bn revenue, $114.0bn profit before tax, 23.2bn tax paid, 167,185
   employees). → **Safeguard-clause omission of the EU detail.**

Micro-contrast worth citing: Apple's Romanian PE books a **44% profit margin on
23 employees**, while Google's Romanian operations book a **~10% margin on 391
employees** — a clean illustration of why headcount/payroll-based unitary
apportionment moves profit away from these structures.

## The argument, in one paragraph

Barely 40% of US multinationals meet the EU public-CbCR standard (vs ~71% for UK
and ~72% for Japan), roughly half file Romania-only, and US compliance is
falling, not rising. Crucially, the data US firms withhold is exactly the data
that would reveal profit shifting — the **EU haven rows (Ireland, Luxembourg,
Netherlands)**. Apple discloses only Romania; Google blanks every EU jurisdiction
via the safeguard clause. This makes voluntary/public CbCR unusable for pinning
down where US MNEs book profit (hence the reliance on OECD aggregate CbCR + a
unitary-taxation estimate in this project) and is itself the strongest case for
**mandatory, fully disaggregated public CbCR**.

## Sources

- Fair Tax Foundation, *pCbCR across Europe 2025 — MNEs from the US increasingly
  laggards* (12 Jan 2026): https://fairtaxmark.net/pcbcr-across-europe-2025/
- Fair Tax Foundation, *Latest analysis of corporate compliance with EU pCbCR
  Directive: 60% perform well, but US and Swiss multinationals are laggards*
  (1 Jul 2025): https://fairtaxmark.net/analysis-of-eu-pcbcr-corporate-income-tax-reports/
- Fair Tax Foundation, *Research finds US multinationals are increasingly
  laggards on tax transparency, in comparison to the UK and Japan*:
  https://fairtaxmark.net/research-finds-us-multinationals-are-increasingly-laggards-on-tax-transparency-in-comparison-to-the-uk-and-japan/
- Fair Tax Foundation, *Trump administration wages war on corporate tax
  transparency whilst many US MNCs quietly embrace pCbCR*:
  https://fairtaxmark.net/trump-administration-wages-war-on-corporate-tax-transparency-whilst-many-us-mncs-quietly-embrace-public-country-by-country-reporting/
- Primary filings: `data/raw/cbcr/pcbcr/apple_Romania-CbCR-FY24.pdf`,
  `data/raw/cbcr/pcbcr/romania-tax-info_2024-1-1_2024-12-31_ro_v1_google.pdf`,
  `data/raw/cbcr/pcbcr/romania-tax-info_2023-1-1_2023-12-31_ro_v1_google.pdf`

Chart: `output/us_multinationals/figures/pcbcr_us_compliance_gap.png` (built by
`src/us_only/pcbcr_compliance_chart.py`).
