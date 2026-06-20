# review - Review Pipeline 审查层

## 概述

`review` 模块实现 Review Pipeline 审查层，每轮对话后对对话内容进行结构化审查。当前实现为规则版（不调用大模型），后续可替换为 LLM Review。

**核心特性：**
- **规则审查** - 基于关键词规则判断记忆写入、关系变化及剧情节点更新
- **结构化输出** - 返回标准化的审查结果，包含记忆写入建议、关系变化、评分等
- **事件驱动** - 支持通过 event_bus 发射审查事件
- **可扩展** - 支持后续替换为 LLM 版本

## 核心类

### ReviewInput

审查输入数据模型。

```python
from nbot.review.models import ReviewInput

inp = ReviewInput(
    conversation_id="conv_abc",
    character_id="char_xyz",
    user_id="user_123",
    group_id="group_456",
    user_message="你好，今天天气真好",
    ai_reply="是的，天气很好呢！",
    selected_choice={"level": "normal", "text": "继续聊天"},
    turn_context={"mood": "happy", "energy": 0.8},
    real_time_context={"hour": 14, "day_of_week": "Saturday"},
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `conversation_id` | `str` | 会话 ID |
| `character_id` | `str` | 角色 ID |
| `user_id` | `str` | 用户 ID |
| `group_id` | `str` | 群聊 ID（可选） |
| `user_message` | `str` | 用户消息 |
| `ai_reply` | `str` | AI 回复 |
| `selected_choice` | `Dict` | 已选择的剧情选项（可选） |
| `turn_context` | `Dict` | 回合上下文（可选） |
| `real_time_context` | `Dict` | 现实时间上下文（可选） |

### ReviewOutput

审查输出数据模型。

```python
from nbot.review.models import ReviewOutput

output = ReviewOutput(
    should_write_memory=True,
    memory_content="用户今天心情很好",
    memory_importance=0.7,
    relationship_delta={"affection": 2, "trust": 1},
    scores={"memory": 0.8, "relationship": 0.6, "plot": 0.3},
    plot_update={"node_id": "pn_001", "score": 0.5},
    skipped=False,
    source="rule",
)
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `should_write_memory` | `bool` | 是否需要写入记忆 |
| `memory_content` | `str` | 记忆内容 |
| `memory_importance` | `float` | 记忆重要性（0-1） |
| `relationship_delta` | `Dict` | 关系变化增量 |
| `scores` | `Dict` | 各维度评分 |
| `plot_update` | `Dict` | 剧情更新建议 |
| `skipped` | `bool` | 是否跳过审查 |
| `source` | `str` | 审查来源（"rule" 或 "llm"） |

### ReviewPipeline

审查管道编排器。

```python
from nbot.review import get_review_pipeline
from nbot.review.models import ReviewInput

# 获取全局单例
pipeline = get_review_pipeline(event_bus=event_bus)

# 执行审查
inp = ReviewInput(
    conversation_id="conv_abc",
    character_id="char_xyz",
    user_id="user_123",
    user_message="你好",
    ai_reply="你好呀！",
)

output = pipeline.run(inp)

if output.should_write_memory:
    print(f"需要写入记忆: {output.memory_content}")
    print(f"记忆重要性: {output.memory_importance}")

if output.relationship_delta:
    print(f"关系变化: {output.relationship_delta}")
```

## 审查规则

### 记忆写入判断

基于关键词和对话内容判断是否需要写入记忆：

| 触发条件 | 记忆类型 | 重要性 |
|----------|----------|--------|
| 包含情感关键词 | 情感记忆 | 0.6-0.8 |
| 包含重要事件 | 事件记忆 | 0.7-0.9 |
| 包含个人信息 | 用户画像 | 0.5-0.7 |
| 普通对话 | 不写入 | - |

**情感关键词示例：**
- 正面：开心、快乐、喜欢、爱、感谢
- 负面：难过、伤心、生气、害怕、担心
- 中性：记得、想起、忘记、知道

### 关系变化判断

根据对话内容和剧情选项判断关系变化：

| 场景 | 关系变化 |
|------|----------|
| 积极互动 | affection +1~3, trust +1~2 |
| 消极互动 | affection -1~2, trust -1 |
| 剧情选项（重要） | 根据选项级别调整 |
| 剧情选项（转折） | 大幅调整 |

### 剧情评分

对剧情相关对话进行评分：

| 评分维度 | 说明 |
|----------|------|
| `memory` | 记忆写入价值（0-1） |
| `relationship` | 关系发展价值（0-1） |
| `plot` | 剧情推进价值（0-1） |

## 事件发射

Review Pipeline 通过 event_bus 发射以下事件：

| 事件 | 时机 | Payload |
|------|------|---------|
| `review.started` | 审查开始 | conversation_id, character_id |
| `review.finished` | 审查完成 | 审查结果摘要 |
| `review.memory.scored` | 记忆评分完成 | 评分详情 |
| `review.relationship.scored` | 关系评分完成 | 评分详情 |
| `review.plot.scored` | 剧情评分完成 | 评分详情 |

```python
from nbot.hooks.event_bus import get_event_bus
from nbot.review import get_review_pipeline

# 初始化时传入 event_bus
event_bus = get_event_bus()
pipeline = get_review_pipeline(event_bus=event_bus)

# 执行审查时自动发射事件
output = pipeline.run(inp)
```

## 与 MemoryFS 集成

