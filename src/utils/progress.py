import contextvars
import threading
import uuid
from datetime import datetime, timezone
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.style import Style
from rich.text import Text
from typing import Dict, Optional, Callable, List

console = Console()

# Context variable to track the current run_id.  Set by SSE endpoints and
# propagated into worker threads so that agents always emit progress to the
# correct per-run tracker, even when multiple runs execute concurrently.
_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_run_id", default=None
)


def generate_run_id() -> str:
    """Generate a unique run ID for isolating progress tracking."""
    return uuid.uuid4().hex


def get_current_run_id() -> Optional[str]:
    """Return the run_id associated with the current execution context."""
    return _current_run_id.get()


def set_current_run_id(run_id: Optional[str]) -> contextvars.Token:
    """Set the run_id for the current execution context.

    Returns the context token so callers can restore the previous value.
    """
    return _current_run_id.set(run_id)


class AgentProgress:
    """Manages progress tracking for a single run.

    Each run (hedge-fund /run or /backtest) gets its own ``AgentProgress``
    instance so that status updates and registered handlers are fully
    isolated from other concurrent runs.
    """

    def __init__(self):
        self.agent_status: Dict[str, Dict[str, str]] = {}
        self.table = Table(show_header=False, box=None, padding=(0, 1))
        self.live = Live(self.table, console=console, refresh_per_second=4)
        self.started = False
        self.update_handlers: List[Callable] = []

    def register_handler(self, handler: Callable):
        """Register a handler to be called when agent status updates."""
        self.update_handlers.append(handler)
        return handler  # Return handler to support use as decorator

    def unregister_handler(self, handler: Callable):
        """Unregister a previously registered handler."""
        if handler in self.update_handlers:
            self.update_handlers.remove(handler)

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

    def update_status(
        self,
        agent_name: str,
        ticker: Optional[str] = None,
        status: str = "",
        analysis: Optional[str] = None,
    ):
        """Update the status of an agent."""
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

        # Notify all registered handlers
        for handler in self.update_handlers:
            handler(agent_name, ticker, status, analysis, timestamp)

        self._refresh_display()

    def get_all_status(self):
        """Get the current status of all agents as a dictionary."""
        return {
            agent_name: {
                "ticker": info["ticker"],
                "status": info["status"],
                "display_name": self._get_display_name(agent_name),
            }
            for agent_name, info in self.agent_status.items()
        }

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

        for agent_name, info in sorted(self.agent_status.items(), key=sort_key):
            status = info["status"]
            ticker = info["ticker"]
            # Create the status text with appropriate styling
            if status.lower() == "done":
                style = Style(color="green", bold=True)
                symbol = "\u2713"
            elif status.lower() == "error":
                style = Style(color="red", bold=True)
                symbol = "\u2717"
            else:
                style = Style(color="yellow")
                symbol = "\u22ef"

            agent_display = self._get_display_name(agent_name)
            status_text = Text()
            status_text.append(f"{symbol} ", style=style)
            status_text.append(f"{agent_display:<20}", style=Style(bold=True))

            if ticker:
                status_text.append(f"[{ticker}] ", style=Style(color="cyan"))
            status_text.append(status, style=style)

            self.table.add_row(status_text)


class ProgressTracker:
    """Registry that multiplexes per-run ``AgentProgress`` instances.

    The global ``progress`` object is now a ``ProgressTracker``.  When an
    agent calls ``progress.update_status(...)`` the tracker inspects the
    current ``contextvars`` context to determine which run the call belongs
    to and delegates to the corresponding ``AgentProgress`` instance.

    This ensures that concurrent runs never see each other's events.
    """

    def __init__(self):
        self._trackers: Dict[str, AgentProgress] = {}
        self._lock = threading.Lock()
        # Fallback tracker used when no run_id is set (e.g. CLI usage)
        self._default = AgentProgress()

    # -- registry management -------------------------------------------------

    def create_tracker(self, run_id: str) -> AgentProgress:
        """Create and register a new per-run tracker.

        Returns the newly created ``AgentProgress`` instance.
        """
        with self._lock:
            tracker = AgentProgress()
            self._trackers[run_id] = tracker
            return tracker

    def get_tracker(self, run_id: Optional[str] = None) -> AgentProgress:
        """Return the tracker for *run_id*, or the default tracker."""
        if run_id is None:
            return self._default
        with self._lock:
            return self._trackers.get(run_id, self._default)

    def remove_tracker(self, run_id: str) -> None:
        """Remove and discard the tracker for *run_id*."""
        with self._lock:
            tracker = self._trackers.pop(run_id, None)
        if tracker is not None:
            tracker.stop()
            tracker.update_handlers.clear()

    # -- convenience helpers -------------------------------------------------

    def _resolve_tracker(self) -> AgentProgress:
        """Return the tracker for the current context."""
        run_id = _current_run_id.get()
        return self.get_tracker(run_id)

    # -- proxy API (backward-compatible with the old AgentProgress) ---------

    def register_handler(self, handler: Callable):
        """Register *handler* on the tracker for the current context."""
        return self._resolve_tracker().register_handler(handler)

    def unregister_handler(self, handler: Callable):
        """Unregister *handler* from the tracker for the current context."""
        self._resolve_tracker().unregister_handler(handler)

    def start(self):
        self._resolve_tracker().start()

    def stop(self):
        self._resolve_tracker().stop()

    def update_status(
        self,
        agent_name: str,
        ticker: Optional[str] = None,
        status: str = "",
        analysis: Optional[str] = None,
    ):
        """Update agent status on the tracker for the current context."""
        self._resolve_tracker().update_status(agent_name, ticker, status, analysis)

    def get_all_status(self):
        return self._resolve_tracker().get_all_status()


# Global instance -- drop-in replacement for the old ``AgentProgress()`` singleton.
progress = ProgressTracker()
