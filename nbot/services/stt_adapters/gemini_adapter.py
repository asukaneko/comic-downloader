"""Gemini 原生 STT 适配器"""
import base64
import json
import logging
import os

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.stt_adapters.base import STTAdapter

_log = logging.getLogger(__name__)


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


class GeminiSTTAdapter(STTAdapter):
    """Gemini 原生 STT 适配器

    API: POST /v1beta/models/<model>:generateContent
    认证: x-goog-api-key 头
    模型: gemini-2.5-flash
    请求: contents.parts 含文本提示 + inlineData(base64 音频)
    响应: candidates[].content.parts[].text
    """

    def get_supported_params(self) -> list:
        return ["model", "language"]

    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("Gemini STT 需要 API Key，请在模型配置中设置 api_key")

        model = config.get("stt_model") or config.get("model") or "gemini-2.5-flash"
        lang = language or config.get("stt_language") or config.get("language") or ""

        url = _resolve_generate_content_url(
            config.get("base_url", ""), model, config.get("stt_url", "")
        )

        with open(audio_file_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        mime_type = self._guess_media_type(audio_file_path)

        language_hint = f" in {lang}" if lang and lang != "auto" else ""
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": f"请准确转录这段音频，只输出转录文本，不要解释。{language_hint}"},
                        {"inlineData": {"mimeType": mime_type, "data": audio_b64}},
                    ],
                }
            ]
        }

        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        extra = self._parse_custom_headers(config.get("stt_headers", ""))
        if extra:
            headers.update(extra)

        _log.info("Gemini STT: url=%s, model=%s, lang=%s, size=%d", url, model, lang, os.path.getsize(audio_file_path))
        resp = http_requests.post(
            url,
            headers=headers,
            data=json.dumps(body).encode("utf-8"),
            timeout=60,
            **model_proxy_request_kwargs(config.get("proxy_url", "")),
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Gemini STT error: HTTP {resp.status_code} - {resp.text[:300]}")

        try:
            resp_json = resp.json()
        except ValueError:
            return resp.text.strip()

        parts = []
        candidates = resp_json.get("candidates") or []
        for candidate in candidates:
            parts.extend(((candidate.get("content") or {}).get("parts")) or [])
        text = "".join(
            part.get("text", "") for part in parts if part.get("text")
        ).strip()
        if text:
            return text
        return resp_json.get("text") or resp.text.strip()
