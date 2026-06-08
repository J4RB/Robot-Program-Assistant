"""Utilities for normalizing and extracting retrieval results."""

import json
from typing import Any, Dict, List

from langchain_core.messages import ToolMessage


def format_search_results(search_results: List[Dict[str, Any]], collection_name: str) -> List[Dict[str, Any]]:
    """Normalize raw vector search results into compact dicts for tool output."""
    formatted = []
    for doc in search_results:
        payload = doc.get("raw_payload", {}) if isinstance(doc, dict) else {}
        formatted.append({
            "id": doc.get("id"),
            "text": doc.get("text", ""),
            "score": float(doc.get("score", 0.0) or 0.0),
            "source": collection_name,
            "program_id": payload.get("program_id"),
            "program_name": payload.get("program_name"),
            "robot_type": payload.get("robot_type"),
            "application_type": payload.get("application_type"),
            "chunk_index": payload.get("chunk_index"),
            "chunk_type": payload.get("chunk_type"),
            "section_name": payload.get("section_name"),
            "snippet_path": payload.get("snippet_path"),
            "snippet_text": payload.get("snippet_text"),
            "start_line": payload.get("start_line"),
            "end_line": payload.get("end_line"),
            "doc_name": payload.get("doc_name"),
            "page_number": payload.get("page_number"),
            "source_file_path": payload.get("source_file_path"),
            "raw_payload": payload,
        })
    return formatted


def collect_sources_from_tool_messages(messages: List[Any]) -> List[Dict[str, Any]]:
    """Collect retrieved documents from ToolMessage entries in the message list."""
    sources: List[Dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        try:
            payload = json.loads(message.content)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        collection = payload.get("collection", "unknown")
        for doc in payload.get("results", []):
            if isinstance(doc, dict):
                sources.append({
                    "id": doc.get("id"),
                    "text": doc.get("text", ""),
                    "source": collection,
                    "score": doc.get("score", 0.0),
                    "collection_fields": doc,
                })
    return sources


def normalize_sources(sources: Any) -> List[Dict[str, Any]]:
    """Coerce raw source dicts into a consistent shape for the API response."""
    if not isinstance(sources, list):
        return []
    normalized = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        normalized.append({
            "id": source.get("id"),
            "text": str(source.get("text", "")),
            "source": str(source.get("source", "")),
            "score": float(source.get("score", 0.0) or 0.0),
            "collection_fields": source.get("metadata") or source.get("collection_fields") or {},
        })
    return normalized


def count_sources_by_collection(sources: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return a mapping of collection name -> number of retrieved documents."""
    counts: Dict[str, int] = {}
    for source in sources:
        src = str(source.get("source", "unknown"))
        counts[src] = counts.get(src, 0) + 1
    return counts
