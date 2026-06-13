import logging
from typing import Any, Dict, Optional

from app.backend.database import SessionLocal
from app.backend.models.schemas import FlowRunStatus
from app.backend.repositories.flow_repository import FlowRepository
from app.backend.repositories.flow_run_repository import FlowRunRepository

logger = logging.getLogger(__name__)


class FlowRunService:
    """Persists the FlowRun lifecycle for streaming hedge fund / backtest executions.

    Owns a dedicated DB session (decoupled from the request-scoped ``Depends(get_db)``
    session) so that a terminal status can be written from the streaming generator's
    ``finally`` block even when the client disconnects and the request task is
    cancelled. All DB operations are best-effort: failures are logged and never
    propagated, so persistence problems cannot break the SSE stream.
    """

    def __init__(self) -> None:
        self._db = SessionLocal()
        self._run_repo = FlowRunRepository(self._db)
        self._flow_repo = FlowRepository(self._db)

    def start(self, flow_id: Optional[int], request_data: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """Create a run for a saved flow and mark it IN_PROGRESS.

        Returns the new run id, or ``None`` when there is no saved flow to track
        (``flow_id`` is ``None`` or the flow does not exist). When ``None`` is
        returned, the other lifecycle methods become no-ops.
        """
        if flow_id is None:
            return None
        try:
            flow = self._flow_repo.get_flow_by_id(flow_id)
            if not flow:
                logger.warning("FlowRunService.start: flow %s not found; skipping run tracking", flow_id)
                return None
            run = self._run_repo.create_flow_run(flow_id=flow_id, request_data=request_data)
            run_id = run.id
            self._run_repo.update_flow_run(run_id=run_id, status=FlowRunStatus.IN_PROGRESS)
            return run_id
        except Exception as e:
            logger.error("FlowRunService.start failed for flow %s: %s", flow_id, e)
            return None

    def complete(self, run_id: Optional[int], results: Optional[Dict[str, Any]] = None) -> None:
        """Mark the run COMPLETE and persist its results."""
        if run_id is None:
            return
        try:
            self._run_repo.update_flow_run(run_id=run_id, status=FlowRunStatus.COMPLETE, results=results)
        except Exception as e:
            logger.error("FlowRunService.complete failed for run %s: %s", run_id, e)

    def error(self, run_id: Optional[int], message: str) -> None:
        """Mark the run ERROR and persist the error message."""
        if run_id is None:
            return
        try:
            self._run_repo.update_flow_run(run_id=run_id, status=FlowRunStatus.ERROR, error_message=message)
        except Exception as e:
            logger.error("FlowRunService.error failed for run %s: %s", run_id, e)

    def close(self) -> None:
        """Close the owned DB session."""
        try:
            self._db.close()
        except Exception as e:
            logger.error("FlowRunService.close failed: %s", e)
