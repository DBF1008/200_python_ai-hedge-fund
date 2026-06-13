"""
Regression tests for per-run progress isolation.

These tests verify that concurrent hedge-fund / backtest runs never
cross-contaminate their progress events, even when agents execute
interleaved in a shared thread pool.
"""

import asyncio
import contextvars
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest

from src.utils.progress import (
    AgentProgress,
    ProgressTracker,
    _current_run_id,
    generate_run_id,
    get_current_run_id,
    progress,
    set_current_run_id,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Collector:
    """Thread-safe event collector that mimics an SSE handler."""

    def __init__(self, label: str):
        self.label = label
        self.events: list[tuple] = []
        self._lock = threading.Lock()

    def handler(self, agent_name, ticker, status, analysis, timestamp):
        with self._lock:
            self.events.append((agent_name, ticker, status))

    @property
    def count(self) -> int:
        with self._lock:
            return len(self.events)


# ---------------------------------------------------------------------------
# Unit tests – ProgressTracker registry
# ---------------------------------------------------------------------------

class TestProgressTrackerRegistry:
    """Verify the ProgressTracker registry creates, retrieves, and removes
    per-run trackers correctly."""

    def test_create_and_get_tracker(self):
        tracker = ProgressTracker()
        run_id = "run-1"
        t = tracker.create_tracker(run_id)
        assert isinstance(t, AgentProgress)
        assert tracker.get_tracker(run_id) is t

    def test_get_tracker_returns_default_for_unknown_id(self):
        tracker = ProgressTracker()
        t = tracker.get_tracker("nonexistent")
        # Should return the default tracker (same object for every unknown id)
        assert t is tracker.get_tracker("also-nonexistent")

    def test_remove_tracker(self):
        tracker = ProgressTracker()
        run_id = "run-1"
        tracker.create_tracker(run_id)
        tracker.remove_tracker(run_id)
        # After removal, should fall back to default
        assert tracker.get_tracker(run_id) is tracker._default

    def test_multiple_trackers_are_independent(self):
        tracker = ProgressTracker()
        t1 = tracker.create_tracker("a")
        t2 = tracker.create_tracker("b")
        assert t1 is not t2
        assert t1 is not tracker._default
        assert t2 is not tracker._default


# ---------------------------------------------------------------------------
# Unit tests – ContextVar routing
# ---------------------------------------------------------------------------

class TestContextVarRouting:
    """Verify that update_status routes to the correct per-run tracker
    based on the ContextVar."""

    def test_update_routes_to_correct_tracker(self):
        tracker = ProgressTracker()
        run_a = "run-a"
        run_b = "run-b"
        ta = tracker.create_tracker(run_a)
        tb = tracker.create_tracker(run_b)
        ca = _Collector("a")
        cb = _Collector("b")
        ta.register_handler(ca.handler)
        tb.register_handler(cb.handler)

        # Emit on run_a
        set_current_run_id(run_a)
        tracker.update_status("agent_1", "AAPL", "working")

        # Emit on run_b
        set_current_run_id(run_b)
        tracker.update_status("agent_2", "MSFT", "working")

        assert ca.count == 1
        assert cb.count == 1
        assert ca.events[0] == ("agent_1", "AAPL", "working")
        assert cb.events[0] == ("agent_2", "MSFT", "working")

        # Clean up
        set_current_run_id(None)
        tracker.remove_tracker(run_a)
        tracker.remove_tracker(run_b)

    def test_no_run_id_uses_default_tracker(self):
        tracker = ProgressTracker()
        c = _Collector("default")
        tracker._default.register_handler(c.handler)

        # No ContextVar set
        set_current_run_id(None)
        tracker.update_status("agent_x", None, "init")

        assert c.count == 1
        tracker._default.unregister_handler(c.handler)


# ---------------------------------------------------------------------------
# Unit tests – generate_run_id
# ---------------------------------------------------------------------------

class TestGenerateRunId:
    def test_unique(self):
        ids = {generate_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_is_string(self):
        assert isinstance(generate_run_id(), str)


# ---------------------------------------------------------------------------
# Concurrency tests – thread-pool isolation
# ---------------------------------------------------------------------------

class TestThreadPoolIsolation:
    """Simulate the production scenario where two runs execute their agents
    concurrently in a shared thread pool.  Events must never leak across
    runs."""

    def test_concurrent_runs_isolated_in_thread_pool(self):
        """Two runs execute agents interleaved in a thread pool.
        Each run's collector must only see its own events."""

        tracker = ProgressTracker()

        run_a = "run-a"
        run_b = "run-b"
        ta = tracker.create_tracker(run_a)
        tb = tracker.create_tracker(run_b)

        ca = _Collector("a")
        cb = _Collector("b")
        ta.register_handler(ca.handler)
        tb.register_handler(cb.handler)

        barrier = threading.Barrier(2)

        def simulate_agent(run_id: str, agent_name: str, tickers: list[str]):
            """Simulates an agent running in a thread-pool worker."""
            # Set the ContextVar for this run (mirrors what
            # ``create_agent_function`` does in production).
            set_current_run_id(run_id)
            for i, ticker in enumerate(tickers):
                # Synchronise with the other thread to maximise interleaving
                barrier.wait(timeout=5)
                tracker.update_status(agent_name, ticker, f"step {i}")
            # Final status
            barrier.wait(timeout=5)
            tracker.update_status(agent_name, None, "Done")

        tickers_a = ["AAPL", "GOOG", "AMZN"]
        tickers_b = ["MSFT", "TSLA", "NVDA"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            fut_a = pool.submit(simulate_agent, run_a, "agent_alpha", tickers_a)
            fut_b = pool.submit(simulate_agent, run_b, "agent_beta", tickers_b)
            fut_a.result(timeout=10)
            fut_b.result(timeout=10)

        # Each collector should have exactly len(tickers) + 1 (final Done) events
        expected_a = len(tickers_a) + 1
        expected_b = len(tickers_b) + 1
        assert ca.count == expected_a, (
            f"Collector A expected {expected_a} events, got {ca.count}: {ca.events}"
        )
        assert cb.count == expected_b, (
            f"Collector B expected {expected_b} events, got {cb.count}: {cb.events}"
        )

        # Verify no cross-contamination: collector A should never see
        # agent_beta events, and vice versa.
        for agent_name, ticker, status in ca.events:
            assert agent_name == "agent_alpha", (
                f"Collector A received event from wrong agent: {agent_name}"
            )
        for agent_name, ticker, status in cb.events:
            assert agent_name == "agent_beta", (
                f"Collector B received event from wrong agent: {agent_name}"
            )

        # Verify tickers are correct for each run
        a_tickers = {t for (_, t, _) in ca.events if t is not None}
        b_tickers = {t for (_, t, _) in cb.events if t is not None}
        assert a_tickers == set(tickers_a)
        assert b_tickers == set(tickers_b)

        # Clean up
        tracker.remove_tracker(run_a)
        tracker.remove_tracker(run_b)

    def test_many_concurrent_runs_isolated(self):
        """Stress test with many concurrent runs."""
        tracker = ProgressTracker()
        num_runs = 10
        tickers_per_run = 5

        collectors: dict[str, _Collector] = {}
        run_ids: list[str] = []

        for i in range(num_runs):
            run_id = generate_run_id()
            run_ids.append(run_id)
            t = tracker.create_tracker(run_id)
            c = _Collector(f"run-{i}")
            t.register_handler(c.handler)
            collectors[run_id] = c

        barrier = threading.Barrier(num_runs)

        def simulate_run(run_id: str, idx: int):
            set_current_run_id(run_id)
            agent_name = f"agent_{idx}"
            for j in range(tickers_per_run):
                barrier.wait(timeout=10)
                tracker.update_status(agent_name, f"TK{idx}{j}", f"step {j}")
            barrier.wait(timeout=10)
            tracker.update_status(agent_name, None, "Done")

        with ThreadPoolExecutor(max_workers=num_runs) as pool:
            futures = [
                pool.submit(simulate_run, rid, i)
                for i, rid in enumerate(run_ids)
            ]
            for f in futures:
                f.result(timeout=30)

        # Each collector should have exactly tickers_per_run + 1 events
        for rid, c in collectors.items():
            expected = tickers_per_run + 1
            assert c.count == expected, (
                f"Collector for {rid} expected {expected} events, got {c.count}"
            )

        # Verify no cross-contamination
        for i, rid in enumerate(run_ids):
            c = collectors[rid]
            expected_agent = f"agent_{i}"
            for agent_name, ticker, status in c.events:
                assert agent_name == expected_agent, (
                    f"Run {i} collector saw event from {agent_name}"
                )
            if ticker is not None:
                expected_tickers = {f"TK{i}{j}" for j in range(tickers_per_run)}
                actual_tickers = {t for (_, t, _) in c.events if t is not None}
                assert actual_tickers == expected_tickers

        # Clean up
        for rid in run_ids:
            tracker.remove_tracker(rid)


# ---------------------------------------------------------------------------
# Concurrency tests – asyncio isolation
# ---------------------------------------------------------------------------

class TestAsyncioIsolation:
    """Verify isolation when runs are launched as asyncio tasks (the actual
    production pattern used by the SSE endpoints)."""

    @pytest.mark.asyncio
    async def test_concurrent_async_tasks_isolated(self):
        """Two asyncio tasks run concurrently, each setting a different
        run_id.  Their collectors must not cross-contaminate."""

        tracker = ProgressTracker()

        run_a = generate_run_id()
        run_b = generate_run_id()
        ta = tracker.create_tracker(run_a)
        tb = tracker.create_tracker(run_b)

        ca = _Collector("a")
        cb = _Collector("b")
        ta.register_handler(ca.handler)
        tb.register_handler(cb.handler)

        async def simulate_async_run(run_id: str, agent_name: str, steps: int):
            set_current_run_id(run_id)
            for i in range(steps):
                tracker.update_status(agent_name, f"T{i}", f"step {i}")
                await asyncio.sleep(0)  # yield control
            tracker.update_status(agent_name, None, "Done")

        # Launch both tasks concurrently
        await asyncio.gather(
            simulate_async_run(run_a, "agent_a", 10),
            simulate_async_run(run_b, "agent_b", 10),
        )

        # Each collector should have 11 events (10 steps + Done)
        assert ca.count == 11
        assert cb.count == 11

        # No cross-contamination
        for agent_name, _, _ in ca.events:
            assert agent_name == "agent_a"
        for agent_name, _, _ in cb.events:
            assert agent_name == "agent_b"

        tracker.remove_tracker(run_a)
        tracker.remove_tracker(run_b)

    @pytest.mark.asyncio
    async def test_async_with_executor_isolation(self):
        """Simulates the production pattern: an asyncio task runs sync
        agent code via run_in_executor with context propagation."""
        import contextvars

        tracker = ProgressTracker()

        run_a = generate_run_id()
        run_b = generate_run_id()
        ta = tracker.create_tracker(run_a)
        tb = tracker.create_tracker(run_b)

        ca = _Collector("a")
        cb = _Collector("b")
        ta.register_handler(ca.handler)
        tb.register_handler(cb.handler)

        def sync_agent(run_id: str, agent_name: str, steps: int):
            """Runs in a thread-pool worker; must set ContextVar first."""
            set_current_run_id(run_id)
            for i in range(steps):
                tracker.update_status(agent_name, f"T{i}", f"step {i}")
            tracker.update_status(agent_name, None, "Done")

        async def run_in_executor(run_id: str, agent_name: str, steps: int):
            """Mimics ``run_graph_async`` context propagation."""
            loop = asyncio.get_running_loop()
            set_current_run_id(run_id)
            ctx = contextvars.copy_context()
            await loop.run_in_executor(
                None,
                lambda: ctx.run(sync_agent, run_id, agent_name, steps),
            )

        await asyncio.gather(
            run_in_executor(run_a, "agent_a", 10),
            run_in_executor(run_b, "agent_b", 10),
        )

        assert ca.count == 11
        assert cb.count == 11
        for agent_name, _, _ in ca.events:
            assert agent_name == "agent_a"
        for agent_name, _, _ in cb.events:
            assert agent_name == "agent_b"

        tracker.remove_tracker(run_a)
        tracker.remove_tracker(run_b)


# ---------------------------------------------------------------------------
# Integration test – agent_service wrapper
# ---------------------------------------------------------------------------

class TestAgentServiceWrapper:
    """Verify that the ``create_agent_function`` wrapper correctly
    propagates the run_id from graph state to the progress ContextVar."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_langchain(self):
        pytest.importorskip("langchain_core")

    def test_wrapper_propagates_run_id(self):
        from app.backend.services.agent_service import create_agent_function

        tracker = ProgressTracker()
        run_id = generate_run_id()
        ta = tracker.create_tracker(run_id)
        c = _Collector("test")
        ta.register_handler(c.handler)

        def fake_agent(state, agent_id="test_agent"):
            # Inside the agent, progress.update_status should route to
            # the correct tracker
            progress.update_status(agent_id, "AAPL", "analysing")
            return {"messages": [], "data": state["data"]}

        wrapped = create_agent_function(fake_agent, "test_agent")

        state = {
            "messages": [],
            "data": {"tickers": ["AAPL"]},
            "metadata": {"run_id": run_id},
        }

        wrapped(state)

        assert c.count == 1
        assert c.events[0] == ("test_agent", "AAPL", "analysing")

        tracker.remove_tracker(run_id)

    def test_wrapper_restores_context(self):
        """After the wrapped agent returns, the ContextVar should be
        restored to its previous value."""
        from app.backend.services.agent_service import create_agent_function

        tracker = ProgressTracker()
        run_id_outer = generate_run_id()
        run_id_inner = generate_run_id()
        t_outer = tracker.create_tracker(run_id_outer)
        t_inner = tracker.create_tracker(run_id_inner)

        c_outer = _Collector("outer")
        c_inner = _Collector("inner")
        t_outer.register_handler(c_outer.handler)
        t_inner.register_handler(c_inner.handler)

        def fake_agent(state, agent_id="test_agent"):
            progress.update_status(agent_id, "MSFT", "inner")
            return {"messages": [], "data": state["data"]}

        wrapped = create_agent_function(fake_agent, "test_agent")

        # Set outer context
        set_current_run_id(run_id_outer)
        progress.update_status("outer_agent", None, "before")

        state = {
            "messages": [],
            "data": {"tickers": ["MSFT"]},
            "metadata": {"run_id": run_id_inner},
        }
        wrapped(state)

        # After wrapper, outer context should be restored
        progress.update_status("outer_agent", None, "after")

        assert c_outer.count == 2  # before + after
        assert c_inner.count == 1  # inner only

        for agent_name, _, _ in c_outer.events:
            assert agent_name == "outer_agent"
        for agent_name, _, _ in c_inner.events:
            assert agent_name == "test_agent"

        set_current_run_id(None)
        tracker.remove_tracker(run_id_outer)
        tracker.remove_tracker(run_id_inner)

    def test_wrapper_works_without_run_id(self):
        """When state has no run_id, the wrapper should still work
        (CLI backward compatibility)."""
        from app.backend.services.agent_service import create_agent_function

        def fake_agent(state, agent_id="test_agent"):
            progress.update_status(agent_id, "AAPL", "done")
            return {"messages": [], "data": state["data"]}

        wrapped = create_agent_function(fake_agent, "test_agent")

        state = {
            "messages": [],
            "data": {"tickers": ["AAPL"]},
            "metadata": {},  # no run_id
        }

        # Should not raise
        result = wrapped(state)
        assert result is not None


# ---------------------------------------------------------------------------
# Backward compatibility test – global progress singleton
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Verify that existing code that uses the global ``progress`` object
    continues to work without modification."""

    def test_global_progress_update_status(self):
        """Calling progress.update_status() with no ContextVar set should
        use the default tracker (CLI mode)."""
        set_current_run_id(None)
        # Should not raise
        progress.update_status("test_agent", "AAPL", "testing")
        status = progress.get_all_status()
        assert "test_agent" in status

    def test_global_progress_register_unregister_handler(self):
        """Register/unregister on the global progress object should work
        when no run_id is set."""
        set_current_run_id(None)
        events = []

        def handler(agent_name, ticker, status, analysis, timestamp):
            events.append((agent_name, ticker, status))

        progress.register_handler(handler)
        progress.update_status("test_agent", "AAPL", "hello")
        progress.unregister_handler(handler)
        progress.update_status("test_agent", "AAPL", "world")

        assert len(events) == 1
        assert events[0] == ("test_agent", "AAPL", "hello")

    def test_start_stop_on_default(self):
        """start() and stop() should work on the default tracker."""
        set_current_run_id(None)
        # These should not raise
        progress.start()
        progress.stop()
