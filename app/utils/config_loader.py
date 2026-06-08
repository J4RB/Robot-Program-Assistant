"""Configuration loader.

Singleton configuration manager that loads configs from YAML files.
"""

import yaml
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigLoader:
    """Load and manage configuration from YAML files."""

    _instance: Optional['ConfigLoader'] = None
    _configs: Dict[str, Dict[str, Any]] = {}

    def __new__(cls):
        """Singleton pattern - only one config instance."""
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize config loader."""
        if not self._configs:
            self._load_all_configs()

    def _load_all_configs(self) -> None:
        """Load all available config files."""
        app_root = Path(__file__).parent.parent

        # Load backend config
        backend_config_path = app_root / "backend" / "config.yaml"
        if backend_config_path.exists():
            self._load_config_file("backend", backend_config_path)

        # Load data_pipeline config
        pipeline_config_path = app_root / "data_pipeline" / "config.yaml"
        if pipeline_config_path.exists():
            self._load_config_file("data_pipeline", pipeline_config_path)

    def _load_config_file(self, section: str, config_path: Path) -> None:
        """Load a single config file."""
        config_path = Path(config_path).resolve()

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                if config:
                    self._configs[section] = config
                    print(f"[INFO] Loaded {section} config from: {config_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to parse config file {config_path}: {e}")

    def load_config(self, config_path: Path, section: str) -> None:
        """Manually override a loaded config section at runtime."""
        if section not in {"backend", "data_pipeline"}:
            raise ValueError(
                "Invalid section. Expected one of: 'backend', 'data_pipeline'"
            )

        # Replace current section config with override file content.
        self._configs.pop(section, None)
        self._load_config_file(section, Path(config_path))

    def get_backend_config(self) -> Dict[str, Any]:
        """Get backend configuration section."""
        return self._configs.get("backend", {})

    def get_data_pipeline_config(self) -> Dict[str, Any]:
        """Get data_pipeline configuration section."""
        return self._configs.get("data_pipeline", {})

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation."""
        keys = key.split('.')

        # If first key is a section name, use that section
        if keys[0] in self._configs:
            section = self._configs[keys[0]]
            remaining_keys = keys[1:]
        else:
            # Search all sections
            section = None
            remaining_keys = keys
            for config in self._configs.values():
                if keys[0] in config:
                    section = config
                    remaining_keys = keys[1:]
                    break

        if section is None:
            return default

        # Navigate through nested keys
        value = section
        for k in remaining_keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value

    @property
    def config(self) -> Dict[str, Dict[str, Any]]:
        """Get all loaded configurations."""
        return self._configs

    # Backend config helpers
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration from backend config."""
        return self.get_backend_config().get('llm', {})

    def get_rag_config(self) -> Dict[str, Any]:
        """Get RAG configuration from backend config."""
        return self.get_backend_config().get('rag', {})

    def get_memory_config(self) -> Dict[str, Any]:
        """Get conversation memory configuration from backend config."""
        return self.get_backend_config().get('memory', {})

    def get_api_config(self) -> Dict[str, Any]:
        """Get API configuration from backend config."""
        return self.get_backend_config().get('api', {})

    def get_formatting_config(self) -> Dict[str, Any]:
        """Get formatting configuration from backend config."""
        return self.get_backend_config().get('formatting', {})

    # Data Pipeline config helpers
    def get_vector_store_config(self) -> Dict[str, Any]:
        """Get vector store configuration from data_pipeline config."""
        return self.get_data_pipeline_config().get('vector_store', {})

    def get_embedding_config(self) -> Dict[str, Any]:
        """Get embedding configuration from data_pipeline config."""
        return self.get_data_pipeline_config().get('embedding', {})

    def get_processing_config(self, processor_name: str = None) -> Dict[str, Any]:
        """Get processing configuration from data_pipeline config."""
        processing = self.get_data_pipeline_config().get('processing', {})
        if processor_name:
            return processing.get(processor_name, {})
        return processing

    def get_workspace_root(self) -> Path:
        """Get the workspace root directory."""
        app_root = Path(__file__).parent.parent
        workspace_root = app_root.parent
        return workspace_root


def get_config() -> ConfigLoader:
    """Get the singleton config instance."""
    return ConfigLoader()
