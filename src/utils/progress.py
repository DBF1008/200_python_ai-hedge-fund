import threading
import uuid
from datetime import datetime, timezone
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.style import Style
from rich.text import Text
from typing import Dict, Optional, Callable, List, Set

console = Console()


class AgentProgress:
    """Manages progress tracking for multiple agents with run-scoped isolation.

    Each SSE run (hedge-fund run or backtest) must call:
      1. start_run() -> run_id
      2. register_agents_for_run(agent_ids, run_id)
      3. register_handler(handler, run_id)
    and finally:
      4. end_run(run_id)

    This ensures that:
    - Events from a cancelled run's lingering agents are ignored.
    - A new run never inherits stale agent_status from a previous run.
    - Handlers only receive events from their own run.
    """

    def __init__(self):
        # Run lifecycle tracking (thread-safe via _lock)
        self._lock = threading.Lock()
        self._active_runs: Set[str] = set()
        self._agent_to_run: Dict[str, str] = {}
        self._run_handlers: Dict[str, list] = {}

        # Agent status per run: {run_id: {agent_name: status_dict}}
        self._run_agent_status: Dict[str, Dict[str, dict]] = {}

        # Flat agent_status (backward-compatible, used by CLI Rich display)
        self.agent_status: Dict[str, Dict[str, str]] = {}

        # Rich console display (CLI only)
        self.table = Table(show_header=False, box=None, padding=(0, 1))
        self.live = Live(self.table, console=console, refresh_per_second=4)
        self.started = False

        # Legacy flat handler list (backward-compatible, used by CLI)
        self.update_handlers: List[Callable] = []

    # ---- Run lifecycle ------------------------------------------------

    def start_run(self) -> str:
        """Start a new isolated run. Returns a unique run_id."""
        run_id = str(uuid.uuid4())
        with self._lock:
            self._active_runs.add(run_id)
            self._run_agent_status[run_id] = {}
            self._run_handlers[run_id] = []
        return run_id

    def end_run(self, run_id: str):
        """End a run and clean up all its state."""
        with self._lock:
            self._active_runs.discard(run_id)
            # Remove all agent -> run associations for this run
            agents_to_remove = [
                a for a, r in self._agent_to_run.items() if r == run_id
            ]
            for agent in agents_to_remove:
                del self._agent_to_run[agent]
            # Remove run-scoped state
            self._run_agent_status.pop(run_id, None)
            self._run_handlers.pop(run_id, None)

    def register_agents_for_run(self, agent_ids: list, run_id: str):
        """Explicitly associate agent IDs with a run.

        Only agents registered here will have their progress updates accepted.
        This prevents lingering agents from a cancelled run from contaminating
        a new run that uses the same agent IDs.
        """
        with self._lock:
            if run_id not in self._active_runs:
                return
            for agent_id in agent_ids:
                self._agent_to_run[agent_id] = run_id

    # ---- Handler registration -----------------------------------------

    def register_handler(self, handler: Callable, run_id: str = None):
        """Register a handler to be called when agent status updates.

        If run_id is provided, the handler only receives events from that run.
        If run_id is None, the handler receives all events (legacy/CLI behavior).
        """
        if run_id:
            with self._lock:
                if run_id not in self._run_handlers:
                    self._run_handlers[run_id] = []
                self._run_handlers[run_id].append(handler)
        else:
            self.update_handlers.append(handler)
        return handler  # Return handler to support use as decorator

    def unregister_handler(self, handler: Callable, run_id: str = None):
        """Unregister a previously registered handler."""
        if run_id:
            with self._lock:
                if run_id in self._run_handlers:
                    try:
                        self._run_handlers[run_id].remove(handler)
                    except ValueError:
                        pass
        else:
            if handler in self.update_handlers:
                self.update_handlers.remove(handler)

    # ---- Status updates -----------------------------------------------

    def update_status(
        self,
        agent_name: str,
        ticker: Optional[str] = None,
        status: str = "",
        analysis: Optional[str] = None,
    ):
        """Update the status of an agent.

        Run-scoped filtering:
        - If the agent is registered to an active run, the update is delivered
          only to that run's handlers.
        - If the agent's run has ended (or it was never registered), the update
          is silently dropped.  This prevents stale events from lingering
          thread-pool agents from reaching a new run.

        Legacy behaviour (no runs active):
        - If no runs are active, the update is delivered to legacy handlers
          (used by the CLI Rich display).
        """
        run_id = self._get_run_for_agent(agent_name)

        if run_id is None:
            # Agent not registered to any run.
            # If there are active runs, this is a stale event -> drop it.
            # If there are no active runs (CLI mode), fall through to legacy path.
            with self._lock:
                if self._active_runs:
                    return
                run_id = None  # legacy path
        else:
            # Agent is registered to a run.  If that run is no longer active,
            # the update is stale -> drop it.
            with self._lock:
                if run_id not in self._active_runs:
                    return

        timestamp = datetime.now(timezone.utc).isoformat()

        # Update run-scoped agent_status
        if run_id:
            with self._lock:
                if run_id not in self._run_agent_status:
                    self._run_agent_status[run_id] = {}
                if agent_name not in self._run_agent_status[run_id]:
                    self._run_agent_status[run_id][agent_name] = {
                        "status": "",
                        "ticker": None,
                    }

                entry = self._run_agent_status[run_id][agent_name]
                if ticker:
                    entry["ticker"] = ticker
                if status:
                    entry["status"] = status
                if analysis:
                    entry["analysis"] = analysis
                entry["timestamp"] = timestamp

            # Notify run-scoped handlers (outside the lock to avoid deadlocks)
            with self._lock:
                handlers = list(self._run_handlers.get(run_id, []))
            for handler in handlers:
                handler(agent_name, ticker, status, analysis, timestamp)
        else:
            # Legacy path: flat agent_status + global handlers
            if agent_name not in self.agent_status:
                self.agent_status[agent_name] = {"status": "", "ticker": None}

            if ticker:
                self.agent_status[agent_name]["ticker"] = ticker
            if status:
                self.agent_status[agent_name]["status"] = status
            if analysis:
                self.agent_status[agent_name]["analysis"] = analysis
            self.agent_status[agent_name]["timestamp"] = timestamp

            for handler in self.update_handlers:
                handler(agent_name, ticker, status, analysis, timestamp)

        self._refresh_display()

    # ---- Queries ------------------------------------------------------

    def _get_run_for_agent(self, agent_name: str) -> Optional[str]:
        """Return the run_id an agent is registered to, or None."""
        with self._lock:
            return self._agent_to_run.get(agent_name)

    def get_all_status(self, run_id: str = None):
        """Get the current status of all agents.

        If run_id is given, returns status for that run only.
        Otherwise returns the flat (legacy) agent_status.
        """
        if run_id:
            with self._lock:
                statuses = self._run_agent_status.get(run_id, {})
                return {
                    name: {
                        "ticker": info.get("ticker"),
                        "status": info.get("status"),
                        "display_name": self._get_display_name(name),
                    }
                    for name, info in statuses.items()
                }
        return {
            name: {
                "ticker": info.get("ticker"),
                "status": info.get("status"),
                "display_name": self._get_display_name(name),
            }
            for name, info in self.agent_status.items()
        }

    # ---- Cleanup helpers ----------------------------------------------

    def clear_all_status(self, run_id: str = None):
        """Clear agent status for a specific run, or all run-scoped status."""
        if run_id:
            with self._lock:
                self._run_agent_status[run_id] = {}
        else:
            with self._lock:
                self._run_agent_status.clear()

    def reset(self):
        """Reset ALL progress state (runs, agents, handlers, status)."""
        with self._lock:
            self._active_runs.clear()
            self._agent_to_run.clear()
            self._run_agent_status.clear()
            self._run_handlers.clear()
            self.agent_status.clear()
            self.update_handlers.clear()

    # ---- Display helpers ----------------------------------------------

    def _get_display_name(self, agent_name: str) -> str:
        """Convert agent_name to a display-friendly format."""
        return agent_name.replace("_agent", "").replace("_", " ").title()

    def start(self):
        """Start the Rich progress display (CLI only)."""
        if not self.started:
            self.live.start()
            self.started = True

    def stop(self):
        """Stop the Rich progress display (CLI only)."""
        if self.started:
            self.live.stop()
            self.started = False

    def _refresh_display(self):
        """Refresh the Rich progress display (CLI only)."""
        # Use flat agent_status for display (CLI path)
        if not self.agent_status:
            return

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
            status = info.get("status", "")
            ticker = info.get("ticker")
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
