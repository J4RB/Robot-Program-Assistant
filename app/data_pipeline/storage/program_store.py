"""SQLite program store."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from app.utils.config_loader import get_config


def _new_program_id() -> str:
    """Create a new globally unique program ID."""
    return str(uuid.uuid4())


class ProgramStore:
    """Persist and retrieve robot program data (code)."""

    def __init__(self):
        config = get_config()
        store_config = config.get_data_pipeline_config().get("program_store", {})
        workspace_root = config.get_workspace_root()
        store_path = workspace_root / store_config.get("path", "program_database/programs.sqlite")

        self.path = Path(store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS programs (
                program_id TEXT PRIMARY KEY,
                program_name TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                program_json TEXT NOT NULL,
                source_file_path TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_programs_source_file_path_unique
            ON programs(source_file_path)
            WHERE source_file_path IS NOT NULL
            """
        )
        self.connection.commit()

    def reset_programs(self) -> None:
        """Delete all program rows."""
        self.connection.execute("DELETE FROM programs")
        self.connection.commit()

    @staticmethod
    def _to_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _from_json(value: str) -> Any:
        return json.loads(value)

    def upsert_program(
        self,
        program_id: Optional[str],
        program_name: str,
        metadata: Dict[str, Any],
        program_json: Dict[str, Any],
        source_file_path: Optional[str] = None,
    ) -> str:
        """Insert a program record and return its program ID."""
        canonical_program_id = (program_id or "").strip()
        if not canonical_program_id:
            canonical_program_id = _new_program_id()

        self.connection.execute(
            """
            INSERT INTO programs (program_id, program_name, metadata_json, program_json, source_file_path, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(program_id) DO UPDATE SET
                program_name=excluded.program_name,
                metadata_json=excluded.metadata_json,
                program_json=excluded.program_json,
                source_file_path=excluded.source_file_path,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                canonical_program_id,
                program_name,
                self._to_json(metadata),
                self._to_json(program_json),
                source_file_path,
            ),
        )
        self.connection.commit()
        return canonical_program_id

    def get_or_create_program_id(
        self,
        program_name: str,
        metadata: Dict[str, Any],
        program_json: Dict[str, Any],
        source_file_path: str,
    ) -> str:
        """Return stable UUID for source file path, creating it once in SQLite."""
        row = self.connection.execute(
            "SELECT program_id FROM programs WHERE source_file_path = ?",
            (source_file_path,),
        ).fetchone()

        existing_program_id = row["program_id"] if row else None
        if existing_program_id:
            self.upsert_program(
                program_id=existing_program_id,
                program_name=program_name,
                metadata=metadata,
                program_json=program_json,
                source_file_path=source_file_path,
            )
            return existing_program_id

        return self.upsert_program(
            program_id=_new_program_id(),
            program_name=program_name,
            metadata=metadata,
            program_json=program_json,
            source_file_path=source_file_path,
        )

    def get_program(self, program_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a program by its id."""
        raw_program_id = (program_id or "").strip()
        row = self.connection.execute(
            "SELECT * FROM programs WHERE program_id = ?",
            (raw_program_id,),
        ).fetchone()

        if row is None:
            return None

        metadata = self._from_json(row["metadata_json"])
        program_json = self._from_json(row["program_json"])

        return {
            "program_id": row["program_id"],
            "program_name": row["program_name"],
            "metadata": metadata,
            "program_json": program_json,
            "source_file_path": row["source_file_path"],
            "updated_at": row["updated_at"],
        }

    def list_program_ids(self) -> Iterable[str]:
        """List all stored program ids."""
        cursor = self.connection.execute("SELECT program_id FROM programs ORDER BY program_id")
        for row in cursor.fetchall():
            yield row["program_id"]

    def close(self) -> None:
        self.connection.close()
