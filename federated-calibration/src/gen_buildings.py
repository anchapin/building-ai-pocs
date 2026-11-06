"""Synthetic building generator for the federated-calibration POC (slice 1).

The generator produces a small population of *synthetic* buildings.  Each
building is a 1R1C grey-box zone with a known thermostat (proportional power
controller) driven by

    C dT/dt = UA * (T_out - T) + s * P_sched(t) + g_sol * S(t) + Q_hvac(T, T_set)

with

    C     : zone capacitance            [J/K]      (unknown to the client)
    UA    : envelope + infiltration UA  [W/K]      (unknown to the client)
    s     : internal-gain scale         [-]        (unknown to the client)
    g_sol : solar-gain scale            [W]        (unknown to the client)
    P_sched(t) : occupancy/equipment profile    (shape known to the client)
    S(t)  : clear-sky shape             [-]        (shape known to the client)
    Q_hvac : thermostat power           [W]        (law known to the client)

The solar term is *not* perfectly predictable: the truth modulates the
clear-sky shape with a per-building cloudy AR(1) factor, which no client
model contains.  This is the deliberate model-misspecification of the POC:
a building can only calibrate the mean solar gain, never the day's cloud
pattern.  It is what keeps the local calibration error above the
measurement-noise floor and makes the federated-vs-isolated comparison
non-trivial.

Everything else is driven by synthetic weather traces and setpoint
schedules.  The truth simulator lives in this file; the *client-side* model
(what a building's own controller would calibrate) is an independent
re-implementation in `local_model.py`.  `tests/test_gen_buildings.py`
cross-checks the two implementations.

Population (9 federated clients + 2 held-out buildings):

    clients 0..8  : {light, medium, heavy} vintage x {temperate, cold, hot}
    held-out  H1  : medium / temperate   (in-family, zero-shot target)
    held-out  H2  : very heavy / hot     (non-IID stress target)

Nothing is downloaded: the population is generated locally and is fully
determined by the seed.  Generated series are written to `data/` (git
ignored) by the CLI; they are never committed.

Usage:
    python src/gen_buildings.py --seed 42 --out-dir ../data
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np

# --------------------------------------------------------------------------
# physics constants (the thermostat law is *known* to every client)
# --------------------------------------------------------------------------

DT = 3600.0            # hourly time step [s]
K_PROP = 40.0          # thermostat proportional power gain [W/K]
Q_HEAT_MAX = 3000.0    # heating power limit [W]
Q_COOL_MAX = 2500.0    # cooling power limit [W]
NOISE_STD = 0.05       # zone-temperature measurement noise [degC]

# Client-side known occupancy / equipment profile (shape only; the scale `s`
# is a calibration unknown).
P_OCCUPIED = 120.0     # [W]
P_UNOCCUPIED = 25.0    # [W]
OCCUPY_START = 7
OCCUPY_END = 19       # occupied for hours [7, 19)

# Vintage families: (capacitance [J/K], envelope UA [W/K], solar gain [W])
VINTAGES: Dict[str, Tuple[float, float, float]] = {
    "light": (1.5e6, 10.0, 300.0),
    "medium": (3.0e6, 18.0, 400.0),
    "heavy": (6.0e6, 28.0, 500.0),
    "very_heavy": (1.2e7, 35.0, 600.0),
}

CLIMATES: Dict[str, Tuple[float, float, float]] = {
    # (mean outdoor temp [degC], diurnal amplitude [degC], phase [h])
    "temperate": (12.0, 5.0, 9.0),
    "cold": (2.0, 4.0, 9.5),
    "hot": (24.0, 6.0, 8.0),
    # only used by the "wide" heterogeneity mode (slice 2)
    "arctic": (-8.0, 3.0, 9.5),
    "tropical": (30.0, 4.0, 9.0),
}

# (name, vintage, climate) of the nine federated clients.
CLIENT_SPECS: List[Tuple[str, str, str]] = [
    ("client-0", "light", "temperate"),
    ("client-1", "medium", "temperate"),
    ("client-2", "heavy", "temperate"),
    ("client-3", "light", "cold"),
    ("client-4", "medium", "cold"),
    ("client-5", "heavy", "cold"),
    ("client-6", "light", "hot"),
    ("client-7", "medium", "hot"),
    ("client-8", "heavy", "hot"),
]

# (name, vintage, climate) of the two held-out buildings.
HELDOUT_SPECS: List[Tuple[str, str, str]] = [
    ("holdout-H1", "medium", "temperate"),
    ("holdout-H2", "very_heavy", "hot"),
]

# --------------------------------------------------------------------------
# heterogeneity modes (slice 2)
#
# "baseline"  : the slice-1 population (unchanged, bit-identical).
# "wide"      : same nine client archetypes, but the per-building truth
#               parameters are drawn from a much wider range (a strongly
#               heterogeneous federation).
# "clustered" : the nine clients fall into three tight clusters with very
#               different vintages/climates (a clustered non-IID split):
#               clients 0-2 light/cold, 3-5 heavy/hot, 6-8 medium/temperate.
#               Within a cluster the truth parameters are nearly identical,
#               across clusters they are far apart -- so the *arithmetic
#               mean* of the client parameter vectors is not any real
#               building.
#
# The held-out buildings are NOT changed by the mode: the evaluation
# protocol stays the slice-1 one (H1 = medium/temperate, H2 = very
# heavy/hot), so slice-2 numbers are comparable with slice-1 numbers.
# --------------------------------------------------------------------------
HETEROGENEITY_MODES: Tuple[str, ...] = ("baseline", "wide", "clustered", "iid")

# Per-building truth-parameter ranges, per mode.  The keys are the truth
# parameter names; the values are the (low, high) multipliers applied to
# the archetype's nominal value.
TRUTH_RANGES: Dict[str, Dict[str, Tuple[float, float]]] = {
    "baseline": {
        "C": (0.85, 1.15),
        "UA": (0.85, 1.15),
        "s": (0.6, 1.4),
        "g_sol": (0.8, 1.2),
    },
    "wide": {
        "C": (0.6, 1.7),
        "UA": (0.6, 1.7),
        "s": (0.35, 1.9),
        "g_sol": (0.55, 1.5),
    },
    # clusters are tight around their archetype value (see _cluster_specs)
    "clustered": {
        "C": (0.95, 1.05),
        "UA": (0.95, 1.05),
        "s": (0.9, 1.1),
        "g_sol": (0.95, 1.05),
    },
    # IID control: every client is the same archetype with a very tight
    # truth spread, so the federation is (nearly) IID.  Used only to
    # re-check the issue's No-go trigger "federated ~= centralised on IID
    # synthetic data".
    "iid": {
        "C": (0.98, 1.02),
        "UA": (0.98, 1.02),
        "s": (0.95, 1.05),
        "g_sol": (0.98, 1.02),
    },
}

# Clustered mode: (client index range, vintage, climate) of the three
# client clusters.
CLUSTER_SPECS: List[Tuple[Tuple[int, int], str, str]] = [
    ((0, 3), "light", "cold"),
    ((3, 6), "heavy", "hot"),
    ((6, 9), "medium", "temperate"),
]

DEFAULT_HOURS = 240  # 10 days of hourly data per building


# --------------------------------------------------------------------------
# data classes
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class TruthParams:
    """The (unknown to the client) physical parameters of a building."""

    C: float
    UA: float
    s: float
    g_sol: float

    def to_dict(self) -> Dict[str, float]:
        return {"C": self.C, "UA": self.UA, "s": self.s, "g_sol": self.g_sol}


@dataclass
class Building:
    """A synthetic building: its truth parameters and its time series."""

    name: str
    vintage: str
    climate: str
    truth: TruthParams
    t_out: np.ndarray
    t_set: np.ndarray
    p_sched: np.ndarray
    t_zone: np.ndarray
    t_zone_clean: np.ndarray
    meta: Dict[str, object] = field(default_factory=dict)

    def client_series(self) -> Dict[str, np.ndarray]:
        """The raw time-series a client sees (no truth parameters).

        `clear_sky` is a *public* deterministic shape (hour-of-day based),
        not private data; the client can compute it itself.
        """
        return {
            "t_out": self.t_out,
            "t_set": self.t_set,
            "p_sched": self.p_sched,
            "clear_sky": clear_sky(len(self.t_out)),
            "t_zone": self.t_zone,
        }


# --------------------------------------------------------------------------
# exogenous drivers
# --------------------------------------------------------------------------

def occupancy_profile(n: int) -> np.ndarray:
    """Known occupancy/equipment profile shape [W] (no scale)."""
    hod = np.arange(n) % 24
    occupied = (hod >= OCCUPY_START) & (hod < OCCUPY_END)
    return np.where(occupied, P_OCCUPIED, P_UNOCCUPIED)


def clear_sky(n: int) -> np.ndarray:
    """Public clear-sky shape [-] (daytime bell, zero at night).

    The *shape* is public (it is a function of the hour of the day); the
    solar *gain* is unknown, and the truth's cloudy modulation is not
    knowable at all.
    """
    hod = np.arange(n) % 24
    return np.maximum(0.0, np.sin(np.pi * (hod - 6.0) / 12.0))


def cloudy_factor(n: int, rng: np.random.Generator) -> np.ndarray:
    """AR(1) cloud modulation of the solar gain [-] (unknowable)."""
    x = np.empty(n, dtype=np.float64)
    x[0] = 1.0
    eps = rng.normal(0.0, 0.35, n)
    for k in range(1, n):
        x[k] = 0.8 * x[k - 1] + 0.2 * (1.0 + eps[k])
    return np.clip(x, 0.3, 1.8)


def weather_trace(climate: str, n: int, rng: np.random.Generator) -> np.ndarray:
    """Synthetic hourly outdoor temperature [degC] for a climate."""
    mean, amp, phase = CLIMATES[climate]
    h = np.arange(n, dtype=np.float64)
    diurnal = amp * np.sin(2.0 * np.pi * (h - phase) / 24.0)
    # slow synoptic drift (period ~ 4 days) + AR(1) weather noise
    synoptic = 2.5 * np.sin(2.0 * np.pi * h / (96.0) + 0.7)
    noise = np.zeros(n)
    eps = rng.normal(0.0, 0.35, n)
    for k in range(1, n):
        noise[k] = 0.6 * noise[k - 1] + eps[k]
    return mean + diurnal + synoptic + noise


def setpoint_schedule(n: int, offset: float) -> np.ndarray:
    """Setpoint schedule [degC]: occupied setback, unoccupied setback."""
    hod = np.arange(n) % 24
    occupied = (hod >= OCCUPY_START) & (hod < 23)
    return np.where(occupied, 21.0, 17.0) + offset


# --------------------------------------------------------------------------
# truth simulator
# --------------------------------------------------------------------------

def simulate_truth(params: TruthParams, t_out: np.ndarray, t_set: np.ndarray,
                   p_sched: np.ndarray, clear: np.ndarray, cloud: np.ndarray,
                   t_init: float) -> np.ndarray:
    """Explicit-Euler truth rollout of the 1R1C zone [degC] (no noise)."""
    n = len(t_out)
    t = np.empty(n, dtype=np.float64)
    t[0] = t_init
    for k in range(n):
        cur = t[k]
        err = t_set[k] - cur
        q_hv = float(np.clip(K_PROP * err, -Q_COOL_MAX, Q_HEAT_MAX))
        q_sol = params.g_sol * clear[k] * cloud[k]
        dT = DT / params.C * (params.UA * (t_out[k] - cur)
                              + params.s * p_sched[k] + q_sol + q_hv)
        if k + 1 < n:
            t[k + 1] = cur + dT
    return t


# --------------------------------------------------------------------------
# population
# --------------------------------------------------------------------------

def _make_building(name: str, vintage: str, climate: str, rng: np.random.Generator,
                   n_hours: int,
                   ranges: Dict[str, Tuple[float, float]] | None = None
                   ) -> Building:
    c_nom, ua_nom, g_nom = VINTAGES[vintage]
    r = ranges if ranges is not None else TRUTH_RANGES["baseline"]
    truth = TruthParams(
        C=float(c_nom * rng.uniform(*r["C"])),
        UA=float(ua_nom * rng.uniform(*r["UA"])),
        s=float(rng.uniform(*r["s"])),
        g_sol=float(g_nom * rng.uniform(*r["g_sol"])),
    )
    t_out = weather_trace(climate, n_hours, rng)
    set_offset = float(rng.uniform(-0.8, 0.8))
    t_set = setpoint_schedule(n_hours, set_offset)
    p_sched = occupancy_profile(n_hours)
    clear = clear_sky(n_hours)
    cloud = cloudy_factor(n_hours, rng)
    t_init = float(t_set[0] + rng.uniform(-0.3, 0.3))
    t_clean = simulate_truth(truth, t_out, t_set, p_sched, clear, cloud, t_init)
    t_zone = t_clean + rng.normal(0.0, NOISE_STD, n_hours)
    return Building(
        name=name, vintage=vintage, climate=climate, truth=truth,
        t_out=t_out, t_set=t_set, p_sched=p_sched,
        t_zone=t_zone, t_zone_clean=t_clean,
        meta={"setpoint_offset": set_offset, "t_init": t_init,
              "noise_std": NOISE_STD},
    )


def client_specs(heterogeneity: str = "baseline") -> List[Tuple[str, str, str]]:
    """The (name, vintage, climate) list of the nine clients, per mode.

    "baseline"  -- the slice-1 population (unchanged).
    "wide"      -- the same archetypes, but wider per-building truth spread
                   (handled in `_make_building`).
    "clustered" -- three tight, well-separated clusters (light/cold,
                   heavy/hot, medium/temperate): a clustered non-IID split.
    """
    if heterogeneity == "baseline":
        return list(CLIENT_SPECS)
    if heterogeneity == "wide":
        return list(CLIENT_SPECS)
    if heterogeneity == "clustered":
        specs: List[Tuple[str, str, str]] = []
        for (lo, hi), vintage, climate in CLUSTER_SPECS:
            for i in range(lo, hi):
                specs.append(("client-%d" % i, vintage, climate))
        return specs
    if heterogeneity == "iid":
        # every client the same archetype: an (almost) IID federation
        return [("client-%d" % i, "medium", "temperate") for i in range(9)]
    raise ValueError("unknown heterogeneity mode %r (known: %s)"
                     % (heterogeneity, ", ".join(HETEROGENEITY_MODES)))


def generate_population(seed: int = 42, n_hours: int = DEFAULT_HOURS,
                        heterogeneity: str = "baseline"
                        ) -> Tuple[List[Building], List[Building]]:
    """Generate the client population and the held-out buildings.

    Deterministic for a fixed seed: every building draws from its own
    `np.random.default_rng([seed, index])` stream, so the population does
    not depend on the order in which buildings are generated.

    `heterogeneity` selects the client population (see `client_specs`); the
    held-out buildings are the same in every mode, so the evaluation
    protocol is unchanged.
    """
    ranges = TRUTH_RANGES[heterogeneity]
    clients: List[Building] = []
    for i, (name, vintage, climate) in enumerate(client_specs(heterogeneity)):
        rng = np.random.default_rng([seed, i])
        clients.append(_make_building(name, vintage, climate, rng, n_hours,
                                       ranges))
    heldout: List[Building] = []
    for j, (name, vintage, climate) in enumerate(HELDOUT_SPECS):
        rng = np.random.default_rng([seed, 100 + j])
        heldout.append(_make_building(name, vintage, climate, rng, n_hours,
                                       TRUTH_RANGES["baseline"]))
    return clients, heldout


def save_population(out_dir: str, seed: int, clients: List[Building],
                    heldout: List[Building]) -> str:
    """Write the generated population to `out_dir` (git-ignored scratch)."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "buildings_seed%d.npz" % seed)
    arrays: Dict[str, np.ndarray] = {}
    meta: Dict[str, object] = {"seed": seed, "buildings": []}
    for b in list(clients) + list(heldout):
        for key, arr in b.client_series().items():
            arrays["%s_%s" % (b.name, key)] = arr
        meta["buildings"].append({
            "name": b.name, "vintage": b.vintage, "climate": b.climate,
            "truth": b.truth.to_dict(), "meta": b.meta,
        })
    np.savez_compressed(path, **arrays)
    with open(os.path.join(out_dir, "buildings_seed%d.json" % seed), "w") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    return path


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--hours", type=int, default=DEFAULT_HOURS)
    parser.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    args = parser.parse_args(argv)
    clients, heldout = generate_population(args.seed, args.hours)
    path = save_population(args.out_dir, args.seed, clients, heldout)
    print("seed=%d  clients=%d  heldout=%d  hours=%d" % (
        args.seed, len(clients), len(heldout), args.hours))
    for b in list(clients) + list(heldout):
        print("  %-12s %-11s %-10s C=%.3g UA=%.3g s=%.2f" % (
            b.name, b.vintage, b.climate, b.truth.C, b.truth.UA, b.truth.s))
    print("written: %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
