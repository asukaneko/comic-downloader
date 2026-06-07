# stt - 语音识别

## 概述

STT（Speech-to-Text）模块提供可插拔的语音识别能力，采用与 TTS 相同的 **适配器 + 注册表** 架构。支持云端 API 和本地离线两种模式。

```text
音频文件
  -> stt_config.py (配置标准化)
  -> stt_adapters/__init__.py (注册表选择适配器)
  -> 具体适配器 (OpenAI / 小米 / 本地 Whisper)
  -> 识别文本
```

## 架构

### 核心组件

| 文件 | 职责 |
|------|------|
| `stt_adapters/base.py` | 抽象基类 `STTAdapter`，定义统一接口 |
| `stt_adapters/__init__.py` | 适配器注册表，`get_adapter()` 工厂函数 |
| `stt_adapters/openai_adapter.py` | OpenAI 兼容适配器 |
| `stt_adapters/xiaomi_adapter.py` | 小米 MiMo 适配器 |
| `stt_adapters/local_adapter.py` | 本地 faster-whisper 适配器 |
| `stt.py` | STT 服务入口（程序调用） |
| `tts_config.py` | 配置标准化与解析 |

### STTAdapter 基类

所有 STT 适配器继承自 `STTAdapter` 抽象基类：

```python
from abc import ABC, abstractmethod

class STTAdapter(ABC):
    @abstractmethod
    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        """将音频文件转换为文字"""

    def get_supported_params(self) -> list:
        """返回该适配器支持的额外参数列表"""
```

### 注册表

```python
from nbot.services.stt_adapters import get_adapter, get_all_adapters

adapter = get_adapter("openai")          # OpenAI 适配器
adapter = get_adapter("xiaomi")          # 小米适配器
adapter = get_adapter("local")           # 本地 Whisper
adapter = get_adapter("faster_whisper")  # 本地 Whisper 别名
adapter = get_adapter("unknown")         # 回退到 OpenAI（默认）

all_adapters = get_all_adapters()
```

## 提供商

### OpenAI 兼容

支持 OpenAI Whisper、SiliconFlow 及所有兼容 `/v1/audio/transcriptions` 端点的提供商。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_type` | 提供商标识 | `openai_compatible` |
| `stt_model` | 模型名称 | `whisper-1` |
| `stt_language` | 语言代码 | `zh` |

**API 流程：**

1. 以 multipart form 上传音频文件
2. POST 到 `{base_url}/v1/audio/transcriptions`
3. 请求参数：`model`、`language`、`response_format=text`
4. 返回纯文本识别结果

### 小米 MiMo

使用小米 MiMo 的 Chat Completions 接口进行语音识别。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_type` | 提供商标识 | `xiaomi` |
| `stt_model` | 模型名称 | `mimo-v2.5-asr` |
| `stt_language` | 语言代码 | `auto` |

**API 流程：**

1. 读取音频文件并转为 base64 data URL
2. 若音频格式非 wav/mp3（如 webm），自动通过 ffmpeg 转换为 wav
3. 构建 Chat Completions 格式请求体，音频放在 `input_audio` 字段
4. POST 到 `{base_url}/chat/completions`，认证头为 `api-key`
5. 从 `choices[0].message.content` 提取识别文本

::: warning 音频格式限制
小米 API 仅支持 wav 和 mp3 格式。其他格式（webm、ogg、m4a 等）会自动通过 ffmpeg 转换为 wav。请确保系统已安装 ffmpeg。
:::

### 本地 faster-whisper

使用本地部署的 faster-whisper 模型，完全离线运行，无需网络请求。

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `provider_type` | 提供商标识 | `local` / `faster_whisper` |
| `stt_model` | 模型名称 | `tiny` |
| `stt_language` | 语言代码 | `zh` |
| `device` | 计算设备 | `cpu` |
| `compute_type` | 计算精度 | `int8` |
| `beam_size` | Beam search 宽度 | `5` |

**支持的模型：**

| 模型 | 参数量 | 显存需求 | 速度 | 准确度 |
|------|--------|---------|------|--------|
| `tiny` | 39M | ~1GB | 最快 | 一般 |
| `base` | 74M | ~1GB | 快 | 较好 |
| `small` | 244M | ~2GB | 中等 | 好 |
| `medium` | 769M | ~5GB | 较慢 | 很好 |
| `large-v3` | 1550M | ~10GB | 慢 | 最佳 |

