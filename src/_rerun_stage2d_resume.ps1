# STAGE 2D RESUME (after the disk-full crash 2026-07-13): the gravity baseline
# and excl_resource scenarios completed incl. their s6 passes — only the floored
# scenario's s5 died mid-write (its partial outputs were deleted; completed
# scenarios' misalignment files were gzip-compressed in place to free space).
# Reruns s5 + s6 for the FLOORED gravity scenario only.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Start-Transcript -Path (Join-Path $PSScriptRoot "..\data\intermediate\rerun_stage2d_resume.log") -Force

$env:RUN_DATASET = "excl_resource_floored"
$env:REPORTED_ONLY = "0"
Write-Output "=== s5 excl_resource_floored REPORTED=0 ==="
python 5_estimate_profit_shifting.py
if ($LASTEXITCODE -ne 0) { throw "s5 excl_resource_floored failed ($LASTEXITCODE)" }
Write-Output "=== s6 unitary_taxation_excl_resource_floored ==="
python 6_winners_losers_analysis.py unitary_taxation_excl_resource_floored
if ($LASTEXITCODE -ne 0) { throw "s6 failed ($LASTEXITCODE)" }

Remove-Item Env:RUN_DATASET, Env:REPORTED_ONLY -ErrorAction SilentlyContinue
Write-Output "STAGE 2D COMPLETE"
Stop-Transcript
