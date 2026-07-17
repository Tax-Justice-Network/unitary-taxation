"""Orchestrator: run scripts 1_8 → 4 → 5 (× 8 dataset/reported combos) → 8.

For each script-5 pass, we patch RUN_DATASET and REPORTED_ONLY in
5_estimate_profit_shifting.py via in-memory dict, then importlib.reload.
This keeps the existing per-run topic naming so script 8 picks up the new
outputs.
"""
import sys
import os
import time
import subprocess
from pathlib import Path

src_dir = Path(__file__).resolve().parent
os.chdir(src_dir)
sys.path.insert(0, str(src_dir))
sys.path.insert(0, str(src_dir / "3_extractive_prep"))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def run(label: str, cmd: list, env_extra: dict | None = None,
        cwd: str | None = None):
    print(f"\n=== {label} ===", flush=True)
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    rc = subprocess.run(cmd, env=env, cwd=cwd)
    if rc.returncode != 0:
        print(f"  FAILED (rc={rc.returncode})", flush=True)
    return rc.returncode == 0


print(f"WD: {os.getcwd()}", flush=True)
print(f"START: {time.strftime('%H:%M:%S')}", flush=True)

# Step 1: regenerate resource_payments using newly enriched operator data
# Script uses relative paths from its own dir, so cwd needs to match.
ext_prep_dir = str(src_dir / "3_extractive_prep")
run("1_8 resource_payments aggregation",
    ["python", "1_8_resource_payments_by_hq_source.py"],
    cwd=ext_prep_dir)

# Step 2: script 4 — correcting CbCR for resource payments
run("script 4 correcting CbCR",
    ["python", "4_correcting_cbcr_for_resource_payments.py"])

# Step 3: script 5 over all 4 datasets × {REPORTED False/True}, with s6 after each
datasets = ["disaggregated", "excl_resource", "excl_resource_floored", "incl_resource"]
i = 0
total = len(datasets) * 2
for ds in datasets:
    for rep in (False, True):
        i += 1
        # Map (dataset, reported) → output topic for s6 consolidation
        topic_base = {
            "disaggregated": "unitary_taxation_disaggregated",
            "excl_resource": "unitary_taxation_excl_resource",
            "excl_resource_floored": "unitary_taxation_excl_resource_floored",
            "incl_resource": "unitary_taxation_incl_resource",
        }[ds]
        topic = topic_base + ("_reported" if rep else "")
        run(f"s5 ({i}/{total}) {ds} REPORTED={rep}",
            ["python", "5_estimate_profit_shifting.py"],
            env_extra={"RUN_DATASET": ds, "REPORTED_ONLY": "1" if rep else "0"})
        run(f"s6 ({i}/{total}) {topic}",
            ["python", "6_winners_losers_analysis.py", topic])

# Step 4: script 8 — five-scenario report
run("script 8 five-scenario report",
    ["python", "8_five_scenario_report.py"])

print(f"\nEND: {time.strftime('%H:%M:%S')}", flush=True)
print("ALL DONE", flush=True)
