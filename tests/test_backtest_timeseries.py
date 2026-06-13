"""Unit tests for the pure ``BacktestService._build_timeseries`` staticmethod.

These exercise only the in-memory assembly of the plottable backtest
time-series (date stringification, ``return_pct``, benchmark merge incl.
``None`` gaps, and exposure passthrough with day-0 defaults). No network or
graph execution is involved.

The heavy import chain (pandas / langgraph / langchain_core, pulled in via
``app.backend.services.backtest_service`` -> ``graph`` -> ``src.main``) is
guarded with ``importorskip`` so this module skips cleanly in minimal
environments and runs fully under the project's dependency set.
"""

import pytest

pytest.importorskip("pandas")
pytest.importorskip("requests")
pytest.importorskip("langchain_core")
pytest.importorskip("langgraph")

import pandas as pd  # noqa: E402

from app.backend.services.backtest_service import BacktestService  # noqa: E402


def test_build_timeseries_basic():
    initial_capital = 1000.0

    # Mirrors the real shape: the seed day-0 point has only Date + value (no
    # exposures); subsequent points carry full exposure fields.
    portfolio_values = [
        {"Date": pd.Timestamp("2024-01-01"), "Portfolio Value": 1000.0},
        {
            "Date": pd.Timestamp("2024-01-02"),
            "Portfolio Value": 1100.0,
            "Long Exposure": 800.0,
            "Short Exposure": 200.0,
            "Gross Exposure": 1000.0,
            "Net Exposure": 600.0,
            "Long/Short Ratio": 4.0,
        },
        {
            "Date": pd.Timestamp("2024-01-03"),
            "Portfolio Value": 900.0,
            "Long Exposure": 0.0,
            "Short Exposure": 0.0,
            "Gross Exposure": 0.0,
            "Net Exposure": 0.0,
            "Long/Short Ratio": None,
        },
    ]

    benchmark_by_date = {
        "2024-01-01": 1000.0,  # normalized to base -> 0% return
        "2024-01-02": None,    # explicit gap (no quote) -> nullable passthrough
        # "2024-01-03" intentionally absent -> .get(...) yields None
    }

    series = BacktestService._build_timeseries(
        portfolio_values, benchmark_by_date, initial_capital
    )

    assert len(series) == 3

    # --- Day 0 (seed point): no exposures -> defaults; benchmark present ---
    p0 = series[0]
    assert p0["date"] == "2024-01-01"
    assert p0["portfolio_value"] == 1000.0
    assert p0["return_pct"] == pytest.approx(0.0)
    assert p0["benchmark_value"] == 1000.0
    assert p0["benchmark_return_pct"] == pytest.approx(0.0)
    assert p0["long_exposure"] == 0.0
    assert p0["short_exposure"] == 0.0
    assert p0["gross_exposure"] == 0.0
    assert p0["net_exposure"] == 0.0
    assert p0["long_short_ratio"] is None

    # --- Day 1: +10% equity; benchmark gap (None); full exposures ---
    p1 = series[1]
    assert p1["date"] == "2024-01-02"
    assert p1["return_pct"] == pytest.approx(10.0)
    assert p1["benchmark_value"] is None
    assert p1["benchmark_return_pct"] is None
    assert p1["long_exposure"] == 800.0
    assert p1["short_exposure"] == 200.0
    assert p1["gross_exposure"] == 1000.0
    assert p1["net_exposure"] == 600.0
    assert p1["long_short_ratio"] == 4.0

    # --- Day 2: -10% equity; benchmark key missing -> None ---
    p2 = series[2]
    assert p2["date"] == "2024-01-03"
    assert p2["return_pct"] == pytest.approx(-10.0)
    assert p2["benchmark_value"] is None
    assert p2["benchmark_return_pct"] is None
    assert p2["long_short_ratio"] is None


def test_build_timeseries_empty():
    assert BacktestService._build_timeseries([], {}, 1000.0) == []
