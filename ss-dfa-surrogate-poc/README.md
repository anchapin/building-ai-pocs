# SS-DFA Surrogate POC

**Status:** In progress — background worker running, report pending.

**Question:** Can SS-DFA (state-skipping Direct Feedback Alignment) with a single-map architecture train a small building thermal surrogate as well as ordinary backpropagation, and does it survive the ~7-bit precision optical hardware would impose?

**Decision it supports:** Whether to write an NLR LDRD Seed pre-proposal on cheaper-to-train surrogates for Fluxion, with photonics as a possible Phase 2.

**Scope:** Standalone Python/PyTorch, single-zone RC thermal teacher, MLP + LSTM baselines first, then SS-DFA/single-map. Physics evaluation (8,760-step rollout, out-of-distribution, monotonicity, energy balance) plus a separate 7-bit noise gate. No Fluxion integration, no optical hardware.

**Deliverables (when done):** code + dataset generator, `REPORT.md` leading with exactly one label — Go, Go (software only), Conditional, or No-go — and a run log.

**Source paper:** Zhang et al., *Nature Computational Science*, 5 Nov 2026. doi:10.1038/s43588-026-01075-w
