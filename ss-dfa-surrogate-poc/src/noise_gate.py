"""Noise gate (brief Section 6). Runs LAST and SEPARATELY; its verdict is never
merged with the Section 5 software verdict.

Exact analogue-noise model used (stated here because it is a deliverable):

WEIGHT QUANTISATION
  Per-tensor symmetric uniform, round-to-nearest:
      scale = max|w| / (2^(b-1) - 1);  w_q = clamp(round(w/scale), -qmax, qmax) * scale
  Applied to every trained weight and bias. No retraining, no recalibration.

ACTIVATION QUANTISATION
  Same rule, applied to the live activation tensor at every arithmetic site
  (network input, each reservoir/LSTM/linear output, each nonlinearity output).

GAUSSIAN NOISE (7 bits only)
  At each arithmetic site, after quantisation:
      a <- a + eps,   eps ~ N(0, (sigma_frac * R)^2),   R = 2 * max|a|
  i.e. sigma is a fraction of that tensor's own signal range. sigma_frac in
  {0.01, 0.03}.

SLOW MULTIPLICATIVE DRIFT (7 bits only)
  One independent Ornstein-Uhlenbeck process per weight tensor, advanced once
  per rollout hour and applied to the weights immediately before that hour's
  prediction:
      e_{t+1} = e_t * exp(-1/tau) + sqrt(1 - exp(-2/tau)) * xi_t * sigma_eq
      tau = 730 h (~1 month),  sigma_eq = 0.01,  e_0 = 0
      W <- W * (1 + e_t)
  So weights drift by ~1% (1 sigma) over a month-long timescale across the
  rollout year. Every weight tensor participates, including the SS-DFA fixed
  W_in / W_res / W_fb buffers (on optical hardware the fixed maps drift too).
  Recomputed fresh per condition from a fixed seed. The one-step check under
  the drift condition is evaluated with the weights drifted to the
  end-of-year state.

NO RETRAINING AND NO RECALIBRATION AFTER QUANTISATION.

Checks 1 (one-step), 2 (full-year rollout) and 5 (energy balance) are re-run at
each precision. Everything is reported as a ratio to the FP32 result.
"""

import argparse
import json
from collections import deque

import numpy as np
import torch

import common as C
import train as T
import evaluate as E
from models import count_params, quantise_tensor

TAU_H = 730.0
SIGMA_EQ = 0.01


class Drift:
    """Per-tensor OU drift, advanced once per rollout hour.

    Covers every weight tensor in the model, including fixed buffers (for the
    SS-DFA single-map block the fixed W_in / W_res / W_fb would drift on real
    optical hardware just like the trained readout). Quantisation is always
    re-applied to the FP32 base, so repeated conditions never quantise on top
    of a quantised value.
    """

    def __init__(self, model, seed=5):
        self.model = model
        g = np.random.default_rng(seed)
        self.decay = float(np.exp(-1.0 / TAU_H))
        self.diff = float(np.sqrt(1.0 - np.exp(-2.0 / TAU_H))) * SIGMA_EQ
        self.tensors = [(n, p) for n, p in model.named_parameters()]
        self.tensors += [(n, b) for n, b in model.named_buffers()]
        self.eps = {n: 0.0 for n, _ in self.tensors}
        self._g = g
        # FP32 reference weights.
        self.base = {n: p.detach().clone() for n, p in self.tensors}

    def step(self, t):
        del t
        for n in self.eps:
            self.eps[n] = (self.eps[n] * self.decay
                           + self.diff * float(self._g.standard_normal()))

    def apply(self, bits, save=True):
        """Write (quantised, drifted) weights into the model; optionally returns
        the previous weights so they can be restored afterwards."""
        saved = None
        if save:
            saved = {n: p.detach().clone() for n, p in self.tensors}
        with torch.no_grad():
            for n, p in self.tensors:
                w = quantise_tensor(self.base[n], bits) * (1.0 + self.eps[n])
                p.copy_(w)
        return saved

    def restore(self, saved):
        with torch.no_grad():
            for n, p in self.tensors:
                p.copy_(saved[n])


