"""Physics evaluation (brief Section 5) and the headline results table.

All five checks run for all three models:
  1. one-step and 24-hour open-loop accuracy on the test year (MAE, RMSE,
     NMBE, CV(RMSE) in the ASHRAE Guideline 14 form)
  2. full-year (8760 h) free-running rollout: boundedness, final/max error,
     drift, blow-up step
  3. out-of-distribution, no retraining: envelope variants + extreme weeks
  4. monotonicity / physics-sanity paired counterfactuals
  5. energy balance over the rollout year
Plus one figure per model: predicted vs teacher temperature for the hottest
and coldest test-year week, in rollout mode.

UNIT CONVENTION: `predict_next` returns SCALED model outputs. `rollout()` and
`horizon_k()` convert to RAW degC / kWh immediately, so every rollout metric is
plain C.metrics() on raw values. Only `one_step()` returns scaled values, and
it inverse-transforms them explicitly before computing metrics.
"""

import argparse
import json
from collections import deque

import numpy as np
import torch

import common as C
import train as T
from models import LSTMSurrogate, SSDFA, count_params

FI = {f: i for i, f in enumerate(C.FEATURES)}
IDX_T = C.IDX_T
SC = {}


def load_trained(kind, cfg_dict, seed):
    cfg = {}
    for k, v in cfg_dict.items():
        try:
            cfg[k] = eval(v)
        except (ValueError, SyntaxError):
            cfg[k] = v
    model = T.make_model(kind, cfg, seed)
    sd = torch.load(C.ROOT / "weights" / f"{kind}_seed{seed}.pt", map_location="cpu")
    model.load_state_dict(sd)
    model.eval()
    return model


# ---------------------------------------------------------------- inference --
@torch.no_grad()
def predict_next(model, window):
    """window (L,6) oldest->newest. Returns the SCALED prediction vector (3,)."""
    xb = torch.from_numpy(window.astype(np.float32)).unsqueeze(0)
    if isinstance(model, (SSDFA, LSTMSurrogate)):
        y, _ = model(xb, None)
    else:
        y = model(xb)
    return y[0].detach().numpy()


def to_raw_temp(scaled):
    return scaled * SC["s_std"][0] + SC["s_mean"][0]


def to_raw_temp_inv(raw):
    return (raw - SC["s_mean"][0]) / SC["s_std"][0]


def to_raw_energy(scaled_vec2):
    return np.asarray(scaled_vec2) * SC["y_std"][1:3] + SC["y_mean"][1:3]


@torch.no_grad()
def rollout(model, arr, L=C.N_HISTORY, per_step=None):
    """Free-running rollout over `arr` (a full year or a slice).

    Exogenous inputs come from the data; only the zone temperature is fed back
    from the model's own prediction. The initial condition is the true state at
    the first hour; no later teacher values are revealed to the model.
    `per_step(t)`, if given, is called immediately before each hourly
    prediction (used by the noise gate to advance hardware drift).
    Returns (T_hat raw degC [n], E_hat raw kWh [n,2], blowup_step or None).
    """
    X, S, n = arr["X"], arr["S"], arr["n"]
    Feat = np.concatenate([X, S.reshape(-1, 1)], axis=1)   # private working copy
    buf = deque(maxlen=L)
    for i in range(L - 1):
        buf.append(Feat[i])                                # warm-up: true history
    t_hat = np.empty(n)
    e_hat = np.empty((n, 2))
    blowup = None
    for t in range(n):
        buf.append(Feat[t])
        if per_step is not None:
            per_step(t)
        p = predict_next(model, np.stack(buf))
        t_scaled = float(p[0])
        t_raw = to_raw_temp(t_scaled)
        if not np.isfinite(t_raw) or abs(t_raw) > 1e3:
            blowup = t
            t_raw = float(np.clip(t_raw, -1e3, 1e3))
            t_scaled = float(to_raw_temp_inv(t_raw))
        t_hat[t] = t_raw
        e_hat[t] = to_raw_energy(p[1:3])
        if t + 1 < n:                                      # feed our own state back
            Feat[t + 1, IDX_T] = t_scaled
    return t_hat, e_hat, blowup


@torch.no_grad()
def one_step(model, arr, batch=2048):
    """Teacher-forced one-step prediction over a whole year (scaled units)."""
    Xw, Yw = arr["Xw"], arr["Yw"]
    preds = []
    for i in range(0, len(Xw), batch):
        xb = torch.from_numpy(Xw[i:i + batch]).float()
        if isinstance(model, (SSDFA, LSTMSurrogate)):
            y, _ = model(xb, None)
        else:
            y = model(xb)
        preds.append(y.detach().numpy())
    return np.concatenate(preds), Yw


