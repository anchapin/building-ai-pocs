# Neural-operator surrogate POC — VERDICT: No-go

**Label: No-go.** This is the full-POC verdict (slice 3 closes the POC).
A clean No-go is a successful outcome: the POC answered its question, and
the answer is that neither the physics-informed arm nor the shared-encoder
arm earns a Go on the issue's three gates. The slice notes below hold the
evidence; this section is the verdict and nothing else.

## The three gates (issue #3)

| Gate | Result |
|---|---|
| Surrogate beats MLP on extrapolation (unseen weather + unseen setpoint) by ≥20% RMSE | **PARTIAL.** PINN with NOMINAL parameters meets it on all three unseen splits (weather −32.5%, setpoint −61.8%, both −29.3%). PINN with TRUE parameters meets it only on setpoints (−65.8%; weather −18.3%, both −7.7%). SharedEnc-RC (nominal base) also prints MET — but see the disqualification below: its numbers are the nominal-RC baseline, not learning. |
| Heat-balance residual <5% on held-out rollouts | **NOT MET anywhere, by any honest arm.** Best honest value is PINN-true in-distribution, 7.8%; PINN-nominal 8.7% in-distribution; 51–73% on unseen weather/both. |
| ≥50× speedup vs EnergyPlus | **NOT MET.** Standing measurement ~1× (0.9–1.2×, slice 2). No vectorised/compiled rollout was built in this slice, so the gate was not re-tested. |

## Why No-go, not Conditional