**模型别名映射：**

系统会自动将云端模型名映射到本地模型：

| 云端模型名 | 映射到本地 |
|-----------|-----------|
| `whisper-1` | `tiny` |
| `gpt-4o-mini-transcribe` | `base` |
| `gpt-4o-transcribe` | `base` |

**特性：**

- 线程安全的单例模型加载，首次加载后复用
- 支持从项目本地缓存 `data/models/faster-whisper/` 加载模型
- 支持 CUDA GPU 加速（需配置 `device=cuda`）

::: tip 本地部署建议
对于中文识别，推荐使用 `small` 或 `medium` 模型，在速度和准确度之间取得较好平衡。`tiny` 模型适合对延迟敏感但准确度要求不高的场景。
:::

## 配置

### 配置优先级

```text
1. Web 后台 AI 模型配置 (purpose="stt")  ← 推荐
2. config.ini [stt] 段
3. 环境变量
```

### Web 后台配置（推荐）

在 Web 后台的 **AI 能力配置** 页面，添加一个 purpose 为 `stt` 的模型。若不配置云端 STT，系统会自动回退到本地 faster-whisper。

### 统一配置字段

```python
{
    "api_key": str,              # API 密钥
    "base_url": str,             # API 基础 URL
    "provider_type": str,        # 提供商类型: openai_compatible / xiaomi / local
    "stt_provider": str,         # 显式提供商覆盖
    "stt_url": str,              # 自定义端点 URL
    "stt_model": str,            # 模型名称
    "stt_language": str,         # 语言代码: zh / en / auto
    "stt_headers": str,          # 自定义 HTTP 请求头 (JSON 字符串)
    "device": str,               # 计算设备: cpu / cuda (本地专用)
    "compute_type": str,         # 计算精度: int8 / float16 (本地专用)
    "beam_size": int,            # Beam search 宽度 (本地专用)
}
```

### config.ini 配置

```ini
[stt]
local_enabled = false
model = tiny
language = zh
device = cpu
compute_type = int8
beam_size = 5
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `API_KEY` | 全局 API Key 回退 |
| `OPENAI_API_KEY` | OpenAI 专用 Key |
| `NBOT_LOCAL_STT_ENABLED` | 启用本地 faster-whisper |
| `NBOT_FASTER_WHISPER_MODEL` | Whisper 模型名称 |
| `NBOT_FASTER_WHISPER_DEVICE` | 计算设备 (cpu/cuda) |
| `NBOT_FASTER_WHISPER_COMPUTE_TYPE` | 计算精度 (int8/float16) |
| `NBOT_FASTER_WHISPER_BEAM_SIZE` | Beam search 宽度 |
| `NBOT_STT_LANGUAGE` | 默认识别语言 |

## 使用方式

### Web API

```bash
# 语音识别
curl -X POST http://localhost:5000/api/stt/transcribe \
  -F "file=@audio.mp3" \
  -F "language=zh"

# 返回: {"success": true, "text": "识别出的文字", "language": "zh", "provider": "openai"}
```

### 程序调用

```python
from nbot.services.stt import transcribe, transcribe_from_url

# 从本地文件识别
text = transcribe("/path/to/audio.mp3", language="zh")

# 从 URL 识别
text = transcribe_from_url("https://example.com/audio.mp3", language="zh")
```

### Web 后台语音输入

Web 聊天界面支持语音输入，录制的音频会通过 `/api/stt/transcribe` 接口识别为文字后发送。

## 添加新适配器

1. 在 `nbot/services/stt_adapters/` 下创建新文件
2. 继承 `STTAdapter` 并实现 `transcribe()` 方法
3. 在 `__init__.py` 的 `_ADAPTERS` 字典中注册

```python
from nbot.services.stt_adapters.base import STTAdapter

class MySTTAdapter(STTAdapter):
    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        # 实现语音识别逻辑
        ...
        return "识别出的文字"

    def get_supported_params(self) -> list:
        return ["model", "language"]
```

## 相关页面

- [tts - 语音合成](./tts.md) — 配套的 TTS 模块
- [ai - AI客户端](./ai.md) — 多模型配置入口
- [routes - API路由](../web/routes.md) — Voice API 路由
