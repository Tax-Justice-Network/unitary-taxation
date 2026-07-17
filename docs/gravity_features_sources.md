# Gravity / ML imputation feature sources (García-Bernardo & Janský 2024)

Replicates the missing-data imputation of **García-Bernardo & Janský (2024),
*Profit shifting of multinational corporations worldwide*, World Development
177, 106527**, Table A.2. We train a Histogram-based Gradient Boosting model to
predict each `(reporter, partner, year)` cell's **employees, unrelated-party
sales, tangible assets**, then impute **profit = imputed factor × the
country's reported productivity-per-factor** and **rescale profits
proportionally** so reporting countries' sums match the CbCR aggregate.

Decision (2026-06-15): **public sources only**, sourced fresh via API where
possible and **cached to `data/raw/`** for reproducibility; the proprietary
LinkedIn block and commercial snapshots are **omitted and documented** (see
bottom). Integrated into `2_disaggregate_aggregated_values.py` as the **single
disaggregation method** (since 2026-06-23 — the former `IMPUTE_METHOD` trimmed-mean
toggle was removed; see `docs/disaggregation_method_change.md`).

Confidence: H = direct official source; M = proxy / version mismatch; L = weak.

## Reachability (tested 2026-06-15)
- ✅ World Bank API · ✅ UN Comtrade API · ✅ BIS bulk zip · ✅ CEPII bulk zip
  (`https://www.cepii.fr/DATA_DOWNLOAD/gravity/data/Gravity_csv_V202211.zip`, 207 MB)
- ❌ IMF SDMX (`dataservices.imf.org` DNS-dead; `api.imf.org`/datamapper 404/403)
  → CDIS (FDI) + CPIS (portfolio) need a resolved new endpoint or **manual bulk
  download** from data.imf.org.

## Bilateral variables

| Var(s) | Source | Fetch | Status / conf |
|---|---|---|---|
| ln_Import, ln_Export | UN Comtrade | API `comtradeapi.un.org/public/v1/preview/C/A/HS` (TOTAL, flow M/X) | ✅ API · H |
| ln_FDI_inward, ln_FDI_outward | IMF CDIS via **WB Data360** | API `data360api.worldbank.org/data360/data?DATABASE_ID=IMF_CDIS&INDICATOR=IMF_CDIS_IWDA_BP6` — bilateral counterpart in `COMP_BREAKDOWN_1` (IMF IFS numeric codes → ISO3); outward by mirror | ✅ API · H |
| ln_PortI_inward, ln_PortI_outward | IMF CPIS via **WB Data360** | API `datasetId=IMF_CPIS` (50 indicators); same bilateral structure | ✅ API · H |
| ln_dClaims, ln_dLiabilities, ln_BIS | BIS LBS A6.2 / consol. B4 | bulk zip `bis.org/statistics/full_lbs_d_pub_csv.zip` | ✅ bulk · H |
| ln_distw, tdiff, contig, comlang_off/ethno, comcol, comcur, comrelig, col45/fr/to, colony, curcol, cursib, sibling, comleg_pre/posttrans, transition_legalchange, fta_wto, gsp(_o/d_d), heg_o/d, eu_to_acp, acp_to_eu | CEPII GravData V202211 | bulk zip (URL above) | ✅ bulk · H |

## Unilateral variables

