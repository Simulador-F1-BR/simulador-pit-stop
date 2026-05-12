from datetime import datetime, timezone

import fastf1
import pandas as pd
import streamlit as st


SESSION_NAME_MATCHERS = {
    "R": ["race"],
    "FP1": ["practice 1", "free practice 1"],
    "FP2": ["practice 2", "free practice 2"],
    "FP3": ["practice 3", "free practice 3"],
}


def _normalize_session_timestamp(value):
    if pd.isna(value):
        return None

    ts = pd.Timestamp(value)

    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")

    return ts


def _matches_session_name(session_name, session_type):
    if pd.isna(session_name):
        return False

    normalized = str(session_name).strip().lower()
    expected = SESSION_NAME_MATCHERS.get(session_type, [])

    return any(token in normalized for token in expected)


def _practice_session_code(session_name):
    for session_code in ("FP1", "FP2", "FP3"):
        if _matches_session_name(session_name, session_code):
            return session_code

    return None


def _get_event_row(schedule: pd.DataFrame, round_number: int):
    rows = schedule[schedule["RoundNumber"] == round_number]

    if rows.empty:
        return None

    return rows.iloc[0]


def _get_available_practice_session_codes_from_row(row):
    codes = []

    for index in range(1, 6):
        session_key = f"Session{index}"

        if session_key not in row.index:
            continue

        code = _practice_session_code(row.get(session_key))

        if code is None:
            continue

        if _session_has_happened(row, code):
            codes.append(code)

    return list(dict.fromkeys(codes))


def _get_schedule_session_date(row, session_type):
    for index in range(1, 6):
        session_key = f"Session{index}"

        if session_key not in row.index:
            continue

        if not _matches_session_name(row.get(session_key), session_type):
            continue

        utc_key = f"Session{index}DateUtc"
        local_key = f"Session{index}Date"

        if utc_key in row.index and pd.notna(row.get(utc_key)):
            return _normalize_session_timestamp(row.get(utc_key))

        if local_key in row.index and pd.notna(row.get(local_key)):
            return _normalize_session_timestamp(row.get(local_key))

    return None


def _session_has_happened(row, session_type):
    session_date = _get_schedule_session_date(row, session_type)

    if session_date is None:
        return False

    return session_date <= pd.Timestamp(datetime.now(timezone.utc))


def _fill_lap_seconds(laps: pd.DataFrame):
    df = laps.copy()

    if "LapSeconds" not in df.columns and "LapTime" in df.columns:
        df["LapSeconds"] = df["LapTime"].dt.total_seconds()

    if "Time" in df.columns:
        derived = df["Time"].diff().dt.total_seconds()

        if len(derived) > 0 and pd.notna(df["Time"].iloc[0]):
            derived.iloc[0] = df["Time"].iloc[0].total_seconds()

        df["LapSeconds"] = df["LapSeconds"].fillna(derived)

    if "LapStartTime" in df.columns and "Time" in df.columns:
        derived_from_window = (
            df["Time"] - df["LapStartTime"]
        ).dt.total_seconds()
        df["LapSeconds"] = df["LapSeconds"].fillna(derived_from_window)

    return df


def _ensure_tyre_life(laps: pd.DataFrame):
    df = laps.copy()

    if "TyreLife" not in df.columns:
        df["TyreLife"] = pd.NA

    if df["TyreLife"].notna().any():
        return df

    if "Stint" in df.columns:
        df["TyreLife"] = df.groupby("Stint").cumcount() + 1

    return df


def _filter_valid_laps(laps: pd.DataFrame):
    df = laps.copy()

    if "LapSeconds" not in df.columns:
        return pd.DataFrame()

    df = df.dropna(subset=["LapSeconds"]).copy()

    if df.empty:
        return pd.DataFrame()

    df = df[
        (df["LapSeconds"] > 40) &
        (df["LapSeconds"] < 300)
    ].copy()

    return df.reset_index(drop=True)


def _extract_fp2_long_runs(laps: pd.DataFrame, min_clean_laps: int = 4):
    df = laps.copy()

    if df.empty:
        return df

    if "Stint" not in df.columns:
        return pd.DataFrame()

    clean_mask = pd.Series(True, index=df.index)

    if "PitInTime" in df.columns:
        clean_mask &= df["PitInTime"].isna()

    if "PitOutTime" in df.columns:
        clean_mask &= df["PitOutTime"].isna()

    valid_stints = (
        df[clean_mask]
        .groupby("Stint")["LapNumber"]
        .count()
    )
    valid_stints = valid_stints[valid_stints >= min_clean_laps].index

    if len(valid_stints) == 0:
        return pd.DataFrame()

    df = df[df["Stint"].isin(valid_stints)].copy()

    if "Compound" in df.columns:
        df = df[df["Compound"].notna()].copy()

    return df.reset_index(drop=True)


