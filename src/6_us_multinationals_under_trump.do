cd "C:\Users\aliso\OneDrive\المستندات\github\sotj_profit_shifting_estimates"

* Start with segment information
import delimited "data\2025\raw\segment_reporting_compustat.csv", clear
keep tic datadate conm cusip snms soptp1 geotp sales capxs ias emps atlls revts gvkey 
lab var ias "Identifiable (Total) Assets"
lab var atlls "Long Lived Assets"
lab var revts "Total revenues"
lab var geotp "Geographic segment type"
label define geotp 2 "Domestic" 3 "Non-Domestic", replace
label values geotp geotp

gen double fdate = date(datadate, "DMY")
gen int year = year(fdate) // In compustat fiscal year is always the year of reporting
keep if geotp == 3 & revts > 0 & revts != .
keep gvkey
duplicates drop
save "data\2025\raw\segment_reporting.dta", replace

import delimited "data/2025/raw/compustat_etrs_plusinactive_20251023.csv", clear
rename fyear year
* ================================================================
* Restrict sample to US firms after 2015
* ================================================================
keep if fic == "USA"
duplicates tag gvkey year, gen(dup) // Only very few duplicates, all except for one line with all values missing
drop if dup == 1 & pi == .
keep if inrange(year, 2015, 2024)

* ================================================================
* Optionally: Restrict sample to firms with SOME foreign operations
* ================================================================
*merge m:1 gvkey using  "data\2025\raw\segment_reporting.dta", keep(match)

* ================================================================
* Domestic pretax income (PIDOM), compute if missing
* ================================================================
replace pidom = pi - pifo if missing(pidom) & !missing(pi, pifo)
replace pifo = pi - pidom if missing(pifo) & !missing(pi, pidom)

* ================================================================
* Domestic tax provision
*   Refined: fed + state + (deferred_total − deferred_foreign)
*   Fallback: TXT − TXFO
* ================================================================
gen double tax_dom_refined = .
replace   tax_dom_refined = txfed + txs if !missing(txfed, txs)
replace   tax_dom_refined = tax_dom_refined + (txdi - txdfo) ///
    if !missing(tax_dom_refined, txdi, txdfo)

gen double tax_dom_simple = .
replace tax_dom_simple  = txt - (txfo + txdfo) if !missing(txt, txfo) & !missing(txdfo)


gen double tax_dom_supersimple = .
replace   tax_dom_supersimple  = txt - txfo  if !missing(txt,txfo)

gen double tax_domestic = tax_dom_refined
replace tax_domestic = tax_dom_simple if missing(tax_domestic)
replace tax_domestic = tax_dom_supersimple if missing(tax_domestic)

* ================================================================
* Foreign tax provision
*   txfo + txdfo
* ================================================================
gen double tax_foreign = txfo + txdfo
replace tax_foreign = txfo if tax_foreign == . & txfo != .

* ================================================================
* ETRs per firm-year (set missing when denominator <= 0)
* ================================================================
gen double etr_foreign  = .
replace   etr_foreign  = tax_foreign / pifo if !missing(tax_foreign, pifo) & pifo  > 0

gen double etr_domestic = .
replace   etr_domestic = tax_domestic / pidom if !missing(tax_domestic, pidom) & pidom > 0

* Instead of using the "original" values for total taxes and total profits, we 
* aggregate them by using the domestic and foreign values. This ensures that we have
* the same sample of firms everywhere.
gen double etr = .
replace etr = txt/pi if !(missing(txt,pi)) & pi > 0

* ================================================================
*  Pretax profit shares (by geography)
*   Shares defined only when total pretax > 0 and component >= 0
* ================================================================
gen profit_total = pidom + pifo
replace profit_total = pidom if profit_total == . & pifo == .
replace profit_total = pifo if profit_total == . & pidom == .

gen double share_pretax_foreign  = .
replace   share_pretax_foreign  = pifo  / profit_total if !missing(pifo, profit_total)  & profit_total > 0 & pifo  >= 0

gen double share_pretax_domestic = .
replace   share_pretax_domestic = pidom / profit_total if !missing(pidom, profit_total) & profit_total > 0 & pidom >= 0

* ================================================================
* Total taxes & profits (matched to dom/for components) + Total ETR
* ================================================================
gen double tax_total_matched    = .
replace   tax_total_matched    = tax_domestic + tax_foreign if !missing(tax_domestic, tax_foreign)
replace tax_total_matched = tax_domestic if tax_foreign == .
replace tax_total_matched = tax_foreign if tax_domestic == .

