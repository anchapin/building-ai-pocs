# Building AI POCs

Small, time-boxed proof-of-concept experiments at the intersection of AI and building energy modeling. Each POC is 25–40 hours, standalone, and judged by a fixed go/no-go gate written *before* any results.

A clean negative result is a successful outcome — it saves a proposal cycle. No POC here is a product, a Fluxion replacement, or a claim of ASHRAE 140 compliance.

## How a POC works

1. A brief defines one narrow question, baselines, physics checks, and fixed go/no-go thresholds.
2. The work is standalone (Python/PyTorch, synthetic or open data). No Fluxion integration, no hardware, no licensed data as a first step.
3. The deliverable is code + a `REPORT.md` that leads with exactly one label: **Go**, **Go (software only)**, **Conditional**, or **No-go**.
4. Winners may be promoted: to a standalone repo, into Fluxion, into Matchline, or into an NLR LDRD proposal. Losers stay here as a recorded negative result.

## POCs

| Folder | Idea | Status |
| --- | --- | --- |
| `ss-dfa-surrogate-poc/` | SS-DFA / single-map (optical-AI framework) as a cheap-to-train thermal surrogate. Baseline for the photonic question. | In progress |
| `retrofit-copilot/` | Matchline drawing → calibrated baseline → neuro-symbolic agent ranking energy-conservation measures. | **Go** — spun out to [anchapin/retrofit-copilot](https://github.com/anchapin/retrofit-copilot) (2026-11-06) |
| `neural-operator-surrogate/` | Differentiable neural-operator / PINN surrogate for a slow BEM component, standalone. | Not started |
| `drawing-verifier/` | VLM + neuro-symbolic verifier hardening drawing-to-BEM (Matchline). | In progress (slice 3: shared-wall zone membership; label Conditional) |
| `world-model-hvac-control/` | Diffusion / world-model HVAC control for grid-interactive buildings. | Not started |
| `federated-calibration/` | Federated, physics-informed calibration across simulated buildings. | No-go (verdict 2026-11-06: FedAvg never beats one-shot parameter averaging by ≥15%; IID control fires the No-go trigger) |
| `local-first-building-agent/` | Small on-device models as a building agent, benchmarked against a frontier model. | Not started |

Suggested order: drawing verifier first (de-risks the Retrofit Copilot's input), then Retrofit Copilot, then the neural-operator surrogate.

## Background

- Zhang et al., "Scalable physical deep learning using optical dynamics with state-skipping training and single-map architecture," *Nature Computational Science*, 5 Nov 2026. doi:10.1038/s43588-026-01075-w
- Fluxion: https://github.com/anchapin/fluxion — physics-based building simulation engine.
- Matchline: https://github.com/anchapin/matchline — drawing-to-BEM prototype.

## License

MIT. See `LICENSE`.
