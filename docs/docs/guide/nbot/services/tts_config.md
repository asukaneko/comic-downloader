# tts_config - TTS/STT 配置管理

## 概述

`tts_config.py` 提供 TTS（文本转语音）和 STT（语音转文本）的配置标准化与解析。配置来源包括 Web 端模型配置和 `config.ini` 回退。

## normalize_tts_config

标准化原始模型配置为统一的 TTS 参数字典：

```python
from nbot.services.tts_config import normalize_tts_config

config = normalize_tts_config(model_config)
```

返回字段：

| 字段 | 来源优先级 | 默认值 |
|------|-----------|--------|
| `api_key` | `resolve_runtime_api_key()` | — |
| `base_url` | `base_url` | `https://api.openai.com/v1` |
| `provider_type` | `provider_type` | `openai_compatible` |
| `tts_provider` | `tts_provider` | `""` |
| `tts_url` | `tts_url` | `""` |
| `tts_model` | `tts_model` > `model` | `gpt-4o-mini-tts` |
| `tts_voice` | `tts_voice` > `voice` | `alloy` |
| `tts_speed` | `tts_speed` > `speed` | `1.0` |
| `tts_pitch` | `tts_pitch` > `pitch` | `1.0` |
| `tts_volume` | `tts_volume` > `volume` | `1.0` |
| `tts_format` | `tts_format` | `mp3` |
| `tts_upload_url` | `tts_upload_url` | `""` |
| `tts_headers` | `tts_headers` | `""` |
| `tts_body_template` | `tts_body_template` | `""` |
| `tts_resource_id` | `tts_resource_id` | `""` |
| `tts_ref_audio` | `tts_ref_audio` | `""` |
| `tts_user` | `tts_user` | `""` |

`voice` 字段若为空或 `"default"`，回退为 `"alloy"`。

## normalize_stt_config

标准化 STT 配置：

```python
from nbot.services.tts_config import normalize_stt_config

config = normalize_stt_config(model_config)
```

| 字段 | 来源优先级 | 默认值 |
|------|-----------|--------|
| `api_key` | `resolve_runtime_api_key()` | — |
| `base_url` | `base_url` | `""` |
| `provider_type` | `provider_type` | `openai_compatible` |
| `stt_provider` | `stt_provider` | `""` |
| `stt_url` | `stt_url` | `""` |
| `stt_model` | `stt_model` > `model` | `whisper-1` |
| `stt_language` | `stt_language` > `language` | `zh` |
| `stt_headers` | `stt_headers` | `""` |
| `device` | `device` | `""` |
| `compute_type` | `compute_type` | `""` |
| `beam_size` | `beam_size` | `5` |

## 服务端配置获取

`get_tts_config_from_server(server, model_id="")` 从 Web 服务端状态解析 TTS 配置：

```python
from nbot.services.tts_config import get_tts_config_from_server

config = get_tts_config_from_server(server)
```

优先级：
1. `model_id` 参数指定的模型
2. `server.active_models_by_purpose["tts"]` 标记的活跃模型
3. 第一个 `purpose="tts"` 且 `enabled=True` 的模型
4. 回退到 `get_tts_config()`

## 回退配置

`get_tts_config()` 在无 Web 配置可用时从 `config.ini` 读取：

```python
from nbot.services.tts_config import get_tts_config

config = get_tts_config()
# 先尝试 get_tts_model_config()，失败则从 config.ini [ApiKey] 读取 api_key
```

## 提供商解析

`provider_type` 和 `tts_provider` 共同决定 TTS 提供商：

| provider_type | 典型值 | 说明 |
|---------------|--------|------|
| `openai_compatible` | OpenAI、MiniMax、SiliconFlow | 标准 OpenAI 兼容 API |
| `doubao` | 豆包 | 字节跳动 TTS |
| `xiaomi` | 小米 | 小米语音合成 |

`resolve_runtime_api_key()` 根据 `provider_type` 自动选择对应的环境变量。

## 自定义 TTS URL

`tts_url`、`tts_upload_url`、`tts_headers`、`tts_body_template` 支持使用非标准 API。`tts_resource_id` 用于指定音频资源 ID，`tts_ref_audio` 用于声音克隆参考音频。

## 相关页面

- [ai - AI 客户端](./ai.md#多模型支持) — TTS/STT 模型配置入口
- [tts - 语音合成](../channel/tts.md) — TTS 适配器使用
- [stt - 语音识别](../channel/stt.md) — STT 适配器使用
