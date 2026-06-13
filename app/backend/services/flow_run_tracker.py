from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.backend.database.connection import SessionLocal
from app.backend.repositories.flow_run_repository import FlowRunRepository
from app.backend.repositories.flow_repository import FlowRepository
from app.backend.models.schemas import FlowRunStatus


class FlowRunTracker:
    """
    Tracks flow run lifecycle within SSE event generators.

    Creates and updates HedgeFundFlowRun records as the execution
    progresses through start -> in_progress -> complete/error.

    All methods are no-ops if flow_id is None or the flow doesn't exist,
    so callers can use this unconditionally.

    Uses its own DB session (not from FastAPI Depends) because the
    dependency-injected session is closed before the async generator finishes.
    """

    def __init__(self, flow_id: Optional[int], request_data: Optional[Dict[str, Any]] = None):
        self.flow_id = flow_id
        self.request_data = request_data
        self.run_id: Optional[int] = None
        self._db: Optional[Session] = None
        self._active = False

    def _get_db(self) -> Session:
        """Lazily create a DB session (not from FastAPI dependency)."""
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def mark_started(self) -> Optional[int]:
        """
        Create a FlowRun record and set status to IN_PROGRESS.
        Returns the run_id, or None if tracking is inactive.
        """
        if self.flow_id is None:
            return None

        try:
            db = self._get_db()
            flow_repo = FlowRepository(db)
            flow = flow_repo.get_flow_by_id(self.flow_id)
            if not flow:
                self._active = False
                return None

            self._active = True
            run_repo = FlowRunRepository(db)
            flow_run = run_repo.create_flow_run(
                flow_id=self.flow_id,
                request_data=self.request_data
            )
            self.run_id = flow_run.id

            # Immediately transition to IN_PROGRESS
            run_repo.update_flow_run(
                run_id=self.run_id,
                status=FlowRunStatus.IN_PROGRESS
            )
            return self.run_id

        except Exception as e:
            print(f"FlowRunTracker: Failed to mark started: {e}")
            self._active = False
            return None

    def mark_complete(self, results: Dict[str, Any],
                      final_portfolio: Optional[Dict[str, Any]] = None) -> None:
        """Mark the run as COMPLETE and persist results."""
        if not self._active or self.run_id is None:
            return

        try:
            db = self._get_db()
            run_repo = FlowRunRepository(db)

            # Persist final_portfolio if available
            if final_portfolio:
                flow_run = run_repo.get_flow_run_by_id(self.run_id)
                if flow_run:
                    flow_run.final_portfolio = final_portfolio
                    db.commit()

            run_repo.update_flow_run(
                run_id=self.run_id,
                status=FlowRunStatus.COMPLETE,
                results=results,
            )
        except Exception as e:
            print(f"FlowRunTracker: Failed to mark complete: {e}")

    def mark_error(self, error_message: str) -> None:
        """Mark the run as ERROR with a descriptive message."""
        if not self._active or self.run_id is None:
            return

        try:
            db = self._get_db()
            run_repo = FlowRunRepository(db)
            run_repo.update_flow_run(
                run_id=self.run_id,
                status=FlowRunStatus.ERROR,
                error_message=error_message
            )
        except Exception as e:
            print(f"FlowRunTracker: Failed to mark error: {e}")

    def close(self) -> None:
        """Close the DB session. Call in finally block."""
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
            self._db = None
