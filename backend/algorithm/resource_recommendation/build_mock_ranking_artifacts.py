"""Build SmartTutor resource-ranking schema, vocabulary, and checkpoint.

This script is intentionally data-driven from the configured SmartTutor database.
It creates a self-contained checkpoint directory with:

- schema.json
- vocab.json
- ns_groups.json
- train_config.json
- model.pt

Examples:

    python build_mock_ranking_artifacts.py --db-path /data/smart_tutor.sqlite \
        --output-dir checkpoints/smart_tutor_real_init
    SMART_TUTOR_RANKING_SOURCE_DB=/data/smart_tutor.sqlite \
        python build_mock_ranking_artifacts.py --output-dir checkpoints/smart_tutor_real_init
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import torch
import yaml

from model import PCVRHyFormer


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_APP_CONFIG_PATH = BACKEND_DIR / "config" / "app.yaml"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "checkpoints" / "smart_tutor_mock_init"
SOURCE_DB_ENV_KEYS = (
    "SMART_TUTOR_RANKING_SOURCE_DB",
    "SMART_TUTOR_RANKING_SOURCE_DB_PATH",
)
APP_DB_ENV_KEYS = (
    "SMART_TUTOR_DATABASE__URL",
    "DATABASE_URL",
)
TIME_BUCKET_COUNT = 65


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate SmartTutor resource ranking artifacts from a configured SQLite database."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite database file path. Overrides --db-url, environment variables, and app.yaml.",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLite SQLAlchemy URL, e.g. sqlite+aiosqlite:///./smart_tutor.db.",
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_APP_CONFIG_PATH,
        help="Application YAML config used when db path/url is not passed.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seq-max-len", type=int, default=20)
    args = parser.parse_args()

    db_path = resolve_source_db_path(
        db_path=args.db_path,
        db_url=args.db_url,
        config_path=args.config_path,
    )

    torch.manual_seed(args.seed)
    rows = load_source_rows(db_path)
    artifacts = build_artifacts(rows, seq_max_len=args.seq_max_len, seed=args.seed)
    write_artifacts(args.output_dir, artifacts)
    build_checkpoint(args.output_dir, artifacts["schema"], artifacts["train_config"], artifacts["ns_groups"])

    print(f"source database: {db_path}")
    print(f"wrote SmartTutor ranking artifacts to {args.output_dir}")


def resolve_source_db_path(
    db_path: Path | None,
    db_url: str | None,
    config_path: Path,
) -> Path:
    if db_path is not None:
        return normalize_db_path(db_path, BACKEND_DIR, prefer_cwd=True)
    if db_url:
        return database_url_to_path(db_url, BACKEND_DIR, prefer_cwd=True)

    source_env = first_non_empty(*(os.environ.get(key) for key in SOURCE_DB_ENV_KEYS))
    if source_env:
        return database_url_to_path(source_env, BACKEND_DIR, prefer_cwd=True)

    app_env = first_non_empty(*(os.environ.get(key) for key in APP_DB_ENV_KEYS))
    if app_env:
        return database_url_to_path(app_env, BACKEND_DIR, prefer_cwd=False)

    app_yaml_url = read_database_url_from_yaml(config_path)
    if app_yaml_url:
        return database_url_to_path(app_yaml_url, BACKEND_DIR, prefer_cwd=False)

    raise ValueError(
        "No source database configured. Pass --db-path/--db-url, set "
        "SMART_TUTOR_RANKING_SOURCE_DB, or configure database.url in app.yaml."
    )


def first_non_empty(*values: str | None) -> str:
    for value in values:
        if value and str(value).strip():
            return str(value).strip()
    return ""


def read_database_url_from_yaml(config_path: Path) -> str:
    path = normalize_db_path(config_path, BACKEND_DIR, prefer_cwd=True)
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh) or {}
    database = config.get("database") if isinstance(config, dict) else {}
    if not isinstance(database, dict):
        return ""
    return str(database.get("url") or "")


def database_url_to_path(value: str, base_dir: Path, prefer_cwd: bool = False) -> Path:
    value = value.strip()
    if value.startswith("sqlite"):
        database = sqlite_url_database(value)
        return normalize_db_path(Path(database), base_dir, prefer_cwd=prefer_cwd)
    if "://" in value:
        raise ValueError(
            f"Unsupported source database URL: {value}. "
            "The artifact generator currently reads SQLite database files; "
            "pass a SQLite export path with --db-path if production uses another engine."
        )
    return normalize_db_path(Path(value), base_dir, prefer_cwd=prefer_cwd)


def sqlite_url_database(url: str) -> str:
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            database = unquote(url[len(prefix):])
            break
    else:
        raise ValueError(f"Unsupported SQLite URL format: {url}")

    if database in {"", ":memory:"}:
        raise ValueError("In-memory SQLite databases cannot be used for artifact generation.")
    if len(database) >= 3 and database[0] == "/" and database[2] == ":":
        database = database[1:]
    return database


def normalize_db_path(path: Path, base_dir: Path, prefer_cwd: bool = False) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if expanded.is_absolute():
        return expanded.resolve()

    cwd_path = Path.cwd() / expanded
    if prefer_cwd and cwd_path.exists():
        return cwd_path.resolve()
    return (base_dir / expanded).resolve()


def load_source_rows(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"source database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        resources = fetch_all(
            conn,
            """
            SELECT id, name, type, difficult, time_need, full_score, url
            FROM learning_resources
            ORDER BY id
            """,
        )
        knowledge_points = fetch_all(
            conn,
            """
            SELECT id, name, subject, grade, grade_level, cognitive_level, difficult
            FROM knowledge_points
            ORDER BY id
            """,
        )
        resource_knowledge = fetch_all(
            conn,
            """
            SELECT rk.resource_id, rk.kp_id, kp.name AS knowledge_name
            FROM resource_knowledge rk
            LEFT JOIN knowledge_points kp ON rk.kp_id = kp.id
            ORDER BY rk.resource_id, rk.kp_id
            """,
        )
        users = fetch_all(conn, "SELECT id, username FROM users ORDER BY id")
        profiles = fetch_all(
            conn,
            """
            SELECT user_id, knowledge_graph, learning_style, current_level,
                   weak_points, preferences, grade_level
            FROM user_profiles
            ORDER BY user_id
            """,
        )
        interactions = fetch_all(
            conn,
            """
            SELECT learner_id, resource_id, result_type, is_rec, is_correct,
                   score, learn_score, feedback_score, created_at
            FROM learner_resource_interactions
            ORDER BY created_at
            """,
        )
    finally:
        conn.close()

    return {
        "db_path": str(db_path),
        "resources": resources,
        "knowledge_points": knowledge_points,
        "resource_knowledge": resource_knowledge,
        "users": users,
        "profiles": profiles,
        "interactions": interactions,
    }


def fetch_all(conn: sqlite3.Connection, sql: str) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql).fetchall()]


def build_artifacts(rows: dict[str, Any], seq_max_len: int, seed: int) -> dict[str, Any]:
    resource_to_knowledge: dict[str, list[str]] = defaultdict(list)
    for row in rows["resource_knowledge"]:
        resource_to_knowledge[str(row["resource_id"])].extend(
            item
            for item in (row.get("kp_id"), row.get("knowledge_name"))
            if item is not None and str(item) != ""
        )

    knowledge_values = []
    for row in rows["knowledge_points"]:
        knowledge_values.extend([row.get("id"), row.get("name")])

    profile_weak_points = []
    profile_preference_keys = []
    for profile in rows["profiles"]:
        profile_weak_points.extend(as_list_json(profile.get("weak_points")))
        preferences = as_dict_json(profile.get("preferences"))
        profile_preference_keys.extend(preferences.keys())

    result_types = [row.get("result_type") for row in rows["interactions"]]
    result_types.extend(["VIEW", "ANSWER", "INTERACTION"])

    vocab_features = {
        "user_features.user_id": make_vocab(1, [row.get("id") for row in rows["users"]] + [row.get("user_id") for row in rows["profiles"]]),
        "user_features.current_level": make_vocab(2, [row.get("current_level") for row in rows["profiles"]]),
        "user_features.grade_level": make_vocab(3, [row.get("grade_level") for row in rows["profiles"]]),
        "user_features.learning_style": make_vocab(4, [row.get("learning_style") for row in rows["profiles"]]),
        "user_features.weak_points": make_vocab(5, profile_weak_points + knowledge_values),
        "user_features.preference_keys": make_vocab(6, profile_preference_keys),
        "item_features.resource_id": make_vocab(101, [row.get("id") for row in rows["resources"]]),
        "item_features.resource_type": make_vocab(102, [row.get("type") for row in rows["resources"]]),
        "item_features.knowledge_tags": make_vocab(103, knowledge_values),
        "sequence_features.interaction.resource_id_seq": make_vocab(1001, [row.get("id") for row in rows["resources"]]),
        "sequence_features.interaction.resource_type_seq": make_vocab(1002, [row.get("type") for row in rows["resources"]]),
        "sequence_features.interaction.result_type_seq": make_vocab(1003, result_types),
        "sequence_features.interaction.is_rec_seq": make_vocab(1004, ["0", "1"]),
        "sequence_features.interaction.is_correct_seq": make_vocab(1005, ["0", "1"]),
    }

    schema = {
        "user_int": [
            [1, vocab_features["user_features.user_id"]["vocab_size"], 1],
            [2, vocab_features["user_features.current_level"]["vocab_size"], 1],
            [3, vocab_features["user_features.grade_level"]["vocab_size"], 1],
            [4, vocab_features["user_features.learning_style"]["vocab_size"], 1],
            [5, vocab_features["user_features.weak_points"]["vocab_size"], 4],
            [6, vocab_features["user_features.preference_keys"]["vocab_size"], 4],
        ],
        "item_int": [
            [101, vocab_features["item_features.resource_id"]["vocab_size"], 1],
            [102, vocab_features["item_features.resource_type"]["vocab_size"], 1],
            [103, vocab_features["item_features.knowledge_tags"]["vocab_size"], 4],
            [104, 12, 1],
            [105, 64, 1],
            [106, 3, 1],
            [107, 102, 1],
        ],
        "user_dense": [
            [201, 1],
            [202, 1],
            [203, 1],
        ],
        "seq": {
            "seq_a": {
                "prefix": "resource_interaction_seq",
                "ts_fid": 1000,
                "features": [
                    [1001, vocab_features["sequence_features.interaction.resource_id_seq"]["vocab_size"]],
                    [1000, 2147483647],
                    [1002, vocab_features["sequence_features.interaction.resource_type_seq"]["vocab_size"]],
                    [1003, vocab_features["sequence_features.interaction.result_type_seq"]["vocab_size"]],
                    [1004, vocab_features["sequence_features.interaction.is_rec_seq"]["vocab_size"]],
                    [1005, vocab_features["sequence_features.interaction.is_correct_seq"]["vocab_size"]],
                    [1006, 12],
                    [1007, 12],
                    [1008, 7],
                ],
            }
        },
    }

    vocab = {
        "metadata": {
            "source_db": rows["db_path"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "resource_count": len(rows["resources"]),
            "knowledge_point_count": len(rows["knowledge_points"]),
            "user_count": len(rows["users"]),
            "interaction_count": len(rows["interactions"]),
            "unknown_id": 1,
        },
        "features": vocab_features,
    }

    ns_groups = {
        "user_ns_groups": {
            "U_PROFILE": [1, 2, 3, 4, 5, 6],
        },
        "item_ns_groups": {
            "I_RESOURCE": [101, 102, 103, 104, 105, 106, 107],
        },
    }

    train_config = {
        "seed": seed,
        "schema_path": "schema.json",
        "ns_groups_json": "ns_groups.json",
        "seq_max_lens": f"seq_a:{seq_max_len}",
        "d_model": 64,
        "emb_dim": 32,
        "num_queries": 1,
        "num_hyformer_blocks": 2,
        "num_heads": 4,
        "seq_encoder_type": "transformer",
        "hidden_mult": 4,
        "dropout_rate": 0.01,
        "seq_top_k": 20,
        "seq_causal": False,
        "action_num": 1,
        "use_time_buckets": True,
        "num_time_buckets": TIME_BUCKET_COUNT,
        "rank_mixer_mode": "full",
        "use_rope": False,
        "rope_base": 10000.0,
        "emb_skip_threshold": 0,
        "seq_id_threshold": 10000,
        "ns_tokenizer_type": "rankmixer",
        "user_ns_tokens": 1,
        "item_ns_tokens": 1,
        "note": "Randomly initialized from SmartTutor source database; not trained.",
    }

    metadata = {
        "source_db": rows["db_path"],
        "generated_at": vocab["metadata"]["generated_at"],
        "seq_max_len": seq_max_len,
        "resource_ids": [row.get("id") for row in rows["resources"]],
        "warning": "This checkpoint is randomly initialized and only validates the online model path.",
    }

    return {
        "schema": schema,
        "vocab": vocab,
        "ns_groups": ns_groups,
        "train_config": train_config,
        "metadata": metadata,
    }


def make_vocab(fid: int, values: list[Any]) -> dict[str, Any]:
    cleaned = sorted({str(value) for value in values if value is not None and str(value) != ""})
    mapping = {"__UNK__": 1}
    for index, value in enumerate(cleaned, start=2):
        mapping[value] = index
    return {
        "fid": fid,
        "unknown_id": 1,
        "vocab_size": max(mapping.values()) + 1,
        "values": mapping,
    }


def as_list_json(value: Any) -> list[Any]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        return parsed if isinstance(parsed, list) else []
    return []


def as_dict_json(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def write_artifacts(output_dir: Path, artifacts: dict[str, Any]) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "schema.json", artifacts["schema"])
    write_json(output_dir / "vocab.json", artifacts["vocab"])
    write_json(output_dir / "ns_groups.json", artifacts["ns_groups"])
    write_json(output_dir / "train_config.json", artifacts["train_config"])
    write_json(output_dir / "generation_metadata.json", artifacts["metadata"])


def write_json(path: Path, payload: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def build_checkpoint(
    output_dir: Path,
    schema: dict[str, Any],
    train_config: dict[str, Any],
    ns_groups: dict[str, Any],
) -> None:
    user_int_feature_specs = build_feature_specs(schema["user_int"])
    item_int_feature_specs = build_feature_specs(schema["item_int"])
    seq_vocab_sizes = build_seq_vocab_sizes(schema["seq"])
    user_fid_to_index = {fid: index for index, (fid, _, _) in enumerate(build_layout(schema["user_int"])[0])}
    item_fid_to_index = {fid: index for index, (fid, _, _) in enumerate(build_layout(schema["item_int"])[0])}
    user_ns_groups = [
        [user_fid_to_index[fid] for fid in fids if fid in user_fid_to_index]
        for fids in ns_groups["user_ns_groups"].values()
    ]
    item_ns_groups = [
        [item_fid_to_index[fid] for fid in fids if fid in item_fid_to_index]
        for fids in ns_groups["item_ns_groups"].values()
    ]

    model = PCVRHyFormer(
        user_int_feature_specs=user_int_feature_specs,
        item_int_feature_specs=item_int_feature_specs,
        user_dense_dim=sum(int(length) for _, length in schema["user_dense"]),
        item_dense_dim=0,
        seq_vocab_sizes=seq_vocab_sizes,
        user_ns_groups=user_ns_groups,
        item_ns_groups=item_ns_groups,
        d_model=train_config["d_model"],
        emb_dim=train_config["emb_dim"],
        num_queries=train_config["num_queries"],
        num_hyformer_blocks=train_config["num_hyformer_blocks"],
        num_heads=train_config["num_heads"],
        seq_encoder_type=train_config["seq_encoder_type"],
        hidden_mult=train_config["hidden_mult"],
        dropout_rate=train_config["dropout_rate"],
        seq_top_k=train_config["seq_top_k"],
        seq_causal=train_config["seq_causal"],
        action_num=train_config["action_num"],
        num_time_buckets=train_config["num_time_buckets"],
        rank_mixer_mode=train_config["rank_mixer_mode"],
        use_rope=train_config["use_rope"],
        rope_base=train_config["rope_base"],
        emb_skip_threshold=train_config["emb_skip_threshold"],
        seq_id_threshold=train_config["seq_id_threshold"],
        ns_tokenizer_type=train_config["ns_tokenizer_type"],
        user_ns_tokens=train_config["user_ns_tokens"],
        item_ns_tokens=train_config["item_ns_tokens"],
    )
    model.eval()
    torch.save(model.state_dict(), output_dir / "model.pt")


def build_layout(cols: list[list[int]]) -> tuple[list[tuple[int, int, int]], list[int]]:
    entries = []
    vocab_sizes = []
    offset = 0
    for fid, vocab_size, length in cols:
        entries.append((int(fid), offset, int(length)))
        vocab_sizes.extend([int(vocab_size)] * int(length))
        offset += int(length)
    return entries, vocab_sizes


def build_feature_specs(cols: list[list[int]]) -> list[tuple[int, int, int]]:
    entries, vocab_sizes = build_layout(cols)
    specs = []
    for _, offset, length in entries:
        specs.append((max(vocab_sizes[offset:offset + length]), offset, length))
    return specs


def build_seq_vocab_sizes(seq_schema: dict[str, Any]) -> dict[str, list[int]]:
    result = {}
    for domain, config in sorted(seq_schema.items()):
        ts_fid = int(config["ts_fid"])
        result[domain] = [
            int(vocab_size)
            for fid, vocab_size in config["features"]
            if int(fid) != ts_fid
        ]
    return result


if __name__ == "__main__":
    main()
