"""Conversation memory management for assistant chat."""

import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from app.utils.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A single message in conversation history."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    token_count: int = 0  # Approximate token count


class ConversationMemory:
    """Manages conversation history."""

    def __init__(self):
        """Initialize conversation memory with configuration from config.yaml."""
        # Load from config
        config_loader = ConfigLoader()
        memory_config = config_loader.get_memory_config()
        llm_config = config_loader.get_llm_config()
        
        context_window_tokens = int(llm_config.get("context_window_tokens", 262144))
        max_memory_tokens_override = memory_config.get("max_memory_tokens")
        max_memory_fraction = float(memory_config.get("max_memory_fraction", 0.20))

        if max_memory_tokens_override is not None:
            self.max_memory_tokens = int(max_memory_tokens_override)
        else:
            # Clamp fraction to a sensible range to avoid starving retrieval/prompt budget.
            clamped_fraction = min(max(max_memory_fraction, 0.05), 0.45)
            self.max_memory_tokens = int(context_window_tokens * clamped_fraction)

        # Auto-derive message capacity from expected turn size.
        max_query_length = 2000
        max_output_tokens = int(llm_config.get("max_output_tokens", 512))
        estimated_user_tokens = max(64, int(max_query_length / 4))
        estimated_turn_tokens = estimated_user_tokens + max_output_tokens + 100
        self.max_messages = max(
            8,
            min(80, int((self.max_memory_tokens / max(estimated_turn_tokens, 1)) * 2)),
        )

        # Heuristic token estimation constants when no tokenizer is available.
        self.token_overhead_per_message = 12
        self.chars_per_token = 4.0
        self.tokens_per_word = 1.3
        
        self.messages: List[Message] = []
        self.total_tokens = 0

    def add_message(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        # Estimate token count
        token_count = self._estimate_tokens(content)
        
        # Create message
        message = Message(
            role=role,
            content=content,
            token_count=token_count,
        )
        
        # Add to history
        self.messages.append(message)
        self.total_tokens += token_count
        
        logger.debug(f"[MESSAGE] Added {role} message: {token_count} tokens (total: {self.total_tokens})")
        
        # Check if memory exceeds limit
        if self.total_tokens > self.max_memory_tokens:
            self._apply_memory_strategy()

    def get_history(self) -> str:
        """Get formatted conversation history for LLM context."""
        if not self.messages:
            return ""
        
        history_lines = []
        for msg in self.messages:
            prefix = "User" if msg.role == "user" else "Assistant"
            history_lines.append(f"{prefix}: {msg.content}")
        
        return "\n\n".join(history_lines)

    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        return {
            "message_count": len(self.messages),
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_memory_tokens,
            "percent_used": round(100 * self.total_tokens / self.max_memory_tokens, 1),
            "oldest_message_age": (
                (datetime.now() - self.messages[0].timestamp).total_seconds()
                if self.messages else 0
            ),
        }

    def _estimate_tokens(self, content: str) -> int:
        """Estimate token count for text."""
        char_based = int(len(content) / self.chars_per_token)
        word_based = int(len(content.split()) * self.tokens_per_word)
        return self.token_overhead_per_message + max(char_based, word_based)

    def _apply_memory_strategy(self) -> None:
        """Apply memory management strategy."""
        logger.warning(
            f"[OVERFLOW] Memory overflow: {self.total_tokens} tokens / {self.max_memory_tokens} max"
        )
        
        # First: Aggressive pruning if too many messages
        if len(self.messages) > self.max_messages:
            self._prune_messages(keep_count=self.max_messages // 2)
            logger.info(f"[PRUNE] Pruned to {len(self.messages)} messages")
        
        # Second: If still over, apply rolling window
        if self.total_tokens > self.max_memory_tokens:
            self._rolling_window_pruning()
            logger.info(
                f"[WINDOW] Applied rolling window: {len(self.messages)} messages, "
                f"{self.total_tokens} tokens"
            )

    def _prune_messages(self, keep_count: int) -> None:
        """Remove oldest messages, keeping most recent."""
        if len(self.messages) <= keep_count:
            return
        
        # Keep last N messages
        self.messages = self.messages[-keep_count:]
        
        # Recalculate total tokens
        self.total_tokens = sum(msg.token_count for msg in self.messages)

    def _rolling_window_pruning(self) -> None:
        """Apply rolling window: remove oldest message until under limit."""
        while self.total_tokens > self.max_memory_tokens and self.messages:
            removed = self.messages.pop(0)
            self.total_tokens -= removed.token_count
            logger.debug(f"[REMOVE] Removed oldest message: {removed.token_count} tokens")

    def clear(self) -> None:
        """Clear all conversation history."""
        self.messages = []
        self.total_tokens = 0
        logger.info("[CLEAR] Conversation memory cleared")
