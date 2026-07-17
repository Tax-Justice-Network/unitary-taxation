# Results section — filled placeholder numbers

All values: **reported sample, 2016–2022, constant 2022 US dollars**, headline formula
**sales & employees (destination)**, revenue on **ETR-CIT** (gains at CIT, losses at ETR)
unless stated. Denominator for "% of current CIT" = the figures' `tax_revenue_current`
series (same basis as the % panels). Pull the numbers below into the main draft.

## §5.1 — taxable profits
- ⚠ **"Largest beneficiaries" is mis-stated.** The text names the **US and Germany**, but the actual largest winners by **taxable profit** are **India ≈ +$540 bn** and **France ≈ +$479 bn**, then Germany ≈ +$283 bn and the US ≈ +$255 bn. By **tax revenue**: India ≈ +$205 bn, US ≈ +$191 bn, France ≈ +$168 bn, UK ≈ +$165 bn, Germany ≈ +$111 bn.
  → Rewrite the sentence to lead with **India** (largest on both metrics), e.g. "the largest beneficiaries include India and France (or the United States)." If you keep the `XXX and YYY` slot for two countries, use **India ≈ +$540 bn and France ≈ +$479 bn** (taxable profit, preferred formula).
- **Taxable-profit increase, $ range and % range across the four formulas** (2022$; % = Δ ÷ reported profit base):
  - India **+$186–540 bn** (**+43% to +125%**), France **+$410–491 bn** (**+56% to +67%**), United States **+$255–1,344 bn** (**+3% to +17%**), Germany **+$265–360 bn** (**+24% to +32%**).
  - Ordering is formula-dependent: India is largest under sales & employees; the US is largest in $ under CCCTB but only +3–17% of its very large base.
- **Low-income % gain** (`between X and Y%`): **between ≈140% (CCCTB) and ≈258% (sales & employees)**; the preferred sales & employees formula gives **≈258%**. → "between roughly 140% and 260%".
- CCCTB → upper-middle (China-driven) **net loss** claim: **confirmed** (CCCTB upper-middle net taxable profit ≈ **−$403 bn**).

## §5.1 — largest losers (Δ taxable profit, range across the 4 formulas, 2022$bn)
- Hubs/havens ($ range; % of booked profit lost): Hong Kong $507–654 (−60% to −77%) · Singapore $433–501 (−56% to −65%) · Switzerland $417–477 (−49% to −56%) · Netherlands $278–323 (−36% to −41%) · Cayman $250–276 (−89% to −99%) · Bermuda $246–261 (−94% to −99%).
- Non-haven losers: Japan $407–707 (−15% to −27%) · China $580–905 (−8% to −12%) · Canada $104–252 (−9% to −21%). Under sales & employees Japan is the **largest** loser (−$707bn), Hong Kong second (−$654bn), China **third** (−$610bn).
- **Home bias / over-booking** (domestic cell, 2022$bn, 2016–2022): own MNEs book at home vs activity-warranted — Japan **$2,396 vs $1,116 (2.1×)**, China **$5,170 vs $3,369 (1.5×)**, Canada **$1,060 vs $484 (2.2×)**. Verified: the entire net loss of Japan/Canada comes from the domestic cell (foreign parents there actually gain slightly); low-income aggregate reported profit is negative (−$6.5bn), so the 140–260% LIC gain is computed only over positive-base LICs.

## §5.3 — resource-exclusion examples (Δ tax revenue, ETR-CIT, 2022$; baseline "resources ignored" → "resources excluded")
- Figure 5 = **Angola** (−$1.4bn → +$2.2bn) + **South Sudan** (small negative for CCCTB/3-factor/DWS → small positive). Chad dropped — it does **not** lose under the baseline (positive under all four formulas, both ETR-CIT and ETR-ETR).
- Further examples named in text: **Peru** −$2.1bn → +$10.7bn; **Libya** −$7.7bn → +$0.7bn; **Chile** −$0.7bn → +$5.7bn. (Income spread: Peru/Chile upper-middle, Angola lower-middle, South Sudan low.)

