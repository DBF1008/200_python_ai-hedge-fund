from functools import partial
from typing import Callable
from src.graph.state import AgentState
from src.utils.progress import set_current_run_id


def create_agent_function(agent_function: Callable, agent_id: str) -> Callable[[AgentState], dict]:
    """
    Creates a new function from an agent function that accepts an agent_id.

    The wrapper also propagates the ``run_id`` stored in the graph state
    metadata to the progress tracking ``ContextVar`` so that every agent
    call emits progress updates to the correct per-run tracker, even when
    multiple runs execute concurrently in thread-pool workers.

    :param agent_function: The agent function to wrap.
    :param agent_id: The ID to be passed to the agent.
    :return: A new function that can be called by LangGraph.
    """

    def wrapper(state: AgentState, *, _agent_id: str = agent_id):
        # Propagate run_id from graph state into the contextvar so that
        # ``progress.update_status(...)`` inside the agent routes to the
        # correct per-run tracker.
        run_id = state.get("metadata", {}).get("run_id")
        token = set_current_run_id(run_id)
        try:
            return agent_function(state, agent_id=_agent_id)
        finally:
            # Restore previous value (important when agents are nested
            # or when the same thread is reused by a pool).
            from src.utils.progress import _current_run_id
            _current_run_id.reset(token)

    # Preserve partial-like introspection for debugging
    wrapper.__name__ = getattr(agent_function, "__name__", "agent")
    wrapper.__qualname__ = getattr(agent_function, "__qualname__", wrapper.__name__)
    return wrapper
