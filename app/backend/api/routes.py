"""API routes for the backend assistant."""

import json
import logging
import queue
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.backend.orchestrator import Orchestrator
from app.data_pipeline.storage import ProgramStore
from app.utils.config_loader import ConfigLoader


logger = logging.getLogger(__name__)

# Load config for request validation
config_loader = ConfigLoader()
formatting_config = config_loader.get_formatting_config()
max_query_length = 2000
log_max_length = int(formatting_config.get("max_log_message_length", 100))
error_max_length = int(formatting_config.get("max_error_message_length", 200))

# Router
router = APIRouter()


# Dependency Injection
def get_orchestrator(request: Request) -> Orchestrator:
    """Get the orchestrator from app state."""
    orchestrator = getattr(request.app.state, "orchestrator", None)
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not initialized")
    return orchestrator


@lru_cache(maxsize=1)
def get_program_store() -> ProgramStore:
    """Get a program store instance for editor-facing program data."""
    return ProgramStore()


# Request/Response Models
class ChatRequest(BaseModel):
    """Request body for the /api/chat endpoint."""

    message: str = Field(..., min_length=1, max_length=max_query_length, description="User's query")
    program_context: Optional[str] = Field(
        None,
        description="Optional user-provided program context to inject into synthesis",
    )
    max_program_results: Optional[int] = Field(
        None, ge=1, le=20, description="Optional override for max program results"
    )
    max_documentation_results: Optional[int] = Field(
        None, ge=1, le=20, description="Optional override for max documentation results"
    )


class Source(BaseModel):
    """A single source document in the response."""

    text: str = Field(..., description="Snippet from the source document")
    source: str = Field(..., description="Source database: 'programs' or 'documentation'")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0.0-1.0)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Source-specific metadata")


class RoutingMetadata(BaseModel):
    """Metadata about the routing decision and retrieval strategy."""

    intent: str = Field(..., description="Classified query intent")
    program_context_mode: str = Field(..., description="How much program content to inject")
    databases_searched: List[str] = Field(..., description="Databases that were searched")
    doc_counts_requested: Dict[str, int] = Field(
        ..., description="Number of documents requested per database"
    )
    doc_counts_retrieved: Dict[str, int] = Field(
        ..., description="Number of documents actually retrieved per database"
    )


class ChatResponse(BaseModel):
    """Response body for the /api/chat endpoint."""

    response: str = Field(..., description="Generated response to the user's query")
    sources: List[Source] = Field(..., description="List of source documents used")
    routing: RoutingMetadata = Field(..., description="Routing decision metadata")
    session_id: str = Field(..., description="Unique session ID for this query - used to retrieve full execution trace")


class SearchRequest(BaseModel):
    """Request body for the /api/search endpoint (pure semantic search)."""

    query: str = Field(..., min_length=1, max_length=max_query_length, description="Search query")
    limit: int = Field(10, ge=1, le=50, description="Maximum number of results to return")


class SearchResponse(BaseModel):
    """Response body for the /api/search endpoint."""

    query: str = Field(..., description="The search query")
    results: List[Source] = Field(..., description="Search results with similarity scores")
    count: int = Field(..., description="Number of results returned")


def _to_chat_response(result: Dict[str, Any]) -> ChatResponse:
    """Convert a raw orchestrator result dictionary into a ChatResponse model."""
    response_text = result.get("response", "")
    sources = result.get("sources", [])
    routing = result.get("routing", {})
    session_id = result.get("session_id", "unknown")

    source_objects = [
        Source(
            text=source.get("text", ""),
            source=source.get("source", ""),
            score=source.get("score", 0.0),
            metadata=source.get("metadata") or source.get("collection_fields"),
        )
        for source in sources
    ]

    routing_obj = RoutingMetadata(
        intent=routing.get("intent", "both"),
        program_context_mode=routing.get("program_context_mode", "metadata"),
        databases_searched=routing.get("databases_searched", routing.get("sources_searched", [])),
        doc_counts_requested=routing.get("doc_counts_requested", {}),
        doc_counts_retrieved=routing.get("doc_counts_retrieved", {}),
    )

    return ChatResponse(
        response=response_text,
        sources=source_objects,
        routing=routing_obj,
        session_id=session_id,
    )