class QConf:
    """Minimal quantisation config accepted by models.qa/qw."""

    def __init__(self, bits, noise_frac):
        self.bits = bits
        self.noise_frac = noise_frac


def set_quant(model, bits, noise_frac):
    model.q = None if bits >= 32 else QConf(bits, noise_frac)


@torch.no_grad()
def one_step_rmse(model, arr, batch=2048):
    Xw, Yw = arr["Xw"], arr["Yw"]
    errs_t, errs_e = [], []
    for i in range(0, len(Xw), batch):
        xb = torch.from_numpy(Xw[i:i + batch]).float()
        if isinstance(model, (E.SSDFA, E.LSTMSurrogate)):
            y, _ = model(xb, None)
        else:
            y = model(xb)
        y = y.numpy()
        errs_t.append(y[:, 0] - Yw[i:i + len(y), 0])
        errs_e.append(y[:, 1:3] - Yw[i:i + len(y), 1:3])
    et = np.concatenate(errs_t)
    ee = np.concatenate(errs_e)
    # scaled units; convert temperature to degC for reporting
    rmse_t = float(np.sqrt(np.mean(et ** 2)) * E.SC["s_std"][0])
    rmse_e = float(np.sqrt(np.mean(ee ** 2)) * np.mean(E.SC["y_std"][1:3]))
    return dict(temp_rmse_C=rmse_t, energy_rmse_mean_kWh=rmse_e)


