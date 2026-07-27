# STAGE 2e RESUME (after the disk-full crash 2026-07-12): scenarios 1-2
# (disaggregated, excl_resource) completed incl. their s6 pass — only the
# floored scenario's s5 died mid-write. Reruns s5 + s6 for floored only.
# (Scripts 2 and 4 completed before the crash; do NOT rerun them.)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Start-Transcript -Path (Join-Path $PSScriptRoot "..\data\intermediate\rerun_stage2e_resume.log") -Force

$env:RUN_DATASET = "excl_resource_floored"
$env:REPORTED_ONLY = "1"
Write-Output "=== s5 excl_resource_floored REPORTED=1 ==="
python 5_estimate_profit_shifting.py
if ($LASTEXITCODE -ne 0) { throw "s5 excl_resource_floored failed ($LASTEXITCODE)" }
Write-Output "=== s6 unitary_taxation_excl_resource_floored_reported ==="
python 6_winners_losers_analysis.py unitary_taxation_excl_resource_floored_reported
if ($LASTEXITCODE -ne 0) { throw "s6 failed ($LASTEXITCODE)" }

Remove-Item Env:RUN_DATASET, Env:REPORTED_ONLY -ErrorAction SilentlyContinue
Write-Output "STAGE 2E COMPLETE"
Stop-Transcript
