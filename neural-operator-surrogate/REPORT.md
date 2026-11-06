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
