# Consolidated rerun — STAGE 2: disaggregation remerge -> resource correction
# (LIC/LMIC royalty gate) -> UT grid (domfor ETR + destmne/destmnebilat tags +
# floored-baseline fix) -> winners/losers consolidation.
# incl_resource is skipped (annex-only, standing decision); script 8 is left to
# stage 3 alongside the 9-series.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

python 2_disaggregate_aggregated_values.py
if ($LASTEXITCODE -ne 0) { throw "2_disaggregate failed ($LASTEXITCODE)" }

python 4_correcting_cbcr_for_resource_payments.py
if ($LASTEXITCODE -ne 0) { throw "4_correcting failed ($LASTEXITCODE)" }

$datasets = @(
    @{ ds = "disaggregated";         topic = "unitary_taxation_disaggregated" },
    @{ ds = "excl_resource";         topic = "unitary_taxation_excl_resource" },
    @{ ds = "excl_resource_floored"; topic = "unitary_taxation_excl_resource_floored" }
)
foreach ($d in $datasets) {
    foreach ($rep in @("0", "1")) {
        $env:RUN_DATASET = $d.ds
        $env:REPORTED_ONLY = $rep
        Write-Output ("=== s5 {0} REPORTED={1} ===" -f $d.ds, $rep)
        python 5_estimate_profit_shifting.py
        if ($LASTEXITCODE -ne 0) { throw "s5 $($d.ds) rep=$rep failed ($LASTEXITCODE)" }
        $topic = $d.topic + $(if ($rep -eq "1") { "_reported" } else { "" })
        Write-Output ("=== s6 {0} ===" -f $topic)
        python 6_winners_losers_analysis.py $topic
        if ($LASTEXITCODE -ne 0) { throw "s6 $topic failed ($LASTEXITCODE)" }
    }
}
Remove-Item Env:RUN_DATASET, Env:REPORTED_ONLY -ErrorAction SilentlyContinue
Write-Output "STAGE 2 COMPLETE"
