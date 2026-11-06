# Federated Calibration

**Status:** In progress (slice 1: synthetic generator + isolated-local / FedAvg / centralised harness + held-out eval; no Go/no-go verdict yet).

Federated, physics-informed calibration across simulated buildings, sharing no raw time-series. Only parameter updates leave a building. See `REPORT.md` for the slice-1 numbers; the verdict slice is still to come.

## Reproduce

```bash
pip install -r requirements.txt        # numpy, scipy, torch (CPU build)
python src/run_poc.py --seed 42,43,44
```

Prints the headline table (isolated-local vs federated vs centralised on two held-out buildings) and writes the same numbers to `data/results_seed*.json`. Fully deterministic: reruns produce byte-identical JSONs.

## Tests

```bash
python -m pytest tests/ -q        # 16 tests, ~30 s
```

## Layout

- `src/gen_buildings.py` — synthetic building generator (9 client buildings + 2 held-out, different vintages/climates, 240 h series each).
- `src/local_model.py` — 4-parameter grey-box RC model (C, UA, s, g_sol) fitted per building.
- `src/federate.py` — FedAvg over the 9 client models (15 rounds, 60 local steps).
- `src/evaluate.py` — held-out eval: zero-shot transfer rows plus isolated-local rows at 6/12/24/48/72 h of own data.
- `src/run_poc.py` — single reproduce entry point.

## What this slice does NOT do

No Go/no-go verdict yet (see `REPORT.md` — the verdict slice must adjudicate the parameter-mean caveat first). No real-building data, no differential privacy / secure aggregation — synthetic federation proves the algorithm only.
