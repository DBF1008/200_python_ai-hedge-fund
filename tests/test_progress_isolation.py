"""Regression tests for per-run isolation of agent progress streaming.

Background
----------
The backend streams agent progress to the browser over SSE using the global
``src.utils.progress.progress`` singleton. Previously every request registered a
handler onto one shared list and every agent called ``update_status`` on that one
object, which fanned each event out to *all* registered handlers. With two flows
running concurrently, one run's agent updates leaked into another run's SSE queue
(foreign agents/tickers/analysis mixed into the stream).

The fix scopes dispatch by a ``run_id`` carried in a ``contextvars.ContextVar``:
``update_status`` only notifies handlers registered for the run bound to the
current execution context. These tests pin that behaviour, including the
concurrent/interleaved case that originally caused the cross-talk.

Note: ``src.utils.progress`` only depends on ``rich`` so these tests run without
the LLM stack. The final test exercises the real LangGraph thread model and is
skipped automatically when ``langgraph`` is not installed.
"""

import contextvars
import queue
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.utils.progress import AgentProgress, progress, progress_run_context


def _collector(sink):
    """Return a handler matching the production signature that records events."""

    def handler(agent_name, ticker, status, analysis, timestamp):
        sink.append((agent_name, ticker, status, analysis, timestamp))

    return handler


def test_update_status_dispatches_only_to_current_run_handlers():
    """An update fires only the handler bound to the active run context."""
    ap = AgentProgress()
    a_events, b_events = [], []
    ap.register_handler(_collector(a_events), run_id="run-A")
    ap.register_handler(_collector(b_events), run_id="run-B")

    with progress_run_context("run-A"):
        ap.update_status("buffett_x", "AAPL", "Analyzing")
    with progress_run_context("run-B"):
        ap.update_status("munger_y", "MSFT", "Analyzing")

    # An update emitted with no run context must reach neither bucket.
    ap.update_status("orphan", None, "no context")

    assert [(e[0], e[1]) for e in a_events] == [("buffett_x", "AAPL")]
    assert [(e[0], e[1]) for e in b_events] == [("munger_y", "MSFT")]


def test_handler_receives_full_signature():
    """Handlers still receive (agent, ticker, status, analysis, timestamp)."""
    ap = AgentProgress()
    captured = []
    ap.register_handler(lambda *args: captured.append(args), run_id="R")

    with progress_run_context("R"):
        ap.update_status("agent", "AAPL", "Done", analysis="{}")

    assert len(captured) == 1
    agent, ticker, status, analysis, timestamp = captured[0]
    assert (agent, ticker, status, analysis) == ("agent", "AAPL", "Done", "{}")
    assert isinstance(timestamp, str) and timestamp


def test_unregister_handler_is_scoped_to_run():
    """Unregistering removes only the handler for the given run id."""
    ap = AgentProgress()
    events = []
    handler = ap.register_handler(_collector(events), run_id="run-A")
    ap.unregister_handler(handler, run_id="run-A")

    with progress_run_context("run-A"):
        ap.update_status("x", "AAPL", "Analyzing")

    assert events == []


def test_update_status_without_run_context_reaches_no_scoped_handlers():
    """Handlers registered under a run id never see context-less updates."""
    ap = AgentProgress()
    events = []
    ap.register_handler(_collector(events), run_id="run-A")

    ap.update_status("agent", "AAPL", "Analyzing")  # no progress_run_context

    assert events == []


