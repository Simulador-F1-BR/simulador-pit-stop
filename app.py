import pandas as pd
import plotly.express as px
import streamlit as st
import base64
import os
import fastf1

cache_dir = os.path.join(os.getcwd(), "cache")
fastf1.Cache.enable_cache(cache_dir)

GP_TRANSLATIONS = {
    "Bahrain Grand Prix": "GP do Bahrein 🇧🇭",
    "Saudi Arabian Grand Prix": "GP da Arábia Saudita 🇸🇦",
    "Australian Grand Prix": "GP da Austrália 🇦🇺",
    "Azerbaijan Grand Prix": "GP do Azerbaijão 🇦🇿",
    "Miami Grand Prix": "GP de Miami 🇺🇸",
    "Emilia Romagna Grand Prix": "GP da Emilia-Romagna 🇮🇹",
    "Monaco Grand Prix": "GP de Mônaco 🇲🇨",
    "Spanish Grand Prix": "GP da Espanha 🇪🇸",
    "Canadian Grand Prix": "GP do Canadá 🇨🇦",
    "Austrian Grand Prix": "GP da Áustria 🇦🇹",
    "British Grand Prix": "GP da Grã-Bretanha 🇬🇧",
    "Hungarian Grand Prix": "GP da Hungria 🇭🇺",
    "Belgian Grand Prix": "GP da Bélgica 🇧🇪",
    "Dutch Grand Prix": "GP da Holanda 🇳🇱",
    "Italian Grand Prix": "GP da Itália 🇮🇹",
    "Singapore Grand Prix": "GP de Singapura 🇸🇬",
    "Japanese Grand Prix": "GP do Japão 🇯🇵",
    "Qatar Grand Prix": "GP do Catar 🇶🇦",
    "United States Grand Prix": "GP dos Estados Unidos 🇺🇸",
    "Mexico City Grand Prix": "GP da Cidade do México 🇲🇽",
    "São Paulo Grand Prix": "GP de São Paulo 🇧🇷",
    "Las Vegas Grand Prix": "GP de Las Vegas 🇺🇸",
    "Abu Dhabi Grand Prix": "GP de Abu Dhabi 🇦🇪",
    "Chinese Grand Prix": "GP da China 🇨🇳"
}

from analytics import (
    calculate_compound_models,
    calculate_real_pit_loss,
    summarize_driver
)
from config import (
    COMPOUND_COLORS,
    COMPOUNDS,
    DATA_SOURCE_OPTIONS,
    MODE_OPTIONS,
    SUPPORTED_YEARS,
    TRAFFIC_OPTIONS,
    TYRE_STATE,
    WEATHER_OPTIONS,
    apply_theme
)
from data_loader import (
    get_available_events,
    get_available_practice_sessions,
    get_driver_laps,
    get_driver_result_info,
    get_driver_result_time,
    get_drivers,
    get_weather,
    load_session
)
from montecarlo import run_montecarlo
from simulator import rank_strategies


