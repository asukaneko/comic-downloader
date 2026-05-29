# protocols - 多协议适配层

## 概述

`nbot/core/protocols/` 提供统一的多协议适配层，将不同 AI 模型 API 的请求/响应格式抽象为统一接口。选择模型的 `provider_type` 后，系统自动使用对应的接口地址、请求头、请求格式和响应解析器。

## 支持的协议

| 协议 | 文件 | 接口端点 | 适用场景 |
|------|------|----------|----------|
| OpenAI Chat Completions | `openai_chat.py` | `v1/chat/completions` | OpenAI、DeepSeek、硅基流动等兼容服务 |
| OpenAI Responses | `openai_responses.py` | `v1/responses` | OpenAI 新一代 API，支持 agent 和内置工具 |
| Anthropic Messages | `anthropic_messages.py` | `/v1/messages` | Claude 原生 API |
| Gemini Native | `gemini_native.py` | `models/{model}:generateContent` | Gemini 原生 API，支持多模态、thinking、结构化输出 |

## 核心接口

### ModelProtocol

所有协议实现的抽象基类：

```python
class ModelProtocol(ABC):
    name: str                    # 协议标识
    display_name: str            # 人类可读名称
    url_suffix: str              # 自动补全的 URL 后缀

    def resolve_url(base_url, model, *, append_base_url_path) -> str
    def build_headers(api_key, *, stream) -> dict
    def build_payload(model, messages, *, tools, stream, ...) -> dict
    def parse_response(data, *, model, ...) -> NormalizedModelResponse
    def parse_stream_chunk(chunk_data) -> Optional[dict]
    def supports_tools() -> bool
```

### get_protocol()

根据 `provider_type` 获取对应协议实例：

```python
from nbot.core.protocols import get_protocol

protocol = get_protocol("anthropic")          # -> AnthropicMessagesProtocol
protocol = get_protocol("openai_compatible")  # -> OpenAIChatProtocol
protocol = get_protocol("openai_responses")   # -> OpenAIResponsesProtocol
```

### list_protocols()

返回所有已注册协议的元数据（供 UI 下拉框使用）：

```python
from nbot.core.protocols import list_protocols

protocols = list_protocols()
# [
#   {"key": "openai_compatible", "name": "OpenAI Chat Completions", "url_suffix": "/chat/completions", ...},
#   {"key": "openai_responses", "name": "OpenAI Responses API", "url_suffix": "/responses", ...},
#   {"key": "anthropic", "name": "Anthropic Messages", "url_suffix": "/v1/messages", ...},
# ]
```

## provider_type 映射

| provider_type 值 | 协议实现 |
|------------------|----------|
| `openai_compatible` / `openai` / `custom` / `deepseek` / `siliconflow` | OpenAI Chat Completions |
| `openai_responses` | OpenAI Responses |
| `anthropic` / `claude` | Anthropic Messages |
| `gemini` / `google` / `gemini_native` | Gemini Native (generateContent) |

未知类型默认回退到 OpenAI Chat Completions。

## 三种协议对比

### 请求格式

**OpenAI Chat Completions** -- 用 `messages[]` 表示对话：

```json
{
  "model": "gpt-4",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": false
}
```

**OpenAI Responses** -- 用 `input` 表示输入：

```json
{
  "model": "gpt-4",
  "input": [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "你好"}]}],
  "max_output_tokens": 4096
}
```

**Anthropic Messages** -- system 在顶层，`max_tokens` 必传：

```json
{
  "model": "claude-3-opus",
  "system": "你是助手",
  "messages": [{"role": "user", "content": "你好"}],
  "max_tokens": 4096
}
```

### 响应文本提取

| 协议 | 文本路径 |
|------|----------|
| OpenAI Chat | `choices[0].message.content` |
| OpenAI Responses | `output[].content[].type=="output_text"` |
| Anthropic | `content[].type=="text"` |
| Gemini Native | `candidates[0].content.parts[0].text` |

### 工具调用格式

| 协议 | 工具定义 | 工具调用 | 工具结果 |
|------|----------|----------|----------|
| OpenAI Chat | `tools[].type="function"` | `tool_calls[].function.name` | `role: "tool"` |
| OpenAI Responses | `tools[].type="function"` | `output[].type="function_call"` | `type: "function_call_output"` |
| Anthropic | `tools[].name,input_schema` | `content[].type="tool_use"` | `type: "tool_result"` |
| Gemini Native | `tools[].functionDeclarations[]` | `parts[].functionCall` | `parts[].functionResponse` (role: "user") |

### 流式事件

| 协议 | 文本增量 |
|------|----------|
| OpenAI Chat | `choices[0].delta.content` |
| OpenAI Responses | `event.type == "response.output_text.delta"` |
| Anthropic | `content_block_delta.delta.text` |
| Gemini Native | `candidates[0].content.parts[0].text` |

## 使用方式

### 直接使用协议

```python
from nbot.core.protocols import get_protocol
from nbot.core.model_adapter import response_json_utf8
import requests

protocol = get_protocol("anthropic")
url = protocol.resolve_url("https://api.anthropic.com", model="claude-3-opus")
headers = protocol.build_headers(api_key)
payload = protocol.build_payload("claude-3-opus", messages, stream=False)

resp = requests.post(url, json=payload, headers=headers, timeout=120)
normalized = protocol.parse_response(response_json_utf8(resp), model="claude-3-opus")
print(normalized.content)
```

### 通过 AIClient 使用

```python
from nbot.services.ai import ai_client

# 自动根据 provider_type 选择协议
response = ai_client.chat_completion(messages, stream=False)
```

### 通过 Pipeline 使用

```python
from nbot.core.ai_pipeline import AIPipeline, PipelineContext

pipeline = AIPipeline()
result = pipeline.process(ctx, callbacks, tools=tools)
# Pipeline 内部自动根据模型配置选择协议
```

## Web UI 集成

模型配置页面的 Provider 类型下拉框从 `/api/ai-models/protocols` 接口动态获取已注册协议。选择协议后：

- 自动显示对应的 URL 后缀（如 `/chat/completions`、`/v1/messages`、`/responses`）
- 开启「自动补全 Base URL 后缀」时，自动拼接协议路径
- 关闭时，Base URL 作为完整地址使用，但请求仍使用选中协议的格式

## 扩展新协议

实现 `ModelProtocol` 并注册：

```python
from nbot.core.protocols.base import ModelProtocol, register_protocol

class MyCustomProtocol(ModelProtocol):
    @property
    def name(self) -> str:
        return "my_custom"

    @property
    def display_name(self) -> str:
        return "My Custom API"

    @property
    def url_suffix(self) -> str:
        return "/v1/custom"

    # ... 实现其他抽象方法

register_protocol("my_custom", MyCustomProtocol)
```

然后在 `base.py` 的 `_PROVIDER_ALIASES` 中添加映射即可。
