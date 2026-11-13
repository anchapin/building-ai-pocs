"""Phase 0 measurement runner for the PySR symbolic-surrogate POC (issue #47, slice 1).

Runs the two control arms on identical training data and writes the raw measurements
table (results.json + MEASUREMENTS.md):

  arm "ls-refit" : least-squares biquadratic refit (the in-codebase comparator)
  arm "pysr"     : PySR symbolic regression (pinned pysr==2.7.2, Julia backend)

Every row records: configuration, seed, noise condition, training box, wall-clock
seconds, in-range RMSE and out-of-range RMSE (plus the selected equation for PySR).

Usage (from the repo root):

    python3 pysr-symbolic-surrogate/src/run_measurements.py --seeds 0 1 2

"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
import traceback
from typing import Dict, List

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from curves import (  # noqa: E402
    EXTRAPOLATION_BOX,
    IN_RANGE_BOX,
    OPERATING_RANGE,
    REFERENCE_COEFFS,
    TRAIN_BOX,
    generate_dataset,
    ls_biquadratic_fit,
    rmse,
)

HERE = os.path.dirname(os.path.abspath(__file__))
POC_DIR = os.path.dirname(HERE)

FULL_BOX = {"plr": OPERATING_RANGE["plr"], "temp_c": OPERATING_RANGE["temp_c"]}


def box_str(box: Dict[str, tuple]) -> str:
    return (
        f"PLR [{box['plr'][0]:g},{box['plr'][1]:g}] x T "
        f"[{box['temp_c'][0]:g},{box['temp_c'][1]:g}] degC"
    )


def make_splits(seed: int, n_train: int, n_eval: int, noise_pct: float, train_box):
    """Training set (on `train_box`) + in-range and out-of-range evaluation sets.

    Evaluation sets are drawn with a different seed offset so that the in-range
    evaluation samples are *not* the training samples.
    """
    train = generate_dataset(seed, n_train, train_box, noise_pct=noise_pct)
    in_range = generate_dataset(
        seed + 10_000, n_eval, IN_RANGE_BOX if train_box is TRAIN_BOX else train_box,
        noise_pct=0.0,
    )
    out_of_range = generate_dataset(seed + 20_000, n_eval, EXTRAPOLATION_BOX, noise_pct=0.0)
    return train, in_range, out_of_range


def run_ls_refit(seed: int, noise_pct: float, n_train: int, n_eval: int, train_box) -> Dict:
    t0 = time.perf_counter()
    train, in_range, out_of_range = make_splits(seed, n_train, n_eval, noise_pct, train_box)
    coeffs, _ = ls_biquadratic_fit(train.x, train.y)
    rmse_in = rmse(coeffs.evaluate(in_range.x[:, 0], in_range.x[:, 1]), in_range.y)
    rmse_out = rmse(coeffs.evaluate(out_of_range.x[:, 0], out_of_range.x[:, 1]), out_of_range.y)
    return {
        "arm": "ls-refit",
        "configuration": "least-squares biquadratic refit (numpy lstsq, 6 terms)",
        "seed": seed,
        "noise_pct": noise_pct,
        "training_box": box_str(train_box),
        "n_train": n_train,
        "wall_clock_s": round(time.perf_counter() - t0, 3),
        "rmse_in_range": rmse_in,
        "rmse_out_of_range": rmse_out,
        "equation": str(coeffs),
        "notes": "",
    }


def run_pysr(
    seed: int,
    noise_pct: float,
    n_train: int,
    n_eval: int,
    train_box,
    maxsize: int,
    niterations: int,
    populations: int,
    binary_operators,
    unary_operators,
) -> Dict:
    import pysr  # imported lazily so the LS arm still runs if the Julia backend fails

    t0 = time.perf_counter()
    train, in_range, out_of_range = make_splits(seed, n_train, n_eval, noise_pct, train_box)
    model = pysr.PySRRegressor(
        binary_operators=list(binary_operators),
        unary_operators=list(unary_operators),
        niterations=niterations,
        populations=populations,
        maxsize=maxsize,
        elementwise_loss="loss(pred, target) = (pred - target)^2",
        progress=False,
        verbosity=0,
        random_state=seed,
        deterministic=True,
        parallelism="serial",
        timeout_seconds=600,
    )
    model.fit(train.x, train.y)
    pred_in = np.asarray(model.predict(in_range.x), dtype=float)
    pred_out = np.asarray(model.predict(out_of_range.x), dtype=float)
    sympy_eqs = model.sympy()
    equation = str(sympy_eqs[0]) if len(sympy_eqs) else str(model.equations_.iloc[0]["equation"])
    return {
        "arm": "pysr",
        "configuration": (
            f"PySR(bin={list(binary_operators)}, un={list(unary_operators)}, "
            f"maxsize={maxsize}, niterations={niterations}, populations={populations})"
        ),
        "seed": seed,
        "noise_pct": noise_pct,
        "training_box": box_str(train_box),
        "n_train": n_train,
        "wall_clock_s": round(time.perf_counter() - t0, 3),
        "rmse_in_range": rmse(pred_in, in_range.y),
        "rmse_out_of_range": rmse(pred_out, out_of_range.y),
        "equation": equation,
        "notes": f"pysr={pysr.__version__}",
    }


def build_table(rows: List[Dict]) -> str:
    header = (
        "| # | arm | configuration | seed | noise [%] | training box | wall-clock [s] | "
        "in-range RMSE | out-of-range RMSE | selected equation |\n"
        "|---|---|---|---|---|---|---|---|---|---|\n"
    )
    body = ""
    for i, r in enumerate(rows, 1):
        eq = r.get("equation", "")
        eq = str(eq).replace("|", "\\|")
        if len(eq) > 110:
            eq = eq[:107] + "..."
        body += (
            f"| {i} | {r.get('arm','')} | {r.get('configuration','')} | {r.get('seed','')} | "
            f"{r.get('noise_pct','')} | {r.get('training_box','')} | {r.get('wall_clock_s','')} | "
            f"{r.get('rmse_in_range','')} | {r.get('rmse_out_of_range','')} | `{eq}` |\n"
        )
    return header + body


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2])
    ap.add_argument("--noise", type=float, nargs="+", default=[0.0, 1.0])
    ap.add_argument("--n-train", type=int, default=400)
    ap.add_argument("--n-eval", type=int, default=200)
    ap.add_argument("--maxsize", type=int, default=12)
    ap.add_argument("--niterations", type=int, default=15)
    ap.add_argument("--populations", type=int, default=20)
    ap.add_argument("--binary-operators", type=str, default="+,-,*")
    ap.add_argument("--unary-operators", type=str, default="")
    ap.add_argument("--arms", type=str, default="ls-refit,pysr")
    ap.add_argument("--control-arm", action="store_true", help="also run the control/rediscovery arm")
    ap.add_argument("--out", type=str, default=os.path.join(POC_DIR, "results.json"))
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    binary_ops = [o for o in args.binary_operators.split(",") if o]
    unary_ops = [o for o in args.unary_operators.split(",") if o]

    rows: List[Dict] = []
    for seed in args.seeds:
        for noise in args.noise:
            if "ls-refit" in arms:
                rows.append(run_ls_refit(seed, noise, args.n_train, args.n_eval, TRAIN_BOX))
            if "pysr" in arms:
                try:
                    rows.append(
                        run_pysr(
                            seed,
                            noise,
                            args.n_train,
                            args.n_eval,
                            TRAIN_BOX,
                            args.maxsize,
                            args.niterations,
                            args.populations,
                            binary_ops,
                            unary_ops,
                        )
                    )
                except Exception as exc:  # env failure must be surfaced, not hidden
                    rows.append(
                        {
                            "arm": "pysr",
                            "configuration": (
                                f"PySR(bin={binary_ops}, un={unary_ops}, maxsize={args.maxsize}, "
                                f"niterations={args.niterations}, populations={args.populations})"
                            ),
                            "seed": seed,
                            "noise_pct": noise,
                            "training_box": box_str(TRAIN_BOX),
                            "n_train": args.n_train,
                            "wall_clock_s": "",
                            "rmse_in_range": "",
                            "rmse_out_of_range": "",
                            "equation": "",
                            "notes": "ENV/RUN FAILURE: " + repr(exc),
                            "traceback": traceback.format_exc(),
                        }
                    )
            if args.control_arm and "pysr" in arms:
                try:
                    rows.append(
                        run_pysr(
                            seed,
                            noise,
                            args.n_train,
                            args.n_eval,
                            FULL_BOX,
                            args.maxsize,
                            args.niterations,
                            args.populations,
                            binary_ops,
                            unary_ops,
                        )
                    )
                except Exception as exc:
                    rows.append(
                        {
                            "arm": "pysr-control",
                            "configuration": (
                                f"PySR control/rediscovery on full in-range box (bin={binary_ops}, "
                                f"un={unary_ops}, maxsize={args.maxsize}, niterations={args.niterations})"
                            ),
                            "seed": seed,
                            "noise_pct": noise,
                            "training_box": box_str(FULL_BOX),
                            "n_train": args.n_train,
                            "wall_clock_s": "",
                            "rmse_in_range": "",
                            "rmse_out_of_range": "",
                            "equation": "",
                            "notes": "ENV/RUN FAILURE: " + repr(exc),
                            "traceback": traceback.format_exc(),
                        }
                    )

    meta = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "reference_coefficients": {k: str(v) for k, v in REFERENCE_COEFFS.items()},
        "train_box": box_str(TRAIN_BOX),
        "in_range_box": box_str(IN_RANGE_BOX),
        "extrapolation_box": box_str(EXTRAPOLATION_BOX),
        "n_train": args.n_train,
        "n_eval": args.n_eval,
        "rows": rows,
    }
    with open(args.out, "w") as fh:
        json.dump(meta, fh, indent=2)

    table = build_table(rows)
    with open(os.path.join(POC_DIR, "MEASUREMENTS.md"), "w") as fh:
        fh.write("# Raw measurements — PySR symbolic-surrogate POC (issue #47, slice 1)\n\n")
        fh.write(
            "Generated by `src/run_measurements.py` (one row per run). "
            "RMSEs are on the *noise-free* evaluation samples of the in-range box "
            f"({box_str(IN_RANGE_BOX)}) and of the extrapolation box "
            f"({box_str(EXTRAPOLATION_BOX)}).\n\n"
        )
        fh.write(table)
    print(table)
    print(f"wrote {args.out} and {os.path.join(POC_DIR, 'MEASUREMENTS.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
