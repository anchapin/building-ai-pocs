# Differentiable Neural-Operator Surrogate

**Status:** POC CLOSED — verdict **No-go** (slice 3: shared-encoder arm + parameter-mismatch experiment + verdict). See `REPORT.md`.

Differentiable neural-operator / PINN surrogate for a slow BEM component, standalone — clean digital comparison vs the SS-DFA POC.

See the repo README for the POC rules: 25–40 hours, standalone, fixed go/no-go gate, REPORT.md leading with exactly one label (Go, Go (software only), Conditional, or No-go).

## Reproduce slice 1 (CPU-only)

```sh
python -m venv .venv && .venv/bin/pip install -q -r neural-operator-surrogate/requirements.txt
.venv/bin/python neural-operator-surrogate/src/gen_data.py --seed 42
.venv/bin/python neural-operator-surrogate/src/train.py --seed 42
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # headline table
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # determinism rerun: byte-identical output
.venv/bin/python -m pytest neural-operator-surrogate/tests/ -q          # 20 passed
```

Slice-1 headline (seed 42, free-running rollout): MLP in-distribution
RMSE_T 3.84 °C, unseen weather 6.75 °C, unseen setpoint 4.38 °C;
heat-balance residual 33–54% (RC ground truth ~1e-14%). Full table and the
two defects fixed in review are in `REPORT.md`.

## Reproduce slice 2 (CPU-only)

```sh
.venv/bin/python neural-operator-surrogate/src/train.py --seed 42 --arm pinn
.venv/bin/python neural-operator-surrogate/src/train.py --seed 42 --arm pinn --branch-offset 1 --out-dir neural-operator-surrogate/data_off1   # information-matched ablation
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # headline table with PINN rows + gate summary
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # determinism rerun: byte-identical output
.venv/bin/python -m pytest neural-operator-surrogate/tests/ -q          # 20 passed
```

Slice-2 headline (seed 42, free-running rollout): PINN in-distribution
RMSE_T 0.64 °C (MLP 3.84 °C); unseen weather 5.52 °C (MLP 6.75 °C, gate
NOT met at -18%); unseen setpoint 1.50 °C (MLP 4.38 °C, gate MET at
-66%). Heat-balance residual <5% gate NOT MET on any split; speedup vs
EnergyPlus measured ~1× (0.9–1.2× across runs; ≥50× gate NOT MET). Full table, the ablation,
and the caveats are in `REPORT.md`. EnergyPlus itself is not committed;
to re-measure the speedup, extract the official EnergyPlus 26.2.0 Linux
tarball and run
`.venv/bin/python neural-operator-surrogate/src/benchmark_speedup.py --eplus-dir <install root>`.

## Reproduce slice 3 (CPU-only)

```sh
.venv/bin/python neural-operator-surrogate/src/train.py --seed 42 --arm shared
.venv/bin/python neural-operator-surrogate/src/train.py --seed 42 --arm shared --rc-params nominal
.venv/bin/python neural-operator-surrogate/src/train.py --seed 42 --arm pinn --rc-params nominal   # parameter-mismatch experiment
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # headline table with shared + nominal rows, gate summary, mismatch table
.venv/bin/python neural-operator-surrogate/src/evaluate.py --seed 42   # determinism rerun: byte-identical output
.venv/bin/python -m pytest neural-operator-surrogate/tests/ -q          # 25 passed
```

Slice-3 headline (seed 42, free-running rollout): PINN with NOMINAL
parameters meets the ≥20% extrapolation gate on all three unseen splits
(weather 4.55 °C vs MLP 6.75 °C; setpoint 1.67 °C vs 4.38 °C; both 4.34 °C
vs 6.13 °C) — the only honest arm to do so. Heat-balance residual <5%
gate NOT MET anywhere (best honest 7.8% in-distribution, 51–73% on unseen
weather/both); speedup ≥50× NOT MET (standing ~1×, not re-tested — no
vectorised rollout was built). SharedEnc-RC with TRUE base parameters
prints 0.0000 °C / ~0% everywhere but is DISQUALIFIED as a tautology: an
untrained shared encoder reproduces the RC reference exactly, so it
contains the generative model rather than learning it. With NOMINAL base
parameters it matches the untrained nominal RC (val 0.606 vs 0.625 °C) —
the encoder learns ~nothing. Verdict: **No-go**. Full table, the
mismatch experiment, and the reasoning are in `REPORT.md`.