## §5.2 — tax revenues
- **Total CIT revenue increase** (`XXX`), ETR-CIT: **≈ $1,497 bn (≈ $1.5 tn)** net over 2016–2022 (winners gain ≈ $2,346 bn; havens/losers lose ≈ $849 bn → net +$1,497 bn).
- **Average increase** (`Y%`): **≈ 13%** of current corporate income tax revenues (real÷real; the earlier 16% used a nominal denominator and was overstated — see note at bottom).
- **Hub multiplier / haven leakage ratio** (`approximately XX dollars`): **≈ 2.6** — for every $1 a tax haven collects on the profit shifted into it, the rest of the world loses ≈ $2.6 of tax revenue. Built by `src/9p_haven_leakage_ratio.py` = Σ_havens `tax_revenue_loss_caused_musd` ($993 bn) ÷ Σ_havens `tax_revenue_gain` ($382 bn), reported-only / excl_resource / sales_employees_destcfb / etrmax_inf / ETR-CIT, 2016–2022 excl 2020; havens = `investment_hub` list. **This supersedes the earlier "≈14×"**, which divided *all* winners' gross gains ($2,346 bn) by the hub group's UT loss ($163 bn) — conflating haven shifting with home-bias domestic over-booking (Japan/China/Canada). In fact **havens cause only ≈32% of all UT-reallocated loss**; the rest is home-bias. `tax_revenue_loss_caused` is attributed per HQ (parent) group at each sufferer's own tax rate, so no bilateral step is needed. *Definition-sensitive*: **2.6–2.9** across excl_resource / floored; the resources-ignored baseline gives **3.5** (both-legs-at-ETR) to **4.5** (ETR-CIT) because havens' *collected* revenue is lower there ($222 bn vs $382 bn). Per-haven ratios span pure conduits (Gibraltar ≈265×, BVI ≈18×, Cayman ≈15×, Bermuda ≈14× — they collect almost nothing yet cause large losses) to substance hubs (Ireland/Luxembourg ≈1.4×). See `output/unitary_taxation/across_samples/haven_leakage/`. (A ratio of two deflated dollar figures, so unaffected by the deflator.)
- **Figure 3 (ETR-ETR robustness)** (`XXX` … `Y%`): **≈ $997 bn (≈ $1.0 tn)**, **≈ 8%** of current CIT.
- **Break-even DOMESTIC ETR for home-bias losers** (Table 6, `table6_breakeven_domestic_etr__reported_only.csv`): rate on the smaller UT domestic base needed to keep current domestic MNE-tax revenue = domestic_ETR × domestic_reported ÷ domestic_theoretical. Mostly implausible → profit genuinely relocates: Japan ≈44–66% (cur ≈31%), Norway ≈52–66% (≈32%), Saudi Arabia ≈57–78% (≈37%), Denmark ≈34–90% (≈14%). Exceptions that currently under-tax domestically: Canada ≈20–27% (cur ≈12%, statutory ≈26%), Chile ≈17–25% (cur ≈14%). China ≈30–37% (cur ≈24%, statutory 25%). Contrast with hubs (Table 5), which break even at feasible rates.
- **Break-even ETR for losing hubs** (Table 5, `table5_breakeven_etr__*`): rate a hub would need to keep its current MNE-tax revenue on its smaller UT base = current_ETR × reported ÷ theoretical. Genuine hubs are feasible (at/below statutory CIT): Netherlands **14→23%**, Switzerland **11→24%**, Singapore **9→~24%**, Ireland **19→33%** — an increase of **≈9–18 pp**. Pure conduits (Cayman, Bermuda, BVI, Jersey, Gibraltar) need **60–380%** (no genuine base → infeasible). Home-bias non-haven losers (Japan/China/Canada) are excluded: their profit relocates to real foreign activity, only the domestic ETR (≈ CIT) applies, and they cannot recapture it by raising rates.

## §5.4 — how sales are measured  ⚠ CORRECTION
- The text says destination raises low-income taxable profit **"approximately three times"** vs origin. **Actual ≈ 1.6×** (low-income taxable profit: origin ≈ $31 bn → destination ≈ $50 bn). → change "approximately three times larger" to **"roughly 1.6 times larger" / "about 60% larger"**.

## §5.5 — consolidation
- **Reduction** (`by only X%`): overstatement ≈ **$239 bn**. That is **≈16% of the net headline gain** ($1,497 bn) **or ≈10% of winners' gross gains** ($2,346 bn). Your **intro says "around 10%"** → that is the winners'-gains basis; use the **same basis in §5.5** (10%) or switch both to 16% (net). Flagged for consistency.
- **Average gains** (`X% … compared with Y%`): headline **≈13%** of current CIT → consolidated **≈11%** (real÷real).
- **Luxembourg** share: **≈ $54 bn = 22%** of the total adjustment (top-5 adjustment jurisdictions: Luxembourg, United Kingdom, Venezuela, United States, Netherlands).

## §5.6 — scaling to global profit
- **Uplift** (`by approximately X%`): scaling to global corporate profit multiplies the estimate by **≈2.4×** (i.e. **≈ +144%**). Global winners' gain ≈ **$5.7 tn** over 2016–2022 vs $2.3 tn in the reported sample.
- Per year (2022$): reported estimate **$193–463 bn/yr**; scaled **$660–1,105 bn/yr** (the 2020 peak reflects that year's low CbCR coverage, 31%).
- ⚠ `from X% to Y% globally`: a "% of CIT" that **rises** with scaling is conceptually off — if the revenue *and* the CIT base both scale by 1/coverage, the % is ≈ unchanged. Recommend reporting the **$ uplift (≈2.4×)** rather than a rising %-of-CIT, or state the % stays ≈constant.

## Cross-checks / other corrections
- **Figure numbering** (see chat): your text's Fig 2 = ETR-CIT (file `fig03`), Fig 3 = ETR-ETR (`fig02`), Fig 6 = BFA+Guinea (`fig07`), Fig 7 = revenue-3-treatment (`fig06`). Insert files per that mapping.
- **Intro consistency**: intro still quotes nominal figures ($740B high / $23B low / −$150B hubs); in 2022$ these are ≈ **$815B / $25B / −$163B**. Update the intro (or label nominal) to match the deflated Results.