@torch.no_grad()
@torch.no_grad()
def horizon_k(model, arr, k, L=C.N_HISTORY, n_origins=250):
    """Open-loop k-hour forecasts from many origins on the test year.

    Exogenous inputs over the horizon are the true weather/gain/HVAC values
    (known to a forecaster); the zone temperature is fed back from the model's
    own predictions. Returns raw-unit (T_pred, E_pred, T_true, E_true).
    """
    X, S, Y_raw, n = arr["X"], arr["S"], arr["Y_raw"], arr["n"]
    Feat = np.concatenate([X, S.reshape(-1, 1)], axis=1)
    stride = max(1, (n - L - k) // n_origins)
    pt, pe, tt, te_ = [], [], [], []
    for o in range(L - 1, n - k, stride):
        window = deque(Feat[o - L + 1: o + 1], maxlen=L)   # ends at origin o
        for j in range(k):                                 # predicts step o+1+j
            p = predict_next(model, np.stack(window))
            ts = float(p[0])
            pt.append(to_raw_temp(ts))
            pe.append(to_raw_energy(p[1:3]))
            tt.append(float(Y_raw[o + 1 + j, 0]))
            te_.append(Y_raw[o + 1 + j, 1:3])
            window.append(np.append(Feat[o + 1 + j][:IDX_T], ts))  # own state back
    return np.array(pt), np.array(pe), np.array(tt), np.array(te_)


# ------------------------------------------------------------------- checks --
def do_rollout_block(model, arr, per_step=None):
    t_hat, e_hat, blow = rollout(model, arr, per_step=per_step)
    tgt = arr["S_raw"]
    n = len(tgt)
    months = [slice(int(i * n / 12), int((i + 1) * n / 12)) for i in range(12)]
    return dict(
        temp=C.metrics(tgt, t_hat),
        final_abs_err=float(abs(t_hat[-1] - tgt[-1])),
        max_abs_err=float(np.max(np.abs(t_hat - tgt))),
        blowup_step=blow, bounded=bool(blow is None),
        monthly_max_abs_err=[float(np.max(np.abs(t_hat[s] - tgt[s]))) for s in months],
        drift_per_month=float(np.max(np.abs(t_hat[months[-1]] - tgt[months[-1]]))
                              - np.max(np.abs(t_hat[months[0]] - tgt[months[0]]))),
    ), e_hat


def energy_balance(true_e, pred_e):
    tc, pc = true_e.sum(axis=0), pred_e.sum(axis=0)
    return dict(
        heat_true_kwh=float(tc[0]), heat_pred_kwh=float(pc[0]),
        cool_true_kwh=float(tc[1]), cool_pred_kwh=float(pc[1]),
        total_pct=100.0 * (pc.sum() - tc.sum()) / tc.sum(),
        heat_pct=100.0 * (pc[0] - tc[0]) / tc[0] if tc[0] else float("nan"),
        cool_pct=100.0 * (pc[1] - tc[1]) / tc[1] if tc[1] else float("nan"))


def monotonicity(model, te, ood):
    """Paired counterfactuals through each model's own input interface.

    (a) insulation -> heating energy must not increase. Envelope properties are
        not inputs to the surrogate (they live in the learned dynamics), so this
        counterfactual is realised through the held-out envelope variants: the
        model is run on the teacher's insul_half / insul_double input sequences
        and its predicted heating energy is compared with the base year.
    (b) internal gains +20% -> heating must not increase, cooling must not
        decrease.
    (c) summer outdoor temperature +2 K -> cooling must not decrease.
    """
    out = {}
    _, e_base, _ = rollout(model, te)
    eb = e_base.sum(axis=0)

    a = {}
    for v in ("insul_half", "insul_double"):
        _, ev, bl = rollout(model, ood[v])
        a[v] = float(ev.sum(axis=0)[0])
        a[v + "_bounded"] = bool(bl is None)
    a_res = dict(
        base_heat_kwh=float(eb[0]),
        insul_half_heat_kwh=a["insul_half"], insul_double_heat_kwh=a["insul_double"],
        insul_half_no_increase=bool(a["insul_half"] <= eb[0] * 1.01),
        insul_double_no_increase=bool(a["insul_double"] <= eb[0] * 1.01))

    def with_X(Xmod):
        alt = dict(X=Xmod, S=te["S"].copy(), Y=te["Y"], S_raw=te["S_raw"], n=te["n"])
        _, e, bl = rollout(model, alt)
        return e.sum(axis=0), bool(bl is None)

    X2 = te["X"].copy()
    q = te["X"][:, FI["q_int"]] * SC["x_std"][FI["q_int"]] + SC["x_mean"][FI["q_int"]]
    X2[:, FI["q_int"]] = (q * 1.20 - SC["x_mean"][FI["q_int"]]) / SC["x_std"][FI["q_int"]]
    eg, bg = with_X(X2)
    b_res = dict(
        heat_base_kwh=float(eb[0]), heat_high_kwh=float(eg[0]),
        heat_no_increase=bool(eg[0] <= eb[0] * 1.01),
        cool_base_kwh=float(eb[1]), cool_high_kwh=float(eg[1]),
        cool_no_decrease=bool(eg[1] >= eb[1] * 0.99), bounded=bg)

    X3 = te["X"].copy()
    to = te["X"][:, FI["t_out"]] * SC["x_std"][FI["t_out"]] + SC["x_mean"][FI["t_out"]]
    summer = np.where(to > 18.0)[0]
    X3[summer, FI["t_out"]] = (to[summer] + 2.0 - SC["x_mean"][FI["t_out"]]) / SC["x_std"][FI["t_out"]]
    ec, bc = with_X(X3)
    c_res = dict(
        cool_base_kwh=float(eb[1]), cool_hot_kwh=float(ec[1]),
        cool_no_decrease=bool(ec[1] >= eb[1] * 0.99), bounded=bc)

    checks = dict(insulation=a_res, gains=b_res, summer_temp=c_res,
                  n_total=5,
                  n_pass=int(a_res["insul_half_no_increase"]) + int(a_res["insul_double_no_increase"])
                          + int(b_res["heat_no_increase"]) + int(b_res["cool_no_decrease"])
                          + int(c_res["cool_no_decrease"]))
    return checks


def slice_view(te, s0, length=168):
    sl = slice(s0, s0 + length)
    return dict(X=te["X"][sl], S=te["S"][sl], Y=te["Y"][sl],
                S_raw=te["S_raw"][sl], n=len(te["S"][sl]))


def plot_weeks(model, te, hot0, cold0, kind):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    C.FIGURES.mkdir(exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5))
    for ax, (tag, s0) in zip(axes, (("hottest week", hot0), ("coldest week", cold0))):
        sub = slice_view(te, s0)
        t_hat, _, bl = rollout(model, sub)
        tgt = sub["S_raw"]
        ax.plot(tgt, "k-", lw=1.7, label="teacher")
        ax.plot(t_hat, "r-", lw=1.2, label=f"{kind} (free rollout)")
        ax.axhspan(tgt.min(), tgt.max(), alpha=0.04, color="k")
        ax.set_ylabel("zone temp (C)")
        ax.set_title(f"{tag} of test year, hours {s0}-{s0 + 167}"
                     + (f"  [DIVERGED at h={bl}]" if bl is not None else ""))
        ax.legend(loc="best", fontsize=8)
        ax.grid(alpha=0.3)
    axes[-1].set_xlabel("hour of week")
    fig.suptitle(f"{kind}: free-running rollout vs teacher")
    fig.tight_layout()
    p = C.FIGURES / f"weeks_{kind}.png"
    fig.savefig(p, dpi=130)
    plt.close(fig)
    return str(p.relative_to(C.ROOT))


