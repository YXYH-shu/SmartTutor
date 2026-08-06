# 资源与学伴图推荐训练和部署手册

该目录实现一个共享的异构 GAT：同一图编码器同时服务资源推荐和学伴推荐。后端以 import 方式在 FastAPI 生命周期内常驻加载；推荐请求会对当前全图执行 GAT 前向，再计算本次候选的分数。

## 1. 模型与图

节点类型固定为 `learner`、`resource`、`knowledge_point`。图从当前业务表读取以下关系，并在构图时补充反向边：

| 关系 | 来源表 | 用途 |
|---|---|---|
| learner -> resource | `learner_resource_interactions` | 资源学习交互 |
| resource -> knowledge_point | `resource_knowledge` | 资源覆盖知识点 |
| learner -> knowledge_point | `learner_knowledge_interactions` | 学习者知识状态 |
| knowledge_point -> knowledge_point | `knowledge_knowledge` | 知识点前置关系 |
| learner <-> learner | `learner_learner_relations` | 已有学伴关系 |

三类节点都由冻结的文本模型生成 Embedding，再经过各自训练的线性投影进入异构 GAT（默认两层）。文本向量不是模型权重：它们缓存在 `graph_node_embeddings` 表，命中时直接读取；节点文本变化、模型 ID 或向量维度变化时才重新编码并写回缓存。

资源个性化排序使用资源 head；学伴个性化排序使用对称的学伴 head。资源相似度不经过 GAT，而是以缓存的冻结文本向量分别计算每个锚点与资源的余弦相似度；学伴相似度使用 GAT 聚合后的学习者向量。

## 2. Checkpoint 文件

默认目录为 `backend/algorithm/graph_recommender/ckpt/`，后端和训练脚本都从这里读取四个文件：

```text
encoder.pt             # 共享异构 GAT 编码器
resource_scorer.pt     # 学习者-资源排序头
peer_scorer.pt         # 学习者-学伴排序头
model_config.json      # Embedding、GAT 和训练超参数
```

后端启动和训练命令都要求目录中存在这四个文件。缺失任何一个文件时，后端会记录 warning，两个智能体的 `personality` 排序会按候选原顺序降级；应用仍可继续提供推荐流程。

`model_config.json` 是唯一的模型参数文件，包含 `embedding_dim`、`hidden_dim`、`output_dim`、`heads`、`num_layers`、dropout、预训练参数、任务训练参数和随机种子。三份 `.pt` 文件与该 JSON 必须来自同一次训练；文本 Embedding 和图快照不放入该目录。

## 3. 训练前准备

1. 安装后端依赖，并确保 PyTorch、PyG、SentenceTransformers 可用。
2. 配置当前业务数据库，导入用户、资源和知识点数据。
3. 执行迁移，创建 `graph_node_embeddings` 缓存表：

   ```bash
   cd backend
   alembic upgrade head
   ```

4. 在 `backend/.env` 配置文本模型和 checkpoint 目录。文本模型可填写 Hugging Face 模型名，也可填写已下载的本地目录：

   ```dotenv
   SMART_TUTOR_GRAPH_RECOMMENDER__ENABLED=true
   SMART_TUTOR_GRAPH_RECOMMENDER__CHECKPOINT_DIR=algorithm/graph_recommender/ckpt
   SMART_TUTOR_GRAPH_RECOMMENDER__EMBEDDING_MODEL_ID=BAAI/bge-small-zh-v1.5
   ```

5. 至少准备一个 `learner` 节点、一个 `resource` 节点，以及一类可训练正例：
   - 资源任务：`learner_resource_interactions`
   - 学伴任务：`learner_learner_relations`

   两类任务都存在时会共同训练。某一任务没有训练边时，对应排序头保留初始化权重；两类都没有训练边时，训练命令会停止并报错。`resource_knowledge`、`learner_knowledge_interactions`、`knowledge_knowledge` 会增强图结构，但不是训练命令的前置条件。

## 4. 训练命令

从 `backend/` 目录运行唯一训练入口：

```bash
python algorithm/graph_recommender/train.py
```

训练脚本执行顺序：

1. 检查 `graph_node_embeddings` 表是否存在。
2. 从业务表读取节点和五类关系，打印节点数、边数、孤儿边、重复边和时间戳审计结果。
3. 读取或生成节点文本 Embedding，并更新数据库缓存。
4. 对共享 GAT 做图对比预训练（包含 learner 多兴趣辅助损失）。
5. 冻结图编码器，训练资源 BPR 排序头和学伴 BCE 链路预测头。
6. 输出资源/学伴训练与测试统计，并将三份权重和 `model_config.json` 写入 checkpoint 目录。

资源交互按每个学习者的交互时间留后切分：最后一条用于测试、倒数第二条用于验证。学伴关系按 `created_at` 全局时间切分，并将无向 pair 规范化以避免双向泄漏。验证和测试边不会进入训练编码图。

