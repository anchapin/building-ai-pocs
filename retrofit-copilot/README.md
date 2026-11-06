# Retrofit Copilot

**Status:** Slice 1 done (EnergyPlus baseline + synthetic measured data + bounded
calibration). No Go / no-go verdict yet — see `REPORT.md`. The agent system, the
5 ECMs, the ranking, and the verdict belong to later slices.

Drawing → calibrated baseline → neuro-symbolic agent ranking energy-conservation
measures, simulation-grounded. Standalone POC — no Fluxion or Matchline
integration.

See the repo README for the POC rules: 25–40 hours, standalone, fixed go/no-go
gate, REPORT.md leading with exactly one label (Go, Go (software only),
Conditional, or No-go).

## Reproduce slice 1 (CPU-only)

```sh
sh retrofit-copilot/scripts/fetch_energyplus.sh   # EnergyPlus 26.2.0, ~242 MB download
python3 -m venv .venv && .venv/bin/pip install -q -r retrofit-copilot/requirements.txt
.venv/bin/python retrofit-copilot/src/run_poc.py --all --max-sweeps 3 --out retrofit-copilot/runs/headline_table.md
python3 -m pytest retrofit-copilot/tests/ -q   # 30 passed
```

The full pipeline runs 69 EnergyPlus simulations (~10 min, ~9 s each) and
writes the headline table to `retrofit-copilot/runs/headline_table.md` plus
`results.json` with the full search trace. Runs are scratch (gitignored); the
numbers are recorded in `REPORT.md`.

## Slice-1 headline (EnergyPlus 26.2.0, 5ZoneAirCooled, Chicago TMY3)

Synthetic measured data: the shipped example with infiltration ×2.0, envelope
conductivity ×1.3, cooling setpoint +1.0 K. Bounded calibration (3 named
parameters, fixed grids, Jan–Jun objective, Jul–Dec held out) recovered
infiltration ×2.2, envelope ×1.2, setpoint +1.0 K.

| series | period | NMBE % before → after | CV(RMSE) % before → after |
|---|---|---|---|
| facility energy [kWh] | full year | 0.90 → −0.18 | 11.43 → 1.63 |
| facility energy [kWh] | held-out (Jul–Dec) | −0.32 → −0.10 | 10.64 → 1.12 |
| zone mean air temp [C] | full year | 0.07 → −0.04 | 2.02 → 0.15 |

Monthly NMBE of hourly facility energy: before, 7 of 12 months outside ±5%
(−6.01% to +7.17%); after, all 12 months within ±0.57%. Guideline 14
(hourly CV(RMSE) ≤ 30%, monthly NMBE ±5%) met on every reported period.
Full table, run IDs, and caveats: `REPORT.md`.
