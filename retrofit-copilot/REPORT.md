# Retrofit Copilot — slice 1 note

**Slice 1:** EnergyPlus baseline + synthetic measured data + bounded calibration.
**No Go / Conditional / No-go verdict in this slice** — the verdict belongs to
the full POC: it requires the agent system, the 5-ECM ranking, and the
top-3-vs-ground-truth comparison, all of which are later slices. What follows
is what slice 1 built, what it measured, and what it explicitly does not claim.

## What slice 1 built

All work lives in `retrofit-copilot/` (standalone, CPU-only, no Fluxion or
Matchline integration):

- `scripts/fetch_energyplus.sh` — pins and fetches EnergyPlus 26.2.0
  (NatLabRockies release; the NREL/EnergyPlus repo moved there) into
  `.scratch/` (gitignored) and verifies `--version`.
- `src/run_energyplus.py` — locates the EnergyPlus binary
  (`$ENERGYPLUS_BIN` or `.scratch/EnergyPlus-*/energyplus`), runs one IDF +
  weather file, records a run ID, run directory, and manifest (command,
  input SHAs, output SHAs, return code, duration).
- `src/idf_params.py` — minimal IDF object model plus the three bounded
  calibration parameters, each applied to a copy (the shipped file is never
  edited in place) with a per-value change record:
  `infiltration_flow_scale` (ZoneInfiltration:DesignFlowRate design flow
  rate), `envelope_conductivity_scale` (every `Material` conductivity),
  `cooling_setpoint_offset_k` (every value of the `Clg-SetP-Sch` schedule).
  A reporting-only `Output:Meter` patch (hourly facility meters) is applied
  to every run.
- `src/calibrate.py` — ASHRAE Guideline 14 metrics (NMBE, CV(RMSE), monthly
  splits; `p = 0`, no regression fitted) and the bounded coordinate search
  over fixed, recorded grids (strict-improvement acceptance, reproducible).
- `src/results.py` — parses `eplus.csv` into hourly series (8760 rows) and
  facility-energy / zone-temperature series.
- `src/run_poc.py` — slice-1 driver (`--all`): baseline → synthetic measured
  → bounded calibration → headline table + `results.json`.
- `tests/` — 30 tests (known-value metric cases, IDF patching, manifest
  round-trip, CSV parsing): `python -m pytest retrofit-copilot/tests/ -q`
  → 30 passed.

## What slice 1 measured

Building: the EnergyPlus-shipped example `5ZoneAirCooled.idf`, weather
`USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw`, EnergyPlus 26.2.0. The
example's geometry is the hand-checked geometry input the issue allows (the
drawing verifier is not done); no drawing was parsed in this slice.

Synthetic measured data (ground truth, recorded): the shipped example with
infiltration ×2.0, envelope conductivity ×1.3, cooling setpoint +1.0 K
(run `measured-20261106T090956Z-1483a5`).

Bounded calibration: coordinate search over the three named parameters on
fixed grids (infiltration 1.0–2.4, envelope 0.8–1.4, setpoint −1.0–+2.0 K),
objective = hourly CV(RMSE) of facility energy on Jan–Jun only; Jul–Dec
held out and never seen by the search. 66 search evaluations + baseline +
measured + final calibrated run = 69 EnergyPlus runs. Calibrated parameters
recovered: infiltration ×2.2, envelope ×1.2, setpoint +1.0 K (truth ×2.0,
×1.3, +1.0 K).

Headline table (Guideline 14 thresholds applied: hourly CV(RMSE) ≤ 30%,
monthly NMBE ±5%):

| series | period | NMBE % before → after | CV(RMSE) % before → after | G14 |
|---|---|---|---|---|
| facility energy [kWh] | full year | 0.90 → −0.18 | 11.43 → 1.63 | PASS |
| facility energy [kWh] | calibration (Jan–Jun) | 2.05 → −0.26 | 12.06 → 1.96 | PASS |
| facility energy [kWh] | held-out (Jul–Dec) | −0.32 → −0.10 | 10.64 → 1.12 | PASS |
| zone mean air temp [C] | full year | 0.07 → −0.04 | 2.02 → 0.15 | PASS |

Monthly NMBE of hourly facility energy: before, 7 of 12 months outside ±5%
(−6.01% to +7.17%); after, all 12 months within ±0.57%.

Run audit trail: baseline `baseline-20261106T090947Z-85e761`, synthetic
measured `measured-20261106T090956Z-1483a5`, calibrated
`calibrated-20261106T092111Z-05d7af`. Every number above traces to these
runs; the full search trace is in `runs/results.json` (scratch, gitignored).

Independent supervisor check: re-reading the three `eplus.csv` files with
only the standard library confirmed 8760 hourly rows each and annual
facility energy of 62,528.5 kWh (baseline), 63,098.8 kWh (measured),
63,213.2 kWh (calibrated) — calibrated within 0.18% of measured on the
annual total, consistent with the reported NMBE of −0.18%.

## What slice 1 does NOT claim

- No Go / Conditional / No-go verdict (needs the ECM ranking).
- No ECM ranking, no agent, no LLM-prior control (later slices).
- No drawing was parsed: the geometry is the shipped example file, not a
  Matchline extraction. The drawing → geometry step is still open.
- Guideline 14 is met on synthetic data whose ground truth the calibration
  was built to recover. That proves the calibration machinery works; it
  says nothing about real-building calibration yet.
- The zone-temperature metric is a secondary sanity check, not a Guideline
  14 gate (Guideline 14 applies to energy). Its CV(RMSE) is small partly
  because temperatures sit near a ~22 °C mean.
- `envelope_conductivity_scale` scales EVERY `Material` conductivity,
  including interior materials (carpet, ceiling tiles), not just the opaque
  envelope. The "envelope" label is approximate; the recovered ×1.2 vs
  truth ×1.3 partly reflects that.

## What failed / what would change the recommendation

- The worker hit the 60-step cap with the code, tests, and all 69 runs
  done but REPORT.md, requirements.txt, the README, and .gitignore
  unwritten; the supervisor completed those docs and verified the numbers
  independently (see above). No code change was needed.
- The EnergyPlus repo moved from NREL to NatLabRockies; the fetch script
  pins the new location and version. If that URL goes stale, the reproduce
  command's first step is the thing that breaks.
- The calibration search is coordinate descent on a fixed grid: it
  recovered the truth closely but not exactly (envelope ×1.2 vs ×1.3,
  infiltration ×2.2 vs ×2.0). A later slice that needs tighter recovery
  should widen the grids deliberately and record the change — not silently.