def _is_finished_status(status_value):
    if pd.isna(status_value):
        return None

    status = str(status_value).strip().lower()

    if not status:
        return None

    if "finished" in status:
        return True
    
    if "lapped" in status:
        return True

    if status.startswith("+") and "lap" in status:
        return True

    return False


@st.cache_data
def get_available_events(year: int, session_type: str = "R"):
    try:
        schedule = fastf1.get_event_schedule(year)
        schedule = schedule.dropna(subset=["EventName"])

        events = []

        for _, row in schedule.iterrows():
            if session_type == "PRACTICE":
                practice_codes = _get_available_practice_session_codes_from_row(row)

                if not practice_codes:
                    continue
            else:
                if not _session_has_happened(row, session_type):
                    continue

            rnd = int(row["RoundNumber"])
            name = row["EventName"]

            try:
                lookup_session = (
                    practice_codes[0]
                    if session_type == "PRACTICE"
                    else session_type
                )
                fastf1.get_session(year, rnd, lookup_session)
                events.append({
                    "round": rnd,
                    "name": name
                })
            except Exception:
                pass

        return events

    except Exception:
        return []


@st.cache_data
def get_available_practice_sessions(year: int, round_number: int):
    try:
        schedule = fastf1.get_event_schedule(year)
        row = _get_event_row(schedule, round_number)

        if row is None:
            return []

        codes = _get_available_practice_session_codes_from_row(row)
        sessions = []

        for code in codes:
            try:
                fastf1.get_session(year, round_number, code)
                sessions.append({
                    "code": code,
                    "label": code
                })
            except Exception:
                pass

        return sessions

    except Exception:
        return []


@st.cache_resource
def _load_session_cached(year: int, round_number: int, session_type: str = "R"):
    session = fastf1.get_session(year, round_number, session_type)
    session.load(
        laps=True,
        telemetry=False,
        weather=True,
        messages=False
    )

    return session


def load_session(year: int, round_number: int, session_type: str = "R"):
    session = _load_session_cached(year, round_number, session_type)

    # Detecta se o objeto perdeu os dados (acontece após Streamlit hibernar)
    try:
        _ = session.laps
    except Exception:
        # Cache com objeto morto — força recarregamento
        _load_session_cached.clear()
        session = _load_session_cached(year, round_number, session_type)

    return session


def get_drivers(session):
    drivers = []

    for drv in session.drivers:
        try:
            info = session.get_driver(drv)

            code = info["Abbreviation"]
            name = info["FullName"]

            drivers.append({
                "code": code,
                "name": name
            })
        except Exception:
            pass

    drivers = sorted(drivers, key=lambda item: item["name"])

    return drivers


def get_weather(session):
    try:
        weather = session.weather_data.copy()

        if weather.empty:
            return None

        return {
            "air_temp": float(weather["AirTemp"].mean()),
            "track_temp": float(weather["TrackTemp"].mean()),
            "humidity": float(weather["Humidity"].mean()),
            "rainfall": bool(weather["Rainfall"].any())
        }

    except Exception:
        return None


def get_driver_result_info(session, driver_code):
    try:
        results = session.results.copy()

        if results.empty:
            return None

        driver_row = results[
            results["Abbreviation"] == driver_code
        ]

        if driver_row.empty:
            return None

        driver_row = driver_row.iloc[0]

        winner_row = results[
            results["Position"] == 1
        ]

        winner_time = None

        if not winner_row.empty and pd.notna(winner_row.iloc[0].get("Time")):
            winner_time = float(winner_row.iloc[0]["Time"].total_seconds())

        driver_gap = None
        if pd.notna(driver_row.get("Time")):
            driver_gap = float(driver_row["Time"].total_seconds())

        finished = _is_finished_status(driver_row.get("Status"))
        total_time = None

        if finished is True:
            if int(driver_row.get("Position", 0) or 0) == 1:
                total_time = winner_time
            elif winner_time is not None and driver_gap is not None:
                total_time = winner_time + driver_gap

        return {
            "position": driver_row.get("Position"),
            "status": driver_row.get("Status"),
            "finished": finished,
            "total_time": total_time
        }

    except Exception:
        return None


def get_driver_result_time(session, driver_code):
    info = get_driver_result_info(session, driver_code)

    if not info:
        return None

    return info.get("total_time")


def get_driver_laps(session, driver_code, session_type: str = "R"):
    laps = (
        session.laps.pick_drivers(driver_code)
        .sort_values("LapNumber")
        .copy()
    )

    if laps.empty:
        return pd.DataFrame()

    laps = _fill_lap_seconds(laps)
    laps = _filter_valid_laps(laps)

    if laps.empty:
        return pd.DataFrame()

    if session_type != "R":
        laps = _ensure_tyre_life(laps)
        laps = _extract_fp2_long_runs(laps)

        if laps.empty:
            return pd.DataFrame()

    return laps.reset_index(drop=True)
