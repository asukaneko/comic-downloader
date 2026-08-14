"""通义千问 Qwen TTS 适配器"""
import base64
import json
import logging

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.tts_adapters.base import TTSAdapter

_log = logging.getLogger(__name__)

QWEN_VOICES = [
    {"id": "Cherry", "name": "Cherry", "description": "中文女声 - 青春活泼"},
    {"id": "Serena", "name": "Serena", "description": "中文女声 - 温柔知性"},
    {"id": "Ethan", "name": "Ethan", "description": "中文男声 - 沉稳磁性"},
    {"id": "Elias", "name": "Elias", "description": "中文男声 - 阳光少年"},
    {"id": "Luna", "name": "Luna", "description": "英文女声 - English female"},
    {"id": "Carson", "name": "Carson", "description": "英文男声 - English male"},
]


def _resolve_dashscope_generation_url(base_url: str, custom_url: str = "") -> str:
    """解析 DashScope 多模态生成端点（TTS）地址。"""
    if custom_url:
        return custom_url

    base = (base_url or "").strip().rstrip("/").replace("/compatible-mode/v1", "/api/v1")
    suffix = "/services/aigc/multimodal-generation/generation"
    default_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
    if base.endswith(suffix):
        return base
    if base:
        return f"{base}{suffix}"
    return default_url


class QwenTTSAdapter(TTSAdapter):
    """通义千问 Qwen TTS 适配器

    API: POST /api/v1/services/aigc/multimodal-generation/generation
    认证: Authorization: Bearer <key>
    模型: qwen3-tts-flash
    响应: JSON {output: {audio: {data: <base64>}}}
    """

    def get_supported_params(self) -> list:
        return ["model", "voice", "language"]

    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("Qwen TTS 需要 API Key，请在模型配置中设置 api_key")

        model = config.get("tts_model") or config.get("model") or "qwen3-tts-flash"
        voice = (config.get("tts_voice") or "Cherry").strip()
        if not voice or voice == "default":
            voice = "Cherry"

        language = config.get("tts_language") or config.get("language") or ""
        language_type = {
            "zh": "Chinese",
            "en": "English",
            "ja": "Japanese",
            "ko": "Korean",
        }.get(language.lower(), "Auto")

        url = _resolve_dashscope_generation_url(
            config.get("base_url", ""), config.get("tts_url", "")
        )

        body = {
            "model": model,
            "input": {
                "text": text,
                "voice": voice,
                "language_type": language_type,
            },
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        extra = self._parse_custom_headers(config.get("tts_headers", ""))
        if extra:
            headers.update(extra)

        _log.info("Qwen TTS: url=%s, model=%s, voice=%s, language=%s", url, model, voice, language_type)
        resp = http_requests.post(
            url,
            headers=headers,
            data=json.dumps(body).encode("utf-8"),
            timeout=60,
            **model_proxy_request_kwargs(config.get("proxy_url", "")),
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Qwen TTS error: HTTP {resp.status_code} - {resp.text[:300]}")

        content_type = resp.headers.get("Content-Type", "").lower()
        if "audio" in content_type or "octet-stream" in content_type:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return output_path

        try:
            resp_json = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"Qwen TTS 未返回音频: content-type={content_type or 'unknown'}, body={resp.text[:200]}") from exc

        output = resp_json.get("output") or {}
        audio = output.get("audio") or {}
        audio_b64 = audio.get("data") or audio.get("audio") if isinstance(audio, dict) else None
        if not audio_b64 and isinstance(audio, str):
            audio_b64 = audio
        if isinstance(audio_b64, str) and audio_b64:
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(audio_b64))
            return output_path

        message = output.get("message") or resp_json.get("message") or ""
        raise RuntimeError(f"Qwen TTS 未返回音频: {message or resp.text[:200]}")
