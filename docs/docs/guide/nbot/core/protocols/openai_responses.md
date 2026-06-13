# openai_responses - OpenAI Responses API 协议适配器

## 概述

`OpenAIResponsesProtocol` 适配 OpenAI 新一代 Responses API（`v1/responses`）。与 Chat Completions 不同，Responses API 使用 `input` 数组代替 `messages`，返回结果在 `output` 数组中组织为带类型的 content block。

当 `provider_type` 为 `openai_responses` 时启用此协议。

## Chat Completions vs Responses 核心差异

| 维度 | Chat Completions | Responses API |
|---|---|---|
| 输入字段 | `messages[]` | `input[]`（类型化 items） |
| 输出结构 | `choices[].message` | `output[]`（类型化 items） |
| system 消息 | `role: "system"` | `role: "developer"` + `type: "message"` |
| 工具结果 | `role: "tool"` | `type: "function_call_output"` |
| 流式事件 | `delta.content` | `response.output_text.delta` |
| 最大输出 token | `max_tokens` | `max_output_tokens` |

## resolve_url

补充 `/responses` 路径。特殊处理：已有 `/responses` 但不含 `/chat/` 的 URL 不重复拼接。

## build_payload

主要转换由 `_convert_messages_to_input` 完成：

**system → developer**：
```json
// 输入: {"role": "system", "content": "你是助手"}
// 输出: {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "你是助手"}]}
```

**user 消息**（支持多模态 content block）：
```json
// {"type": "text"} → {"type": "input_text"}
// {"type": "image_url"} → {"type": "input_image", "image_url": "..."}
```

**assistant 消息 + 工具调用**：
- 文本部分 → `type: "message"` + `role: "assistant"` + `output_text`
- 每个 `tool_calls[i]` → 独立 `type: "function_call"` item

**tool 结果**：
```json
// {"role": "tool", "tool_call_id": "call_xxx", "content": "42"}
// → {"type": "function_call_output", "call_id": "call_xxx", "output": "42"}
```

**工具定义**：`_convert_tools()` 将 OpenAI 标准 tools 转为 Responses 格式，添加 `strict: false`。

**tool_choice**：`"auto"` → `{"type": "auto"}`，`"required"` → `{"type": "required"}`，`"none"` → `{"type": "none"}`。

请求体示例：

```json
{
  "model": "gpt-4",
  "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "你好"}]}],
  "tools": [{"type": "function", "name": "get_weather", "parameters": {...}}],
  "max_output_tokens": 4096
}
```

## parse_response

遍历 `data["output"]` 数组，按 `item["type"]` 分发：

- `"message"` → 遍历 `content[]`，提取 `output_text`（正文）和 `reasoning_text`（推理）
- `"function_call"` → 构建 OpenAI 标准 `tool_calls` 格式
- `"reasoning"` → 提取推理文本

文本通过 `repair_mojibake_text` 清洗后组装到 `NormalizedModelResponse`。

## parse_stream_chunk

响应事件类型映射：

| 事件类型 | 返回 |
|---|---|
| `response.output_text.delta` | `{"type": "content", "content": "..."}` |
| `response.output_text.done` | `None`（跳过） |
| `response.function_call_arguments.delta` | `None`（跳过） |
| `response.output_item.done` (function_call) | `{"type": "tool_call_start", "tool_call": {...}}` |
| `response.completed` | `{"type": "usage", "usage": {...}}` 或 `{"type": "stop"}` |

## 注意事项

- Responses API 不支持 `max_tokens`，使用 `max_output_tokens` 替代
- 系统消息的角色被映射为 `developer`，与 Chat Completions 不同
- 当前仅对 `temperature`、`top_p`、`instructions` 三个 `extra_body` 键生效