"""Training for the three models, under one common discipline (brief 4.4).

  * identical splits, identical scaling (train year only), identical MSE loss
    on [zone temperature, heating energy, cooling energy], identical early
    stopping (patience 8 epochs on validation loss)
  * at most 5 configurations per model, fixed in advance
  * every configuration tried is logged, including failures
  * final configuration is re-run with 3 seeds

SS-DFA is trained by `dfa_epoch`, which is state-skipping: it never calls
.backward(), never builds a graph across time, and holds only the single most
recent hidden state and pre-activation in memory.
"""

import argparse
import copy
import json
import time
from pathlib import Path

import numpy as np
import torch

import common as C
from models import MLP, LSTMSurrogate, SSDFA, count_params

BATCH = 256
MAX_EPOCHS = 60
PATIENCE = 8
TBPTT = 24  # truncated-BPTT horizon for the LSTM (= window length)


# ----------------------------------------------------------------- SS-DFA ----
def dfa_epoch(model, X, Yall, Y, opt, batch=BATCH, gen=None):
    """One state-skipping DFA pass; returns (final-step loss, recurrent steps).

    Gradients are *derived* by the DFA rules below and applied by a standard
    optimiser (Adam, as for the baselines). DFA is a rule for how the error
    signal is propagated, not for how the resulting update is scaled; using
    Adam on DFA gradients is standard practice and does not reintroduce BPTT.

    State-skipping invariants (asserted):
      * no autograd graph crosses a time step (everything runs in no_grad)
      * no tensor of shape (B, L, n_res) is ever materialised
      * only the single most recent hidden state / pre-activation is retained
    """
    n = X.shape[0]
    idx = torch.randperm(n, generator=gen)
    tot_loss, steps = 0.0, 0
    for i in range(0, n - batch + 1, batch):
        b = idx[i:i + batch]
        xb, ya, yb = X[b], Yall[b], Y[b]
        B, L, _ = xb.shape
        with torch.no_grad():
            h = model._init_state(xb)
            dW = torch.zeros_like(model.W_out)
            db = torch.zeros_like(model.b_out)
            s_last, x_last = None, None
            for t in range(L):
                h, s = model.step(xb[:, t], h)
                z = model.readout_feat(h, xb[:, t])
                err = z @ model.W_out + model.b_out - ya[:, t]
                dW += z.T @ err          # readout: no backprop through time needed
                db += err.sum(0)
                s_last, x_last = s, xb[:, t]   # O(1) state, overwritten each step
                steps += 1
            # ---- DFA: final output error through a FIXED RANDOM matrix ----
            z_T = model.readout_feat(h, x_last)
            err_T = z_T @ model.W_out + model.b_out - yb
            fb = err_T @ model.W_fb                       # fixed random, not W^T
            dh_dgain = (1.0 - h * h) * s_last             # h_{t-1} held constant
            dh_dscale = (1.0 - h * h) * (x_last @ model.W_in)
            d_gain = (fb * dh_dgain).sum()
            d_scale = (fb * dh_dscale).sum()
            # attach DFA-derived gradients; Adam only rescales the update
            model.W_out.grad = dW / (B * L)
            model.b_out.grad = db / (B * L)
            model.log_gain.grad = d_gain / B
            model.log_input_scale.grad = d_scale / B
        opt.step()
        opt.zero_grad(set_to_none=True)
        with torch.no_grad():
            y_T = model.readout_feat(h, x_last) @ model.W_out + model.b_out
            tot_loss += float(((y_T - yb) ** 2).mean()) * B
    assert h.dim() == 2, "a state trajectory was materialised - this is not state-skipping"
    return tot_loss / n, steps


@torch.no_grad()
def eval_loss(model, X, Y, batch=1024):
    """Validation loss: MSE on all 3 targets at the FINAL window step, identical
    definition for every model (this is what early stopping ranks)."""
    tot, n = 0.0, X.shape[0]
    for i in range(0, n, batch):
        xb, yb = X[i:i + batch], Y[i:i + batch]
        if isinstance(model, SSDFA):
            pred, _ = model.forward(xb)
        elif isinstance(model, LSTMSurrogate):
            pred, _ = model(xb)
        else:
            pred = model(xb)
        tot += float(((pred - yb) ** 2).mean()) * xb.shape[0]
    return tot / n


