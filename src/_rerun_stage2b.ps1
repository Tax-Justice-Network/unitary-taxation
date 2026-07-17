# Consolidated rerun — STAGE 2b: resume after the domfor aggregation fix.
# Scripts 2 and 4 already completed in stage 2; this reruns the UT grid + s6.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

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
Write-Output "STAGE 2B COMPLETE"
