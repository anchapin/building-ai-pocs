# Diffusion / World-Model HVAC Control

**Status:** Slice 1 done (2026-11-06) — simulator + model-free baseline harness work end to end. **No verdict yet** (slice 1 builds the foundation only; the Go / No-go label comes after the world-model comparison in a later slice).

Diffusion / world-model HVAC control for grid-interactive buildings, tested in simulation. See the repo README for the POC rules: 25–40 hours, standalone, fixed go/no-go gate, REPORT.md leading with exactly one label (Go, Go (software only), Conditional, or No-go).

## Simulator

**CityLearn 3.2.0**, dataset `baeda_3dem` (4 buildings, Netherlands climate).
Chosen because it is pip-installable, ships multi-building datasets, and
supports unseen-building / unseen-climate evaluation. Sinergym (needs a full
EnergyPlus install) and BEAVER are deferred; the wrapper's fixed
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

The `baeda_3dem` dataset downloads once into the CityLearn cache on first
use; it is never committed to git (see `.gitignore`).

## Reproduce (smoke baseline)

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
  fixed-setpoint controller used as a reference.
- `run_baseline.py` — trains the model-free SAC baseline (stable-baselines3)
  on one building/climate and writes a results JSON (energy, comfort
  violations, timesteps, seed, full config).
- `tests/` — env contract tests, harness tests (results-JSON schema, headline
  table, determinism: same seed → identical results).

## What slice 2 does

Multi-seed baseline sweep + held-out (unseen building / climate) evaluation
per the protocol in `REPORT.md` — **after** resolving the slice-1 findings
there (energy metric unresponsive on `Building_1`, cooling-only dataset,
degenerate 30/30 °C setpoints). No verdict until the world-model + MPC arm
is built and compared.
