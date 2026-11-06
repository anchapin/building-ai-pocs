"""The three models.

MLP       : feed-forward on a flattened 24 h window, Adam + backprop.
LSTM      : 1-layer LSTM over the same 24 h window, Adam + truncated BPTT.
SS-DFA    : single-map reservoir block + trainable readout, trained by
            state-skipping Direct Feedback Alignment (no BPTT, no stored
            state trajectory).

Quantisation hooks (`QConfig`) exist only for the Section 6 noise gate; they
are inert unless explicitly enabled on a trained model.
"""

import numpy as np
import torch
import torch.nn as nn

from common import N_HISTORY


def math_sqrt(v: float) -> float:
    return float(v) ** 0.5


# ===========================================================================
#                          quantisation / noise-gate helpers
# ===========================================================================
def quantise_tensor(t: torch.Tensor, bits: int) -> torch.Tensor:
    """Symmetric per-tensor uniform quantisation, round-to-nearest."""
    if bits >= 32:
        return t
    qmax = float(2 ** (bits - 1) - 1)
    scale = t.abs().max().clamp(min=1e-12) / qmax
    return torch.round(t / scale).clamp(-qmax, qmax) * scale


def quantise_activation(a: torch.Tensor, bits: int, noise_frac: float) -> torch.Tensor:
    """Per-tensor symmetric quantisation of the live activation, plus optional
    Gaussian noise expressed as a fraction of that tensor's signal range."""
    if bits >= 32 and noise_frac <= 0.0:
        return a
    amax = a.detach().abs().max().clamp(min=1e-12)
    out = a
    if bits < 32:
        qmax = float(2 ** (bits - 1) - 1)
        scale = amax / qmax
        out = torch.round(out / scale).clamp(-qmax, qmax) * scale
    if noise_frac > 0.0:
        rng = a.abs().max().clamp(min=1e-12) * 2.0 * noise_frac   # 1 sigma
        out = out + torch.randn_like(out) * rng
    return out


class QConfig:
    """Post-training quantisation + analogue-noise configuration.

    Attributes
    ----------
    bits : weight/activation bit width (32 = FP32 reference)
    noise_frac : Gaussian noise sigma as a fraction of each tensor's signal
        range (2 * max|value|); 0.0 disables.
    """

    def __init__(self, bits=32, noise_frac=0.0):
        self.bits = bits
        self.noise_frac = noise_frac
        self.drift_eps = {}          # parameter name -> current drift epsilon


def qw(cfg, w):
    if cfg is None:
        return w
    return quantise_tensor(w, cfg.bits)


def qa(cfg, a):
    if cfg is None:
        return a
    return quantise_activation(a, cfg.bits, cfg.noise_frac)


# ===========================================================================
#                                  MLP
# ===========================================================================
class MLP(nn.Module):
    def __init__(self, hidden=(128, 128), n_in=N_HISTORY * 6, n_out=3):
        super().__init__()
        layers, d = [], n_in
        for h in hidden:
            layers += [nn.Linear(d, h), nn.Tanh()]
            d = h
        layers += [nn.Linear(d, n_out)]
        self.net = nn.Sequential(*layers)
        self.q = None

    def forward(self, x):
        # x: (B, L, 6) -> flatten
        if x.dim() == 3:
            x = x.reshape(x.shape[0], -1)
        h = qa(self.q, x)
        for m in self.net:
            if isinstance(m, nn.Linear):
                h = torch.nn.functional.linear(h, qw(self.q, m.weight), qw(self.q, m.bias))
            elif isinstance(m, nn.Tanh):
                h = torch.tanh(h)
            else:
                h = m(h)
        return h


# ===========================================================================
#                                  LSTM
# ===========================================================================
class LSTMSurrogate(nn.Module):
    def __init__(self, hidden=64, layers=1, n_in=6, n_out=3):
        super().__init__()
        self.lstm = nn.LSTM(n_in, hidden, layers, batch_first=True)
        self.head = nn.Linear(hidden, n_out)
        self.hidden = hidden
        self.layers = layers
        self.q = None

    def _cell(self, x, state):
        # quantised path: per-tensor PTQ on weights + activations at each gate.
        # NOTE: gate activations are kept 2-D (B, H); the nn.LSTM-style state
        # (layers, B, H) is squeezed on entry and re-unsqueezed on exit so the
        # broadcast never mixes (B, H) with (1, B, H).
        h0, c0 = state
        h, c = h0[0], c0[0]
        Wih = qa(self.q, qw(self.q, self.lstm.weight_ih_l0))
        Whh = qa(self.q, qw(self.q, self.lstm.weight_hh_l0))
        bi = qw(self.q, self.lstm.bias_ih_l0)
        bh = qw(self.q, self.lstm.bias_hh_l0)
        outputs = []
        for t in range(x.shape[1]):
            xt = qa(self.q, x[:, t])
            gates = (Wih @ xt.T + Whh @ h.T).T + bi + bh
            i, f, g, o = gates.chunk(4, dim=1)
            i = torch.sigmoid(i); f = torch.sigmoid(f)
            g = torch.tanh(g); o = torch.sigmoid(o)
            c = qa(self.q, f * c + i * g)
            h = qa(self.q, o * torch.tanh(c))
            outputs.append(h)
        hq = torch.stack(outputs, dim=1)
        return hq, (h.unsqueeze(0), c.unsqueeze(0))

    def forward(self, x, state=None):
        if self.q is not None and self.layers == 1:
            h, c = self._cell(x, state if state is not None else self._init_state(x))
        else:
            if state is None:
                h, c = self._init_state(x)
                state = (h, c)
            h, c = self.lstm(x, state)
        out = self.head(qa(self.q, h[:, -1]))
        return out, (h, c)

    def _init_state(self, x):
        z = torch.zeros(self.layers, x.shape[0], self.hidden, device=x.device)
        return z, z.clone()