gen double profit_total_matched = .
replace   profit_total_matched = pidom + pifo if !missing(pidom, pifo)
replace profit_total_matched = pidom if missing(pifo)
replace profit_total_matched = pifo if missing(pidom)

* Matched-sample total ETR (preferred)
gen double etr_total = .
replace   etr_total = tax_total_matched / profit_total_matched ///
    if !missing(tax_total_matched, profit_total_matched) & profit_total_matched > 0

* Keep your original total ETR for reference (optional)
gen double etr_total_raw = .
replace   etr_total_raw = txt/pi if !missing(txt, pi) & pi > 0

gen double etr_total_bestcoverage = etr_total
replace etr_total_bestcoverage = etr_total_raw if missing(etr_total_bestcoverage)


* ================================================================
* TABLE 1: US firms, year-level stats (means/medians, counts) 2016–2024
*  Includes ETRs + profit shares
* ================================================================
* Preferred headline series uses best coverage
preserve
    collapse ///
        (mean)   mean_etr_domestic = etr_domestic ///
                 mean_etr_foreign  = etr_foreign  ///
                 mean_etr_total    = etr_total    ///
                 mean_etr_total_bestcoverage = etr_total_bestcoverage ///
                 mean_share_domestic = share_pretax_domestic ///
                 mean_share_foreign  = share_pretax_foreign ///
        (sum)    profits_in_us   = pidom  ///
                 profits_foreign = pifo   ///
                 profits_total   = pi     ///
                 tax_us          = tax_domestic ///
                 tax_foreign     = tax_foreign ///
                 tax_total       = txt    ///
                 profits_total_mnes = profit_total_matched /// optional
                 tax_total_mnes     = tax_total_matched   /// optional
        (median) med_etr_domestic = etr_domestic ///
                 med_etr_foreign  = etr_foreign  ///
                 med_etr_total    = etr_total    ///
                 med_etr_total_bestcoverage = etr_total_bestcoverage ///
                 med_share_domestic = share_pretax_domestic  ///
                 med_share_foreign  = share_pretax_foreign   ///
        (p25)    p25_etr_domestic = etr_domestic ///
                 p25_etr_foreign  = etr_foreign  ///
                 p25_etr_total    = etr_total    ///
                 p25_etr_total_bestcoverage = etr_total_bestcoverage ///
        (count)  N_domestic_etr   = etr_domestic ///
                 N_foreign_etr    = etr_foreign  ///
                 N_total_etr      = etr_total    ///
                 N_total_etr_bestcoverage = etr_total_bestcoverage ///
                 N_domestic_share = share_pretax_domestic ///
                 N_foreign_share  = share_pretax_foreign ///
                 N_profits_us     = pidom ///
                 N_profits_foreign= pifo  ///
                 N_profits_total  = pi, ///
        by(year)

    export excel using "output/2025/tables/us_mnes_under_trump.xlsx", ///
        sheet("US_All") firstrow(variables) sheetmodify keepcellfmt
    export delimited using "output/2025/tables/us_mnes_under_trump_all.csv", replace
restore

* ================================================================
* TABLE 1A: US firms, year-level stats (means/medians, counts) that
* are active in 2016 and 2024
*  Includes ETRs + profit shares
* ================================================================
* Preferred headline series uses best coverage
preserve
bysort gvkey: egen max_year = max(year)
bysort gvkey: egen min_year = min(year)
keep if min_year <=2016 & max_year >= 2024 & max_year != . & min_year != .
    collapse ///
        (mean)   mean_etr_domestic = etr_domestic ///
                 mean_etr_foreign  = etr_foreign  ///
                 mean_etr_total    = etr_total    ///
                 mean_etr_total_bestcoverage = etr_total_bestcoverage ///
                 mean_share_domestic = share_pretax_domestic ///
                 mean_share_foreign  = share_pretax_foreign ///
        (sum)    profits_in_us   = pidom  ///
                 profits_foreign = pifo   ///
                 profits_total   = pi     ///
                 tax_us          = tax_domestic ///
                 tax_foreign     = tax_foreign ///
                 tax_total       = txt    ///
                 profits_total_mnes = profit_total_matched /// optional
                 tax_total_mnes     = tax_total_matched   /// optional
        (median) med_etr_domestic = etr_domestic ///
                 med_etr_foreign  = etr_foreign  ///
                 med_etr_total    = etr_total    ///
                 med_etr_total_bestcoverage = etr_total_bestcoverage ///
                 med_share_domestic = share_pretax_domestic  ///
                 med_share_foreign  = share_pretax_foreign   ///
        (p25)    p25_etr_domestic = etr_domestic ///
                 p25_etr_foreign  = etr_foreign  ///
                 p25_etr_total    = etr_total    ///
                 p25_etr_total_bestcoverage = etr_total_bestcoverage ///
        (count)  N_domestic_etr   = etr_domestic ///
                 N_foreign_etr    = etr_foreign  ///
                 N_total_etr      = etr_total    ///
                 N_total_etr_bestcoverage = etr_total_bestcoverage ///
                 N_domestic_share = share_pretax_domestic ///
                 N_foreign_share  = share_pretax_foreign ///
                 N_profits_us     = pidom ///
                 N_profits_foreign= pifo  ///
                 N_profits_total  = pi, ///
        by(year)

    export excel using "output/2025/tables/us_mnes_under_trump.xlsx", ///
        sheet("US_survivors") firstrow(variables) sheetmodify keepcellfmt
    export delimited using "output/2025/tables/us_mnes_under_trump_survivors.csv", replace
