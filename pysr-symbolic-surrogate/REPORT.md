# Report — PySR symbolic-regression surrogate (POC #47), slice 1 / Phase 0

Status: **slice 1 delivered, NO verdict.** The measurement foundation exists
and the comparator arm is measured; the PySR arm produced no measurements on
this VM for a diagnosed environment reason (below). Judging the POC's actual
question — can PySR recover the known form in-range and beat the refit
out-of-range — requires one PySR run on a host where its Julia backend works.

## Claims

- [observed] The least-squares biquadratic refit, trained on the restricted
  box (PLR 0.3–0.8 × T 24–30.6 °C, 400 samples), recovers the generating
  coefficients exactly on noise-free data for seeds 0–2 (in-range and
  out-of-range RMSE ≈ 1e-15; `MEASUREMENTS.md` rows 1, 3, 5). This is the
  control the PySR arm must be compared against, and it confirms the
  generator + evaluation harness measure what they claim to.
- [observed] At 1% multiplicative noise the same refit's out-of-range RMSE
  (0.0027–0.0148 across seeds 0–2) runs roughly 3–8× its in-range RMSE
  (0.00086–0.0017) — rows 2, 4, 6. The extrapolation gap the POC exists to
  test is real for the comparator on this data.
- [observed] Every PySR fit attempted on this VM (6 fits: restricted +
  control arms, seeds 0–2, plus a minimal direct fit) failed in the Julia
  backend before producing an equation: first `OSError(28)` from juliapkg
  staging its 273.2 MB Julia download in the 512 MB `/tmp` tmpfs, then —
  after a `TMPDIR` fix let the 994 MB Julia install persist — a bare
  `AssertionError()` at the juliacall boundary and a silent process death
  during backend startup, consistent with the VM's memory cap. Full record:
  `MEASUREMENTS.md`, "PySR arm — environment failure record".
- [inference] The PySR arm is most likely to run unmodified on the desktop
  runner (real disk temp, more RAM): the runner code, the data pipeline, and
  the install all work up to the Julia precompile/fit step.
- [unsupported] The generator's variable-role mapping. The worker could not
  copy the numeric `AshrStdCoeffs` values from Fluxion's
  `part_load_curves.rs` (that clone is outside this POC's room), so — as the
  slice brief allowed — it used a clearly cited published set instead: the
  DOE-2-derived `ChillerCentCapFT` biquadratic from EnergyPlus'
  `testfiles/ElectricEIRChiller.idf`. Those coefficients were fitted with
  x = leaving chilled-water temperature, and this POC re-interprets x as
  part-load ratio over PLR 0.3–1.0 while keeping the published temperature
  range. The re-interpretation is documented in `src/curves.py` and is NOT
  a premise for any verdict; a future slice should re-run with the exact
  `AshrStdCoeffs` numbers once they can be brought in legitimately.
- [unsupported] Any claim about PySR's recovery or extrapolation ability —
  no PySR measurement exists yet.

## What was built

- `src/curves.py` — published reference biquadratic (cited coefficients),
  seeded dataset generation on the issue's training / in-range /
  extrapolation boxes, least-squares refit comparator, RMSE.
- `src/run_measurements.py` — both arms behind one CLI; PySR failures are
  recorded as `ENV/RUN FAILURE` rows, never hidden.
- `tests/test_curves.py` — known-value generator tests + refit
  coefficient-recovery tests (full box and restricted box). 4 passed
  (supervisor re-run).
- `MEASUREMENTS.md` — raw table first: 6 LS rows + 6 PySR env-failure rows
  + the environment cost record (pip install ≈452 MB venv, Julia download
  273.2 MB, installed Julia 994 MB).

## Provenance of this slice

The worker (balanced, MiniMax-M2.7) wrote `src/curves.py` and
`src/run_measurements.py` and hit its 60-step cap fighting the Julia install
loop described above (its first run was also killed by a runtime restart at
step 27 and relaunched in place). The supervisor completed the slice:
added the tests, ran the LS arm, diagnosed the PySR failure chain
(/tmp staging → TMPDIR fix → juliacall assertion), and authored this report
and the README. No Fluxion code was touched; `default_ahri_coefficients()` /
`ahri_coefficients.json` were not used as data (fluxion #3942 stays Alex's
call).

## Remaining work (next slice)

1. Run the PySR arm on a capable host (desktop runner; `TMPDIR` on a large
   disk): restricted + control arms, ≥3 seeds, noise 0% and 1%; record
   recovered equations verbatim + search wall-clock per run.
2. Re-run with the exact `AshrStdCoeffs` coefficients from
   `part_load_curves.rs` if they can be cited into the folder legitimately,
   replacing the re-interpreted published set.
3. Only then judge the issue's gates: control-arm recovery (failure = Kill)
   and the out-of-range comparison against the LS refit measured here.
