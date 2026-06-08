"""Session trace logging for assistant queries."""

import json
import logging
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SessionTrace:
    """Execution trace logger."""
    
    def __init__(self, logs_dir: Optional[str] = None):
        """Initialize a new session trace."""
        self.session_id = str(uuid.uuid4())
        self.tz = ZoneInfo("Europe/Copenhagen")
        self.start_time = datetime.now(self.tz)
        self.events: List[Dict[str, Any]] = []
        
        # Set logs directory
        if logs_dir is None:
            logs_dir = Path(__file__).parent.parent.parent.parent / "database" / "logs"
        else:
            logs_dir = Path(logs_dir)
        
        self.logs_dir = logs_dir
        self.log_file = self.logs_dir / f"{self.session_id}.json"
        
        # Create logs directory if it doesn't exist
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[TRACE_INIT] Session {self.session_id} initialized, logging to {self.log_file}")
    
    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log a single event to the trace."""
        try:
            timestamp = datetime.now(self.tz).isoformat()
            event = {
                "timestamp": timestamp,
                "type": event_type,
                "data": data,
            }
            
            self.events.append(event)
            logger.debug(f"[TRACE_EVENT] {event_type}: buffered in memory")
        
        except Exception as e:
            logger.error(f"[TRACE_FAILED] Failed to log event {event_type}: {e}", exc_info=True)
    
    def finalize(self) -> None:
        """Write all buffered events to disk as a JSON file."""
        try:
            trace_document = {
                "session_id": self.session_id,
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.now(self.tz).isoformat(),
                "event_count": len(self.events),
                "events": self.events,
            }
            
            # Write as indented JSON for readability
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(trace_document, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[TRACE_SAVED] Session trace finalized: {self.log_file}")
        
        except Exception as e:
            logger.error(f"[TRACE_SAVE_FAILED] Failed to finalize trace: {e}", exc_info=True)
    
    def log_user_input(self, query: str, **settings) -> None:
        """Log initial user query and settings."""
        self.log_event("user_input", {
            "query": query,
            "settings": settings,
        })
    
    def log_embedding(self, query: str, embedding_dim: int, embedding_time_ms: float, model_name: Optional[str] = None) -> None:
        """Log query embedding event."""
        payload = {
            "query": query,
            "embedding_dim": embedding_dim,
            "embedding_time_ms": embedding_time_ms,
        }
        if model_name:
            payload["model_name"] = model_name

        self.log_event("embedding", payload)
    
    def log_tool_call(self, tool_name: str, query: str, limit: int, step: int) -> None:
        """Log a tool call (retrieval attempt)."""
        self.log_event("tool_call", {
            "tool": tool_name,
            "query": query,
            "limit": limit,
            "step": step,
        })

    def log_per_tool_embedding(self, tool_name: str, query: str, embedding_dim: int, embedding_time_ms: float, model_name: Optional[str] = None) -> None:
        """Log an embedding computed specifically for a tool-call (rewritten query)."""
        payload = {
            "tool": tool_name,
            "query": query,
            "embedding_dim": embedding_dim,
            "embedding_time_ms": embedding_time_ms,
        }
        if model_name:
            payload["model_name"] = model_name

        self.log_event("per_tool_embedding", payload)
    
    def log_tool_result(self, tool_name: str, result_count: int, scores: List[float], 
                       result_objects: List[Dict[str, Any]], step: int, result_time_ms: float) -> None:
        """Log tool result (what was retrieved) - stores FULL results, not just samples."""
        self.log_event("tool_result", {
            "tool": tool_name,
            "result_count": result_count,
            "score_range": {
                "min": min(scores) if scores else 0,
                "max": max(scores) if scores else 0,
                "mean": sum(scores) / len(scores) if scores else 0,
            },
            "results": result_objects,  # FULL results, not truncated samples
            "step": step,
            "result_time_ms": result_time_ms,
        })
    
    def log_evaluation(self, step: int, all_sources_count: int, all_sources_by_tool: Dict[str, int]) -> None:
        """Log context evaluation after tool results."""
        self.log_event("evaluation", {
            "step": step,
            "total_sources_retrieved": all_sources_count,
            "sources_by_tool": all_sources_by_tool,
        })
    
    def log_decision(self, step: int, decision: str, reasoning: str = "") -> None:
        """Log agent decision (CONTINUE or STOP)."""
        self.log_event("decision", {
            "step": step,
            "decision": decision,  # "CONTINUE" or "STOP"
            "reasoning": reasoning,
        })
    
    def log_llm_synthesis_prompt(self, system_prompt: str, query: str, context: str, 
                                 history: List[Dict[str, str]]) -> None:
        """Log the full prompt sent to synthesis LLM."""
        self.log_event("llm_synthesis_prompt", {
            "system_prompt": system_prompt,
            "user_query": query,
            "context": context,  # FULL context, not truncated
            "context_length": len(context),
            "history": history,  # FULL history
            "history_length": len(history),
        })
    
    def log_llm_response(self, response_text: str, response_time_ms: float, 
                        token_estimate: Optional[int] = None) -> None:
        """Log the LLM response from synthesis."""
        self.log_event("llm_response", {
            "response_text": response_text,
            "response_time_ms": response_time_ms,
            "token_estimate": token_estimate,
        })
    
    def log_error(self, error_type: str, error_message: str, context: str = "") -> None:
        """Log an error that occurred during execution."""
        self.log_event("error", {
            "error_type": error_type,
            "error_message": error_message,
            "context": context,
        })
    
    def log_final_output(self, response_text: str, source_count: int, 
                        sources_by_collection: Dict[str, int], total_time_ms: float) -> None:
        """Log final output and summary statistics."""
        self.log_event("final_output", {
            "response_text": response_text,
            "source_count": source_count,
            "sources_by_collection": sources_by_collection,
            "total_time_ms": total_time_ms,
            "session_id": self.session_id,
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of the trace."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time.isoformat(),
            "log_file": str(self.log_file),
        }