restore



* ================================================================
* TABLE 2: Big Tech summary (year-level, like US_All)
*   Firms: Apple, Microsoft, Alphabet/Google, Meta/Facebook, Tesla, Amazon
* ================================================================
preserve
    gen str12 _tic = upper(tic)
    keep if inlist(_tic,"AAPL","MSFT","AMZN","GOOG","GOOGL","META","FB")

    collapse ///
        (mean)   mean_etr_domestic = etr_domestic ///
                 mean_etr_foreign  = etr_foreign  ///
                 mean_etr_total    = etr_total    ///
                 mean_etr_total_bestcoverage = etr_total_bestcoverage ///
                 mean_share_domestic = share_pretax_domestic ///
                 mean_share_foreign  = share_pretax_foreign  ///
        (sum)    profits_in_us   = pidom  ///
                 profits_foreign = pifo   ///
                 profits_total   = pi     ///
                 tax_us          = tax_domestic ///
                 tax_foreign     = tax_foreign ///
                 tax_total       = txt    ///
                 profits_total_matched_sum = profit_total_matched ///
                 tax_total_matched_sum     = tax_total_matched   ///
        (median) med_etr_domestic = etr_domestic ///
                 med_etr_foreign  = etr_foreign  ///
                 med_etr_total    = etr_total    ///
                 med_etr_total_bestcoverage = etr_total_bestcoverage ///
                 med_share_domestic = share_pretax_domestic  ///
                 med_share_foreign  = share_pretax_foreign   ///
        (p25)    p25_etr_domestic = etr_domestic ///
                 p25_etr_foreign  = etr_foreign  ///
                 p25_etr_total    = etr_total    ///
                 p25_etr_total_bestcoverage = etr_total_bestcoverage ///
        (count)  N_domestic_etr   = etr_domestic ///
                 N_foreign_etr    = etr_foreign  ///
                 N_total_etr      = etr_total    ///
                 N_total_etr_bestcoverage = etr_total_bestcoverage ///
                 N_domestic_share = share_pretax_domestic ///
                 N_foreign_share  = share_pretax_foreign ///
                 N_profits_us     = pidom ///
                 N_profits_foreign= pifo  ///
                 N_profits_total  = pi, ///
        by(year)

    export excel using "output/2025/tables/us_mnes_under_trump.xlsx", ///
        sheet("BigTech") firstrow(variables) sheetmodify keepcellfmt
    export delimited using "output/2025/tables/us_mnes_under_trump_bigtech.csv", replace
restore

* Big Tech company-year panel
preserve
    gen str12 _tic = upper(tic)
    keep if inlist(_tic,"AAPL","MSFT","AMZN","GOOGL","GOOG","META","FB")

    keep year gvkey tic conm ///
         etr_domestic etr_foreign etr_total etr_total_raw etr_total_bestcoverage ///
         share_pretax_domestic share_pretax_foreign ///
         pi pidom pifo profit_total_matched ///
         tax_domestic tax_foreign tax_total_matched txt

    order year gvkey tic conm ///
          etr_domestic etr_foreign etr_total etr_total_raw etr_total_bestcoverage ///
          share_pretax_domestic share_pretax_foreign ///
          pi pidom pifo profit_total_matched ///
          tax_domestic tax_foreign tax_total_matched txt

    export excel using "output/2025/tables/us_mnes_under_trump.xlsx", ///
        sheet("BigTech_Panel") firstrow(variables) sheetmodify keepcellfmt
    export delimited using "output/2025/tables/us_mnes_under_trump_bigtech_panel.csv", replace
restore



* ================================================================
* Output:
*   - etr_results.xlsx / Sheet 'US_All'        : year-level ETRs + profit shares (mean/median + N)
*   - etr_results.xlsx / Sheet 'BigTech_Tesla' : company-year ETRs + profit shares
* ================================================================
