# tts - 语音合成

## 概述

TTS（Text-to-Speech）模块提供可插拔的语音合成能力，采用 **适配器 + 注册表** 架构，支持多个 TTS 提供商之间无缝切换。

```text
用户文本
  -> tts_config.py (配置标准化)
  -> tts_adapters/__init__.py (注册表选择适配器)
  -> 具体适配器 (OpenAI / 小米 / 豆包)
  -> 音频文件 (.mp3)
```

## 架构

### 核心组件

| 文件 | 职责 |
|------|------|
| `tts_adapters/base.py` | 抽象基类 `TTSAdapter`，定义统一接口 |
| `tts_adapters/__init__.py` | 适配器注册表，`get_adapter()` 工厂函数 |
| `tts_adapters/openai_adapter.py` | OpenAI 兼容适配器 |
| `tts_adapters/xiaomi_adapter.py` | 小米 MiMo 适配器 |
| `tts_adapters/doubao_adapter.py` | 豆包（火山引擎）适配器 |
| `tts.py` | QQ Bot 侧 TTS 服务入口 |
| `tts_config.py` | 配置标准化与解析 |

### TTSAdapter 基类

所有 TTS 适配器继承自 `TTSAdapter` 抽象基类：

```python
from abc import ABC, abstractmethod

class TTSAdapter(ABC):
    @abstractmethod
    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        """合成语音并保存到文件，返回输出文件路径"""

    def get_default_body_template(self) -> str:
        """返回该适配器的默认请求体模板"""

    def get_supported_params(self) -> list:
        """返回该适配器支持的额外参数列表"""
```

基类还提供两个静态工具方法：

- `_parse_custom_headers(headers_str)` — 解析自定义 HTTP 请求头 JSON 字符串
- `_render_body(template, variables)` — 渲染 `{{variable}}` 模板语法

### 注册表

适配器在模块导入时以单例形式注册：

```python
from nbot.services.tts_adapters import get_adapter, get_all_adapters

# 根据 provider_type 获取适配器
adapter = get_adapter("openai")       # OpenAI 适配器
adapter = get_adapter("xiaomi")       # 小米适配器
adapter = get_adapter("doubao")       # 豆包适配器
adapter = get_adapter("volcengine")   # 豆包别名
adapter = get_adapter("unknown")      # 回退到 OpenAI（默认）

# 获取所有可用适配器信息
all_adapters = get_all_adapters()
```

## 提供商

### OpenAI 兼容

支持 OpenAI、SiliconFlow 及所有兼容 `/v1/audio/speech` 端点的提供商。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_type` | 提供商标识 | `openai_compatible` |
| `tts_model` | 模型名称 | `gpt-4o-mini-tts` |
| `tts_voice` | 音色 | `alloy` |
| `tts_format` | 音频格式 | `mp3` |
| `tts_speed` | 语速 (0.25-4.0) | `1.0` |

**内置音色（13 个）：**

| 音色 | 描述 |
|------|------|
| `alloy` | 中性均衡 |
| `echo` | 温暖共鸣 |
| `fable` | 富有表现力 |
| `onyx` | 深沉权威 |
| `nova` | 明亮活力 |
| `shimmer` | 柔和温柔 |
| `coral` | 友好对话 |
| `verse` | 诗意韵律 |
| `ballad` | 流畅抒情 |
| `ash` | 沉稳从容 |
| `sage` | 睿智深思 |
| `marin` | 清晰明快 |
| `cedar` | 温暖自然 |

支持通过 Web 后台上传自定义音色（SiliconFlow API）。

**API 流程：**

1. 构建 JSON 请求体（model, voice, input, speed, format）
2. POST 到 `{base_url}/v1/audio/speech`
3. 响应为音频二进制流，直接写入文件
4. 若响应为 JSON 且包含 `audio_url`，则下载该 URL 的音频

### 小米 MiMo

使用小米 MiMo 的 Chat Completions 接口进行语音合成。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_type` | 提供商标识 | `xiaomi` |
| `tts_model` | 模型名称 | `mimo-v2.5-tts` |
| `tts_voice` | 音色 | `mimo_default` |
| `tts_format` | 音频格式 | `mp3` |

**内置音色（9 个）：**

| 音色 | 描述 |
|------|------|
| `mimo_default` | 默认音色 |
| `冰糖` | 中文女声 - 温柔甜美 |
| `茉莉` | 中文女声 - 清新自然 |
| `苏打` | 中文男声 - 阳光活力 |
| `白桦` | 中文男声 - 沉稳磁性 |
| `Mia` | 英文女声 |
| `Chloe` | 英文女声 |
| `Milo` | 英文男声 |
| `Dean` | 英文男声 |

**API 流程：**

1. 构建 Chat Completions 格式请求体，文本放在 `assistant` 消息中
2. POST 到 `{base_url}/chat/completions`，认证头为 `api-key`
3. 响应中音频位于 `choices[0].message.audio`，支持 URL 或 base64 两种格式

### 豆包（火山引擎）