## 5. 训练后启动服务

训练与后端使用同一个 checkpoint 目录。完成数据准备后执行：

```bash
cd backend
python algorithm/graph_recommender/train.py
```

训练完成后启动或重启 FastAPI：

```bash
uvicorn app.main:app --reload --port 8000
```

后端严格按 `model_config.json` 构造网络并加载三份权重；维度或网络结构不匹配会拒绝加载。

## 6. 在线运行与数据同步

FastAPI 启动时调用 `GraphRecommender.start()`：加载四个 checkpoint、读取节点和边、补全/读取 Embedding 缓存并发布内存图快照。请求到达时：

- `rank_resources()`、`rank_peers()`、`similar_peers()` 在完整图快照上执行一次 GAT 前向。
- `rank_resource_similarity_pairs()` 只读取资源的冻结文本 Embedding，不依赖图边数量。
- 所有外部调用使用数据库 ID；模块内部负责数据库 ID 与图索引的转换。

应用 ORM 提交成功后会收集图源数据的变更并调用 `sync_after_commit()`。该方法刷新受影响的文本 Embedding、重建全图并原子发布新快照；失败时继续使用旧快照。新增或修改用户、资源、知识点、五类图关系均可走这一机制。若通过外部 SQL、管理工具或其他进程直接写库，当前后端进程不会收到通知，应重启后端或由写入方显式调用同步接口。

### 图同步预留接口

以下接口由 `GraphRecommender` 提供，均在进程内使用，不是 HTTP 接口：

| 接口 | 适用场景 | 行为 |
|---|---|---|
| `start()` | FastAPI 启动 | 加载 checkpoint、Embedding 缓存和完整图，发布首个快照。应用启动过程已调用，无需业务代码重复调用。 |
| `sync_after_commit(changes)` | 业务数据已成功提交后的增量通知 | 处理缓存失效、重建完整图并原子发布新快照。后续新增节点、修改节点、创建或删除图关系时使用。 |
| `refresh_full(changes=None)` | 运维或批量数据导入后的全量刷新 | 重新从数据库读取节点和边；可选 `changes` 用于提示 Embedding 刷新范围。只能在 `start()` 成功后调用。 |
| `reload_model(checkpoint_dir=None)` | 重新读取配置目录中的 checkpoint | 重新加载模型文件，重建图并发布新快照。 |
| `get_status()` | 健康检查和运维观察 | 返回 `ready`、快照 `version`、创建时间、文本模型、维度以及各类节点/边计数。 |

`sync_after_commit()` 的参数是 `GraphChange` 列表。节点事件使用数据库 ID：

```python
GraphChange(operation="upsert", entity_type="learner", entity_id=learner_id)
GraphChange(operation="delete", entity_type="resource", entity_id=resource_id)
GraphChange(operation="upsert", entity_type="knowledge_point", entity_id=knowledge_id)
```

边事件使用关系名与源、目标数据库 ID：

```python
GraphChange(
    operation="upsert",
    entity_type="edge",
    relation_type="interacted_with",
    source_id=learner_id,
    target_id=resource_id,
)
```

可用的 `relation_type` 为：

| 关系名 | 源节点 | 目标节点 | 来源表 |
|---|---|---|---|
| `interacted_with` | learner | resource | `learner_resource_interactions` |
| `covers` | resource | knowledge_point | `resource_knowledge` |
| `has_knowledge_state` | learner | knowledge_point | `learner_knowledge_interactions` |
| `precedes` | knowledge_point | knowledge_point | `knowledge_knowledge` |
| `partnered_with` | learner | learner | `learner_learner_relations` |

应用内使用 `AsyncSessionLocal` 写入上述 ORM 模型时，`GraphAwareAsyncSession.commit()` 会在提交成功后自动生成并发送这些事件；同一次写入不需要业务代码再次调用同步接口。对于外部服务、管理脚本或直连 SQL，必须先确保数据库事务提交成功，再在运行图推荐器的进程中调用：

```python
from algorithm.graph_recommender import GraphChange, get_graph_recommender

changes = [
    GraphChange(
        operation="upsert",
        entity_type="edge",
        relation_type="partnered_with",
        source_id=learner_a_id,
        target_id=learner_b_id,
    )
]
await get_graph_recommender().sync_after_commit(changes)
```

同步只更新当前后端进程的内存快照。多 worker 或多实例部署时，写入方需要向每个进程广播同一批已提交事件；持久化 outbox 和消息队列消费者可直接复用 `sync_after_commit(changes)` 作为消费端入口。

## 7. 验证接口

以下接口仅用于本地演示，不需要认证，不写推荐记录，也不写执行日志：

```text
POST /api/v1/agent-demos/resource-recommender/run
POST /api/v1/agent-demos/study-buddy/run
```

资源演示要求物理资源种子数据；学伴演示要求测试学伴用户已初始化。它们验证的是启动、SQL、图模型调用和输出链路，不代表离线推荐质量。
