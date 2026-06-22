# PlotGraphManager 剧情图管理器

剧情图的核心管理类，负责节点/选择/边的 CRUD、分支管理、回溯、Mermaid 可视化和 JSON 持久化。

## 获取单例

```python
from nbot.plot import get_plot_graph_manager

manager = get_plot_graph_manager(data_dir="data/web", event_bus=event_bus)
```

## CRUD 操作

### 节点

```python
# 添加节点（自动发射 plot.node.created 事件）
node = manager.add_node(node)

# 获取单个节点
node = manager.get_node("pn_001")

# 获取最新节点
latest = manager.get_latest_node("conv_abc")

# 写入消息快照
manager.set_node_messages("pn_001", user_message={...}, assistant_message={...})

# 更新 TTS 音频 URL（写入节点快照的 assistant_message.audio_url）
manager.update_assistant_audio("msg_001", "https://audio...", conversation_id="conv_abc")
```

### 选择

```python
# 添加选择（自动发射 plot.choice.generated 事件）
choice = manager.add_choice(choice)

# 删除节点下所有未选中的选择
count = manager.delete_choices_for_node("pn_001")

# 获取当前激活节点的未选中选择
choices = manager.get_latest_choices("conv_abc")
```

### 边

```python
# 添加边（自动发射 plot.edge.created 事件）
edge = manager.add_edge(edge)

# 为已选选择创建边
edge = manager.create_edge_for_choice("pc_001", "pn_002", "握住手")
```

## 选择处理（select_choice）

标记选择为已选中，触发记忆和世界书桥接：

```python
success = manager.select_choice("pc_001")
```

内部流程：
1. 验证选择存在且未被选中
2. 标记 `choice.selected = True`
3. 更新父节点的 `selected_choice_id`
4. 发射 `plot.choice.selected` 事件
5. 触发 `PlotMemoryBridge`（根据级别写入记忆）
6. 触发 `PlotWorldBookBridge`（转折点写入世界书）

## 分支管理

### 激活节点

激活节点是会话当前所在的分支末端，是选择查询和分支切换的单一真相来源。

```python
# 获取当前激活节点 ID
active_id = manager.get_active_node_id("conv_abc")

# 设置激活节点
manager.set_active_node("conv_abc", "pn_xyz")
```

### 分支创建（branch_from）

从某个选择创建新分支，允许同一父节点存在多条分支路径：

```python
new_node = PlotNode(
    conversation_id="conv_abc",
    character_id="char_xyz",
    title="另一条路",
    summary="选择了不同的方向",
)

branched = manager.branch_from("pc_choice_id", new_node)
```

行为：
- 设置新节点的 `parent_node_id` 指向父节点
- 标记 choice 为已选中
- 创建边连接父节点和新节点
- 不覆盖父节点已有的 `selected_choice_id`（保留首选主线语义）

### 路径物化（materialize_path）

从根节点到目标节点重建完整消息列表：

```python
messages = manager.materialize_path(
    conversation_id="conv_abc",
    node_id="pn_target",
    system_prompt="你是角色...",
)
# 返回: [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}, ...]
```

消息快照机制：
- 每个节点存储 `user_message` 和 `assistant_message` 快照
- 有快照的节点直接使用快照内容
- 缺少快照的历史节点用 `title`/`summary` 兜底重建
- 物化消息赋稳定 ID（`pm_u_<node_id>` / `pm_a_<node_id>`），保证编辑和 TTS 引用正确

### 回溯（rollback）

回溯到指定节点，删除所有后代：

```python
success = manager.rollback("pn_abc", conversation_id="conv_abc")
```

内部流程：
1. BFS 收集所有后代节点（不含目标节点本身）
2. 删除后代节点、相关边和选择
3. 清除目标节点的 `selected_choice_id`
4. 将目标节点名下的选择复位为未选
5. 设置激活节点指向目标节点
6. 发射 `plot.rollback.done` 事件

### 时间线查询

```python
# 获取从根到当前激活节点的路径
timeline = manager.get_timeline("conv_abc")

# 获取某节点的直接子节点
children = manager.get_children("conv_abc", "pn_001")

# 获取从根到指定节点的路径
path = manager.path_to_node("conv_abc", "pn_target")
```

## 图查询

```python
# 获取完整剧情图
graph = manager.get_graph("conv_abc")
# 返回 {"nodes": [...], "choices": [...], "edges": [...]}
```

## Mermaid 可视化

```python
mermaid_code = manager.generate_mermaid("conv_abc")
```

生成 `graph TD` 语法，节点按级别着色：
- 默认：白色
- `important`：黄色 `fill:#ff9`
- `turning_point`：粉色 `fill:#f9f`
- `ending`：青色 `fill:#9ff`

## 事件系统

通过 `set_event_bus(bus)` 注入 `ConversationEventBus`，所有 CRUD 操作自动发射对应事件：

| 操作 | 事件 |
|------|------|
| `add_node` | `plot.node.created`（转折点额外发射 `plot.turning_point.reached`） |
| `add_choice` | `plot.choice.generated` |
| `select_choice` | `plot.choice.selected` |
| `add_edge` | `plot.edge.created` |
| `rollback` | `plot.rollback.done` |

## 持久化

数据存储在 `data/web/plot_graphs.json`，JSON 格式：

```json
{
  "nodes": { "pn_001": { ... } },
  "choices": { "pc_001": { ... } },
  "edges": { "pe_001": { ... } },
  "active": { "conv_abc": "pn_002" }
}
```

所有写操作自动持久化（`_save()`），初始化时自动加载（`_load()`）。
