import numpy as np
import pandas as pd


VALID_COMPOUNDS = [
    "SOFT",
    "MEDIUM",
    "HARD",
    "INTERMEDIATE",
    "WET"
]
TRACK_STATUS_SAFETY_CAR = {"4"}
TRACK_STATUS_VSC = {"6", "7"}
TRACK_STATUS_RED = {"5"}


def _safe_seconds(td):
    if pd.isna(td):
        return None

    try:
        return float(td.total_seconds())
    except Exception:
        return None


def _status_codes(track_status):
    if pd.isna(track_status):
        return set()

    raw = "".join(ch for ch in str(track_status) if ch.isdigit())

    return set(raw) if raw else set()


def _track_state(track_status):
    codes = _status_codes(track_status)

    if not codes:
        return "GREEN"

    if codes & TRACK_STATUS_RED:
        return "RED"

    if codes & TRACK_STATUS_SAFETY_CAR:
        return "SC"

    if codes & TRACK_STATUS_VSC:
        return "VSC"

    if codes == {"1"}:
        return "GREEN"

    return "YELLOW"


def _prepare_laps(laps: pd.DataFrame):
    if laps.empty:
        return laps.copy()

    df = laps.copy()

    if "LapSeconds" not in df.columns and "LapTime" in df.columns:
        df["LapSeconds"] = df["LapTime"].apply(_safe_seconds)

    df = df.dropna(subset=["LapSeconds"]).copy()

    if "LapNumber" not in df.columns:
        df["LapNumber"] = np.arange(1, len(df) + 1)

    df["LapNumber"] = df["LapNumber"].astype(int)
    df["TrackState"] = (
        df["TrackStatus"].apply(_track_state)
        if "TrackStatus" in df.columns else "GREEN"
    )
    df["IsPitLap"] = False

    if "PitInTime" in df.columns:
        df["IsPitLap"] = df["IsPitLap"] | df["PitInTime"].notna()

    if "PitOutTime" in df.columns:
        df["IsPitLap"] = df["IsPitLap"] | df["PitOutTime"].notna()

    df = df[
        (df["LapSeconds"] > 40) &
        (df["LapSeconds"] < 300)
    ].copy()

    return df.reset_index(drop=True)


def _clean_green_laps(laps: pd.DataFrame):
    if laps.empty:
        return laps.copy()

    clean = laps[
        (laps["TrackState"] == "GREEN") &
        (~laps["IsPitLap"])
    ].copy()

    if clean.empty:
        clean = laps[~laps["IsPitLap"]].copy()

    if clean.empty:
        clean = laps.copy()

    return clean


def _estimate_driver_total_time(laps: pd.DataFrame):
    if laps.empty:
        return None

    return float(laps["LapSeconds"].sum())


def _estimate_clean_lap(laps: pd.DataFrame):
    if laps.empty:
        return None

    clean = _clean_green_laps(laps)

    if clean.empty:
        return None

    return float(clean["LapSeconds"].median())


def _fit_compound_model(
    compound_laps: pd.DataFrame,
    total_laps: int,
    fuel_factor: float = 0.0
):
    comp = compound_laps.dropna(
        subset=["TyreLife", "LapSeconds", "LapNumber"]
    ).copy()

    if len(comp) < 5:
        return None

    tyre_age = comp["TyreLife"].astype(float).values
    laps_remaining = np.clip(
        total_laps - comp["LapNumber"].astype(float).values,
        a_min=0,
        a_max=None
    )
    lap_seconds = comp["LapSeconds"].astype(float).values
    adjusted_laps = lap_seconds - (fuel_factor * laps_remaining)

    if comp["TyreLife"].nunique() > 1:
        deg_slope = float(np.polyfit(tyre_age, adjusted_laps, 1)[0])
    else:
        deg_slope = 0.03

    deg_slope = float(np.clip(deg_slope, 0.002, 0.18))
    reference_tyre_life = float(np.median(tyre_age))
    normalized = adjusted_laps - (
        deg_slope * (tyre_age - reference_tyre_life)
    )
    base_lap = float(np.median(normalized))

    predictions = (
        base_lap +
        (deg_slope * (tyre_age - reference_tyre_life)) +
        (fuel_factor * laps_remaining)
    )
    residuals = lap_seconds - predictions

    sigma = (
        float(residuals.std(ddof=1))
        if len(residuals) > 1 else 0.35
    )

    return {
        "base_lap": base_lap,
        "reference_tyre_life": reference_tyre_life,
        "degradation_per_lap": deg_slope,
        "fuel_factor": max(float(fuel_factor), 0.0),
        "mean_tyre_life": float(comp["TyreLife"].mean()),
        "sample_size": int(len(comp)),
        "lap_sigma": float(np.clip(sigma, 0.12, 2.5))
    }


