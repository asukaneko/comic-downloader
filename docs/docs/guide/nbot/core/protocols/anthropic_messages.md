# anthropic_messages - Anthropic Messages 协议适配器

## 概述

`AnthropicMessagesProtocol` 适配 Anthropic Messages API（`/v1/messages`），将 NekoBot 内部的 OpenAI 格式消息转换为 Anthropic 原生格式。当 `provider_type` 为 `anthropic` 或 `claude` 时启用。

## 与 OpenAI Chat Completions 的关键差异

| 维度 | OpenAI | Anthropic |
|---|---|---|
| 认证 | `Authorization: Bearer` | `x-api-key` |
| system 消息 | 在 `messages[]` 中 | 顶层 `system` 字段 |
| assistant 角色 | `role: "assistant"` | `role: "assistant"` |
| 工具调用 | `tool_calls[].function` | `content[].type="tool_use"` |
| 工具结果 | `role: "tool"` | `type: "tool_result"`（合并到 user 消息） |
| max_tokens | 可选 | **必传** |
| API 版本 | 无 | `anthropic-version: 2023-06-01` |

## build_headers

使用 `x-api-key` 头传递 API 密钥，固定附加 `anthropic-version: 2023-06-01`。`stream=True` 时添加 `Accept: text/event-stream`。

## build_payload

`_convert_messages()` 承担核心转换：

**system 消息提取**：
```python
# 输入: [{"role": "system", "content": "你是助手"}, {"role": "user", "content": "你好"}]
# 输出: system="你是助手", messages=[{"role": "user", "content": "你好"}]
```

system 消息从消息列表中剥离，放入顶层 `payload["system"]`。

**assistant 消息 + 工具调用重建**：
```python
# 处理 _thinking_content 字段（DeepSeek R1 等模型要求回传 thinking block）
blocks = []
if thinking_text:
    blocks.append({"type": "thinking", "thinking": thinking_text})
if content:
    blocks.append({"type": "text", "text": content})
for tc in tool_calls:
    blocks.append({"type": "tool_use", "id": tc["id"], "name": func["name"], "input": args})
```

**tool 结果合并**：
```python
# 连续多条 tool_result 自动合并到同一条 user 消息
{
    "role": "user",
    "content": [
        {"type": "tool_result", "tool_use_id": "call_xxx", "content": "42"},
        {"type": "tool_result", "tool_use_id": "call_yyy", "content": "36"},
    ]
}
```

**工具定义转换**（`_convert_tools`）：
```python
# OpenAI: {"type": "function", "function": {"name": "get_weather", "parameters": {...}}}
# Anthropic: {"name": "get_weather", "input_schema": {...}}
# 注意字段名变化：parameters → input_schema
```

**tool_choice 映射**：`"auto"` → `{"type": "auto"}`，`"required"` → `{"type": "any"}`，`"none"` → `None`（不传 tool_choice）。

## parse_response

遍历 `data["content"]` 数组，按 block 类型分发：

| block 类型 | 提取内容 |
|---|---|
| `"text"` | 文本内容 |
| `"thinking"` | 推理内容（`block["thinking"]`） |
| `"tool_use"` | 构建 `tool_calls`（id、name、arguments） |

finish_reason 映射：`"end_turn"` / `"stop"` → `"stop"`，有工具调用 → `"tool_calls"`。

Token 用量字段名翻译：`input_tokens` → `prompt_tokens`，`output_tokens` → `completion_tokens`。

## parse_stream_chunk

事件类型处理：

| 事件类型 | delta 类型 | 返回 |
|---|---|---|
| `content_block_delta` | `text_delta` | `{"type": "content", "content": "..."}` |
| `content_block_delta` | `thinking_delta` | `{"type": "thinking", "thinking": "..."}` |
| `content_block_start` | `tool_use` | `{"type": "tool_call_start", "tool_call": {...}}` |
| `message_stop` | - | `{"type": "stop"}` |

Anthropic 的 thinking 内容通过 `thinking_delta` 事件流式输出，与文本增量走不同的路径。

## 注意事项

- `max_tokens` 是 Anthropic API 的必传字段，默认 4096
- `extra_body` 仅透传 `temperature`、`top_p`、`top_k` 三个参数
- `_thinking_content` 由上游（如 DeepSeek 推理模型）填充，协议层负责正确回传
- tool result 消息合并策略：连续 tool_result 自动合入同一条 user 消息（Anthropic 要求）