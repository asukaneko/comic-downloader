# image_service - 图片生成服务

## 概述

图片生成服务封装了主流图片生成 API（OpenAI 兼容 / SiliconFlow / 自定义协议），供以下两类场景共用：

- **角色立绘生成**（`nbot/web/routes/personality.py`）
- **角色对话中按需生图**（`nbot/core/ai_pipeline.py` 后处理 `_try_send_image`）

v3.0.6 起，角色可在对话中**主动发送图片**：通过 PromptStack 注入的"主动发图能力"段，让 LLM 知道何时何地可以发图，并解析其回复中的 `[send_image: ...]` 标签触发生成与发送。

## 架构

```text
LLM 回复（含 [send_image: ...] 标签）
  │
  ▼
core/ai_pipeline._try_send_image
  ├── extract_send_image_tags()  提取 prompt 列表
  ├── should_send_image_probability()  概率门控
  │
  ▼
image_service.call_image_generation(prompt, config)
  ├── OpenAI 兼容   → POST {base_url}  body={model, prompt, n=1, size}
  ├── SiliconFlow   → POST {base_url}  body={model, prompt, image_size, batch_size=1}
  └── 自定义        → 兜底走 OpenAI 格式
  │
  ▼
_extract_image_url()  解析响应，兼容多种返回结构
  │
  ▼
save_image_to_uploads()  下载/解码并落盘到 nbot/web/static/uploads/...
  │
  ▼
send_image() 回调 → QQ 频道 / Web 频道
```

## 核心 API

### 配置加载

```python
from nbot.services.image_service import get_image_generation_config

config = get_image_generation_config()
# 返回: { api_key, base_url, model, provider_type, provider, append_base_url_path, size }
# 找不到时返回 None
```

**配置来源优先级（从高到低）：**

| 优先级 | 来源 |
|--------|------|
| 1 | 调用方传入的 `image_gen_config` 字典 |
| 2 | `WebChatServer.active_models_by_purpose['image_generation']` 当前选中的模型 |
| 3 | `data/web/ai_models.json` 中 `purpose == "image_generation"` 的第一个启用模型 |
| 4 | 内置默认值 |

> v3.0.6 起新增对 `WebChatServer` 当前选中模型的读取，Web 端切换图片生成模型后无需重启即生效。

### 调用生图

```python
from nbot.services.image_service import call_image_generation, save_image_to_uploads

url_or_b64 = call_image_generation(
    prompt="anime girl cooking in cozy kitchen, warm lighting",
    config=config,
    size="1024x1024",
    extra_keywords=["upper body", "soft smile"],
)
# 成功: 返回图片 URL 或 base64 data URI
# 失败: 返回 None

public_path = save_image_to_uploads(
    image_url_or_b64=url_or_b64,
    upload_dir="/path/to/nbot/web/static/uploads/character_images",
    prefix="image",
)
# 成功: 返回 "/static/uploads/character_images/image_xxx.png"
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `prompt` | `str` | 英文图片描述 prompt |
| `config` | `dict` | 模型配置，至少含 `api_key` / `base_url` / `model` / `provider_type` |
| `size` | `str` | 图片尺寸，如 `"1024x1024"`，空则使用配置或默认 |
| `extra_keywords` | `list[str]` | 追加到 prompt 末尾的关键词列表 |

### PromptStack 注入

```python
from nbot.services.image_service import build_image_capability_injection
from nbot.character.prompt_stack import PromptStack

stack = PromptStack()
ok = build_image_capability_injection(stack)
# 满足全部条件时向 system prompt 追加"主动发图能力"段
```

**注册条件**（需同时满足）：

1. `settings.json` 中 `features.image_generation == True`
2. `ai_models.json` 中已配置 `purpose == "image_generation"` 的可用模型
3. 当前非 agent 会话模式（由调用方在调用前检查）

注入段优先级为 `42`，紧跟 `character.runtime_state`（40）之后，作用域为 `turn`。

### 内联标签解析

```python
from nbot.services.image_service import extract_send_image_tags

cleaned, prompts = extract_send_image_tags(llm_reply)
# cleaned: 已剥离所有 [send_image: ...] 标签的文本
# prompts: 去重后的 prompt 列表（按出现顺序）
```

匹配正则：

```python
SEND_IMAGE_TAG_PATTERN = re.compile(r"\[send_image\s*:\s*([^\]]+?)\s*\]", re.IGNORECASE)
```

### 概率门控

```python
from nbot.services.image_service import should_send_image_probability

