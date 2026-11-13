"""Reference biquadratic HVAC performance curve + least-squares refit comparator.

Scope note (issue #47, SLICE 1 / Phase 0)
----------------------------------------
The POC generator is a *published* ASHRAE/EnergyPlus reference biquadratic of the
form

    evaluate(x, y) = a + b*x + c*x**2 + d*y + e*y**2 + f*x*y      (x = part-load ratio, y = temperature)

as required by issue #47 ("the generator is ONLY the AshrStdCoeffs ASHRAE/EnergyPlus
reference biquadratic curve").  The issue points at Fluxion's
`src/sim/hvac/part_load_curves.rs` (`AshrStdCoeffs`) for the numeric coefficients.
That Fluxion clone lives OUTSIDE this worktree and this POC's room forbids reading
any path outside the worktree, so the issue's numeric constants could not be copied
verbatim.  Per the slice brief, we therefore use a *clearly cited published
ASHRAE/EnergyPlus reference set* instead, namely the DOE-2-derived `Curve:Biquadratic`
coefficients that ship inside EnergyPlus' own example/test file
`testfiles/ElectricEIRChiller.idf` (EnergyPlus source repository, NREL/EnergyPlus):

    ChillerCentCapFT  (Curve:Biquadratic, "Cooling Capacity Function of Temperature
                       Curve for open or hermetic water-cooled centrifugal chillers.
                       Same as DOE-2.1E HERM-CENT-CAP-FT (CCAPT3)")
        a =  0.257896     b =  0.0389016    c = -0.00021708
        d =  0.0468684    e = -0.00094284   f = -0.00034344
        min x = 5.0   max x = 10.0
        min y = 24.0  max y = 35.0

    ChillerCentEIRFT  (Curve:Biquadratic, "Electric Input to Cooling Output Ratio
                       Function of Temperature")
        a =  0.610921     b = -0.0907202   c =  0.00085127
        d = -0.00838187  e =  0.00012192   f =  0.00017850
        min x = 5.0   max x = 10.0
        min y = 24.0  max y = 35.0

Equation form + semantics of the six coefficients and of the x/y range fields are
documented in the EnergyPlus Input-Output Reference, group "Performance Curves",
object `Curve:Biquadratic`:
    https://bigladdersoftware.com/epx/docs/24-2/input-output-reference/group-performance-curves.html
    z = C1 + C2*x + C3*x**2 + C4*y + C5*y**2 + C6*x*y
The same biquadratic form for HVAC capacity/efficiency vs temperature is used by the
ASHRAE-published EnergyPlus VRF model (ASHRAE 2013 paper DA-13-026, Eq. (21),
"CAPFT_coil,cool = a + b(T_wb) + c(T_wb)^2 + d(T_c) + e(T_c)^2 + f(T_wb)(T_c)"; also
issued as FSEC-CR-1950-13), so the *family* exercised here is the published
ASHRAE/EnergyPlus biquadratic performance-curve family.

Variable-role mapping used by this POC (documented, and the reason the numbers differ
from the issue's AshrStdCoeffs):  the issue's convention is (x = part-load ratio,
y = temperature).  The published EnergyPlus coefficient sets above were fitted with
x = leaving chilled-water temperature and y = entering condenser-fluid temperature.
This POC keeps the published coefficient values and the published y (temperature) range
[24, 35] degC, and re-interprets the first independent variable as the part-load
ratio over the chiller's published operating range min PLR = 0.15 .. max PLR = 1.0
(EnergyPlus `Chiller:Electric:EIR` fields "Minimum/Maximum Part Load Ratio" in the
same example file), restricted by issue #47 to PLR 0.3 .. 1.0 for the study.
The re-interpretation is an assumption of this slice, not a published fact; it is
reported as `[unsupported]` in REPORT.md and is NOT a premise for any verdict (this
slice produces no verdict).

Nothing here touches Fluxion's `default_ahri_coefficients()` or `ahri_coefficients.json`;
those are explicitly out of scope as data sources (issue #47, fluxion #3942).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Sequence, Tuple

import numpy as np

__all__ = [
    "BiquadraticCoeffs",
    "REFERENCE_COEFFS",
    "OPERATING_RANGE",
    "TRAIN_BOX",
    "IN_RANGE_BOX",
    "EXTRAPOLATION_BOX",
    "biquadratic",
    "generate_dataset",
    "ls_biquadratic_fit",
    "rmse",
]

# --------------------------------------------------------------------------------------
# Published reference coefficient sets (EnergyPlus testfiles/ElectricEIRChiller.idf)
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class BiquadraticCoeffs:
    """Six coefficients of the ASHRAE/EnergyPlus biquadratic performance curve."""

    a: float
    b: float
    c: float
    d: float
    e: float
    f: float

    def evaluate(self, x, y):
        """evaluate(x, y) = a + b*x + c*x^2 + d*y + e*y^2 + f*x*y (numpy-safe)."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        return (
            self.a
            + self.b * x
            + self.c * x**2
            + self.d * y
            + self.e * y**2
            + self.f * x * y
        )

    def as_vector(self) -> np.ndarray:
        return np.array([self.a, self.b, self.c, self.d, self.e, self.f], dtype=float)

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"{self.a:.6g} + {self.b:.6g}*x + {self.c:.6g}*x^2 + "
            f"{self.d:.6g}*y + {self.e:.6g}*y^2 + {self.f:.6g}*x*y"
        )


