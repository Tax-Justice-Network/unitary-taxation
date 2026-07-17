# Resume STAGE 2c after the build_country_year_baselines fix: only the floored
# pass needs rerunning (passes 1-2 + their s6 completed; pass 3's spec files
# were all written but the run must re-execute to produce the baselines +
# run_summary consistently).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Start-Transcript -Path (Join-Path $PSScriptRoot "..\data\intermediate\rerun_stage2c_resume.log") -Force

$env:RUN_DATASET = "excl_resource_floored"
$env:REPORTED_ONLY = "1"
Write-Output "=== s5 excl_resource_floored REPORTED=1 (resume) ==="
python 5_estimate_profit_shifting.py
if ($LASTEXITCODE -ne 0) { throw "s5 excl_resource_floored failed ($LASTEXITCODE)" }
Write-Output "=== s6 unitary_taxation_excl_resource_floored_reported ==="
python 6_winners_losers_analysis.py unitary_taxation_excl_resource_floored_reported
if ($LASTEXITCODE -ne 0) { throw "s6 floored failed ($LASTEXITCODE)" }
Remove-Item Env:RUN_DATASET, Env:REPORTED_ONLY -ErrorAction SilentlyContinue
Write-Output "STAGE 2C RESUME COMPLETE"
Stop-Transcript