def _predict_clean_lap(row, model, total_laps, fallback_clean_lap):
    if model is None:
        return fallback_clean_lap

    lap_number = float(row.get("LapNumber", 0))
    raw_tyre_age = row.get("TyreLife", 0)
    tyre_age = float(raw_tyre_age) if pd.notna(raw_tyre_age) else 0.0
    laps_remaining = max(total_laps - lap_number, 0)
    reference_tyre_life = model.get("reference_tyre_life", 1.0)

    return (
        model["base_lap"] +
        (
            model["degradation_per_lap"] *
            (tyre_age - reference_tyre_life)
        ) +
        (model.get("fuel_factor", 0.0) * laps_remaining)
    )


def _estimate_global_fuel_factor(
    clean_laps: pd.DataFrame,
    models,
    total_laps: int
):
    if clean_laps.empty:
        return 0.045

    residual_frames = []

    for compound in VALID_COMPOUNDS:
        if compound not in models:
            continue

        model = models[compound]
        comp = clean_laps[clean_laps["Compound"] == compound].copy()

        if comp.empty:
            continue

        tyre_age = comp["TyreLife"].astype(float)
        laps_remaining = (
            total_laps - comp["LapNumber"].astype(float)
        ).clip(lower=0)

        base_without_fuel = (
            model["base_lap"] +
            (
                model["degradation_per_lap"] *
                (tyre_age - model.get("reference_tyre_life", 1.0))
            )
        )

        residual_frames.append(pd.DataFrame({
            "Residual": comp["LapSeconds"].astype(float) - base_without_fuel,
            "LapsRemaining": laps_remaining
        }))

    if not residual_frames:
        return 0.045

    residuals = pd.concat(residual_frames, ignore_index=True)
    residuals = residuals.dropna()

    if len(residuals) < 8 or residuals["LapsRemaining"].nunique() <= 1:
        return 0.045

    slope = float(np.polyfit(
        residuals["LapsRemaining"],
        residuals["Residual"],
        1
    )[0])

    return float(np.clip(slope, 0.015, 0.09))


def _estimate_pit_components(laps: pd.DataFrame, models, total_laps):
    default_in = 3.0
    default_out = 15.0
    default_cycle = 22.0

    if laps.empty:
        return default_in, default_out, default_cycle

    if "PitInTime" not in laps.columns or "PitOutTime" not in laps.columns:
        return default_in, default_out, default_cycle

    clean_baseline = _estimate_clean_lap(laps)

    if clean_baseline is None:
        return default_in, default_out, default_cycle

    pit_in_penalties = []
    pit_out_penalties = []
    cycle_penalties = []

    df = laps.sort_values("LapNumber").reset_index(drop=True)

    for _, row in df[df["PitInTime"].notna()].iterrows():
        compound = row.get("Compound")
        model = models.get(compound)
        predicted_in = _predict_clean_lap(
            row=row,
            model=model,
            total_laps=total_laps,
            fallback_clean_lap=clean_baseline
        )
        pit_in_pen = max(float(row["LapSeconds"] - predicted_in), 0.0)
        pit_in_penalties.append(pit_in_pen)

        next_out = df[
            (df["LapNumber"] == row["LapNumber"] + 1) &
            (df["PitOutTime"].notna())
        ]

        if next_out.empty:
            continue

        out_row = next_out.iloc[0]
        out_model = models.get(out_row.get("Compound"))
        predicted_out = _predict_clean_lap(
            row=out_row,
            model=out_model,
            total_laps=total_laps,
            fallback_clean_lap=clean_baseline
        )
        pit_out_pen = max(
            float(out_row["LapSeconds"] - predicted_out),
            0.0
        )

        pit_out_penalties.append(pit_out_pen)
        cycle_penalties.append(pit_in_pen + pit_out_pen)

    pit_in_pen = (
        float(np.median(pit_in_penalties))
        if pit_in_penalties else default_in
    )
    pit_out_pen = (
        float(np.median(pit_out_penalties))
        if pit_out_penalties else default_out
    )

    if cycle_penalties:
        pit_cycle = float(np.median(cycle_penalties))
    else:
        pit_cycle = pit_in_pen + pit_out_pen

    pit_cycle = max(pit_cycle, pit_in_pen + pit_out_pen)

    return pit_in_pen, pit_out_pen, pit_cycle


