"""Teacher dataset: 2R2C single-zone RC building driven by synthetic hourly weather.

Deterministic: every number below is fixed by SEED and the literal parameter
values in PARAMS / WEATHER_CONFIG / GAINS_CONFIG. Running this script
reproduces the byte-identical dataset.

Split design (no shuffling, no leakage):
  year 1 -> train, year 2 -> validation, year 3 -> test.
  Weather years differ in seed AND in mean-temperature offset AND in the
  internal-gain scale, so the splits are genuinely different distributions.
  Envelope variants (insulation / thermal mass) are generated for the TEST
  year only and are held out of training entirely (used by the OOD and
  monotonicity checks).
"""

import json
from pathlib import Path

import numpy as np

SEED = 20261105

N_STEPS = 8760  # 365 days x 24 h; leap years deliberately ignored (stated assumption)
DT_SUB = 300.0  # seconds, sub-hour integration step for the teacher ODE
SUB_PER_HOUR = int(3600.0 / DT_SUB)

LATITUDE_DEG = 45.0  # northern-hemisphere temperate continental climate

# ---------------------------------------------------------------- envelope ---
# Whole-building 2R2C. Node z = zone air, node m = internal thermal mass.
PARAMS = {
    "base": dict(Cz=4.2e6, Cm=4.0e7, UA_ext=180.0, Uiw=120.0, A_eff=5.0),
    # Out-of-distribution variants (held out of training; TEST year only).
    "insul_half": dict(Cz=4.2e6, Cm=4.0e7, UA_ext=360.0, Uiw=120.0, A_eff=5.0),
    "insul_double": dict(Cz=4.2e6, Cm=4.0e7, UA_ext=90.0, Uiw=120.0, A_eff=5.0),
    "mass_double": dict(Cz=4.2e6, Cm=8.0e7, UA_ext=180.0, Uiw=120.0, A_eff=5.0),
}

# ------------------------------------------------------------------- HVAC ----
HVAC = dict(
    K_h=900.0,       # W/K proportional gain, heating
    K_c=900.0,       # W/K proportional gain, cooling
    Q_h_max=8000.0,  # W delivered heating capacity
    Q_c_max=8000.0,  # W delivered cooling capacity
    T_heat_set_occ=21.0,
    T_heat_set_unocc=17.0,
    T_cool_set_occ=24.5,
    T_cool_set_unocc=28.0,
    eta_heat=0.85,   # heater efficiency -> site heating energy
    cop_a=4.0,       # COP(T_out) = max(cop_min, cop_a - cop_b*(T_out - 20))
    cop_b=0.08,
    cop_min=1.8,
)

WEATHER_CONFIG = dict(
    t_annual_mean=11.0,   # degC, year 1 (offsets below apply per year)
    t_annual_amp=13.5,    # degC, seasonal swing
    diurnal_amp=6.0,      # degC at equinox
    synoptic_ar=0.986,    # hourly AR(1) coefficient (tau ~ 3 days)
    synoptic_sigma=0.34,
    cloud_ar=0.75,
    cloud_sigma=0.28,
    cloud_mean=0.72,
    ghi_clear=1080.0,
)

# year index -> (weather seed, mean-temp offset [K], internal-gain scale)
YEARS = {
    1: (SEED + 101, 0.0, 1.00),   # train
    2: (SEED + 202, 0.8, 0.90),   # validation
    3: (SEED + 303, -0.6, 1.15),  # test
}

VARIANT_YEARS = [3]  # envelope variants exist only for the test year


# ------------------------------------------------------------------ weather --
def generate_weather(seed: int, t_offset: float):
    g = np.random.default_rng(seed)
    doy = np.repeat(np.arange(365), 24).astype(float)
    hod = np.tile(np.arange(24), 365).astype(float)

    # --- clear-sky global horizontal irradiance from simple solar geometry ---
    decl = np.deg2rad(23.45 * np.sin(2.0 * np.pi * (284.0 + doy) / 365.0))
    lat = np.deg2rad(LATITUDE_DEG)
    hour_angle = np.deg2rad(15.0 * (12.0 - (hod + 0.5)))
    sin_elev = np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(hour_angle)
    sin_elev = np.clip(sin_elev, 0.0, None)
    ghi_clear = WEATHER_CONFIG["ghi_clear"] * np.power(sin_elev, 1.15)

    # --- cloudiness: AR(1) at daily scale, small hourly jitter ---
    c = np.zeros(365)
    x = 0.0
    for d in range(365):
        x = WEATHER_CONFIG["cloud_ar"] * x + g.normal(0.0, WEATHER_CONFIG["cloud_sigma"])
        c[d] = x
    c = np.clip(WEATHER_CONFIG["cloud_mean"] + 0.30 * c, 0.18, 1.0)
    cloud = np.repeat(c, 24) + g.normal(0.0, 0.05, N_STEPS)
    cloud = np.clip(cloud, 0.15, 1.0)
    ghi = ghi_clear * cloud

    # --- outdoor dry-bulb: seasonal + diurnal + synoptic AR(1) ---
    t_daily_mean = (
        WEATHER_CONFIG["t_annual_mean"] + t_offset
        - WEATHER_CONFIG["t_annual_amp"] * np.cos(2.0 * np.pi * (doy - 15.0) / 365.0)
    )
    d_amp = WEATHER_CONFIG["diurnal_amp"] * (
        1.0 + 0.30 * np.cos(2.0 * np.pi * (doy - 190.0) / 365.0)
    )
    syn = np.empty(N_STEPS)
    x = 0.0
    for t in range(N_STEPS):
        x = WEATHER_CONFIG["synoptic_ar"] * x + g.normal(0.0, WEATHER_CONFIG["synoptic_sigma"])
        syn[t] = x
    t_out = t_daily_mean + d_amp * np.sin(2.0 * np.pi * (hod - 9.0) / 24.0) + syn

    return t_out.astype(np.float64), ghi.astype(np.float64)


