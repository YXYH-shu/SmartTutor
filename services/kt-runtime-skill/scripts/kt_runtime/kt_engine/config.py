"""KT 工具模型配置。"""

from dataclasses import dataclass
from pathlib import Path
import os


def package_root() -> Path:
    """返回当前 KT 包目录。"""
    return Path(__file__).resolve().parent


def skill_root() -> Path:
    """返回 kt-runtime-skill 根目录。"""
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class KTConfig:
    """KT 推理/训练的运行配置。

    迁移资产时，只需要修改这里的路径或对应环境变量。
    """

    data_dir: Path = skill_root() / "assets" / "kt" / "dataset"
    checkpoint_path: Path = skill_root() / "assets" / "kt" / "checkpoint" / "kt.pt"
    device: str = "cuda:0"
    allow_cpu_fallback: bool = False
    max_seq_len: int = 200
    hidden_dim: int = 128
    dropout: float = 0.4
    history_limit: int = 182

    @classmethod
    def from_env(cls) -> "KTConfig":
        """从环境变量构造配置，未设置时使用默认值。"""
        return cls(
            data_dir=Path(os.getenv("KT_DATA_DIR", cls.data_dir)),
            checkpoint_path=Path(os.getenv("KT_CHECKPOINT", cls.checkpoint_path)),
            device=os.getenv("KT_DEVICE", cls.device),
            allow_cpu_fallback=os.getenv("KT_ALLOW_CPU_FALLBACK", "0") != "0",
            max_seq_len=int(os.getenv("KT_MAX_SEQ_LEN", cls.max_seq_len)),
            hidden_dim=int(os.getenv("KT_HIDDEN_DIM", cls.hidden_dim)),
            dropout=float(os.getenv("KT_DROPOUT", cls.dropout)),
            history_limit=int(os.getenv("KT_HISTORY_LIMIT", cls.history_limit)),
        )
