# Neural-operator surrogate POC — slice 1 note

This is a **slice note, not the POC verdict**. No Go / Go (software only) /
Conditional / No-go label belongs here: the physics-informed arm and the
EnergyPlus speedup comparison do not exist yet, and the label belongs to the
full-POC verdict in a later slice. What follows is what slice 1 built, what it
measured, and what it explicitly does not claim.

## What slice 1 built

All work lives in `neural-operator-surrogate/` (standalone, CPU-only, no
Fluxion integration, no EnergyPlus, no ASHRAE 140 claim):

- `src/rc_model.py` — differentiable 2R2C zone thermal model in PyTorch, with
  a pure-numpy reference rollout (torch-vs-numpy agreement ≤ 1e-6, tested)
  and autograd gradients flowing through a rollout (tested).
- `src/gen_data.py` — synthetic data generated FROM THE RC MODEL ITSELF
  (self-consistent ground truth). 16 train / 8 val / 8 test_id series of 720
  hourly steps; the test splits hold out one weather pattern and one setpoint
  schedule entirely (extrapolation split, leakage-tested).
- `src/models.py` + `src/train.py` — plain-MLP baseline (issue #3 arm (a)):
  window 12, hidden [128, 128], 25,985 parameters, 60 epochs, seed 42.
  One-step RMSE: train 0.0911 / val 0.1096 / test_id 0.1137 °C.
- `src/evaluate.py` — one-command headline table (free-running rollout, not
  teacher-forced): per-split RMSE/MAE for zone temperature and HVAC load,
  heat-balance residual, and peak-load error reported separately.

## Headline table (seed 42, reproduced from a clean run; evaluate re-run is byte-identical)

| split | arm | Nser | RMSE_T [°C] | MAE_T [°C] | RMSE_Q [W] | HBresid [%] | PeakQerr [%] |
|---|---|---|---|---|---|---|---|
| val (in-dist) | RC reference | 8 | 0.0000 | 0.0000 | 0.00 | 4.4e-14 | 0.000 |
| val (in-dist) | MLP (plain) | 8 | 3.8384 | 2.2012 | 134.79 | 37.63 | 58.956 |
| test_id (in-dist) | MLP (plain) | 8 | 3.8502 | 2.1513 | 130.42 | 36.01 | 19.842 |
| test_weather (UNSEEN) | MLP (plain) | 4 | 6.7486 | 5.4324 | 391.96 | 53.73 | -5.548 |
| test_setpoint (UNSEEN) | MLP (plain) | 4 | 4.3799 | 3.3811 | 181.53 | 32.75 | 87.505 |
| test_both (UNSEEN) | MLP (plain) | 2 | 6.1342 | 5.2697 | 316.03 | 49.10 | 18.955 |

Reading: the MLP's free-running error roughly doubles on unseen weather
(3.84 → 6.75 °C) and grows on unseen setpoints (→ 4.38 °C); its
heat-balance residual is 33–54% on every split (the RC ground truth is
~1e-14%), and its peak-load error reaches 87.5% on unseen setpoints — a
surrogate this far off on peak load would be useless for sizing, which is
exactly why the POC reports peak error separately. These are baseline
numbers for the PINN arm to beat, not a verdict on the idea.

## Two defects found and fixed during supervisor review

1. **Pooled-RMSE aggregation bug** (`evaluate.py:aggregate`): the code took
   `mean` of per-series squared errors and then divided by total steps again,
   understating every RMSE in the table by √n_series (val RMSE_T was reported
   as 1.36 °C; the correct pooled value is 3.84 °C — the MAE column was
   correct, which is how the bug was caught: MAE exceeded RMSE, impossible
   for a correct computation). Fixed to `sqrt(sum(rmse_i²·n_i)/sum(n_i))`,
   with a regression test asserting the pooled value equals the direct
   computation and RMSE ≥ MAE on every row.
2. **Delta-target divergence**: the worker's mid-run rewrite of `train.py`
   switched the default target to `delta` with a docstring claim that it
   "keeps the free-running rollout from drifting". Measured: the
   delta-trained model DIVERGES on 5 of 8 validation series (RMSE_T up to
   1e33 °C, blow-up from step ~150), while the level-trained model stays
   bounded on every split. One-step teacher-forced RMSE is similar for both
   (val 0.11 vs 0.09 °C), so this is a rollout property, not a fit property.
   The default is restored to `level` (reproducing the worker's original
   one-step numbers exactly), the false docstring claim is corrected, and
   `evaluate.py` now reads the target parameterisation from `model.pt` and
   prints it — a delta model rolled out as level (or vice versa) misreports
   or diverges, so the wiring is tested, not assumed.

## Determinism

`gen_data.py --seed 42`, `train.py --seed 42`, then `evaluate.py --seed 42`
twice: byte-identical headline tables (diff empty). Training itself is
seeded (seed 42, 1 thread); re-running the whole pipeline reproduces the
one-step RMSEs exactly (0.0911 / 0.1096 / 0.1137 °C).

## NOT claimed in this slice

1. No physics-informed / neural-operator arm exists yet, so no extrapolation
   win factor (the issue's ≥20% gate is untested).
2. No EnergyPlus baseline (not installed on this machine; not attempted), so
   no speed-up factor (the issue's ≥50× gate is untested).
3. No Go / Conditional / No-go verdict — that label belongs to the full POC.

## What slice 2 should do

- Add the PINN / PI-DeepONet arm (issue #3 arm (b)) on identical data, with
  the heat-balance residual in the loss — and train it with a multi-step
  (rollout) loss component, because one-step training is what makes the
  delta parameterisation diverge and leaves the level model at 3.84 °C
  free-running error.
- Add the EnergyPlus data step (example files, e.g. 5ZoneAirCooled) so the
  ≥50× speedup gate can be measured; until then, speedup is not a number.
- Keep the level target as the shared default for every arm until a
  multi-step-trained delta arm proves itself stable.

---

# Neural-operator surrogate POC — slice 2 note

This is a **slice note, not the POC verdict**. No Go / Go (software only) /
Conditional / No-go label belongs here: the shared-encoder RC arm (issue #3
arm (c)) does not exist yet, and the label belongs to the full-POC verdict
in a later slice.

## What slice 2 built

- `src/models.py` — `PINNZone`, a DeepONet-style trunk/branch network
  (trunk = state history window, branch = driving inputs of the step being
  predicted, prediction = scaled inner product + bias), plus
  `pinn_rollout_torch`, a differentiable free-running rollout that also
  returns the per-step heat-balance residual from the 2R2C equations, and
  `build_branch(..., offset=...)` for the information-matched ablation.
- `src/train.py` — `--arm pinn` (60 epochs, seed 42, `level` target):
  loss = one-step MSE + multi-step rollout MSE (24-step horizon) +
  heat-balance-residual MSE (in W, normalised by `--phys-scale` 100 W).
  New `--branch-offset` flag: 0 = branch sees the drivers of the step
  being predicted (default, what the physics residual needs); 1 = branch
  sees the previous step's drivers, i.e. exactly the information the
  plain-MLP window contains.
- `src/evaluate.py` — headline table extended with the PINN arm on the
  same splits and metrics, a second PHYSICS-ALIGNED metrics block (implied
  HVAC load and mass-node dynamics evaluated on the PRE-step zone
  temperature, as the RC model does — the slice-1 metric uses the
  post-step temperature, which scores the exact ground truth at 0.02–2.96%
  instead of ~1e-14%), a GATE SUMMARY (≥20% extrapolation reduction,
  <5% heat-balance residual), and `headline_table.json` now holds both
  blocks (`{"summary": [...], "aligned": [...]}`).
- `src/benchmark_speedup.py` — measures the surrogate's batched 5-zone
  annual rollout and, when an EnergyPlus binary is supplied, the
  5ZoneAirCooled full-year run; prints the speedup with its scope.
- `tests/test_pinn.py` — 4 new tests: branch-offset alignment (regression
  test for a supervisor-found bug: the original `build_branch` returned
  one row too many for offset 1), residual of the exact RC trajectory
  ~0 through `pinn_rollout_torch`, rollout determinism/finiteness/
  warm-start, checkpoint round-trip of `branch_offset`.
- EnergyPlus 26.2.0 installed from the official Ubuntu 24.04 tarball
  (downloaded by the slice-2 worker) and run on this machine — see
  "Speedup" below. The install itself is not committed (gitignored
  `data/energyplus/`); `benchmark_speedup.py` documents how to reproduce it.

## Headline table (seed 42; evaluate re-run is byte-identical)

Legacy metrics (same as slice 1). The physics-aligned block and the gate
summary are in the full `evaluate.py` output.

| split | arm | RMSE_T [°C] | RMSE_Q [W] | HBresid [%] | PeakQerr [%] |
|---|---|---|---|---|---|
| val (in-dist) | MLP (plain) | 3.8384 | 134.79 | 37.63 | 58.956 |
| val (in-dist) | PINN (offset 0) | 0.6429 | 45.81 | 8.20 | -5.767 |
| val (in-dist) | PINN (offset 1, info-matched) | 0.6708 | 46.16 | 9.77 | -8.879 |
| test_id (in-dist) | MLP (plain) | 3.8502 | 130.42 | 36.01 | 19.842 |
| test_id (in-dist) | PINN (offset 0) | 0.6391 | 44.42 | 8.02 | -5.410 |
| test_id (in-dist) | PINN (offset 1, info-matched) | 0.6523 | 43.61 | 9.02 | -10.227 |
| test_weather (UNSEEN) | MLP (plain) | 6.7486 | 391.96 | 53.73 | -5.548 |
| test_weather (UNSEEN) | PINN (offset 0) | 5.5170 | 417.29 | 71.88 | -50.585 |
| test_weather (UNSEEN) | PINN (offset 1, info-matched) | 6.4792 | 467.98 | 75.48 | -48.291 |
| test_setpoint (UNSEEN) | MLP (plain) | 4.3799 | 181.53 | 32.75 | 87.505 |
| test_setpoint (UNSEEN) | PINN (offset 0) | 1.4995 | 70.33 | 11.47 | 18.671 |
| test_setpoint (UNSEEN) | PINN (offset 1, info-matched) | 2.1736 | 124.36 | 13.09 | 118.803 |
| test_both (UNSEEN) | MLP (plain) | 6.1342 | 316.03 | 49.10 | 18.955 |
| test_both (UNSEEN) | PINN (offset 0) | 5.6610 | 421.06 | 72.62 | -44.674 |
| test_both (UNSEEN) | PINN (offset 1, info-matched) | 6.8117 | 454.83 | 75.31 | -48.415 |

PINN training (seed 42, 60 epochs): one-step RMSE train 0.141 / val 0.184 /
test_id 0.187 °C (worse than the MLP's 0.091/0.110/0.114 — the PINN
optimises rollout + physics, not one-step fit); free-running val rollout
RMSE 0.643 °C (offset 0) / 0.671 °C (offset 1).

Gate summary (issue #3, PINN offset 0 vs MLP, physics-aligned HB residual):
- Extrapolation ≥20% RMSE reduction: setpoint MET (-65.8%); weather NOT MET
  (-18.3%); both NOT MET (-7.7%).
- Heat-balance residual <5%: NOT MET on every split (7.8% val, 7.6%
  test_id, 71.3% weather, 11.4% setpoint, 72.5% both — physics-aligned
  metric; legacy metric is near-identical).
- Peak-load error (reported separately): PINN much better than MLP on
  setpoint (18.7% vs 87.5%) but worse on weather (-50.6% vs -5.5%) and
  both (-44.7% vs 19.0%).

## Reading: what the PINN proves and what it does not

1. **In-distribution, the physics + rollout training is a large win**
   (RMSE_T 3.84 → 0.64 °C, -83%). The multi-step loss fixes exactly what
   one-step training broke in slice 1.
2. **Extrapolation is mixed, not a clean win.** The ≥20% gate is met only
   on unseen setpoints. On unseen weather the PINN is only 18% better
   than the MLP, and on weather+setpoint only 8% better. The
   information-matched control (offset 1) is worse still on weather
   (-4%) and both (+11% — worse than the MLP), so part of the headline
   PINN's weather/both advantage is the current-step exogenous inputs,
   but the physics + rollout training still wins in-distribution and on
   setpoints with identical information.
3. **The heat-balance gate fails everywhere.** The physics loss does not
   deliver heat-balance consistency on held-out rollouts: 7.8% in
   distribution, 71–73% on unseen weather/both — worse than the MLP's
   54%/49% there. A drifted trajectory has a large implied imbalance, so
   this metric conflates trajectory error with physics violation; but on
   its own terms the issue's <5% gate is not met, and the physics-loss
   variant has not earned a keep verdict on this evidence.
4. **Optimistic setting, stated plainly.** The ground truth IS the RC
   model, the physics loss uses the KNOWN per-series RC parameters, and
   each rollout starts from the true wall state. A PINN that can
   reconstruct its own generative model is an upper bound, not evidence
   for a real building. Slice 3 (shared-encoder arm) and any funded
   follow-on must test parameter-mismatch robustness (nominal vs true
   parameters) before claiming physics priors help in practice.

## Speedup (measured, not estimated)

EnergyPlus 26.2.0, 5ZoneAirCooled full-year run, Chicago TMY3 weather,
on this machine: **8.3–11.6 s** wall across runs (EnergyPlus's own timer
reported 10.94 s on the first run). Surrogate, batched 5-zone × 8760-step
free-running PINN rollout, same machine: **9.5–10.9 s** (3 trials, median
9.98 s on the first measurement, 9.69 s on the re-run); single-zone
8760-step rollout 1.75–2.24 s. Speedup ≈ **1× (0.9–1.2× across runs)** —
the ≥50× gate is **NOT MET**.

Why so slow: the rollout is a Python loop over 8760 steps with a per-step
torch call on a tiny model, so call overhead dominates; EnergyPlus is
compiled and fast on this small example. A vectorised/compiled rollout
could be much faster, but that is not what this code does, and this POC
reports the measured number. Reproduce with
`src/benchmark_speedup.py --eplus-bin <path-to-energyplus-binary>`
(the EnergyPlus install is not committed; see the script's docstring).

## Determinism

`gen_data.py --seed 42`, `train.py --seed 42`, `train.py --seed 42 --arm pinn`,
`train.py --seed 42 --arm pinn --branch-offset 1 --out-dir data_off1`,
then `evaluate.py --seed 42` twice: byte-identical headline tables.
Training is seeded (seed 42, 1 thread); the PINN offset-0 run took 96.7 s
wall (60 epochs, best epoch 30), offset-1 94.5 s (best epoch 30).

## NOT claimed in this slice

1. No Go / Conditional / No-go verdict — that label belongs to the full POC.
2. No ≥20% extrapolation gate met across the board (weather and both fail).
3. No <5% heat-balance gate met on any split.
4. No ≥50× speedup (measured ~1.2×).
5. The PINN arm has not been tested with mismatched (nominal) RC
   parameters, so no claim about physics priors under parameter error.

## What slice 3 should do

- Add the shared-encoder differentiable RC arm (issue #3 arm (c)) on the
  same data and splits, evaluated by the same harness.
- Test parameter-mismatch robustness: PINN with nominal (train-median)
  RC parameters in the physics loss vs per-series true parameters.
- Revisit the speedup only with a vectorised/compiled rollout; do not
  re-measure the Python-loop rollout and expect a different number.