使用火山引擎 TTS V3 的 HTTP Chunked 端点。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_type` | 提供商标识 | `doubao` / `volcengine` |
| `tts_voice` | 音色 ID | `zh_female_shuangkuaisisi_moon_bigtts` |
| `tts_format` | 音频格式 | `mp3` |
| `tts_speed` | 语速 | `0` |
| `tts_volume` | 音量 | `0` |
| `tts_resource_id` | 资源 ID | `seed-tts-2.0` |

**内置音色（16 个）：**

| 音色 ID | 名称 | 描述 |
|---------|------|------|
| `zh_female_shuangkuaisisi_moon_bigtts` | 爽快思思 | 甜美活泼 |
| `zh_male_bvlazysheep` | 懒羊羊 | 慵懒磁性 |
| `zh_male_ahu_conversation_wvae_bigtts` | 阿虎 | 对话风格 |
| `zh_female_vv_uranus_bigtts` | VV | 支持方言 |
| `zh_female_cancan_mars_bigtts` | 灿灿 | 阳光活力 |
| `zh_male_chongchong_mars_bigtts` | 冲冲 | 活力少年 |
| `zh_female_dandan_mars_bigtts` | 旦旦 | 温柔知性 |
| `zh_male_dongbeihaoran_mars_bigtts` | 浩然 | 东北方言 |
| `zh_female_gufeng_mars_bigtts` | 古风 | 古典韵味 |
| `zh_male_haoyu_mars_bigtts` | 浩宇 | 成熟稳重 |
| `zh_female_shuangkuang_mars_bigtts` | 爽快 | 直爽大方 |
| `zh_male_tianyuan_mars_bigtts` | 田园 | 温暖治愈 |
| `zh_female_wanwan_mars_bigtts` | 婉婉 | 温柔甜美 |
| `zh_female_xinrui_mars_bigtts` | 心蕊 | 知性优雅 |
| `zh_male_yunxi_mars_bigtts` | 云希 | 清新少年 |
| `zh_female_yunxia_mars_bigtts` | 云霞 | 温暖亲切 |

**API 流程：**

1. 构建包含 `req_params` 的 JSON 请求体
2. POST 到 `https://openspeech.bytedance.com/api/v3/tts/unidirectional`
3. 认证头：`X-Api-Key`（API Key）+ `X-Api-Resource-Id`（资源 ID）
4. 响应为 chunked JSON 流，每个 chunk 包含 base64 编码的音频片段
5. 收集所有片段后拼接写入文件

## 配置

### 配置优先级

```text
1. Web 后台 AI 模型配置 (purpose="tts")  ← 推荐
2. config.ini [voice] 段
3. 环境变量
```

### Web 后台配置（推荐）

在 Web 后台的 **AI 能力配置** 页面，添加一个 purpose 为 `tts` 的模型，填入对应的 API Key、Base URL、模型名称等字段。系统会自动根据 `provider_type` 选择对应的适配器。

### 统一配置字段

```python
{
    "api_key": str,              # API 密钥
    "base_url": str,             # API 基础 URL
    "provider_type": str,        # 提供商类型: openai_compatible / xiaomi / doubao
    "tts_provider": str,         # 显式提供商覆盖
    "tts_url": str,              # 自定义端点 URL
    "tts_model": str,            # 模型名称
    "tts_voice": str,            # 音色标识
    "tts_speed": float,          # 语速 0.25-4.0
    "tts_pitch": float,          # 音调 0.5-2.0
    "tts_volume": float,         # 音量 0.0-2.0
    "tts_format": str,           # 音频格式: mp3 / wav / opus / flac
    "tts_headers": str,          # 自定义 HTTP 请求头 (JSON 字符串)
    "tts_body_template": str,    # 自定义请求体模板 ({{variable}} 语法)
    "tts_upload_url": str,       # 自定义音色上传端点
    "tts_resource_id": str,      # 豆包专用资源 ID
}
```

### config.ini 配置

```ini
[voice]
voice = fnlp/MOSS-TTSD-v0.5:diana
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `API_KEY` | 全局 API Key 回退 |
| `OPENAI_API_KEY` | OpenAI 专用 Key |
| `VOICE` | 旧版 voice 格式 `model:voice` |

## 使用方式

### QQ Bot

在 QQ 群中使用 `/tts` 命令开关 TTS 功能。开启后，Bot 的文字回复会自动附带语音消息。

### Web API

```bash
# 语音合成
curl -X POST http://localhost:5000/api/tts/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "你好，世界", "model_id": "your-tts-model-id"}'

# 返回: {"success": true, "audio_url": "/api/tts/audio/xxx.mp3"}

# 获取音频文件
curl http://localhost:5000/api/tts/audio/xxx.mp3 -o output.mp3
```

### TTS Playground

Web 后台提供 TTS Playground 页面，支持：

- 在线试听所有音色
- 实时合成预览
- 上传自定义音色

### 程序调用

```python
from nbot.services.tts_adapters import get_adapter
from nbot.services.tts_config import get_tts_config

config = get_tts_config()
adapter = get_adapter(config.get("provider_type", ""))
adapter.synthesize("你好，世界", config, "/tmp/output.mp3")
```

## 自定义请求体模板

对于非标准 API，可通过 `tts_body_template` 自定义请求体：

```json
{
    "tts_body_template": "{\"model\":\"{{model}}\",\"voice\":\"{{voice}}\",\"input\":\"{{text}}\",\"speed\":{{speed}}}"
}
```

可用变量：`model`、`voice`、`text`、`speed`、`pitch`、`volume`、`response_format`

## 添加新适配器

1. 在 `nbot/services/tts_adapters/` 下创建新文件
2. 继承 `TTSAdapter` 并实现 `synthesize()` 方法
3. 在 `__init__.py` 的 `_ADAPTERS` 字典中注册

```python
from nbot.services.tts_adapters.base import TTSAdapter

class MyTTSAdapter(TTSAdapter):
    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        # 实现语音合成逻辑
        ...
        return output_path

    def get_supported_params(self) -> list:
        return ["model", "voice", "text"]
```

## 相关页面

- [stt - 语音识别](./stt.md) — 配套的 STT 模块
- [ai - AI客户端](./ai.md) — 多模型配置入口
- [routes - API路由](../web/routes.md) — Voice API 路由
