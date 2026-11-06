# Differentiable Neural-Operator Surrogate

**Status:** Slice 1 done (differentiable 2R2C model + synthetic data + MLP baseline + eval harness). No Go/no-go verdict yet — see `REPORT.md`.

Differentiable neural-operator / PINN surrogate for a slow BEM component, standalone — clean digital comparison vs the SS-DFA POC.

See the repo README for the POC rules: 25–40 hours, standalone, fixed go/no-go gate, REPORT.md leading with exactly one label (Go, Go (software only), Conditional, or No-go).

## Reproduce slice 1 (CPU-only)

```sh
python -m venv .venv && .venv/bin/pip install -q -r neural-operator-surrogate/requirements.txt
.venv/bin/python neural-operator-surrogate/src/gen_data.py --seed 42
.venv/bin/python neural-operator-surrogate/src/train.py --seed 42
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # headline table
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # determinism rerun: byte-identical output
.venv/bin/python -m pytest neural-operator-surrogate/tests/ -q          # 16 passed
```

Slice-1 headline (seed 42, free-running rollout): MLP in-distribution
RMSE_T 3.84 °C, unseen weather 6.75 °C, unseen setpoint 4.38 °C;
heat-balance residual 33–54% (RC ground truth ~1e-14%). Full table and the
two defects fixed in review are in `REPORT.md`.
