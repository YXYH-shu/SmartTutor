"""Online predictor adapter for the resource CTR ranking model."""

from __future__ import annotations

import importlib.util
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from hashlib import blake2b
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_CONFIG_PATH = _BACKEND_DIR / "config" / "resource_ranking_model.yaml"
_ALGORITHM_DIR = _BACKEND_DIR / "algorithm" / "resource_recommendation"
_DEFAULT_MODEL_DIR = _ALGORITHM_DIR / "checkpoints" / "smart_tutor_mock_init"
_DEFAULT_SCHEMA_PATH = _DEFAULT_MODEL_DIR / "schema.json"
_DEFAULT_VOCAB_PATH = _DEFAULT_MODEL_DIR / "vocab.json"

# Keep this in sync with backend/algorithm/resource_recommendation/dataset.py.
_TIME_BUCKET_BOUNDARIES = [
    5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60,
    120, 180, 240, 300, 360, 420, 480, 540, 600,
    900, 1200, 1500, 1800, 2100, 2400, 2700, 3000, 3300, 3600,
    5400, 7200, 9000, 10800, 12600, 14400, 16200, 18000, 19800, 21600,
    32400, 43200, 54000, 64800, 75600, 86400,
    172800, 259200, 345600, 432000, 518400, 604800,
    1123200, 1641600, 2160000, 2592000,
    4320000, 6048000, 7776000,
    11664000, 15552000,
    31536000,
]
_NUM_TIME_BUCKETS = len(_TIME_BUCKET_BOUNDARIES) + 1
_FALLBACK_MODEL_CFG = {
    "d_model": 64,
    "emb_dim": 64,
    "num_queries": 1,
    "num_hyformer_blocks": 2,
    "num_heads": 4,
    "seq_encoder_type": "transformer",
    "hidden_mult": 4,
    "dropout_rate": 0.01,
    "seq_top_k": 50,
    "seq_causal": False,
    "action_num": 1,
    "num_time_buckets": _NUM_TIME_BUCKETS,
    "rank_mixer_mode": "full",
    "use_rope": False,
    "rope_base": 10000.0,
    "emb_skip_threshold": 0,
    "seq_id_threshold": 10000,
    "ns_tokenizer_type": "rankmixer",
    "user_ns_tokens": 0,
    "item_ns_tokens": 0,
}
_MODEL_CFG_KEYS = list(_FALLBACK_MODEL_CFG.keys())


@dataclass
class _FeatureLayout:
    entries: list[tuple[int, int, int]]
    vocab_sizes: list[int]

    @property
    def total_dim(self) -> int:
        return sum(length for _, _, length in self.entries)

    def offset_length(self, fid: int) -> tuple[int, int] | None:
        for entry_fid, offset, length in self.entries:
            if entry_fid == fid:
                return offset, length
        return None

    def vocab_at(self, offset: int) -> int:
        if offset < 0 or offset >= len(self.vocab_sizes):
            return 0
        return self.vocab_sizes[offset]


