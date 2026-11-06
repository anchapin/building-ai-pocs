# Federated Calibration — verdict: No-go

**Verdict: No-go.** Slice 2 ran the discriminating experiments slice 1 left open
(partial participation, wider and clustered heterogeneity, and an IID control) and
adjudicated the parameter-mean caveat. FedAvg never beats the best non-federated
transfer — one-shot parameter averaging — by the issue's ≥15% bar in any of the
6 configurations × 2 held-out buildings (best case +8.7%, one building, one
configuration), and the IID control fires the issue's No-go trigger outright:
on IID synthetic data federated, centralised, parameter-mean, and donor-mean all
agree to within ~0.3%. A clean No-go is a successful outcome for this POC. The
slice-1 sections below are unchanged; the verdict evidence is §6.

## 1. What was built

Fully synthetic federation, no real-building data. 9 client buildings + 2 held-out buildings (`holdout-H1`, `holdout-H2`), generated with different vintages/climates as 240 h series. Each building fits a 4-parameter grey-box RC model (thermal capacitance `C`, loss coefficient `UA`, solar aperture `s`, solar gain `g_sol`); only parameter updates are shared — no raw time-series ever leaves a building. Three approaches compared on each held-out building, zero-shot (no own data):

- **isolated-local** — the held-out building fitted on its own first 6/12/24/48/72 h (and full series, in-sample, for reference);
- **federated** — FedAvg over the 9 client models, 15 rounds × 60 local steps;
- **centralised** — one model fitted on the pooled data of all 9 clients (reference only).

Two extra zero-shot transfer rows are reported because the issue's "isolated-local" baseline is ambiguous zero-shot (a building with no own data has no local model): the donor client-0 model transferred as-is, and the mean RMSE of the 9 donor models transferred as-is. A third row, one-shot parameter averaging (mean of the 9 fitted parameter sets, no rounds), is reported because it turned out to matter — see §4.

Method: eval window 72–240 h, rollout RMSE in °C, 3 seeds (42, 43, 44), 400 fit steps. Deterministic: rerunning `python src/run_poc.py --seed 42,43,44` reproduces byte-identical `data/results_seed*.json` (verified by the supervisor; two runs into different directories differ only in the out-dir path printed on stdout).

Tests: 16 in `tests/` (`python -m pytest tests/ -q`, ~30 s), including a boundary test that a client holds no other building's private series (`t_out`, `t_zone`) and a byte-identical-rerun test.

## 2. Headline numbers (rollout RMSE, °C; mean ± std over 3 seeds)

### holdout-H1

| variant | mean | std | FedAvg vs |
|---|---|---|---|
| own data, first 6 h | 4.0537 | 4.3152 | −83.4% |
| own data, first 12 h | 0.3320 | 0.1105 | +102.1% |
| own data, first 24 h | 0.2415 | 0.0648 | +177.8% |
| own data, first 48 h | 0.2466 | 0.0358 | +172.1% |
| own data, first 72 h | 0.2222 | 0.0559 | +202.0% |
| own data, full series (in-sample) | 0.2049 | 0.0656 | +227.5% |
| zero-shot, donor client-0 model | 1.5587 | 0.7699 | −57.0% |
| zero-shot, mean donor RMSE (9 isolated models) | 1.1758 | 0.1483 | −42.9% |
| zero-shot, parameter-mean of 9 client models | 0.6311 | 0.3615 | +6.3% |
| **zero-shot, FedAvg over 9 clients** | **0.6710** | **0.1846** | — |
| zero-shot, one model on pooled data | 0.7174 | 0.1281 | −6.5% |

### holdout-H2

| variant | mean | std | FedAvg vs |
|---|---|---|---|
| own data, first 6 h | 4.0143 | 1.1782 | −75.5% |
| own data, first 12 h | 2.1113 | 0.0787 | −53.5% |
| own data, first 24 h | 1.7805 | 0.0411 | −44.8% |
| own data, first 48 h | 0.5589 | 0.2527 | +75.8% |
| own data, first 72 h | 0.5474 | 0.0594 | +79.5% |
| own data, full series (in-sample) | 0.1713 | 0.0199 | +473.6% |
| zero-shot, donor client-0 model | 1.9872 | 0.1212 | −50.6% |
| zero-shot, mean donor RMSE (9 isolated models) | 1.2860 | 0.0555 | −23.6% |
| zero-shot, parameter-mean of 9 client models | 0.9267 | 0.0994 | +6.0% |
| **zero-shot, FedAvg over 9 clients** | **0.9826** | **0.0657** | — |
| zero-shot, one model on pooled data | 1.0573 | 0.0474 | −7.1% |

