# Diffusion / World-Model HVAC Control

**Status:** Slice 2 done (2026-11-06) — findings F1–F3 resolved, train/held-out sets fixed, 3-seed SAC baseline sweep run. **No verdict yet** (the Go / No-go label comes after the world-model + MPC arm is built and compared in slice 3).

Diffusion / world-model HVAC control for grid-interactive buildings, tested in simulation. See the repo README for the POC rules: 25–40 hours, standalone, fixed go/no-go gate, REPORT.md leading with exactly one label (Go, Go (software only), Conditional, or No-go).

## Simulator

**CityLearn 3.2.0.** Slice 1 used `baeda_3dem` (4 buildings, Netherlands
climate); slice 2 moved to the RESStock neighbourhood datasets (see
"Evaluation sets" below) because `baeda_3dem` is cooling-only and its net
electricity does not respond to the HVAC action at all. Sinergym (needs a
full EnergyPlus install) and BEAVER are deferred; the wrapper's fixed
action/observation contract is simulator-agnostic enough to swap later if
CityLearn proves unsuitable.

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Python 3.12.3 on this VM (4 cores, 7.7 GB RAM, no GPU). Note: CityLearn
3.2.0 pins `scikit-learn<=1.2.2` and 1.2.2 has no cp312 wheel, so pip builds
it from source on first install (~15 min; the built wheel is then cached by
pip). If the build fails with "No space left on device", point TMPDIR at a
filesystem with >= 1 GB free (this VM's /tmp is a 512 MB tmpfs):

```sh
TMPDIR=/var/tmp .venv/bin/pip install -r requirements.txt
```

The datasets download once into the CityLearn cache on first use; they are
never committed to git (see `.gitignore`). The RESStock datasets need
CityLearn's battery-sizing data, which is fetched once from the CityLearn
GitHub release and cached under `<poc>/.cache/citylearn/` -- the scripts
default `XDG_CACHE_HOME` to that worktree-local cache, so runs do not depend
on the shared-egress GitHub API rate limit. The datasets themselves live
under `data/datasets/` (extracted from the CityLearn v3.2.0 release tarball);
delete that directory to re-fetch them.

## Reproduce (slice-2 sweep)

```sh
.venv/bin/python run_sweep.py --dataset tx_travis_county_neighborhood \
    --building resstock-amy2018-2021-release-1-102188 \
    --timesteps 10000 --seeds 0,1,2 \
    --eval-start-step 4368 --eval-episode-steps 168 \
    --eval-on vt_chittenden_county_neighborhood:resstock-amy2018-2021-release-1-112208 \
    --eval-on ca_alameda_county_neighborhood:resstock-amy2018-2021-release-1-102040 \
    --out results --quiet
.venv/bin/python -m pytest tests/ -q
```

Survey (which datasets respond to control, and where):

```sh
.venv/bin/python survey_datasets.py --datasets tx_travis_county_neighborhood \
    --buildings resstock-amy2018-2021-release-1-102188 \
    --start-step 4368 --episode-steps 168 --out results/survey_tx_june.json
```

## Evaluation sets (slice 2)

- **Train:** `tx_travis_county_neighborhood` / `resstock-amy2018-2021-release-1-102188`
  (Texas, hot climate; heat pump 4.04 kW heat / 7.37 kW cool, both actuated).
- **Held-out:** `vt_chittenden_county_neighborhood` / `resstock-amy2018-2021-release-1-112208`
  (Vermont, cold; 16.73 kW heat / 4.19 kW cool) and
  `ca_alameda_county_neighborhood` / `resstock-amy2018-2021-release-1-102040`
  (California, mild; 8.87 kW heat / 3.11 kW cool).
- **Evaluation window:** start step 4368, 168 steps (June 2–8) — a summer
  week with non-degenerate, varying setpoints on all three sets. Training
  uses sequential 24-step windows over the whole year; evaluation replays
  the one fixed June week so every seed is scored on identical episodes.
- **Metric:** net electricity [kWh] per episode (responsive to control on
  all three RESStock buildings, verified by the survey) and comfort
  violations reported separately. In these datasets heating and cooling
  setpoints are equal to the baseline indoor-temperature trajectory (a
  zero-width band), so "comfort" means tracking that trajectory; the
  do-nothing controller is evaluated on the same windows as the F3 check.

Full numbers and the F1–F3 resolutions are in `REPORT.md`.

## Reproduce (slice-1 smoke baseline)

```sh
.venv/bin/python run_baseline.py --timesteps 2000 --seed 0 --out results --quiet
.venv/bin/python -m pytest tests/ -q
```

Smoke run, 2026-11-06, `baeda_3dem` / `Building_1`, 2,000 training steps,
seed 0, 33.2 s wall time (2 eval episodes, 46 steps):

| controller | energy kWh/ep | comfort violations/ep | violation degC/ep |
|---|---|---|---|
| SAC (model-free baseline) | 0.568 | 17.0 | 30.53 |
| rule-based fixed setpoint | 0.568 | 20.5 | 41.17 |

Read the numbers with the findings in `REPORT.md`: on this building the
energy signal does not respond to the HVAC action at all (identical to 6
decimals under 0 / full-heat / full-cool), so the energy column above is
vacuous and the comfort column is the only live signal — slice 2 must
resolve the energy metric before the full baseline sweep.

## Layout

- `citylearn_env.py` — `CityLearnHVACEnv`: fixed 1-scalar-per-building
  action contract (`[-1, 1]`, negative = cooling, positive = heating) and
  fixed 10-floats-per-building observation contract, plus the rule-based
  fixed-setpoint controller used as a reference. Slice 2 added
  `start_step` (pin one evaluation window), `solar_generation` (default
  off), and `resolve_dataset_schema` (prefer a local `data/datasets/`
  copy).
- `run_baseline.py` — trains the model-free SAC baseline (stable-baselines3)
  on one building/climate and writes a results JSON (energy, comfort
  violations, timesteps, seed, full config).
- `survey_datasets.py` — constant-action survey: for each candidate
  dataset/building, scores action 0 / full-heat / full-cool on the SAME
  episode window and reports whether net electricity responds.
- `run_sweep.py` — multi-seed SAC sweep: trains on the train set at >=3
  seeds and evaluates SAC, rule-based, and do-nothing controllers on the
  train set and every held-out set, on one fixed window per set.
- `tests/` — env contract tests, harness tests (results-JSON schema, headline
  table, determinism: same seed → identical results), survey tests
  (baeda non-response, same-window monotonic response), sweep tests.

## What slice 3 does

Build the diffusion / latent-dynamics world model + MPC/planning controller
and compare it against the slice-2 sweep headline on the same fixed sets
and window, under the issue-#4 gates (>=5% energy win on the unseen
building/climate at equal comfort, <=1,000 real-environment steps). The
verdict (Go / Go (software only) / Conditional / No-go) is written then.