def _sse_event(event: str, payload: Dict[str, Any]) -> str:
    """Create one SSE event chunk."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# Route Handlers
@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "UR Robot Assistant Backend"}


def _normalize_program_id(program_id: str) -> str:
    """Normalize request path input for direct UUID lookup."""
    return (program_id or "").strip()


@router.get("/api/programs/{program_id}/json")
async def get_program_json(
    program_id: str,
    program_store: ProgramStore = Depends(get_program_store),
) -> Dict[str, Any]:
    """Load editable program representation from the program store."""
    program = program_store.get_program(_normalize_program_id(program_id))
    if not program:
        raise HTTPException(status_code=404, detail=f"Program not found: {program_id}")

    return program["program_json"]


@router.get("/api/programs/{program_id}/download")
async def download_program(
    program_id: str,
    program_store: ProgramStore = Depends(get_program_store),
) -> FileResponse:
    """Download raw .urpx file for the requested program."""
    program = program_store.get_program(_normalize_program_id(program_id))
    if not program:
        raise HTTPException(status_code=404, detail=f"Program not found: {program_id}")

    source_file_path = program.get("source_file_path")
    if not source_file_path:
        raise HTTPException(status_code=404, detail=f"Source file path missing for program: {program_id}")

    urpx_file = Path(source_file_path)
    if not urpx_file.exists():
        raise HTTPException(status_code=404, detail=f"Source .urpx file not found: {source_file_path}")

    return FileResponse(
        path=str(urpx_file),
        media_type="application/octet-stream",
        filename=urpx_file.name,
    )


@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> ChatResponse:
    """Chat endpoint for assistant query processing."""
    try:
        logger.info(f"[CHAT] Processing query: {request.message[:log_max_length]}...")

        program_context = request.program_context

        # Invoke the response pipeline with optional overrides
        result = orchestrator.invoke(
            query=request.message,
            program_context=program_context,
            max_program_results=request.max_program_results,
            max_documentation_results=request.max_documentation_results,
        )

        response = _to_chat_response(result)

        logger.info(f"[SUCCESS] Response generated successfully (sources: {len(response.sources)})")
        return response

    except ValueError as e:
        logger.warning(f"[INVALID] Invalid input: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"[ERROR] Orchestrator pipeline error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Processing error: {str(e)[:error_max_length]}",
        )
    except Exception as e:
        logger.error(f"[ERROR] Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> StreamingResponse:
    """Streaming chat endpoint that emits progress updates and final response."""

    events: queue.Queue[tuple[str, Dict[str, Any]]] = queue.Queue()

    def progress_callback(message: str) -> None:
        logger.info("[CHAT_PROGRESS] %s", message)
        events.put(("progress", {"message": message}))

    def worker() -> None:
        try:
            logger.info(f"[CHAT] Processing query (stream): {request.message[:log_max_length]}...")
            result = orchestrator.invoke(
                query=request.message,
                program_context=request.program_context,
                max_program_results=request.max_program_results,
                max_documentation_results=request.max_documentation_results,
                progress_callback=progress_callback,
            )

            response = _to_chat_response(result)
            events.put(("final", response.model_dump()))
            logger.info("[SUCCESS] Streaming response generated successfully")
        except Exception as exc:
            logger.error(f"[ERROR] Streaming chat failed: {exc}", exc_info=True)
            events.put(("error", {"message": "Sorry, I encountered an error. Please try again."}))
        finally:
            events.put(("done", {}))

    threading.Thread(target=worker, daemon=True).start()

    def event_stream():
        while True:
            event_type, payload = events.get()
            if event_type == "done":
                break
            yield _sse_event(event_type, payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.post("/api/chat/clear-memory")
def clear_chat_memory(orchestrator: Orchestrator = Depends(get_orchestrator)) -> Dict[str, str]:
    """Clear server-side conversational memory used by the orchestrator."""
    try:
        orchestrator.clear_memory()
        return {"status": "ok", "message": "Conversation memory cleared"}
    except Exception as e:
        logger.error(f"[CLEAR_ERROR] Failed to clear chat memory: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear chat memory")


@router.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> SearchResponse:
    """Semantic search endpoint."""
    try:
        logger.info(f"[SEARCH] Semantic search: {request.query[:100]}... (limit: {request.limit})")

        # Embed the query
        query_embedding = orchestrator.embedding_model.embed(request.query)

        # Direct semantic search on programs collection
        search_results = orchestrator.vector_store.search(
            collection_name="robot_programs",
            query_embedding=query_embedding,
            limit=request.limit,
        )

        # Format results
        sources = [
            Source(
                text=result["text"][:200] + "..." if len(result["text"]) > 200 else result["text"],
                source=(
                    result.get("raw_payload", {}).get("program_name")
                    or result.get("raw_payload", {}).get("program_id")
                    or "robot_program"
                ),
                score=round(result["score"], 4),
                metadata=result.get("raw_payload", {}),
            )
            for result in search_results
        ]

        logger.info(f"[SEARCH] Semantic search returned {len(sources)} results")

        return SearchResponse(
            query=request.query,
            results=sources,
            count=len(sources),
        )

    except ValueError as e:
        logger.warning(f"[INVALID] Invalid input: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SEARCH_ERROR] Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Search error: {str(e)[:200]}",
        )
