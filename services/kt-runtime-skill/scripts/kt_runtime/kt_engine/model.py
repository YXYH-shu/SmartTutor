"""KT 神经网络模型。

本文件中的参数命名刻意保持与 `TZB_raw/kt/model.py` 一致，因此旧版
`kt.pth` 权重可以不经过转换直接加载。
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class KT(nn.Module):
    """Revisiting Knowledge Tracing 模型。

    KT 同时维护三类知识状态：
    - problem/question state：学生对具体题目的掌握状态；
    - skill/concept state：学生对相关知识点的掌握状态；
    - domain state：学生在整个学习领域上的整体掌握状态。
    """

    def __init__(
        self,
        qst_num: int,
        skl_num: int,
        max_seq_len: int = 400,
        d: int = 128,
        dropout: float = 0.4,
    ) -> None:
        super().__init__()

        self.pro_max = qst_num
        self.skill_max = skl_num
        self.max_seq_len = max_seq_len

        # 题目、知识点、答题结果的可学习向量表示。
        self.pro_embed = nn.Parameter(torch.rand(self.pro_max, d))
        self.skill_embed = nn.Parameter(torch.rand(self.skill_max, d))
        self.ans_embed = nn.Parameter(torch.rand(2, d))

        # 最终预测头会拼接“领域状态、题目状态、知识点状态、当前题目表示”，所以输入维度是 4d。
        self.out = nn.Sequential(
            nn.Linear(4 * d, d),
            nn.ReLU(),
            nn.Dropout(p=dropout),
            nn.Linear(d, 1),
        )

        self.dropout = nn.Dropout(p=dropout)
        self.time_embed = nn.Parameter(torch.rand(200, d))

        # 领域初始状态；`c_state` 当前不参与 forward，但保留以兼容 raw 版本 checkpoint。
        self.ls_state = nn.Parameter(torch.rand(1, d))
        self.c_state = nn.Parameter(torch.rand(1, d))

        # 题目状态与知识点状态的初始表，按序列位置取用。
        self.pro_state = nn.Parameter(torch.rand(self.max_seq_len, d))
        self.skill_state = nn.Parameter(torch.rand(self.max_seq_len, d))

        # FRU 中的遗忘门和更新单元：分别作用于题目、知识点、领域三类状态。
        self.obtain_pro_forget = nn.Sequential(nn.Linear(2 * d, d), nn.Sigmoid())
        self.obtain_pro_state = nn.Sequential(nn.Linear(2 * d, d))
        self.obtain_all_forget = nn.Sequential(nn.Linear(2 * d, d), nn.Sigmoid())
        self.obtain_skill_forget = nn.Sequential(nn.Linear(2 * d, d), nn.Sigmoid())
        self.obtain_skill_state = nn.Sequential(nn.Linear(2 * d, d))
        self.obtain_all_state = nn.Sequential(nn.Linear(2 * d, d))

        # Rasch 风格难度项：题目难度标量 * 知识点变化向量。
        self.akt_pro_diff = nn.Parameter(torch.rand(self.pro_max, 1))
        self.akt_pro_change = nn.Parameter(torch.rand(self.skill_max, d))

    def forward(
        self,
        last_problem: torch.Tensor,
        next_problem: torch.Tensor,
        next_skill: torch.Tensor,
        next_ans: torch.Tensor,
    ) -> torch.Tensor:
        """预测每个下一题被答对的概率。

        Args:
            last_problem: 历史题目 id，形状为 [batch, seq]。
            next_problem: 下一时刻题目 id，形状为 [batch, seq]。
            next_skill: 下一时刻题目的主知识点 id，形状为 [batch, seq]。
            next_ans: 下一时刻答题结果，形状为 [batch, seq]。
        """
        device = last_problem.device
        batch = last_problem.shape[0]
        seq = last_problem.shape[-1]

        if seq > self.max_seq_len:
            raise ValueError(f"sequence length {seq} exceeds max_seq_len={self.max_seq_len}")

        # 题目表示 = 题目向量 + 知识点向量 + 题目难度调制项。
        next_pro_embed = (
            F.embedding(next_problem, self.pro_embed)
            + F.embedding(next_skill, self.skill_embed)
            + F.embedding(next_problem, self.akt_pro_diff)
            * F.embedding(next_skill, self.akt_pro_change)
        )
        # 当前交互表示 X_t = 题目表示 E_t + 答题结果表示 R_t。
        next_x = next_pro_embed + F.embedding(next_ans.long(), self.ans_embed)

        # 记录每道题/每个知识点上一次出现的位置，用于计算遗忘间隔。
        last_pro_time = torch.zeros((batch, self.pro_max), device=device)
        last_skill_time = torch.zeros((batch, self.skill_max), device=device)

        # 三类知识状态的初始值。
        pro_state = self.pro_state[:seq].unsqueeze(0).repeat(batch, 1, 1)
        skill_state = self.skill_state[:seq].unsqueeze(0).repeat(batch, 1, 1)
        all_state = self.ls_state.repeat(batch, 1)

        batch_index = torch.arange(batch, device=device)
        all_time_gap = torch.ones((batch, seq), device=device)
        all_time_gap_embed = F.embedding(all_time_gap.long(), self.time_embed)

        predictions = []
        for now_step in range(seq):
            # 取出当前时刻要预测的题目与知识点。
            now_pro_embed = next_pro_embed[:, now_step]
            now_item_pro = next_problem[:, now_step]
            now_item_skill = next_skill[:, now_step]

            # 找到同一道题上一次出现时的题目状态，并嵌入时间间隔。
            last_batch_pro_time = last_pro_time[batch_index, now_item_pro]
            last_batch_pro_state = pro_state[batch_index, last_batch_pro_time.long()]
            pro_gap_embed = F.embedding((now_step - last_batch_pro_time).long(), self.time_embed)

            # 找到同一知识点上一次出现时的知识点状态，并嵌入时间间隔。
            last_batch_skill_time = last_skill_time[batch_index, now_item_skill]
            last_batch_skill_state = skill_state[batch_index, last_batch_skill_time.long()]
            skill_gap_embed = F.embedding((now_step - last_batch_skill_time).long(), self.time_embed)

            # Forget：根据时间间隔对题目状态做遗忘。
            pro_forget = self.obtain_pro_forget(
                self.dropout(torch.cat([last_batch_pro_state, pro_gap_embed], dim=-1))
            )
            last_batch_pro_state = last_batch_pro_state * pro_forget

            # Forget：根据时间间隔对知识点状态做遗忘。
            skill_forget = self.obtain_skill_forget(
                self.dropout(torch.cat([last_batch_skill_state, skill_gap_embed], dim=-1))
            )
            last_batch_skill_state = last_batch_skill_state * skill_forget

            # Forget：领域状态每步推进，使用统一的时间间隔表示。
            all_forget = self.obtain_all_forget(
                self.dropout(torch.cat([all_state, all_time_gap_embed[:, now_step]], dim=-1))
            )
            last_batch_all_state = all_state * all_forget

            # Response：先基于遗忘后的状态预测当前题目的正确概率。
            final_state = torch.cat(
                (last_batch_all_state, last_batch_pro_state, last_batch_skill_state, now_pro_embed),
                dim=-1,
            )
            pred = torch.sigmoid(self.out(self.dropout(final_state))).squeeze(-1)
            predictions.append(pred)

            # Update：用当前交互更新领域状态。
            all_obtain = self.obtain_all_state(
                self.dropout(torch.cat([last_batch_all_state, next_x[:, now_step]], dim=-1))
            )
            all_state = last_batch_all_state + torch.tanh(all_obtain)

            # Update：用当前交互更新题目状态，并记录该题最近出现位置。
            pro_obtain = self.obtain_pro_state(
                self.dropout(torch.cat([last_batch_pro_state, next_x[:, now_step]], dim=-1))
            )
            pro_state[:, now_step] = last_batch_pro_state + torch.tanh(pro_obtain)
            last_pro_time[batch_index, now_item_pro] = now_step

            # Update：用当前交互更新知识点状态，并记录该知识点最近出现位置。
            skill_obtain = self.obtain_skill_state(
                self.dropout(torch.cat([last_batch_skill_state, next_x[:, now_step]], dim=-1))
            )
            skill_state[:, now_step] = last_batch_skill_state + torch.tanh(skill_obtain)
            last_skill_time[batch_index, now_item_skill] = now_step

        return torch.vstack(predictions).T
