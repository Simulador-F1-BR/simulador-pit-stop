import random
from statistics import mean, pstdev

from config import WEATHER_EFFECTS, TRAFFIC_EFFECTS


VALID_COMPOUNDS = [
    "SOFT",
    "MEDIUM",
    "HARD",
    "INTERMEDIATE",
    "WET"
]
WET_COMPOUNDS = {"INTERMEDIATE", "WET"}
STRATEGY_SEPARATOR = " -> "


def _is_valid_strategy(strategy, relaxed_rule=False):
    compounds = [compound for compound in strategy if compound]

    if not compounds:
        return False

    unique_compounds = set(compounds)

    if len(compounds) == 1:
        return relaxed_rule or bool(unique_compounds & WET_COMPOUNDS)

    if relaxed_rule:
        return True

    if unique_compounds & WET_COMPOUNDS:
        return True

    return len(unique_compounds) >= 2


def build_strategy_pool(start_compound, models):
    available = [
        compound for compound in models.keys()
        if compound != "GLOBAL"
    ]
    available = [
        compound for compound in available
        if compound in VALID_COMPOUNDS
    ]

    if start_compound not in available:
        available.append(start_compound)

    available = list(dict.fromkeys(available))
    relaxed_rule = len(available) == 1
    strategies = []

    if _is_valid_strategy((start_compound,), relaxed_rule):
        strategies.append((start_compound,))

    for second in available:
        combo = (start_compound, second)

        if _is_valid_strategy(combo, relaxed_rule):
            strategies.append(combo)

    for second in available:
        for third in available:
            combo = (start_compound, second, third)

            if _is_valid_strategy(combo, relaxed_rule):
                strategies.append(combo)

    return list(dict.fromkeys(strategies))


def get_weather_penalty(weather):
    effect = WEATHER_EFFECTS[weather]
    return effect["pace"], effect["deg"], effect["var"]


def get_traffic_penalty(traffic):
    effect = TRAFFIC_EFFECTS[traffic]
    return random.uniform(effect["min"], effect["max"])


def should_have_safety_car(chance):
    return random.uniform(0, 100) <= chance


def build_neutralization_plan(total_laps, chance, window):
    if chance <= 0 or not should_have_safety_car(chance):
        return None

    lower = max(1, min(window[0], total_laps))
    upper = max(lower, min(window[1], total_laps))
    start_lap = random.randint(lower, upper)
    kind = random.choices(
        population=["VSC", "SC"],
        weights=[0.45, 0.55],
        k=1
    )[0]
    duration = random.randint(2, 3) if kind == "VSC" else random.randint(3, 5)
    end_lap = min(total_laps, start_lap + duration - 1)

    return {
        "type": kind,
        "start_lap": start_lap,
        "end_lap": end_lap,
        "laps": set(range(start_lap, end_lap + 1))
    }


def get_neutralization_factor(global_model, plan, lap_number):
    if not plan or lap_number not in plan["laps"]:
        return 1.0

    if plan["type"] == "SC":
        return global_model.get("sc_lap_multiplier", 1.32)

    return global_model.get("vsc_lap_multiplier", 1.14)


def get_pit_discount(global_model, plan, lap_number):
    if not plan or lap_number not in plan["laps"]:
        return 1.0

    if plan["type"] == "SC":
        return global_model.get("sc_pit_factor", 0.58)

    return global_model.get("vsc_pit_factor", 0.72)


def allocate_stints(total_laps, n_stints):
    if n_stints == 2:
        first = int(total_laps * 0.55)
        second = total_laps - first
        return [first, second]

    if n_stints == 3:
        first = int(total_laps * 0.42)
        second = int(total_laps * 0.28)
        third = total_laps - first - second
        return [first, second, third]

    base = total_laps // n_stints
    arr = [base] * n_stints
    arr[-1] += total_laps - sum(arr)
    return arr