# ===========================================================================
#                        SS-DFA single-map reservoir
# ===========================================================================
class SSDFA(nn.Module):
    """Single-map block + trainable readout, trained with state-skipping DFA.

    Architecture (see REPORT.md for the full assumption list):
      * `W_in`  fixed random input matrix (input scaling is a trainable scalar)
      * `W_res` fixed random recurrent matrix, scaled to a target spectral
        radius; NOT trained
      * one fixed scalar 1-D map  f(s) = tanh(g * s), reused at every time
        step; the map gain `g` is a single trainable scalar ("lightly
        parameterised")
      * trainable linear readout W_out, b_out
      * `W_fb`   fixed random feedback matrix used by DFA to project the final
        output error back onto the reservoir - this is the DFA rule; it is NOT
        the transpose of any forward weight

    Training never backpropagates through time and never stores the hidden
    state trajectory: see `dfa_steps` in train.py.
    """

    def __init__(self, n_res=160, n_in=6, n_out=3, spectral_radius=0.9,
                 input_scale_init=1.0, gain_init=1.0, sparsity=0.10, seed=0,
                 readout_with_input=False):
        super().__init__()
        g = torch.Generator().manual_seed(seed)

        W_in = torch.randn(n_in, n_res, generator=g) / math_sqrt(n_in)
        self.register_buffer("W_in", W_in)

        W_res = (torch.rand(n_res, n_res, generator=g) < sparsity).float() \
            * (torch.randn(n_res, n_res, generator=g))
        eig = torch.linalg.eigvals(W_res).abs().max().item()
        W_res = W_res * (spectral_radius / max(eig, 1e-9))
        self.register_buffer("W_res", W_res)

        # DFA feedback matrix: fixed, random, independent of forward weights.
        W_fb = torch.randn(n_out, n_res, generator=g) / math_sqrt(n_out + n_res)
        self.register_buffer("W_fb", W_fb)

        self.readout_with_input = readout_with_input
        d = n_res + (n_in if readout_with_input else 0)
        self.W_out = nn.Parameter(torch.zeros(d, n_out))
        self.b_out = nn.Parameter(torch.zeros(n_out))
        self.log_input_scale = nn.Parameter(torch.log(torch.tensor(float(input_scale_init))))
        self.log_gain = nn.Parameter(torch.log(torch.tensor(float(gain_init))))

        self.n_res = n_res
        self.q = None

    @property
    def input_scale(self):
        return self.log_input_scale.exp()

    @property
    def gain(self):
        return self.log_gain.exp()

    def _init_state(self, x):
        return torch.zeros(x.shape[0], self.n_res, device=x.device)

    def step(self, x_t, h_prev):
        """One step of the single-map block. Returns h_t and the pre-activation
        s_t (needed by the state-skipping DFA update; O(1) extra state)."""
        s = self.input_scale * (x_t @ self.W_in) + h_prev @ self.W_res
        h = torch.tanh(self.gain * qa(self.q, s))
        return h, s

    def readout_feat(self, h, x_t):
        if self.readout_with_input:
            return torch.cat([h, x_t], dim=1)
        return h

    def forward(self, x, state=None):
        """Run the window, return readout at the final step and final state."""
        B, L, _ = x.shape
        h = state if state is not None else self._init_state(x)
        s = None
        for t in range(L):
            h, s = self.step(x[:, t], h)
        z = self.readout_feat(h, x[:, -1])
        y = z @ qw(self.q, self.W_out) + qw(self.q, self.b_out)
        return y, h

    def rollout_state(self, x, state=None):
        """Same as forward but explicitly returns the final hidden state."""
        y, h = self.forward(x, state)
        return y, h


def count_params(model, trainable_only=False):
    if trainable_only:
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
    tot = 0
    for p in model.parameters():
        tot += p.numel()
    for b in model.buffers():
        tot += b.numel()
    return tot