REFERENCE_COEFFS: Dict[str, "BiquadraticCoeffs"] = {
    # Cooling Capacity Function of Temperature (DOE-2.1E HERM-CENT-CAP-FT / CCAPT3).
    "ChillerCentCapFT": BiquadraticCoeffs(0.257896, 0.0389016, -0.00021708, 0.0468684, -0.00094284, -0.00034344),
    # Electric Input to Cooling Output Ratio Function of Temperature.
    "ChillerCentEIRFT": BiquadraticCoeffs(0.610921, -0.0907202, 0.00085127, -0.00838187, 0.00012192, 0.00017850),
}

#: PLR operating range of the published chiller (EnergyPlus `Chiller:Electric:EIR`
#: "Minimum/Maximum Part Load Ratio" = 0.15 / 1.0), narrowed to the range the issue
#: studies (0.3 .. 1.0).
OPERATING_RANGE = {"plr": (0.3, 1.0), "temp_c": (24.0, 35.0)}

#: Restricted training box (issue #47 task 1): PLR 0.3-0.8 and the lower ~60 % of the
#: published temperature range [24, 35] -> [24, 30.6].
TRAIN_BOX = {"plr": (0.3, 0.8), "temp_c": (24.0, 30.6)}

#: In-range evaluation box: identical to the training box (held-out samples).
IN_RANGE_BOX = {"plr": (0.3, 0.8), "temp_c": (24.0, 30.6)}

#: Extrapolation box (issue #47 task 1): PLR 0.8-1.0 and the upper temperature range.
EXTRAPOLATION_BOX = {"plr": (0.8, 1.0), "temp_c": (30.6, 35.0)}


def biquadratic(x, y, coeffs: BiquadraticCoeffs):
    """Functional alias for `coeffs.evaluate(x, y)`."""
    return coeffs.evaluate(x, y)


# --------------------------------------------------------------------------------------
# Data generation
# --------------------------------------------------------------------------------------


@dataclass
class Dataset:
    """A generated sample set: inputs (N,2) as (plr, temp_c) plus outputs (N,)."""

    x: np.ndarray
    y: np.ndarray
    box: Dict[str, Tuple[float, float]]

    def __len__(self) -> int:
        return int(self.x.shape[0])


def generate_dataset(
    seed: int,
    n_samples: int,
    box: Dict[str, Tuple[float, float]],
    coeffs: BiquadraticCoeffs = REFERENCE_COEFFS["ChillerCentCapFT"],
    noise_pct: float = 0.0,
) -> Dataset:
    """Sample the reference biquadratic uniformly on `box`.

    `noise_pct` is a multiplicative (i.e. relative) noise level: 1.0 means 1 %.
    With noise_pct = 0 the samples are exactly on the curve (control condition).
    """
    rng = np.random.default_rng(seed)
    (plr_lo, plr_hi) = box["plr"]
    (t_lo, t_hi) = box["temp_c"]
    plr = rng.uniform(plr_lo, plr_hi, size=n_samples)
    temp = rng.uniform(t_lo, t_hi, size=n_samples)
    out = coeffs.evaluate(plr, temp)
    if noise_pct:
        out = out * (1.0 + noise_pct / 100.0 * rng.standard_normal(n_samples))
    return Dataset(x=np.column_stack([plr, temp]), y=np.asarray(out, dtype=float), box=box)


def design_matrix(x: np.ndarray) -> np.ndarray:
    """Design matrix [1, x, x^2, y, y^2, x*y] for the biquadratic basis."""
    x = np.asarray(x, dtype=float)
    plr, temp = x[:, 0], x[:, 1]
    return np.column_stack([np.ones_like(plr), plr, plr**2, temp, temp**2, plr * temp])


def ls_biquadratic_fit(
    x: np.ndarray, y: np.ndarray
) -> Tuple[BiquadraticCoeffs, np.ndarray]:
    """Least-squares biquadratic refit (the comparator).

    Returns the refitted coefficients and the residual vector.  This is the in-codebase
    comparator the issue mentions; it is handed exactly the same training data as PySR.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    design = design_matrix(x)
    coeffs, residuals, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    resid = y - design @ coeffs
    return (
        BiquadraticCoeffs(*(float(c) for c in coeffs)),
        resid,
    )


def rmse(pred, truth) -> float:
    pred = np.asarray(pred, dtype=float)
    truth = np.asarray(truth, dtype=float)
    return float(math.sqrt(float(np.mean((pred - truth) ** 2))))