| Var(s) | Source | Fetch | Status / conf |
|---|---|---|---|
| entry_proc, entry_time, entry_tp, gatt, ln_area, ln_entry_cost, english, ln_pop, ln_gdp_d, ln_gdpcap_d/ln_gdppc_d | CEPII GravData | from the same bulk zip | ✅ bulk · H |
| EU28, OECD, Ukt, region_tjn | derived / TJN | dummies + `unilateral_cross` (in raw) | ✅ in-repo · H |
| governance (WGI PCA-1) | World Bank WGI | API: GE/RL/RQ/CC/PV/VA `.EST`; PCA in code | ✅ API · M (PCA) |
| ln_population, ln_GDP_int | World Bank | SP.POP.TOTL, NY.GDP.MKTP.CD | ✅ API · H |
| ln_consumption | World Bank NE.CON.PRVT.KD | API | ✅ API · H |
| ln_gfcf | World Bank NE.GDI.FTOT.KD | API | ✅ API · H |
| ln_FDI_Inflows_WDI_d | World Bank BX.KLT.DINV.CD.WD | API | ✅ API · H |
| ln_imports_wbd, ln_exports_wbd | World Bank NE.IMP/EXP.GNFS.CD | API | ✅ API · H |
| ln_ip_payments_wbd, ln_ip_receipts_wbd | World Bank BM/BX.GSR.ROYL.CD | API | ✅ API · H |
| ln_ExternalDebtStocks | World Bank DT.DOD.DECT.CD | API | ✅ API · H |
| ln_gov_exp_educ_sgdp_wb | World Bank SE.XPD.TOTL.GD.ZS | API | ✅ API · H |
| tax_complex | World Bank IC.TAX.DURS | API | ✅ API · H |
| Nurses_per_1000, ln_Nurses | World Bank SH.MED.NUMW.P3 (+pop) | API | ✅ API · H |
| Physicians_per_1000, ln_physician | World Bank SH.MED.PHYS.ZS (+pop) | API | ✅ API · H |
| ln_Health_expenditure_gdp | World Bank SH.XPD.GHED.GD.ZS | API | ✅ API · H |
| ln_who_gvt_health_expenditure | WHO GHED | in-repo `WHO health expenditure.xlsx` | ✅ in-repo · H |
| ln_month_wage | ILO | in-repo ILO wage file | ✅ in-repo · H |
| ln_cit_revenue, ln_resource_revenue(_gdp), ln_resource_taxes, ln_total_taxes_revenue | UNU-WIDER GRD | in-repo `UNUWIDERGRD_2025.xlsx` | ✅ in-repo · H |
| Total FSI | TJN FSI | in-repo `portal_fsi_results.csv` | ✅ in-repo · H |
| cthi | TJN CTHI | in-repo `portal_cthi_data.csv` | ✅ in-repo · H |
| cit, ln_cit | OECD/TaxFoundation | in-repo CIT data | ✅ in-repo · H |
| etr_real, ln_etr_real | CbCR-weighted | derive from pipeline ETRs | ✅ derive · M |
| ln_n_companies_orb | Orbis | in-repo Orbis (#MNCs >750M) | ✅ in-repo · M |
| ln_GreenfieldFDI_inward/outward | UNCTAD | manual (UNCTAD WIR annex) | ⚠️ manual · M |

## Omitted (documented deviations from the paper)

- **LinkedIn block (proprietary, García-Bernardo & Stausholm, forthcoming) —
  NOT publicly available, omitted:** `ln_audience`, `ln_accountant_d`,
  `ln_all_tax`, `ln_banker`, `ln_ceo`, `ln_cfo`, `ln_coo`, `ln_cxo`,
  `ln_engineer`, `ln_finance`, `ln_other_corporate`, `ln_wealth`,
  `ln_transfer_pricing`, `ln_tax_compliance_audit` (14 vars).
- **Commercial static snapshots — omitted unless manually supplied:**
  `ln_uhnwi` (Credit Suisse Global Wealth Report 2018), `ratings` (Trading
  Economics, Feb 2019).

Cite as: *"following García-Bernardo & Janský (2024), using their public
feature set; the proprietary LinkedIn-derived variables and two commercial
snapshots are excluded."* Top predictors in their Fig. A.6 (outward FDI,
imports/exports, GDP, portfolio investment) are all retained.

## Build plan

1. `src/gravity/` fetchers (pull-and-cache to `data/raw/gravity/`): CEPII bulk,
   Comtrade API, BIS bulk, World Bank API (multi-indicator), IMF CDIS/CPIS
   (endpoint TBD / manual). Each writes a frozen CSV; re-reads cache if present.
2. `src/gravity/build_features.py`: assemble the `(reporter, partner, year)`
   feature matrix (bilateral + unilateral-of-both-sides), logs, joins to CbCR.
3. `src/gravity/impute_model.py`: `HistGradientBoostingRegressor` per target
   (ln_emp, ln_sales, ln_tangible), trained on reported cells; predict missing;
   report out-of-sample R² (target ≈ 0.74 / 0.56 / 0.44).
4. Profit: `profit = imputed factor × reported productivity-per-factor`, then
   **rescale** so reporting parents' imputed sums match the CbCR aggregate.
5. Integrated in `2_disaggregate_aggregated_values.py` as the sole method (gravity
   activity + profitability profit); trimmed-mean removed 2026-06-23.
