"""学习路径规划的搜索核心：双策略多目标遗传算法（迁移自 DSMOEA）。

和 `LPP/DSMOEA/src/counterfactual/genetic_algorithm.py` 相比，本文件做了
一处关键重构：**不再直接依赖任何具体的 KT 模型类**，而是通过
`scorers.base.KTScorer` 接口调用打分逻辑（`self.scorer.forward_batch(...)`、
`self.scorer.skills_of(...)`、`self.scorer.questions_of_skill(...)`）。

这样 DKT/SAKT、KT，或者未来任何新模型，只要各自实现一个 `KTScorer`，
就可以直接复用这里的搜索算法，不需要改动任何一行搜索逻辑。

算法数学逻辑（交叉/变异概率、非支配排序、经验矩阵更新公式、softmax 采样
温度等）与 DSMOEA 原始实现保持一致，只做了以下清理（详见 DSMOEA/README.md
里记录的同类问题）：

1. `init(pop_size)` 按 pop_size 动态生成种群（原版硬编码 20/10/10/10=50，
   pop_size 非 50 时会触发死循环，这里已修复）。
2. 死循环哨兵检查改成一次性 `assert`。
3. 类内部方法统一使用 `self.xxx`，不依赖脚本级别的全局变量。
4. "技能"统一表示为 `list[int]`，不再像原版那样把技能编码成逗号拼接的
   字符串在 numpy 里绕一圈再拆开。
"""

from __future__ import annotations

import random
from collections import defaultdict

import numpy as np
import torch

from lpp_runtime.scorers.base import KTScorer