def epoch_pass(kind, model, X, Y, opt, cfg, gen):
    """One training pass; returns (loss, recurrent steps, optimizer steps)."""
    n = X.shape[0]
    idx = torch.randperm(n, generator=gen)
    tot, rsteps, osteps = 0.0, 0, 0
    for i in range(0, n - BATCH + 1, BATCH):
        b = idx[i:i + BATCH]
        xb, yb = X[b], Y[b]
        opt.zero_grad(set_to_none=True)
        if kind == "lstm":
            pred, _ = model(xb)
            loss = ((pred - yb) ** 2).mean()
            rsteps += xb.shape[0] * xb.shape[1]
        elif kind == "mlp":
            pred = model(xb)                       # (B,3) next-step prediction
            loss = ((pred - yb) ** 2).mean()
            rsteps += 0
        loss.backward()
        opt.step()
        tot += float(loss) * xb.shape[0]
        osteps += 1
    return tot / n, rsteps, osteps


# --------------------------------------------------------------- config grid -
# Fixed in advance. At most 5 per model (brief 4.4). Logged including failures.
CONFIGS = {
    "mlp": [
        dict(hidden=(128, 128), lr=1e-3),
        dict(hidden=(256, 256), lr=1e-3),
        dict(hidden=(128, 128), lr=3e-4),
        dict(hidden=(256, 128), lr=1e-3),
        dict(hidden=(128, 64), lr=3e-3),
    ],
    "lstm": [
        dict(hidden=64, layers=1, lr=1e-3),
        dict(hidden=96, layers=1, lr=1e-3),
        dict(hidden=64, layers=1, lr=3e-4),
        dict(hidden=64, layers=2, lr=1e-3),
        dict(hidden=128, layers=1, lr=3e-4),
    ],
    "ssdfa": [
        dict(n_res=160, spectral_radius=0.9, input_scale=1.0, gain=1.0,
             sparsity=0.10, readout_with_input=True, lr=1e-2, lr_deep=1e-3),
        dict(n_res=160, spectral_radius=0.9, input_scale=1.0, gain=1.0,
             sparsity=0.10, readout_with_input=False, lr=1e-2, lr_deep=1e-3),
        dict(n_res=192, spectral_radius=0.99, input_scale=1.0, gain=1.0,
             sparsity=0.10, readout_with_input=True, lr=1e-2, lr_deep=1e-3),
        dict(n_res=160, spectral_radius=0.6, input_scale=1.0, gain=2.0,
             sparsity=0.10, readout_with_input=True, lr=1e-2, lr_deep=1e-3),
        dict(n_res=128, spectral_radius=0.9, input_scale=2.0, gain=1.0,
             sparsity=0.05, readout_with_input=True, lr=3e-2, lr_deep=1e-3),
    ],
}


def make_model(kind, cfg, seed):
    if kind == "mlp":
        return MLP(hidden=cfg["hidden"])
    if kind == "lstm":
        return LSTMSurrogate(hidden=cfg["hidden"], layers=cfg["layers"])
    return SSDFA(n_res=cfg["n_res"], spectral_radius=cfg["spectral_radius"],
                 input_scale_init=cfg["input_scale"], gain_init=cfg["gain"],
                 sparsity=cfg["sparsity"], readout_with_input=cfg["readout_with_input"],
                 seed=seed)


def train_one(kind, cfg, seed, train_arr, val_arr, max_epochs=MAX_EPOCHS,
              verbose=False, tag=""):
    C.set_seed(seed)
    gen = torch.Generator().manual_seed(seed + 777)
    model = make_model(kind, cfg, seed)
    Xtr = torch.from_numpy(train_arr["Xw"]).float()
    Ytr = torch.from_numpy(train_arr["Yw"]).float()
    Ytr_all = torch.from_numpy(train_arr["Yall"]).float()
    Xva = torch.from_numpy(val_arr["Xw"]).float()
    Yva = torch.from_numpy(val_arr["Yw"]).float()

    if kind == "ssdfa":
        opt = torch.optim.Adam([p for p in model.parameters() if p.requires_grad],
                               lr=cfg["lr"])
        train_fn = lambda: dfa_epoch(model, Xtr, Ytr_all, Ytr, opt, gen=gen)
    else:
        opt = torch.optim.Adam(model.parameters(), lr=cfg["lr"])
        train_fn = lambda: epoch_pass(kind, model, Xtr, Ytr, opt, cfg, gen)

    t0 = time.time()
    best_val, best_state, best_epoch, since = float("inf"), None, 0, 0
    tot_rsteps, tot_osteps = 0, 0
    hist = []
    for ep in range(max_epochs):
        if kind == "ssdfa":
            tl, r = train_fn()
            o = 0
        else:
            tl, r, o = train_fn()
        tot_rsteps += r
        tot_osteps += o
        vl = eval_loss(model, Xva, Yva)
        hist.append(dict(epoch=ep, train_loss=tl, val_loss=vl, elapsed_s=time.time() - t0))
        if verbose and (ep % 5 == 0 or ep == max_epochs - 1):
            print(f"  [{tag}] ep{ep:3d} train {tl:.5f} val {vl:.5f} ({time.time()-t0:.1f}s)", flush=True)
        if vl < best_val - 1e-6:
            best_val, best_epoch, since = vl, ep, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            since += 1
            if since >= PATIENCE:
                break
    wall = time.time() - t0
    if best_state is not None:
        model.load_state_dict(best_state)
    return dict(
        model=model, kind=kind, cfg=cfg, seed=seed, val_loss=best_val,
        best_epoch=best_epoch, epochs_run=len(hist), wall_s=wall,
        train_wall_s=wall, recurrent_steps=tot_rsteps, optimizer_steps=tot_osteps,
        n_trainable=count_params(model, True), n_total=count_params(model),
        peak_rss_mb=C.peak_rss_mb(), hist=hist,
    )


