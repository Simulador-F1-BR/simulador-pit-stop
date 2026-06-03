import json
import os
import time
from datetime import datetime, timezone
 
import fastf1
import pandas as pd
import streamlit as st
 
try:
    from fastf1.exceptions import RateLimitExceededError
except ImportError:
    RateLimitExceededError = Exception
 
DATA_CACHE_DIR = "data_cache"
 
SESSION_NAME_MATCHERS = {
    "R":   ["race"],
    "FP1": ["practice 1", "free practice 1"],
    "FP2": ["practice 2", "free practice 2"],
    "FP3": ["practice 3", "free practice 3"],
}
 
 
# ---------------------------------------------------------------------------
# Helpers de data/schedule
# ---------------------------------------------------------------------------
 
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
    for code in ("FP1", "FP2", "FP3"):
        if _matches_session_name(session_name, code):
            return code
    return None
 
 
def _get_event_row(schedule: pd.DataFrame, round_number: int):
    rows = schedule[schedule["RoundNumber"] == round_number]
    return rows.iloc[0] if not rows.empty else None
 
 
def _get_available_practice_session_codes_from_row(row):
    codes = []
    for i in range(1, 6):
        key = f"Session{i}"
        if key not in row.index:
            continue
        code = _practice_session_code(row.get(key))
        if code and _session_has_happened(row, code):
            codes.append(code)
    return list(dict.fromkeys(codes))
 
 
def _get_schedule_session_date(row, session_type):
    for i in range(1, 6):
        key = f"Session{i}"
        if key not in row.index:
            continue
        if not _matches_session_name(row.get(key), session_type):
            continue
        for date_key in (f"Session{i}DateUtc", f"Session{i}Date"):
            if date_key in row.index and pd.notna(row.get(date_key)):
                return _normalize_session_timestamp(row.get(date_key))
    return None
 
 
def _session_has_happened(row, session_type):
    d = _get_schedule_session_date(row, session_type)
    if d is None:
        return False
    return d <= pd.Timestamp(datetime.now(timezone.utc))
 
 
# ---------------------------------------------------------------------------
# Helpers de laps
# ---------------------------------------------------------------------------
 
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
        dfw = (df["Time"] - df["LapStartTime"]).dt.total_seconds()
        df["LapSeconds"] = df["LapSeconds"].fillna(dfw)
    return df
 
 
def _ensure_tyre_life(laps: pd.DataFrame):
    df = laps.copy()
    if "TyreLife" not in df.columns:
        df["TyreLife"] = pd.NA
    if not df["TyreLife"].notna().any() and "Stint" in df.columns:
        df["TyreLife"] = df.groupby("Stint").cumcount() + 1
    return df
 
 
def _filter_valid_laps(laps: pd.DataFrame):
    df = laps.copy()
    if "LapSeconds" not in df.columns:
        return pd.DataFrame()
    df = df.dropna(subset=["LapSeconds"])
    df = df[(df["LapSeconds"] > 40) & (df["LapSeconds"] < 300)]
    return df.reset_index(drop=True)
 
 
def _extract_fp2_long_runs(laps: pd.DataFrame, min_clean_laps: int = 4):
    df = laps.copy()
    if df.empty or "Stint" not in df.columns:
        return pd.DataFrame()
    mask = pd.Series(True, index=df.index)
    if "PitInTime" in df.columns:
        mask &= df["PitInTime"].isna()
    if "PitOutTime" in df.columns:
        mask &= df["PitOutTime"].isna()
    valid = df[mask].groupby("Stint")["LapNumber"].count()
    valid = valid[valid >= min_clean_laps].index
    if len(valid) == 0:
        return pd.DataFrame()
    df = df[df["Stint"].isin(valid)].copy()
    if "Compound" in df.columns:
        df = df[df["Compound"].notna()].copy()
    return df.reset_index(drop=True)
 
 
def _is_finished_status(status_value):
    if pd.isna(status_value):
        return None
    s = str(status_value).strip().lower()
    if not s:
        return None
    if "finished" in s or "lapped" in s:
        return True
    if s.startswith("+") and "lap" in s:
        return True
    return False
 
 
# ---------------------------------------------------------------------------
# Extração do objeto Session → dados puros
# ---------------------------------------------------------------------------
 
def _extract_from_session(session) -> dict:
    """Extrai tudo do objeto Session como tipos puros. Nunca retorna o objeto."""
    # Verifica _laps interno — a property pública pode lançar DataNotLoadedError
    laps_internal = getattr(session, "_laps", None)
    if laps_internal is None or (hasattr(laps_internal, "empty") and laps_internal.empty):
        raise ValueError("Sessão carregada mas _laps está vazio")
 
    laps_raw = laps_internal.copy()
 
    drivers = []
    for drv in session.drivers:
        try:
            info = session.get_driver(drv)
            drivers.append({"code": info["Abbreviation"], "name": info["FullName"]})
        except Exception:
            pass
    drivers = sorted(drivers, key=lambda d: d["name"])
 
    weather = None
    try:
        w = session.weather_data.copy()
        if not w.empty:
            weather = {
                "air_temp":   float(w["AirTemp"].mean()),
                "track_temp": float(w["TrackTemp"].mean()),
                "humidity":   float(w["Humidity"].mean()),
                "rainfall":   bool(w["Rainfall"].any()),
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
        "laps":       laps_raw,
        "drivers":    drivers,
        "weather":    weather,
        "results":    results_raw,
        "total_laps": total_laps,
    }
 
 
