**Analyze new results for SOTJ23

cd "C:\Users\AlisonSchultz\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Tax avoidance"

import excel using "2017_tax_avoidance_sotj_table.xlsx", first clear
rename * *_2017
rename Name_2017 country
drop if MNCs_2017==""
rename MNCs_2017 MNCs
save "2017_tax_avoidance_sotj_table.dta", replace

import excel using "2018_tax_avoidance_sotj_table_old.xlsx", first clear
rename * *_old
rename Name_old country
drop if MNCs_old=="0"
rename MNCs_old MNCs
save "2018_tax_avoidance_sotj_table_DaniNov.dta", replace

import excel using "2018_tax_avoidance_sotj_table_new.xlsx", first clear
rename * *_new
rename Name_new country
drop if MNCs_new=="0"
rename MNCs_new MNCs
save "2018_tax_avoidance_sotj_table_AlisonJun.dta", replace

joinby country MNCs using "2018_tax_avoidance_sotj_table_DaniNov.dta", unmatched(both)
rename _merge _merge_oldnew
gen diff_newold = ProfitlossM_new - ProfitlossM_old
replace diff_newold=ProfitlossM_old if ProfitlossM_new==.
sort diff_newold
joinby country MNCs using "2017_tax_avoidance_sotj_table.dta", unmatched(both)


gen diff_old2017 = ProfitlossM_old - ProfitlossM_2017
replace diff_old2017=ProfitlossM_2017 if ProfitlossM_old==.
gen diff_new2017 = ProfitlossM_new - ProfitlossM_2017
replace diff_new2017=ProfitlossM_2017 if ProfitlossM_new==.

sort diff_new2017
br country MNCs diff* ProfitlossM* 


bys country: egen sum_c_profit=sum(ProfitlossM_new)
duplicates drop country, force
gsort -sum_c_profit
br country sum_c_profit

if diff_old2017>diff_new2017


br 



***Country-level analysis
global path "C:\Users\AlisonSchultz\OneDrive - Tax Justice Network Ltd\Documents\GitHub\sotj_profit_shifting_estimates"
import delimited "${path}/data/raw/estimations/CBCR_TABLEI_20062023110215400_corrIDN_withultimateparent.csv", clear
save "${path}/data/raw/estimations/oecd_table1.dta", replace
global country "Algeria " 
keep if partnerjurisdiction=="$country" & cbc=="PROFIT" & grouping=="Sub-Groups with positive profits"
keep ultimateparentjurisdiction value year
replace value=value/1000000000
reshape wide value, i(ultimateparentjurisdiction) j(year)
rename ultimateparentjurisdiction country
graph bar (asis) value2016 value2017 value2018, over(country, label(angle(45))) ytitle("Reported profits (USD billion)") title("MNEs' reported profits in: $country") subtitle("Source: Aggregate CbCR data from OECD") legend(order (1 "2016" 2 "2017" 3 "2018") cols(3))

use "oecd_table1.dta", clear
global country "Algeria"
keep if partnerjurisdiction=="$country" & cbc=="EMPLOYEES" & grouping=="Sub-Groups with positive profits"
keep if ultimateparentjurisdiction!=partnerjurisdiction
keep ultimateparentjurisdiction value year
reshape wide value, i(ultimateparentjurisdiction) j(year)
rename ultimateparentjurisdiction country
graph bar (asis) value2016 value2017 value2018, over(country, label(angle(45))) ytitle("Reported profits (USD billion)") title("MNEs' reported profits in: $country") subtitle("Source: Aggregate CbCR data from OECD") legend(order (1 "2016" 2 "2017" 3 "2018") cols(3))

*Misalignment at bilateral level
use "oecd_table1.dta", clear
keep if cbc=="PROFIT" | cbc=="EMPLOYEES"
keep if grouping=="Sub-Groups with positive profits"
tostring year, gen(year_string)
gen bilateralyear=cou+jur+year_string
keep bilateralyear ultimateparentjurisdiction cou partnerjurisdiction jur year value cbc
reshape wide value, i(bilateralyear) j(cbc) string
bys jur year: egen tot_profit=sum(valuePROFIT)
gen sh_profit_in_jur=(valuePROFIT/tot_profit)*100
bys jur year: egen tot_employees=sum(valueEMPLOYEES)
gen sh_employees_in_jur=(valueEMPLOYEES/tot_employees)*100
br cou jur sh_profit_in_jur sh_employees_in_jur if jur=="ARG" & year==2018
rename ultimateparentjurisdiction country
levelsof partnerjurisdiction if partnerjurisdiction=="Algeria", l(jurs) /*Generating this for NLD only for now, as there is an error for countries without any data*/
levelsof year, l(years)
foreach jur of local jurs { 
foreach year of local years {
quietly: graph bar (asis) sh_profit_in_jur sh_employees_in_jur if partnerjurisdiction=="`jur'" & year==`year' & jur!=cou, ///
	over(country, label(angle(45))) ytitle("Share (%)") ///
	title("MNEs' misalignment: `jur', `year'") subtitle("Source: Aggregate CbCR data from OECD") ///
	legend(order (1 "Share of profits in `jur'" 2 "Share of employees in `jur'") cols(1))
graph export "C:\Users\AlisonSchultz\OneDrive - Tax Justice Network Ltd\Documents\GitHub\sotj_profit_shifting_estimates\figures\misalignment_`jur'_`year'.png", replace
}
}


/*



reshape wide sh_profit_in_jur sh_employees_in_jur, i(bilateralyear) j(year)

graph bar (asis) sh_profit_in_jur2016 sh_profit_in_jur2017 sh_profit_in_jur2018 ///
	sh_employees_in_jur2016 sh_employees_in_jur2017 sh_employees_in_jur2018, ///
	over(country, label(angle(45))) ytitle("Reported profits (USD billion)") ///
	title("MNEs' reported profits in: $country") subtitle("Source: Aggregate CbCR data from OECD") ///
	legend(order (1 "2016" 2 "2017" 3 "2018") cols(3))


