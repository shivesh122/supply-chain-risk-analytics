"""
Demand forecasting with additive Holt-Winters (triple exponential smoothing, weekly season).

* Parameters (alpha, beta, gamma) are chosen by grid search on one-step-ahead error.
* Accuracy is measured on a 28-day holdout against a seasonal-naive baseline
  (WAPE = sum|actual - forecast| / sum(actual)).
* The model is then refit on all data to forecast the next 28 days with an 80% interval.
Forecasts use unconstrained demand (units demanded), not units sold, so stockouts
do not bias the forecast downward.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .db import query

SEASON = 7
HORIZON = 28
GRID_ALPHA = (0.05, 0.1, 0.2, 0.35)
GRID_BETA = (0.0, 0.01, 0.05)
GRID_GAMMA = (0.05, 0.15, 0.3)
Z80 = 1.2816


def holt_winters_fit(y: np.ndarray, alpha: float, beta: float, gamma: float, m: int = SEASON):
    """Returns (level, trend, seasonals, one-step fitted values)."""
    n = len(y)
    level = y[:m].mean()
    trend = (y[m : 2 * m].mean() - y[:m].mean()) / m if n >= 2 * m else 0.0
    season = list(y[:m] - level)
    fitted = np.empty(n)
    for t in range(n):
        s = season[t % m]
        fitted[t] = level + trend + s
        prev_level = level
        level = alpha * (y[t] - s) + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
        season[t % m] = gamma * (y[t] - level) + (1 - gamma) * s
    return level, trend, season, fitted


def holt_winters_forecast(level, trend, season, n_obs: int, h: int, m: int = SEASON) -> np.ndarray:
    return np.array([level + (i + 1) * trend + season[(n_obs + i) % m] for i in range(h)])


def best_params(y: np.ndarray):
    best, best_sse = None, np.inf
    for a, b, g in itertools.product(GRID_ALPHA, GRID_BETA, GRID_GAMMA):
        *_, fitted = holt_winters_fit(y, a, b, g)
        sse = float(((y[SEASON:] - fitted[SEASON:]) ** 2).sum())
        if sse < best_sse:
            best, best_sse = (a, b, g), sse
    return best


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    total = np.abs(actual).sum()
    return float(np.abs(actual - forecast).sum() / total) if total else 0.0


def forecast_series(y: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    train, test = y[:-HORIZON], y[-HORIZON:]
    a, b, g = best_params(train)
    lvl, tr, se, _ = holt_winters_fit(train, a, b, g)
    holdout_fc = np.maximum(holt_winters_forecast(lvl, tr, se, len(train), HORIZON), 0)
    naive_fc = np.tile(train[-SEASON:], HORIZON // SEASON + 1)[:HORIZON]

    a, b, g = best_params(y)
    lvl, tr, se, fitted = holt_winters_fit(y, a, b, g)
    resid_sd = float(np.std(y[SEASON:] - fitted[SEASON:]))
    fc = np.maximum(holt_winters_forecast(lvl, tr, se, len(y), HORIZON), 0)
    width = Z80 * resid_sd * np.sqrt(1 + np.arange(HORIZON) * 0.05)
    future = pd.date_range(dates[-1] + pd.Timedelta(days=1), periods=HORIZON, freq="D")

    return {
        "params": {"alpha": a, "beta": b, "gamma": g},
        "holdout_wape": round(wape(test, holdout_fc), 4),
        "naive_wape": round(wape(test, naive_fc), 4),
        "history": [{"date": d.strftime("%Y-%m-%d"), "actual": int(v)} for d, v in zip(dates[-120:], y[-120:])],
        "holdout": [{"date": d.strftime("%Y-%m-%d"), "forecast": round(float(v), 1)} for d, v in zip(dates[-HORIZON:], holdout_fc)],
        "forecast": [
            {"date": d.strftime("%Y-%m-%d"), "forecast": round(float(v), 1), "lower": round(float(max(v - w, 0)), 1), "upper": round(float(v + w), 1)}
            for d, v, w in zip(future, fc, width)
        ],
        "next_28d_total": int(round(fc.sum())),
    }


def forecast_all_products() -> tuple[list[dict], dict]:
    df = query(
        """
        SELECT p.product_id, p.sku, p.product_name, p.category, d.full_date, SUM(f.units_demanded) AS demand
        FROM fact_sales f
        JOIN dim_product p ON p.product_key = f.product_key
        JOIN dim_date d    ON d.date_key = f.date_key
        GROUP BY p.product_id, p.sku, p.product_name, p.category, d.full_date
        ORDER BY p.product_id, d.full_date
        """
    )
    df["full_date"] = pd.to_datetime(df["full_date"])
    results = []
    for (pid, sku, name, cat), g in df.groupby(["product_id", "sku", "product_name", "category"], sort=True):
        r = forecast_series(g["demand"].to_numpy(dtype=float), pd.DatetimeIndex(g["full_date"]))
        results.append({"product_id": pid, "sku": sku, "product_name": name, "category": cat, **r})

    w_model = np.mean([r["holdout_wape"] for r in results])
    w_naive = np.mean([r["naive_wape"] for r in results])
    summary = {
        "method": "Holt-Winters additive (weekly seasonality), grid-searched per SKU",
        "horizon_days": HORIZON,
        "avg_wape": round(float(w_model), 4),
        "avg_naive_wape": round(float(w_naive), 4),
        "forecast_accuracy_pct": round(100 * (1 - float(w_model)), 1),
        "improvement_vs_naive_pct": round(100 * (w_naive - w_model) / w_naive, 1) if w_naive else 0.0,
    }
    return results, summary