def extract_actual_strategy(laps: pd.DataFrame):
    if laps.empty:
        return None

    df = _prepare_laps(laps)

    if df.empty or "Compound" not in df.columns:
        return None

    df = df.sort_values("LapNumber").reset_index(drop=True)

    strategy = []
    pit_windows = []
    stints = []

    current_compound = None
    current_start = None
    last_lap = None
    previous_tyre_life = None
    start_tyre_age = None

    for _, row in df.iterrows():
        compound = row.get("Compound")
        lap_number = int(row["LapNumber"])
        tyre_life = row.get("TyreLife")
        is_new_stint = False

        if pd.isna(compound):
            compound = current_compound

        if current_compound is None:
            is_new_stint = True
        elif pd.notna(row.get("PitOutTime")):
            is_new_stint = True
        elif (
            previous_tyre_life is not None and
            pd.notna(tyre_life) and
            float(tyre_life) < float(previous_tyre_life)
        ):
            is_new_stint = True
        elif compound != current_compound:
            is_new_stint = True

        if is_new_stint:
            if current_compound is not None and current_start is not None:
                stints.append({
                    "compound": current_compound,
                    "start_lap": current_start,
                    "end_lap": last_lap,
                    "laps": (last_lap - current_start + 1)
                })

            current_compound = compound
            current_start = lap_number

            if compound:
                strategy.append(compound)

            if start_tyre_age is None and pd.notna(tyre_life):
                start_tyre_age = max(int(float(tyre_life)) - 1, 0)

        if pd.notna(row.get("PitInTime")):
            pit_windows.append(lap_number)

        last_lap = lap_number
        previous_tyre_life = tyre_life

    if current_compound is not None and current_start is not None and last_lap is not None:
        stints.append({
            "compound": current_compound,
            "start_lap": current_start,
            "end_lap": last_lap,
            "laps": (last_lap - current_start + 1)
        })

    unique_strategy = [compound for compound in strategy if compound]

    return {
        "strategy": " -> ".join(unique_strategy),
        "stint_compounds": tuple(unique_strategy),
        "pit_windows": sorted(set(pit_windows)),
        "stop_count": len(set(pit_windows)),
        "stints": stints,
        "start_tyre_age": int(start_tyre_age or 0),
        "compounds_used": sorted(set(unique_strategy))
    }


def summarize_track_status(laps: pd.DataFrame):
    if laps.empty:
        return {
            "green_laps": 0,
            "yellow_laps": 0,
            "vsc_laps": 0,
            "sc_laps": 0,
            "red_laps": 0,
            "neutralization_window": None,
            "has_neutralization": False,
            "has_red_flag": False
        }

    df = _prepare_laps(laps)

    states = {
        "GREEN": [],
        "YELLOW": [],
        "VSC": [],
        "SC": [],
        "RED": []
    }

    for _, row in df.iterrows():
        state = row["TrackState"]
        states.setdefault(state, []).append(int(row["LapNumber"]))

    neutralization_laps = sorted(states["VSC"] + states["SC"])

    return {
        "green_laps": len(states["GREEN"]),
        "yellow_laps": len(states["YELLOW"]),
        "vsc_laps": len(states["VSC"]),
        "sc_laps": len(states["SC"]),
        "red_laps": len(states["RED"]),
        "neutralization_window": (
            min(neutralization_laps),
            max(neutralization_laps)
        ) if neutralization_laps else None,
        "has_neutralization": bool(neutralization_laps),
        "has_red_flag": bool(states["RED"])
    }


