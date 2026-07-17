# %% [markdown]
# Bootstrap the gravity imputation to get standard errors on the UT misalignment
# estimates (García-Bernardo & Janský 2024 train 1000× on bootstrapped samples).
#
# For each seed s the full chain is re-run end to end, propagating imputation
# uncertainty into the country estimates:
#   1. impute_model.py  (GRAVITY_BOOT_SEED=s) — resample training cells, refit,
#      predict -> gravity_imputed_activity__boot{s}.csv
#   2. 2_disaggregate   (GRAVITY_BOOT_SEED=s)
#      -> cbcr_main_disaggregated__boot{s}.csv
#   3. 5_estimate       (RUN_DATASET=disaggregated, RUN_INPUT_FILE=that
#      file, RUN_OUTPUT_TOPIC=unitary_taxation_gravity_boot) -> country estimates
# Then per (iso_partner, year) we record mean / SE / 2.5–97.5% CI across draws.
#
# Heavy: each draw ≈ a few minutes. Set N_BOOT modestly (env) and scale up for
# a production run. Defaults pick the headline spec + reporter-only mode.

# %%
import glob
import os
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "src")
GR = os.path.join(SRC, "gravity")
PY = sys.executable

N_BOOT = int(os.environ.get("N_BOOT", "20"))
SEED0 = int(os.environ.get("BOOT_SEED0", "1"))   # seed 0 reserved for point est.
# Default FULL mode: imputation uncertainty only enters when imputed rows are
# used. In reporter-only mode (REPORTED_ONLY=1) the disaggregated rows are
# dropped, so bootstrapping the imputation yields ~0 SE by construction.
REPORTED = os.environ.get("REPORTED_ONLY", "0")
SPEC = os.environ.get(
    "BOOT_SPEC",
    "employees_payroll__etrdef_average__etrmax_inf__loss_cit_gain_etr",
)
TOPIC = "unitary_taxation_gravity_boot"
_sub = "_reported" if REPORTED not in ("0", "false", "False", "") else ""
# Resolve through config.output_dirs so the nested-layout remap applies
# (gravity_boot now lives under output/diagnostics/gravity_boot[...]/).
if SRC not in sys.path:
    sys.path.insert(0, SRC)
from config import output_dirs  # noqa: E402
EST_GLOB = str(output_dirs(f"{TOPIC}{_sub}")[0]
               / "disaggregated" / f"country_estimates__{SPEC}.csv")
METRIC = os.environ.get("BOOT_METRIC", "revenue_gain_from_ut")


def run(script, cwd, extra_env):
    env = dict(os.environ)
    env.update(extra_env)
    subprocess.run([PY, script], cwd=cwd, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# %%
draws = []
for s in range(SEED0, SEED0 + N_BOOT):
    run("impute_model.py", GR, {"GRAVITY_BOOT_SEED": str(s)})
    run("2_disaggregate_aggregated_values.py", SRC,
        {"GRAVITY_BOOT_SEED": str(s)})
    run("5_estimate_profit_shifting.py", SRC, {
        "RUN_DATASET": "disaggregated",
        "RUN_INPUT_FILE": f"cbcr_main_disaggregated__boot{s}.csv",
        "RUN_OUTPUT_TOPIC": TOPIC,
        "REPORTED_ONLY": REPORTED,
    })
    f = glob.glob(EST_GLOB)
    if not f:
        print(f"  seed {s}: estimate file not found, skipping")
        continue
    d = pd.read_csv(f[0])[["iso_partner", METRIC]]
    d = d.groupby("iso_partner", as_index=False)[METRIC].sum()
    d["seed"] = s
    draws.append(d)
    print(f"  seed {s} done ({len(draws)}/{N_BOOT})", flush=True)

# %%
alld = pd.concat(draws, ignore_index=True)
g = alld.groupby("iso_partner")[METRIC]
out = pd.DataFrame({
    "boot_mean": g.mean(),
    "boot_se": g.std(ddof=1),
    "ci_lo_2.5": g.quantile(0.025),
    "ci_hi_97.5": g.quantile(0.975),
    "n_draws": g.count(),
}).reset_index()
dest = os.path.join(ROOT, "output", "destination_sales", "tables",
                    f"gravity_bootstrap_SEs__{SPEC}.csv")
out.to_csv(dest, index=False)
print(f"\nBootstrap SEs: {len(out)} jurisdictions, {N_BOOT} draws, "
      f"{'reporter-only' if _sub else 'full'} mode -> "
      f"output/destination_sales/tables/{os.path.basename(dest)}")
print(out.sort_values("boot_mean").head(8).to_string(index=False))
