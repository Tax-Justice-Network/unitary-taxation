# Document audit — errors, incorrect formulations & reference gaps

Audit of `Unitary taxation.docx` (main doc). **List only — nothing was changed in the main
document.** The figure/table/appendix/reference *additions* are in
`Unitary taxation_autodraft_v4.docx` (a copy), flagged with `⟦INSERTED BY SCRIPT⟧`.

## 1. References (cited but missing / wrong)
- **Missing from the reference list** (cited in text): **IGF & ATAF (2022)**, **Loretz (2026)**,
  **Palanský & Schultz (2024)**. → added (flagged, to verify) in the References block of v4.
- **OECD (2020) mismatch.** The reference is *"Report on Pillar One Blueprint"*, but the
  CFB/ADS market-allocation method cited in §4.2.3 (ch. 2, paras 92–99) is from the OECD (2020)
  ***Economic Impact Assessment*** — a different document. Fix the reference (or split into two
  OECD 2020 entries and cite the right one in each place).

## 2. Introduction — 5 unfilled `[REF]` placeholders (proposed citations, verify)
1. *"Conservative politicians criticise the ever-growing complexity"* → e.g. Devereux & Vella
   (2018), *Implications of Digitalisation for International Corporate Tax Reform*; or an OECD/IMF
   complexity source. **[editorial — verify]**
2. *"Progressive voices point to … avoidance and the draining of public budgets"* →
   **Tørsløv, Wier & Zucman (2023)** and **Alstadsæter, Godar, Nicolaides & Zucman (2024)**
   (both already in the reference list — just cite them here).
3. *"Labour unions argue … weakens their hand in collective bargaining"* → e.g. Fuest, Peichl &
   Siegloch (2018) on the wage incidence of corporate taxation; or an ITUC/TUAC position paper.
   **[verify]**
4. *"Civil society actors decry the failure to make big companies pay their fair share"* →
   Tax Justice Network / Oxfam campaign material. **[verify]**
5. *"Even large multinationals themselves favour simpler solutions"* → e.g. The B Team responsible-
   tax statements, or a business-survey source. **[weakest claim — verify or soften]**
- Also: the **author placeholder note** at the top of the Introduction ("I actually hoped you'd
  write the intro, Alex?") should be removed before submission.

## 3. §4.4 (converting taxable-profit change to revenue) — wording
- **Garbled sentence:** *"we assume that both losses from unitary taxation are currently taxed at
  the ETR and gains from unitary taxation would be taxed at the ETR."* → rephrase, e.g. *"we value
  both the profit a country loses and the profit it gains at the effective tax rate (ETR–ETR)."*
- **Incomplete sentence (second specification):** *"While profits that are currently strategically
  located away from the economic activity are probably taxed at the ETR we observe in our data (or
  lower …)."* — has no main clause; complete it.
- **Typos:** *"incentiuve"* → *"incentive"*; *"would have probably be fully taxed"* → *"would
  probably have been fully taxed"*.
- (Not an error: the ETR–CIT logic — gains at statutory CIT, losses at ETR — is consistent with the
  code and with the Fig 3 caption.)

## 4. Appendix numbering & cross-references
- **Appendix B** prose refers to *"Tables A1–A3"* and *"Table A4"*, but the tables are labelled
  **Table B1, Table A2, Table A3** — unify (e.g. B1–B4).
- The **gravity feature-group table is double-numbered**: called *"Table B1"* in the Appendix D
  prose but titled *"Table C1"*. Pick one label.
- **Appendix D** says *"Appendix A lists which reporters fall into each category"* — that list is in
  **Appendix B**, not A.
- **Appendix B** prose says *"we disaggregate their aggregated rows (Appendix B)"* — the
  disaggregation method is described in **Appendix D**.

## 5. Minor
- §4.3 typo: *"multiationals"* → *"multinationals"*.
- §3.2.1 heading *"Analytical Activity of Multinational Enterprises database"* → gloss the acronym:
  *"Analytical AMNE (Activity of Multinational Enterprises) database"*.

## 6. Verified consistent (not errors)
- Headline numbers in the Introduction — ≈80% of countries / four-fifths of population, 97% under
  the floor, high-income ≈ $740B, lower-mid ≈ $380B, upper-mid ≈ $360B, low-income ≈ $23B, LIC ≈
  +410%, hubs ≈ −30% / −$150B — all match the current (1%–10% floor, reported, ETR-CIT) runs.
- The ETR–CIT revenue specification matches the pipeline's `loss_cit_gain_etr` rate mode.
