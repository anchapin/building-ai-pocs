# POC #4 — Diffusion / world-model HVAC control: slice-1 note

**No verdict yet — slice 1.** Slice 1 builds the simulator + model-free
baseline harness only. The Go / No-go label comes after the world-model +
MPC arm is built and compared against the baseline on an unseen
building/climate.

## Question (from issue #4)

Can a learned world model of indoor climate (diffusion / latent dynamics) +
planning beat model-free RL on an *unseen* building/climate, with far fewer
real-environment steps? Gates: world-model controller beats model-free by
**≥5% energy at equal comfort** on the unseen building/climate, using
**≤1,000 real-environment steps**. No real-building deployment — a sim
saving is not a real saving.

## What slice 1 built

- **Simulator: CityLearn 3.2.0, dataset `baeda_3dem`.** Chosen because it
  is pip-installable, ships multi-building datasets, and supports
  unseen-building/climate evaluation. Sinergym (full EnergyPlus install)
  and BEAVER deferred. The `baeda_3dem` dataset has **4 buildings**, not 5
  (`Building_5` does not exist).
- **`citylearn_env.py` — `CityLearnHVACEnv`.** Fixed contract: 1 scalar per
  building in `[-1, 1]` (negative = cooling, positive = heating); 10 floats
  per building (outdoor/indoor temp, heating/cooling setpoints, comfort
  band, net electricity, cooling/heating demand, hour, day-of-year).
  Storage / EV / deferrable-load actions held at 0. Includes the
  rule-based fixed-setpoint controller used as a reference.
