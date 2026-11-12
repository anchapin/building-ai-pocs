# SS-DFA surrogate POC — report

**Recommendation: No-go.**

Using the fixed §7 thresholds from the brief, SS-DFA (state-skipping Direct
Feedback Alignment on a single-map reservoir) fails the primary accuracy bar:
mean test-year rollout RMSE is **1.46 ± 0.83 °C vs 0.66 ± 0.04 °C for the LSTM
baseline — 2.20× worse (120% worse)**, far beyond the 50% no-go line. It also
fails 2 of the brief's 4 physics-sanity sign checks (both internal-gains
counterfactuals) at every seed, which independently trips the no-go clause.
SS-DFA *does* train ~4× faster than the LSTM with ~80× fewer trainable
parameters and it passes rollout stability, energy balance, and the 7-bit noise
gate — but the Conditional escape clause ("under half the LSTM's wall-clock at
comparable accuracy") does not apply because accuracy is not comparable. The
negative is clean and was reached inside the effort box: SS-DFA's state-skipping
training is cheap, but on this continuous, long-horizon regression task it does
not reach recurrent-backprop accuracy. The extension of the paper's claim from
MNIST/CIFAR-10 classification to building-surrogate regression is not supported
by this POC.

## 1. Task and teacher

**Teacher chosen: self-implemented 2R2C resistance–capacitance single-zone
model** (`src/gen_data.py`), the preferred option in §4.1. No EnergyPlus was
used. Hourly outputs (300 s internal sub-steps), latitude 45°N, generator seed
**20261105** — the dataset regenerates bit-identically from the repo alone
(`python src/gen_data.py`, see README).

- **State:** zone air node `Cz` coupled to a thermal-mass node `Cm` via `Uiw`;
  gains (solar through effective aperture `A_eff`, internal gains) split between
  nodes. `base`: Cz = 4.2e6 J/K, Cm = 4.0e7 J/K, UA_ext = 180 W/K, Uiw = 120 W/K,
  A_eff = 5 m².
- **HVAC:** proportional (K = 900 W/K), heating/cooling capped at 8 kW;
  setpoints 21/17 °C (heat, occ/unocc) and 24.5/28 °C (cool, occ/unocc);
  heating energy = Q/0.85; cooling COP = clamp(4.0 − 0.08·T_out, 1.8, ∞).
- **Weather (synthetic, per year):** annual mean 11 °C, amplitude 13.5 K,
  diurnal amplitude 6 K, AR(1) synoptic noise (φ = 0.986, σ = 0.34 K), AR(1)
  cloud cover (φ = 0.75, σ = 0.28, mean 0.72), clear-sky GHI 1080 W/m².
  Year 1 (train): offset +0.0 K, amp ×1.0. Year 2 (val): +0.8 K, ×0.9.
  Year 3 (test): −0.6 K, ×1.15. 8,760 h per year; no shuffling, no leakage;
  windows never cross a year boundary.
- **OOD envelope variants (held out from training, test year only):**
  `insul_half` (UA_ext 360), `insul_double` (UA_ext 90), `mass_double`
  (Cm 8.0e7).
- **Model inputs at each step:** T_out, GHI, internal gains, q_heat, q_cool +
  autoregressive zone temperature (24 h window). **Targets:** next-step zone
  temperature and hourly heating/cooling energy. All scalers fit on year 1 only.

### SS-DFA assumptions (§4.3 — the paper's exact formulation was not available; standard DFA + reservoir reading)

1. **Single map:** one fixed scalar map f(s) = tanh(g·s), reused at every time
   step; gain `g` is the only "lightly parameterised" part of the dynamics.
2. **Fixed random matrices:** W_in (input, 6→n_res), W_res (recurrent,
   sparsity 0.10, spectral radius scaled to 0.9), W_fb (DFA feedback,
   3→n_res, random and **not** any transpose of a forward weight).
3. **Trainable:** linear readout W_out/b_out (with window inputs concatenated:
   `readout_with_input=True` in the best config) plus two scalars
   (input scale, map gain) → **503 trainable parameters**; everything else
   frozen.
4. **DFA rule:** readout gradients are the ordinary instantaneous readout
   gradients accumulated over the window; the two scalar gradients are the
   **final-step** output error projected through the fixed random W_fb, with
   the reservoir state held constant at t−1 (a one-step derivative
   approximation). Adam scales these DFA-derived updates; `backward()` is never
   called.
5. **State-skipping invariants (asserted in `dfa_epoch`, `src/train.py`):**
   everything runs under `no_grad`, no `(B, L, n_res)` tensor is ever
   materialised, only the single most recent hidden state/pre-activation is
   retained. This **is** the state-skipping path; storing all states + BPTT
   would disqualify it, and it does neither.
6. Model size vs LSTM: 27,543 total params (503 trainable) vs 40,227 — well
   within the 2× budget.

## 2. Headline results (test year, 3 seeds, mean ± sample std)

| Model | 1-step T RMSE (°C) | 24 h T RMSE (°C) | Rollout T RMSE (°C) | Rollout max abs err (°C) | Train wall (s) | Epochs | Trainable params | Recurrent state evals |
|---|---|---|---|---|---|---|---|---|
| MLP (256,256) | 0.236 ± 0.007 | 0.619 | 0.616 ± 0.051 | 3.07 | 16 ± 3 | 35 | 103,683 | 0 |
| LSTM 96×1 | 0.271 ± 0.020 | 0.628 | **0.662 ± 0.041** | 3.84 | 336 ± 239 | 60 | 40,227 | 12.5 M |
| SS-DFA | 0.355 ± 0.008 | 1.108 | **1.457 ± 0.834** | 6.74 | 80 ± 5 | 31 | **503** | **0.026 M** |

Validation loss (val year): MLP 0.00167–0.00190, LSTM 0.00121–0.00133,
SS-DFA 0.00288–0.00375. Tuning stayed inside the §4.4 budget (5 configs per
model, logged in `results/tuning_log.json` including every failure); each
model's final config is the one reported.

**SS-DFA/LSTM rollout RMSE ratio: 2.20× on seed means** (per-seed matched:
3.53×, 1.52×, 1.48×). Even SS-DFA's best seed is 48% worse than its matched
LSTM seed — no seed is inside the 20% Go band. SS-DFA trains 4.2× faster with
~490× fewer recurrent state evaluations, but not at comparable accuracy.

## 3. Physics table (§5; 3 seeds, mean unless stated)

| Check | MLP | LSTM | SS-DFA |
|---|---|---|---|
| **1. One-step T**: MAE / RMSE (°C), NMBE, CV(RMSE) | 0.143 / 0.236, +0.10%, 1.03% | 0.180 / 0.271, +0.23%, 1.18% | 0.210 / 0.355, +0.14%, 1.54% |
| **1. One-step energy** RMSE heat/cool (kWh) | 0.131 / 0.259 | 0.074 / 0.085 | 0.122 / 0.244 |
| **1. 24 h** T RMSE (°C), CV(RMSE) | 0.619, 2.70% | 0.628, 2.74% | 1.108, 4.83% |
| **2. 8,760 h rollout**: bounded / blow-up | yes / none | yes / none | yes / none |
| 2. Final abs err (°C) / drift per month (°C) | 0.98 / −0.68 | 1.19 / −1.69 | 0.76 / −4.44 |
| **3. OOD rollout RMSE (°C)**: insul_half / insul_double / mass_double | 1.21 / 1.89 / 0.68 | **0.87 / 1.28 / 0.66** | 1.54 / 2.69 / 1.54 |
| 3. OOD extreme weeks (°C): hottest / coldest | 0.49 / 1.08 | **0.40 / 1.21** | 0.91 / 2.17 |
| **4. Monotonicity** — (a) more insulation ⇒ heat does not increase | PASS | PASS | PASS |
| 4. (b) gains +20% ⇒ heat does not increase | 1/3 seeds FAIL | 1/3 seeds FAIL (+2.6%) | **FAIL (3/3, +1.9 to +3.4%)** |
| 4. (b) gains +20% ⇒ cool does not decrease | **FAIL (3/3)** | PASS | **FAIL (3/3)** |
| 4. (c) summer T_out +2 K ⇒ cool does not decrease | PASS | PASS | PASS |
| **5. Energy balance** (rollout year): total / heat / cool (%) | +0.04 / +0.50 / −0.81 | +0.62 / +1.34 / −0.72 | −0.54 / +1.13 / −3.66 |

All three models stay bounded in every rollout (test year, all OOD variants,
both extreme weeks) — no blow-up anywhere. SS-DFA's error grows steadily over
the rollout year (drift −4.4 °C/month worst seed; max |err| 7.9 °C) without
diverging.

Scoring note (reported, not fixed post hoc): `evaluate.py` codes five sub-checks
and its `insul_half_no_increase` sub-check demands that *halving* insulation not
increase heating — the reverse of the brief's stated check and of physics. All
three models in fact predict **more** heating for the worse-insulated envelope
(+64 to +69%), i.e. the physically correct response, which the coded sub-check
marks "fail". The table above counts the brief's four sign checks as written;
the verdict does not hinge on this (SS-DFA fails the two unambiguous gains
checks).

## 4. Noise gate (§6; SS-DFA and LSTM, seed 11, no retraining/recalibration)

Quantisation: symmetric per-tensor, round-to-nearest, weights and activations
at every arithmetic site. Noise (7-bit only): Gaussian, σ = 1%/3% of each
tensor's own range (2·max|a|), applied after quantisation at every site.
Drift (7-bit only): per-tensor Ornstein–Uhlenbeck, τ = 730 h, σ_eq = 1%,
advanced and applied once per rollout hour, covering the SS-DFA fixed
W_in/W_res/W_fb too; one-step under drift uses end-of-year weights.

| Condition | SS-DFA rollout RMSE (°C) / ×FP32 | SS-DFA 1-step ×FP32 | LSTM rollout RMSE (°C) / ×FP32 | LSTM 1-step ×FP32 |
|---|---|---|---|---|
| FP32 (reference) | 2.417 / 1.00 | 1.00 | 0.685 / 1.00 | 1.00 |
| 8-bit | 2.429 / 1.01 | 1.05 | 0.709 / 1.04 | 1.02 |
| **7-bit** | **2.415 / 1.00** | 1.00 | **0.687 / 1.00** | 1.07 |
| 7-bit + 1% noise | 2.294 / 0.95 | 1.22 | 0.808 / 1.18 | 2.34 |
| 7-bit + 3% noise | 2.413 / 1.00 | 2.25 | 1.639 / **2.39** | 6.15 |
| 7-bit + drift | 2.444 / 1.01 | 1.01 | 0.622 / 0.91 | 1.04 |
| 6-bit | 2.727 / 1.13 | 1.23 | 0.744 / 1.09 | 1.45 |

Every condition stayed bounded. **Gate rule (7-bit rollout ≤ 2× FP32 and no
divergence): SS-DFA PASSES** — clean 7-bit 1.00×, worst 7-bit condition
(drift) 1.01×. The LSTM passes clean 7-bit (1.00×) but under the stricter
reading including the injected 3% noise it exceeds 2× (2.39×). The photonic
*inference* story survives for SS-DFA; it is the FP32 *training* accuracy that
fails the POC.

## 5. Figures (§5, free-running rollout)

- `figures/weeks_mlp.png`, `figures/weeks_lstm.png`, `figures/weeks_ssdfa.png` —
  predicted vs teacher zone temperature for the hottest week (h 4536–4703) and
  coldest week (h 0–167) of the test year. The SS-DFA plot shows visible
  cold-drift across the coldest week; MLP/LSTM track the teacher closely.

## 6. What failed, what was not tested, what would change the recommendation

**Failed / findings**

- SS-DFA accuracy: 2.2× worse rollout RMSE than the LSTM, with large seed
  variance (2.42 / 1.05 / 0.91 °C) and a systematic cold drift in multi-month
  free-running rollouts. One-step error is much closer (1.31×) — the deficit is
  accumulated-state error, which is exactly what a fixed-map reservoir without
  gradient flow through time struggles to correct.
- Internal-gains counterfactuals: SS-DFA's predicted heating rises ~2.6% (all
  seeds +1.9 to +3.4%) and cooling falls ~2.4% under +20% internal gains (wrong
  signs) at every seed.
