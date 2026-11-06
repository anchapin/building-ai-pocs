# Differentiable Neural-Operator Surrogate

**Status:** Slice 2 done (PINN / PI-DeepONet arm + information-matched ablation + EnergyPlus speedup measurement). No Go/no-go verdict yet — see `REPORT.md`.

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