def generate_gains(seed: int, scale: float):
    g = np.random.default_rng(seed)
    day_idx = np.arange(365)
    dow = (day_idx + 2) % 7  # arbitrary fixed weekday phase
    dow = np.repeat(dow, 24)
    hod = np.tile(np.arange(24), 365).astype(float)
    occupied = ((dow < 5) & (hod >= 6.0) & (hod < 22.0)).astype(float)
    q_int = (120.0 + 780.0 * occupied) * scale
    q_int = q_int * (1.0 + g.normal(0.0, 0.05, N_STEPS))
    return np.clip(q_int, 0.0, None), occupied


# ------------------------------------------------------------------- teacher -
def simulate(envelope: str, year: int):
    p = PARAMS[envelope]
    w_seed, t_off, g_scale = YEARS[year]
    t_out, ghi = generate_weather(w_seed, t_off)
    q_int, occupied = generate_gains(SEED + 900 + year, g_scale)

    Cz, Cm, UA, Uiw = p["Cz"], p["Cm"], p["UA_ext"], p["Uiw"]
    A_eff = p["A_eff"]
    # Conductances in W/K (whole-building). heat_flow = conductance * dT.
    G_ow, G_iw = UA, Uiw

    hv = HVAC
    Tz, Tm = 20.0, 19.0  # fixed, deterministic initial condition
    T_zone = np.empty(N_STEPS)
    q_heat = np.empty(N_STEPS)
    q_cool = np.empty(N_STEPS)
    dt = DT_SUB

    for t in range(N_STEPS):
        th_set = hv["T_heat_set_occ"] if occupied[t] else hv["T_heat_set_unocc"]
        tc_set = hv["T_cool_set_occ"] if occupied[t] else hv["T_cool_set_unocc"]
        q_sol_air = A_eff * ghi[t] * 0.60  # 60% of solar gain absorbed at air node
        q_sol_mas = A_eff * ghi[t] * 0.40
        qh_h = qc_h = 0.0
        for _ in range(SUB_PER_HOUR):
            qh = min(hv["K_h"] * max(0.0, th_set - Tz), hv["Q_h_max"])
            qc = min(hv["K_c"] * max(0.0, Tz - tc_set), hv["Q_c_max"])
            dtz = ((Tm - Tz) * G_iw + q_int[t] + q_sol_air + qh - qc) / Cz
            dtm = ((t_out[t] - Tm) * G_ow + (Tz - Tm) * G_iw + q_sol_mas) / Cm
            Tz += dtz * dt
            Tm += dtm * dt
            qh_h += qh
            qc_h += qc
        T_zone[t] = Tz
        q_heat[t] = qh_h / SUB_PER_HOUR  # W, hourly mean delivered heating
        q_cool[t] = qc_h / SUB_PER_HOUR  # W, hourly mean delivered cooling

    # Site energy: heating through a 0.85-efficient heater, cooling through an
    # outdoor-temperature-dependent chiller COP. 1-hour steps, W -> kWh.
    cop = np.maximum(hv["cop_min"], hv["cop_a"] - hv["cop_b"] * (t_out - 20.0))
    e_heat = q_heat / 1000.0 / hv["eta_heat"]
    e_cool = q_cool / 1000.0 / cop

    return dict(
        t_out=t_out, ghi=ghi, q_int=q_int, occupied=occupied.astype(np.float64),
        q_heat=q_heat, q_cool=q_cool, t_zone=T_zone, e_heat=e_heat, e_cool=e_cool,
        T0=np.array([20.0]),
    )


def main():
    out = Path(__file__).resolve().parents[1] / "data"
    out.mkdir(parents=True, exist_ok=True)

    tasks = [(y, "base") for y in YEARS]
    tasks += [(y, v) for y in VARIANT_YEARS for v in PARAMS if v != "base"]

    for year, env in tasks:
        d = simulate(env, year)
        name = f"year{year}_{env}.npz"
        np.savez_compressed(out / name, **d)
        print(
            f"wrote {name}: Tz mean {d['t_zone'].mean():6.2f} C  "
            f"Heat {d['e_heat'].sum():8.1f} kWh  Cool {d['e_cool'].sum():7.1f} kWh  "
            f"Tout[{d['t_out'].min():6.1f},{d['t_out'].max():6.1f}]"
        )

    meta = dict(
        seed=SEED, n_steps=N_STEPS, dt_sub_seconds=DT_SUB, latitude_deg=LATITUDE_DEG,
        params=PARAMS, hvac=HVAC, weather=WEATHER_CONFIG, years={str(k): v for k, v in YEARS.items()},
        variant_years=VARIANT_YEARS,
        splits={"train": "year1_base", "validation": "year2_base", "test": "year3_base"},
        ood_variants=[v for v in PARAMS if v != "base"],
        columns=["t_out", "ghi", "q_int", "occupied", "q_heat", "q_cool", "t_zone", "e_heat", "e_cool"],
        units=dict(t_out="degC", ghi="W/m2", q_int="W", q_heat="W", q_cool="W",
                   t_zone="degC", e_heat="kWh/h", e_cool="kWh/h"),
    )
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print("wrote meta.json")


if __name__ == "__main__":
    main()
