**Analyze new results for SOTJ23

import excel using "C:\Users\15671304\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Tax avoidance\2017_tax_avoidance_sotj_table.xlsx", first clear
rename * *_2017
rename Name_2017 country
drop if MNCs_2017=="0"
rename MNCs_2017 MNCs
save "2017_tax_avoidance_sotj_table.dta", replace

import excel using "C:\Users\15671304\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Tax avoidance\2018_tax_avoidance_sotj_table.xlsx", first clear
rename * *_old
rename Name_old country
drop if MNCs_old=="0"
rename MNCs_old MNCs
save "2018_tax_avoidance_sotj_table_DaniNov.dta", replace


import excel using "C:\Users\15671304\Github repositories\sotj_profit_shifting_estimates\data\final\analysis\2018_tax_avoidance_sotj_table_new.xlsx", first clear
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
replace diff_old2017=ProfitlossM_old if ProfitlossM_2017==.
gen diff_new2017 = ProfitlossM_new - ProfitlossM_2017
replace diff_new2017=ProfitlossM_old if ProfitlossM_new==.

br country MNCs diff* ProfitlossM* 

if diff_old2017>diff_new2017


br 