class GeneticAlgorithmBase:
    """对单条学生做题序列执行反事实/路径规划搜索的双策略多目标遗传算法。"""

    def __init__(
        self,
        scorer: KTScorer,
        e_ICEf,
        e_ACEf,
        e_weightf,
        hist_q,
        hist_a,
        next_q,
        next_a,
        hist_q_old,
        hist_a_old,
        next_q_old,
        next_a_old,
        base,
        target_question: int,
        target_skills: list[int],
        candidate_pool_all: list[int],
        candidate_pool_default: list[int],
        candidate_pool_untried_skill: list[int],
        candidate_pool_wrong_skill: list[int],
        candidate_pool_target_skill: list[int],
        skill_num: int,
        matrix: bool = True,
    ):
        self.scorer = scorer
        self.e_ICEf = e_ICEf
        self.e_ACEf = e_ACEf
        self.e_weightf = e_weightf
        self.hist_q = hist_q  # 历史题目序列 shape -> [1, length]
        self.hist_a = hist_a  # 历史作答序列 shape -> [1, length]
        self.next_q = next_q  # 下一时刻题目序列，最后一位是待预测题目
        self.next_a = next_a
        self.hist_q_old = hist_q_old
        self.hist_a_old = hist_a_old
        self.next_q_old = next_q_old
        self.next_a_old = next_a_old
        self.base = base
        self.cause_len = 5  # 反事实/规划序列长度（mask 段 + 题目段各占一半基因）
        self.target_question = target_question  # 要提升掌握度的目标题目
        self.target_skills = target_skills  # 目标题目对应的知识点
        self.candidate_pool_all = candidate_pool_all
        self.candidate_pool_default = candidate_pool_default
        self.candidate_pool_untried_skill = candidate_pool_untried_skill
        self.candidate_pool_wrong_skill = candidate_pool_wrong_skill
        self.candidate_pool_target_skill = candidate_pool_target_skill
        self.skill_num = skill_num
        self.matrix = matrix

    def reset(self):
        self.cg = 0  # 当前进化代数
        self.best_v = 0
        self.best_x = None
        self.best_fitness = []

    def init(self, pop_size: int):
        """初始化种群，融合四种先验采样策略：

        - 默认策略：不限制候选题目（全量候选池）
        - 探索策略：候选来自"未涉及目标技能"的题目
        - 利用策略：候选来自历史错题对应技能的题目
        - 技能相关策略：候选来自目标题目对应技能的题目

        按 40% / 20% / 20% / 20% 的比例根据实际 pop_size 生成种群，
        总数严格等于 pop_size（最后一组吸收取整误差）。
        """
        if pop_size % 2 != 0:
            raise ValueError(f"pop_size 必须是偶数（用于两两交叉），当前为 {pop_size}")

        group_sizes = [
            int(round(pop_size * 0.4)),
            int(round(pop_size * 0.2)),
            int(round(pop_size * 0.2)),
        ]
        group_sizes.append(pop_size - sum(group_sizes))

        candidate_pools = [
            self.candidate_pool_default,
            self.candidate_pool_untried_skill,
            self.candidate_pool_wrong_skill,
            self.candidate_pool_target_skill,
        ]

        X0 = []
        for pool, n in zip(candidate_pools, group_sizes):
            options = [x for x in pool if x != self.target_question]
            if not options:
                # 极端情况下某个候选池为空（比如某个知识点在 KT 里只映射了
                # 目标题目本身），退回全量候选池，保证一定能采样出个体。
                options = [x for x in self.candidate_pool_all if x != self.target_question]
            for _ in range(n):
                ind_len = np.random.randint(0, 2, self.cause_len)
                while (ind_len == 0).all():
                    ind_len = np.random.randint(0, 2, self.cause_len)
                if len(options) >= self.cause_len:
                    ind_que = random.sample(options, self.cause_len)
                else:
                    # DSMOEA 原本假设每个候选池至少有 cause_len 个不同题目
                    # （Eedi 平均每个知识点关联 ~88 道题）。KT 数据集更稀疏
                    # （每个知识点平均只关联 ~2.9 道题），候选池可能小于
                    # cause_len，这里退化为有放回采样，允许同一题目在基因里
                    # 出现多次（不影响算法正确性，只是候选题目多样性变低）。
                    ind_que = random.choices(options, k=self.cause_len)
                ind = np.concatenate((ind_len, ind_que), axis=0)
                X0.append(ind)

        return [list(array) for array in X0]

    def get_skills_of_question(self, question_id) -> list[int]:
        return self.scorer.skills_of(int(question_id))

    def get_skills_of_questions(self, question_ids) -> list[list[int]]:
        return [self.scorer.skills_of(int(q)) for q in question_ids]

    def update_matrix(self, base, fitness, mask_list0):
        """用本代种群的效应值更新技能间经验矩阵 ICE / ACE / Weight。"""
        for q in range(len(mask_list0)):
            mask_list = mask_list0[q]
            mid = len(mask_list) // 2
            picked = [mask_list[i + self.cause_len] for i in range(mid) if mask_list[i] == 1]
            if not picked:
                return
            his_skills = set()
            for question_id in picked:
                his_skills.update(self.get_skills_of_question(question_id))
            for skill in self.target_skills:
                for his_skill in his_skills:
                    try:
                        self.e_ICEf[his_skill][skill] += fitness[q]
                    except Exception as exc:
                        raise RuntimeError(
                            f"无法更新知识点经验矩阵：source={his_skill}, target={skill}"
                        ) from exc
                    self.e_weightf[his_skill][skill] += 1
                    self.e_ACEf[his_skill][skill] = (
                        self.e_ICEf[his_skill][skill] / self.e_weightf[his_skill][skill]
                    )

    def choice_skills(self, skills: list[int]):
        """基于经验矩阵 ACE，按 softmax 采样一个变异用的候选题目。"""
        e_ACE = self.e_ACEf
        t = 1.5  # softmax 温度，1.5 最好；不能为 0

        if not skills:
            # 兜底：当前基因位上的题目查不到任何知识点（比如它是从全量候选池里
            # 随机换来的、实际不存在的题目 id）。此时无法走经验矩阵引导，退回
            # 从默认候选池随机选一道有效题目，并返回 a=0 表示"没用到矩阵"。
            options = [int(x) for x in self.candidate_pool_default if x != self.target_question]
            return np.random.choice(options), 0

        if len(skills) != 1:
            M0_rows = []
            for r in skills:
                row = e_ACE[r].copy()
                row[skills] = 0
                M0_rows.append(row)
            M0 = np.stack(M0_rows, axis=0)

            flat = M0.ravel()
            expv = np.exp(flat / t)
            p = expv / expv.sum()
            sampled_index = np.random.choice(flat.size, p=p)
            num_cols = M0.shape[1]
            sampled_skill = int(sampled_index % num_cols)
        else:
            r = skills[0]
            row = e_ACE[r].copy()
            row[r] = 0
            expv = np.exp(row / t)
            p = expv / expv.sum()
            sampled_skill = int(np.random.choice(np.arange(len(p)), p=p))

        options = [
            int(x) for x in self.scorer.questions_of_skill(sampled_skill) if x != self.target_question
        ]
        if not options:
            options = [int(x) for x in self.candidate_pool_default if x != self.target_question]
        return np.random.choice(options), 1

    def fast_non_dominated_sort(self, base, values1, values2):
        """快速非支配排序（NSGA-II 经典实现）。"""
        f1_min, f1_max = min(values1), max(values1)
        values10 = [0 for _ in values1] if f1_min == f1_max else [
            (x1 - f1_min) / (f1_max - f1_min) for x1 in values1
        ]
        f2_min, f2_max = min(values2), max(values2)
        values20 = [0 for _ in values2] if f2_min == f2_max else [
            (x2 - f2_min) / (f2_max - f2_min) for x2 in values2
        ]

        S = [[] for _ in range(len(values10))]
        front = [[]]
        n = [0 for _ in range(len(values10))]
        rank = [0 for _ in range(len(values10))]

        for p in range(len(values10)):
            S[p] = []
            n[p] = 0
            for q in range(len(values10)):
                if (values10[p] < values10[q] and values20[p] < values20[q]) or (
                    values10[p] <= values10[q] and values20[p] < values20[q]
                ) or (values10[p] < values10[q] and values20[p] <= values20[q]):
                    if q not in S[p]:
                        S[p].append(q)
                elif (values10[q] < values10[p] and values20[q] < values20[p]) or (
                    values10[q] <= values10[p] and values20[q] < values20[p]
                ) or (values10[q] < values10[p] and values20[q] <= values20[p]):
                    n[p] += 1
            if n[p] == 0:
                rank[p] = 0
                if p not in front[0]:
                    front[0].append(p)

        i = 0
        while front[i]:
            Q = []
            for p in front[i]:
                for q in S[p]:
                    n[q] -= 1
                    if n[q] == 0:
                        rank[q] = i + 1
                        if q not in Q:
                            Q.append(q)
            i += 1
            front.append(Q)

        del front[len(front) - 1]
        return front

    def crossover(self, X):
        """三种交叉方式（前半段交叉 / 后半段交叉 / 整体交叉）随机选择。"""
        for i in range(0, X.shape[0], 2):
            xa = X[i, :]
            xb = X[i + 1, :]
            crossover_type = np.random.choice([0, 1, 2])

            if crossover_type == 0:
                for j in range(X.shape[1] // 2):
                    if np.random.rand() <= 0.2:
                        xa[j], xb[j] = xb[j], xa[j]
            elif crossover_type == 1:
                for j in range(X.shape[1] // 2, X.shape[1]):
                    if np.random.rand() <= 0.2:
                        xa[j], xb[j] = xb[j], xa[j]
            else:
                for j in range(X.shape[1]):
                    if np.random.rand() <= 0.3:
                        xa[j], xb[j] = xb[j], xa[j]

            X[i, :] = xa
            X[i + 1, :] = xb

        return X

    def mutation(self, X, sum_mution, max_gen):
        c11 = 0.5
        for i in range(X.shape[0]):
            crossover_type1 = np.random.choice([0, 1])
            if crossover_type1 == 0:
                for j in range(X.shape[1] // 2):
                    if np.random.rand() <= 0.5:
                        X[i, j] = (X[i, j] + 1) % 2
            else:
                for j in range(X.shape[1] // 2, X.shape[1]):
                    if np.random.rand() <= c11:
                        if np.random.rand() <= 0.3:
                            cur_question = X[i, j]
                            his_skills = self.get_skills_of_question(cur_question)
                            X[i, j], a = self.choice_skills(his_skills)
                            if a != 0:
                                sum_mution += 1
                        else:
                            options = [
                                x for x in self.candidate_pool_all if x != self.target_question
                            ]
                            X[i, j] = np.random.choice(options)
        return X, sum_mution

    def predict_1(self, X, base):
        """批量计算种群适应度：把"逐题追加"的每一步做成 batch 前向。

        与具体模型解耦：每一步实际的前向计算都通过 `self.scorer.forward_batch()`
        完成，本方法只负责维护"历史序列如何随候选题目增长"这部分模型无关的逻辑。
        """
        device = self.scorer.device
        B = len(X)
        cause_len = self.cause_len

        plans, steps = [], []
        for item0 in X:
            mask = item0[:cause_len]
            ques = item0[cause_len:]
            plan = [q for m, q in zip(mask, ques) if m == 1]
            plans.append(plan)
            steps.append(len(plan))

        max_steps = max(steps) if steps else 0

        cur_q = [self.hist_q.clone().to(device).long() for _ in range(B)]
        cur_a = [self.hist_a.clone().to(device).long() for _ in range(B)]
        cur_next_q = [self.next_q.clone().to(device).long() for _ in range(B)]
        cur_next_a = [self.next_a.clone().to(device).long() for _ in range(B)]

        last_step_label = [None] * B
        last_step_ques = [None] * B

        que_all1 = steps[:]
        suc_nums_all = [0] * B

        with torch.inference_mode():
            for s in range(max_steps):
                active = [i for i in range(B) if s < steps[i]]
                if not active:
                    break

                items = torch.cat([cur_q[i] for i in active], dim=0).to(device).long()
                answers = torch.cat([cur_a[i] for i in active], dim=0).to(device).long()

                ques_choice = torch.tensor(
                    [[plans[i][s]] for i in active], device=device, dtype=torch.long
                )

                idx_list = []
                for k, i in enumerate(active):
                    idx_i = torch.cat((cur_next_q[i][:, :-1], ques_choice[k:k + 1]), dim=-1).long()
                    idx_list.append(idx_i)
                idx = torch.cat(idx_list, dim=0).to(device).long()

                out = self.scorer.forward_batch(items, answers, idx)
                if out.dim() == 3:
                    out = out.squeeze(-1)
                y_last = out[:, -1]

                label_ca = (y_last >= 0.5).to(torch.long).unsqueeze(1)
                for k, i in enumerate(active):
                    last_step_label[i] = label_ca[k:k + 1]
                    last_step_ques[i] = ques_choice[k:k + 1]

                    cur_next_a[i] = torch.cat((cur_next_a[i][:, :-1], last_step_label[i]), dim=-1).long()
                    cur_q[i] = torch.cat((cur_q[i], last_step_ques[i]), dim=-1).long()
                    cur_a[i] = torch.cat((cur_a[i], cur_next_a[i][:, -1:]), dim=-1).long()
                    cur_next_q[i] = torch.cat(
                        (cur_q[i][:, 1:], self.next_q_old[:, -1:].to(device)), dim=-1
                    ).long()

            finals = []
            for i in range(B):
                if last_step_ques[i] is None:
                    last_step_ques[i] = cur_next_q[i][:, -1:].clone().long()
                if last_step_label[i] is None:
                    last_step_label[i] = cur_next_a[i][:, -1:].clone().long()

                finals.append((i, cur_q[i].to(device).long(), cur_a[i].to(device).long(), cur_next_q[i].to(device).long()))

            # 按长度分桶批量前向
            buckets = defaultdict(list)
            for i, d, a, idx in finals:
                buckets[d.size(1)].append((i, d, a, idx))

            pro_all = np.zeros(B, dtype=np.float32)
            for L, group in buckets.items():
                d_batch = torch.cat([g[1] for g in group], dim=0).to(device).long()
                a_batch = torch.cat([g[2] for g in group], dim=0).to(device).long()
                i_batch = torch.cat([g[3] for g in group], dim=0).to(device).long()

                out_final = self.scorer.forward_batch(d_batch, a_batch, i_batch)
                if out_final.dim() == 3:
                    out_final = out_final.squeeze(-1)
                y_last_final = out_final[:, -1].detach().cpu().numpy()

                for k, (i, _, _, _) in enumerate(group):
                    pro_all[i] = y_last_final[k]

        for i in range(B):
            if pro_all[i] >= 0.7:
                suc_nums_all[i] += 1

        effect_list = pro_all - base
        effect_list1 = -effect_list
        logit0 = np.log(base / (1 - base))
        logit1 = np.log(pro_all / (1 - pro_all))
        abs1 = np.abs(logit0 - logit1)

        return effect_list1, effect_list, que_all1, abs1, base, pro_all, suc_nums_all

    def weighted_sum_sort(self, c1, c2, weights=(0.9, 0.1)):
        distances = weights[0] * c1 + weights[1] * c2
        return np.argsort(distances)

    def improved_non_dominated_sort(self, values10, values20, frontiers, weights=(0.9, 0.1)):
        final_sorted_solutions = []
        for frontier in frontiers:
            if len(frontier) > 1:
                values10 = np.array(values10)
                values20 = np.array(values20)
                current_frontier_solutions1 = values10[frontier]
                current_frontier_solutions2 = values20[frontier]
                sorted_indices = self.weighted_sum_sort(
                    current_frontier_solutions1, current_frontier_solutions2, weights
                )
                final_sorted_solutions.extend(frontier[i] for i in sorted_indices)
            else:
                final_sorted_solutions.append(frontier[0])
        return final_sorted_solutions

    def improved_non_dominated_sort2(self, solutions, weights=(0.9, 0.1)):
        base = self.base
        (
            function1_values,
            fyuan,
            function2_values,
            function3_values,
            base1,
            base2,
            suc_nums,
        ) = self.predict_1(solutions, base)

        f1_min, f1_max = min(function1_values), max(function1_values)
        values10 = [0 for _ in function1_values] if f1_min == f1_max else [
            (x1 - f1_min) / (f1_max - f1_min) for x1 in function1_values
        ]
        f2_min, f2_max = min(function2_values), max(function2_values)
        values20 = [0 for _ in function2_values] if f2_min == f2_max else [
            (x2 - f2_min) / (f2_max - f2_min) for x2 in function2_values
        ]

        frontiers = self.fast_non_dominated_sort(base, function1_values[:], function2_values[:])

        final_sorted_solutions = []
        for frontier in frontiers:
            if len(frontier) > 1:
                values10 = np.array(values10)
                values20 = np.array(values20)
                current_frontier_solutions1 = values10[frontier]
                current_frontier_solutions2 = values20[frontier]
                sorted_indices = self.weighted_sum_sort(
                    current_frontier_solutions1, current_frontier_solutions2, weights
                )
                final_sorted_solutions.extend(frontier[i] for i in sorted_indices)
            else:
                final_sorted_solutions.append(frontier[0])
        return final_sorted_solutions

    def run0707(self, pop_size=50, max_gen=100, weights=(0.9, 0.1)):
        """主搜索流程：初始化种群 -> 交叉变异 -> 非支配排序 -> 精英选择，迭代 max_gen 代。"""
        self.reset()
        fitness_func1 = self.predict_1
        base = self.base

        solution = self.init(pop_size)
        gen_no = 0
        lit_best0, lit_best1, lit_best2, lit_best3, lit_bestq = [], [], [], [], []
        p_best_base1, p_best_base2, p_best_length, p_best_logit, p_suc_nums = [], [], [], [], []
        sum_mution = 0
        max_value = 0.0
        best_v11 = None
        max_index = 0

        while gen_no < max_gen:
            (
                function1_values,
                fyuan,
                function2_values,
                function3_values,
                base1,
                base2,
                suc_nums,
            ) = fitness_func1(solution, base)

            if self.matrix:
                self.update_matrix(base, fyuan, solution)

            f1_min, f1_max = min(function1_values), max(function1_values)
            values10 = [0 for _ in function1_values] if f1_min == f1_max else [
                (x1 - f1_min) / (f1_max - f1_min) for x1 in function1_values
            ]
            f2_min, f2_max = min(function2_values), max(function2_values)
            values20 = [0 for _ in function2_values] if f2_min == f2_max else [
                (x2 - f2_min) / (f2_max - f2_min) for x2 in function2_values
            ]

            non_dominated_sorted_solution0 = self.fast_non_dominated_sort(
                base, function1_values[:], function2_values[:]
            )

            if gen_no == max_gen - 1:
                pareto_frontiers_data_best = non_dominated_sorted_solution0[0]
                for j in pareto_frontiers_data_best:
                    p_best_base1.append(base1)
                    p_best_base2.append(base2[j])
                    p_best_length.append(abs(function2_values[j]))
                    p_best_logit.append(function3_values[j])
                    p_suc_nums.append(suc_nums[j])

            non_dominated_sorted_solution = self.improved_non_dominated_sort(
                values10, values20, non_dominated_sorted_solution0, weights
            )

            max_index = non_dominated_sorted_solution[0]
            best_v11 = solution[max_index]
            suc_res = suc_nums[max_index]
            ques_sum = 0
            for s in range(len(best_v11) // 2, len(best_v11)):
                if best_v11[s - len(best_v11) // 2] == 1:
                    ques_sum += 1
            lit_bestq.append(ques_sum)
            max_value = fyuan[max_index]
            lit_best0.append(suc_res)
            lit_best1.append(max_value)
            lit_best2.append(best_v11)
            logit0 = np.log(base / (1 - base))
            pre_base = base + max_value
            logit1 = np.log(pre_base / (1 - pre_base))
            lit_best3.append(abs(logit0 - logit1))

            self.cg = gen_no + 1
            solution0 = np.array(solution)
            solution1 = self.crossover(solution0)
            solution11, sum_mution = self.mutation(solution1, sum_mution, max_gen)
            solution12 = solution11.tolist()
            for i in range(len(solution12)):
                while solution12[i][: self.cause_len] == [0] * self.cause_len:
                    solution12[i][: self.cause_len] = np.random.randint(0, 2, self.cause_len).tolist()
            solution2 = solution[:] + solution12

            assert len(solution2) == 2 * pop_size, (
                f"种群规模异常：len(solution2)={len(solution2)}，期望 {2 * pop_size}"
            )

            non_dominated_sorted_solution2 = self.improved_non_dominated_sort2(solution2, weights)
            new_solution = []
            for i in non_dominated_sorted_solution2:
                new_solution.append(i)
                if len(new_solution) == pop_size:
                    break
            solution = [solution2[i] for i in new_solution]
            gen_no += 1

        ques_list11 = []
        if best_v11 is not None:
            for s in range(len(best_v11) // 2, len(best_v11)):
                if best_v11[s - len(best_v11) // 2] == 1:
                    ques_list11.append(best_v11[s])

        fina_score = max_value + base
        change_num = len(ques_list11)
        pre_base = base + max_value
        logit0 = np.log(base / (1 - base))
        logit1 = np.log(pre_base / (1 - pre_base))

        return {
            "base": base,
            "final_score": fina_score,
            "effect_gain": max_value,
            "recommended_questions": ques_list11,
            "success_history": lit_best0,
            "effect_history": lit_best1,
            "best_individual_history": lit_best2,
            "logit_gap_history": lit_best3,
            "change_num": change_num,
            "logit0": logit0,
            "logit1": logit1,
            "e_ICEf": self.e_ICEf,
            "e_ACEf": self.e_ACEf,
            "e_weightf": self.e_weightf,
        }
