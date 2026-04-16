* Differences 2017 and 2018
***Country-level analysis
global path "C:\Users\AlisonSchultz\OneDrive - Tax Justice Network Ltd\Documents\GitHub\sotj_profit_shifting_estimates"
*import delimited "${path}/data/raw/estimations/CBCR_TABLEI_20062023110215400_corrIDN_allcolumns.csv", clear
*save "${path}/data/raw/estimations/oecd_table1.dta", replace

use "${path}/data/raw/estimations/oecd_table1.dta", clear
global country "Brazil" 
keep if partnerjurisdiction=="$country" & cbc=="PROFIT" & grouping=="All Sub-Groups"
keep ultimateparentjurisdiction value year
replace value=value/1000000000
reshape wide value, i(ultimateparentjurisdiction) j(year)
rename ultimateparentjurisdiction country
graph bar (asis) value2016 value2017 value2018, over(country, label(angle(45))) ytitle("Reported profits (USD billion)") title("MNEs' reported profits in: $country") subtitle("Source: Aggregate CbCR data from OECD") legend(order (1 "2016" 2 "2017" 3 "2018") cols(3))
graph export "C:\Users\AlisonSchultz\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Reasons_for_changes_2017_to_2018\Figures\\${country}\profits_over_time_${country}.png", replace

use "${path}/data/raw/estimations/oecd_table1.dta", clear
global country "Brazil"
keep if partnerjurisdiction=="$country" & cbc=="EMPLOYEES" & grouping=="All Sub-Groups"
keep if ultimateparentjurisdiction!=partnerjurisdiction
keep ultimateparentjurisdiction value year
reshape wide value, i(ultimateparentjurisdiction) j(year)
rename ultimateparentjurisdiction country
graph bar (asis) value2016 value2017 value2018, over(country, label(angle(45))) ytitle("Reported employees") title("MNEs' reported employees in: $country") subtitle("Source: Aggregate CbCR data from OECD") legend(order (1 "2016" 2 "2017" 3 "2018") cols(3))
graph export "C:\Users\AlisonSchultz\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Reasons_for_changes_2017_to_2018\Figures\\${country}\employees_over_time_${country}.png", replace

*Misalignment at bilateral level
use "${path}/data/raw/estimations/oecd_table1.dta", clear
keep if cbc=="PROFIT" | cbc=="EMPLOYEES"
keep if grouping=="All Sub-Groups"
keep if year == 2017 | year == 2018
tostring year, gen(year_string)
gen bilateralyear=cou+jur+year_string
keep bilateralyear ultimateparentjurisdiction cou partnerjurisdiction jur year value cbc
reshape wide value, i(bilateralyear) j(cbc) string
bys cou year: egen tot_profit=total(valuePROFIT)
gen sh_profit_in_jur=(valuePROFIT/tot_profit)*100
replace sh_profit_in_jur = . if tot_profit < 0
bys cou year: egen tot_employees=total(valueEMPLOYEES)
gen sh_employees_in_jur=(valueEMPLOYEES/tot_employees)*100
rename ultimateparentjurisdiction country
levelsof partnerjurisdiction if partnerjurisdiction=="Brazil", l(jurs) /*Generating this for NLD only for now, as there is an error for countries without any data*/
levelsof year, l(years)
foreach jur of local jurs { 
foreach year of local years {
quietly: graph bar (asis) sh_profit_in_jur sh_employees_in_jur if partnerjurisdiction=="`jur'" & year==`year' & jur!=cou, ///
	over(country, label(angle(45))) ytitle("Share (%)") ///
	title("MNEs' misalignment: `jur', `year'") subtitle("Source: Aggregate CbCR data from OECD") ///
	legend(order (1 "Share of profits in `jur'" 2 "Share of employees in `jur'") cols(1))
graph export "C:\Users\AlisonSchultz\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Reasons_for_changes_2017_to_2018\Figures\\${country}\misalignment_`jur'_`year'.png", replace
}
}


/*
reshape wide sh_profit_in_jur sh_employees_in_jur, i(bilateralyear) j(year)

graph bar (asis) sh_profit_in_jur2016 sh_profit_in_jur2017 sh_profit_in_jur2018 ///
	sh_employees_in_jur2016 sh_employees_in_jur2017 sh_employees_in_jur2018, ///
	over(country, label(angle(45))) ytitle("Reported profits and employees") ///
	title("MNEs' reported profits and employees in: $country") subtitle("Source: Aggregate CbCR data from OECD") ///
	legend(order (1 "2016" 2 "2017" 3 "2018") cols(3))


