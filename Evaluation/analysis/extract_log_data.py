from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def extract_log_data(root: Path) -> None:
    data_dir = root / "Evaluation" / "data"
    log_dir = data_dir / "participants"

    raw_sessions_path = data_dir / "assistant_logs_raw_sessions.csv"
    raw_embeddings_path = data_dir / "assistant_logs_raw_embeddings.csv"
    manual_task_extraction_path = data_dir / "assistant_task_extraction.csv"

    log_rows: list[dict[str, float | int | str | None]] = []
    embedding_rows: list[dict[str, float | int | str]] = []

    existing_task_ids: dict[str, str] = {}
    if manual_task_extraction_path.exists():
        try:
            existing_sessions_df = pd.read_csv(manual_task_extraction_path)
            if "task_id" in existing_sessions_df.columns:
                existing_task_ids = {
                    str(row["session_id"]): str(row["task_id"])
                    for _, row in existing_sessions_df[["session_id", "task_id"]].dropna().iterrows()
                    if str(row["task_id"]).strip() and str(row["task_id"]).strip().lower() != "nan"
                }
        except Exception:
            existing_task_ids = {}

    for log_path in log_dir.glob("*/logs/*.json"):
        try:
            log_data = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        start_time = log_data.get("start_time")
        end_time = log_data.get("end_time")
        if not start_time or not end_time:
            continue

        try:
            duration_s = (datetime.fromisoformat(end_time) - datetime.fromisoformat(start_time)).total_seconds()
        except Exception:
            continue

        events = log_data.get("events", [])
        session_id = str(log_data.get("session_id", log_path.stem))
        task_id = log_data.get("task_id")
        if task_id is None or str(task_id).strip() == "":
            task_id = existing_task_ids.get(session_id)

        tool_calls = sum(1 for e in events if e.get("type") == "tool_call")

        program_context = None
        for event in events:
            if event.get("type") == "user_input":
                program_context = event.get("data", {}).get("settings", {}).get("program_context")
                break

        embedding_ms: list[float] = []
        for event_index, event in enumerate(events):
            if event.get("type") != "per_tool_embedding":
                continue
            value = event.get("data", {}).get("embedding_time_ms")
            if not isinstance(value, (int, float)):
                continue
            value_float = float(value)
            embedding_ms.append(value_float)
            embedding_rows.append(
                {
                    "participant": log_path.parts[-3],
                    "session_id": session_id,
                    "event_index": int(event_index),
                    "embedding_time_ms": value_float,
                    "source_log": str(log_path.relative_to(root)),
                }
            )

        log_rows.append(
            {
                "participant": log_path.parts[-3],
                "session_id": session_id,
                "task_id": task_id,
                "start_time": str(start_time),
                "end_time": str(end_time),
                "duration_s": float(duration_s),
                "tool_calls": int(tool_calls),
                "program_context": bool(program_context),
                "embedding_calls": int(len(embedding_ms)),
                "embedding_ms_sum": float(sum(embedding_ms)) if embedding_ms else 0.0,
                "source_log": str(log_path.relative_to(root)),
            }
        )

    sessions_columns = [
        "participant",
        "session_id",
        "task_id",
        "start_time",
        "end_time",
        "duration_s",
        "tool_calls",
        "program_context",
        "embedding_calls",
        "embedding_ms_sum",
        "source_log",
    ]
    embeddings_columns = [
        "participant",
        "session_id",
        "event_index",
        "embedding_time_ms",
        "source_log",
    ]

    pd.DataFrame(log_rows, columns=sessions_columns).to_csv(raw_sessions_path, index=False)
    pd.DataFrame(embedding_rows, columns=embeddings_columns).to_csv(raw_embeddings_path, index=False)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    extract_log_data(root)


if __name__ == "__main__":
    main()
