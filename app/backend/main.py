"""FastAPI backend for the assistant orchestration service."""

import argparse
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

# Add app root to path for imports
app_root = Path(__file__).parent.parent
sys.path.insert(0, str(app_root.parent))  # Add workspace root
sys.path.insert(0, str(app_root))  # Add app root

def _parse_cli_config_override() -> Optional[Path]:
    """Parse optional --config path from CLI arguments."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--config",
        type=str,
        help="Path to backend YAML config file",
    )
    args, _ = parser.parse_known_args(sys.argv[1:])

    if not args.config:
        return None

    override_path = Path(args.config).expanduser()
    if not override_path.is_absolute():
        return (Path.cwd() / override_path).resolve()
    return override_path.resolve()


config_override_path = _parse_cli_config_override()

from app.utils.config_loader import ConfigLoader

config_loader = ConfigLoader()
if config_override_path:
    config_loader.load_config(config_override_path, section="backend")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.backend.orchestrator import Orchestrator
from app.backend.api.routes import router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

if config_override_path:
    logger.info(
        "[CONFIG] Using backend config override from CLI: %s",
        str(config_override_path),
    )


# Global orchestrator
orchestrator: Optional[Orchestrator] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Async context manager for app startup and shutdown.

    Initializes all dependencies (embeddings, vector store, orchestrator).
    """
    # STARTUP
    global orchestrator

    logger.info("[START] Starting assistant backend server...")

    try:
        # Initialize the orchestrator
        orchestrator = Orchestrator()
        app.state.orchestrator = orchestrator
        logger.info("Orchestrator initialized (includes embedding model, vector store, and LLM)")

        logger.info("[STARTUP] Assistant backend startup complete")

    except Exception as e:
        logger.error(f"[INIT_FAILED] Failed to initialize assistant backend: {e}", exc_info=True)
        raise

    yield

    logger.info("Shutting down assistant backend...")
    logger.info("[SHUTDOWN] Assistant backend shutdown complete")


# FastAPI Application
app = FastAPI(
    title="UR Robot Assistant Backend",
    description="Assistant backend for robot program retrieval, documentation retrieval, and response synthesis",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware to allow frontend requests.
cors_origins = [
    "localhost",
    "localhost:3000",
    "127.0.0.1:3000",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info(f"[CONFIG] CORS middleware configured for origins: {cors_origins}")

# Include API routes
app.include_router(router)


# Entry Point
if __name__ == "__main__":
    import uvicorn

    # Start the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
