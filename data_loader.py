import time
from datetime import datetime, timezone

import fastf1
import pandas as pd
import streamlit as st

try:
    from fastf1.exceptions import RateLimitExceededError
except ImportError:
    RateLimitExceededError = Exception


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
        derived_from_window = (df["Time"] - df["LapStartTime"]).dt.total_seconds()
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
    df = df[(df["LapSeconds"] > 40) & (df["LapSeconds"] < 300)].copy()
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
        df[clean_mask].groupby("Stint")["LapNumber"].count()
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


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    keep = [
        "LapNumber", "LapSeconds", "Compound", "TyreLife", "Stint",
        "PitInTime", "PitOutTime", "TrackStatus", "Position",
        "Driver", "Team",
    ]
    existing = [c for c in keep if c in df.columns]
    out = df[existing].copy()

    for col in ["PitInTime", "PitOutTime"]:
        if col in out.columns:
            try:
                out[col] = out[col].apply(
                    lambda v: v.total_seconds() if pd.notna(v) and hasattr(v, "total_seconds") else v
                )
            except Exception:
                out[col] = pd.NA

    return out


def _extract_from_session(session) -> dict:
    laps_internal = session._laps
    if laps_internal is None or laps_internal.empty:
        raise ValueError("session._laps está vazio após session.load()")

    laps_raw = laps_internal.copy()

    drivers = []
    for drv in session.drivers:
        try:
            info = session.get_driver(drv)
            drivers.append({
                "code": info["Abbreviation"],
                "name": info["FullName"],
            })
        except Exception:
            pass
    drivers = sorted(drivers, key=lambda d: d["name"])

    weather = None
    try:
        w = session.weather_data.copy()
        if not w.empty:
            weather = {
                "air_temp": float(w["AirTemp"].mean()),
                "track_temp": float(w["TrackTemp"].mean()),
                "humidity": float(w["Humidity"].mean()),
                "rainfall": bool(w["Rainfall"].any()),
            }
    except Exception:
        pass

    results_raw = pd.DataFrame()
    try:
        results_raw = session.results.copy()
    except Exception:
        pass

    total_laps = None
    try:
        total_laps = int(session.total_laps)
    except Exception:
        pass

    return {
        "laps": laps_raw,
        "drivers": drivers,
        "weather": weather,
        "results": results_raw,
        "total_laps": total_laps,
    }


def _load_session_raw(year: int, round_number: int, session_type: str):
    max_attempts = 4
    for attempt in range(max_attempts):
        is_last = attempt == max_attempts - 1
        wait = 20 * (attempt + 1)

        try:
            session = fastf1.get_session(year, round_number, session_type)
            session.load(laps=True, telemetry=False, weather=True, messages=False)
            return _extract_from_session(session)

        except RateLimitExceededError:
            if is_last:
                st.error(
                    "Limite de requisições da API FastF1 atingido. "
                    "Aguarde alguns minutos e recarregue a página."
                )
                st.stop()
            st.warning(f"Rate limit da API. Aguardando {wait}s... (tentativa {attempt + 1}/{max_attempts})")
            time.sleep(wait)

        except Exception:
            if is_last:
                st.error(
                    "Não foi possível carregar os dados da sessão após várias tentativas. "
                    "Recarregue a página. Se o erro persistir, aguarde alguns minutos."
                )
                st.stop()
            time.sleep(wait)

@st.cache_data(show_spinner=False)
def _get_session_data(year: int, round_number: int, session_type: str) -> dict:
    return _load_session_raw(year, round_number, session_type)


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
                    practice_codes[0] if session_type == "PRACTICE" else session_type
                )
                fastf1.get_session(year, rnd, lookup_session)
                events.append({"round": rnd, "name": name})
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
                sessions.append({"code": code, "label": code})
            except Exception:
                pass
        return sessions
    except Exception:
        return []


def load_session(year: int, round_number: int, session_type: str = "R"):
    return _get_session_data(year, round_number, session_type)


def get_drivers(session: dict):
    return session.get("drivers", [])


def get_weather(session: dict):
    return session.get("weather")


def get_driver_result_info(session: dict, driver_code: str):
    try:
        results = session.get("results", pd.DataFrame())
        if results is None or results.empty:
            return None

        driver_row = results[results["Abbreviation"] == driver_code]
        if driver_row.empty:
            return None
        driver_row = driver_row.iloc[0]

        winner_row = results[results["Position"] == 1]
        winner_time = None
        if not winner_row.empty and pd.notna(winner_row.iloc[0].get("Time")):
            t = winner_row.iloc[0]["Time"]
            winner_time = float(t.total_seconds()) if hasattr(t, "total_seconds") else float(t)

        driver_gap = None
        if pd.notna(driver_row.get("Time")):
            t = driver_row["Time"]
            driver_gap = float(t.total_seconds()) if hasattr(t, "total_seconds") else float(t)

        finished = _is_finished_status(driver_row.get("Status"))
        total_time = None
        if finished is True:
            pos = int(driver_row.get("Position", 0) or 0)
            if pos == 1:
                total_time = winner_time
            elif winner_time is not None and driver_gap is not None:
                total_time = winner_time + driver_gap

        return {
            "position": driver_row.get("Position"),
            "status": driver_row.get("Status"),
            "finished": finished,
            "total_time": total_time,
        }
    except Exception:
        return None


def get_driver_result_time(session: dict, driver_code: str):
    info = get_driver_result_info(session, driver_code)
    if not info:
        return None
    return info.get("total_time")


def get_driver_laps(session: dict, driver_code: str, session_type: str = "R"):
    laps_raw = session.get("laps", pd.DataFrame())

    if laps_raw is None or laps_raw.empty:
        return pd.DataFrame()

    try:
        laps = laps_raw[laps_raw["Driver"] == driver_code].sort_values("LapNumber").copy()
    except Exception:
        return pd.DataFrame()

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


def get_total_laps(session: dict) -> int | None:
    return session.get("total_laps")