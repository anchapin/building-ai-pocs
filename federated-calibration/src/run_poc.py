"""Single reproduce entry point for the federated-calibration POC (slice 1).

    python src/run_poc.py --seed 42

Prints the headline table (isolated-local vs federated vs centralised on a
held-out building), the per-building rows and the FedAvg diagnostics, and
writes the same numbers to `data/results_seed*.json`.

`--seed` accepts a comma-separated list (e.g. `--seed 42,43,44`); with more
than one seed a mean +/- std summary over the seeds is printed as well.
The output is fully deterministic: no timestamps, no unseeded randomness.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate import (DEFAULT_DATA_DIR, LOCAL_BUDGETS, _rel_change,  # noqa: E402
                      run_seed)


def _parse_seeds(text: str) -> List[int]:
    seeds = [int(s) for s in str(text).replace(" ", "").split(",") if s]
    if not seeds:
        raise ValueError("no seed given")
    return seeds


def _summary(results: List[Dict[str, object]]) -> None:
    """Mean +/- std over seeds of the headline numbers (per held-out building)."""
    print("")
    print("summary over %d seed(s)" % len(results))
    print("-" * 78)
    for heldout_name in sorted(results[0]["heldout"].keys()):  # type: ignore[index]
        variants = [r["variant"] for r in results[0]["heldout"][heldout_name]]  # type: ignore[index]
        per_variant = {}
        for i, variant in enumerate(variants):
            per_variant[variant] = [
                float(r["heldout"][heldout_name][i]["rmse_rollout"])  # type: ignore[index]
                for r in results]
        fed_vals = per_variant["zero-shot, FedAvg over 9 clients"]
        fed_mean = float(np.mean(fed_vals))
        print("held-out building %s" % heldout_name)
        print("%-42s %10s %10s %12s" % ("variant", "mean", "std", "fed vs iso"))
        for variant in variants:
            vals = per_variant[variant]
            mean = float(np.mean(vals))
            std = float(np.std(vals))
            rel = _rel_change(mean, fed_mean)
            print("%-42s %10.4f %10.4f %+11.1f%%" % (variant, mean, std,
                                                      100.0 * rel))


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=str, default="42",
                        help="seed or comma-separated list of seeds")
    parser.add_argument("--hours", type=int, default=240)
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--local-steps", type=int, default=60)
    parser.add_argument("--fit-steps", type=int, default=400)
    parser.add_argument("--out-dir", default=DEFAULT_DATA_DIR)
    args = parser.parse_args(argv)

    seeds = _parse_seeds(args.seed)
    results = []
    for seed in seeds:
        print("")
        print("=" * 78)
        print("federated-calibration POC, slice 1 -- seed %d" % seed)
        print("=" * 78)
        res = run_seed(seed, hours=args.hours, rounds=args.rounds,
                       local_steps=args.local_steps, fit_steps=args.fit_steps)
        results.append(res)

    os.makedirs(args.out_dir, exist_ok=True)
    for seed, res in zip(seeds, results):
        path = os.path.join(args.out_dir, "results_seed%d.json" % seed)
        with open(path, "w") as fh:
            json.dump(res, fh, indent=2, sort_keys=True)
        print("")
        print("results written: %s" % path)

    if len(results) > 1:
        _summary(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
