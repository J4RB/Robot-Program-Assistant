"""LLM management - Client initialization and prompt templates."""

from app.backend.llm.client import initialize_llm
from app.backend.llm.prompts import (
	get_agentic_system_prompt,
	get_synthesis_prompt_template,
)

__all__ = [
	"initialize_llm",
	"get_agentic_system_prompt",
	"get_synthesis_prompt_template",
]