def simulate_strategy(
    total_laps,
    strategy,
    models,
    start_state,
    start_age,
    weather,
    traffic,
    sc_chance,
    sc_window,
    base_pit_loss
):
    if "GLOBAL" not in models:
        return None

    global_model = models["GLOBAL"]

    calibration = global_model.get("calibration_factor", 1.0)
    default_fuel_factor = global_model.get("fuel_factor", 0.0)
    pit_in_pen = global_model.get("pit_in_penalty", 3.0)
    pit_out_pen = global_model.get("pit_out_penalty", 15.0)
    pit_cycle = float(base_pit_loss or global_model.get("pit_cycle_loss", 22.0))
    default_sigma = global_model.get("lap_sigma", 0.20)

    weather_pace, weather_deg, weather_var = get_weather_penalty(weather)
    neutralization = build_neutralization_plan(total_laps, sc_chance, sc_window)

    total_time = 0.0
    history = []
    pit_windows = []

    stint_plan = allocate_stints(total_laps, len(strategy))
    lap_counter = 1
    pending_pit_discount = 1.0

    for stint_idx, compound in enumerate(strategy):
        if compound not in models:
            return None

        model = models[compound]
        base_lap = model["base_lap"]
        deg = model["degradation_per_lap"] * weather_deg
        tyre_limit = model["mean_tyre_life"]
        reference_tyre_life = model.get("reference_tyre_life", 1.0)
        fuel_factor = model.get("fuel_factor", default_fuel_factor)
        lap_sigma = model.get("lap_sigma", default_sigma)

        stint_laps = stint_plan[stint_idx]

        if stint_idx == 0:
            tyre_age = start_age if start_state == "Usado" else 0
        else:
            tyre_age = 0

        for local_lap in range(stint_laps):
            tyre_age += 1

            laps_remaining = max(total_laps - lap_counter, 0)
            fuel_penalty = laps_remaining * fuel_factor
            traffic_penalty = get_traffic_penalty(traffic)

            lap_time = (
                base_lap +
                (deg * (tyre_age - reference_tyre_life)) +
                fuel_penalty +
                weather_pace +
                traffic_penalty
            )

            if tyre_age > tyre_limit:
                cliff = tyre_age - tyre_limit
                lap_time += cliff * 0.12

            neutralization_factor = get_neutralization_factor(
                global_model,
                neutralization,
                lap_counter
            )
            lap_time *= neutralization_factor

            lap_time += random.gauss(0, lap_sigma * weather_var)

            if calibration != 1.0:
                lap_time *= calibration

            if (
                local_lap == stint_laps - 1 and
                stint_idx < len(strategy) - 1
            ):
                pending_pit_discount = get_pit_discount(
                    global_model,
                    neutralization,
                    lap_counter
                )
                lap_time += pit_in_pen * pending_pit_discount

            if local_lap == 0 and stint_idx > 0:
                lap_time += pit_out_pen * pending_pit_discount

            total_time += lap_time

            history.append({
                "Lap": lap_counter,
                "Compound": compound,
                "TyreAge": tyre_age,
                "LapTime": lap_time
            })

            lap_counter += 1

        if stint_idx < len(strategy) - 1:
            residual_lane_loss = max(
                pit_cycle - pit_in_pen - pit_out_pen,
                0.0
            )
            total_time += residual_lane_loss * pending_pit_discount
            pit_windows.append(lap_counter - 1)

    return {
        "strategy": STRATEGY_SEPARATOR.join(strategy),
        "pit_windows": pit_windows,
        "total_time": total_time,
        "history": history,
        "had_sc": bool(neutralization),
        "sc_lap": neutralization["start_lap"] if neutralization else None,
        "neutralization_type": neutralization["type"] if neutralization else None,
        "neutralization_window": (
            neutralization["start_lap"],
            neutralization["end_lap"]
        ) if neutralization else None
    }


def rank_strategies(
    total_laps,
    start_compound,
    start_state,
    start_age,
    weather,
    traffic,
    sc_chance,
    sc_window,
    models,
    pit_loss,
    evaluation_runs=9
):
    pool = build_strategy_pool(start_compound, models)
    results = []

    for strategy in pool:
        simulations = []

        for _ in range(max(evaluation_runs, 1)):
            sim = simulate_strategy(
                total_laps=total_laps,
                strategy=strategy,
                models=models,
                start_state=start_state,
                start_age=start_age,
                weather=weather,
                traffic=traffic,
                sc_chance=sc_chance,
                sc_window=sc_window,
                base_pit_loss=pit_loss
            )

            if sim:
                simulations.append(sim)

        if not simulations:
            continue

        mean_time = mean(sim["total_time"] for sim in simulations)
        time_std = pstdev(sim["total_time"] for sim in simulations)
        representative = min(
            simulations,
            key=lambda sim: abs(sim["total_time"] - mean_time)
        )
        representative["total_time"] = mean_time
        representative["time_std"] = time_std
        results.append(representative)

    results.sort(key=lambda result: result["total_time"])

    return results