def calculate_compound_models(laps: pd.DataFrame):
    if laps.empty:
        return {}

    df = _prepare_laps(laps)

    if df.empty:
        return {}

    clean_baseline = _estimate_clean_lap(df)
    driver_time = _estimate_driver_total_time(df)

    if clean_baseline is None:
        clean_baseline = float(df["LapSeconds"].median())

    total_laps = int(df["LapNumber"].max())
    clean_green = _clean_green_laps(df)
    provisional_models = {}

    for compound in VALID_COMPOUNDS:
        comp = clean_green[clean_green["Compound"] == compound].copy()
        model = _fit_compound_model(comp, total_laps, fuel_factor=0.0)

        if model is not None:
            provisional_models[compound] = model

    if not provisional_models:
        return {}

    fuel_factor = _estimate_global_fuel_factor(
        clean_laps=clean_green,
        models=provisional_models,
        total_laps=total_laps
    )

    models = {}

    for compound in VALID_COMPOUNDS:
        comp = clean_green[clean_green["Compound"] == compound].copy()
        model = _fit_compound_model(
            comp,
            total_laps,
            fuel_factor=fuel_factor
        )

        if model is not None:
            models[compound] = model

    compound_models = list(models.values())
    lap_sigma = float(np.average([
        model["lap_sigma"] for model in compound_models
    ]))

    pit_in_pen, pit_out_pen, pit_cycle = _estimate_pit_components(
        laps=df,
        models=models,
        total_laps=total_laps
    )

    models["GLOBAL"] = {
        "avg_clean_lap": float(clean_baseline),
        "driver_total_time": float(driver_time),
        "calibration_factor": 1.0,
        "pit_in_penalty": float(pit_in_pen),
        "pit_out_penalty": float(pit_out_pen),
        "pit_cycle_loss": float(pit_cycle),
        "fuel_factor": max(float(fuel_factor), 0.0),
        "lap_sigma": max(float(lap_sigma), 0.12),
        "sc_lap_multiplier": 1.32,
        "vsc_lap_multiplier": 1.14,
        "sc_pit_factor": 0.58,
        "vsc_pit_factor": 0.72
    }

    return models


def calculate_real_pit_loss(laps: pd.DataFrame):
    models = calculate_compound_models(laps)

    if "GLOBAL" in models:
        return models["GLOBAL"]["pit_cycle_loss"]

    return 22.0


def get_available_compounds(laps: pd.DataFrame):
    if laps.empty:
        return []

    compounds = (
        laps["Compound"]
        .dropna()
        .unique()
        .tolist()
    )

    compounds = [
        compound for compound in compounds
        if compound in VALID_COMPOUNDS
    ]

    return sorted(compounds)


def summarize_driver(laps: pd.DataFrame):
    if laps.empty:
        return None

    df = _prepare_laps(laps)
    models = calculate_compound_models(df)
    global_data = models.get("GLOBAL", {})

    return {
        "avg_lap": float(df["LapSeconds"].mean()),
        "best_lap": float(df["LapSeconds"].min()),
        "laps": int(len(df)),
        "avg_position": float(df["Position"].mean())
        if "Position" in df.columns else None,
        "driver_total_time": global_data.get("driver_total_time"),
        "calibration_factor": global_data.get("calibration_factor"),
        "pit_cycle_loss": global_data.get("pit_cycle_loss"),
        "actual_strategy": extract_actual_strategy(df),
        "track_status": summarize_track_status(df)
    }
