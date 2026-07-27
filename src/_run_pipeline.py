"""Orchestrator: run scripts 3_38 → 4 → 5 (× dataset/reported combos) → 6.

Each script-5 pass runs as a subprocess with RUN_DATASET and REPORTED_ONLY
set via environment variables, keeping the per-run topic naming so the
downstream report scripts pick up the outputs.
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


# Env vars that narrow/widen script 5's spec grid. A value lingering from an
# earlier shell session (e.g. a DEST_SUBSET fast run or the bootstrap driver's
# ETR_THRESHOLDS) would silently change every canonical pass, so the child env
# is scrubbed of them unless this orchestrator sets them explicitly.
_SCRUB_ENV = ("DEST_SUBSET", "ETR_THRESHOLDS", "RUN_DATASET", "REPORTED_ONLY")


def run(label: str, cmd: list, env_extra: dict | None = None,
        cwd: str | None = None):
    print(f"\n=== {label} ===", flush=True)
    env = os.environ.copy()
    for k in _SCRUB_ENV:
        env.pop(k, None)
    if env_extra:
        env.update(env_extra)
    # Bare "python" would pick up whatever is first on PATH; run the stages
    # with the same interpreter as the orchestrator.
    if cmd and cmd[0] == "python":
        cmd = [sys.executable] + cmd[1:]
    rc = subprocess.run(cmd, env=env, cwd=cwd)
    if rc.returncode != 0:
        # Fail FAST: a failed stage means every later stage would silently run
        # on stale previous-vintage inputs and end with a misleading ALL DONE.
        print(f"  FAILED (rc={rc.returncode}) — aborting pipeline", flush=True)
        sys.exit(rc.returncode)
    return True


print(f"WD: {os.getcwd()}", flush=True)
print(f"START: {time.strftime('%H:%M:%S')}", flush=True)

# Step 1: regenerate the resource_payments aggregation.
# Script uses relative paths from its own dir, so cwd needs to match.
ext_prep_dir = str(src_dir / "3_extractive_prep")
run("3_38 resource_payments aggregation",
    ["python", "3_38_resource_payments_by_hq_source.py"],
    cwd=ext_prep_dir)

# Step 2: script 4 — correcting CbCR for resource payments
run("script 4 correcting CbCR",
    ["python", "4_correcting_cbcr_for_resource_payments.py"])

# Step 3: script 5 over the datasets × {REPORTED False/True}, with s6 after each
datasets = ["disaggregated", "excl_resource", "excl_resource_floored",
            "excl_resource_floored_allrowsalloc",   # floor-allocation sensitivity
            "incl_resource"]
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
            "excl_resource_floored_allrowsalloc": "unitary_taxation_excl_resource_floored_allrowsalloc",
            "incl_resource": "unitary_taxation_incl_resource",
        }[ds]
        topic = topic_base + ("_reported" if rep else "")
        run(f"s5 ({i}/{total}) {ds} REPORTED={rep}",
            ["python", "5_estimate_profit_shifting.py"],
            env_extra={"RUN_DATASET": ds, "REPORTED_ONLY": "1" if rep else "0"})
        run(f"s6 ({i}/{total}) {topic}",
            ["python", "6_consolidate_country_estimates.py", topic])

# The pipeline ends here (script 6 = per-scenario consolidation). The
# scenario comparison and every figure/table are EXHIBIT scripts — the shared
# machinery is _scenario_machinery.py; run 7c_resource_rights.py or the
# paper drivers separately.

print(f"\nEND: {time.strftime('%H:%M:%S')}", flush=True)
print("ALL DONE", flush=True)
