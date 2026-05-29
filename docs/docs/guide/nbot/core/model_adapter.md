# model_adapter - 模型适配

## 概述

`model_adapter.py` 提供模型适配的**共享基础设施**，包括统一响应格式 `NormalizedModelResponse`、提供商推断 `ProviderProfile`、消息清洗工具等。

实际的协议适配（URL 构建、请求格式、响应解析）已迁移到 [protocols 多协议适配层](./protocols.md)。

## 架构

```
model_adapter.py          -- 共享工具（NormalizedModelResponse、消息清洗、推理提取）
    |
protocols/
    base.py               -- ModelProtocol 抽象基类 + 注册表
    openai_chat.py        -- v1/chat/completions 协议
    openai_responses.py   -- v1/responses 协议
    anthropic_messages.py -- /v1/messages 协议
```

## 核心数据结构

### NormalizedModelResponse

所有协议解析后的统一响应格式：

```python
from nbot.core.model_adapter import NormalizedModelResponse

@dataclass
class NormalizedModelResponse:
    content: str                    # 提取的文本内容
    finish_reason: str              # "stop" / "tool_calls"
    tool_calls: List[Dict]          # 工具调用列表（OpenAI 标准格式）
    thinking_content: str           # 推理/思考内容
    usage: Dict[str, int]           # token 用量
    raw_message: Dict               # 原始 API 响应
    raw_data: Dict                  # 完整原始数据
```

### ProviderProfile

提供商能力描述：

```python
from nbot.core.model_adapter import ProviderProfile

@dataclass
class ProviderProfile:
    name: str
    endpoint_mode: str           # "openai_chat_completions" / "raw"
    supports_tools: bool
    supports_reasoning: bool
    supports_stream: bool
```

## 共享工具函数

### normalize_usage_dict()

标准化不同提供商的 token 用量字段：

```python
from nbot.core.model_adapter import normalize_usage_dict

# OpenAI: prompt_tokens / completion_tokens
# Anthropic: input_tokens / output_tokens
# 统一输出: {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
usage = normalize_usage_dict(raw_usage)
```

### extract_reasoning_content()

从响应中提取推理/思考内容：

```python
from nbot.core.model_adapter import extract_reasoning_content

thinking = extract_reasoning_content(response_data)
```

### repair_mojibake_text()

修复乱码文本：

```python
from nbot.core.model_adapter import repair_mojibake_text

fixed = repair_mojibake_text("ä½ å¥½")  # -> "你好"
```

## 推荐用法

新代码应直接使用 [protocols 协议层](./protocols.md)：

```python
from nbot.core.protocols import get_protocol

protocol = get_protocol(provider_type)
url = protocol.resolve_url(base_url, model=model)
headers = protocol.build_headers(api_key)
payload = protocol.build_payload(model, messages, stream=False)
normalized = protocol.parse_response(response_data, model=model)
print(normalized.content)
```

## 能力声明

每个模型配置可以声明支持的能力：

```python
model_config = {
    "model": "gpt-4",
    "provider_type": "openai_compatible",
    "supports_tools": True,
    "supports_reasoning": True,
    "supports_stream": True
}
```

## 运行时配置切换

```python
from nbot.services.ai import refresh_runtime_ai_config

config = refresh_runtime_ai_config()
print(f"当前模型: {config['model']}")
print(f"协议: {config['provider_type']}")
```

## 多模型配置

```json
// data/web/ai_models.json
{
    "active_model_id": "model_1",
    "models": [
        {
            "id": "model_1",
            "name": "GPT-4",
            "model": "gpt-4",
            "provider_type": "openai_compatible",
            "enabled": true
        },
        {
            "id": "model_2",
            "name": "Claude 3",
            "model": "claude-3-opus",
            "provider_type": "anthropic",
            "enabled": true
        },
        {
            "id": "model_3",
            "name": "GPT-4.1 Responses",
            "model": "gpt-4.1",
            "provider_type": "openai_responses",
            "enabled": true
        }
    ]
}
```
