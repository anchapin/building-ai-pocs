# Federated Calibration

**Status:** No-go (slice 2 verdict, 2026-11-06). FedAvg never beats one-shot
parameter averaging by the issue's ≥15% bar in any of 6 configurations × 2
held-out buildings (best +8.7%), and the IID control fires the issue's No-go
trigger outright (federated ≈ centralised to within ~0.3%). See `REPORT.md`
§6 for the verdict evidence; slice 1 numbers are §§1–5.

Federated, physics-informed calibration across simulated buildings, sharing no raw time-series. Only parameter updates leave a building.

## Reproduce

```bash
pip install -r requirements.txt        # numpy, scipy, torch (CPU build)
python src/run_poc.py --seed 42,43,44
python src/run_slice2.py --seed 42,43,44   # verdict slice: 6 configs, writes data/slice2_results.json
```

Prints the headline table (isolated-local vs federated vs centralised on two held-out buildings) and writes the same numbers to `data/results_seed*.json`. Fully deterministic: reruns produce byte-identical JSONs.

## Tests

```bash
python -m pytest tests/ -q        # 36 tests, ~4 min (slice-2 tests run real seeds)
```

## Layout

- `src/gen_buildings.py` — synthetic building generator (9 client buildings + 2 held-out, different vintages/climates, 240 h series each). Heterogeneity modes: `baseline`, `wide`, `clustered`, `iid` (slice 2).
- `src/local_model.py` — 4-parameter grey-box RC model (C, UA, s, g_sol) fitted per building.
- `src/federate.py` — FedAvg over the 9 client models (15 rounds, 60 local steps). Slice 2 adds partial participation (`--participation`, seeded per-round subsets).
- `src/evaluate.py` — held-out eval: zero-shot transfer rows plus isolated-local rows at 6/12/24/48/72 h of own data.
- `src/run_poc.py` — single reproduce entry point for slice 1.
- `src/run_slice2.py` — verdict-slice driver: 6 configurations (baseline, partial participation, wide, clustered, clustered + participation, iid control) over 3 seeds; writes `data/slice2_results.json`.

## What this slice does NOT do

No Go verdict — the verdict is **No-go** (see `REPORT.md` §6). No real-building data, no differential privacy / secure aggregation — synthetic federation proves the algorithm only.
