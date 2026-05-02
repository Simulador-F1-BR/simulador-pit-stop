import numpy as np

from simulator import STRATEGY_SEPARATOR, simulate_strategy


def run_montecarlo(
    n_runs,
    total_laps,
    strategy,
    models,
    start_state,
    start_age,
    weather,
    traffic,
    sc_chance,
    sc_window,
    pit_loss
):
    samples = []

    for _ in range(n_runs):
        sim = simulate_strategy(
            total_laps=total_laps,
            strategy=tuple(strategy.split(STRATEGY_SEPARATOR)),
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
            samples.append(sim["total_time"])

    if len(samples) == 0:
        return None

    arr = np.array(samples)

    return {
        "mean": float(arr.mean()),
        "std": float(arr.std()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "p5": float(np.percentile(arr, 5)),
        "p95": float(np.percentile(arr, 95))
    }
