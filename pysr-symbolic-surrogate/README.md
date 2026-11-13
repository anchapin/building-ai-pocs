# PySR symbolic-regression surrogate for an HVAC performance curve (POC #47)

Slice 1 / Phase 0: measurement foundation. A least-squares biquadratic refit
(the comparator) is measured against data generated from a published
ASHRAE/EnergyPlus reference biquadratic curve; the PySR arm is stood up but
its fits are blocked by this VM's environment (see `REPORT.md` and the
environment failure record in `MEASUREMENTS.md`). **No verdict yet.**

## Layout

- `src/curves.py` — reference biquadratic generator + least-squares refit +
  RMSE; training / in-range / extrapolation boxes per issue #47.
- `src/run_measurements.py` — measurement runner; writes `results.json` and
  `MEASUREMENTS.md` (one row per run: configuration, seed, training box,
  wall-clock, in-range RMSE, out-of-range RMSE, selected equation).
- `tests/test_curves.py` — known-value tests for the generator and the
  refit's coefficient recovery.
- `MEASUREMENTS.md` — the raw measurements table (first deliverable).
- `REPORT.md` — typed claims, status, and what remains.

## Reproduce

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/python src/run_measurements.py --seeds 0 1 2 --noise 0 1 --arms ls-refit
# PySR arm (needs a host where the Julia backend can install + precompile;
# set TMPDIR to a large-disk directory first — /tmp is a 512 MB tmpfs here):
TMPDIR=<large-disk-dir> .venv/bin/python src/run_measurements.py --seeds 0 1 2 --noise 0 --arms ls-refit,pysr --control-arm
```
