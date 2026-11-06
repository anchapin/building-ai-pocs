# SS-DFA surrogate POC

A self-contained proof-of-concept testing whether **SS-DFA** — state-skipping
Direct Feedback Alignment (Zhang et al., *Nature Computational Science*, 5 Nov
2026, doi:10.1038/s43588-026-01075-w) with a single-map reservoir — can train a
small building-thermal surrogate as well as ordinary backpropagation, and
whether the result survives the ~7-bit precision optical hardware would impose.

Three models on identical data (2R2C RC teacher, 3 synthetic weather years +
3 held-out envelope variants):

- **MLP** — feed-forward on a 24 h window, Adam + backprop
- **LSTM** — 96-unit LSTM, Adam + truncated BPTT (the bar SS-DFA must clear)
- **SS-DFA** — fixed random reservoir + one reused tanh map + trainable readout
  (503 trainable params), trained by the state-skipping DFA path: no BPTT, no
  stored state trajectory (asserted in `src/train.py:dfa_epoch`)

Verdict and full analysis: **`REPORT.md`** (No-go — SS-DFA is 2.2× worse than
the LSTM on full-year rollout RMSE but passes the 7-bit noise gate).

## Reproducing the headline results table

One command, from nothing (CPU, ~2 h):

```bash
python src/gen_data.py && python src/train.py && python src/evaluate.py
```

`gen_data.py` regenerates the identical dataset from seed 20261105
(`data/meta.json` holds every parameter). `train.py` runs the fixed 5-config
tuning sweep and the 3-seed finals for all three models and writes
`results/tuned_*.json`, `results/best_configs.json`, `weights/*.pt`.
`evaluate.py` loads those weights and writes the headline + physics tables to
`results/physics_eval.json` and the hottest/coldest-week plots to `figures/`.
The headline table in `REPORT.md` §2 is `results/physics_eval.json` →
`training_cost` (train wall, params) joined with each model's
`one_step_temp` / `h24_temp` / `rollout` metrics averaged over seeds 11/22/33.

The noise gate runs last and separately (~12 min, no retraining):

```bash
python src/noise_gate.py        # -> results/noise_gate.json, results/noise_gate_verdict.json
```

If the trained weights are already present, `evaluate.py` alone reproduces the
headline and physics tables in ~9 min.

## Layout

```
src/gen_data.py    2R2C RC teacher, 3 years + 3 OOD envelope variants
src/common.py      splits, scalers (train-year-only fit), Guideline-14 metrics
src/models.py      MLP, LSTM, SSDFA + quantisation/noise hooks (§6 only)
src/train.py       fixed tuning grids, DFA training path, 3-seed finals
src/evaluate.py    §5 physics eval: 1-step/24 h, 8,760 h rollout, OOD,
                   monotonicity counterfactuals, energy balance, plots
src/noise_gate.py  §6: 8/7/6-bit PTQ, 1%/3% analogue noise, OU weight drift
src/diag_ssdfa.py  SS-DFA training diagnostics
data/              dataset + meta.json (all teacher parameters, seed 20261105)
results/           every table in REPORT.md, as JSON
figures/           weeks_{mlp,lstm,ssdfa}.png
```

## Environment

Python 3.12, `pip install -r requirements.txt` (torch 2.15.0+cpu, numpy 2.5.4,
matplotlib 3.11.2). CPU only; the eval scripts pin 1 thread (batch-1 rollout
steps are ~100× faster without thread contention).
