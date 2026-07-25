# PlotChoiceGenerator 选择生成器

AI 驱动的剧情分支选择生成器，每轮调用 LLM 生成 3 个不同级别的选择项。

## 基本用法

```python
from nbot.plot import PlotChoiceGenerator

generator = PlotChoiceGenerator()
choices = await generator.generate(
    response_text=ai_reply,
    turn_context={"mood": "happy", "relationship": "好感度75"},
    session_context={"recent_topics": ["天气", "动漫"], "current_arc": "校园日常"},
    recent_history=[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
    session_id="sess_abc",
)
# 返回: [{"level": "normal", "text": "...", "intent": "..."}, ...]
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `response_text` | `str` | AI 角色的回复文本 |
| `turn_context` | `dict` | 当前轮次上下文（mood, relationship 等） |
| `session_context` | `dict` | 会话级别上下文（recent_topics, current_arc） |
| `recent_history` | `list[dict]` | 最近几轮对话 `[{role, content}, ...]`，用于避免重复 |
| `session_id` | `str` | 会话 ID，用于 token 统计 |

## 选择生成规则

### 三个级别

| 级别 | 推进力度 | 说明 |
|------|----------|------|
| `normal` | 小步 | 顺势推进，带出新细节或下一步动作 |
| `important` | 中步 | 主动开辟新话题、转移场景或推进关系 |
| `turning_point` | 大步 | 时间跳跃、突发事件、新人物或重大决定 |

### 核心铁律

每个选择必须引入「上一轮还不存在的新东西」，从以下至少一类取材：
- 新的行动目标或动作
- 尚未聊过的新话题
- 场景或地点转移
- 时间推移或跳跃
- 新出场人物或关系进展
- 突发外部事件

严禁「原地打转」的写法：复述角色刚说过的话、反复追问同一件事、停留在同一场景情绪中纠缠。

### 文本要求

- 必须使用第一人称或直接动作（"我拉起你往门外走"）
- 禁止元指令句式（"告诉她……""问她是否……"）
- 禁止第三人称描述（"她/他/角色/玩家"）
- 建议 8-24 字

## 文本规范化（_normalize_choice_text）

自动将 AI 生成的元指令转换为第一人称可发送消息：

| AI 输出 | 转换后 |
|---------|--------|
| "告诉她你想去看电影" | "我想告诉你，想去看电影" |
| "问她是否愿意一起去" | "我想问你，是否愿意一起去" |
| "向她表达你的感受" | "我想对你说，我的感受" |
| "握住她的手" | "我握住你的手" |

转换规则：
1. 前缀替换（"告诉她" → "我想告诉你，"）
2. 代词替换（"她的" → "你的"，"她" → "你"）
3. 动作前缀补 "我"（"握住" → "我握住"）

## 错误回退

AI 无响应或解析失败时，回退到默认选择：

```python
_DEFAULT_CHOICES = [
    {"level": "normal", "text": "我拉起你，说走，带你去个地方。", "intent": "顺势推进"},
    {"level": "important", "text": "对了，我一直想跟你聊聊另一件事。", "intent": "主动开辟新话题"},
    {"level": "turning_point", "text": "几天后，我带着一个没人知道的消息回来找你。", "intent": "时间跳跃+突发事件"},
]
```

## AI 调用

使用 `ai_client.chat_completion()` 发送请求，system prompt 包含完整的分支设计指令。token 用量通过 `token_stats` 模块记录（purpose: `PURPOSE_PLOT`）。

## 风格选择（v3.0.6+）

会话可通过 `plot_choice_style` 字段指定本次剧情选项的整体语气与取向。

### 预设风格

| key | 名称 | 说明 |
|-----|------|------|
| `default` | 默认 | 不追加任何风格要求，沿用基础 system prompt |
| `sweet` | 甜蜜暧昧 | 三个选择都带心动、亲近或试探，让关系更靠近一步 |
| `suspense` | 悬疑紧张 | 三个选择都带不安、悬念或压迫感，引入疑点与潜在危机 |
| `daily` | 日常轻松 | 三个选择自然、生活化、带点小趣味，不必强行制造大冲突 |
| `dramatic` | 戏剧转折 | 三个选择都倾向于制造强烈情节起伏，用意外、抉择、冲突推动剧情 |

### 自定义风格

除预设外，前端允许输入任意自定义风格描述（如"偏幽默吐槽""偏诗意抒情"），原样追加到 system prompt 的"本次剧情风格要求"段落中。

### 风格注入逻辑

风格要求由 `_build_system_prompt(style)` 在基础 system prompt 末尾追加：

```text
【本次剧情风格要求】
<style 原文>
注意：风格只影响三个选择的语气与取向，上文"必须推进剧情"的铁律与文本写法要求仍然全部适用。
```

### 会话字段传递路径

```text
Web 前端 (plotChoiceStyle)
  → socket_events  → req.metadata.plot_choice_style
  → ai_pipeline    → ctx.metadata.plot_choice_style
  → PlotChoiceGenerator.generate(style=...)
  → 持久化层 plot_choice_style 字段
```

## 剧情大纲（plot_outline，v3.1.4+）

会话可携带一段"剧情大纲"，用于引导 AI 在生成选项时遵循既定剧情走向。大纲可以是整篇故事梗概，也可以是当前章节的剧情要点。

### 用法

```python
choices = await generator.generate(
    response_text=ai_reply,
    turn_context={...},
    session_context={...},
    recent_history=[...],
    session_id="sess_abc",
    style="dramatic",
    outline="第一章：在雨夜的咖啡馆相遇，主角意外得知对方是失踪多年的青梅竹马……",  # 新增
)
```

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `outline` | `str \| None` | 剧情大纲文本，传入后会被截断到 8000 字符并组合到 user prompt |

### 截断策略

为控制上下文窗口压力，大纲在传入时会截断到 **8000 字符**（覆盖大多数 5k-7k 字大纲）。截断逻辑在 `_build_user_prompt` 中完成，超出部分丢弃并保留前文。

### Prompt 组合

- `_build_system_prompt`：在大纲存在时追加"必须遵循剧情大纲走向"的约束
- `_build_user_prompt`：将大纲原文与当前回合上下文组合发送

### 会话字段传递路径

```text
Web 前端 (plotOutline)
  → socket_events  → req.metadata.plot_outline
  → sessions 路由  → 会话持久化字段 plot_outline
  → ai_pipeline    → ctx.metadata.plot_outline
  → PlotChoiceGenerator.generate(outline=...)
```

前端新增"编辑剧情大纲"按钮与模态框，支持文本域直接编辑、`.txt` 文件导入、清空、字数统计。保存后自动触发选项重新生成。

## AI 调用

使用 `ai_client.chat_completion()` 发送请求，system prompt 包含完整的分支设计指令。token 用量通过 `token_stats` 模块记录（purpose: `PURPOSE_PLOT`）。
