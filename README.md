# Building AI POCs

Small, time-boxed proof-of-concept experiments at the intersection of AI and building energy modeling. Each POC is 25–40 hours, standalone, and judged by a fixed go/no-go gate written *before* any results.

A clean negative result is a successful outcome — it saves a proposal cycle. No POC here is a product, a Fluxion replacement, or a claim of ASHRAE 140 compliance.

## How a POC works

1. A brief defines one narrow question, baselines, physics checks, and fixed go/no-go thresholds.
2. The work is standalone (Python/PyTorch, synthetic or open data). No Fluxion integration, no hardware, no licensed data as a first step.
3. The deliverable is code + a `REPORT.md` that leads with exactly one label: **Go**, **Go (software only)**, **Conditional**, or **No-go**.
4. Winners may be promoted: to a standalone repo, into Fluxion, into Matchline, or into an NLR LDRD proposal. Losers stay here as a recorded negative result.

## Claim typing in proposals and reports

Every POC proposal and every `REPORT.md` carries a `## Claims` section listing its *load-bearing* claims — statements offered as evidence for the verdict, founding premises/hypotheses the verdict depends on, or the verdict's direct justification. Ordinary prose needs no tags; load-bearing claims each carry exactly one:

- `[observed]` — a measured fact, **with its source in the same line** (a command and its output, a file:line, a ledger count with n, a run/PR ID, a URL). No source, no `[observed]`.
- `[inference]` — a conclusion drawn from observations; cite the observations it is drawn from.
- `[unsupported]` — an assumption carried forward, named as such. It may be carried and tested; it may **never** be a premise for a Go/No-go, and it must never appear in the report's verdict or ask lines.
- `[decision]` — the operator's call, **with its date**. A decision is not evidence.

Copyable template:

```markdown
## Claims

- [observed] <claim> — source: <command / file:line / ledger, n>
- [inference] <claim> — from <the observations cited above>
- [unsupported] <claim> — carried as an assumption; NOT a premise for any verdict in this artifact
- [decision] <claim> — <name>, <YYYY-MM-DD>

## Hypothesis updates (reports, at verdict time)

- H<n> <hypothesis, verbatim from the proposal> — update: supported | weakened | refuted | untested
```

`untested` is a valid, honest update — a hypothesis the POC did not reach stays untested; it is never silently dropped and never upgraded to supported by proximity to a Go.

Why: claim-typing a past POC's report found two premises its No-go verdict rested on that were assumptions, invisible until typed (the SS-DFA standard-reading assumption and an uncited hardware-precision premise). Typing costs minutes and makes that class of hidden premise visible before the verdict, not after.

Lint (advisory, blocks nothing): `python3 ~/workspace/plan-coder-repo/bin/claimcheck.py lint <artifact.md>` — exit 1 lists violations (untagged claim, `[observed]` without a source, `[unsupported]` in a premise/verdict position, or a missing `## Claims` section); exit 0 = clean. (Product-engineering spike Part D, plan-coder; enabled 2026-11-10.)

## POCs

| Folder | Idea | Status |
| --- | --- | --- |
| `ss-dfa-surrogate-poc/` | SS-DFA / single-map (optical-AI framework) as a cheap-to-train thermal surrogate. Baseline for the photonic question. | No-go — SS-DFA is 2.2× worse than the LSTM on full-year rollout RMSE but passes the 7-bit noise gate |
| `retrofit-copilot/` | Matchline drawing → calibrated baseline → neuro-symbolic agent ranking energy-conservation measures. | **Go** — spun out to [anchapin/retrofit-copilot](https://github.com/anchapin/retrofit-copilot) (2026-11-06) |
| `neural-operator-surrogate/` | Differentiable neural-operator / PINN surrogate for a slow BEM component, standalone. | No-go — POC closed (slice 3 closes the POC): heat-balance residual <5% gate NOT MET by any honest arm (best 7.8% in-distribution, 51–73% on unseen weather/both); speedup ≥50× gate NOT MET (standing ~1×) |
| `drawing-verifier/` | VLM + neuro-symbolic verifier hardening drawing-to-BEM (Matchline). | In progress (slice 3: shared-wall zone membership; label Conditional) |
| `world-model-hvac-control/` | Diffusion / world-model HVAC control for grid-interactive buildings. | No-go (verdict 2026-11-06: world-model + MPC fails the ≥5%-at-equal-comfort gate on both unseen sets in two independent runs; LSTM hidden state unobservable from the 10-float observation) |
| `federated-calibration/` | Federated, physics-informed calibration across simulated buildings. | No-go (verdict 2026-11-06: FedAvg never beats one-shot parameter averaging by ≥15%; IID control fires the No-go trigger) |
| `local-first-building-agent/` | Small on-device models as a building agent, benchmarked against a frontier model. | Not started |

Closing note: the previous "Suggested order" line is withdrawn — it pointed at POCs that are closed. The status board above is the source of truth: every POC is closed except `drawing-verifier/` (**Conditional** — the symbolic-checker half is demonstrated and measured; the VLM second-reader half is deferred, and no Matchline extraction run was performed) and `local-first-building-agent/` (**Not started**). Closed: `ss-dfa-surrogate-poc/` (**No-go**), `retrofit-copilot/` (**Go** — spun out to [anchapin/retrofit-copilot](https://github.com/anchapin/retrofit-copilot)), `neural-operator-surrogate/` (**No-go**), `world-model-hvac-control/` (**No-go**), `federated-calibration/` (**No-go**).

## Background

- Zhang et al., "Scalable physical deep learning using optical dynamics with state-skipping training and single-map architecture," *Nature Computational Science*, 5 Nov 2026. doi:10.1038/s43588-026-01075-w
- Fluxion: https://github.com/anchapin/fluxion — physics-based building simulation engine.
- Matchline: https://github.com/anchapin/matchline — drawing-to-BEM prototype.

## License

MIT. See `LICENSE`.