- The MLP also fails the cooling-gains check at all seeds (−1.5 to −3.9%), and
  the LSTM fails the heating-gains check at one seed (+2.6%) — the counterfactual
  is applied through each model's own input interface, and both feed-forward
  models partially ignore the gains channel. The LSTM still passes 11 of its
  12 seed-level sign checks, so the machinery is not broken.

**Not tested (out of scope under this brief)**: noise-aware or quantisation-aware
retraining; reservoir sizes/gains beyond the 5-config budget; hybrid DFA/BPTT
schemes (e.g. truncated sensitivity propagation — this starts to look like BPTT
and was deliberately not attempted); multi-zone or real (TMY) weather; EnergyPlus
teachers; optical hardware or vendor SDKs; ASHRAE 140 / full Guideline 14
validation (the teacher is a simplified 2R2C model).

**What would change the recommendation**: a state-skipping scheme that lifts the
best-seed rollout RMSE within 20% of the LSTM across seeds (e.g. via a longer or
better-conditioned single map, or a cheap forward-mode sensitivity through the
reservoir that still avoids storing trajectories); or a demonstrated training-
cost crossover at a scale where the LSTM becomes genuinely expensive while
SS-DFA accuracy stays acceptable. Neither is a small step, and both belong in a
separate, explicitly funded experiment.