if should_send_image_probability():  # 默认从 settings.json 读取
    await send_image(prompt)
```

## 协议适配

### 支持的 provider

| `provider_type` | 请求体关键字段 | 响应解析 |
|-----------------|----------------|----------|
| `openai_compatible` / `openai` | `model`, `prompt`, `n=1`, `size` | `data[0].url` / `data[0].b64_json` |
| `siliconflow` | `model`, `prompt`, `image_size`, `batch_size=1` | `images[0].url` |
| 火山 ark / 豆包 | OpenAI 兼容 | `data[0].url`（size 自动放大到 1920x1920） |
| 自定义文本 | 兜底走 OpenAI 格式 | 兼容 markdown 图片、http URL、base64 data URI |

### 响应结构兼容

`_extract_image_url()` 依次尝试以下结构：

1. `result["data"][0]["url"]` 或 `result["data"][0]["b64_json"]`（OpenAI / 火山 ark）
2. `result["choices"][0]["message"]["content"]` 中的 markdown 图片 / http URL / base64（自定义）
3. `result["images"][0]["url"]`（SiliconFlow）

### 火山引擎 size 下限

火山引擎 ark（豆包）对图片像素数有下限（≥ 3,686,400，约 1920x1920）。`_resolve_size()` 会按 `provider_type` / `base_url` 自动识别火山引擎，并把过小的尺寸放大到 `1920x1920`。

## 配置

### settings.json

```json
{
  "features": {
    "image_generation": true
  },
  "image_generation": {
    "probability": 30,
    "size": "1024x1024"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `features.image_generation` | `bool` | 总开关 |
| `image_generation.probability` | `0-100` | 兜底发图概率（前端滑块，内部归一化为 0~1） |
| `image_generation.size` | `str` | 默认图片尺寸（前端下拉选择） |

### ai_models.json

在 `data/web/ai_models.json` 中添加一条 `purpose: "image_generation"` 的模型记录即可被服务识别。

```json
{
  "id": "img_model_1",
  "purpose": "image_generation",
  "enabled": true,
  "provider_type": "openai_compatible",
  "base_url": "https://api.example.com/v1/images/generations",
  "api_key": "sk-xxx",
  "model": "dall-e-3",
  "size": "1024x1024"
}
```

Web 端在「AI 模型」页将某个图片模型标记为"当前选中"后，`WebChatServer.active_models_by_purpose['image_generation']` 即更新，无需重启。

## Web 前端

### 设置界面

- **总开关**：AI 角色生图功能
- **兜底发图概率**：0~100 的滑块，控制即使 LLM 没有主动发图，系统按概率补一张图的概率
- **默认图片尺寸**：下拉选择（512x512 / 768x768 / 1024x1024 / 1024x1792 / 1792x1024）

### 消息渲染

- AI 生成的图片以裸图形式展示，无气泡包裹
- 图片下方附带 `prompt` 描述（折叠展示，避免打扰阅读）
- 点击图片查看原图
- 包裹容器与提示卡片使用独立 CSS 样式，支持亮色模式

## 与其他模块的关系

| 模块 | 关系 |
|------|------|
| **character** | 通过 `character.image_capability` 动态 PromptStack 段向 LLM 注入"主动发图"能力 |
| **core / ai_pipeline** | 后处理 `_try_send_image` 解析 `[send_image: ...]` 标签，调用本服务生图并发送 |
| **web / server** | `WebChatServer.active_models_by_purpose['image_generation']` 提供当前选中模型 |
| **channels** | `send_image` 回调同时支持 QQ 频道与 Web 频道 |
| **web / routes/personality** | 复用 `call_image_generation` + `save_image_to_uploads` 生成角色立绘 |

## 相关页面

- [ai - AI客户端](./ai.md) — AI 模型配置
- [character - 实时情感引擎](../character/index.md) — PromptStack 动态段
- [web / server - 服务入口](../web/server.md) — `WebChatServer` 当前模型管理
- [chat_service - 聊天服务](./chat_service.md) — `_try_send_image` 后处理位置
