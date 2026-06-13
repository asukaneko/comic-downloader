# react - ReAct Agent

## 概述

`react.py` 实现 ReAct（Reasoning + Acting）Agent 模式，让 AI 能够循环思考和调用工具，逐步推理直至回答问题。

## ReActAgent 类

```python
from nbot.services.react import ReActAgent, get_react_agent

agent = ReActAgent(max_iterations=5, timeout=60)
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_iterations` | 5 | 最大思考循环次数 |
| `timeout` | 60 | 单次思考超时（秒） |

## 全局单例

```python
from nbot.services.react import get_react_agent

agent = get_react_agent()
```

## 数据模型

### ThoughtStep

```python
from nbot.services.react import ThoughtStep

step = ThoughtStep(
    step=1,
    thought="用户想知道天气，我需要查询天气工具",
    action="get_weather",
    action_input="Beijing",
    observation="25°C，晴",
    is_false=False
)
```

- `action="完成"` 或 `is_final=True` 时终止循环
- `action="无"` 或 `action=None` 时不执行工具调用

### ReActResult

```python
from nbot.services.react import ReActResult

result = ReActResult(
    success=True,
    final_answer="北京当前 25°C，晴",
    thought_steps=[step],
    error=None
)
```

## 思考链执行

```python
async def think(question, context, ai_client) -> ReActResult:
```

流程：
1. 构建思考提示词（含用户问题、可用工具列表、历史思考步骤）
2. 调用 AI 客户端获取回复
3. 解析回复为 ThoughtStep（思考→行动→输入）
4. 若行动为"完成"或标记为最终步骤，返回结果
5. 若有工具调用，通过 `plugin_manager.execute_skill()` 执行
6. 记录观察结果，进入下一轮迭代
7. 达到 `max_iterations` 仍未完成时返回当前最佳答案

### 思考提示词格式

```
思考: <你对问题的分析>
行动: <要调用的技能名称，如果没有则写"无">
输入: <技能需要的参数，如果没有则写"无">
观察结果: <技能返回的结果，用于下一步思考>
```

每次迭代将前序思考链追加到提示词末尾，形成上下文。

## 技能执行

```python
async def _execute_action(action, action_input, context) -> str:
```

通过 `plugin_manager.execute_skill()` 调用技能系统。成功时返回 `result.content`，失败时返回错误信息。

## 步骤解析

`_parse_thought()` 从 AI 输出文本中提取 `思考`、`行动`、`输入`、`观察结果` 字段：

| 字段 | 匹配模式 | 说明 |
|------|----------|------|
| `思考` | `思考:` | 分析内容 |
| `行动` | `行动:` | 技能名（"完成"表示终结） |
| `输入` | `输入:` | 技能参数（"无"表示空） |
| `观察结果` | `观察结果:` / `观察:` | 工具返回（由框架填充） |

多行文本自动追加到当前字段。

## 与工具注册集成

ReAct Agent 使用 `SkillDispatcher` 获取可用技能列表，而非直接使用 MCP 或 function calling 工具：

```python
dispatcher = get_skill_dispatcher(plugin_manager)
skills_prompt = dispatcher.get_available_skills_prompt()
```

每个思考步骤中通过 `plugin_manager.execute_skill()` 调用实际技能。

## 相关页面

- [mcp_bridge - MCP 桥梁](./mcp_bridge.md) — MCP 工具与 function calling 转换
- [skills - 技能系统](../plugins/skills.md) — ReAct 底层的技能执行引擎