def main():
    # See evaluate.main(): 1 thread is ~100x faster on batch-1 rollout steps.
    torch.set_num_threads(1)
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, nargs="*", default=[11])
    ap.add_argument("--precisions", type=int, nargs="*", default=[32, 8, 7, 6])
    ap.add_argument("--noise", type=float, nargs="*", default=[0.0, 0.01, 0.03])
    a = ap.parse_args()

    sx, ss, sy = C.Scaler(), C.Scaler(), C.Scaler()
    tr = C.build_arrays(1, "base", sx, ss, sy, fit=True)
    te = C.build_arrays(3, "base", sx, ss, sy, fit=False)
    for arr in (tr, te):
        arr["Xw"], arr["Yw"], arr["Yall"] = C.windows(arr)
    E.SC["s_mean"], E.SC["s_std"] = ss.mean, ss.std
    E.SC["y_mean"], E.SC["y_std"] = sy.mean, sy.std
    E.SC["x_mean"], E.SC["x_std"] = sx.mean, sx.std

    bcfg = json.loads((C.RESULTS / "best_configs.json").read_text())
    out = {}
    for kind in ("ssdfa", "lstm"):
        model = E.load_trained(kind, bcfg[kind]["best_cfg"], a.seeds[0])
        out[kind] = {}

        for bits in a.precisions:
            for frac in a.noise:
                if bits != 7 and frac != 0.0:
                    continue          # noise is a 7-bit-only condition
                tag = f"{bits}b" + (f"_noise{frac}" if frac else "")
                drift = Drift(model, seed=5)
                set_quant(model, bits, frac)
                saved_w = drift.apply(bits)

                os_ = one_step_rmse(model, te)
                rb, e_hat = E.do_rollout_block(model, te)
                bal = E.energy_balance(te["Y_raw"][:, 1:3], e_hat)
                out[kind][tag] = dict(
                    bits=bits, noise_frac=frac,
                    one_step=os_, rollout=rb, energy_balance=bal,
                    drift_eps_final={k: float(v) for k, v in drift.eps.items()})

                # restore FP32 weights for the next condition
                drift.restore(saved_w)
                set_quant(model, 32, 0.0)
                print(f"[{kind}] {tag}: rollout rmse {rb['temp']['rmse']:.3f} C "
                      f"max {rb['max_abs_err']:.1f} C bounded={rb['bounded']} "
                      f"bal {bal['total_pct']:+.1f}%  1step {os_['temp_rmse_C']:.3f} C",
                      flush=True)

        # ---- 7-bit + slow multiplicative drift over the rollout year ----
        # One OU step per rollout hour, applied to the weights just before each
        # hourly prediction. One-step is evaluated with the weights drifted to
        # the end-of-year state.
        drift = Drift(model, seed=5)
        set_quant(model, 7, 0.0)
        drift.apply(7, save=False)            # hour 0: quantised, no drift yet

        def advance(t):
            drift.step(t)
            drift.apply(7, save=False)

        rb, e_hat = E.do_rollout_block(model, te, per_step=advance)
        bal = E.energy_balance(te["Y_raw"][:, 1:3], e_hat)
        os_ = one_step_rmse(model, te)        # end-of-year drifted weights
        out[kind]["7b_drift"] = dict(
            bits=7, noise_frac=0.0, drift=True,
            one_step=os_, rollout=rb, energy_balance=bal,
            drift_eps_final={k: float(v) for k, v in drift.eps.items()})
        print(f"[{kind}] 7b_drift: rollout rmse {rb['temp']['rmse']:.3f} C "
              f"max {rb['max_abs_err']:.1f} C bounded={rb['bounded']} "
              f"bal {bal['total_pct']:+.1f}%  1step {os_['temp_rmse_C']:.3f} C",
              flush=True)
        # restore FP32 weights (drift.base holds the FP32 reference)
        with torch.no_grad():
            for n, p in drift.tensors:
                p.copy_(drift.base[n])
        set_quant(model, 32, 0.0)

        # ratios to FP32
        base = out[kind]["32b"]
        for tag, d in out[kind].items():
            d["ratio_to_fp32"] = dict(
                rollout_rmse=d["rollout"]["temp"]["rmse"] / base["rollout"]["temp"]["rmse"],
                rollout_max_abs_err=(d["rollout"]["max_abs_err"]
                                     / max(base["rollout"]["max_abs_err"], 1e-9)),
                one_step_temp_rmse=d["one_step"]["temp_rmse_C"]
                / max(base["one_step"]["temp_rmse_C"], 1e-12),
                energy_balance_abs=d["energy_balance"]["total_pct"]
                - base["energy_balance"]["total_pct"])

    C.save_json(out, C.RESULTS / "noise_gate.json")

    # ---------------- gate verdict ----------------
    # Gate rule as written in the brief: 7-bit rollout RMSE vs FP32, and
    # divergence. Reported for the clean 7-bit condition, plus the worst
    # 7-bit condition (1%/3% noise, drift) as a stricter reading.
    print("\n=== NOISE GATE (7 bits) ===")
    verdicts = {}
    for kind in ("ssdfa", "lstm"):
        d = out[kind].get("7b")
        if d is None:
            continue
        r = d["ratio_to_fp32"]["rollout_rmse"]
        div = not d["rollout"]["bounded"]
        ok = (r <= 2.0) and not div
        worst_tag, worst_r = "7b", r
        for tag, dd in out[kind].items():
            if tag.startswith("7b"):
                rr = dd["ratio_to_fp32"]["rollout_rmse"]
                if rr > worst_r:
                    worst_tag, worst_r = tag, rr
        worst_div = not out[kind][worst_tag]["rollout"]["bounded"]
        verdicts[kind] = dict(
            ratio=float(r), diverged=div, passes_gate=bool(ok),
            worst_7b_tag=worst_tag, worst_7b_ratio=float(worst_r),
            worst_7b_diverged=bool(worst_div),
            passes_gate_strict=bool((worst_r <= 2.0) and not worst_div))
        print(f"{kind}: 7-bit clean rollout RMSE ratio to FP32 = {r:.2f}x, "
              f"diverged={div}  ->  {'PASS' if ok else 'FAIL'}; "
              f"worst 7-bit condition {worst_tag} = {worst_r:.2f}x "
              f"({'PASS' if verdicts[kind]['passes_gate_strict'] else 'FAIL'} strict)")
    C.save_json(verdicts, C.RESULTS / "noise_gate_verdict.json")


if __name__ == "__main__":
    main()