def test_concurrent_interleaved_runs_do_not_cross_talk():
    """Two runs executing interleaved across threads stay fully isolated.

    This reproduces the original bug's conditions: each "run" sets its run
    context in a worker thread and then emits many agent updates from child
    threads via a copied context (mirroring how LangGraph dispatches parallel
    nodes). A barrier forces both runs to emit simultaneously so their updates
    interleave. Each handler must receive exactly its own run's events and none
    from the other run. Under the old fan-out-to-all behaviour both queues would
    receive every event, so this assertion is what catches the regression.
    """
    ap = AgentProgress()
    a_q: "queue.Queue" = queue.Queue()
    b_q: "queue.Queue" = queue.Queue()
    ap.register_handler(lambda agent, ticker, *rest: a_q.put((agent, ticker)), run_id="A")
    ap.register_handler(lambda agent, ticker, *rest: b_q.put((agent, ticker)), run_id="B")

    updates_per_run = 40
    start_barrier = threading.Barrier(2)

    def emit(agent, ticker, i):
        ap.update_status(agent, ticker, f"step-{i}")

    def run(run_id, agent, ticker):
        # Worker thread: bind the run context, then fan updates out to child
        # threads using a copied context (the LangGraph parallel-node model).
        with progress_run_context(run_id):
            ctx = contextvars.copy_context()
            start_barrier.wait()  # force the two runs to interleave
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = [
                    pool.submit(ctx.run, emit, agent, ticker, i)
                    for i in range(updates_per_run)
                ]
                for future in futures:
                    future.result()

    with ThreadPoolExecutor(max_workers=2) as pool:
        fa = pool.submit(run, "A", "buffett_A", "AAPL")
        fb = pool.submit(run, "B", "munger_B", "MSFT")
        fa.result()
        fb.result()

    a_events = list(a_q.queue)
    b_events = list(b_q.queue)

    # Every event arrived, on the correct stream, with nothing leaked across.
    assert len(a_events) == updates_per_run
    assert len(b_events) == updates_per_run
    assert all(event == ("buffett_A", "AAPL") for event in a_events), a_events
    assert all(event == ("munger_B", "MSFT") for event in b_events), b_events
    assert all(event[0] != "munger_B" for event in a_events)
    assert all(event[0] != "buffett_A" for event in b_events)


def test_real_langgraph_propagates_run_id_isolation():
    """End-to-end: the real global ``progress`` stays isolated across two
    concurrent LangGraph runs using the exact production wiring
    (``run_in_executor`` + ``progress_run_context`` set inside the worker).

    Skipped unless ``langgraph`` is installed; runs in the full CI environment.
    """
    pytest.importorskip("langgraph")

    import asyncio
    import operator
    from typing import Annotated, TypedDict

    from langgraph.graph import END, StateGraph

    class GraphState(TypedDict):
        log: Annotated[list, operator.add]

    def start_node(_state):
        return {"log": []}

    def make_node(agent_name, ticker):
        def node(_state):
            # Real agents call the global singleton with no run identity; the
            # run id must be supplied by the surrounding context only.
            progress.update_status(agent_name, ticker, "Done")
            return {"log": [agent_name]}

        return node

    def build_graph(prefix, ticker):
        graph = StateGraph(GraphState)
        graph.add_node("start_node", start_node)
        for name in ("n1", "n2", "n3"):
            graph.add_node(name, make_node(f"{prefix}_{name}", ticker))
            graph.add_edge("start_node", name)
            graph.add_edge(name, END)
        graph.set_entry_point("start_node")
        return graph.compile()

    a_events, b_events = [], []
    handler_a = progress.register_handler(lambda agent, *rest: a_events.append(agent), run_id="RID-A")
    handler_b = progress.register_handler(lambda agent, *rest: b_events.append(agent), run_id="RID-B")

    try:
        async def main():
            loop = asyncio.get_running_loop()

            def run(run_id, graph):
                # Production pattern: bind the run id inside the worker thread,
                # then invoke; LangGraph copies the context into node threads.
                with progress_run_context(run_id):
                    return graph.invoke({"log": []})

            graph_a = build_graph("A", "AAPL")
            graph_b = build_graph("B", "MSFT")
            await asyncio.gather(
                loop.run_in_executor(None, lambda: run("RID-A", graph_a)),
                loop.run_in_executor(None, lambda: run("RID-B", graph_b)),
            )

        asyncio.run(main())
    finally:
        progress.unregister_handler(handler_a, run_id="RID-A")
        progress.unregister_handler(handler_b, run_id="RID-B")

    assert sorted(a_events) == ["A_n1", "A_n2", "A_n3"], a_events
    assert sorted(b_events) == ["B_n1", "B_n2", "B_n3"], b_events
