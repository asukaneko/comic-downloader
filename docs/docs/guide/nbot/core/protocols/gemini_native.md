# gemini_native - Gemini Native 协议适配器

## 概述

`GeminiNativeProtocol` 适配 Google Gemini 原生 API（`models/{model}:generateContent`），将内部 OpenAI 格式消息转换为 Gemini 的 `contents`/`parts` 格式。当 `provider_type` 为 `gemini`、`google` 或 `gemini_native` 时启用。

## 与 OpenAI Chat Completions 的关键差异

| 维度 | OpenAI | Gemini Native |
|---|---|---|
| 认证 | `Authorization: Bearer` | `?key=API_KEY`（URL 参数） |
| 角色名 | `assistant` | `model` |
| 内容结构 | `content: string` | `parts: [{text: "..."}]` |
| system 消息 | 在 `messages[]` 中 | 顶层 `systemInstruction` |
| 工具定义 | `tools[].type="function"` | `tools[].functionDeclarations[]` |
| 工具调用 | `tool_calls` | `parts[].functionCall` |
| 工具结果 | `role: "tool"` | `role: "user"` + `parts[].functionResponse` |
| 对话轮次 | `messages[]` | `contents[]` |

## resolve_url

URL 构建逻辑：

1. 流式模式使用 `:streamGenerateContent`，非流式使用 `:generateContent`
2. 自动拼接 `/models/{model}:{action}`
3. Google 官方 API（`googleapis.com` 或 `google.com`）自动追加 `?key={api_key}`
4. 通过 `&` 处理已有 query 参数的 URL

```python
protocol.resolve_url("https://generativelanguage.googleapis.com", model="gemini-2.0-flash", api_key="xxx")
# → "https://generativelanguage.googleapis.com/models/gemini-2.0-flash:generateContent?key=xxx"
```

## build_headers

- `Content-Type: application/json` 总是设置
- `Authorization: Bearer` 同时发送（兼容代理/中转服务）
- `stream=True` 时添加 `Accept: text/event-stream`

## build_payload

`_convert_messages()` 执行核心转换：

**system 指令**：从消息列表中提取 system 消息，放入顶层 `systemInstruction`：
```json
{"systemInstruction": {"parts": [{"text": "你是助手"}]}}
```

**user 消息**：
- 纯文本 → `{"text": "你好"}`
- `image_url`（data URI） → `{"inlineData": {"mimeType": "image/png", "data": "base64..."}}`
- 多模态 content block 数组 → 分别转换

**assistant（model）消息**：
- 角色从 `assistant` → `model`
- `_thinking_content` → `{"thought": "..."}`
- 普通文本 → `{"text": "..."}`
- 工具调用 → `{"functionCall": {"name": "...", "args": {...}}}`

**tool 结果**：
```json
{
  "role": "user",
  "parts": [{"functionResponse": {"name": "get_weather", "response": {"result": "25°C"}}}]
}
```

**工具定义转换**（`_convert_tools`）：

```python
# OpenAI: {"type": "function", "function": {"name": "get_weather", "parameters": {...}}}
# Gemini: [{"functionDeclarations": [{"name": "get_weather", "parameters": {...}}]}]
```

工具定义中的 JSON Schema 扩展字段（`$schema`、`$id`、`$ref`、`$defs`、`definitions`）被 `_strip_json_schema_extras()` 递归移除，因为 Gemini API 不接受这些字段。

## thoughtSignature 处理

Gemini 多轮工具调用需要 `thoughtSignature` 来回传：

- **解析时**：从 `functionCall.thoughtSignature` 或 part 级别的 `thoughtSignature` 中提取，存入 `tool_call["_thought_signature"]`
- **构建时**：回读 `_thought_signature`，放入 `functionCall` 的同级字段
- 这是一个**内部隐式字段**，不在 `NormalizedModelResponse` 的公开字段中暴露

## parse_response

遍历 `candidates[0].content.parts`：

| part 类型 | 提取 |
|---|---|
| `text` | 文本内容 |
| `thought` | 推理内容 |
| `functionCall` | 构建 tool_calls + 提取 thoughtSignature |

安全拦截处理：`promptFeedback.blockReason` 非空时返回拦截提示文本而不是空结果。

finish_reason 映射：`STOP` → `"stop"`，`MAX_TOKENS` → `"length"`，其他 → `"stop"`。

用量从 `usageMetadata` 提取：`promptTokenCount` → `prompt_tokens`，`candidatesTokenCount` → `completion_tokens`。

## parse_stream_chunk

流式 `candidates[0].content.parts` 遍历：

- `text` → `{"type": "content", "content": "..."}`
- `functionCall` → `{"type": "tool_call_start", "tool_call": {...}}`（含 `_thought_signature`）
- `usageMetadata` 非空 → `{"type": "usage", "usage": {...}}`

### 边界场景处理

为提升流式响应的健壮性，解析器在以下场景中**不会抛异常**，而是安全降级：

| 场景 | 行为 |
|------|------|
| `candidates` / `content` / `parts` 为 `None` | 返回 `{"type": "content", "content": ""}` |
| `candidates` 为空数组 | 返回 `{"type": "content", "content": ""}` |
| chunk 仅含 `usageMetadata`（无 content） | 返回 `{"type": "usage", "usage": {...}}` |
| chunk 仅含 `finishReason`（流结束，content 为 None） | 返回 `{"type": "content", "content": ""}` |
| `candidate` / `part` 不是 dict 类型 | 跳过该节点继续处理 |

Gemini 流式请求默认携带 `?alt=sse` 参数，确保返回标准 SSE 格式（部分代理会自动追加）。

## 注意事项

- 认证：Google 官方 API 使用 URL query 参数 `?key=`，非 Google 的中转服务使用 `Authorization: Bearer`
- JSON Schema 清理：`_strip_json_schema_extras` 移除 Gemini 明确拒绝的字段（包括 `additionalProperties` 等扩展字段）
- `tool_choice` 参数当前被忽略（Gemini 不直接支持）
- `maxOutputTokens` 通过 `generationConfig` 传递
- `extra_body` 支持 `temperature`、`topP`、`topK`、`responseMimeType`、`responseSchema` 等
- 多轮工具调用必须正确回传 `thoughtSignature`，否则 API 会报错