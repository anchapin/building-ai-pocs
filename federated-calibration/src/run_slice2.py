"""Slice-2 experiment driver: adjudicate the parameter-mean caveat.

    python src/run_slice2.py --seed 42,43,44

Slice 1 measured FedAvg on the slice-1 population and found that one-shot
parameter averaging (the mean of the nine fitted parameter vectors) was
*better* than FedAvg -- which would fail issue #5's >=15% gate if the gate
is read against the best non-federated transfer.  This driver runs the
same protocol (3 seeds, same eval window, same 9-client + 2-held-out
setup) on the two cheap discriminating axes named in slice 1 §4:

  * partial participation  -- a per-round random subset of the clients is
    online (`--participation`), so a *single-shot* aggregation only ever
    sees the clients that are online at that moment, while FedAvg keeps
    learning over rounds;
  * client heterogeneity  -- a wider truth-parameter spread ("wide") or a
    clustered non-IID population in three well-separated groups
    ("clustered").
  * iid control           -- every client the same archetype with a tight
    truth spread, re-checking issue #5's No-go trigger "federated ~=
    centralised on IID synthetic data".

Everything is deterministic: the client subsets are drawn from a seeded
generator, so two runs produce byte-identical JSONs.

The output is written to `data/slice2_results.json` and a mean +/- std
summary over the seeds is printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Sequence

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate import DEFAULT_DATA_DIR, _rel_change, run_seed  # noqa: E402

# The transfer rows that matter for the gate.
VARIANT_FEDAVG = "zero-shot, FedAvg over 9 clients"
VARIANT_PARAM_MEAN = "zero-shot, parameter-mean of 9 client models"
VARIANT_DONOR_MEAN = "zero-shot, mean donor RMSE (9 isolated models)"
VARIANT_DONOR0 = "zero-shot, donor client-0 model"
VARIANT_CENTRAL = "zero-shot, one model on pooled data"

# (label, heterogeneity, participation)
CONFIGS: List[tuple] = [
    ("baseline (slice-1 control)", "baseline", 1.0),
    ("partial participation p=0.5", "baseline", 0.5),
    ("wide heterogeneity", "wide", 1.0),
    ("clustered heterogeneity", "clustered", 1.0),
    ("clustered + participation p=0.5", "clustered", 0.5),
    ("iid control (No-go trigger check)", "iid", 1.0),
]


def _rows(result: Dict[str, object], heldout: str) -> Dict[str, Dict]:
    return {r["variant"]: r for r in result["heldout"][heldout]}  # type: ignore[index]


def _param_mean_variants(rows: Dict[str, Dict]) -> List[str]:
    return [v for v in rows if v.startswith("zero-shot, parameter-mean")]


def run_config(seeds: Sequence[int], heterogeneity: str, participation: float,
               hours: int = 240, rounds: int = 15, local_steps: int = 60,
               fit_steps: int = 400, verbose: bool = False) -> List[Dict]:
    out = []
    for seed in seeds:
        res = run_seed(seed, hours=hours, rounds=rounds,
                       local_steps=local_steps, fit_steps=fit_steps,
                       heterogeneity=heterogeneity, participation=participation,
                       verbose=verbose)
        out.append(res)
    return out


def summarise(label: str, results: List[Dict]) -> Dict[str, object]:
    """Mean +/- std over seeds of every transfer row, per held-out building."""
    summary: Dict[str, object] = {"config": label}
    per_building: Dict[str, object] = {}
    for heldout in sorted(results[0]["heldout"].keys()):  # type: ignore[index]
        variants = [r["variant"] for r in results[0]["heldout"][heldout]]  # type: ignore[index]
        table: Dict[str, Dict[str, float]] = {}
        for v in variants:
            vals = [float(_rows(r, heldout)[v]["rmse_rollout"]) for r in results]
            table[v] = {"mean": float(np.mean(vals)),
                        "std": float(np.std(vals)),
                        "values": vals}
        fed = table[VARIANT_FEDAVG]["mean"]
        table["_gate"] = {}
        for v in variants:
            if v == VARIANT_FEDAVG:
                continue
            table["_gate"][v] = {  # type: ignore[index]
                "rel_change_fedavg_vs_row": _rel_change(table[v]["mean"], fed),
                "improvement_pct": -100.0 * _rel_change(table[v]["mean"], fed),
            }
        per_building[heldout] = table
    summary["heldout"] = per_building
    # non-IID diagnostics (mean over seeds)
    diag = results[0]["federated_diagnostics"]
    summary["max_client_update_spread"] = [
        float(r["federated_diagnostics"]["max_client_update_spread"])
        for r in results]
    summary["global_rmse_per_round_on_probe"] = [
        r["federated_diagnostics"]["global_model_rmse_per_round_on_probe"]
        for r in results]
    summary["distinct_participants"] = [
        r["federated_diagnostics"].get("distinct_participants")
        for r in results]
    return summary


def print_summary(summary: Dict[str, object]) -> None:
    print("")
    print("=" * 78)
    print("config: %s" % summary["config"])
    print("=" * 78)
    for heldout, table in summary["heldout"].items():  # type: ignore[union-attr]
        print("held-out building %s" % heldout)
        print("%-52s %9s %9s %11s" % ("variant", "mean", "std", "fed vs row"))
        for v, d in table.items():  # type: ignore[union-attr]
            if v == "_gate":
                continue
            g = table["_gate"].get(v, {})  # type: ignore[index]
            rel = g.get("rel_change_fedavg_vs_row")
            rel_s = "%+10.1f%%" % (100.0 * rel) if rel is not None else " " * 11
            print("%-52s %9.4f %9.4f %11s" % (v, d["mean"], d["std"], rel_s))
    print("max client-update spread per seed: %s" % (
        ", ".join("%.3f" % v for v in summary["max_client_update_spread"])))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=str, default="42,43,44")
    parser.add_argument("--hours", type=int, default=240)
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--local-steps", type=int, default=60)
    parser.add_argument("--fit-steps", type=int, default=400)
    parser.add_argument("--out-dir", default=DEFAULT_DATA_DIR)
    args = parser.parse_args(argv)

    seeds = [int(s) for s in str(args.seed).replace(" ", "").split(",") if s]
    if not seeds:
        raise ValueError("no seed given")

    all_results: Dict[str, object] = {}
    for label, heterogeneity, participation in CONFIGS:
        results = run_config(seeds, heterogeneity, participation,
                              hours=args.hours, rounds=args.rounds,
                              local_steps=args.local_steps,
                              fit_steps=args.fit_steps)
        key = "%s|%s|p%g" % (heterogeneity, participation, participation)
        summary = summarise(label, results)
        all_results[key] = {
            "label": label,
            "heterogeneity": heterogeneity,
            "participation": participation,
            "seeds": seeds,
            "summary": summary,
            "per_seed": results,
        }
        print_summary(summary)

    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, "slice2_results.json")
    with open(path, "w") as fh:
        json.dump(all_results, fh, indent=2, sort_keys=True)
    print("")
    print("results written: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
