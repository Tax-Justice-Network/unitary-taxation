# STAGE 2d: FULL-SAMPLE (gravity-imputed, REPORTED_ONLY=0) UT grid + s6 —
# run after all specification choices were locked (2026-07-12): complete
# destination measure, domfor ETR, LIC/LMIC royalty gate, floored-baseline fix.
# These are the heavy passes (~3-6x the reported sample); run in a user
# terminal. Log: data/intermediate/rerun_stage2d.log
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Start-Transcript -Path (Join-Path $PSScriptRoot "..\data\intermediate\rerun_stage2d.log") -Force

$datasets = @(
    @{ ds = "disaggregated";         topic = "unitary_taxation_disaggregated" },
    @{ ds = "excl_resource";         topic = "unitary_taxation_excl_resource" },
    @{ ds = "excl_resource_floored"; topic = "unitary_taxation_excl_resource_floored" }
)
foreach ($d in $datasets) {
    $env:RUN_DATASET = $d.ds
    $env:REPORTED_ONLY = "0"
    Write-Output ("=== s5 {0} REPORTED=0 ===" -f $d.ds)
    python 5_estimate_profit_shifting.py
    if ($LASTEXITCODE -ne 0) { throw "s5 $($d.ds) failed ($LASTEXITCODE)" }
    Write-Output ("=== s6 {0} ===" -f $d.topic)
    python 6_winners_losers_analysis.py $d.topic
    if ($LASTEXITCODE -ne 0) { throw "s6 $($d.topic) failed ($LASTEXITCODE)" }
}
Remove-Item Env:RUN_DATASET, Env:REPORTED_ONLY -ErrorAction SilentlyContinue
Write-Output "STAGE 2D COMPLETE"
Stop-Transcript
