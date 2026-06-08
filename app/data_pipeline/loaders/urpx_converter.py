"""urpx conversion helpers."""

import json
from pathlib import Path
from typing import Any, Dict


def urpx_to_json(urpx_path: str) -> Dict[str, Any]:
    """Convert a urpx file to a JSON-friendly structure."""
    try:
        with open(urpx_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        try:
            data = json.loads(content)
            prettified_content = json.dumps(data, indent=2)
            return {
                "name": Path(urpx_path).stem,
                "format": "json",
                "content": {"program.json": prettified_content},
                "main_content": prettified_content,
                "files": ["program.json"],
                "data": data,
            }
        except json.JSONDecodeError:
            return {
                "name": Path(urpx_path).stem,
                "format": "text",
                "content": {"program.txt": content},
                "main_content": content,
                "files": ["program.txt"],
            }

    except Exception as e:
        try:
            return {
                "name": Path(urpx_path).stem,
                "format": "error",
                "error": f"Failed to read file: {str(e)}",
            }
        except Exception:
            return {
                "name": Path(urpx_path).stem,
                "format": "error",
                "error": str(e),
            }
