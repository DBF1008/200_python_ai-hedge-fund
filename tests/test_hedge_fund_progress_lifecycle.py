"""Route-level tests: each hedge-fund run/backtest starts from clean progress.

These exercise the real ``/hedge-fund/run`` and ``/hedge-fund/backtest`` SSE
endpoints with the heavy graph/backtest work mocked out, asserting that residual
global progress from a previous (possibly interrupted) run never leaks into a new
request -- covering interrupt-then-retry, disconnect-then-recover, and back-to-back
runs.

Skipped automatically when the LangGraph stack the route module imports is not
installed in the current environment.
"""

import json
import types

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.backend.routes.hedge_fund as hf  # noqa: E402
from app.backend.database import get_db  # noqa: E402
from src.utils.progress import progress  # noqa: E402


def _minimal_run_request():
    return {
        "tickers": ["AAPL"],
        "graph_nodes": [
            {"id": "warren_buffett_node01"},
            {"id": "portfolio_manager_node01"},
        ],
        "graph_edges": [
            {
                "id": "e1",
                "source": "warren_buffett_node01",
                "target": "portfolio_manager_node01",
            }
        ],
        # Provide keys inline so the route never touches the DB-backed key service.
        "api_keys": {"OPENAI_API_KEY": "test"},
    }


def _minimal_backtest_request():
    req = _minimal_run_request()
    req.update({"start_date": "2024-01-01", "end_date": "2024-01-05"})
    return req


@pytest.fixture(autouse=True)
def _clean_progress():
    """Keep the shared global progress tracker isolated between tests."""
    progress.update_handlers.clear()
    progress.agent_status.clear()
    yield
    progress.update_handlers.clear()
    progress.agent_status.clear()


@pytest.fixture
def captured():
    return {"run_snapshots": [], "bt_snapshots": []}


@pytest.fixture
def client(monkeypatch, captured):
    test_app = FastAPI()
    test_app.include_router(hf.router)

    def _fake_get_db():
        yield None

    test_app.dependency_overrides[get_db] = _fake_get_db

    # Avoid building/compiling a real LangGraph.
    monkeypatch.setattr(
        hf,
        "create_graph",
        lambda graph_nodes, graph_edges: types.SimpleNamespace(compile=lambda: object()),
    )

    async def _fake_run_graph_async(
        graph,
        portfolio,
        tickers,
        start_date,
        end_date,
        model_name,
        model_provider,
        request=None,
    ):
        # Snapshot the shared tracker at the moment this run actually begins.
        captured["run_snapshots"].append(dict(progress.agent_status))
        # Emit this run's own progress, like the real agents would.
        progress.update_status("warren_buffett_node01", tickers[0], "In progress")
        progress.update_status("warren_buffett_node01", tickers[0], "Done")
        return {
            "messages": [
                types.SimpleNamespace(
                    content=json.dumps({"AAPL": {"action": "hold", "quantity": 0}})
                )
            ],
            "data": {"analyst_signals": {}, "current_prices": {}},
        }

    monkeypatch.setattr(hf, "run_graph_async", _fake_run_graph_async)

    class _FakeBacktestService:
        def __init__(self, **kwargs):
            pass

        async def run_backtest_async(self, progress_callback=None):
            captured["bt_snapshots"].append(dict(progress.agent_status))
            progress.update_status("warren_buffett_node01", "AAPL", "Done")
            return {
                "performance_metrics": {},
                "final_portfolio": {"cash": 1.0, "margin_used": 0.0, "positions": {}},
                "results": [],
            }

    monkeypatch.setattr(hf, "BacktestService", _FakeBacktestService)

    return TestClient(test_app)


def test_run_starts_clean_after_interrupted_run(client, captured):
    # Residue from a previous interrupted run sitting in the shared tracker.
    progress.agent_status.update(
        {
            "warren_buffett_old99": {
                "status": "Done",
                "ticker": "AAPL",
                "analysis": "stale",
            },
            "risk_management_agent_old99": {"status": "Error", "ticker": None},
        }
    )

    resp = client.post("/hedge-fund/run", json=_minimal_run_request())
    assert resp.status_code == 200
    body = resp.text
    assert "event: start" in body
    # Stale agents from the previous run never reached this run's SSE stream.
    assert "old99" not in body

    # The run task observed a clean tracker at start (reset ran before it).
    assert captured["run_snapshots"], "run_graph_async was not invoked"
    assert captured["run_snapshots"][-1] == {}

    # This run's state was cleaned up when the request finished.
    assert progress.agent_status == {}


def test_consecutive_runs_do_not_reuse_state(client, captured):
    r1 = client.post("/hedge-fund/run", json=_minimal_run_request())
    assert r1.status_code == 200
    assert captured["run_snapshots"][0] == {}
    assert progress.agent_status == {}

    r2 = client.post("/hedge-fund/run", json=_minimal_run_request())
    assert r2.status_code == 200
    # Run 2 started clean even though run 1 finished "Done" on the same agent id.
    assert captured["run_snapshots"][1] == {}
    assert progress.agent_status == {}


def test_backtest_starts_clean_after_residue(client, captured):
    progress.agent_status["warren_buffett_old"] = {"status": "Error", "ticker": None}

    resp = client.post("/hedge-fund/backtest", json=_minimal_backtest_request())
    assert resp.status_code == 200
    assert captured["bt_snapshots"], "run_backtest_async was not invoked"
    assert captured["bt_snapshots"][-1] == {}
    assert progress.agent_status == {}
