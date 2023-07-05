**Analyze new results for SOTJ23

import excel using "C:\Users\15671304\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Tax avoidance\2018_tax_avoidance_sotj_table.xlsx", first clear
rename * *_old
rename Name_old country
drop if MNCs_old=="0"
save "C:\Users\15671304\Tax Justice Network Ltd\TJN - Shared Documents\Workstreams\Scale of Tax Injustice\State of Tax Justice report\2023 Report\Tax avoidance\2018_tax_avoidance_sotj_table.xlsx"


import excel using "C:\Users\15671304\Github repositories\sotj_profit_shifting_estimates\data\final\analysis\2018_tax_avoidance_sotj_table_new.xlsx", first clear
rename * *_new
rename Name_new country
drop if MNCs_new=="0"