## 7. Run log

- **Hardware:** CPU only — 4 cores, torch 2.15.0+cpu, numpy 2.5.4, Python 3.12
  (`.venv`). No GPU was available or used.
- **Wall-clock (all runs, 2026-11-06 UTC):** dataset 04:21–04:24; baseline +
  SS-DFA tuning and 3-seed finals 04:30–06:18 (≈1 h 48 m; 24 full trainings =
  15 tuning + 9 finals, plus short smoke runs);
  verification/smoke 11:51–12:50; §5 physics eval 12:41–12:50 (9 min, single
  process, all 3 models × 3 seeds); §6 noise gate 12:53–13:05 (12 min).
  Total elapsed ≈ 8.7 h, well inside the 25–40 h effort box; the 40 h stop rule
  was not approached.
- **Steps exceeding their time box:** none in §§4–6. §5 and §6 finished far
  inside their boxes (9 min vs 6–10 h; 12 min vs 3–5 h).
- **Incidents:** one VM restart at ~12:23 UTC killed run 4 mid-smoke (no
  artefact loss; weights and tuning results were already on disk). Three issues
  were found and fixed in this run's verification phase: (1) batch-1 rollout steps
  were ~100× slower than necessary from OpenMP thread contention (fixed by
  pinning 1 thread in the eval scripts — scheduling only, no math change);
  (2) the quantised-LSTM cell broadcast `(B,H)` gate activations against a
  `(1,B,H)` state, silently producing `(1,B,3)` outputs (fixed; FP32 path and
  all §5 results were unaffected — they use `nn.LSTM` directly); (3) the §6
  drift process was initialised but never advanced (`Drift.step()` was never
  called), so the required drift condition was silently inert (fixed: drift is
  now advanced and applied per rollout hour; the whole §6 gate was re-run with
  drift active).

