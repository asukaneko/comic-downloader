# openai_chat - OpenAI Chat Completions 协议适配器

## 概述

`OpenAIChatProtocol` 实现了 OpenAI Chat Completions API（`v1/chat/completions`）的协议适配。这是 NekoBot 的**默认协议**——所有未知 `provider_type` 都回退到此协议。

适用场景：OpenAI、DeepSeek、硅基流动、Minimax、智谱 GLM、Qwen 等所有兼容 `v1/chat/completions` 格式的提供商。

## 请求流程

```python
protocol = get_protocol("openai_compatible")
url = protocol.resolve_url("https://api.openai.com", model="gpt-4")
# → "https://api.openai.com/v1/chat/completions"

headers = protocol.build_headers("sk-xxx", stream=True)
# → Authorization: Bearer sk-xxx, Content-Type: application/json

payload = protocol.build_payload("gpt-4", messages, tools=tool_defs)
```

## resolve_url

自动拼接 `/chat/completions`：

| 输入 base_url | 结果 |
|---|---|
| `https://api.openai.com/v1` | `https://api.openai.com/v1/chat/completions` |
| `https://api.deepseek.com` | `https://api.deepseek.com/chat/completions` |
| 已含 `/chat/completions` | 原样返回 |

`append_base_url_path=False` 时直接返回 base_url 原文。

## build_headers

标准 Bearer Token 认证。`stream=True` 时额外添加 `Accept: text/event-stream` 和 `Cache-Control: no-cache`。

## build_payload

核心转换逻辑：

1. **提供商检测**：通过 `infer_provider_profile()` 推断当前模型的能力（是否支持工具调用）
2. **消息归一化**：`normalize_messages_for_provider()` 将内部格式统一为 OpenAI 标准
3. **消息清洗**：`sanitize_messages_for_chat_api()` 移除空内容消息、修正角色顺序、合并连续同角色消息
4. **工具注入**：仅在检测到提供商支持工具时，才添加 `tools` 和 `tool_choice` 字段
5. **额外参数**：`extra_body` 中的参数直接合并到 payload 顶层

最终 payload 结构：

```json
{
  "model": "gpt-4",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": false,
  "tools": [{"type": "function", "function": {...}}],
  "tool_choice": "auto"
}
```

## parse_response

委托给 `normalize_chat_completion_data()` 进行解析：

- 文本路径：`choices[0].message.content`
- 工具调用：`choices[0].message.tool_calls`
- 推理内容：自动探测 `reasoning_content` / `reasoning` 字段（DeepSeek R1 等）
- finish_reason 映射：`"stop"` / `"length"` / `"tool_calls"`
- token 用量从 `usage` 字段提取

## parse_stream_chunk

流式事件处理：

```python
chunk = {"choices": [{"delta": {"content": "你好"}}]}
result = protocol.parse_stream_chunk(chunk)
# → {"type": "content", "content": "你好"}
```

- 文本增量从 `choices[0].delta.content` 提取
- 自动修复乱码文本（`repair_mojibake_text`）
- 非文本块（空 delta、无 choices）返回 `None`，由调用方丢弃

## 错误处理

- `base_url` 为空时抛出 `ValueError("base_url 未配置")`
- 工具调用按 OpenAI 标准 `tool_calls[].function` 结构组织
- 空响应（无 choices 或无 content）返回空字符串

## 注意事项

- `max_tokens` 由上层控制，payload 中不显式传递（大多数兼容服务自动使用模型默认值）
- `extra_body` 可用于传递 `temperature`、`top_p`、`presence_penalty` 等参数
- 工具调用协议参考 OpenAI 标准：`tools[].type="function"`，`tool_calls[].function.name`
- 使用 `append_base_url_path=False` 时，base_url 需自行包含 `/chat/completions` 路径