"""FedAvg harness for the federated-calibration POC (slice 1).

Boundary enforced *in code*, not just in prose:

  * a `Client` owns exactly one building's raw time-series and never
    exposes them: the only thing that leaves a client is a dict of four
    physical parameters (`local_update`),
  * the `FedAvgServer` accepts *only* such parameter dicts.  `aggregate`
    validates every update and raises `TypeError` if anything that is not
    a scalar parameter is handed in (numpy arrays, tensors, series, ...),
  * the server keeps no per-building state: it stores the global parameter
    vector and a scalar history.

`tests/test_boundary.py` proves the property: after a full federated
round no client object holds another building's series, and the server
holds no array at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence

import numpy as np

from local_model import (NOMINAL_PARAMS, PARAM_NAMES, LocalFit, fit_local,
                         mean_params, rmse_on_window)

# --------------------------------------------------------------------------
# client
# --------------------------------------------------------------------------


class Client:
    """One building's private data + its local calibration.

    The raw series are stored in `_series` and are never returned by any
    public method: `local_update` returns parameters only.
    """

    def __init__(self, name: str, series: Mapping[str, np.ndarray]):
        self.name = str(name)
        self._series = {k: np.asarray(v, dtype=np.float64)
                        for k, v in series.items()}
        self._n_local_updates = 0

    # -- introspection used by the boundary test -------------------------
    @property
    def series_arrays(self) -> List[np.ndarray]:
        """The arrays this client holds (private; used by the tests)."""
        return list(self._series.values())

    @property
    def n_local_updates(self) -> int:
        return self._n_local_updates

    # -- the only thing that may leave the client ------------------------
    def local_update(self, global_params: Mapping[str, float],
                     steps: int = 60, lr: float = 0.05) -> Dict[str, float]:
        """Run local SGD on THIS building's data and return the parameters.

        The returned dict contains scalars only -- no data, no gradients,
        no per-sample statistics.
        """
        fit: LocalFit = fit_local(self._series, init_params=global_params,
                                  steps=steps, lr=lr)
        self._n_local_updates += 1
        return {k: float(fit.params[k]) for k in PARAM_NAMES}

    def local_fit(self, init_params: Optional[Mapping[str, float]] = None,
                  steps: int = 400, lr: float = 0.05) -> LocalFit:
        """Full local calibration (isolated-local arm)."""
        return fit_local(self._series, init_params=init_params, steps=steps,
                         lr=lr)

    def evaluate(self, params: Mapping[str, float], start: int, end: int) -> float:
        """Free-running rollout RMSE of the given parameters on this client."""
        return rmse_on_window(params, self._series, start, end)


# --------------------------------------------------------------------------
# server
# --------------------------------------------------------------------------


class FedAvgServer:
    """The aggregator.  It sees parameter updates only -- never data."""

    def __init__(self, init_params: Optional[Mapping[str, float]] = None):
        self.global_params: Dict[str, float] = {
            k: float((init_params or NOMINAL_PARAMS)[k]) for k in PARAM_NAMES}
        self.round_history: List[Dict[str, float]] = []
        self.n_aggregations = 0

    # -- validation ------------------------------------------------------
    @staticmethod
    def _validate_update(update: object) -> Dict[str, float]:
        if not isinstance(update, Mapping):
            raise TypeError(
                "FedAvg accepts parameter updates only, got %s -- raw data "
                "must never reach the server" % type(update).__name__)
        extra = set(update) - set(PARAM_NAMES)
        if extra:
            raise TypeError("unexpected entries in a parameter update: %s"
                            % sorted(extra))
        out: Dict[str, float] = {}
        for k in PARAM_NAMES:
            v = update[k]
            if isinstance(v, (np.ndarray, list, tuple, dict)):
                raise TypeError(
                    "parameter %r must be a scalar, got %s -- raw data must "
                    "never reach the server" % (k, type(v).__name__))
            if isinstance(v, np.generic):
                v = v.item()
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                raise TypeError("parameter %r must be a real scalar, got %r"
                                % (k, v))
            if not np.isfinite(out[k]):
                raise ValueError("parameter %r is not finite: %r" % (k, out[k]))
        return out

    # -- the FedAvg step -------------------------------------------------
    def aggregate(self, updates: Sequence[Mapping[str, float]]
                  ) -> Dict[str, float]:
        """Average the client parameter updates (FedAvg)."""
        if not updates:
            raise ValueError("no client updates to aggregate")
        validated = [self._validate_update(u) for u in updates]
        self.global_params = mean_params(validated)
        self.n_aggregations += 1
        return dict(self.global_params)


@dataclass
class RoundRecord:
    """Per-round diagnostics (scalars only -- no data)."""

    round: int
    global_params: Dict[str, float]
    client_params: List[Dict[str, float]] = field(default_factory=list)
    client_losses: List[float] = field(default_factory=list)

    def spread(self) -> float:
        """Max relative spread of the client updates around their mean."""
        if not self.client_params:
            return 0.0
        vals = np.array([[p[k] for k in PARAM_NAMES] for p in self.client_params])
        mean = vals.mean(axis=0)
        rel = np.abs(vals - mean) / np.maximum(np.abs(mean), 1e-12)
        return float(rel.max())


def run_fedavg(clients: Sequence[Client], server: FedAvgServer,
               rounds: int = 15, local_steps: int = 60, lr: float = 0.05
               ) -> List[RoundRecord]:
    """Run `rounds` FedAvg rounds over `clients`.

    Each round: every client starts from the current global parameters,
    runs `local_steps` local SGD steps on its OWN data, and returns its
    parameters; the server averages them.  No raw series ever cross the
    client/server boundary.
    """
    records: List[RoundRecord] = []
    for r in range(int(rounds)):
        updates = [c.local_update(server.global_params, steps=local_steps, lr=lr)
                   for c in clients]
        server.aggregate(updates)
        records.append(RoundRecord(round=r,
                                   global_params=dict(server.global_params),
                                   client_params=[dict(u) for u in updates]))
    return records
