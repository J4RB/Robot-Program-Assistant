"""Embedding service."""
from langchain_ollama import OllamaEmbeddings
import numpy as np
from app.utils.config_loader import get_config
from typing import List, Union, Optional



class EmbeddingModel:
    """Embedding model wrapper."""
    def __init__(self, model_name: Optional[str] = None):
        config = get_config()
        embedding_config = config.get_embedding_config()

        # Read from config or override with provided model_name
        self.model_name = model_name or embedding_config.get("model_name")
        self.batch_size = int(embedding_config.get("batch_size", 64))
        self.base_url = embedding_config.get(
            "base_url",
            config.get_llm_config().get("base_url", "http://localhost:11434"),
        )
        self.request_timeout_seconds = int(embedding_config.get("request_timeout_seconds", 60))

        # Get embedding dimension from config
        self.embedding_dim = int(embedding_config.get("embedding_dimension"))

        # Load model
        print(f"[INFO] Loading Ollama embedding model: {self.model_name}")
        self.model = OllamaEmbeddings(
            model=self.model_name,
            base_url=self.base_url,
            client_kwargs={"timeout": self.request_timeout_seconds},
        )

    def embed(self, text: Union[str, List[str]]) -> np.ndarray:
        """Embed text(s)."""
        if isinstance(text, list):
            vectors: List[List[float]] = []
            for i in range(0, len(text), self.batch_size):
                batch = text[i : i + self.batch_size]
                vectors.extend(self.model.embed_documents(batch))
            return np.asarray(vectors, dtype=np.float32)

        return np.asarray(self.model.embed_query(text), dtype=np.float32)
