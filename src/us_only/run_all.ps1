# Re-run ALL home-group UT figures (US / EU / all multinationals, CCCTB + SOTJ,
# ETR-max inf + 0.15) plus the combined US-vs-EU figures.
#
# Use this after updating the input data/2024/final/cbcr_main_disaggregated.csv.
# NO INTERNET is required — everything reads that local file, computes, and
# writes figures/tables to output/ and mirrors them to the shared folder.
#
# Run from the repository root, e.g.:
#   conda activate sotj_profit_shifting_estimates
#   powershell -ExecutionPolicy Bypass -File src\us_only\run_all.ps1
#
# GLOBAL is run FIRST for each formula so the US/EU figures can read the fresh
# all_multinationals files (the German "vs all MNEs" dashed boxes and the
# EU-loss-by-headquarters figures depend on them).

$ErrorActionPreference = "Stop"
foreach ($ff in @("ccctb", "employees_payroll")) {
    $env:FIG_FORMULA = $ff
    foreach ($hg in @("GLOBAL", "USA", "EU27")) {
        foreach ($em in @("inf", "0.15")) {
            $env:HOME_GROUP = $hg
            $env:ETR_MAX = $em
            Write-Host "=== $ff / $hg / $em ===" -ForegroundColor Cyan
            python src\us_only\estimate_us_multinationals.py
        }
    }
    # Combined US-vs-EU figures (uses FIG_FORMULA + ETR_MAX; HOME_GROUP ignored).
    Write-Host "=== combine $ff (inf, 0.15) ===" -ForegroundColor Cyan
    $env:ETR_MAX = "inf";  python src\us_only\combine_us_eu.py
    $env:ETR_MAX = "0.15"; python src\us_only\combine_us_eu.py
}
Write-Host "ALL DONE - 12 estimate runs + 4 combine runs" -ForegroundColor Green
