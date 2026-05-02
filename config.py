from datetime import datetime
import os
import fastf1
import streamlit as st


cache_dir = "./cache"
if not os.path.exists(cache_dir):
    os.makedirs(cache_dir)

fastf1.Cache.enable_cache(cache_dir)


# temporadas suportadas
CURRENT_YEAR = datetime.now().year
SUPPORTED_YEARS = list(range(2023, CURRENT_YEAR + 1))

# fonte de dados
DATA_SOURCE_OPTIONS = {
    "Corrida oficial (R)": "R",
    "Previsão com TL": "PRACTICE",
}

# cores oficiais
COMPOUND_COLORS = {
    "SOFT": "#ff2d2d",
    "MEDIUM": "#ffd000",
    "HARD": "#ffffff",
    "INTERMEDIATE": "#43a047",
    "WET": "#1e88e5",
}

# compostos
COMPOUNDS = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"]

# estados do pneu
TYRE_STATE = ["Novo", "Usado"]

# clima
WEATHER_OPTIONS = [
    "Seco",
    "Nublado",
    "Variável",
    "Chuva leve",
    "Chuva forte"
]

# tráfego
TRAFFIC_OPTIONS = [
    "Baixo",
    "Médio",
    "Alto"
]

# modo
MODE_OPTIONS = [
    "FIA Real",
    "Hipotético"
]

# impacto clima (delta pace, delta degradação, variância)
WEATHER_EFFECTS = {
    "Seco": {
        "pace": 0.0,
        "deg": 1.00,
        "var": 1.00
    },
    "Nublado": {
        "pace": 0.15,
        "deg": 0.95,
        "var": 1.05
    },
    "Variável": {
        "pace": 0.60,
        "deg": 1.15,
        "var": 1.25
    },
    "Chuva leve": {
        "pace": 2.50,
        "deg": 0.85,
        "var": 1.60
    },
    "Chuva forte": {
        "pace": 6.00,
        "deg": 0.70,
        "var": 2.20
    }
}

# impacto tráfego
TRAFFIC_EFFECTS = {
    "Baixo": {
        "min": 0.10,
        "max": 0.35
    },
    "Médio": {
        "min": 0.30,
        "max": 0.80
    },
    "Alto": {
        "min": 0.60,
        "max": 1.50
    }
}


def apply_theme():
    st.set_page_config(
        page_title="Estratégia de Pit Stop: Simulador de F1",
        page_icon="🏎️",
        layout="wide"
    )

    st.markdown(
        """
        <style>
        .main {
            background-color: #0e1117;
        }

        section[data-testid="stSidebar"] {
            background: #111827;
        }

        div[data-testid="metric-container"]{
            border-radius:16px;
            padding:15px;
            background: rgba(255,255,255,0.04);
            border:1px solid rgba(255,255,255,.05);
        }

        h1,h2,h3 {
            color:white !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )