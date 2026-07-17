# Consolidated rerun — STAGE 1: cleaning -> destination sales -> disaggregation.
# (Stage 2 = _run_pipeline.py: 4 -> 5 x datasets x samples -> 6 -> 8; then 9-series.)
# Launched 2026-07-12. Log: data/intermediate/rerun_stage1.log (via Tee below).
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python 1_clean.py
if ($LASTEXITCODE -ne 0) { throw "1_clean failed ($LASTEXITCODE)" }
python 1b_destination_based_sales.py
if ($LASTEXITCODE -ne 0) { throw "1b failed ($LASTEXITCODE)" }
python 2_disaggregate_aggregated_values.py
if ($LASTEXITCODE -ne 0) { throw "2_disaggregate failed ($LASTEXITCODE)" }
Write-Output "STAGE 1 COMPLETE"