- Two of the three gates fail decisively: heat balance by 1.5–14×, speedup by ~50×. A Conditional would need a credible single condition; this needs two fundamental fixes (a physics-consistency mechanism that actually delivers HB <5% on held-out rollouts, and a vectorised rollout that reaches ≥50×), both unproven and both new research, not follow-on slices.
- The shared-encoder arm (c) — the arm this slice was supposed to add — contributes nothing beyond its own baseline. With TRUE base parameters it is disqualified as a tautology (supervisor-proved: an untrained SharedEncoderRC reproduces the RC reference to RMSE_T 0.0000 on every split — it contains the exact generative model, so its 100% extrapolation "win" and ~0% heat-balance residual are not results). With NOMINAL base parameters it matches the untrained nominal RC almost exactly (trained val 0.6057 / weather 1.3672 / both 1.2038 °C vs untrained nominal RC 0.6254 / 1.3605 / 1.2025 °C) — the encoder learns ~nothing, and further training makes the rollout worse (val 0.606 → 1.074 by epoch 59 while the one-step loss falls: the same one-step-training-destabilises-rollouts lesson as slice 1's delta divergence).
- Peak-load error, reported separately as the issue requires, stays unusable for sizing on the hard splits: PINN −43% to −50% on unseen weather/both.
- The one genuine positive — PINN-nominal beats the MLP on every unseen split — does not rescue the verdict: it still violates heat balance everywhere and runs at ~1× EnergyPlus speed, so it is neither physics-consistent nor faster. It is kept as a research note (below), not as a surrogate to adopt.

## What failed

1. The physics-residual loss does not deliver heat-balance consistency on held-out rollouts (best 7.8% in-distribution, 51–73% OOD). The metric conflates trajectory error with physics violation (slice 2), but on its own terms the <5% gate is not met, and no arm comes close OOD.
2. The speedup gate was never plausibly reachable with a Python-loop rollout (~1× measured); the vectorised/compiled rollout that could change it was identified in slice 2 and not built in slice 3 (the worker re-downloaded EnergyPlus 26.2.0 and hit the step cap before running the benchmark; `benchmark_speedup.py` is untouched).
3. The shared-encoder arm's design is degenerate with true parameters (see above) and inert with nominal ones. The NeuralBES-style variant is killed for this component.
4. Per the issue's No-go text, the physics-loss variant is killed as a surrogate for this component. Note the nuance: the issue's literal No-go trigger (PINN ≤ MLP OOD) is NOT what happened — PINN-nominal beats the MLP OOD on all splits. The kill is on the Go bar instead: a surrogate that fails heat balance and speed is not adoptable however it extrapolates.

## What would change the recommendation

- A physics-consistency mechanism that reaches HB <5% on held-out rollouts (not just in-distribution), demonstrated on the same harness — the current residual loss does not.
- A vectorised/compiled rollout measured at ≥50× vs EnergyPlus on the same 5ZoneAirCooled comparison.
- Both together, in a new spike, not a slice 4: the POC's effort box is spent, and the remaining work is new research (plus a real-building test, since all of this is on self-consistent RC ground truth — see the optimistic-setting caveat in the slice-2 note, which still stands).

## What survives as research notes (not adoption)

- PINN with nominal (train-median) parameters extrapolates better than PINN with true parameters: weather −17%, both −23% RMSE_T vs the true-parameter arm, and it meets the ≥20% extrapolation gate on all three unseen splits. The "correct" prior does worse OOD than the approximate one — the Jiang et al. (2025) warning, replicated in the other direction. Any funded follow-on that uses physics priors should test nominal-vs-true parameters as a first experiment.
- Multi-step (rollout) loss is what fixed the MLP's free-running error in-distribution (3.84 → 0.64 °C); one-step training alone destabilises rollouts (slice 1 delta divergence; slice-3 shared-nominal val rollout 0.606 → 1.074 across epochs while one-step loss falls). Rollout-aware training is necessary, just not sufficient for the HB gate.

---

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
---

# Neural-operator surrogate POC — slice 3 note

This slice closes the POC. The verdict is at the top of this file
(**No-go**); what follows is what slice 3 built, what it measured, and
what it explicitly does not claim.

## What slice 3 built

All work lives in `neural-operator-surrogate/` (standalone, CPU-only, no
Fluxion integration, no EnergyPlus claim beyond the measured speedup,
no ASHRAE 140 claim):

- `src/models.py` — `SharedEncoderRC`, a NeuralBES-style shared-encoder
  differentiable RC model (issue #3 arm (c)): one encoder shared by every
  time step maps the state-history window to a latent code; two heads
  produce multiplicative (log-space) corrections of four RC parameters
  (UA_win, UA_inf, C_air, R_wall) and a learned heat-flow correction
  (tanh, ±2000 W). The zone temperature is obtained by integrating the
  differentiable 2R2C equations with the corrected parameters — the
  physics is hard-wired in the architecture, not a soft loss penalty.
  Heads are zero-initialised, so an untrained model is exactly the base
  RC model. Plus `median_params` (per-parameter train-median = nominal
  parameters) and `shared_rollout_torch` / `rollout_shared`.
- `src/train.py` — `--arm shared` (60 epochs, seed 42, `level` target)
  and `--rc-params {true,nominal}` for both the PINN and shared arms;
  best-epoch selection by val rollout RMSE (as in slice 2); checkpoints
  record `rc_params_mode`.
- `src/evaluate.py` — headline table extended with `PINN (nominal
  params)`, `SharedEnc-RC`, and `SharedEnc-RC (nominal base)` rows on
  every split, a gate summary covering all four surrogate arms, and a
  PARAMETER-MISMATCH table (PINN nominal vs true, per split).
- `tests/test_shared.py` — 5 new tests (25 total, all passing): the
  untrained-shared-is-RC-reference property, the nominal-variant-is-a-
  real-test property, rollout determinism/finiteness/warm-start,
  checkpoint round-trip of `rc_params_mode`, `median_params` medians.
- `neural-operator-surrogate/data/` holds the trained checkpoints
  (gitignored, as before): `model_shared.pt`,
  `model_shared_nominal.pt`, `model_pinn_nominal.pt` (trained by the
  supervisor to complete the mismatch experiment — the worker hit the
  step cap during the EnergyPlus re-download before training it),
  plus the slice-1/2 checkpoints. EnergyPlus 26.2.0 was re-downloaded
  into gitignored `data/energyplus/` (official Ubuntu 24.04 tarball);
  the benchmark was not run — see "Speedup" below.

## Headline table (seed 42; evaluate re-run is byte-identical)

Free-running rollout RMSE_T [°C] (physics-aligned heat-balance residual
in brackets). Full table, MAE/RMSE_Q/peak-load error, and the gate
summary are in the `evaluate.py --seed 42` output.

| split | MLP | PINN (true) | PINN (nominal) | SharedEnc-RC | SharedEnc-RC (nominal) |
|---|---|---|---|---|---|
| val | 3.8384 [37.1%] | 0.6429 [7.8%] | 0.5701 [8.7%] | 0.0000 [0.000%] † | 0.6057 [9.0%] |
| test_id | 3.8502 [35.5%] | 0.6391 [7.6%] | 0.5713 [8.6%] | 0.0000 [0.000%] † | 0.6129 [8.9%] |
| test_weather (UNSEEN) | 6.7486 [53.6%] | 5.5170 [71.3%] | 4.5548 [51.5%] | 0.0001 [0.001%] † | 1.3672 [16.8%] |
| test_setpoint (UNSEEN) | 4.3799 [33.0%] | 1.4995 [11.4%] | 1.6718 [11.9%] | 0.0001 [0.000%] † | 0.5337 [7.8%] |
| test_both (UNSEEN) | 6.1342 [49.2%] | 5.6610 [72.5%] | 4.3366 [55.8%] | 0.0001 [0.001%] † | 1.2038 [15.3%] |

† DISQUALIFIED — tautology, not a result. Supervisor-proved: an
untrained SharedEncoderRC rolled out with TRUE base parameters
reproduces the RC reference to RMSE_T 0.0000 on every split (the
zero-init heads vanish, so the rollout IS the 2R2C ground truth). Its
100% extrapolation "win" and ~0% heat-balance residual are structural
and are excluded from every gate judgement in this report. The honest
shared-encoder numbers are the nominal-base column.

## The honest shared-encoder numbers (nominal base)

Trained SharedEnc-RC (nominal base) vs the untrained nominal RC with
the same parameters — the comparison that isolates what the encoder
learned:

| split | untrained nominal RC | trained SharedEnc-RC (nominal) |
|---|---|---|
| val | 0.6254 | 0.6057 |
| test_id | 0.6320 | 0.6129 |
| test_weather | 1.3605 | 1.3672 (worse) |
| test_setpoint | 0.5505 | 0.5337 |
| test_both | 1.2025 | 1.2038 (worse) |

The encoder learns ~nothing: ±3% on the in-distribution splits, worse
on two of three unseen splits. Training history shows why: best epoch
is 0 (val rollout 0.606) and the rollout degrades to 1.074 by epoch 59
while the one-step loss falls 0.263 → 0.026. One-step training
destabilises the rollout; the best checkpoint is the least-trained one.

## Parameter-mismatch experiment (PINN, nominal vs true)

| split | RMSE_T true | RMSE_T nominal | delta | HBresid true | HBresid nominal |
|---|---|---|---|---|---|
| val | 0.6429 | 0.5701 | −11.3% | 7.792 | 8.732 |
| test_id | 0.6391 | 0.5713 | −10.6% | 7.555 | 8.648 |
| test_weather | 5.5170 | 4.5548 | −17.4% | 71.265 | 51.546 |
| test_setpoint | 1.4995 | 1.6718 | +11.5% | 11.439 | 11.887 |
| test_both | 5.6610 | 4.3366 | −23.4% | 72.509 | 55.830 |

The nominal-parameter PINN extrapolates BETTER than the
true-parameter PINN on weather and both (and meets the ≥20%
extrapolation gate on all three unseen splits — the only honest arm to
do so). Heat balance still fails for both (8.7–8.6% in-distribution,
51–56% OOD for nominal). The physics prior with the "correct"
parameters does worse OOD than with approximate ones.

## Training facts

- SharedEnc-RC (true): 60 epochs, seed 42, 261.8 s wall, best epoch 55,
  30,149 parameters, val rollout RMSE 1.2e-05 °C (tautology — see above).
- SharedEnc-RC (nominal): 60 epochs, seed 42, 257.9 s wall, best epoch
  0, val rollout RMSE 0.6057 °C.
- PINN (nominal): 60 epochs, seed 42, 94.0 s wall, best epoch 43, val
  rollout RMSE 0.5701 °C (trained by the supervisor; the worker's
  transcript shows it planned this run in `/tmp/run_c.sh` but hit the
  60-step cap during the EnergyPlus re-download first).
- Determinism: `gen_data.py --seed 42`, `train.py --seed 42`,
  `evaluate.py --seed 42` twice: byte-identical headline tables.
  Tests: 25 passed (`pytest neural-operator-surrogate/tests/ -q`).

## Speedup (not re-measured)

The ≥50× gate is NOT MET and was not re-tested: no vectorised/compiled
rollout was built in this slice (`benchmark_speedup.py` untouched).
The standing measurement from slice 2 (~1×, 0.9–1.2×) is the number;
do not cite it as new evidence from this slice. The worker
re-downloaded EnergyPlus 26.2.0 into gitignored `data/energyplus/`
(the tarball extracts with non-fatal `tar` ownership warnings on this
VM — `Cannot change ownership to uid 1001` — the binary itself works;
see the worker transcript steps 57–60) and hit the step cap before
running the benchmark.

## NOT claimed in this slice

1. No SharedEnc-RC (true base) win of any kind — disqualified, see above.
2. No ≥50× speedup (not re-tested; standing ~1×).
3. No <5% heat-balance gate met on any split by any honest arm.
4. No claim that physics priors help in practice: the nominal-vs-true
   result cuts the other way, and everything is still on
   self-consistent RC ground truth (the optimistic-setting caveat from
   slice 2 stands).
5. The verdict (No-go) is in the verdict section at the top of this
   file. This slice note records the evidence for it.

## What slice 3 did not do (and why)

- No vectorised/compiled rollout: the worker spent its steps on the
  arm, the mismatch wiring, and the EnergyPlus re-download, and hit
  the 60-step cap before the benchmark. The supervisor did not attempt
  it either — it is a new research task, not supervisor-completion
  fallout, and the verdict does not depend on it (the HB gate already
  fails decisively).
- No new tests for the mismatch table itself beyond the checkpoint
  round-trip: the table is a pure function of the evaluated
  checkpoints, and `evaluate.py` was re-run twice byte-identically by
  the supervisor.
