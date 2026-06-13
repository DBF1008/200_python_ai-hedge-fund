from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from datetime import datetime

from app.backend.routes import api_router
from app.backend.database.connection import engine, SessionLocal
from app.backend.database.models import Base, HedgeFundFlowRun
from app.backend.models.schemas import FlowRunStatus
from app.backend.services.ollama_service import ollama_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Hedge Fund API", description="Backend API for AI Hedge Fund", version="0.1.0")

# Initialize database tables (this is safe to run multiple times)
Base.metadata.create_all(bind=engine)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # Frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all routes
app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    """Startup event to check Ollama availability and clean up stale runs."""
    # Clean up any IN_PROGRESS runs that were interrupted by a server restart
    try:
        db = SessionLocal()
        stale_runs = db.query(HedgeFundFlowRun).filter(
            HedgeFundFlowRun.status == FlowRunStatus.IN_PROGRESS.value
        ).all()

        for run in stale_runs:
            run.status = FlowRunStatus.ERROR.value
            run.error_message = "Server restarted while run was in progress"
            run.completed_at = datetime.utcnow()

        if stale_runs:
            db.commit()
            logger.info(f"Marked {len(stale_runs)} stale IN_PROGRESS runs as ERROR")
        db.close()
    except Exception as e:
        logger.warning(f"Failed to cleanup stale runs: {e}")

    # Check Ollama availability
    try:
        logger.info("Checking Ollama availability...")
        status = await ollama_service.check_ollama_status()
        
        if status["installed"]:
            if status["running"]:
                logger.info(f"✓ Ollama is installed and running at {status['server_url']}")
                if status["available_models"]:
                    logger.info(f"✓ Available models: {', '.join(status['available_models'])}")
                else:
                    logger.info("ℹ No models are currently downloaded")
            else:
                logger.info("ℹ Ollama is installed but not running")
                logger.info("ℹ You can start it from the Settings page or manually with 'ollama serve'")
        else:
            logger.info("ℹ Ollama is not installed. Install it to use local models.")
            logger.info("ℹ Visit https://ollama.com to download and install Ollama")
            
    except Exception as e:
        logger.warning(f"Could not check Ollama status: {e}")
        logger.info("ℹ Ollama integration is available if you install it later")