- **`run_baseline.py`.** Trains the model-free SAC baseline
  (stable-baselines3, chosen over PPO because the action is a continuous
  power fraction and SAC is CityLearn's own reference baseline) on one
  building/climate; writes a results JSON (energy, comfort violations,
  timesteps, seed, full config) and prints a headline table.
- **`tests/` (10 tests).** Env contract (finite observations, non-negative
  energy, comfort metric every step), harness (results-JSON schema,
  headline table), determinism (same seed → identical results JSON).
  **10/10 pass in 40.2 s**, verified by the supervisor from a fresh venv
  install (see Verification).
- **`requirements.txt`** (exact pins, Python 3.12.3, CPU-only torch) and
  **`.gitignore`** (venv, dataset cache, model/result binaries).

## Verification (supervisor, 2026-11-06)

- `pip install -r requirements.txt` in a fresh venv: succeeds (~15.6 min;
  scikit-learn 1.2.2 builds from source on cp312, wheel now cached).
- `python -m pytest tests/ -q`: **10 passed in 40.2 s**. (One supervisor
  fix: `evaluate_rule_based` was missing the `steps` key the schema test
  requires; one line + counter added, suite re-run green.)
- Smoke baseline: `run_baseline.py --timesteps 2000 --seed 0 --out results
  --quiet` → 33.2 s wall time, results JSON written. Determinism re-check
  is part of the suite (two subprocess runs, seed 3, identical results).
- Worker note: the worker hit the 60-step cap mid-test-writing with a
  think-leak report; the diff was verified from git and completed by the
  supervisor (test fix above + this REPORT.md + README.md). The worker
  never ran the tests or the baseline itself.

## Smoke results (do not quote as a finding — smoke budget only)

`baeda_3dem` / `Building_1`, 2,000 training steps, seed 0, 2 eval episodes
(46 steps — episodes are 23 steps at `episode_time_steps=24`):

| controller | energy kWh/ep | comfort violations/ep | violation degC/ep |
|---|---|---|---|
| SAC (model-free baseline) | 0.568 | 17.0 | 30.53 |
| rule-based fixed setpoint | 0.568 | 20.5 | 41.17 |

## Findings — slice 2 must resolve these before the full baseline sweep

- **F1 — the energy signal does not respond to the HVAC action on
  `Building_1`.** Constant-action 23-step rollouts (supervisor diagnostic):
  net electricity is **0.567642 kWh for action 0, full-heat, and
  full-cool alike** (identical to 6 decimals); the cooling device's own
  `electricity_consumption` series reads 0.000 even at full cooling.
  The smoke table's energy column is therefore vacuous on this building.
  Slice 2 must find a building/dataset where the energy metric responds
  to control (or define a thermal-energy metric) before sweeping — the
  ≥5% energy gate cannot be measured on `Building_1` as it stands.
- **F2 — `baeda_3dem` is cooling-only.** Every building's
  `heating_device.nominal_power` is 0.0; `active_actions` are
  `cooling_device` (+ `cooling_storage`, `dhw_storage`). The wrapper's
  heating half is a no-op on this dataset. Either pick a dataset with
  actuated heating or scope the POC to cooling-only explicitly.
- **F3 — degenerate 30/30 °C setpoints at the dataset start.** Heating and
  cooling setpoints both read 30.00 °C with indoor 28.12 °C (outdoor
  19.17 °C), so the comfort violation is heating-side and the only
  actuated direction (cooling) pushes indoor temperature *away* from the
  setpoint: full cooling raises the violation (38.32 → 42.14 degC over 23
  steps) while mean indoor temp falls only 28.33 → 28.17 °C. The best
  controller on this episode is "do nothing". Slice 2 must survey
  setpoint variation across the dataset/year and pick train/eval episodes
  where control can actually improve comfort.
- **F4 — the wrapper is faithful.** Raw CityLearn and wrapper indoor-temp
  trajectories agree exactly under 0 / full-cool; the findings above are
  dataset behaviour, not wrapper bugs.

## Evaluation protocol (slice 2)

- **Training set:** one building/climate (to be fixed by slice 2 after F1–F3
  are resolved — not `Building_1` as-is).
- **Held-out set:** at least one *unseen* building and one *unseen* climate
  (candidate held-out climates from the CityLearn dataset list:
  `citylearn_challenge_2020_climate_zone_1..4`, `tx_travis_county_neighborhood`,
  `vt_chittenden_county_neighborhood`, `ca_alameda_county_neighborhood`).
- **Seeds:** ≥3 for every reported number (RL evaluation is seed-sensitive).
- **Gates (from issue #4):** world-model + MPC beats model-free by ≥5%
  energy at equal comfort on the unseen building/climate, using ≤1,000
  real-environment steps; comfort violations reported separately from
  energy savings.
- **No-go triggers:** it only wins in-distribution (memorisation, not a
  world model); or the energy/comfort gates cannot be measured (F1–F3
  unresolved) — in which case slice 2 reports that plainly instead of
  sweeping on a vacuous metric.

---

# POC #4 — Diffusion / world-model HVAC control: slice-2 note

**No verdict yet — slice 2.** Slice 2 resolves findings F1–F3, fixes the
train/held-out sets, and runs the model-free baseline sweep at 3 seeds. The
Go / No-go label comes after the world-model + MPC arm (slice 3) is built
and compared against the sweep headline below.

## What slice 2 built

- **`survey_datasets.py` (new).** Constant-action survey: for each candidate
  dataset/building it runs action 0 / full-heat / full-cool on the SAME
  episode window through the same `CityLearnHVACEnv` the RL harness uses,
  and reports heating/cooling `nominal_power`, net electricity under each
  action, heating/cooling demand, and setpoint/indoor ranges.
- **`citylearn_env.py` — `start_step`, `solar_generation`,
  `resolve_dataset_schema`.** `start_step > 0` pins every reset to the
  single window `[start_step, start_step + episode_steps - 1]` via
  CityLearn's episode-splits list (0 keeps the default sequential windows);
  `solar_generation` defaults to `False` (avoids the optional PySAM
  dependency; keeps the energy metric about consumption only); datasets
  resolve to a local `data/datasets/<name>/` copy when present, else
  CityLearn downloads them once. The worker's draft of these two parameters
  was docstring-only (no implementation); the supervisor implemented them.
- **`run_sweep.py` (new).** Multi-seed SAC sweep: trains on the train set
  at ≥3 seeds (sequential 24-step windows over the whole year) and evaluates
  SAC, rule-based, and do-nothing controllers on the train set and every
  held-out set, on one fixed window per set. Writes one sweep JSON (per-seed
  detail + headline mean ± std) and prints the headline table.
- **`run_baseline.py`.** Gained `--start-step` / `--solar-generation` /
  `--no-solar-generation` passthroughs and indoor-temperature min/max in
  both evaluators' output (a dynamics-validity check — see the caveat).
- **Tests: 10 → 18.** New `tests/test_survey.py` (baeda non-response,
  same-window monotonic response, `resolve_dataset_schema`) and
  `tests/test_sweep.py` (parser, do-nothing evaluator, small end-to-end
  sweep schema + headline). **18/18 pass in ~35 s.**

## F1–F3 resolutions

- **F1 — RESOLVED: net electricity responds to control on the RESStock
  buildings.** Corrected survey (24-step day-1 window, all three actions on
  the same window — see the confound correction below):

  | dataset / building | heat kW | cool kW | net@0 | net@heat | net@cool | spread |
  |---|---|---|---|---|---|---|
  | tx_travis / …102188 | 4.04 | 7.37 | 8.98 | 13.01 | 16.35 | 7.37 |
  | vt_chittenden / …112208 | 16.73 | 4.19 | 0.37 | 17.10 | 4.56 | 16.73 |
  | ca_alameda / …102040 | 8.87 | 3.11 | 1.30 | 10.17 | 4.41 | 8.87 |
  | baeda_3dem / Building_1 | 0.00 | 7.58 | 0.5676 | 0.5676 | 0.5676 | 0.00 |
  | 2020 climate zones 1–4 / Building_1 | 0.00 | 125–162 | 9.19–9.95 | = net@0 | = net@0 | 0.00 |

  (kWh per 24-step episode window; full rows in `results/survey_*_start0.json`.)
  The response is monotonic and sane on all three RESStock buildings
  (heating and cooling both cost more than do-nothing). `baeda_3dem` and
  the 2020 challenge datasets are flat to 4 decimals — their net
  electricity does not respond to the HVAC action at all, so the ≥5%
  energy gate cannot be measured on them. No thermal-energy substitute
  metric was needed: net electricity is the sweep metric.
- **F2 — RESOLVED: heating is actuated.** All three RESStock buildings have
  a heat-pump `cooling_or_heating_device` with real heating nominal power
  (tx 4.04 kW, vt 16.73 kW, ca 8.87 kW); the wrapper's signed action
  contract (positive = heating, negative = cooling) drives it, verified by
  heating demand responding under full-heat (tx 92.1 kWh, vt 218.1 kWh,
  ca 71.7 kWh over the day-1 window). No cooling-only scoping was needed.
  `baeda_3dem` and the 2020 zones stay cooling-only (heating nominal 0.0).
- **F3 — RESOLVED: setpoints vary over the year; the eval window is a
  summer week.** In the RESStock datasets the heating and cooling setpoints
  are equal to the baseline indoor-temperature trajectory everywhere (a
  zero-width band; full-year ranges tx 17.78–27.22 °C, vt 17.22–26.11 °C,
  ca 17.22–25.56 °C), so "comfort" means tracking that trajectory. The
  June eval window (start step 4368, 168 steps) has varying setpoints on
  all three sets (tx 24.44–27.22, vt 18.33–26.00, ca 23.50–25.56 °C).
  Control CAN improve comfort there: the sweep's do-nothing reference
  leaves 2031 / 1084 / 447 violation-degC per episode (tx/vt/ca) while SAC
  leaves 323 / 347 / 171 — so "do nothing" is no longer the best
  controller on any set.

## Fixed evaluation sets (slice 2 protocol)

- **Train:** `tx_travis_county_neighborhood` /
  `resstock-amy2018-2021-release-1-102188` (Texas, hot climate).
- **Held-out:** `vt_chittenden_county_neighborhood` /
  `resstock-amy2018-2021-release-1-112208` (Vermont, cold) and
  `ca_alameda_county_neighborhood` /
  `resstock-amy2018-2021-release-1-102040` (California, mild) — unseen
  buildings AND unseen climates.
- **Evaluation window:** start step 4368, 168 nominal steps (June 2–8).
  A nominal N-step episode yields N−1 transitions (CityLearn terminates
  when `time_step` reaches the episode end; slice 1's smoke run showed the
  same: 2 episodes = 46 steps), so the eval episode is 167 steps.
  Training uses sequential 24-step windows over the whole year.
- **Sweep:** SAC (stable-baselines3, defaults: buffer 10,000, lr 3e-4,
  gamma 0.99, batch 64), 10,000 training steps per seed, seeds 0, 1, 2;
  solar generation off; reward −(1.0·energy + 0.5·violation).

## Sweep headline (June window, 167 steps/episode, mean ± std over 3 seeds)

| set :: controller | energy kWh/ep | comfort viol./ep | viol. degC/ep |
|---|---|---|---|
| tx (train) :: SAC | 1.19 ± 0.11 | 154.0 ± 0.0 | 323 ± 94 |
| tx (train) :: rule-based | 5.10 ± 2.67 | 154.0 ± 0.0 | 1112 ± 61 |
| tx (train) :: do-nothing | 1.04 ± 0.00 | 154.0 ± 0.0 | 2031 ± 0 |
| vt (held-out) :: SAC | 1.42 ± 0.53 | 154.0 ± 0.0 | 347 ± 51 |
| vt (held-out) :: rule-based | 7.99 ± 6.77 | 154.0 ± 0.0 | 1212 ± 16 |
| vt (held-out) :: do-nothing | 0.39 ± 0.00 | 154.0 ± 0.0 | 1084 ± 0 |
| ca (held-out) :: SAC | 3.40 ± 0.95 | 154.0 ± 0.0 | 171 ± 57 |
| ca (held-out) :: rule-based | 9.57 ± 0.58 | 154.0 ± 0.0 | 506 ± 21 |
| ca (held-out) :: do-nothing | 1.14 ± 0.02 | 154.0 ± 0.0 | 447 ± 0 |

Full per-seed table:
`results/sweep_sac_tx_travis_county_neighborhood_resstock-amy2018-2021-release-1-102188_s0-1-2.json`
(426.5 s wall time; ~133 s training per seed).

Reading the headline:

- **SAC dominates the rule-based reference on both axes, on all three
  sets** — 2.8–5.6× less energy and 3.0–3.5× fewer violation-degrees.
  That is the number slice 3's world model + MPC must beat.
- **SAC beats do-nothing on comfort everywhere** (6.3× tx, 3.1× vt,
  2.6× ca fewer violation-degrees) **for an energy premium** (+14% tx,
  +264% vt, +198% ca — do-nothing spends almost no HVAC energy, so any
  control costs energy; the premium is the price of the comfort gain).
- **The violation COUNT (154/167) carries no signal.** The LSTM dynamics
  pins indoor temperature to the CSV baseline for the first 13 steps of
  every episode (a warm-up/lookback window), so the first 13 steps never
  violate for any controller; the remaining 154 steps essentially always
  violate (zero-width band). Only the violation DEGREES discriminate.
- **Seed sensitivity is real.** SAC's energy varies 2–3× across seeds on
  the held-out sets (vt 0.70–1.96, ca 2.31–4.62 kWh/ep); rule-based
  energy varies up to 18× (vt 0.95–17.13). Three seeds is a minimum, not
  a luxury — slice 3 must report ≥3 seeds too.

## Dynamics-validity caveat — read before trusting any number here

The CityLearn LSTM dynamics is **not physically faithful under large
actions**, and the evidence is in the sweep itself:

- A diagnostic rollout on the tx June window (supervisor, 2026-11-06):
  with no HVAC the indoor temperature sits exactly on the baseline for
  13 steps, then drifts up (25.7 → 29.2 → 32.2 °C). The rule-based
  controller sees indoor 2.8 °C above setpoint, applies full cooling
  (−1.0), and the LSTM answers by crashing indoor temperature 11 °C in
  one hour (28.4 → 17.3 °C) — a 7.4 kW device cannot do that to a real
  house in one hour. The controller then heats at full power, and the
  system bang-bang oscillates. That oscillation is why rule-based looks
  so bad: it is fighting the dynamics model, not the building.
- The survey's constant-action probes show the same failure mode:
  sustained full-cool drives indoor to 5.3 °C (tx), −14.0 °C (vt);
  sustained full-heat drives it to 53.1 °C (tx). The LSTM extrapolates
  wildly outside realistic operation.
- SAC wins largely by acting GENTLY: its indoor ranges stay within
  11–38 °C while rule-based visits −16.5 to +56.4 °C. SAC learned the
  dynamics' gain, not necessarily the building's physics.

Consequences: the slice-2 sweep is a fair baseline for slice 3 (same
simulator, same window, same protocol), but a "win" against it may partly
reflect exploiting or avoiding dynamics artifacts rather than real
physics. Slice 3 must check its controller's indoor-temperature ranges
and action magnitudes the same way, and must not claim a real-building
saving from any of this.

## Survey correction (supervisor)

The worker's first survey run was **confounded and is superseded**: it
reused one environment across the three constant-action rollouts, but
with `start_step == 0` CityLearn advances to the next sequential episode
window on every reset — so the three actions were scored on three
different days. That run reported a 7.8–10.6 kWh "spread" for the 2020
challenge datasets and a spurious "full heat uses less energy than
do-nothing" for tx_travis. The corrected survey constructs a fresh
environment per action (same window for all three): the 2020 zones'
spread is exactly 0.0000 (no response at all) and tx_travis is monotonic
(8.98 / 13.01 / 16.35 kWh). The confounded file was deleted; the
corrected rows are in `results/survey_*_start0.json` and
`results/survey_*_june.json`. The test
`test_probe_same_window_response_is_monotonic` fails on the old code and
passes on the new code.

## Datasets excluded, and why

- **`baeda_3dem`** (slice 1's dataset): F1 fails (net electricity flat
  0.5676 kWh under all actions) and F2 fails (cooling-only). Kept as the
  smoke-test dataset in the test suite only.
- **2020 challenge zones 1–4**: F1 fails (net flat), F2 fails
  (cooling-only), F3 fails — the CSVs carry NO setpoint columns, so the
  wrapper reads 0.00 °C setpoints, and the buildings have NO `dynamics`
  model, so indoor temperature follows the precomputed CSV and control
  cannot change comfort at all. Unusable for this POC.
- **RESStock neighbourhoods are the only surveyed datasets that clear all
  three findings.** Only the first building of each was probed; other
  buildings in the same datasets are candidates for slice 3's transfer
  evaluation if more held-out buildings are wanted.

## Verification (supervisor, 2026-11-06)

- `python -m pytest tests/ -q`: **18 passed in ~35 s** (10 slice-1 tests
  unchanged and green; 8 new survey/sweep tests).
- Survey re-runs (supervisor, corrected script): all 11 survey JSONs in
  `results/` reproduce the table above; the baeda non-response and the
  tx monotonic response are pinned by tests.
- Sweep reproduce command (see README): 3 seeds × 10,000 steps, 426.5 s
  wall time; sweep JSON written; do-nothing rows reproduce the survey's
  June-window numbers exactly (tx 1.0405, vt 0.3943, ca 1.1590 kWh),
  which cross-checks the sweep harness against the survey harness.
- Worker note: the worker hit the 60-step cap mid-survey (think-leak
  report, docstring-only env changes, no sweep/tests/docs). The diff was
  verified from git and completed by the supervisor: implemented
  `start_step`/`solar_generation`/local-schema resolution in the wrapper,
  fixed the survey's day-confound, ran the survey + sweep, added the
  tests, and authored this note + the README update. Supervisor
  corrections to the worker's draft: (1) the env parameters were
  documented but not implemented; (2) the survey scored actions on
  different days; (3) setpoint/indoor ranges covered only the last
  rollout instead of all three.

## What slice 3 does

Build the diffusion / latent-dynamics world model + MPC/planning controller
and compare it against the sweep headline above on the same fixed sets and
June window, under the issue-#4 gates (≥5% energy win on the unseen
building/climate at equal comfort, ≤1,000 real-environment steps).
**No verdict yet — verdict after the world-model arm (slice 3).**
