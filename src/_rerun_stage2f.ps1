# Consolidated rerun — STAGE 2f (2026-07-12): ex-IP promoted to the HEADLINE
# destination measure. `mne_plus_dds_share` (tag destmnedds) now EXCLUDES SH /
# charges for the use of IP from the deliverable-services leg; the IP-inclusive
# full Handbook aggregate becomes the sensitivity (destmneddsinclip).
# Script 1b has already been rerun. Chain: 2 -> 4 -> 5 x 3 (REPORTED) -> 6.
# Gravity (stage 2d) runs AFTER this.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Start-Transcript -Path (Join-Path $PSScriptRoot "..\data\intermediate\rerun_stage2f.log") -Force

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
Write-Output "STAGE 2F COMPLETE"
Stop-Transcript
