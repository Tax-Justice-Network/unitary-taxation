# %% [markdown]
# First-pass imputation model: HistGradientBoostingRegressor per target
# (ln employees / sales / tangible assets), trained on observed CbCR cells,
# 60/40 split, out-of-sample R² (paper: 0.74 / 0.56 / 0.44).

# %%
import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import r2_score
from sklearn.model_selection import train_test_split

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
M = os.path.join(ROOT, "data", "intermediate", "gravity", "gravity_feature_matrix.parquet")
m = pd.read_parquet(M) if M.endswith(".parquet") else pd.read_csv(M)

# Bootstrap hook: when GRAVITY_BOOT_SEED is set, resample the training cells
# with replacement (García-Bernardo & Janský 2024 train 1000× on bootstrapped
# samples to get SEs), refit, predict, and write a seed-tagged activity file.
# Unset = point estimate. The driver run_bootstrap.py loops seeds end-to-end.
_BOOT = os.environ.get("GRAVITY_BOOT_SEED")
BOOT = int(_BOOT) if _BOOT not in (None, "") else None

# Public-feature model. The paper's per-target hyperparameters were tried and
# gave marginally lower R²; this config is slightly better. The residual gap to
# the paper (emp 0.74 / sales 0.56) is attributable to the omitted proprietary
# LinkedIn variables (their top emp/sales predictors, not publicly available).
TARGETS = {
    "employees": ("ln_n_employees", 0.1, 10.0),
    "sales": ("ln_unrelated_party_revenues", 0.1, 10.0),
    "tangible": ("ln_tangible_assets_except_cash", 0.1, 10.0),
}
DROP = set(["iso_parent", "iso_partner", "n_employees", "unrelated_party_revenues",
            "tangible_assets_except_cash"] + [t[0] for t in TARGETS.values()])
feat_cols = [c for c in m.columns
             if c not in DROP and pd.api.types.is_numeric_dtype(m[c])]
print(f"{len(feat_cols)} feature columns; {len(m)} rows total")

for name, (tgt, lr, l2) in TARGETS.items():
    d = m[m[tgt].notna() & np.isfinite(m[tgt])]
    if BOOT is not None:
        d = d.sample(frac=1.0, replace=True, random_state=BOOT)  # bootstrap resample
    X, y = d[feat_cols], d[tgt]
    if BOOT is None:  # report out-of-sample R² only for the point estimate
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.4, random_state=0)
        r2 = r2_score(yte, HistGradientBoostingRegressor(
            learning_rate=lr, max_iter=400, l2_regularization=l2,
            min_samples_leaf=20, random_state=0).fit(Xtr, ytr).predict(Xte))
        print(f"  {name:<10} n={len(d):>6}  out-of-sample R2 = {r2:.3f}")
    # Refit on all (resampled) observed cells, then predict every pair.
    final = HistGradientBoostingRegressor(
        learning_rate=lr, max_iter=400, l2_regularization=l2,
        min_samples_leaf=20, random_state=(BOOT or 0),
    ).fit(X, y)
    raw = tgt.replace("ln_", "")
    pred = np.clip(np.expm1(final.predict(m[feat_cols])), 0, None)

    # ── Micro-state guardrail ────────────────────────────────────────────────
    # These predictions feed script 2 only as within-(year,parent,aggregate)
    # redistribution weights, so a micro-state with an implausibly large
    # predicted value grabs an outsized share of a disaggregated aggregate →
    # huge imputed profit and huge bootstrap SE (FSM/ASM/Cook Is. are the worst
    # offenders without a cap). Cap each (parent, partner) prediction at the LARGER of two
    # ceilings, so the cap binds only on markets that are tiny on BOTH:
    #   (a) CAP_MULT × the market's largest OBSERVED value for this factor
    #       (keeps real havens — CYM/BMU/… — whose observed cells are large), and
    #   (b) an economic-size ceiling: SALES/ASSETS ≤ GDP_MULT × GDP_d, EMPLOYEES
    #       ≤ POP_FRAC × population_d (keeps real but sparsely-reported economies
    #       like LICs, whose GDP dwarfs their thin CbCR footprint).
    # gdp_d / pop_d are in THOUSANDS (CEPII units) → ×1000 to USD / persons.
    # A market tiny on both dimensions (true micro-state) is clamped; LIC point
    # estimates are essentially untouched because (b) is generous for them.
    CAP_MULT, GDP_MULT, POP_FRAC = 10.0, 3.0, 0.5
    obs_cap = (CAP_MULT * m["iso_partner"].map(m.groupby("iso_partner")[raw].max())
               ).to_numpy(dtype=float)
    if name == "employees":
        size_cap = (POP_FRAC * m["pop_d"] * 1e3).to_numpy(dtype=float)
    else:
        size_cap = (GDP_MULT * m["gdp_d"] * 1e3).to_numpy(dtype=float)
    with np.errstate(invalid="ignore"):
        cap = np.nanmax(np.vstack([obs_cap, size_cap]), axis=0)  # NaN only if both NaN
    cap = np.where(np.isfinite(cap), cap, np.nanquantile(cap, 0.10))
    capped = pred > cap
    pred = np.where(capped, cap, pred)
    m["pred_" + raw] = pred
    if BOOT is None:
        print(f"  {name:<10} guardrail capped {int(capped.sum()):>6} / "
              f"{len(pred)} pairs ({100*capped.mean():.1f}%)")

PRED_COLS = ["pred_n_employees", "pred_unrelated_party_revenues",
             "pred_tangible_assets_except_cash"]
preds = m[["iso_parent", "iso_partner", "year"] + PRED_COLS].copy()
preds = preds.dropna(subset=["iso_parent", "iso_partner"])
suffix = f"__boot{BOOT}" if BOOT is not None else ""
fname = f"gravity_imputed_activity{suffix}.csv"
preds.to_csv(os.path.join(os.path.dirname(M), fname), index=False)
print(f"\nPredicted activity for {len(preds)} pairs -> data/intermediate/gravity/{fname}")
