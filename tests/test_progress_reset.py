"""Lifecycle tests for the shared :class:`AgentProgress` tracker.

The backend keeps progress in a single global ``AgentProgress`` instance whose
``agent_status`` dict used to accumulate across runs. When a user interrupted a
run (cancel / client disconnect) and then re-executed the same flow, the new run
could inherit the previous run's agent statuses, analysis, or terminal
("Done"/"Error") results.

These tests pin down the fix: every run must start from a clean tracker, the
tracker must be cleaned up when a run ends, and clearing per-run state must not
detach an active subscriber. The scenarios mirror what the SSE routes do:
``reset() -> register_handler() -> update_status()* -> unregister_handler() ->
reset()``.
"""

from src.utils.progress import AgentProgress


def _collector():
    """Return ``(seen, handler)`` where ``seen`` records the handler's updates."""
    seen = []

    def handler(agent_name, ticker, status, analysis, timestamp):
        seen.append((agent_name, status))

    return seen, handler


def _run_once(progress, handler, emissions):
    """Drive one run the way the backend route does and return its start snapshot.

    Returns ``get_all_status()`` captured immediately after the start-of-run
    reset (and handler registration) -- this is the state a freshly started run
    would observe before doing any work of its own.
    """
    progress.reset()  # start-of-run: clean slate
    progress.register_handler(handler)
    snapshot_at_start = progress.get_all_status()
    try:
        for agent, ticker, status in emissions:
            progress.update_status(agent, ticker, status)
    finally:
        progress.unregister_handler(handler)
        progress.reset()  # end-of-run cleanup
    return snapshot_at_start


def test_reset_clears_agent_status():
    progress = AgentProgress()
    progress.update_status("warren_buffett_abc123", "AAPL", "Done")
    assert progress.agent_status != {}

    progress.reset()

    assert progress.agent_status == {}
    assert progress.get_all_status() == {}


def test_reset_keeps_registered_handlers():
    # reset() must only clear per-run data, not detach the active subscriber, so a
    # run started right after a reset still streams to its handler.
    progress = AgentProgress()
    seen, handler = _collector()
    progress.register_handler(handler)

    progress.reset()
    progress.update_status("warren_buffett_abc123", "AAPL", "In progress")

    assert ("warren_buffett_abc123", "In progress") in seen


def test_consecutive_runs_do_not_reuse_state():
    progress = AgentProgress()

    seen1, h1 = _collector()
    start1 = _run_once(
        progress,
        h1,
        [
            ("warren_buffett_n1", "AAPL", "In progress"),
            ("warren_buffett_n1", "AAPL", "Done"),
        ],
    )
    # Run 1 started clean and cleaned up after itself.
    assert start1 == {}
    assert progress.agent_status == {}

    seen2, h2 = _collector()
    start2 = _run_once(
        progress,
        h2,
        [
            ("warren_buffett_n1", "AAPL", "In progress"),
            ("warren_buffett_n1", "AAPL", "Done"),
        ],
    )
    # Run 2 also started from a clean slate even though run 1 used the same agent
    # id and finished "Done" -- no stale Done leaked into run 2's start.
    assert start2 == {}
    # Run 2's subscriber only ever saw run 2's own emissions.
    assert seen2 == [
        ("warren_buffett_n1", "In progress"),
        ("warren_buffett_n1", "Done"),
    ]
    assert progress.agent_status == {}


def test_retry_after_interrupted_run_starts_clean():
    progress = AgentProgress()

    # Residue left behind by a previously interrupted run (e.g. work that kept
    # writing to the shared tracker, or a crash before cleanup completed).
    progress.update_status("warren_buffett_old", "AAPL", "Done")
    progress.update_status("risk_management_agent_old", None, "Error")
    assert progress.agent_status != {}

    seen, handler = _collector()
    start = _run_once(
        progress,
        handler,
        [
            ("warren_buffett_new", "AAPL", "In progress"),
            ("warren_buffett_new", "AAPL", "Done"),
        ],
    )

    # The retry did not inherit the interrupted run's stale Done/Error state.
    assert "warren_buffett_old" not in start
    assert "risk_management_agent_old" not in start
    assert start == {}
    # The retry's subscriber never saw the stale agents.
    assert all(agent.endswith("_new") for agent, _ in seen)
    assert progress.agent_status == {}


def test_disconnect_cleanup_leaves_no_stuck_status():
    progress = AgentProgress()
    seen, handler = _collector()

    # A run is interrupted mid-flight (only "In progress" emitted, never "Done"),
    # then the request ends and runs its cleanup -- as on a client disconnect.
    progress.reset()
    progress.register_handler(handler)
    progress.update_status("warren_buffett_mid", "AAPL", "In progress")
    progress.unregister_handler(handler)
    progress.reset()  # disconnect / cancel cleanup

    # No stuck "In progress" entry remains to bleed into the next run.
    assert progress.agent_status == {}

    # A run started after recovering from the disconnect still starts clean.
    seen2, handler2 = _collector()
    start2 = _run_once(progress, handler2, [("growth_agent_x", "AAPL", "Done")])
    assert start2 == {}
    assert progress.agent_status == {}
