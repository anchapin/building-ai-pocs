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
