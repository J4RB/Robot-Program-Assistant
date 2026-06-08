#!/usr/bin/env python
"""Script to build the databases.

Usage:
    python data_pipeline/build_vector_database.py
    python data_pipeline/build_vector_database.py --config /path/to/config.yaml
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

# Add repo/app roots to path
app_root = Path(__file__).parent.parent
repo_root = app_root.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(app_root))

from data_pipeline.loaders import DocumentLoader, ProgramLoader, urpx_to_json
from data_pipeline.embedding import EmbeddingModel
from data_pipeline.storage import ProgramStore, VectorStore
from app.utils.config_loader import get_config


def load_documents(doc_loader: DocumentLoader) -> List:
    """Load and chunk documentation PDFs."""
    print("Scanning documentation...")
    
    try:
        doc_chunks = doc_loader.load_pdfs()
        print(f"Total documentation chunks: {len(doc_chunks)}\n")
        return doc_chunks
    except Exception as e:
        print(f"[ERROR] Error loading documentation: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return []


def index_programs(
    vector_store: VectorStore,
    embedding_model: EmbeddingModel,
    program_chunks: List,
    collection_name: str = "robot_programs",
) -> int:
    """Index programs into vector store."""
    if not program_chunks:
        print("No programs to index")
        return 0
    
    print(f"Indexing {len(program_chunks)} programs...")
    
    try:
        # Get embeddings
        texts = [chunk.chunk_text for chunk in program_chunks]
        print(f"[INFO] Embedding {len(texts)} programs...")
        embeddings = embedding_model.embed(texts)

        # Create collection with model-specific vector size
        vector_store.create_collection(
            collection_name,
            recreate=True,
            vector_size=int(embeddings.shape[1]),
        )
        
        # Upsert to vector store
        vector_store.upsert_documents(
            collection_name=collection_name,
            documents=program_chunks,
            embeddings=embeddings,
            doc_type="program"
        )
        
        print(f"  Indexed {len(program_chunks)} programs\n")
        return len(program_chunks)
        
    except Exception as e:
        print(f"  [ERROR] Error indexing programs: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return 0


def index_program_code_chunks(
    vector_store: VectorStore,
    embedding_model: EmbeddingModel,
    code_chunks: List,
    collection_name: str = "robot_program_code",
) -> int:
    """Index robot program code chunks into vector store."""
    if not code_chunks:
        print("No robot program code chunks to index")
        return 0

    print(f"Indexing {len(code_chunks)} robot program code chunks...")

    try:
        texts = [chunk.chunk_text for chunk in code_chunks]
        print(f"[INFO] Embedding {len(texts)} code chunks...")
        embeddings = embedding_model.embed(texts)

        vector_store.create_collection(
            collection_name,
            recreate=True,
            vector_size=int(embeddings.shape[1]),
        )

        vector_store.upsert_documents(
            collection_name=collection_name,
            documents=code_chunks,
            embeddings=embeddings,
            doc_type="program_code",
        )

        print(f"  Indexed {len(code_chunks)} robot code chunks\n")
        return len(code_chunks)

    except Exception as e:
        print(f"  [ERROR] Error indexing robot code chunks: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return 0


def index_program_store(program_store: ProgramStore, program_loader: ProgramLoader) -> tuple[int, Dict[str, str]]:
    """Populate SQLite."""
    if not program_loader.programs_dir.exists():
        print("No programs directory found for program store indexing")
        return 0, {}

    indexed = 0
    program_id_by_source_path: Dict[str, str] = {}
    program_dirs = sorted([d for d in program_loader.programs_dir.iterdir() if d.is_dir()], key=lambda p: p.name)

    for program_dir in program_dirs:
        urpx_file = program_dir / f"{program_dir.name}.urpx"
        meta_file = program_dir / "meta.json"

        if not urpx_file.exists() or not meta_file.exists():
            continue

        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            source_file_path = str(urpx_file.resolve())
            program_json = urpx_to_json(source_file_path)
            program_id = program_store.get_or_create_program_id(
                program_name=metadata.get("name", program_dir.name),
                metadata=metadata,
                program_json=program_json,
                source_file_path=source_file_path,
            )

            program_id_by_source_path[source_file_path] = program_id
            indexed += 1
        except Exception as e:
            print(f"  [ERROR] Error indexing program store entry for {program_dir.name}: {str(e)}")

    print(f"  Indexed {indexed} programs into program store\n")
    return indexed, program_id_by_source_path


def apply_program_ids_to_chunks(
    program_chunks: List,
    program_code_chunks: List,
    program_id_by_source_path: Dict[str, str],
) -> None:
    """Assign SQLite UUIDs to in-memory chunks before vector indexing."""
    missing_program_chunk_ids = 0
    for chunk in program_chunks:
        source_file_path = str(Path(chunk.source_file_path).resolve())
        program_id = program_id_by_source_path.get(source_file_path)
        if program_id:
            chunk.program_id = program_id
        else:
            missing_program_chunk_ids += 1

    missing_code_chunk_ids = 0
    for chunk in program_code_chunks:
        source_file_path = str(Path(chunk.source_file_path).resolve())
        program_id = program_id_by_source_path.get(source_file_path)
        if program_id:
            chunk.program_id = program_id
        else:
            missing_code_chunk_ids += 1

    if missing_program_chunk_ids or missing_code_chunk_ids:
        raise RuntimeError(
            "Missing SQLite UUID mapping for "
            f"{missing_program_chunk_ids} program chunk(s) and {missing_code_chunk_ids} code chunk(s)."
        )


def index_documentation(
    vector_store: VectorStore,
    embedding_model: EmbeddingModel,
    doc_chunks: List,
    collection_name: str = "documentation",
) -> int:
    """Index documentation into vector store."""
    if not doc_chunks:
        print("No documentation chunks to index")
        return 0
    
    print(f"Indexing {len(doc_chunks)} documentation chunks...")
    
    try:
        # Get embeddings
        chunk_texts = [chunk.chunk_text for chunk in doc_chunks]
        print(f"[INFO] Embedding {len(chunk_texts)} chunks...")
        embeddings = embedding_model.embed(chunk_texts)

        # Create collection with model-specific vector size
        vector_store.create_collection(
            collection_name,
            recreate=True,
            vector_size=int(embeddings.shape[1]),
        )
        
        # Upsert to vector store
        vector_store.upsert_documents(
            collection_name=collection_name,
            documents=doc_chunks,
            embeddings=embeddings,
            doc_type="documentation"
        )
        
        print(f"  Indexed {len(doc_chunks)} documentation chunks\n")
        return len(doc_chunks)
        
    except Exception as e:
        print(f"  [ERROR] Error indexing documentation: {str(e)}\n")
        import traceback
        traceback.print_exc()
        return 0


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build the databases"
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to data pipeline YAML config file (overrides app/data_pipeline/config.yaml)"
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("Vector Database Builder")
    print("=" * 70)
    print()
    
    try:
        # Load configuration with override support
        config = get_config()
        if args.config:
            config.load_config(Path(args.config), section="data_pipeline")
        
        # Get workspace root
        workspace_root = config.get_workspace_root()
        rag_collections = config.get_rag_config().get("collections", {})
        programs_collection = rag_collections.get("programs", "robot_programs")
        program_code_collection = rag_collections.get("program_code", "robot_program_code")
        docs_collection = rag_collections.get("documentation", "documentation")
        
        print(f"Workspace: {workspace_root}")
        print()
        
        # Initialize services
        print("Initializing services...")
        
        embedding_model = EmbeddingModel()
        embedding_config = config.get_embedding_config()
        print(f"  [INFO] Embedding model: {embedding_config.get('model_name', 'all-MiniLM-L6-v2')}")
        
        vector_store = VectorStore()
        print(f"  [INFO] Vector store initialized")
        vector_store.reset_storage()
        print(f"  [INFO] Vector store reset for clean rebuild")

        program_store = ProgramStore()
        print(f"  [INFO] Program store initialized")
        program_store.reset_programs()
        print(f"  [INFO] Program store reset for clean rebuild")
        
        program_loader = ProgramLoader()
        print(f"  [INFO] Program loader initialized")
        
        doc_loader = DocumentLoader()
        doc_config = config.get_processing_config('documentation')
        chunk_size = doc_config.get('chunk_size')
        chunk_overlap = doc_config.get('overlap')
        print(f"  [INFO] Document loader (chunk_size={chunk_size} tokens, overlap={chunk_overlap} tokens)\n")
        
        # Load data
        print("Loading data...")
        program_chunks = program_loader.load_all_programs()
        program_code_chunks = program_loader.load_all_program_code_chunks()
        doc_chunks = load_documents(doc_loader)

        programs_stored, program_id_by_source_path = index_program_store(program_store, program_loader)
        apply_program_ids_to_chunks(program_chunks, program_code_chunks, program_id_by_source_path)

        print(f"Programs loaded: {len(program_chunks)}")
        print(f"Program code chunks loaded: {len(program_code_chunks)}")
        print(f"Documentation chunks loaded: {len(doc_chunks)}\n")
        
        # Index data
        print("=" * 70)
        print("Indexing Data")
        print("=" * 70)
        print()
        
        programs_indexed = index_programs(
            vector_store,
            embedding_model,
            program_chunks,
            collection_name=programs_collection,
        )
        code_chunks_indexed = index_program_code_chunks(
            vector_store,
            embedding_model,
            program_code_chunks,
            collection_name=program_code_collection,
        )
        docs_indexed = index_documentation(
            vector_store,
            embedding_model,
            doc_chunks,
            collection_name=docs_collection,
        )
        
        # Summary
        print("=" * 70)
        print("Build Complete!")
        print("=" * 70)
        print(f"Program metadata indexed:   {programs_indexed}")
        print(f"Code chunks indexed:{code_chunks_indexed}")
        print(f"Programs stored:    {programs_stored}")
        print(f"Docs indexed:       {docs_indexed}")
        print(f"Total items:        {programs_indexed + code_chunks_indexed + docs_indexed + programs_stored}")
        print()
        print("Vector databases are ready for use.")
        print()
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 70)
        print("Build Failed!")
        print("=" * 70)
        print(f"Error: {str(e)}")
        print()
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