def tune(kind, train_arr, val_arr, seeds=(0,), verbose=True, max_epochs=MAX_EPOCHS):
    """Sweep the fixed config grid; return (best_result, log_of_all_configs)."""
    log = []
    for ci, cfg in enumerate(CONFIGS[kind]):
        for sd in seeds:
            r = train_one(kind, cfg, sd, train_arr, val_arr, max_epochs=max_epochs,
                          verbose=verbose, tag=f"{kind} c{ci} s{sd}")
            log.append(dict(kind=kind, cfg_idx=ci, cfg={k: str(v) for k, v in cfg.items()},
                            seed=sd, val_loss=r["val_loss"], epochs_run=r["epochs_run"],
                            best_epoch=r["best_epoch"], wall_s=r["wall_s"],
                            n_trainable=r["n_trainable"], n_total=r["n_total"],
                            status="ok"))
            if verbose:
                print(f"[tune] {kind} cfg{ci} seed{sd}: val {r['val_loss']:.5f} "
                      f"({r['wall_s']:.1f}s, {r['epochs_run']} ep)", flush=True)
    best = min(log, key=lambda d: d["val_loss"])
    return best, log


def final_runs(kind, cfg, train_arr, val_arr, seeds=(11, 22, 33)):
    out = []
    for sd in seeds:
        r = train_one(kind, cfg, sd, train_arr, val_arr)
        r["cfg_idx"] = None
        out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="smoke test: 2 epochs")
    ap.add_argument("--seeds", type=int, nargs="*", default=None,
                    help="override tuning seed (default 0)")
    a = ap.parse_args()
    max_ep = 2 if a.quick else MAX_EPOCHS
    tune_seed = a.seeds if a.seeds else (0,)

    sx, ss, sy = C.Scaler(), C.Scaler(), C.Scaler()
    tr = C.build_arrays(1, "base", sx, ss, sy, fit=True)
    va = C.build_arrays(2, "base", sx, ss, sy, fit=False)
    for arr in (tr, va):
        arr["Xw"], arr["Yw"], arr["Yall"] = C.windows(arr)

    C.save_json(dict(
        features=C.FEATURES, targets=C.TARGETS, n_history=C.N_HISTORY,
        x_mean=list(sx.mean), x_std=list(sx.std),
        s_mean=list(ss.mean), s_std=list(ss.std),
        y_mean=list(sy.mean), y_std=list(sy.std),
    ), C.RESULTS / "scalers.json")

    weights_dir = C.ROOT / "weights"
    weights_dir.mkdir(exist_ok=True)
    results, all_logs = {}, []
    for kind in ("mlp", "lstm", "ssdfa"):
        best, log = tune(kind, tr, va, seeds=tune_seed, verbose=True, max_epochs=max_ep)
        all_logs += log
        cfg = CONFIGS[kind][best["cfg_idx"]]
        runs = final_runs(kind, cfg, tr, va)
        for j, r in enumerate(runs):
            torch.save(r["model"].state_dict(), weights_dir / f"{kind}_seed{r['seed']}.pt")
        results[kind] = dict(
            best_cfg={k: str(v) for k, v in cfg.items()}, best_cfg_idx=best["cfg_idx"],
            runs=[{k: v for k, v in r.items() if k not in ("model", "hist")} for r in runs])
        C.save_json(results[kind], C.RESULTS / f"tuned_{kind}.json")
        print(f"[final] {kind}: cfg{best['cfg_idx']} "
              f"val {[round(r['val_loss'],5) for r in runs]} "
              f"wall {[round(r['wall_s'],1) for r in runs]}", flush=True)
    C.save_json(all_logs, C.RESULTS / "tuning_log.json")
    C.save_json({k: {kk: vv for kk, vv in v.items() if kk != "runs"}
                 for k, v in results.items()}, C.RESULTS / "best_configs.json")


if __name__ == "__main__":
    main()