# --------------------------------------------------------------------- main --
def main():
    # Batch-1 rollout steps are tiny; >1 OpenMP thread is pure contention
    # (measured 74 ms vs 0.73 ms per LSTM step on this 4-core box). Threading
    # affects scheduling only, not the math.
    torch.set_num_threads(1)
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[11, 22, 33])
    a = ap.parse_args()

    sx, ss, sy = C.Scaler(), C.Scaler(), C.Scaler()
    tr = C.build_arrays(1, "base", sx, ss, sy, fit=True)
    te = C.build_arrays(3, "base", sx, ss, sy, fit=False)
    for arr in (tr, te):
        arr["Xw"], arr["Yw"], arr["Yall"] = C.windows(arr)
    SC["s_mean"], SC["s_std"] = ss.mean, ss.std
    SC["y_mean"], SC["y_std"] = sy.mean, sy.std
    SC["x_mean"], SC["x_std"] = sx.mean, sx.std

    bcfg = json.loads((C.RESULTS / "best_configs.json").read_text())
    tune_logs = json.loads((C.RESULTS / "tuning_log.json").read_text())

    variants = ["insul_half", "insul_double", "mass_double"]
    ood = {v: C.build_arrays(3, v, sx, ss, sy, fit=False) for v in variants}
    teacher_raw = C.load_year(3, "base")
    hot0, cold0 = C.hottest_coldest_weeks(teacher_raw["t_out"])

    results = {"hot_week_start": hot0, "cold_week_start": cold0}
    for kind in ("mlp", "lstm", "ssdfa"):
        results[kind] = {"seeds": {}}
        for sd in a.seeds:
            model = load_trained(kind, bcfg[kind]["best_cfg"], sd)
            res = dict(seed=sd,
                       n_trainable=count_params(model, True), n_total=count_params(model))

            # -- check 1 --
            p1, y1 = one_step(model, te)
            res["one_step_temp"] = C.metrics(ss.inverse(y1[:, [0]])[:, 0],
                                             ss.inverse(p1[:, [0]])[:, 0])
            res["one_step_energy"] = {
                k: C.metrics(sy.inverse(y1[:, [j + 1]])[:, 0], sy.inverse(p1[:, [j + 1]])[:, 0])
                for j, k in enumerate(["e_heat", "e_cool"])}
            pt, pe, tt, tet = horizon_k(model, te, 24)
            res["h24_temp"] = C.metrics(tt, pt)
            res["h24_energy"] = {k: C.metrics(tet[:, j], pe[:, j])
                                 for j, k in enumerate(["e_heat", "e_cool"])}

            # -- check 2 + 5 --
            res["rollout"], e_hat = do_rollout_block(model, te)
            res["energy_balance"] = energy_balance(te["Y_raw"][:, 1:3], e_hat)

            # -- check 3 --
            res["ood"] = {}
            for v, oa in ood.items():
                rb, ev = do_rollout_block(model, oa)
                res["ood"][v] = dict(rollout_temp=rb["temp"], bounded=rb["bounded"],
                                     max_abs_err=rb["max_abs_err"],
                                     energy=energy_balance(oa["Y_raw"][:, 1:3], ev))
            for tag, s0 in (("hottest_week", hot0), ("coldest_week", cold0)):
                rb, ev = do_rollout_block(model, slice_view(te, s0))
                res["ood"][tag] = dict(rollout_temp=rb["temp"], bounded=rb["bounded"],
                                       max_abs_err=rb["max_abs_err"])

            # -- check 4 --
            res["monotonicity"] = monotonicity(model, te, ood)
            results[kind]["seeds"][str(sd)] = res
            print(f"[{kind} s{sd}] 1step {res['one_step_temp']['rmse']:.3f}C "
                  f"rollout {res['rollout']['temp']['rmse']:.3f}C "
                  f"max {res['rollout']['max_abs_err']:.1f}C "
                  f"bounded={res['rollout']['bounded']} "
                  f"bal {res['energy_balance']['total_pct']:+.1f}% "
                  f"mono {res['monotonicity']['n_pass']}/5", flush=True)

        model = load_trained(kind, bcfg[kind]["best_cfg"], a.seeds[0])
        results[kind]["figure"] = plot_weeks(model, te, hot0, cold0, kind)

    cost = {}
    for kind in ("mlp", "lstm", "ssdfa"):
        d = json.loads((C.RESULTS / f"tuned_{kind}.json").read_text())
        rs = d["runs"]
        cost[kind] = dict(
            wall_s_mean=float(np.mean([r["wall_s"] for r in rs])),
            wall_s_std=float(np.std([r["wall_s"] for r in rs])),
            epochs_mean=float(np.mean([r["epochs_run"] for r in rs])),
            optimizer_steps_mean=float(np.mean([r["optimizer_steps"] for r in rs])),
            recurrent_steps_mean=float(np.mean([r["recurrent_steps"] for r in rs])),
            n_trainable=int(rs[0]["n_trainable"]), n_total=int(rs[0]["n_total"]),
            peak_rss_mb=float(np.mean([r["peak_rss_mb"] for r in rs])),
            cfg=d["best_cfg"], cfg_idx=d["best_cfg_idx"])
    results["training_cost"] = cost
    results["tuning_budget"] = dict(
        configs_per_model=len(T.CONFIGS["mlp"]),
        per_config=[{k: v for k, v in r.items() if k != "cfg"} for r in tune_logs])

    C.save_json(results, C.RESULTS / "physics_eval.json")
    print("wrote", C.RESULTS / "physics_eval.json")


if __name__ == "__main__":
    main()
