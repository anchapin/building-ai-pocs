# Federated Calibration — slice 1 report

**Verdict: none yet.** This is slice 1 of issue #5 (synthetic generator + isolated-local / FedAvg / centralised harness + held-out eval). The Go/no-go verdict belongs to the next slice, which must adjudicate the parameter-mean caveat in §4 before applying the issue's ≥15% gate. Nothing below is a verdict.

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
