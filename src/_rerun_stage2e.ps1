# Consolidated rerun — STAGE 2e (2026-07-12): destination-measure revision.
# The headline destination key changed to all-MNE sales + the MNE SHARE of BaTIS
# digitally-deliverable imports (destmnedds); the ADS-proxy leg was retired.
# Script 1b has already been rerun. This chain propagates the new columns:
#   2 (disaggregate, merges 1b columns) -> 4 (resource datasets)
#   -> 5 x 3 scenarios (REPORTED sample) -> 6 per scenario.
# Full-sample (gravity) passes remain deferred to stage 2d (run AFTER this).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Start-Transcript -Path (Join-Path $PSScriptRoot "..\data\intermediate\rerun_stage2e.log") -Force

Write-Output "=== s2 disaggregate ==="
python 2_disaggregate_aggregated_values.py
if ($LASTEXITCODE -ne 0) { throw "s2 failed ($LASTEXITCODE)" }

Write-Output "=== s4 resource correction ==="
python 4_correcting_cbcr_for_resource_payments.py
if ($LASTEXITCODE -ne 0) { throw "s4 failed ($LASTEXITCODE)" }

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
Write-Output "STAGE 2E COMPLETE"
Stop-Transcript
