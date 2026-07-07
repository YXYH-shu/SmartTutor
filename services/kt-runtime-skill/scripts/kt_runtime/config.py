from __future__ import annotations

import copy
import os
import tomllib
from typing import Any


KT_RUNTIME_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(KT_RUNTIME_DIR)
SKILL_ROOT = os.path.dirname(SCRIPTS_DIR)
DEFAULT_CONFIG_PATH = os.path.join(SKILL_ROOT, "config", "runtime.toml")
DEFAULT_REKT_CLI_PATH = os.path.join(SKILL_ROOT, "scripts", "kt_runtime", "rekt_engine", "cli.py")
DEFAULT_REKT_DATA_DIR = os.path.join(SKILL_ROOT, "assets", "rekt", "dataset")
DEFAULT_REKT_CHECKPOINT_PATH = os.path.join(SKILL_ROOT, "assets", "rekt", "checkpoint", "rekt.pt")


DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "num_skills": 348,
    },
    "runtime": {
        "backend": "rekt_cli",
        "device": "cuda:0",
    },
    "rekt": {
        "cli_path": DEFAULT_REKT_CLI_PATH,
        "data_dir": DEFAULT_REKT_DATA_DIR,
        "checkpoint_path": DEFAULT_REKT_CHECKPOINT_PATH,
        "max_seq_len": 200,
        "hidden_dim": 128,
        "dropout": 0.4,
        "history_limit": 200,
        "allow_cpu_fallback": True,
    },
    "history": {
        "max_interactions": 300,
        "selection": "recent",
    },
    "prediction": {
        "default_targets": "all",
    },
    "analysis": {
        "enabled": True,
        "max_knowledge_points": 18,
        "max_suggestions": 4,
        "recent_window": 20,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_runtime_config(config_path: str | None = None) -> dict[str, Any]:
    path = config_path or DEFAULT_CONFIG_PATH
    config = copy.deepcopy(DEFAULT_CONFIG)
    if os.path.exists(path):
        with open(path, "rb") as file_obj:
            loaded = tomllib.load(file_obj)
        config = _deep_merge(config, loaded)
    config["_meta"] = {"config_path": path}
    return config
