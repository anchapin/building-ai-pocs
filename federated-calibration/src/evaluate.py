"""Evaluation harness for the federated-calibration POC (slice 1).

One command prints the headline table:

    python src/run_poc.py --seed 42

The headline is the *zero-shot transfer* comparison on a held-out building
H that no arm was allowed to train on (except the isolated-local arms,
which are the baselines that are allowed to use H's own data):

    isolated-local  : H calibrated with its own data (several data budgets)
                      + the zero-shot isolated baseline (a single other
                      building's local model applied to H)
    federated       : FedAvg over the nine client buildings; H's data is
                      never seen by the server or by any client
    centralised     : one parameter set fitted on all nine clients' pooled
                      data (upper-bound reference; it *may* see raw data)

All arms are evaluated on the same window of H (the hours after the
isolated-local data budget) and with the same free-running rollout, so the
comparison is apples-to-apples.

Also reported: per-building rows for the nine clients, the FedAvg round
diagnostics (client-update spread -- the non-IID indicator) and the
relative RMSE change of the federated arm against each isolated baseline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from federate import Client, FedAvgServer, RoundRecord, run_fedavg  # noqa: E402
from gen_buildings import (DEFAULT_HOURS, Building, generate_population)  # noqa: E402
from local_model import (LocalFit, NOMINAL_PARAMS, PARAM_NAMES, fit_local,  # noqa: E402
                         fit_pooled, one_step_rmse, rmse, rmse_on_window,
                         rollout)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(PROJECT_DIR, "data")

# Local data budgets (hours) of the isolated-local arm on the held-out
# building.  The evaluation window starts at the largest budget, so every
# arm is scored on data none of them was trained on.
LOCAL_BUDGETS: Tuple[int, ...] = (6, 12, 24, 48, 72)

ARM_ISO = "isolated-local"
ARM_FED = "federated (FedAvg)"
ARM_CENTRAL = "centralised (pooled)"

COMFORT_LO = 17.0   # degC, lower comfort bound of the sanity check
COMFORT_HI = 25.0   # degC, upper comfort bound of the sanity check


def _rel_change(base: float, new: float) -> float:
    """Relative RMSE change of `new` vs `base` (negative = improvement)."""
    if base == 0 or not np.isfinite(base):
        return float("nan")
    return (new - base) / base


class Experiment:
    """Everything the three arms need, for one generated population."""

    def __init__(self, seed: int, hours: int = DEFAULT_HOURS,
                 rounds: int = 15, local_steps: int = 60,
                 fit_steps: int = 400, lr: float = 0.05):
        self.seed = int(seed)
        self.hours = int(hours)
        self.rounds = int(rounds)
        self.local_steps = int(local_steps)
        self.fit_steps = int(fit_steps)
        self.lr = float(lr)

        self.client_buildings, self.heldout_buildings = generate_population(
            self.seed, self.hours)
        self.clients = [Client(b.name, b.client_series())
                        for b in self.client_buildings]
        self.eval_start = max(LOCAL_BUDGETS)
        self.eval_end = self.hours

        # (1) isolated-local: every client calibrated on its own data only.
        self.local_fits: List[LocalFit] = [
            c.local_fit(NOMINAL_PARAMS, steps=self.fit_steps, lr=self.lr)
            for c in self.clients]

        # (2) federated: FedAvg over parameter updates only.
        self.server = FedAvgServer(NOMINAL_PARAMS)
        self.records: List[RoundRecord] = run_fedavg(
            self.clients, self.server, rounds=self.rounds,
            local_steps=self.local_steps, lr=self.lr)
        self.fed_params = dict(self.server.global_params)

        # (3) centralised reference: pooled data, single parameter set.
        self.central_fit = fit_pooled(
            [b.client_series() for b in self.client_buildings],
            init_params=NOMINAL_PARAMS, steps=self.fit_steps, lr=self.lr)
        self.central_params = dict(self.central_fit.params)

    # ------------------------------------------------------------------
    # arms
    # ------------------------------------------------------------------
    def iso_local_params(self, building: Building, budget: int) -> Dict[str, float]:
        """Isolated-local calibration of `building` on its first `budget` h."""
        fit = fit_local(building.client_series(), init_params=NOMINAL_PARAMS,
                        steps=self.fit_steps, lr=self.lr, start=0, end=budget)
        return dict(fit.params)

    def arm_rows(self, building: Building) -> List[Dict[str, object]]:
        """Every arm evaluated on the held-out building `building`."""
        series = building.client_series()
        start, end = self.eval_start, self.eval_end
        rows: List[Dict[str, object]] = []

        def _row(arm: str, variant: str, train_data: str, params: Mapping[str, float],
                 uses_h_data: bool) -> Dict[str, object]:
            pred = rollout(params, series, start=start, end=end)
            truth = np.asarray(series["t_zone"], dtype=np.float64)[start:end]
            comfort = float(np.mean((pred >= COMFORT_LO) & (pred <= COMFORT_HI)))
            return {
                "arm": arm,
                "variant": variant,
                "train_data": train_data,
                "rmse_rollout": rmse(pred, truth),
                "rmse_one_step": one_step_rmse(params, series, start, end),
                "pred_min": float(pred.min()),
                "pred_max": float(pred.max()),
                "frac_hours_comfort": comfort,
                "params": {k: float(params[k]) for k in PARAM_NAMES},
                "uses_h_data": uses_h_data,
            }

        for budget in LOCAL_BUDGETS:
            params = self.iso_local_params(building, budget)
            rows.append(_row(ARM_ISO, "own data, first %d h" % budget,
                              "H's own series, %d h" % budget, params, True))

        full = fit_local(series, init_params=NOMINAL_PARAMS,
                         steps=self.fit_steps, lr=self.lr)
        rows.append(_row(ARM_ISO, "own data, full series (in-sample)",
                         "H's own series, %d h" % self.hours, full.params, True))

        # zero-shot isolated baselines: each client's local model applied to H.
        # Two summaries, kept distinct because they answer different
        # questions: the mean of the nine donors' RMSEs is the expected
        # zero-shot error of picking one isolated model at random (the
        # issue's "isolated-local" baseline); the parameter-mean model is a
        # one-shot average of the nine parameter vectors (no FedAvg rounds),
        # which is itself a form of aggregation.
        donor_stats = []
        for fit in self.local_fits:
            pred_d = rollout(fit.params, series, start=start, end=end)
            truth_d = np.asarray(series["t_zone"], dtype=np.float64)[start:end]
            donor_stats.append({
                "rmse": rmse(pred_d, truth_d),
                "one_step": one_step_rmse(fit.params, series, start, end),
                "pred_min": float(pred_d.min()),
                "pred_max": float(pred_d.max()),
                "comfort": float(np.mean(
                    (pred_d >= COMFORT_LO) & (pred_d <= COMFORT_HI))),
            })
        rows.append(_row(ARM_ISO, "zero-shot, donor client-0 model",
                         "client-0's own series only", self.local_fits[0].params,
                         False))
        rows.append({
            "arm": ARM_ISO,
            "variant": "zero-shot, mean donor RMSE (9 isolated models)",
            "train_data": "9 separate client models, mean of their zero-shot RMSEs",
            "rmse_rollout": float(np.mean([d["rmse"] for d in donor_stats])),
            "rmse_one_step": float(np.mean([d["one_step"] for d in donor_stats])),
            "pred_min": float(np.mean([d["pred_min"] for d in donor_stats])),
            "pred_max": float(np.mean([d["pred_max"] for d in donor_stats])),
            "frac_hours_comfort": float(np.mean([d["comfort"] for d in donor_stats])),
            "params": {k: float(np.mean([f.params[k] for f in self.local_fits]))
                       for k in PARAM_NAMES},
            "uses_h_data": False,
        })
        mean_iso_params = {k: float(np.mean([f.params[k] for f in self.local_fits]))
                           for k in PARAM_NAMES}
        rows.append(_row(ARM_ISO,
                         "zero-shot, parameter-mean of 9 client models",
                         "9 client parameter vectors averaged once (no FedAvg rounds)",
                         mean_iso_params, False))

        rows.append(_row(ARM_FED, "zero-shot, FedAvg over 9 clients",
                         "parameter updates only (no raw series)",
                         self.fed_params, False))
        rows.append(_row(ARM_CENTRAL, "zero-shot, one model on pooled data",
                         "all 9 clients' raw series pooled",
                         self.central_params, False))
        return rows

    def per_building_rows(self) -> List[Dict[str, object]]:
        """Per-building rows for the nine clients (same window, same arms)."""
        rows: List[Dict[str, object]] = []
        start, end = self.eval_start, self.eval_end
        for b, client, local_fit in zip(self.client_buildings, self.clients,
                                        self.local_fits):
            series = b.client_series()
            iso72 = self.iso_local_params(b, self.eval_start)
            rows.append({
                "building": b.name,
                "vintage": b.vintage,
                "climate": b.climate,
                "rmse_iso_72h": rmse_on_window(iso72, series, start, end),
                "rmse_iso_full": rmse_on_window(local_fit.params, series, 0, end),
                "rmse_fed": rmse_on_window(self.fed_params, series, start, end),
                "rmse_central": rmse_on_window(self.central_params, series,
                                                start, end),
            })
        return rows

    def fed_diagnostics(self, probe: Optional[Building] = None
                         ) -> Dict[str, object]:
        """Non-IID diagnostics of the federated run (scalars only).

        `probe` is the held-out building used to watch the global model
        across rounds (evaluation only -- the probe's data never enters
        the federation).
        """
        spreads = [r.spread() for r in self.records]
        local_mean = {k: float(np.mean([f.params[k] for f in self.local_fits]))
                      for k in PARAM_NAMES}
        gap = {k: float((self.fed_params[k] - local_mean[k]) /
                        max(abs(local_mean[k]), 1e-12)) for k in PARAM_NAMES}
        per_round_rmse: List[float] = []
        if probe is not None:
            series = probe.client_series()
            for r in self.records:
                per_round_rmse.append(rmse_on_window(r.global_params, series,
                                                    self.eval_start,
                                                    self.eval_end))
        return {
            "rounds": self.rounds,
            "local_steps": self.local_steps,
            "final_global_params": dict(self.fed_params),
            "mean_of_local_optima": local_mean,
            "centralised_params": dict(self.central_params),
            "fedavg_vs_mean_local_rel_gap": gap,
            "client_update_spread_per_round": spreads,
            "max_client_update_spread": float(max(spreads)) if spreads else 0.0,
            "global_model_rmse_per_round_on_probe": per_round_rmse,
        }


# --------------------------------------------------------------------------
# printing
# --------------------------------------------------------------------------

def print_headline(rows: Sequence[Mapping[str, object]], title: str,
                   baseline_variants: Sequence[str] = ()) -> None:
    print("")
    print(title)
    print("-" * len(title))
    print("%-16s %-38s %12s %12s" % ("arm", "variant", "RMSE_roll", "RMSE_1step"))
    for r in rows:
        print("%-16s %-38s %12.4f %12.4f" % (
            r["arm"], r["variant"], r["rmse_rollout"], r["rmse_one_step"]))
    by_variant = {r["variant"]: r for r in rows}
    fed = by_variant.get("zero-shot, FedAvg over 9 clients")
    if fed is not None:
        for variant in baseline_variants:
            base = by_variant.get(variant)
            if base is None:
                continue
            rel = _rel_change(float(base["rmse_rollout"]),
                              float(fed["rmse_rollout"]))
            print("  federated vs %-38s : %+7.1f%% RMSE (negative = federated better)"
                  % (variant, 100.0 * rel))


def print_per_building(rows: Sequence[Mapping[str, object]]) -> None:
    print("")
    print("per-building rows (nine federated clients, window %d..%d h)"
          % (rows[0]["_start"], rows[0]["_end"]))
    print("%-10s %-11s %-10s %11s %11s %11s %11s" % (
        "building", "vintage", "climate", "iso_72h", "iso_full", "fed", "central"))
    for r in rows:
        print("%-10s %-11s %-10s %11.4f %11.4f %11.4f %11.4f" % (
            r["building"], r["vintage"], r["climate"], r["rmse_iso_72h"],
            r["rmse_iso_full"], r["rmse_fed"], r["rmse_central"]))


def run_seed(seed: int, hours: int = DEFAULT_HOURS, rounds: int = 15,
             local_steps: int = 60, fit_steps: int = 400,
             lr: float = 0.05, verbose: bool = True) -> Dict[str, object]:
    """Run the whole comparison for one seed and return the result dict."""
    exp = Experiment(seed, hours=hours, rounds=rounds,
                     local_steps=local_steps, fit_steps=fit_steps, lr=lr)

    heldout_rows: Dict[str, List[Dict[str, object]]] = {}
    for b in exp.heldout_buildings:
        rows = exp.arm_rows(b)
        heldout_rows[b.name] = rows
        if verbose:
            print_headline(
                rows,
                "held-out building %s (%s / %s) - zero-shot transfer, "
                "window %d..%d h" % (b.name, b.vintage, b.climate,
                                     exp.eval_start, exp.eval_end),
                baseline_variants=("own data, first %d h" % max(LOCAL_BUDGETS),
                                   "zero-shot, mean over 9 isolated client models",
                                   "own data, full series (in-sample)"))

    pb = exp.per_building_rows()
    for r in pb:
        r["_start"] = exp.eval_start
        r["_end"] = exp.eval_end
    if verbose:
        print_per_building(pb)
        probe = exp.heldout_buildings[0]
        diag = exp.fed_diagnostics(probe)
        print("")
        print("FedAvg diagnostics (non-IID indicators)")
        print("  final global parameters : C=%.4g UA=%.4g s=%.4g g_sol=%.4g" % (
            diag["final_global_params"]["C"], diag["final_global_params"]["UA"],
            diag["final_global_params"]["s"],
            diag["final_global_params"]["g_sol"]))
        print("  mean of local optima     : C=%.4g UA=%.4g s=%.4g g_sol=%.4g" % (
            diag["mean_of_local_optima"]["C"], diag["mean_of_local_optima"]["UA"],
            diag["mean_of_local_optima"]["s"],
            diag["mean_of_local_optima"]["g_sol"]))
        print("  centralised (pooled)     : C=%.4g UA=%.4g s=%.4g g_sol=%.4g" % (
            diag["centralised_params"]["C"], diag["centralised_params"]["UA"],
            diag["centralised_params"]["s"],
            diag["centralised_params"]["g_sol"]))
        print("  FedAvg vs mean local optima (relative): C=%+.1f%% UA=%+.1f%% "
              "s=%+.1f%% g_sol=%+.1f%%" % (
                  100 * diag["fedavg_vs_mean_local_rel_gap"]["C"],
                  100 * diag["fedavg_vs_mean_local_rel_gap"]["UA"],
                  100 * diag["fedavg_vs_mean_local_rel_gap"]["s"],
                  100 * diag["fedavg_vs_mean_local_rel_gap"]["g_sol"]))
        print("  client-update spread per round (max rel): %s" % (
            ", ".join("%.3f" % s for s in diag["client_update_spread_per_round"])))
        print("  max client-update spread over rounds: %.3f"
              % diag["max_client_update_spread"])
        print("  global model RMSE per round on %s: %s" % (
            probe.name,
            ", ".join("%.3f" % v for v in
                      diag["global_model_rmse_per_round_on_probe"])))

    result: Dict[str, object] = {
        "seed": seed,
        "config": {"hours": hours, "rounds": rounds, "local_steps": local_steps,
                   "fit_steps": fit_steps, "eval_start": exp.eval_start,
                   "eval_end": exp.eval_end,
                   "local_budgets": list(LOCAL_BUDGETS)},
        "heldout": heldout_rows,
        "per_building": [{k: v for k, v in r.items() if not k.startswith("_")}
                         for r in pb],
        "federated_diagnostics": exp.fed_diagnostics(),
    }
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--local-steps", type=int, default=60)
    parser.add_argument("--fit-steps", type=int, default=400)
    parser.add_argument("--out-dir", default=DEFAULT_DATA_DIR)
    args = parser.parse_args(argv)
    res = run_seed(args.seed, hours=args.hours, rounds=args.rounds,
                   local_steps=args.local_steps, fit_steps=args.fit_steps)
    os.makedirs(args.out_dir, exist_ok=True)
    path = os.path.join(args.out_dir, "results_seed%d.json" % args.seed)
    with open(path, "w") as fh:
        json.dump(res, fh, indent=2, sort_keys=True)
    print("")
    print("results written: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
