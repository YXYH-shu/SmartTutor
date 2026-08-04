"""KT 打分器的抽象接口（端口）。

学习路径规划的搜索算法（`search/genetic_algorithm.py`）只依赖这个接口，
不依赖任何具体的知识追踪模型实现。新增一个模型后端（DKT / SAKT / REKT /
未来任何模型），只需要实现这个接口，不需要改动搜索算法本身。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import torch


@runtime_checkable
class KTScorer(Protocol):
    """统一的 KT 模型打分接口。

    约定（和 DSMOEA 原始 DKT/SAKT 调用惯例保持一致，方便迁移）：

    - `hist_q` / `hist_a`：形状 [B, L]，表示"已经发生的历史交互"
      （历史题目 id 和对应作答 0/1），按时间顺序排列。
    - `next_q`：形状 [B, L]，与 hist_q 对齐的"下一题"序列；除最后一位外，
      其余位置的取值调用方保证与 hist_q 整体右移一位一致（不同后端是否
      使用这些位置由具体实现决定），**只有最后一位是本次真正要评估的
      候选题目**。
    - 返回：形状 [B, L] 或至少 [B] 的预测正确率；调用方只会读取最后一位
      `[:, -1]`。

    这样设计的原因：DKT/SAKT 的 `next_q` 各位置互相独立、只有最后一位
    被读取；而 REKT 是自回归的，需要把 hist_q/hist_a 和新候选题拼接成
    一条完整的交互链才能正确计算——但两者都可以通过这同一个函数签名表达，
    差异被封装在各自的 `forward_batch` 实现里，搜索算法完全不用关心。
    """

    def forward_batch(
        self, hist_q: torch.Tensor, hist_a: torch.Tensor, next_q: torch.Tensor
    ) -> torch.Tensor:
        """单次批量前向，返回预测正确率序列。"""
        ...

    def skills_of(self, question_id: int) -> list[int]:
        """返回某道题关联的知识点 id 列表。"""
        ...

    def questions_of_skill(self, skill_id: int) -> list[int]:
        """返回某个知识点关联的题目 id 列表（技能 -> 题目反向索引）。"""
        ...

    @property
    def question_universe_size(self) -> int:
        """候选题目池大小（题目 id 的取值上界）。"""
        ...

    @property
    def device(self) -> torch.device:
        ...
