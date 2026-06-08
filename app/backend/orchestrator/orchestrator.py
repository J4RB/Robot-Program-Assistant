"""Backend orchestration loop for retrieval and response synthesis."""

import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Add app root to path for imports (supports direct execution)
app_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(app_root.parent))  # Add workspace root
sys.path.insert(0, str(app_root))  # Add app root

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.backend.orchestrator.memory import ConversationMemory
from app.backend.orchestrator.results import (
    count_sources_by_collection,
    collect_sources_from_tool_messages,
    format_search_results,
    normalize_sources,
)
from app.backend.orchestrator.trace import SessionTrace
from app.backend.llm import client as llm
from app.backend.llm.prompts import get_agentic_system_prompt, get_synthesis_prompt_template
from app.data_pipeline.embedding.embedding_model import EmbeddingModel
from app.data_pipeline.storage.vector_store import VectorStore
from app.utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class Orchestrator:
    """Single-loop orchestrator that performs tool use, retrieval, and synthesis."""

    def __init__(self):
        self.config = ConfigLoader()
        self.embedding_model = EmbeddingModel()
        self.vector_store = VectorStore()
        self.llm = llm.initialize_llm()

        # Per-tool embedding model overrides (optional). Config key: data_pipeline.embedding.per_tool_models
        embedding_config = self.config.get_embedding_config()
        per_tool_models = embedding_config.get("per_tool_models", {}) or {}
        self.tool_embedding_models: Dict[str, EmbeddingModel] = {}
        for tool_name, model_name in per_tool_models.items():
            try:
                self.tool_embedding_models[tool_name] = EmbeddingModel(model_name=model_name)
            except Exception:
                logger.warning("[EMBED] Failed to load per-tool embedding model %s for %s", model_name, tool_name)

        self.agent_tools = self._define_tools()
        self.agent_tool_map = {agent_tool.name: agent_tool for agent_tool in self.agent_tools}
        self.agent_llm = self._bind_agent_llm(self.llm)

        self.memory = ConversationMemory()

        formatting_config = self.config.get_formatting_config()
        self.max_history_message_length = int(formatting_config.get("max_history_message_length", 500))

        llm_config = self.config.get_llm_config()
        memory_config = self.config.get_memory_config()
        collections = self.config.get_rag_config().get("collections", {})
        self.programs_collection = collections.get("programs", "robot_programs")
        self.program_code_collection = collections.get("program_code", "robot_program_code")
        self.documentation_collection = collections.get("documentation", "documentation")
        self.search_tool_collections: Dict[str, str] = {
            "search_robot_programs": self.programs_collection,
            "search_robot_code": self.program_code_collection,
            "search_documentation": self.documentation_collection,
        }

        self.context_window_tokens = int(llm_config.get("context_window_tokens", 262144))
        max_memory_tokens_override = memory_config.get("max_memory_tokens")
        max_memory_fraction = float(memory_config.get("max_memory_fraction", 0.20))
        if max_memory_tokens_override is not None:
            self.max_memory_tokens = int(max_memory_tokens_override)
        else:
            clamped_fraction = min(max(max_memory_fraction, 0.05), 0.45)
            self.max_memory_tokens = int(self.context_window_tokens * clamped_fraction)

        logger.info("[INIT] Orchestrator initialized")

    def _bind_agent_llm(self, base_llm: Any) -> Any:
        """Bind tools to the LLM when the model supports tool calling."""
        try:
            return base_llm.bind_tools(self.agent_tools)
        except Exception as exc:
            logger.warning("[INIT] Tool binding unavailable; using text-only fallback: %s", exc)
            return base_llm

    def _define_tools(self) -> list[Any]:
        """Define the tools and return them as a list."""

        @tool("search_robot_programs")
        def search_robot_programs(query: str, limit: int = 3) -> str:
            """Search for robot programs by query. Returns program metadata and summaries."""
            return self._search_collection(self.programs_collection, query, limit)

        @tool("search_robot_code")
        def search_robot_code(query: str, limit: int = 3) -> str:
            """Search for robot program code snippets by query. Returns extracted code segments."""
            return self._search_collection(self.program_code_collection, query, limit)

        @tool("search_documentation")
        def search_documentation(query: str, limit: int = 3) -> str:
            """Search for technical documentation by query. Returns documentation chunks and guides."""
            return self._search_collection(self.documentation_collection, query, limit)

        return [search_robot_programs, search_robot_code, search_documentation]

    def invoke(
        self,
        query: str,
        program_context: Optional[str] = None,
        max_program_results: Optional[int] = None,
        max_documentation_results: Optional[int] = None,
        use_conversation_history: bool = True,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Run agentic retrieval, then synthesis, returning a chat-style response."""
        pipeline_start = time.time()
        trace = SessionTrace()
        
        try:
            self._report_progress(progress_callback, "Processing query...")
            self.memory.add_message("user", query)
            
            # Log user input
            trace.log_user_input(
                query=query,
                program_context=bool(program_context),
                max_program_results=max_program_results,
                max_documentation_results=max_documentation_results,
                use_conversation_history=use_conversation_history,
            )

            # Stage 1: Agentic retrieval - agent calls tools to gather context
            sources, retrieval_exhausted = self._agentic_loop(
                query=query,
                program_context=program_context,
                max_program_results=max_program_results,
                max_documentation_results=max_documentation_results,
                use_conversation_history=use_conversation_history,
                progress_callback=progress_callback,
                trace=trace,
            )

            # Stage 2: Synthesis - pass retrieved context to LLM to generate response
            self._report_progress(progress_callback, "Generating response for user...")
            response_text = self._synthesize_response(
                query=query,
                sources=sources,
                program_context=program_context,
                use_conversation_history=use_conversation_history,
                retrieval_exhausted=retrieval_exhausted,
                trace=trace,
            )

            self.memory.add_message("assistant", response_text)

            # Build basic orchestration metadata from actual retrieved sources
            sources = normalize_sources(sources)
            doc_counts = count_sources_by_collection(sources)
            
            # Log final output
            total_time_ms = (time.time() - pipeline_start) * 1000
            trace.log_final_output(
                response_text=response_text,
                source_count=len(sources),
                sources_by_collection=doc_counts,
                total_time_ms=total_time_ms,
            )
            
            # Finalize trace to disk
            trace.finalize()
            
            logger.info(f"[TRACE] Complete execution trace saved to session: {trace.session_id}")

            return {
                "response": response_text,
                "sources": sources,
                "routing": {
                    "doc_counts_retrieved": doc_counts,
                    "sources_searched": list(doc_counts.keys()),
                    "retrieval_exhausted": retrieval_exhausted,
                },
                "memory": self.memory.get_memory_stats(),
                "session_id": trace.session_id,
            }
        except Exception as exc:
            logger.error("[PIPELINE_FAILED] Orchestrator pipeline failed: %s", exc, exc_info=True)
            trace.log_error(
                error_type=type(exc).__name__,
                error_message=str(exc),
                context="Orchestrator pipeline execution",
            )
            raise

    def _agentic_loop(
        self,
        query: str,
        program_context: Optional[str],
        max_program_results: Optional[int],
        max_documentation_results: Optional[int],
        use_conversation_history: bool,
        progress_callback: Optional[Callable[[str], None]] = None,
        trace: Optional[SessionTrace] = None,
    ) -> tuple[List[Dict[str, Any]], bool]:
        """Agentic orchestration loop: let the LLM call tools until it has enough context."""
        messages = self._assemble_agent_messages(
            query, program_context, use_conversation_history,
            max_program_results, max_documentation_results,
        )
        max_steps = 5

        for step_num in range(1, max_steps + 1):
            self._report_progress(progress_callback, "Deciding to call tool or stop...")
            response = self.agent_llm.invoke(messages)
            messages.append(response)

            tool_calls = getattr(response, "tool_calls", None) or []
            if not tool_calls:
                sources = collect_sources_from_tool_messages(messages)
                logger.info("[AGENT_COMPLETE] Completed in %d step(s), %d source(s)", step_num, len(sources))
                self._report_progress(progress_callback, "Agent has enough information to answer.")
                return sources, False

            logger.info("[AGENT_STEP_%d] LLM decided to call %d tool(s)", step_num, len(tool_calls))
            for tool_call in tool_calls:
                tool_message = self._dispatch_tool_call(tool_call, step_num, progress_callback, trace)
                messages.append(tool_message)

        sources = collect_sources_from_tool_messages(messages)
        logger.warning("[AGENT_COMPLETE] Exceeded %d steps; returning %d source(s)", max_steps, len(sources))
        self._report_progress(progress_callback, "Reached retrieval step limit. Using best available information...")
        return sources, True

    def _assemble_agent_messages(
        self,
        query: str,
        program_context: Optional[str],
        use_conversation_history: bool,
        max_program_results: Optional[int],
        max_documentation_results: Optional[int],
    ) -> List[Any]:
        """Assemble the initial message list for the agent model."""
        messages: List[Any] = [
            SystemMessage(content=get_agentic_system_prompt()),
            HumanMessage(content=query),
        ]

        if program_context:
            messages.append(HumanMessage(content=f"User-provided program context to consider:\n{program_context}"))

        if use_conversation_history and len(self.memory.messages) > 1:
            history_lines = [
                f"{'User' if msg.role == 'user' else 'Assistant'}: {msg.content[:self.max_history_message_length]}"
                for msg in self.memory.messages[:-1]
            ]
            if history_lines:
                messages.append(HumanMessage(content="Conversation history:\n" + "\n".join(history_lines)))

        overrides = []
        if max_program_results is not None:
            overrides.append(f"max_program_results={max_program_results}")
        if max_documentation_results is not None:
            overrides.append(f"max_documentation_results={max_documentation_results}")
        if overrides:
            messages.append(HumanMessage(content="User overrides: " + " ".join(overrides)))

        return messages

    def _dispatch_tool_call(
        self,
        tool_call: Dict[str, Any],
        step_num: int,
        progress_callback: Optional[Callable[[str], None]] = None,
        trace: Optional[SessionTrace] = None,
    ) -> ToolMessage:
        """Execute a single tool call from the agent loop and return a ToolMessage."""
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {}) or {}
        tool_id = tool_call.get("id")
        query_arg = tool_args.get("query", "")
        limit_arg = tool_args.get("limit", 3)

        logger.info("[AGENT_TOOL] Tool: %s, Query: '%s', Limit: %d", tool_name, query_arg[:60], limit_arg)
        if trace:
            trace.log_tool_call(tool_name=tool_name, query=query_arg, limit=limit_arg, step=step_num)

        self._report_progress(progress_callback, f"Retrieving from database... ({tool_name})")
        call_start = time.time()
        result_content = self._execute_router_tool(tool_name, tool_args, progress_callback, trace)
        result_time_ms = (time.time() - call_start) * 1000

        self._log_tool_result(tool_name, result_content, step_num, result_time_ms, trace)
        self._report_progress(progress_callback, "Evaluating retrieved information...")

        return ToolMessage(content=result_content, tool_call_id=tool_id)

    def _log_tool_result(
        self,
        tool_name: str,
        result_content: str,
        step_num: int,
        result_time_ms: float,
        trace: Optional[SessionTrace],
    ) -> None:
        """Parse and log a tool result for debugging and tracing."""
        try:
            tool_result = json.loads(result_content)
        except Exception:
            logger.debug("[AGENT_RESULT] Could not parse tool result for %s", tool_name)
            return

        if "error" in tool_result:
            logger.info("[AGENT_RESULT] Tool %s failed: %s", tool_name, tool_result.get("error"))
        else:
            result_count = tool_result.get("count", 0)
            logger.info("[AGENT_RESULT] Tool %s returned %d result(s)", tool_name, result_count)
            if trace:
                results = tool_result.get("results", [])
                scores = [r.get("score", 0) for r in results]
                trace.log_tool_result(
                    tool_name=tool_name,
                    result_count=result_count,
                    scores=scores,
                    result_objects=results,
                    step=step_num,
                    result_time_ms=result_time_ms,
                )

    def _synthesize_response(
        self,
        query: str,
        sources: List[Dict[str, Any]],
        program_context: Optional[str] = None,
        use_conversation_history: bool = True,
        retrieval_exhausted: bool = False,
        trace: Optional[SessionTrace] = None,
    ) -> str:
        """Synthesis stage: pass retrieved context to LLM to generate response."""
        # Format the retrieved sources as context
        context_lines = []
        if sources:
            context_lines.append("## Retrieved Information:")
            for idx, source in enumerate(sources, 1):
                src = source.get("source", "unknown")
                collection_fields = source.get("collection_fields", {})
                context_lines.append(f"\n**Source {idx} ({src}):**")

                # For program code sources, include the structured snippet so the LLM
                # sees the actual node parameters, not just the summary chunk_text.
                snippet_text = collection_fields.get("snippet_text") if isinstance(collection_fields, dict) else None
                if snippet_text:
                    chunk_text = source.get("text", "")
                    context_lines.append(chunk_text)
                    context_lines.append(snippet_text)
                else:
                    context_lines.append(source.get("text", ""))
        
        if program_context:
            context_lines.append("\n## Provided Program Context:")
            context_lines.append(program_context)

        context = "\n".join(context_lines) if context_lines else "No context retrieved."

        # Format conversation history
        history_lines = []
        if use_conversation_history and len(self.memory.messages) > 1:
            history_messages = self.memory.messages[:-1]
            for msg in history_messages:
                prefix = "User" if msg.role == "user" else "Assistant"
                history_lines.append(f"{prefix}: {msg.content[:self.max_history_message_length]}")
        
        history = "\n".join(history_lines) if history_lines else "No prior conversation."

        retrieval_status = (
            "Retrieval reached the maximum number of tool steps and may be incomplete. "
            "Use the gathered context to give the best possible answer, and clearly state any uncertainty or missing information."
            if retrieval_exhausted
            else "Retrieval completed normally. Use the gathered context to answer confidently when possible."
        )

        # Create synthesis chat prompt and invoke synthesis LLM
        synthesis_template = get_synthesis_prompt_template()
        synthesis_messages = synthesis_template.format_messages(
            query=query,
            context=context,
            history=history,
            retrieval_status=retrieval_status,
        )

        # Log the synthesis prompt to trace
        if trace:
            trace.log_llm_synthesis_prompt(
                system_prompt=str(synthesis_messages[0].content) if synthesis_messages else "",
                query=query,
                context=context,
                history=history.split("\n") if history != "No prior conversation." else [],
            )

        llm_start = time.time()
        response = self.llm.invoke(synthesis_messages)
        llm_time_ms = (time.time() - llm_start) * 1000
        response_text = str(response.content).strip()
        
        # Log the LLM response to trace
        if trace:
            trace.log_llm_response(
                response_text=response_text,
                response_time_ms=llm_time_ms,
            )
        
        return response_text

    def _execute_router_tool(
        self,
        tool_name: Optional[str],
        tool_args: Dict[str, Any],
        progress_callback: Optional[Callable[[str], None]] = None,
        trace: Optional[SessionTrace] = None,
    ) -> str:
        """Dispatch a tool call by name and return its JSON result string."""
        if not tool_name:
            return json.dumps({"error": "Missing tool name"}, ensure_ascii=False)
        if self.agent_tool_map.get(tool_name) is None:
            return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)

        try:
            if tool_name.startswith("search_"):
                return self._run_search_tool(tool_name, tool_args, trace)
            result = self.agent_tool_map[tool_name].invoke(tool_args)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:
            logger.error("[TOOL_FAILED] Tool %s failed: %s", tool_name, exc, exc_info=True)
            self._report_progress(progress_callback, f"Tool failed ({tool_name}). Continuing with available context...")
            return json.dumps({"error": f"Tool {tool_name} failed", "details": str(exc)}, ensure_ascii=False)

    def _run_search_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        trace: Optional[SessionTrace],
    ) -> str:
        """Embed the tool query and run the appropriate vector collection search."""
        collection_name = self.search_tool_collections.get(tool_name)
        if not collection_name:
            return json.dumps({"error": f"Unknown search tool: {tool_name}"}, ensure_ascii=False)

        q = tool_args.get("query", "") if isinstance(tool_args, dict) else ""
        limit = tool_args.get("limit", 3) if isinstance(tool_args, dict) else 3
        model = self.tool_embedding_models.get(tool_name, self.embedding_model)

        query_embedding = None
        if q:
            try:
                emb_start = time.time()
                query_embedding = model.embed(q)
                embed_time_ms = (time.time() - emb_start) * 1000
                logger.info("[EMBED] Embedded query for %s (model=%s)", tool_name, getattr(model, "model_name", None))
                if trace:
                    trace.log_per_tool_embedding(
                        tool_name=tool_name,
                        query=q,
                        embedding_dim=len(query_embedding),
                        embedding_time_ms=embed_time_ms,
                        model_name=getattr(model, "model_name", None),
                    )
            except Exception:
                logger.warning("[EMBED] Embedding failed for %s; falling back to inline embedding", tool_name)

        return self._search_collection(collection_name, q, limit, query_embedding=query_embedding)

    @staticmethod
    def _report_progress(progress_callback: Optional[Callable[[str], None]], message: str) -> None:
        if not progress_callback:
            return
        try:
            progress_callback(message)
        except Exception:
            # Progress reporting should never break the request pipeline.
            pass

    def _search_collection(self, collection_name: str, query: str, limit: int, query_embedding: Optional[Any] = None) -> str:
        try:
            limit = max(1, min(int(limit), 5))
        except Exception:
            limit = 3

        try:
            if query_embedding is None:
                query_embedding = self.embedding_model.embed(query)
                logger.info("[EMBED] Query embedded for %s", collection_name)
            
            search_results = self.vector_store.search(
                collection_name=collection_name,
                query_embedding=query_embedding,
                limit=limit,
            )
            formatted = format_search_results(search_results, collection_name)
            return json.dumps(
                {
                    "collection": collection_name,
                    "query": query,
                    "limit": limit,
                    "count": len(formatted),
                    "results": formatted,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            logger.error("[SEARCH_FAILED] Failed to search %s: %s", collection_name, exc, exc_info=True)
            return json.dumps(
                {
                    "collection": collection_name,
                    "query": query,
                    "limit": limit,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )

    def clear_memory(self) -> None:
        self.memory.clear()
        logger.info("[CLEAR] Conversation memory cleared - starting new session")