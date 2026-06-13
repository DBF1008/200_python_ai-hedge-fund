import contextvars
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.style import Style
from rich.text import Text
from typing import Dict, Optional, Callable, List

console = Console()

# Identifies which run the currently executing code belongs to. It is set inside
# the worker thread that runs a graph (and propagates to LangGraph's node threads
# via copied contexts) so that ``AgentProgress.update_status`` can route events
# only to the handlers registered for that run. ``None`` means "no run context"
# (e.g. the CLI, which relies on the rich display rather than handlers).
_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("agent_progress_run_id", default=None)


class AgentProgress:
    """Manages progress tracking for multiple agents."""

    def __init__(self):
        self.agent_status: Dict[str, Dict[str, str]] = {}
        self.table = Table(show_header=False, box=None, padding=(0, 1))
        self.live = Live(self.table, console=console, refresh_per_second=4)
        self.started = False
        # Handlers are bucketed by run id so that concurrent runs only ever
        # receive their own events. The lock guards both this mapping and
        # ``agent_status`` because ``update_status`` is now invoked concurrently
        # from many run/agent threads.
        self._handlers_by_run: Dict[Optional[str], List[Callable[..., None]]] = {}
        self._lock = threading.RLock()

    def register_handler(self, handler: Callable[..., None], run_id: Optional[str] = None):
        """Register a handler to be called when an agent status updates for ``run_id``.

        Handlers are isolated per run id so concurrent runs never receive each
        other's events. ``run_id=None`` is the unscoped bucket used outside of a
        run context (e.g. the CLI)."""
        with self._lock:
            self._handlers_by_run.setdefault(run_id, []).append(handler)
        return handler  # Return handler to support use as decorator

    def unregister_handler(self, handler: Callable[..., None], run_id: Optional[str] = None):
        """Unregister a handler previously registered for ``run_id``."""
        with self._lock:
            handlers = self._handlers_by_run.get(run_id)
            if handlers and handler in handlers:
                handlers.remove(handler)
                if not handlers:
                    self._handlers_by_run.pop(run_id, None)

    def start(self):
        """Start the progress display."""
        if not self.started:
            self.live.start()
            self.started = True

    def stop(self):
        """Stop the progress display."""
        if self.started:
            self.live.stop()
            self.started = False

    def update_status(self, agent_name: str, ticker: Optional[str] = None, status: str = "", analysis: Optional[str] = None):
        """Update the status of an agent and notify only the current run's handlers."""
        # Resolve which run this update belongs to from the surrounding context.
        run_id = _current_run_id.get()

        with self._lock:
            if agent_name not in self.agent_status:
                self.agent_status[agent_name] = {"status": "", "ticker": None}

            if ticker:
                self.agent_status[agent_name]["ticker"] = ticker
            if status:
                self.agent_status[agent_name]["status"] = status
            if analysis:
                self.agent_status[agent_name]["analysis"] = analysis

            # Set the timestamp as UTC datetime
            timestamp = datetime.now(timezone.utc).isoformat()
            self.agent_status[agent_name]["timestamp"] = timestamp

            # Snapshot only the handlers registered for this run so we can notify
            # them outside the lock (a slow handler must not block other runs).
            handlers = list(self._handlers_by_run.get(run_id, ()))
            do_refresh = self.started

        # Notify only this run's handlers; other runs' queues are never touched.
        for handler in handlers:
            handler(agent_name, ticker, status, analysis, timestamp)

        # The rich Live display is only active in the single-threaded CLI path.
        if do_refresh:
            self._refresh_display()

    def get_all_status(self):
        """Get the current status of all agents as a dictionary."""
        with self._lock:
            return {agent_name: {"ticker": info["ticker"], "status": info["status"], "display_name": self._get_display_name(agent_name)} for agent_name, info in self.agent_status.items()}

    def _get_display_name(self, agent_name: str) -> str:
        """Convert agent_name to a display-friendly format."""
        return agent_name.replace("_agent", "").replace("_", " ").title()

    def _refresh_display(self):
        """Refresh the progress display."""
        self.table.columns.clear()
        self.table.add_column(width=100)

        # Sort agents with Risk Management and Portfolio Management at the bottom
        def sort_key(item):
            agent_name = item[0]
            if "risk_management" in agent_name:
                return (2, agent_name)
            elif "portfolio_management" in agent_name:
                return (3, agent_name)
            else:
                return (1, agent_name)

        with self._lock:
            status_snapshot = list(self.agent_status.items())
        for agent_name, info in sorted(status_snapshot, key=sort_key):
            status = info["status"]
            ticker = info["ticker"]
            # Create the status text with appropriate styling
            if status.lower() == "done":
                style = Style(color="green", bold=True)
                symbol = "✓"
            elif status.lower() == "error":
                style = Style(color="red", bold=True)
                symbol = "✗"
            else:
                style = Style(color="yellow")
                symbol = "⋯"

            agent_display = self._get_display_name(agent_name)
            status_text = Text()
            status_text.append(f"{symbol} ", style=style)
            status_text.append(f"{agent_display:<20}", style=Style(bold=True))

            if ticker:
                status_text.append(f"[{ticker}] ", style=Style(color="cyan"))
            status_text.append(status, style=style)

            self.table.add_row(status_text)


# Create a global instance
progress = AgentProgress()


@contextmanager
def progress_run_context(run_id: Optional[str]):
    """Bind progress updates emitted within this block to ``run_id``.

    Set this inside the thread that drives a graph run *before* invoking it; the
    run id then propagates to any threads spawned with a copied context (which is
    how LangGraph executes parallel nodes), so every agent update is routed to
    that run's handlers only."""
    token = _current_run_id.set(run_id)
    try:
        yield
    finally:
        _current_run_id.reset(token)


def set_progress_run_id(run_id: Optional[str]):
    """Imperatively bind the current context to ``run_id``; returns a reset token."""
    return _current_run_id.set(run_id)


def reset_progress_run_id(token) -> None:
    """Undo a previous :func:`set_progress_run_id` using its token."""
    _current_run_id.reset(token)


def get_current_run_id() -> Optional[str]:
    """Return the run id bound to the current context, if any."""
    return _current_run_id.get()