def format_seconds(total_seconds):
    if total_seconds is None:
        return "-"

    minutes = int(total_seconds // 60)
    seconds = total_seconds - (minutes * 60)

    return f"{minutes}m {seconds:04.1f}s"


def format_delta(delta_seconds):
    if delta_seconds is None:
        return "-"

    sign = "+" if delta_seconds >= 0 else "-"
    return f"{sign}{abs(delta_seconds):.1f}s"


def format_pit_windows(pit_windows):
    if not pit_windows:
        return "Sem parada"

    return " / ".join(f"V{int(lap)}" for lap in pit_windows)


def get_default_compound(preview_laps, preview_strategy, source_mode):
    if (
        source_mode == "R" and
        preview_strategy and
        preview_strategy.get("stint_compounds")
    ):
        candidate = preview_strategy["stint_compounds"][0]

        if candidate in COMPOUNDS:
            return candidate

    if not preview_laps.empty and "Compound" in preview_laps.columns:
        compounds = preview_laps["Compound"].dropna()

        if not compounds.empty:
            candidate = compounds.value_counts().index[0]

            if candidate in COMPOUNDS:
                return candidate

    return COMPOUNDS[0]


apply_theme()

st.markdown(
    """
    <style>
    .subtitulo {
        text-align: center;
        font-size: 18px;
        color: white;
        margin-bottom: 30px;
        font-family: 'Poppins', sans-serif;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown(
    '<h1 style="text-align:center; font-size:60px; color:#e10600;">🏎️ Estratégia de Pit Stop: Simulador de F1</h1>',
    unsafe_allow_html=True
)
st.markdown(
    '<p class="subtitulo">Analise a corrida real ou preveja a prova a partir de um treino livre</p>',
    unsafe_allow_html=True
)

preview_laps = pd.DataFrame()
preview_summary = None
preview_strategy = None
preview_track_status = None
result_info = None
source_mode = "R"
selected_session_code = "R"
selected_session_label = "R"
projected_total_laps = None
manual_pit_loss = None

with st.sidebar:
    st.header("⚙️ Configuração")

    source_label = st.selectbox(
        "📊 Fonte dos dados",
        list(DATA_SOURCE_OPTIONS.keys())
    )
    source_mode = DATA_SOURCE_OPTIONS[source_label]

    year = st.selectbox(
        "📅 Temporada",
        SUPPORTED_YEARS,
        index=len(SUPPORTED_YEARS) - 1
    )

    events = get_available_events(year, session_type=source_mode)

    if len(events) == 0:
        if source_mode == "PRACTICE":
            st.error("Nenhum GP com treino livre disponível para previsão nesta temporada.")
        else:
            st.error("Nenhum GP de corrida disponível.")
        st.stop()

    event_names = [event["name"] for event in events]
    selected_event = st.selectbox(
    "📍 GP", 
    event_names,
    format_func=lambda x: GP_TRANSLATIONS.get(x, x) 
    )
    
    def get_base64_of_bin_file(bin_file):
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()

    GP_BACKGROUNDS = {
        "Bahrain Grand Prix": "assets/bahrein.jpeg",
        "São Paulo Grand Prix": "assets/interlagos.jpeg",
        "Italian Grand Prix": "assets/monza.png",
        "Las Vegas Grand Prix": "assets/las vegas.jpeg",
        "Saudi Arabian Grand Prix": "assets/arabia_saudita.png",
        "Australian Grand Prix": "assets/australia.jpeg",
        "Azerbaijan Grand Prix": "assets/azerbaijao.jpeg",
        "Miami Grand Prix": "assets/miami.jpeg",
        "Emilia Romagna Grand Prix": "assets/imola.jpeg",
        "Monaco Grand Prix": "assets/monaco.jpeg",
        "Spanish Grand Prix": "assets/espanha.jpeg",
        "Canadian Grand Prix": "assets/canada.jpeg",
        "Austrian Grand Prix": "assets/austria.jpeg",
        "British Grand Prix": "assets/silverstone.jpeg",
        "Hungarian Grand Prix": "assets/hungria.jpeg",
        "Belgian Grand Prix": "assets/spa.jpeg",
        "Dutch Grand Prix": "assets/zandvoort.jpeg",
        "Singapore Grand Prix": "assets/singapura.jpeg",
        "Japanese Grand Prix": "assets/suzuka.jpeg",
        "Qatar Grand Prix": "assets/catar.jpeg",
        "United States Grand Prix": "assets/austin.jpeg",
        "Mexico City Grand Prix": "assets/mexico.jpeg",
        "Abu Dhabi Grand Prix": "assets/abu_dhabi.jpeg",
        "Chinese Grand Prix": "assets/china.jpeg"
    }

    caminho_imagem = GP_BACKGROUNDS.get(selected_event, "assets/default_f1.jpeg")

    try:
        img_base64 = get_base64_of_bin_file(caminho_imagem)
        bg_image_css = f"linear-gradient(rgba(14, 17, 23, 0.85), rgba(14, 17, 23, 0.88)), url('data:image/jpeg;base64,{img_base64}')"
    except FileNotFoundError:
        bg_image_css = "none"

    page_bg_img = f"""
    <style>
    .stApp {{
        background-image: {bg_image_css};
        background-size: cover;
        background-position: center center;
        background-attachment: fixed;
    }}

    .main {{
        background-color: transparent !important;
    }}

    h1, h2, h3, p, span, div[data-testid="metric-container"] label {{
        text-shadow: 1px 1px 4px rgba(0, 0, 0, 0.8);
    }}
    .stApp {{
    background-image: {bg_image_css};
    background-size: cover;
    background-position: center top; 
    background-attachment: fixed;
    }}

    .main {{
        background-color: transparent !important;
    }}

    .block-container {{
        padding-top: 1rem !important;
        margin-top: 0 !important;
    }}

    header[data-testid="stHeader"] {{
        background-color: transparent !important;
    }}

    h1, h2, h3, p, span, div[data-testid="metric-container"] label {{
        text-shadow: 1px 1px 4px rgba(0, 0, 0, 0.8);
    }}
    </style>
    """

    st.markdown(page_bg_img, unsafe_allow_html=True)

    selected_round = next(
        event["round"]
        for event in events
        if event["name"] == selected_event
    )

    if source_mode == "PRACTICE":
        practice_sessions = get_available_practice_sessions(year, selected_round)

        if len(practice_sessions) == 0:
            st.error(
                "Este GP não possui treino livre disponível para previsão. "
                "Escolha outro evento ou outra sessão base."
            )
            st.stop()

        practice_labels = [session["label"] for session in practice_sessions]
        selected_session_label = st.selectbox(
            "⏱️ Sessão base da previsão",
            practice_labels
        )
        selected_session_code = next(
            session["code"]
            for session in practice_sessions
            if session["label"] == selected_session_label
        )
    else:
        selected_session_code = "R"
        selected_session_label = "R"

    with st.spinner(f"Carregando sessão {selected_session_label}..."):
        session = load_session(
            year,
            selected_round,
            session_type=selected_session_code
        )

    drivers = get_drivers(session)

    if len(drivers) == 0:
        st.error("Nenhum piloto encontrado.")
        st.stop()

    driver_names = [
        f'{driver["name"]} ({driver["code"]})'
        for driver in drivers
    ]

    selected_driver_label = st.selectbox("🪖 Piloto", driver_names)
    selected_driver = next(
        driver["code"]
        for driver in drivers
        if f'{driver["name"]} ({driver["code"]})' == selected_driver_label
    )

    preview_laps = get_driver_laps(
        session,
        selected_driver,
        session_type=selected_session_code
    )

    if not preview_laps.empty:
        preview_summary = summarize_driver(preview_laps)

        if source_mode == "R" and preview_summary:
            preview_strategy = preview_summary.get("actual_strategy")
            preview_track_status = preview_summary.get("track_status")

    if source_mode == "R":
        result_info = get_driver_result_info(session, selected_driver)

    default_start_compound = get_default_compound(
        preview_laps,
        preview_strategy,
        source_mode
    )
    default_start_state_index = 0
    default_start_age = 0

    if source_mode == "R" and preview_strategy:
        if preview_strategy.get("start_tyre_age", 0) > 0:
            default_start_state_index = 1
            default_start_age = preview_strategy["start_tyre_age"]

    st.divider()
    st.subheader("🛞 Pneu Inicial")

    start_compound = st.selectbox(
        "Composto",
        COMPOUNDS,
        index=COMPOUNDS.index(default_start_compound)
    )

    start_state = st.radio(
        "Estado",
        TYRE_STATE,
        horizontal=True,
        index=default_start_state_index
    )

    start_age = 0

    if start_state == "Usado":
        start_age = st.slider(
            "Idade do pneu (voltas)",
            1,
            20,
            max(default_start_age, 1)
        )

    st.divider()
    st.subheader("🌤️ Cenário")

    mode = st.radio(
        "Modo",
        MODE_OPTIONS,
        horizontal=True
    )

    real_weather = get_weather(session)
    default_weather = "Seco"

    if real_weather:
        if real_weather["rainfall"]:
            default_weather = "Chuva leve"
        elif real_weather["track_temp"] < 30:
            default_weather = "Nublado"

    if mode == "FIA Real":
        weather = default_weather
        st.info(f"Clima detectado: {weather}")
    else:
        weather = st.selectbox(
            "Clima",
            WEATHER_OPTIONS,
            index=WEATHER_OPTIONS.index(default_weather)
        )

    traffic = st.selectbox(
        "🚦 Tráfego",
        TRAFFIC_OPTIONS,
        index=1
    )

    if source_mode == "PRACTICE":
        st.divider()
        st.subheader("🔮 Previsão da Corrida")

        projected_total_laps = st.number_input(
            "Voltas previstas da corrida",
            min_value=20,
            max_value=90,
            value=57,
            step=1
        )
        manual_pit_loss = st.number_input(
            "Perda estimada de pit (s)",
            min_value=10.0,
            max_value=40.0,
            value=22.0,
            step=0.5
        )
        st.caption(
            f"Usando {selected_session_label} como base preditiva para os long runs."
        )

    st.divider()
    st.subheader("🚥 Neutralização")

    if (
        source_mode == "R" and
        mode == "FIA Real" and
        preview_track_status
    ):
        real_window = preview_track_status["neutralization_window"] or (15, 45)
        sc_chance = 100 if preview_track_status["has_neutralization"] else 0
        sc_window = real_window

        if preview_track_status["has_neutralization"]:
            st.info(
                "SC/VSC real detectado entre "
                f"V{real_window[0]} e V{real_window[1]}."
            )
        else:
            st.info("Nenhuma neutralização detectada nesta corrida.")
    else:
        sc_chance = st.slider("Chance de SC/VSC (%)", 0, 100, 30)
        sc_window = st.slider("Janela provável", 1, 80, (15, 45))

    st.divider()
    st.subheader("🎲 Monte Carlo")

    mc_runs = st.slider(
        "Simulações",
        50,
        1000,
        150,
        step=50
    )

    run = st.button(
        "🚀 SIMULAR ESTRATÉGIA",
        use_container_width=True
    )

if not run:
    st.stop()

with st.spinner("Processando estratégia matemática..."):
    laps = preview_laps.copy()

    if laps.empty or len(laps) < 5:
        if source_mode == "PRACTICE":
            st.warning(
                "Piloto sem long runs suficientes no treino livre selecionado para modelar a corrida."
            )
        else:
            st.warning("Piloto sem voltas válidas suficientes nesta corrida.")
        st.stop()

    models = calculate_compound_models(laps)

    if len(models) == 0:
        st.warning("Sem dados suficientes para modelar a degradação.")
        st.stop()

    available_compounds = [
        compound for compound in models.keys()
        if compound in COMPOUNDS
    ]

    if start_compound not in available_compounds:
        st.warning(
            f"{start_compound} não possui dados suficientes para este piloto nesse GP."
        )
        st.info(
            f"Compostos disponíveis: {', '.join(available_compounds)}"
        )
        st.stop()

    if len(available_compounds) == 1:
        st.warning(
            "Apenas um composto possui dados suficientes para este piloto. "
            "O simulador vai liberar estratégias fallback com esse composto "
            "para evitar a quebra da análise."
        )

    summary = summarize_driver(laps)

    if source_mode == "PRACTICE":
        total_laps = int(projected_total_laps)
        pit_loss = float(manual_pit_loss)
    else:
        total_laps = int(session.total_laps)
        pit_loss = calculate_real_pit_loss(laps)

    ranking = rank_strategies(
        total_laps=total_laps,
        start_compound=start_compound,
        start_state=start_state,
        start_age=start_age,
        weather=weather,
        traffic=traffic,
        sc_chance=sc_chance,
        sc_window=sc_window,
        models=models,
        pit_loss=pit_loss
    )

    if len(ranking) == 0:
        st.error("Não foi possível gerar estratégias.")
        st.stop()

    best = ranking[0]

    mc = run_montecarlo(
        n_runs=mc_runs,
        total_laps=total_laps,
        strategy=best["strategy"],
        models=models,
        start_state=start_state,
        start_age=start_age,
        weather=weather,
        traffic=traffic,
        sc_chance=sc_chance,
        sc_window=sc_window,
        pit_loss=pit_loss
    )

    if mc is None:
        st.error("Erro na simulação Monte Carlo.")
        st.stop()

    actual_strategy = None
    track_status = None
    actual_total_time = None
    actual_mc = None
    can_compare_real = False

    if source_mode == "R" and summary:
        actual_strategy = summary.get("actual_strategy")
        track_status = summary.get("track_status")

        if not result_info or result_info.get("finished") is not False:
            actual_total_time = get_driver_result_time(session, selected_driver)

            if actual_total_time is None:
                actual_total_time = summary.get("driver_total_time")

        can_compare_real = (
            actual_strategy is not None and
            actual_total_time is not None and
            (not result_info or result_info.get("finished") is not False)
        )

        if can_compare_real:
            actual_start_age = actual_strategy.get("start_tyre_age", 0)
            actual_start_state = "Usado" if actual_start_age > 0 else "Novo"

            actual_mc = run_montecarlo(
                n_runs=max(80, mc_runs // 2),
                total_laps=total_laps,
                strategy=actual_strategy["strategy"],
                models=models,
                start_state=actual_start_state,
                start_age=actual_start_age,
                weather=weather,
                traffic=traffic,
                sc_chance=sc_chance,
                sc_window=sc_window,
                pit_loss=pit_loss
            )


tempo_total = mc["mean"]
pit_text = format_pit_windows(best["pit_windows"])

delta_best_vs_real = (
    tempo_total - actual_total_time
    if actual_total_time is not None else None
)
delta_actual_strategy = (
    actual_mc["mean"] - actual_total_time
    if actual_mc and actual_total_time is not None else None
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown("### 🏆 Melhor Estratégia")
    st.success(best["strategy"])

with col2:
    st.metric("🔧 Janela de pit stop", pit_text)

with col3:
    st.metric("⏱️ Tempo estimado", format_seconds(tempo_total))

with col4:
    st.metric("🎯 Confiança", f"+/- {mc['std']:.1f}s")

st.divider()

comp1, comp2, comp3, comp4 = st.columns(4)

if source_mode == "R":
    with comp1:
        st.metric("🏁 Tempo real do piloto", format_seconds(actual_total_time))

    with comp2:
        st.metric("⚖️ Delta melhor x real", format_delta(delta_best_vs_real))

    with comp3:
        st.metric("⏱️ Perda de tempo no pit stop", f"{pit_loss:.1f}s")

    with comp4:
        if track_status:
            
            flags = []
            if track_status['sc_laps'] > 0:
                flags.append(f"{track_status['sc_laps']} SC")
            if track_status['vsc_laps'] > 0:
                flags.append(f"{track_status['vsc_laps']} VSC")
            if track_status['red_laps'] > 0:
                flags.append(f"{track_status['red_laps']} RED")
            
            texto_bandeiras = "/".join(flags) if flags else "Nenhuma"
            
            st.metric("🚩 Bandeiras", texto_bandeiras)
        else:
            st.metric("🚩 Bandeiras", "-")
else:
    with comp1:
        st.metric("⏱️ Sessão base", selected_session_label)

    with comp2:
        st.metric("🔁 Voltas previstas", str(total_laps))

    with comp3:
        st.metric("⏱️ Pit loss usado", f"{pit_loss:.1f}s")

    with comp4:
        st.metric("🛞 Compostos no treino", ", ".join(available_compounds))

if source_mode == "R" and result_info and result_info.get("finished") is False:
    st.warning(
        "⚠️ O piloto não finalizou a corrida. "
        f"Status FIA: {result_info.get('status')}. "
        "As voltas ainda podem ser usadas para simular, mas o tempo oficial "
        "final e o Delta não são comparáveis."
    )

if source_mode == "R" and track_status and track_status.get("has_red_flag"):
    st.warning(
        "🚩 Esta corrida teve bandeira vermelha. O tempo real oficial da FIA "
        "inclui minutos com o carro parado, então o Delta contra o tempo "
        "simulado pode parecer artificialmente maior."
    )

st.divider()

left, right = st.columns(2)

if source_mode == "R":
    with left:
        st.subheader("🎬 Corrida Real")

        if actual_strategy:
            st.info(actual_strategy["strategy"])
            st.metric(
                "🔧 Paradas reais",
                format_pit_windows(actual_strategy["pit_windows"])
            )
        else:
            st.warning("Não foi possível identificar a estratégia real.")

        if actual_mc and delta_actual_strategy is not None:
            st.metric(
                "Erro simulando a estratégia real",
                format_delta(delta_actual_strategy)
            )

    with right:
        st.subheader("🧠 Leitura do Modelo")

        if summary:
            st.metric("🔥 Melhor volta real", format_seconds(summary["best_lap"]))
            st.metric("📊 Média de volta", format_seconds(summary["avg_lap"]))

        if best.get("neutralization_type"):
            st.metric(
                "🚥 Neutralização simulada",
                (
                    f"{best['neutralization_type']} "
                    f"V{best['neutralization_window'][0]}-V{best['neutralization_window'][1]}"
                )
            )
        else:
            st.metric("🚥 Neutralização simulada", "Nenhuma")
else:
    with left:
        st.subheader("📋 Base do Treino")
        st.metric("Sessão escolhida", selected_session_label)
        st.metric("Long runs válidos", str(len(laps)))

        if "Stint" in laps.columns:
            st.metric("Stints válidos", str(laps["Stint"].nunique()))

        st.metric("Compostos observados", ", ".join(available_compounds))

    with right:
        st.subheader("🧠 Leitura do Modelo")

        if summary:
            st.metric("🔥 Melhor volta do treino", format_seconds(summary["best_lap"]))
            st.metric("📊 Média do treino", format_seconds(summary["avg_lap"]))

        if best.get("neutralization_type"):
            st.metric(
                "🚥 Neutralização simulada",
                (
                    f"{best['neutralization_type']} "
                    f"V{best['neutralization_window'][0]}-V{best['neutralization_window'][1]}"
                )
            )
        else:
            st.metric("🚥 Neutralização simulada", "Nenhuma")

st.divider()

weather_data = get_weather(session)

if weather_data:
    st.subheader("🌍 Contexto FIA")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("🌡️ Ar", f"{weather_data['air_temp']:.1f} °C")

    with c2:
        st.metric("🛣️ Pista", f"{weather_data['track_temp']:.1f} °C")

    with c3:
        st.metric("💧 Umidade", f"{weather_data['humidity']:.1f}%")

    with c4:
        st.metric("🌧️ Chuva", "Sim" if weather_data["rainfall"] else "Não")

    if source_mode == "R" and track_status:
        t1, t2, t3, t4, t5 = st.columns(5)

        with t1:
            st.metric("🟩 Voltas verdes", track_status["green_laps"])

        with t2:
            st.metric("🟨 Voltas amarelas", track_status["yellow_laps"])

        with t3:
            st.metric("🟧 Voltas VSC", track_status["vsc_laps"])

        with t4:
            st.metric("🟧 Voltas SC", track_status["sc_laps"])

        with t5:
            st.metric("🟥 Bandeiras vermelhas", track_status["red_laps"])

st.divider()

st.subheader("🏅 Ranking de Estratégias")

top5 = ranking[:5]
rank_rows = [
    {
        "Estratégia": item["strategy"],
        "Tempo (s)": item["total_time"]
    }
    for item in top5
]

if can_compare_real and actual_mc and actual_strategy:
    rank_rows.append({
        "Estratégia": f"{actual_strategy['strategy']} (real)",
        "Tempo (s)": actual_mc["mean"]
    })

df_rank = pd.DataFrame(rank_rows)

fig_rank = px.bar(
    df_rank,
    x="Estratégia",
    y="Tempo (s)",
    template="plotly_dark",
    text_auto=".1f"
)

st.plotly_chart(fig_rank, use_container_width=True)

st.subheader("📈 Volta a volta: Melhor Simulação")

hist = pd.DataFrame(best["history"])

fig_best = px.line(
    hist,
    x="Lap",
    y="LapTime",
    color="Compound",
    template="plotly_dark",
    color_discrete_map=COMPOUND_COLORS
)

st.plotly_chart(fig_best, use_container_width=True)

if source_mode == "R" and can_compare_real:
    st.subheader("🔍 Comparação Volta a Volta")

    real_hist = laps[["LapNumber", "LapSeconds"]].copy()
    real_hist = real_hist.rename(
        columns={
            "LapNumber": "Lap",
            "LapSeconds": "Tempo real"
        }
    )

    sim_hist = hist[["Lap", "LapTime"]].rename(
        columns={"LapTime": "Tempo simulado"}
    )

    comparison = real_hist.merge(sim_hist, on="Lap", how="inner")
    comparison_long = comparison.melt(
        id_vars="Lap",
        value_vars=["Tempo real", "Tempo simulado"],
        var_name="Série",
        value_name="LapTime"
    )

    fig_compare = px.line(
        comparison_long,
        x="Lap",
        y="LapTime",
        color="Série",
        template="plotly_dark"
    )

    st.plotly_chart(fig_compare, use_container_width=True)
elif source_mode == "PRACTICE":
    st.subheader("📊 Dados Base do Treino")

    practice_hist = laps.copy()

    if "Compound" not in practice_hist.columns:
        practice_hist["Compound"] = "UNKNOWN"

    fig_practice = px.line(
        practice_hist,
        x="LapNumber",
        y="LapSeconds",
        color="Compound",
        template="plotly_dark",
        color_discrete_map=COMPOUND_COLORS
    )

    st.plotly_chart(fig_practice, use_container_width=True)