Review Pipeline 的输出可以写入 MemoryFS：

```python
from nbot.memory import get_memory_fs
from nbot.review import get_review_pipeline

def apply_review(inp: ReviewInput):
    pipeline = get_review_pipeline()
    output = pipeline.run(inp)
    
    if output.should_write_memory:
        fs = get_memory_fs()
        fs.write(
            path=fs.path_user(inp.character_id, inp.user_id),
            character_id=inp.character_id,
            target_id=inp.user_id,
            content=output.memory_content,
            importance=output.memory_importance,
        )
    
    return output
```

## 与 CharacterRuntime 集成

Review Pipeline 已集成到 `CharacterRuntime`，在 `after_turn` 阶段自动执行：

```python
class CharacterRuntime:
    def _run_review(self, chat_request, result, turn_context):
        """执行 Review Pipeline"""
        from nbot.review import get_review_pipeline
        
        pipeline = get_review_pipeline(event_bus=self._event_bus)
        
        inp = ReviewInput(
            conversation_id=turn_context.conversation_id,
            character_id=turn_context.identity.character_id,
            user_id=turn_context.identity.target_id,
            user_message=chat_request.message,
            ai_reply=result.text,
            selected_choice=turn_context.selected_choice,
            turn_context=turn_context.to_dict(),
            real_time_context=turn_context.real_time_context,
        )
        
        output = pipeline.run(inp)
        
        # 应用审查结果
        if output.should_write_memory:
            self._apply_memory_write(output, turn_context.identity)
        
        if output.relationship_delta:
            self._apply_relationship_delta(output.relationship_delta, turn_context)
```

## Web API

| 方法 | 路由 | 说明 |
|------|------|------|
| GET | `/api/review/logs` | 获取审查日志 |
| GET | `/api/review/memory-fs` | 获取 MemoryFS 文件列表 |
| GET | `/api/review/event-stream` | SSE 事件流 |
| POST | `/api/review/run` | 手动触发审查 |

### 获取审查日志

```bash
curl /api/review/logs?limit=50&domain=memory
```

### 手动触发审查

```bash
curl -X POST /api/review/run \
  -H "Content-Type: application/json" \
  -d '{
    "conversation_id": "conv_abc",
    "character_id": "char_xyz",
    "user_id": "user_123",
    "user_message": "你好",
    "ai_reply": "你好呀！"
  }'
```

## 目录结构

```
nbot/review/
├── __init__.py      # 模块入口
├── models.py        # ReviewInput / ReviewOutput 数据模型
├── pipeline.py      # ReviewPipeline 编排器
└── rule_review.py   # 规则版审查实现
```

## 使用示例

### 基本使用

```python
from nbot.review import get_review_pipeline
from nbot.review.models import ReviewInput

# 获取审查管道
pipeline = get_review_pipeline()

# 准备输入
inp = ReviewInput(
    conversation_id="conv_abc",
    character_id="neko_girl",
    user_id="user_123",
    user_message="我今天很开心，因为考试通过了！",
    ai_reply="太好了！恭喜你！",
)

# 执行审查
output = pipeline.run(inp)

# 处理结果
print(f"是否写入记忆: {output.should_write_memory}")
if output.should_write_memory:
    print(f"记忆内容: {output.memory_content}")
    print(f"记忆重要性: {output.memory_importance}")

print(f"关系变化: {output.relationship_delta}")
print(f"评分: {output.scores}")
```

### 带剧情选项的审查

```python
from nbot.review.models import ReviewInput

inp = ReviewInput(
    conversation_id="conv_abc",
    character_id="neko_girl",
    user_id="user_123",
    user_message="我选择勇敢面对",
    ai_reply="你做出了正确的选择！",
    selected_choice={
        "level": "turning_point",
        "text": "勇敢面对挑战",
        "intent": "推进剧情",
    },
)

output = pipeline.run(inp)
# 剧情转折点通常会有更高的记忆重要性和关系变化
```

### 带现实时间上下文的审查

```python
from datetime import datetime

now = datetime.now()
inp = ReviewInput(
    conversation_id="conv_abc",
    character_id="neko_girl",
    user_id="user_123",
    user_message="晚上好",
    ai_reply="晚上好！今天过得怎么样？",
    real_time_context={
        "hour": now.hour,
        "day_of_week": now.strftime("%A"),
        "is_weekend": now.weekday() >= 5,
    },
)

output = pipeline.run(inp)
# 现实时间上下文可以影响审查结果
```

## 扩展为 LLM 版本

当前实现为规则版，后续可扩展为 LLM 版本：

```python
class LLMReview:
    """LLM 版审查器（示例）"""
    
    def run(self, inp: ReviewInput) -> ReviewOutput:
        # 调用 LLM 进行审查
        prompt = self._build_prompt(inp)
        response = await llm.chat(prompt)
        
        # 解析 LLM 输出
        return self._parse_response(response)

# 在 ReviewPipeline 中使用
pipeline = ReviewPipeline(mode="llm")
output = pipeline.run(inp)
```

## 最佳实践

1. **事件驱动** - 通过 event_bus 监听审查事件，实现解耦
2. **结果应用** - 审查结果应异步应用，避免阻塞主流程
3. **错误处理** - 审查失败不应影响正常对话流程
4. **日志记录** - 记录审查日志，便于调试和分析
5. **性能优化** - 规则版审查应保持低延迟，避免调用外部服务
