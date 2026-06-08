"""LLM client initialization and configuration."""

import logging

from langchain_ollama import ChatOllama

from app.utils.config_loader import get_config

logger = logging.getLogger(__name__)


def initialize_llm() -> ChatOllama:
    """
    Initialize the LLM client from configuration.

    Configuration is read from app/backend/config.yaml llm section.

    Returns:
        Configured ChatOllama instance
    """
    # Load from config
    config = get_config()
    llm_config = config.get_llm_config()

    model = llm_config["model"]
    base_url = llm_config["base_url"]
    temperature = llm_config["temperature"]
    context_window_tokens = int(llm_config.get("context_window_tokens", 262144))
    max_output_tokens = int(llm_config.get("max_output_tokens", 512))
    reasoning = bool(llm_config.get("reasoning", False))
    request_timeout_seconds = int(llm_config.get("request_timeout_seconds", 60))

    llm = ChatOllama(
        model=model,
        base_url=base_url,
        temperature=float(temperature),
        num_ctx=context_window_tokens,
        num_predict=max_output_tokens,
        reasoning=reasoning,
        sync_client_kwargs={"timeout": request_timeout_seconds},
    )

    logger.info(
        "[INIT] LLM initialized: %s at %s (num_ctx=%s, num_predict=%s, reasoning=%s, timeout=%ss)",
        model,
        base_url,
        context_window_tokens,
        max_output_tokens,
        reasoning,
        request_timeout_seconds,
    )
    return llm