# ---------------------------------------------------------------------------
# Cache em disco (data_cache/) — opcional, para GPs pré-baixados
# ---------------------------------------------------------------------------
 
def _disk_key(year: int, round_number: int, session_type: str) -> str:
    return f"{year}_{round_number}_{session_type}"
 
 
def _load_from_disk(year: int, round_number: int, session_type: str):
    path = os.path.join(DATA_CACHE_DIR, _disk_key(year, round_number, session_type))
    laps_f    = os.path.join(path, "laps.parquet")
    results_f = os.path.join(path, "results.parquet")
    meta_f    = os.path.join(path, "meta.json")
    if not all(os.path.exists(f) for f in [laps_f, results_f, meta_f]):
        return None
    try:
        laps    = pd.read_parquet(laps_f)
        results = pd.read_parquet(results_f)
        with open(meta_f) as f:
            meta = json.load(f)
        return {"laps": laps, "drivers": meta["drivers"],
                "weather": meta["weather"], "results": results,
                "total_laps": meta["total_laps"]}
    except Exception:
        return None
 
 
# ---------------------------------------------------------------------------
# Carregamento via API com retry
# ---------------------------------------------------------------------------
 
def _load_from_api(year: int, round_number: int, session_type: str) -> dict:
    max_attempts = 5
    for attempt in range(max_attempts):
        is_last = attempt == max_attempts - 1
        wait    = 15 * (attempt + 1)   # 15s, 30s, 45s, 60s
        try:
            session = fastf1.get_session(year, round_number, session_type)
            session.load(laps=True, telemetry=False, weather=True, messages=False)
            return _extract_from_session(session)
 
        except RateLimitExceededError:
            if is_last:
                st.error("Limite de requisições da API FastF1. Aguarde alguns minutos e recarregue.")
                st.stop()
            st.warning(f"Rate limit da API. Aguardando {wait}s... (tentativa {attempt + 1}/{max_attempts})")
            time.sleep(wait)
 
        except Exception:
            if is_last:
                st.error("Não foi possível carregar a sessão. Aguarde alguns segundos e recarregue a página.")
                st.stop()
            time.sleep(wait)
 
 
# ---------------------------------------------------------------------------
# Cache em memória — armazena DADOS PUROS, não o objeto Session
# ---------------------------------------------------------------------------
 
@st.cache_data(show_spinner=False, ttl=3600)
def _get_session_data(year: int, round_number: int, session_type: str) -> dict:
    """
    TTL de 1h: se o cache expirar o Streamlit recarrega automaticamente.
    Isso elimina o problema do objeto morto — nunca cacheamos o Session.
    """
    cached = _load_from_disk(year, round_number, session_type)
    if cached is not None:
        return cached
    return _load_from_api(year, round_number, session_type)
 
 
# ---------------------------------------------------------------------------
# API pública — mesmas assinaturas do app.py original
# ---------------------------------------------------------------------------
 
@st.cache_data
def get_available_events(year: int, session_type: str = "R"):
    try:
        schedule = fastf1.get_event_schedule(year)
        schedule = schedule.dropna(subset=["EventName"])
        events = []
        for _, row in schedule.iterrows():
            if session_type == "PRACTICE":
                codes = _get_available_practice_session_codes_from_row(row)
                if not codes:
                    continue
            else:
                if not _session_has_happened(row, session_type):
                    continue
            rnd  = int(row["RoundNumber"])
            name = row["EventName"]
            try:
                lookup = codes[0] if session_type == "PRACTICE" else session_type
                fastf1.get_session(year, rnd, lookup)
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
 
 
def load_session(year: int, round_number: int, session_type: str = "R") -> dict:
    """Retorna dict com dados puros — nunca retorna o objeto Session."""
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
        row = results[results["Abbreviation"] == driver_code]
        if row.empty:
            return None
        row = row.iloc[0]
 
        winner = results[results["Position"] == 1]
        winner_time = None
        if not winner.empty and pd.notna(winner.iloc[0].get("Time")):
            t = winner.iloc[0]["Time"]
            winner_time = float(t.total_seconds() if hasattr(t, "total_seconds") else t)
 
        driver_gap = None
        if pd.notna(row.get("Time")):
            t = row["Time"]
            driver_gap = float(t.total_seconds() if hasattr(t, "total_seconds") else t)
 
        finished   = _is_finished_status(row.get("Status"))
        total_time = None
        if finished is True:
            pos = int(row.get("Position", 0) or 0)
            if pos == 1:
                total_time = winner_time
            elif winner_time is not None and driver_gap is not None:
                total_time = winner_time + driver_gap
 
        return {"position": row.get("Position"), "status": row.get("Status"),
                "finished": finished, "total_time": total_time}
    except Exception:
        return None
 
 
def get_driver_result_time(session: dict, driver_code: str):
    info = get_driver_result_info(session, driver_code)
    return info.get("total_time") if info else None
 
 
def get_driver_laps(session: dict, driver_code: str, session_type: str = "R"):
    laps_raw = session.get("laps", pd.DataFrame())
    if laps_raw is None or laps_raw.empty:
        return pd.DataFrame()
 
    try:
        laps = (
            laps_raw[laps_raw["Driver"] == driver_code]
            .sort_values("LapNumber")
            .copy()
        )
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
 
 
def get_total_laps(session: dict):
    return session.get("total_laps")