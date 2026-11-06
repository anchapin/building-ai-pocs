"""Diagnostic: is the SS-DFA gap caused by the DFA training rule, or by the
fixed-reservoir architecture itself?

Same fixed reservoir, three readouts:
  (a) DFA (as used in the POC)
  (b) ridge regression on the final reservoir state  -- the classic ESN oracle
  (c) ridge on [final state, current input]          -- architecture ceiling

Deleted from the headline path; results are quoted in REPORT.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
import torch

import common as C
import train as T
from models import SSDFA

sx, ss, sy = C.Scaler(), C.Scaler(), C.Scaler()
tr = C.build_arrays(1, "base", sx, ss, sy, fit=True)
va = C.build_arrays(2, "base", sx, ss, sy, fit=False)
for arr in (tr, va):
    arr["Xw"], arr["Yw"], arr["Yall"] = C.windows(arr)
Xtr = torch.from_numpy(tr["Xw"]).float()
Ytr = torch.from_numpy(tr["Yw"]).float()
Ytr_all = torch.from_numpy(tr["Yall"]).float()
Xva = torch.from_numpy(va["Xw"]).float()
Yva = torch.from_numpy(va["Yw"]).float()

cfg = T.CONFIGS["ssdfa"][0]
C.set_seed(0)
m = SSDFA(n_res=cfg["n_res"], spectral_radius=cfg["spectral_radius"],
          input_scale_init=cfg["input_scale"], gain_init=cfg["gain"],
          sparsity=cfg["sparsity"], seed=0)
gen = torch.Generator().manual_seed(777)

print("=== (a) DFA training ===")
for ep in range(40):
    tl, _ = T.dfa_epoch(m, Xtr, Ytr_all, Ytr, cfg["lr_out"], cfg["lr_deep"], gen=gen)
    if ep % 4 == 0 or ep == 39:
        vl = T.eval_loss(m, Xva, Yva)
        print(f"  ep{ep:3d} train {tl:.5f} val {vl:.5f} gain {m.gain.item():.3f} "
              f"in_scale {m.input_scale.item():.3f}")

# ---- reservoir states for ridge readouts (subsample train windows for speed)
with torch.no_grad():
    def states(X, n_max=6000):
        H, XL = [], []
        for i in range(0, min(len(X), n_max), 512):
            xb = X[i:i + 512]
            h = m._init_state(xb)
            s = None
            for t in range(xb.shape[1]):
                h, s = m.step(xb[:, t], h)
            H.append(h)
            XL.append(xb[:, -1])
        return torch.cat(H), torch.cat(XL)

    Htr, Xtr_last = states(Xtr)
    Hva, Xva_last = states(Xva)
    Ytr_sub = Ytr[: len(Htr)]
    Yva_sub = Yva[: len(Hva)]

    def ridge(H, Y, lam=1e-2):
        A = H.T @ H + lam * torch.eye(H.shape[1])
        return torch.linalg.solve(A, H.T @ Y)

    for name, Ht, Xt, Hv, Xv in [
        ("(b) ridge on final state", Htr, None, Hva, None),
        ("(c) ridge on [state, input]", torch.cat([Htr, Xtr_last], 1), None,
         torch.cat([Hva, Xva_last], 1), None),
    ]:
        W = ridge(Ht, Ytr_sub)
        va_loss = float((((Hv @ W) - Yva_sub) ** 2).mean())
        tr_loss = float((((Ht @ W) - Ytr_sub) ** 2).mean())
        print(f"{name}: train {tr_loss:.5f} val {va_loss:.5f}")