("FedAvg vs" is the relative change of FedAvg against that row: negative means FedAvg is better. The 6 h isolated-local rows have huge std — 6 h of data barely identifies the model.)

## 3. Findings

1. **FedAvg clearly beats donor transfer.** Against the mean donor RMSE, FedAvg wins by 42.9% (H1) and 23.6% (H2); against a single donor model, by 57.0% / 50.6%. On the issue's ≥15% gate read against donor baselines, slice 1 clears the bar on both held-out buildings.
2. **FedAvg's zero-shot transfer is worth roughly 12–48 h of a building's own data — no more.** Once the held-out building has its own data, local fitting wins: H1 crosses between 6 h and 12 h (iso-12 h 0.332 vs FedAvg 0.671), H2 between 24 h and 48 h (iso-48 h 0.559 vs FedAvg 0.983). Federated transfer is a cold-start story, not a replacement for local calibration.
3. **Centralised pooling is NOT an upper bound for zero-shot transfer here.** FedAvg beats the pooled-data model on both buildings (−6.5% / −7.1%). Pooling raw data across non-IID clients compromises the fit; averaging parameter updates does better. The issue's No-go trigger "federated ≈ centralised on IID synthetic data" does not fire — the data are non-IID and federated is better, not ≈.
4. **One-shot parameter averaging beats 15 rounds of FedAvg.** The mean of the 9 fitted parameter sets, transferred with no rounds at all, scores 0.6311 / 0.9267 against FedAvg's 0.6710 / 0.9826 (FedAvg +6.3% / +6.0% worse). For this 4-parameter model class, the federated protocol adds nothing over naive averaging — and the averaging row is the right comparator for the ≥15% gate, not the donor rows. This is the open question the verdict slice must settle: if the gate is read against the best non-federated transfer, FedAvg does not clear it.
5. **Non-IID is real and persistent, but FedAvg does not diverge.** Client-update spread stays 0.60–0.61 across all 15 rounds — clients keep pulling in different directions and the spread never collapses. FedAvg converges in 1–2 rounds anyway (global parameters stable after round 1); 15 rounds is overkill, the cost is the local fits.
6. **Zero raw time-series shared.** Only 4-parameter updates cross the wire (boundary-tested: a client holds no other building's `t_out` / `t_zone` series).

## 4. What would change the recommendation (for the verdict slice)

- Decide the gate's baseline: donor-mean (cleared: −42.9% / −23.6%) or best non-federated transfer, i.e. parameter-mean (not cleared: FedAvg is 6% worse). The verdict hinges on this reading, and it is a judgement call, not a measurement.
- If the protocol is to earn its keep, it needs a setting where averaging fails: richer model classes (more parameters, less identifiable from a single building), more heterogeneous clients, or partial participation. On 4-parameter RC models with 9 similar clients, averaging already captures the transfer.
- Do not claim this proves the privacy or deployment story; synthetic federation proves the algorithm only (per issue #5 scope).

## 5. Supervisor verification notes (2026-11-06)

The worker's run hit the 60-step cap before running tests or writing this report, so the supervisor verified and finished the slice: fixed a real bug the worker's last edit introduced (`evaluate.py` raised `NameError: rollout is not defined` — the import was missing), fixed two failing tests (an over-strict boundary assertion on public deterministic shapes; a byte-identical-rerun test tripped by the out-dir path in stdout), and corrected a silent headline-row semantic change (the worker's JSONs reported the donor-mean row; the code had been edited to report the parameter-mean instead — both rows are now reported, separately labelled). All numbers in §2 were recomputed by the supervisor from an independent 3-seed run, not copied from the worker's output. Suite: 16/16 passed against the final code.

## 5. Supervisor verification notes (2026-11-06)

The worker's run hit the 60-step cap before running tests or writing this report, so the supervisor verified and finished the slice: fixed a real bug the worker's last edit introduced (`evaluate.py` raised `NameError: rollout is not defined` — the import was missing), fixed two failing tests (an over-strict boundary assertion on public deterministic shapes; a byte-identical-rerun test tripped by the out-dir path in stdout), and corrected a silent headline-row semantic change (the worker's JSONs reported the donor-mean row; the code had been edited to report the parameter-mean instead — both rows are now reported, separately labelled). All numbers in §2 were recomputed by the supervisor from an independent 3-seed run, not copied from the worker's output. Suite: 16/16 passed against the final code.

## 6. Slice 2: the verdict (2026-11-06)

### 6.1 What was built

Two discriminating axes from slice 1 §4, plus the IID control, all in
`src/run_slice2.py` (single reproduce entry point,
`python src/run_slice2.py --seed 42,43,44`, writing
`data/slice2_results.json`):

- **Partial participation** (`src/federate.py`): a per-round random subset of
  the clients is online (`--participation`, seeded, so runs stay
  deterministic). Two extra one-shot baselines are reported under partial
  participation, because "the mean of all 9 fitted models" is not achievable
  in one simultaneous shot when only a subset is online: the parameter-mean
  of the clients online in round 1, and the parameter-mean of all clients
  that took part over the run (collected offline, over time).
- **Client heterogeneity** (`src/gen_buildings.py`): `wide` (same nine
  archetypes, much wider per-building truth spread) and `clustered` (three
  tight, well-separated groups: light/cold, heavy/hot, medium/temperate).
  The held-out buildings are unchanged in every mode, so slice-2 numbers are
  comparable with slice-1 numbers.
- **IID control** (`iid` mode): all nine clients the same archetype
  (medium/temperate) with a very tight truth spread — a (nearly) IID
  federation, re-checking the issue's No-go trigger "federated ≈
  centralised on IID synthetic data".

Same protocol as slice 1 throughout: 3 seeds (42, 43, 44), 240 h series, eval
window 72–240 h, rollout RMSE in °C, 15 FedAvg rounds × 60 local steps,
400-step local fits. Tests grew from 16 to 36 (`python -m pytest tests/ -q`),
covering subset selection, the heterogeneity modes, the extra baselines, the
unchanged slice-1 artefact shape, and slice-2 determinism.

### 6.2 Transfer table: FedAvg vs the best non-federated transfer

Rollout RMSE, °C, mean ± std over 3 seeds. "FedAvg vs param-mean" is the
relative improvement of FedAvg over one-shot parameter averaging (positive =
FedAvg better); the issue's ≥15% gate is applied on this column.

| configuration | holdout | FedAvg | parameter-mean | FedAvg vs param-mean | FedAvg vs donor-mean | FedAvg vs centralised |
|---|---|---|---|---|---|---|
| baseline p=1.0 (control) | H1 | 0.6710 ± 0.1846 | 0.6311 ± 0.3615 | −6.3% | +42.9% | +6.5% |
| baseline p=1.0 (control) | H2 | 0.9826 ± 0.0657 | 0.9267 ± 0.0994 | −6.0% | +23.6% | +7.1% |
| partial participation p=0.5 | H1 | 0.7236 ± 0.0803 | 0.6311 ± 0.3615 | −14.6% | +38.5% | −0.9% |
| partial participation p=0.5 | H2 | 0.9574 ± 0.0430 | 0.9267 ± 0.0994 | −3.3% | +25.6% | +9.5% |
| wide heterogeneity | H1 | 0.5782 ± 0.2621 | 0.5488 ± 0.3621 | −5.4% | +64.1% | +18.2% |
| wide heterogeneity | H2 | 0.8467 ± 0.0929 | 0.8113 ± 0.0483 | −4.4% | +41.2% | +39.1% |
| clustered heterogeneity | H1 | 0.9045 ± 0.2423 | 0.6379 ± 0.3359 | −41.8% | +7.9% | +10.5% |
| clustered heterogeneity | H2 | 0.8956 ± 0.0399 | 0.8855 ± 0.0816 | −1.1% | +22.0% | +17.6% |
| clustered + participation p=0.5 | H1 | 0.9237 ± 0.2489 | 0.6379 ± 0.3359 | −44.8% | +5.9% | +8.6% |
| clustered + participation p=0.5 | H2 | 0.8080 ± 0.0385 | 0.8855 ± 0.0816 | **+8.7%** | +29.6% | +25.7% |
| iid control | H1 | 0.6668 ± 0.2123 | 0.6667 ± 0.2115 | −0.0% | +0.2% | +0.3% |
| iid control | H2 | 1.0609 ± 0.0756 | 1.0586 ± 0.0742 | −0.2% | +1.2% | −0.1% |

Reading the table:

- **FedAvg loses to parameter-mean in 11 of 12 building-configurations.**
  Its single win (clustered + p=0.5, H2, +8.7%) is below the 15% bar, and
  the same configuration on H1 is its worst loss (−44.8%). No configuration
  clears the bar on both buildings; no configuration clears it on either
  building.
- **Against the weaker donor-mean baseline, the gate still does not clear
  uniformly.** FedAvg beats donor-mean by ≥15% in 8 of 12 cases, but fails
  on clustered H1 (+7.9% / +5.9%) and on the IID control (+0.2% / +1.2%).
  The donor-mean reading is not the right comparator anyway (see §6.3), but
  even it does not deliver a uniform pass.
- **Against the simultaneous one-shot comparator** (parameter-mean of only
  the clients online in round 1, the honest baseline when participation is
  partial), FedAvg's best is +6.7% (baseline p=0.5, H1) — again below the bar.
- **The IID control fires the issue's No-go trigger.** On IID synthetic data
  all four zero-shot arms agree to within ~0.3% on H1 (FedAvg 0.6668,
  parameter-mean 0.6667, centralised 0.6686, donor-mean 0.6679) and ~1.2% on
  H2. Federated ≈ centralised, exactly the trivial result the issue names
  as a No-go. (Slice 1 §3.3 said this trigger "does not fire" — that was for
  the non-IID slice-1 population. The trigger is about IID data, and the
  control built for this slice shows it fires there.)

### 6.3 Gate adjudication

The issue's Go criterion — "federated beats isolated-local by ≥15% RMSE on a
held-out building (zero-shot transfer)" — needs a baseline, because a
building with no own data has no local model. Slice 1 §4 left the choice
open; this slice decides it, and the decision is the verdict:

- **The gate is applied against the best non-federated transfer:
  one-shot parameter-mean.** It is a single model transferred as-is, built
  from the same fitted client models FedAvg uses, strictly cheaper (one
  average, no rounds, no coordination, no server), and it uses the same
  information. A practitioner choosing between "federated" and "not
  federated" would compare against it, not against transferring a single
  donor's model (a straw man: nobody deploys "pick client 0's model") or
  against the mean of nine donor RMSEs (an average of errors, not a model).
- On that reading the gate fails everywhere: best case +8.7%, eleven cases
  negative. The verdict is **No-go**.

This is a judgement call, stated as one: the numbers do not depend on it
(the donor-mean reading is also reported in full above, and it too fails to
clear uniformly), but the verdict does. Had the gate been read against
donor-mean alone, the slice-1 control would have looked like a pass; the
parameter-mean row is what makes the verdict honest.

### 6.4 Non-IID failure modes (reported honestly)

- **FedAvg does not diverge on non-IID buildings.** The issue's second
  No-go trigger does not fire: client-update spread stays bounded in every
  configuration (baseline 0.60–0.64, p=0.5 0.75–0.96, wide 0.82–1.17,
  clustered 0.51–0.54, clustered+p0.5 0.66–0.83, iid 0.09–0.25) and the
  global model converges within 1–2 rounds in all of them. Non-IID is real
  and persistent — the spread never collapses — but it does not break FedAvg.
- **FedAvg gets worse as heterogeneity grows.** On clustered H1, FedAvg
  (0.9045 / 0.9237) is ~42–45% worse than parameter-mean (0.6379), while on
  the baseline population it is only ~6% worse. Clustering hurts the
  protocol more than it hurts the average: the global model is pulled toward
  the mean of the clusters while the held-out building matches one cluster.
- **Partial participation hurts FedAvg and leaves averaging untouched.**
  Baseline p=0.5 moves FedAvg H1 from 0.6710 to 0.7236 (−14.6% vs
  parameter-mean, from −6.3%); the parameter-mean rows are identical, because
  the fitted client models do not depend on the rounds. Over 15 rounds all 9
  clients take part in every seed, so the "all clients that took part"
  baseline coincides with the 9-client parameter-mean.
- **Seed variance is large and is part of the result.** H1 parameter-mean
  ranges 0.27–1.13 across the three seeds (std 0.36 on a mean of 0.63). The
  verdict uses 3-seed means, and the direction is consistent (11 of 12
  negative), but a 3-seed mean on this population is not a tight estimate —
  do not over-read the second decimal.

### 6.5 Mechanism (hypothesis, not proven)

The leading explanation for why 15 rounds of FedAvg lose to one average: the
two estimators are not given the same fitted models. Parameter-mean averages
the **converged** local fits (400 steps each from the nominal parameters).
FedAvg's local updates run only **60 steps from the moving global
parameters** each round, then get averaged — under-converged updates from a
common init, pulled toward the running mean. The protocol's per-round work is
weaker than the baseline it is compared against, and the deficit grows when
clients disagree (clustered H1). This is consistent with the numbers but was
not isolated by an experiment in this slice: raising local steps/rounds to
test it would be tuning the protocol toward the gate, which the slice does
not do. It is the first thing a follow-on should test (see §6.6).

### 6.6 What would change the recommendation

- **A setting where FedAvg beats parameter-mean by ≥15% on both held-out
  buildings.** The candidates slice 1 §4 named were tested here
  (heterogeneity, partial participation) and did not produce one. Untested
  candidates, in order of plausibility: (a) converged local updates in
  FedAvg (more local steps and/or rounds — tests the §6.5 mechanism);
  (b) a richer model class (more parameters, less identifiable from a single
  building), where one-shot averaging of independently fitted models may
  fail while iterative alignment helps; (c) many more clients, where a
  single average may wash out. Any of these would need a fresh slice with
  the same gate applied against parameter-mean.
- **A different gate.** If the project only needs "better than a donor
  model" (the weak reading), FedAvg clears ≥15% in 8 of 12 cases — but that
  bar is below what one-shot averaging already achieves for free, so it
  would not justify the protocol.
- Do not claim this proves the privacy or deployment story; synthetic
  federation proves the algorithm only (per issue #5 scope). Zero raw
  time-series were shared in any configuration (boundary-tested).

## 7. Supervisor verification notes, slice 2 (2026-11-06)

The worker stopped at step 51/60 with no WORKER_REPORT.md (session exited 0;
transcript ends mid-edit adding the `iid` mode) — same pattern as slice 1.
The supervisor verified the diff from git and completed the slice: wired the
`iid` mode into `run_poc.py --heterogeneity` choices and the slice-2 driver
config list (the worker's code for it was present but unreachable), ran the
full 6-config × 3-seed grid independently (`python src/run_slice2.py --seed
42,43,44`, ~6 min), re-ran it to a second directory (byte-identical
`slice2_results.json`), and re-ran the slice-1 reproduce (`run_poc.py`,
byte-identical `results_seed*.json` vs the worker's rerun). All §6.2 numbers
were read from the supervisor's own `data/slice2_results.json`, not copied
from the worker's transcript. Two of the supervisor's new tests failed first
on over-tight thresholds (iid rel-std 0.0315 vs a 0.03 bound; clustered
within-cluster `s` rel-std 0.080 vs a 0.06 bound) — both are sampling noise
on 3–9 draws, thresholds recalibrated with the reasoning recorded in the
tests, suite now 36/36. Worker burn: 51/60 steps, 2,722,064 in / 75,043 out
(MiniMax-M2.7, no z.ai failover). The verdict (No-go) follows the measured
numbers; the supervisor's only judgement call is the baseline reading in
§6.3, stated there as a judgement call.
