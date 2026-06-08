"""Vector store."""

import shutil
import uuid
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import asdict
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models
from tqdm import tqdm
from app.utils.config_loader import get_config, ConfigLoader


class VectorStore:
    """Vector store abstraction."""

    def __init__(self):
        config = get_config()
        vector_store_config = config.get_vector_store_config()
        # Get embedding dimension from embedding config
        embedding_config = config.get_embedding_config()
        embedding_dim = int(embedding_config.get("embedding_dimension"))
        
        # Resolve path relative to workspace root
        workspace_root = config.get_workspace_root()
        path = workspace_root / vector_store_config['path']
        
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.embedding_dim = embedding_dim
        
        # Load batch size from embedding config
        config_loader = ConfigLoader()
        embedding_config = config_loader.get_embedding_config()
        self.batch_size = embedding_config.get("batch_size", 64)  # Default to 64 if not specified
        
        # Initialize Qdrant client
        self.client = QdrantClient(path=str(self.path))
        print(f"[INFO] Initialized vector store at: {self.path}")

    def _reset_client(self) -> None:
        """Reinitialize local client to clear in-memory collection caches."""
        close_fn = getattr(self.client, "close", None)
        if callable(close_fn):
            close_fn()
        self.client = QdrantClient(path=str(self.path))

    @staticmethod
    def _make_point_id(*parts: str) -> str:
        """Create deterministic UUID point IDs acceptable by local Qdrant."""
        key = "::".join(str(part) for part in parts)
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))

    def reset_storage(self) -> None:
        """Delete and recreate the local vector store directory."""
        close_fn = getattr(self.client, "close", None)
        if callable(close_fn):
            close_fn()

        if self.path.exists():
            shutil.rmtree(self.path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(self.path))
        print(f"[INFO] Reset vector store at: {self.path}")

    def create_collection(
        self,
        collection_name: str,
        recreate: bool = False,
        vector_size: int = 0,
    ) -> bool:
        """Create a collection if it doesn't exist."""
        try:
            # Check if collection exists
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if collection_name in collection_names:
                if recreate:
                    print(f"[INFO] Deleting existing collection: {collection_name}")
                    self.client.delete_collection(collection_name)
                    self._reset_client()
                else:
                    print(f"[INFO] Collection already exists: {collection_name}")
                    return False
            
            collection_vector_size = int(vector_size or self.embedding_dim)
            if collection_vector_size <= 0:
                raise ValueError(
                    "Embedding dimension is not configured. "
                    "Set vector_store.embedding_dimension or pass vector_size."
                )

            # Create collection
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=collection_vector_size,
                    distance=models.Distance.COSINE
                )
            )
            self._reset_client()
            print(f"[SUCCESS] Created collection: {collection_name}")
            return True
        
        except Exception as e:
            print(f"[ERROR] Error creating collection: {e}")
            raise

    def upsert_documents(
        self,
        collection_name: str,
        documents: List[Any],
        embeddings: np.ndarray,
        doc_type: str = "generic"
    ) -> int:
        """Insert documents with embeddings."""
        if len(documents) != len(embeddings):
            raise ValueError(f"Document count ({len(documents)}) != Embedding count ({len(embeddings)})")
        
        # Convert to points
        points = []
        for idx, (doc, embedding) in enumerate(tqdm(
            zip(documents, embeddings),
            total=len(documents),
            desc=f"[INFO] Preparing {doc_type} documents for upsert"
        )):
            # Create payload based on document type
            if doc_type == "program":
                # One metadata point per program: Qdrant point ID must equal SQLite UUID.
                point_id = doc.program_id
                payload = {
                    "id": doc.program_id,
                    "program_id": doc.program_id,
                    "program_name": doc.program_name,
                    "chunk_text": doc.chunk_text,
                    "chunk_index": doc.chunk_index,
                    "metadata": doc.metadata,
                    "robot_type": doc.metadata.get("robotType", ""),
                    "application_type": doc.metadata.get("applicationType", ""),
                }
            elif doc_type == "program_code":
                point_id = self._make_point_id("program_code", doc.program_id, doc.chunk_index)
                payload = {
                    "id": str(point_id),
                    "program_id": doc.program_id,
                    "program_name": doc.program_name,
                    "chunk_text": doc.chunk_text,
                    "chunk_index": doc.chunk_index,
                    "chunk_type": doc.chunk_type,
                    "section_name": doc.section_name,
                    "snippet_path": doc.snippet_path,
                    "snippet_text": doc.snippet_text,
                    "start_line": getattr(doc, 'start_line', None),
                    "end_line": getattr(doc, 'end_line', None),
                }
            elif doc_type == "documentation":
                # Create composite ID: doc_name#page_number#chunk_index
                composite_id = f"{doc.doc_name}#{doc.page_number}#{doc.chunk_index}"
                point_id = self._make_point_id("documentation", doc.doc_name, doc.page_number, doc.chunk_index)
                payload = {
                    "id": composite_id,
                    "doc_name": doc.doc_name,
                    "page_number": doc.page_number,
                    "chunk_index": doc.chunk_index,
                    "chunk_text": doc.chunk_text,
                    "source_file_path": doc.source_file_path,
                }
            else:
                point_id = idx
                payload = asdict(doc) if hasattr(doc, '__dataclass_fields__') else doc
            
            # Create point
            point = models.PointStruct(
                id=point_id,
                vector=embedding.tolist(),
                payload=payload
            )
            points.append(point)
        
        # Upsert in batches
        total_inserted = 0
        
        for i in tqdm(range(0, len(points), self.batch_size), desc="[INFO] Upserting documents"):
            batch = points[i:i+self.batch_size]
            self.client.upsert(
                collection_name=collection_name,
                points=batch
            )
            total_inserted += len(batch)
        
        print(f"[INFO] Upserted {total_inserted} documents to {collection_name}")
        return total_inserted

    def search(
        self,
        collection_name: str,
        query_embedding: np.ndarray,
        limit: int = 10,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Search for similar documents."""
        if limit <= 0:
            return []

        try:
            results = self.client.query_points(
                collection_name=collection_name,
                query=query_embedding.tolist(),
                limit=limit
            ).points
            
            output = []
            for result in results:
                text = result.payload.get("chunk_text", "")
                score = float(result.score)
                
                doc = {
                    "id": str(result.id),
                    "text": text,
                    "score": score,
                    "raw_payload": result.payload, 
                }
                output.append(doc)
            
            return output
        
        except Exception as e:
            print(f"[WARNING] Could not search collection '{collection_name}': {e}")
            return []


    def collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists and has data."""
        try:
            collections = self.client.get_collections()
            collection_names = [c.name for c in collections.collections]
            return collection_name in collection_names
        except Exception as e:
            print(f"[WARNING] Error checking collection existence: {e}")
            return False
