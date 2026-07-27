# Consolidated rerun — STAGE 2c: REPORTED-ONLY UT grid (user 2026-07-12:
# "reported only suffices for now"). Three scenarios x reported sample + s6.
# Scripts 2 and 4 already completed. Full-sample (gravity) passes deferred.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Start-Transcript -Path (Join-Path $PSScriptRoot "..\data\intermediate\rerun_stage2c.log") -Force

$datasets = @(
    @{ ds = "disaggregated";         topic = "unitary_taxation_disaggregated_reported" },
    @{ ds = "excl_resource";         topic = "unitary_taxation_excl_resource_reported" },
    @{ ds = "excl_resource_floored"; topic = "unitary_taxation_excl_resource_floored_reported" }
)
foreach ($d in $datasets) {
    $env:RUN_DATASET = $d.ds
    $env:REPORTED_ONLY = "1"
    Write-Output ("=== s5 {0} REPORTED=1 ===" -f $d.ds)
    python 5_estimate_profit_shifting.py
    if ($LASTEXITCODE -ne 0) { throw "s5 $($d.ds) failed ($LASTEXITCODE)" }
    Write-Output ("=== s6 {0} ===" -f $d.topic)
    python 6_winners_losers_analysis.py $d.topic
    if ($LASTEXITCODE -ne 0) { throw "s6 $($d.topic) failed ($LASTEXITCODE)" }
}
Remove-Item Env:RUN_DATASET, Env:REPORTED_ONLY -ErrorAction SilentlyContinue
Write-Output "STAGE 2C COMPLETE"
Stop-Transcript