## 8. Reproduction

See `README.md`. One command from scratch (data → training → headline + physics
tables + figures): `python src/train.py` after `python src/gen_data.py`, then
`python src/evaluate.py`; the noise gate is `python src/noise_gate.py`. All
result JSON lives in `results/` (`physics_eval.json`, `noise_gate.json`,
`noise_gate_verdict.json`, `tuned_*.json`, `tuning_log.json`).

## Claims

- [observed] Mean test-year rollout temperature RMSE: SS-DFA 1.457 ± 0.834 °C vs LSTM 0.662 ± 0.041 °C vs MLP 0.616 ± 0.051 °C (3 seeds: 11/22/33) — source: `results/physics_eval.json` (per-seed `rollout.temp.rmse`), tabulated in REPORT.md §2.
- [observed] SS-DFA/LSTM rollout-RMSE ratio is 2.20× on seed means, with per-seed matched ratios 3.53× / 1.52× / 1.48× — source: `results/physics_eval.json` (per-seed `rollout.temp.rmse`), REPORT.md §2.
- [observed] One-step temperature RMSE: SS-DFA 0.355 ± 0.008 °C vs LSTM 0.271 ± 0.020 °C vs MLP 0.236 ± 0.007 °C; 24 h RMSE SS-DFA 1.108 °C vs LSTM 0.628 °C vs MLP 0.619 °C — source: `results/physics_eval.json` (per-seed `one_step_temp`, `h24_temp`), REPORT.md §2–§3.
- [observed] SS-DFA fails the brief's two internal-gains sign checks at every seed (heating rises +1.9 to +3.4 %, cooling falls ~2.4 %), while all three models stay bounded with no blow-up in every rollout (test year, OOD variants, both extreme weeks) — source: `results/physics_eval.json` (monotonicity counterfactuals, `rollout.bounded`), REPORT.md §3.
- [observed] SS-DFA has 503 trainable parameters (27,543 total) vs 40,227 for the LSTM; training wall-clock 80 ± 5 s vs 336 ± 239 s (4.2× faster); recurrent state evaluations 0.026 M vs 12.5 M — source: `results/physics_eval.json` (`training_cost`), REPORT.md §2.
- [observed] The 7-bit noise gate passes for SS-DFA: clean 7-bit rollout ratio 1.00× and worst 7-bit condition (drift) 1.01×, no divergence; the LSTM's worst 7-bit condition (3 % noise) reaches 2.39× and fails the strict 2× reading — source: `results/noise_gate_verdict.json` (`passes_gate`, `worst_7b_ratio`, `passes_gate_strict`), REPORT.md §4.
- [observed] All headline, physics-table and noise-gate numbers are committed as JSON under `results/` (`physics_eval.json`, `noise_gate.json`, `noise_gate_verdict.json`, `tuning_log.json`); the dataset regenerates bit-identically from seed 20261105 via `python src/gen_data.py` — source: `results/` and REPORT.md §1, §8.
- [inference] SS-DFA misses the brief's primary accuracy bar by a wide margin: 2.20× rollout RMSE is far beyond the 50 % no-go line, and the 2-of-4 physics sign-check failure independently trips the no-go clause — from the rollout-RMSE and sign-check observations above.
- [inference] The deficit is accumulated-state error rather than one-step error (one-step ratio 1.31× vs 2.20× on rollout RMSE), with a systematic cold drift over the rollout year (worst seed −4.44 °C/month drift, max |err| 7.9 °C) — from the one-step/rollout RMSE and physics-table observations above.
- [inference] The Conditional escape clause ("under half the LSTM's wall-clock at comparable accuracy") does not apply, because SS-DFA's accuracy is not comparable to the LSTM's — from the rollout-RMSE and training-cost observations above.
- [inference] The extension of the paper's claim from MNIST/CIFAR-10 classification to building-surrogate regression is not supported by this POC — from the rollout-RMSE and sign-check observations above.
- [unsupported] The standard DFA + reservoir reading of SS-DFA adopted for this implementation (the paper's exact formulation was not available; REPORT.md §1 assumption set, §4.3) — carried as an assumption; NOT a premise for any verdict in this artifact, and not used as evidence for the No-go.
- [unsupported] The assumption that ~7-bit precision plus the injected analogue-noise model (σ = 1 % / 3 % of each tensor's own range, per-tensor OU drift) stands in for the photonic hardware this POC targets — carried as an assumption; NOT a premise for any verdict in this artifact, and not used as evidence for the No-go.
- [decision] Record this POC as No-go: SS-DFA is 2.2× worse than the LSTM on full-year rollout RMSE, and the Conditional escape clause does not apply — operator, 2026-11-06 (run date, REPORT.md §7).

## Hypothesis updates

- H1 "can train a small building-thermal surrogate as well as ordinary backpropagation" (hypothesis as stated in the POC `README.md`) — update: refuted (2.20× rollout RMSE vs the LSTM; REPORT.md §2).
- H2 "whether the result survives the ~7-bit precision optical hardware would impose" (hypothesis as stated in the POC `README.md`) — update: supported for the 7-bit noise gate as run (1.00× clean, 1.01× worst 7-bit condition; REPORT.md §4).

