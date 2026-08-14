"""Gemini 原生 TTS 适配器"""
import base64
import json
import logging

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.tts_adapters.base import TTSAdapter

_log = logging.getLogger(__name__)

GEMINI_VOICES = [
    {"id": "Kore", "name": "Kore", "description": "标准女声 - Standard female"},
    {"id": "Puck", "name": "Puck", "description": "标准男声 - Standard male"},
    {"id": "Charon", "name": "Charon", "description": "温暖女声 - Warm female"},
    {"id": "Aoede", "name": "Aoede", "description": "清晰女声 - Clear female"},
    {"id": "Fenrir", "name": "Fenrir", "description": "深沉男声 - Deep male"},
    {"id": "Leda", "name": "Leda", "description": "活泼女声 - Lively female"},
    {"id": "Orus", "name": "Orus", "description": "沉稳男声 - Steady male"},
    {"id": "Zephyr", "name": "Zephyr", "description": "柔和男声 - Soft male"},
]


def _resolve_generate_content_url(base_url: str, model: str, custom_url: str = "") -> str:
    """解析 Gemini generateContent 端点地址。"""
    if custom_url:
        return custom_url

    base = (base_url or "").strip().rstrip("/")
    suffix = f"/models/{model}:generateContent"
    default_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    if base.endswith(suffix):
        return base
    if base:
        return f"{base}{suffix}"
    return default_url


class GeminiTTSAdapter(TTSAdapter):
    """Gemini 原生 TTS 适配器

    API: POST /v1beta/models/<model>:generateContent
    认证: x-goog-api-key 头
    模型: gemini-2.5-flash-preview-tts
    响应: candidates[].content.parts[].inlineData.data (base64) 或裸 PCM 音频
    """

    def get_supported_params(self) -> list:
        return ["model", "voice", "language"]

    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("Gemini TTS 需要 API Key，请在模型配置中设置 api_key")

        model = config.get("tts_model") or config.get("model") or "gemini-2.5-flash-preview-tts"
        voice = (config.get("tts_voice") or "Kore").strip()
        if not voice or voice == "default":
            voice = "Kore"
        language = config.get("tts_language") or config.get("language") or ""

        url = _resolve_generate_content_url(
            config.get("base_url", ""), model, config.get("tts_url", "")
        )

        body = {
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}},
                },
            },
        }
        if language and language != "auto":
            body["generationConfig"]["speechConfig"]["languageCode"] = (
                "cmn-CN" if language == "zh" else language
            )

        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        extra = self._parse_custom_headers(config.get("tts_headers", ""))
        if extra:
            headers.update(extra)

        _log.info("Gemini TTS: url=%s, model=%s, voice=%s", url, model, voice)
        resp = http_requests.post(
            url,
            headers=headers,
            data=json.dumps(body).encode("utf-8"),
            timeout=60,
            **model_proxy_request_kwargs(config.get("proxy_url", "")),
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Gemini TTS error: HTTP {resp.status_code} - {resp.text[:300]}")

        content_type = resp.headers.get("Content-Type", "").lower()
        if "audio" in content_type or "octet-stream" in content_type:
            audio_bytes = resp.content
        else:
            audio_bytes = self._extract_inline_audio(resp)
            if not audio_bytes:
                raise RuntimeError(f"Gemini TTS 未返回音频: {resp.text[:200]}")

        with open(output_path, "wb") as f:
            f.write(self._pcm_to_wav(audio_bytes))

        return output_path

    def _extract_inline_audio(self, resp) -> bytes:
        """从 Gemini JSON 响应中提取 inlineData.data 音频。"""
        try:
            resp_json = resp.json()
        except ValueError:
            return b""
        candidates = resp_json.get("candidates") or []
        for candidate in candidates:
            parts = ((candidate.get("content") or {}).get("parts")) or []
            for part in parts:
                inline = part.get("inlineData") or part.get("inline_data") or {}
                data = inline.get("data") or inline.get("b64") or ""
                if data:
                    return base64.b64decode(data)
        return b""
