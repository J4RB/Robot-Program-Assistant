"""Loader for robot program metadata."""
import json
from typing import List, Dict, Any
from dataclasses import dataclass
from tqdm import tqdm
from typing import Optional
from app.utils.config_loader import get_config
from .urpx_converter import urpx_to_json


@dataclass
class ProgramChunk:
    """Represents a chunk of robot program data."""
    program_id: str
    program_name: str
    chunk_text: str
    metadata: Dict[str, Any]
    source_file_path: str
    chunk_index: int = 0


@dataclass
class ProgramCodeChunk:
    """Represents a semantically searchable chunk of robot program code."""
    program_id: str
    program_name: str
    chunk_text: str
    chunk_type: str
    section_name: str
    snippet_path: str
    snippet_text: str
    metadata: Dict[str, Any]
    source_file_path: str
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    chunk_index: int = 0


class ProgramLoader:
    """Load and process robot program metadata from JSON files."""

    def __init__(self):
        config = get_config()
        program_config = config.get_processing_config('robot_programs')
        self.max_code_chunks_per_program = self._parse_optional_positive_int(
            program_config.get('max_code_chunks_per_program')
        )
        self.max_snippet_chars = self._parse_optional_positive_int(
            program_config.get('max_snippet_chars', 4000)
        )
        self.code_action_context_window = self._parse_optional_positive_int(
            program_config.get('code_action_context_window', 1)
        )
        
        # Resolve path relative to workspace root
        workspace_root = config.get_workspace_root()
        self.programs_dir = workspace_root / program_config['dir']
        
        if not self.programs_dir.exists():
            raise FileNotFoundError(f"Programs directory not found: {self.programs_dir}")

    def load_all_programs(self) -> List[ProgramChunk]:
        """Load all robot programs from meta.json files."""
        programs = []
        
        # Find all program directories
        program_dirs = sorted(
            [d for d in self.programs_dir.iterdir() if d.is_dir()],
            key=lambda p: p.name
        )
        
        for program_dir in tqdm(program_dirs, desc="Loading robot programs"):
            meta_file = program_dir / "meta.json"
            if not meta_file.exists():
                print(f"[WARNING] meta.json not found in {program_dir}")
                continue
            
            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                
                program = self._synthesize_program(
                    program_dir_name=program_dir.name,
                    metadata=metadata,
                    source_file_path=str((program_dir / f"{program_dir.name}.urpx").resolve()),
                )
                programs.append(program)
            except Exception as e:
                print(f"[ERROR] Error loading {meta_file}: {e}")
                continue
        
        return programs

    def load_all_program_code_chunks(self) -> List[ProgramCodeChunk]:
        """Load semantically meaningful code chunks from .urpx files."""
        chunks: List[ProgramCodeChunk] = []

        program_dirs = sorted(
            [d for d in self.programs_dir.iterdir() if d.is_dir()],
            key=lambda p: p.name
        )

        for program_dir in tqdm(program_dirs, desc="Loading robot code chunks"):
            meta_file = program_dir / "meta.json"
            urpx_file = program_dir / f"{program_dir.name}.urpx"

            if not meta_file.exists() or not urpx_file.exists():
                continue

            try:
                with open(meta_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                program_json = urpx_to_json(str(urpx_file))
                program_name = metadata.get("name", program_dir.name)
                chunks.extend(
                    self._build_program_code_chunks(
                        program_id="",
                        program_name=program_name,
                        metadata=metadata,
                        program_json=program_json,
                        source_file_path=str(urpx_file.resolve()),
                    )
                )
            except Exception as e:
                print(f"[ERROR] Error loading program code from {program_dir}: {e}")
                continue

        return chunks

    def _synthesize_program(
        self,
        program_dir_name: str,
        metadata: Dict[str, Any],
        source_file_path: str,
    ) -> ProgramChunk:
        """Synthesize text from program metadata."""
        # Extract key fields with defaults
        program_name = metadata.get("name", program_dir_name)
        robot_type = metadata.get("robotType", "Unknown")
        application_type = metadata.get("applicationType", "General")
        gripper_types = metadata.get("gripperType", [])
        object_type = metadata.get("objectType", [])
        actions = metadata.get("actions", [])
        data_available = metadata.get("dataAvailable", "")
        components = metadata.get("components", [])
        
        # Format gripper types
        if isinstance(gripper_types, list):
            gripper_text = ", ".join(gripper_types) if gripper_types else "not specified"
        else:
            gripper_text = str(gripper_types)

        # Format object types
        if isinstance(object_type, list):
            object_text = ", ".join(object_type) if object_type else "not specified"
        else:
            object_text = str(object_type)

        # Format actions
        if isinstance(actions, list):
            action_text = ", ".join(actions) if actions else "not specified"
        else:
            action_text = str(actions)

        # Format components
        if isinstance(components, list):
            component_text = " | ".join(components) if components else "not specified"
        else:
            component_text = str(components)

        # Build synthesized description
        chunk_text = (
            f"Program: {program_name}. "
            f"Robot type: {robot_type}. "
            f"Application: {application_type}. "
            f"Gripper: {gripper_text}. "
            f"Object type: {object_text}. "
            f"Actions: {action_text}. "
            f"Components: {component_text}. "
            f"Data available: {data_available}."
        )

        return ProgramChunk(
            program_id="",
            program_name=program_name,
            chunk_text=chunk_text,
            metadata=metadata,
            source_file_path=source_file_path,
            chunk_index=0
        )

    def _build_program_code_chunks(
        self,
        program_id: str,
        program_name: str,
        metadata: Dict[str, Any],
        program_json: Dict[str, Any],
        source_file_path: str,
    ) -> List[ProgramCodeChunk]:
        """Build action-centric code chunks with JSON snippet references."""
        chunks: List[ProgramCodeChunk] = []
        data = program_json.get("data")

        if not isinstance(data, dict):
            return chunks

        node_entries: List[Dict[str, Any]] = []
        self._collect_nodes(
            node=data.get("program", {}).get("programContent", {}),
            path="program.programContent",
            output=node_entries,
        )

        action_entries: List[Dict[str, Any]] = []
        for entry in node_entries:
            action_name = self._extract_action_name(entry)
            if action_name:
                # annotate original entry so identity is preserved for mapping
                entry["action_name"] = action_name
                action_entries.append(entry)

        action_entries_to_process = (
            action_entries
            if self.max_code_chunks_per_program is None
            else action_entries[:self.max_code_chunks_per_program]
        )
        for idx, entry in enumerate(action_entries_to_process):
            start_line, end_line = self._compute_snippet_line_range(
                program_json, entry["path"], entry["snippet"]
            )

            chunks.append(
                ProgramCodeChunk(
                    program_id=program_id,
                    program_name=program_name,
                    chunk_text=self._build_action_summary(
                        program_name,
                        entry,
                        action_entries_to_process,
                        idx,
                    ),
                    chunk_type="robot_action",
                    section_name=str(entry.get("action_name", "unknown_action")),
                    snippet_path=entry["path"],
                    snippet_text=self._build_readable_snippet(entry),
                    metadata=metadata,
                    source_file_path=source_file_path,
                    chunk_index=idx,
                    start_line=start_line,
                    end_line=end_line,
                )
            )

        # Fallback when no explicit action tokens were discoverable in parameters.
        if not action_entries:
            fallback_nodes = [
                entry for entry in node_entries
                if not entry.get("has_children") and not entry.get("allows_children")
            ]
            fallback_nodes_to_process = (
                fallback_nodes
                if self.max_code_chunks_per_program is None
                else fallback_nodes[:self.max_code_chunks_per_program]
            )
            for idx, entry in enumerate(fallback_nodes_to_process):
                start_line, end_line = self._compute_snippet_line_range(
                    program_json, entry["path"], entry["snippet"]
                )

                chunks.append(
                    ProgramCodeChunk(
                        program_id=program_id,
                        program_name=program_name,
                        chunk_text=self._build_node_summary(program_name, entry),
                        chunk_type="operation_fallback",
                        section_name=entry.get("node_type", "unknown_node"),
                        snippet_path=entry["path"],
                        snippet_text=self._build_readable_snippet(entry),
                        metadata=metadata,
                        source_file_path=source_file_path,
                        chunk_index=idx,
                        start_line=start_line,
                        end_line=end_line,
                    )
                )

        return chunks

    def _collect_nodes(self, node: Any, path: str, output: List[Dict[str, Any]]) -> None:
        """Traverse UR program nodes and collect operation snippets."""
        if isinstance(node, dict):
            contributed = node.get("contributedNode")
            if isinstance(contributed, dict) and contributed.get("type"):
                parameters = contributed.get("parameters") if isinstance(contributed.get("parameters"), dict) else {}
                output.append(
                    {
                        "path": path,
                        "node_type": str(contributed.get("type", "unknown")),
                        "label": self._normalize_label(node.get("programLabel")),
                        "parameter_keys": sorted(parameters.keys()),
                        "has_children": bool(node.get("children")),
                        "allows_children": bool(contributed.get("allowsChildren")),
                        "snippet": {
                            "contributedNode": contributed,
                            "programLabel": node.get("programLabel"),
                        },
                    }
                )

            for key, value in node.items():
                child_path = f"{path}.{key}"
                if isinstance(value, list):
                    for idx, item in enumerate(value):
                        self._collect_nodes(item, f"{child_path}[{idx}]", output)
                else:
                    self._collect_nodes(value, child_path, output)
        elif isinstance(node, list):
            for idx, item in enumerate(node):
                self._collect_nodes(item, f"{path}[{idx}]", output)

    def _build_node_summary(self, program_name: str, entry: Dict[str, Any]) -> str:
        """Create compact natural-language text for embedding."""
        node_type = entry.get("node_type", "unknown")
        label = entry.get("label") or "(no label)"
        snippet = entry.get("snippet", {})
        parameters = snippet.get("contributedNode", {}).get("parameters", {})
        operation_bits = [
            f"Node type: {node_type}",
            f"Label: {label}",
            f"Category: {self._classify_chunk_type(entry)}",
        ]

        for key, value in self._extract_parameter_highlights(parameters):
            operation_bits.append(f"{key}: {value}")

        return (
            f"Program {program_name} operation snippet. "
            + "; ".join(operation_bits)
            + "."
        )

    def _build_action_summary(
        self,
        program_name: str,
        entry: Dict[str, Any],
        ordered_entries: List[Dict[str, Any]],
        entry_idx: int,
    ) -> str:
        """Create compact action-centric text for embedding."""
        action_name = str(entry.get("action_name", "unknown_action"))
        node_type = entry.get("node_type", "unknown")
        label = entry.get("label") or "(no label)"
        snippet = entry.get("snippet", {})
        parameters = snippet.get("contributedNode", {}).get("parameters", {})

        bits = [f"Action: {action_name}", f"Node type: {node_type}", f"Label: {label}"]
        for key, value in self._extract_parameter_highlights(parameters):
            bits.append(f"{key}: {value}")

        context_tokens = self._build_action_context_tokens(ordered_entries, entry_idx)
        if context_tokens:
            bits.append(context_tokens)

        return (
            f"Program {program_name} action snippet. "
            + "; ".join(bits)
            + "."
        )

    def _build_action_context_tokens(self, ordered_entries: List[Dict[str, Any]], entry_idx: int) -> str:
        """Provide neighboring action context to improve retrieval of sequential behavior."""
        if not ordered_entries:
            return ""

        window = self.code_action_context_window or 0
        if window <= 0:
            return ""

        start = max(0, entry_idx - window)
        end = min(len(ordered_entries), entry_idx + window + 1)

        prev_actions = [
            str(ordered_entries[i].get("action_name", ""))
            for i in range(start, entry_idx)
            if ordered_entries[i].get("action_name")
        ]
        next_actions = [
            str(ordered_entries[i].get("action_name", ""))
            for i in range(entry_idx + 1, end)
            if ordered_entries[i].get("action_name")
        ]

        context_bits = []
        if prev_actions:
            context_bits.append(f"Previous actions: {', '.join(prev_actions)}")
        if next_actions:
            context_bits.append(f"Next actions: {', '.join(next_actions)}")
        return "; ".join(context_bits)

    def _extract_action_name(self, entry: Dict[str, Any]) -> str:
        """Extract canonical action token from node parameters when available."""
        snippet = entry.get("snippet", {})
        parameters = snippet.get("contributedNode", {}).get("parameters", {})
        if not isinstance(parameters, dict):
            return ""

        for key in ["moveType", "action", "command", "operation", "mode"]:
            value = parameters.get(key)
            if isinstance(value, (str, int, float, bool)):
                return str(value)

        for key, value in parameters.items():
            key_lower = str(key).lower()
            if not isinstance(value, (str, int, float, bool)):
                continue
            if any(token in key_lower for token in ["action", "type", "mode", "command"]):
                return str(value)

        return ""

    @staticmethod
    def _classify_chunk_type(entry: Dict[str, Any]) -> str:
        """Classify chunk type from structure and parameter schema."""
        parameter_keys = entry.get("parameter_keys") or []
        has_children = bool(entry.get("has_children"))
        allows_children = bool(entry.get("allows_children"))

        if has_children or allows_children:
            return "container"

        if not parameter_keys:
            return "declaration"

        key_set = set(parameter_keys)
        if {"waypoint", "variable"}.issubset(key_set):
            return "pose_operation"

        if "tool" in key_set:
            return "tool_operation"

        # Generic schema-driven fallback that transfers to unseen node types.
        signature = "+".join(parameter_keys[:3])
        return f"operation:{signature}" if signature else "operation"

    @staticmethod
    def _extract_parameter_highlights(parameters: Dict[str, Any]) -> List[tuple[str, str]]:
        """Extract a compact set of parameter descriptors."""
        highlights: List[tuple[str, str]] = []

        preferred_keys = [
            "moveType", "variable", "speed", "acceleration", "tool", "frame",
            "waypoint", "pose", "distance", "force", "mode", "command",
        ]

        ordered_keys: List[str] = []
        for key in preferred_keys:
            if key in parameters:
                ordered_keys.append(key)
        for key in parameters.keys():
            if key not in ordered_keys:
                ordered_keys.append(key)

        for key in ordered_keys:
            value = parameters.get(key)
            normalized = ProgramLoader._parameter_value_to_text(value)
            if normalized and not ProgramLoader._looks_like_noise_token(normalized):
                highlights.append((key, normalized))
            if len(highlights) >= 4:
                break

        return highlights

    @staticmethod
    def _looks_like_noise_token(value: str) -> bool:
        lowered = value.lower()
        if "program-node-label" in lowered:
            return True
        if "translationkey" in lowered:
            return True
        return False

    @staticmethod
    def _parameter_value_to_text(value: Any) -> str:
        if isinstance(value, (str, int, float, bool)):
            return str(value)

        if isinstance(value, dict):
            for nested_key in ["name", "value", "id", "type", "selectedType"]:
                nested_value = value.get(nested_key)
                if isinstance(nested_value, (str, int, float, bool)):
                    return str(nested_value)

        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, (str, int, float, bool)):
                return str(first)

        return ""

    @staticmethod
    def _normalize_label(label: Any) -> str:
        if isinstance(label, str):
            if ProgramLoader._looks_like_noise_token(label):
                return ""
            return label
        if isinstance(label, list):
            parts = []
            for item in label:
                if isinstance(item, dict):
                    params = item.get("interpolateParams")
                    human_param = ProgramLoader._extract_interpolate_param_text(params)
                    if human_param and not ProgramLoader._looks_like_noise_token(human_param):
                        parts.append(human_param)
                        continue

                    primary = item.get("translationKey") or item.get("type")
                    if isinstance(primary, str) and not ProgramLoader._looks_like_noise_token(primary):
                        parts.append(primary)
            return " | ".join(parts)
        return ""

    @staticmethod
    def _extract_interpolate_param_text(params: Any) -> str:
        if not isinstance(params, dict):
            return ""

        preferred_keys = ["name", "value", "id", "speed", "acceleration", "mode", "type"]
        for key in preferred_keys:
            value = params.get(key)
            if isinstance(value, (str, int, float, bool)):
                return str(value)

        for value in params.values():
            if isinstance(value, (str, int, float, bool)):
                return str(value)

        return ""

    def _build_readable_snippet(self, entry: Dict[str, Any]) -> str:
        """Build a human-readable JSON snippet for UI inspection."""
        snippet = entry.get("snippet", {}) if isinstance(entry.get("snippet"), dict) else {}
        contributed = snippet.get("contributedNode", {}) if isinstance(snippet.get("contributedNode"), dict) else {}
        parameters = contributed.get("parameters") if isinstance(contributed.get("parameters"), dict) else {}

        payload = {
            "node_type": entry.get("node_type", "unknown"),
            "action_name": entry.get("action_name"),
            "label": entry.get("label") or "",
            "path": entry.get("path"),
            "parameters": self._sanitize_parameters(parameters),
        }

        return self._truncate_json(payload)

    @staticmethod
    def _compact_value(value: Any) -> Any:
        """Recursively compact entity/selectedType/value wrapper."""
        if isinstance(value, dict):
            # Collapse the PolyScope wrapper: if "value" is a scalar and "selectedType" is present
            if "value" in value and "selectedType" in value:
                inner = value["value"]
                if isinstance(inner, (str, int, float, bool)):
                    return inner
                # value could itself be a nested wrapper (e.g. entity.value is a dict)
                return ProgramLoader._compact_value(inner)
            # Recursively compact remaining dict fields, dropping noise tokens
            result = {}
            for k, v in value.items():
                if k in ("entity",):
                    continue  # entity is just the raw unit-annotated mirror; skip
                compacted = ProgramLoader._compact_value(v)
                if compacted is not None:
                    result[k] = compacted
            return result if result else None
        if isinstance(value, list):
            return [ProgramLoader._compact_value(i) for i in value]
        return value

    @staticmethod
    def _sanitize_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Compact parameters to remove wrapper noise."""
        sanitized: Dict[str, Any] = {}
        for key, value in parameters.items():
            compacted = ProgramLoader._compact_value(value)
            if compacted is None:
                continue
            # Drop top-level string values that are translation key noise
            if isinstance(compacted, str) and ProgramLoader._looks_like_noise_token(compacted):
                continue
            sanitized[key] = compacted
        return sanitized

    def _truncate_json(self, value: Any) -> str:
        """Serialize and trim snippets to avoid oversized payloads."""
        try:
            text = json.dumps(value, ensure_ascii=True, indent=2)
        except TypeError:
            text = str(value)
        if self.max_snippet_chars is None:
            return text
        if len(text) <= self.max_snippet_chars:
            return text
        return text[:self.max_snippet_chars] + "..."

    def _compute_snippet_line_range(self, program_json: Dict[str, Any], path: str, snippet_obj: Any) -> tuple[int, int]:
        """Find the start and end line numbers of a node."""
        main_content = program_json.get("main_content", "")
        if not main_content:
            return (0, 0)

        data_root = program_json.get("data")
        node_obj = None
        if data_root and path:
            try:
                node_obj = self._get_node_by_path(data_root, path)
            except Exception:
                node_obj = None

        guid = None
        if isinstance(node_obj, dict):
            guid = node_obj.get("guid")

        if not guid:
            return (0, 0)

        guid_search = f'"guid": "{guid}"'
        guid_pos = main_content.find(guid_search)
        if guid_pos == -1:
            return (0, 0)

        window_start = max(0, guid_pos - 20000)
        window_text = main_content[window_start:guid_pos]
        cn_key = '"contributedNode"'
        cn_pos_in_window = window_text.rfind(cn_key)
        if cn_pos_in_window == -1:
            return (0, 0)

        cn_abs_pos = window_start + cn_pos_in_window
        start_line = main_content.count("\n", 0, cn_abs_pos) + 1

        brace_count = 0
        started = False
        end_pos = cn_abs_pos
        for i in range(cn_abs_pos, min(len(main_content), cn_abs_pos + 8000)):
            ch = main_content[i]
            if ch == '{':
                brace_count += 1
                started = True
            elif ch == '}':
                brace_count -= 1
            if started and brace_count == 0:
                end_pos = i
                break

        end_line = main_content.count("\n", 0, end_pos) + 1
        return (start_line, end_line)

    def _get_node_by_path(self, root: Any, path: str) -> Any:
        """Navigate the parsed JSON root following a path string like 'program.programContent.children[0]...'."""
        current = root
        if not path:
            return current

        # Split by dots but keep array indices
        parts = path.split('.')
        for part in parts:
            # Handle array indices like 'children[3]'
            while part:
                if '[' in part:
                    prefix, rest = part.split('[', 1)
                    if prefix:
                        current = current.get(prefix)
                    idx_str, remainder = rest.split(']', 1)
                    try:
                        idx = int(idx_str)
                    except Exception:
                        raise KeyError(f"Invalid index in path: {idx_str}")
                    if not isinstance(current, list):
                        raise KeyError(f"Expected list at path segment {part}")
                    current = current[idx]
                    part = remainder.lstrip('.')
                else:
                    # simple key
                    if isinstance(current, dict):
                        current = current.get(part)
                    else:
                        raise KeyError(f"Cannot descend into {type(current)} for key {part}")
                    part = ''
                if current is None:
                    return None

        return current

    def _index_contributed_node_positions(self, main_content: str) -> List[tuple]:
        """Scan the prettified main_content and return list of (start_line, end_line)
        for each occurrence of a 'contributedNode' object in document order."""
        positions: List[tuple] = []
        if not main_content:
            return positions

        lines = main_content.splitlines()
        n = len(lines)
        i = 0
        while i < n:
            line = lines[i]
            if '"contributedNode"' in line:
                # Starting line for the contributedNode block
                start = i + 1
                brace_count = 0
                started = False
                j = i
                while j < n:
                    l = lines[j]
                    for ch in l:
                        if ch == '{':
                            brace_count += 1
                            started = True
                        elif ch == '}':
                            brace_count -= 1
                    if started and brace_count == 0:
                        end = j + 1
                        positions.append((start, end))
                        i = j
                        break
                    j += 1
            i += 1

        return positions
    
    @staticmethod
    def _parse_optional_positive_int(value: Any) -> int | None:
        """Parse positive integer config values; treat null/invalid/non-positive as unlimited."""
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {"", "none", "null", "unlimited"}:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