class ResourceRankingPredictor:
    """Pack SmartTutor ranking instances and call PCVRHyFormer when available."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = self._load_config(config)
        self.enabled = bool(self.config.get("enabled", False))
        self.schema = self._load_schema(self._resolve_schema_path())
        self.vocab = self._load_vocab(self._resolve_vocab_path())
        self._model: Any = None
        self._model_input_cls: Any = None
        self._torch: Any = None
        self._device: str = "cpu"

    def predict(self, instances: list[dict[str, Any]]) -> list[float]:
        if not instances or not self.enabled:
            return []
        try:
            self._ensure_model_loaded()
            return self._predict_loaded(instances)
        except Exception as exc:
            logger.warning("[resource_ranking] CTR predictor unavailable: %s", exc)
            return []

    def pack_instances(self, instances: list[dict[str, Any]]) -> dict[str, Any]:
        batch_size = len(instances)
        seq_max_lens = self._seq_max_lens()
        batch = {
            "user_int_feats": self._zeros_int(batch_size, self.schema["user_int"].total_dim),
            "item_int_feats": self._zeros_int(batch_size, self.schema["item_int"].total_dim),
            "user_dense_feats": self._zeros_float(batch_size, self.schema["user_dense"].total_dim),
            "item_dense_feats": self._zeros_float(batch_size, self.schema["item_dense"].total_dim),
            "seq_data": {},
            "seq_lens": {},
            "seq_time_buckets": {},
            "seq_domains": list(self.schema["seq_domains"]),
        }

        for row_index, instance in enumerate(instances):
            self._pack_int_group(batch["user_int_feats"][row_index], self.schema["user_int"], instance, "user_int")
            self._pack_int_group(batch["item_int_feats"][row_index], self.schema["item_int"], instance, "item_int")
            self._pack_dense_group(batch["user_dense_feats"][row_index], self.schema["user_dense"], instance, "user_dense")

        for domain in self.schema["seq_domains"]:
            side_fids = self.schema["seq_side_fids"][domain]
            max_len = seq_max_lens.get(domain, self.config.get("sequence_max_len", 50))
            batch["seq_data"][domain] = [
                [[0 for _ in range(max_len)] for _ in side_fids]
                for _ in instances
            ]
            batch["seq_lens"][domain] = [0 for _ in instances]
            batch["seq_time_buckets"][domain] = [
                [0 for _ in range(max_len)]
                for _ in instances
            ]

        for row_index, instance in enumerate(instances):
            self._pack_sequence_domains(batch, row_index, instance)

        return batch

    def _predict_loaded(self, instances: list[dict[str, Any]]) -> list[float]:
        scores: list[float] = []
        batch_size = max(1, int(self.config.get("batch_size", 64)))
        self._model.eval()
        with self._torch.no_grad():
            for start in range(0, len(instances), batch_size):
                sub_instances = instances[start:start + batch_size]
                packed = self.pack_instances(sub_instances)
                model_input = self._to_model_input(packed)
                logits, _ = self._model.predict(model_input)
                logits = logits.squeeze(-1)
                probs = self._torch.sigmoid(logits).detach().cpu().tolist()
                if isinstance(probs, float):
                    scores.append(float(probs))
                else:
                    scores.extend(float(item) for item in probs)
        return scores

    def _ensure_model_loaded(self) -> None:
        if self._model is not None:
            return
        ckpt_dir = self._resolve_path(self.config.get("ckpt_dir", ""))
        if not ckpt_dir or not ckpt_dir.exists():
            raise FileNotFoundError(f"checkpoint directory not found: {ckpt_dir}")

        ckpt_path = self._find_checkpoint(ckpt_dir)
        train_config = self._load_train_config(ckpt_dir)
        model_cfg = self._resolve_model_cfg(train_config)
        ns_groups = self._load_ns_groups(ckpt_dir, train_config)

        self._torch = self._import_torch()
        model_cls, model_input_cls = self._import_model_classes()
        self._model_input_cls = model_input_cls
        self._device = self._resolve_device(self._torch)

        model = model_cls(
            user_int_feature_specs=self._feature_specs(self.schema["user_int"]),
            item_int_feature_specs=self._feature_specs(self.schema["item_int"]),
            user_dense_dim=self.schema["user_dense"].total_dim,
            item_dense_dim=self.schema["item_dense"].total_dim,
            seq_vocab_sizes=self.schema["seq_domain_vocab_sizes"],
            user_ns_groups=ns_groups["user"],
            item_ns_groups=ns_groups["item"],
            **model_cfg,
        ).to(self._device)
        state_dict = self._torch.load(str(ckpt_path), map_location=self._device)
        model.load_state_dict(state_dict, strict=True)
        self._model = model

    def _to_model_input(self, batch: dict[str, Any]) -> Any:
        torch = self._torch
        return self._model_input_cls(
            user_int_feats=torch.tensor(batch["user_int_feats"], dtype=torch.long, device=self._device),
            item_int_feats=torch.tensor(batch["item_int_feats"], dtype=torch.long, device=self._device),
            user_dense_feats=torch.tensor(batch["user_dense_feats"], dtype=torch.float32, device=self._device),
            item_dense_feats=torch.tensor(batch["item_dense_feats"], dtype=torch.float32, device=self._device),
            seq_data={
                domain: torch.tensor(batch["seq_data"][domain], dtype=torch.long, device=self._device)
                for domain in batch["seq_domains"]
            },
            seq_lens={
                domain: torch.tensor(batch["seq_lens"][domain], dtype=torch.long, device=self._device)
                for domain in batch["seq_domains"]
            },
            seq_time_buckets={
                domain: torch.tensor(batch["seq_time_buckets"][domain], dtype=torch.long, device=self._device)
                for domain in batch["seq_domains"]
            },
        )

    def _pack_int_group(
        self,
        output: list[int],
        layout: _FeatureLayout,
        instance: dict[str, Any],
        group_name: str,
    ) -> None:
        for mapping in self.config.get("feature_mapping", {}).get(group_name, []):
            fid = int(mapping.get("fid", 0))
            loc = layout.offset_length(fid)
            if loc is None:
                continue
            offset, length = loc
            values = self._as_list(self._get_path(instance, mapping.get("path", "")))
            for pos in range(length):
                raw_value = values[pos] if pos < len(values) else None
                vocab_size = layout.vocab_at(offset + pos)
                output[offset + pos] = self._transform_value(raw_value, mapping, vocab_size)

    def _pack_dense_group(
        self,
        output: list[float],
        layout: _FeatureLayout,
        instance: dict[str, Any],
        group_name: str,
    ) -> None:
        for mapping in self.config.get("feature_mapping", {}).get(group_name, []):
            fid = int(mapping.get("fid", 0))
            loc = layout.offset_length(fid)
            if loc is None:
                continue
            base_offset, length = loc
            target_offset = base_offset + max(0, int(mapping.get("offset", 0)))
            if target_offset >= base_offset + length:
                continue
            value = self._get_path(instance, mapping.get("path", ""))
            if isinstance(value, list):
                value = value[0] if value else None
            output[target_offset] = self._to_float(value)

    def _pack_sequence_domains(
        self,
        batch: dict[str, Any],
        row_index: int,
        instance: dict[str, Any],
    ) -> None:
        seq_cfg = self.config.get("feature_mapping", {}).get("seq", {})
        active_domain = self.config.get("sequence_domain", "seq_a")
        interaction_cfg = seq_cfg.get("interaction", {})
        domain = interaction_cfg.get("domain", active_domain)
        if domain not in batch["seq_data"]:
            return

        side_fids = self.schema["seq_side_fids"][domain]
        side_index = {fid: index for index, fid in enumerate(side_fids)}
        max_len = len(batch["seq_time_buckets"][domain][row_index])

        field_values: dict[int, list[int]] = {}
        for mapping in interaction_cfg.get("fields", []):
            fid = int(mapping.get("fid", 0))
            if fid not in side_index:
                continue
            values = self._as_list(self._get_path(instance, mapping.get("path", "")))
            values = values[-max_len:]
            vocab_size = self.schema["seq_vocab_sizes"][domain].get(fid, 0)
            field_values[fid] = [
                self._transform_value(value, mapping, vocab_size)
                for value in values
            ]

        seq_len = min(max((len(values) for values in field_values.values()), default=0), max_len)
        batch["seq_lens"][domain][row_index] = seq_len
        for fid, values in field_values.items():
            slot = side_index[fid]
            batch["seq_data"][domain][row_index][slot][:len(values)] = values

        timestamps = self._as_list(self._get_path(instance, interaction_cfg.get("timestamp_path", "")))[-max_len:]
        batch["seq_time_buckets"][domain][row_index][:len(timestamps)] = [
            self._time_bucket(value)
            for value in timestamps
        ]

    def _load_config(self, override: dict[str, Any] | None) -> dict[str, Any]:
        defaults = {
            "enabled": False,
            "ckpt_dir": "",
            "device": "auto",
            "batch_size": 64,
            "schema_path": str(_DEFAULT_SCHEMA_PATH),
            "vocab_path": str(_DEFAULT_VOCAB_PATH),
            "sequence_domain": "seq_a",
            "sequence_max_len": 20,
            "seq_max_lens": {"seq_a": 20},
            "feature_mapping": {},
        }
        loaded: dict[str, Any] = {}
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh) or {}
        if override:
            loaded = self._deep_merge(loaded, override)
        return self._deep_merge(defaults, loaded)

    def _load_schema(self, schema_path: Path) -> dict[str, Any]:
        with open(schema_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        user_int_cols = list(raw.get("user_int", []))
        user_int = self._int_layout(user_int_cols)
        item_int = self._int_layout(raw.get("item_int", []))
        user_dense = self._dense_layout(raw.get("user_dense", []))
        item_dense = _FeatureLayout(entries=[], vocab_sizes=[])

        seq_cfg = raw.get("seq", {})
        seq_domains = sorted(seq_cfg.keys())
        seq_side_fids: dict[str, list[int]] = {}
        seq_vocab_sizes: dict[str, dict[int, int]] = {}
        seq_domain_vocab_sizes: dict[str, list[int]] = {}
        for domain in seq_domains:
            ts_fid = seq_cfg[domain].get("ts_fid")
            vocab_by_fid = {int(fid): int(vocab) for fid, vocab in seq_cfg[domain].get("features", [])}
            side_fids = [fid for fid in vocab_by_fid if fid != ts_fid]
            seq_side_fids[domain] = side_fids
            seq_vocab_sizes[domain] = vocab_by_fid
            seq_domain_vocab_sizes[domain] = [vocab_by_fid[fid] for fid in side_fids]

        return {
            "user_int": user_int,
            "item_int": item_int,
            "user_dense": user_dense,
            "item_dense": item_dense,
            "seq_domains": seq_domains,
            "seq_side_fids": seq_side_fids,
            "seq_vocab_sizes": seq_vocab_sizes,
            "seq_domain_vocab_sizes": seq_domain_vocab_sizes,
        }

    def _load_vocab(self, vocab_path: Path | None) -> dict[str, Any]:
        if not vocab_path or not vocab_path.exists():
            return {"features": {}}
        with open(vocab_path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            return {"features": {}}
        raw.setdefault("features", {})
        return raw

    def _int_layout(self, cols: list[list[int]]) -> _FeatureLayout:
        entries: list[tuple[int, int, int]] = []
        vocab_sizes: list[int] = []
        offset = 0
        for fid, vocab_size, length in cols:
            entries.append((int(fid), offset, int(length)))
            vocab_sizes.extend([int(vocab_size)] * int(length))
            offset += int(length)
        return _FeatureLayout(entries=entries, vocab_sizes=vocab_sizes)

    def _dense_layout(self, cols: list[list[int]]) -> _FeatureLayout:
        entries: list[tuple[int, int, int]] = []
        offset = 0
        for fid, length in cols:
            fid = int(fid)
            length = int(length)
            entries.append((fid, offset, length))
            offset += length
        return _FeatureLayout(entries=entries, vocab_sizes=[])

    def _load_train_config(self, ckpt_dir: Path) -> dict[str, Any]:
        train_config_path = ckpt_dir / "train_config.json"
        if not train_config_path.exists():
            return {}
        with open(train_config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _resolve_model_cfg(self, train_config: dict[str, Any]) -> dict[str, Any]:
        cfg: dict[str, Any] = {}
        for key in _MODEL_CFG_KEYS:
            if key == "num_time_buckets":
                if "num_time_buckets" in train_config:
                    cfg[key] = train_config[key]
                elif "use_time_buckets" in train_config:
                    cfg[key] = _NUM_TIME_BUCKETS if train_config["use_time_buckets"] else 0
                else:
                    cfg[key] = _FALLBACK_MODEL_CFG[key]
            else:
                cfg[key] = train_config.get(key, _FALLBACK_MODEL_CFG[key])
        return cfg

    def _load_ns_groups(self, ckpt_dir: Path, train_config: dict[str, Any]) -> dict[str, list[list[int]]]:
        ns_groups_path = train_config.get("ns_groups_json")
        if ns_groups_path:
            candidate = ckpt_dir / Path(ns_groups_path).name
            path = candidate if candidate.exists() else self._resolve_path(ns_groups_path)
            if path and path.exists():
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                return {
                    "user": self._fid_groups_to_indexes(raw.get("user_ns_groups", {}), self.schema["user_int"]),
                    "item": self._fid_groups_to_indexes(raw.get("item_ns_groups", {}), self.schema["item_int"]),
                }
        return {
            "user": [[index] for index in range(len(self.schema["user_int"].entries))],
            "item": [[index] for index in range(len(self.schema["item_int"].entries))],
        }

    def _fid_groups_to_indexes(self, groups: dict[str, list[int]], layout: _FeatureLayout) -> list[list[int]]:
        fid_to_index = {fid: index for index, (fid, _, _) in enumerate(layout.entries)}
        indexed = []
        for fids in groups.values():
            group = [fid_to_index[fid] for fid in fids if fid in fid_to_index]
            if group:
                indexed.append(group)
        return indexed or [[index] for index in range(len(layout.entries))]

    def _feature_specs(self, layout: _FeatureLayout) -> list[tuple[int, int, int]]:
        specs = []
        for _, offset, length in layout.entries:
            vocab_size = max(layout.vocab_sizes[offset:offset + length], default=0)
            specs.append((vocab_size, offset, length))
        return specs

    def _import_torch(self) -> Any:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("torch is required for resource CTR ranking") from exc
        return torch

    def _import_model_classes(self) -> tuple[Any, Any]:
        model_path = _ALGORITHM_DIR / "model.py"
        spec = importlib.util.spec_from_file_location("smart_tutor_resource_ranking_model", model_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot import resource ranking model from {model_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.PCVRHyFormer, module.ModelInput

    def _find_checkpoint(self, ckpt_dir: Path) -> Path:
        for path in sorted(ckpt_dir.iterdir()):
            if path.suffix == ".pt":
                return path
        raise FileNotFoundError(f"no .pt checkpoint in {ckpt_dir}")

    def _resolve_schema_path(self) -> Path:
        ckpt_dir = self._resolve_path(self.config.get("ckpt_dir", ""))
        if ckpt_dir and (ckpt_dir / "schema.json").exists():
            return ckpt_dir / "schema.json"
        configured = self._resolve_path(self.config.get("schema_path", ""))
        return configured or _DEFAULT_SCHEMA_PATH

    def _resolve_vocab_path(self) -> Path | None:
        ckpt_dir = self._resolve_path(self.config.get("ckpt_dir", ""))
        if ckpt_dir and (ckpt_dir / "vocab.json").exists():
            return ckpt_dir / "vocab.json"
        return self._resolve_path(self.config.get("vocab_path", ""))

    def _resolve_path(self, value: Any) -> Path | None:
        if not value:
            return None
        path = Path(str(value))
        if path.is_absolute():
            return path
        return (_BACKEND_DIR / path).resolve()

    def _resolve_device(self, torch: Any) -> str:
        device = str(self.config.get("device", "auto"))
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def _seq_max_lens(self) -> dict[str, int]:
        configured = self.config.get("seq_max_lens", {})
        return {
            domain: max(1, int(configured.get(domain, self.config.get("sequence_max_len", 50))))
            for domain in self.schema["seq_domains"]
        }

    def _transform_value(self, value: Any, mapping: dict[str, Any], vocab_size: int = 0) -> int:
        transform = str(mapping.get("transform") or mapping.get("type") or "category")
        if transform in {"numeric_bucket", "numeric_bucket_sequence"}:
            bucket_size = self._to_float(mapping.get("bucket_size", 1)) or 1.0
            bucket = int(self._to_float(value) / bucket_size) + 1 if value is not None else None
            return self._clip_int(bucket, vocab_size)

        vocab_id = self._lookup_vocab_id(value, mapping)
        if vocab_id is not None:
            return self._clip_int(vocab_id, vocab_size)

        numeric = self._to_int(value)
        if numeric is not None:
            return self._clip_int(numeric, vocab_size)
        if value is None or value == "":
            return 0
        return self._hash_to_bucket(value, mapping, vocab_size)

    def _lookup_vocab_id(self, value: Any, mapping: dict[str, Any]) -> int | None:
        features = self.vocab.get("features", {}) if isinstance(self.vocab, dict) else {}
        path = str(mapping.get("path") or "")
        fid = str(mapping.get("fid") or "")
        vocab_entry = features.get(path) or features.get(fid)
        if not isinstance(vocab_entry, dict):
            return None

        values = vocab_entry.get("values", {})
        if not isinstance(values, dict):
            return None

        key = self._vocab_key(value)
        if key in values:
            return self._to_int(values[key])

        unknown = vocab_entry.get("unknown_id", values.get("__UNK__"))
        return self._to_int(unknown)

    def _vocab_key(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    def _hash_to_bucket(self, value: Any, mapping: dict[str, Any], vocab_size: int) -> int:
        if vocab_size <= 1:
            return 0
        namespace = mapping.get("namespace") or mapping.get("path") or mapping.get("fid") or "feature"
        raw = f"{namespace}:{value}".encode("utf-8")
        return int.from_bytes(blake2b(raw, digest_size=8).digest(), "big") % (vocab_size - 1) + 1

    def _clip_int(self, value: Any, vocab_size: int) -> int:
        raw = self._to_int(value)
        if raw is None or raw <= 0:
            return 0
        if vocab_size > 0 and raw >= vocab_size:
            return 0
        return raw

    def _time_bucket(self, value: Any) -> int:
        timestamp = self._to_timestamp(value)
        if timestamp is None:
            return 0
        diff = max(int(time.time()) - timestamp, 0)
        index = 0
        while index < len(_TIME_BUCKET_BOUNDARIES) and _TIME_BUCKET_BOUNDARIES[index] < diff:
            index += 1
        index = min(index, len(_TIME_BUCKET_BOUNDARIES) - 1)
        return index + 1

    def _to_timestamp(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, int | float):
            return int(value)
        if isinstance(value, datetime):
            return int(value.timestamp())
        text = str(value)
        try:
            return int(float(text))
        except ValueError:
            pass
        try:
            return int(datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None

    def _get_path(self, data: dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in str(path).split("."):
            if not part:
                continue
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    def _as_list(self, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple | set):
            return list(value)
        return [value]

    def _to_int(self, value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return int(value)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _to_float(self, value: Any) -> float:
        if value is None or value == "":
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _zeros_int(self, rows: int, cols: int) -> list[list[int]]:
        return [[0 for _ in range(cols)] for _ in range(rows)]

    def _zeros_float(self, rows: int, cols: int) -> list[list[float]]:
        return [[0.0 for _ in range(cols)] for _ in range(rows)]

    def _deep_merge(self, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        merged = dict(left)
        for key, value in right.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged


_predictor: ResourceRankingPredictor | None = None


def get_resource_ranking_predictor() -> ResourceRankingPredictor:
    global _predictor
    if _predictor is None:
        _predictor = ResourceRankingPredictor()
    return _predictor
