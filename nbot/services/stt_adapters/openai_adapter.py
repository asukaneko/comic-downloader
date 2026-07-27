"""OpenAI 兼容 STT 适配器"""
import logging
import os

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.stt_adapters.base import STTAdapter

_log = logging.getLogger(__name__)


def _resolve_transcriptions_url(base_url: str, custom_url: str = "") -> str:
    """Resolve an OpenAI-compatible transcriptions endpoint."""
    if custom_url:
        return custom_url

    url_base = (base_url or "https://api.openai.com/v1").rstrip("/")
    if url_base.endswith("/audio/transcriptions"):
        return url_base
    if url_base.endswith("/v1"):
        return f"{url_base}/audio/transcriptions"
    return f"{url_base}/v1/audio/transcriptions"


class OpenAISTTAdapter(STTAdapter):
    """OpenAI 兼容 STT API 适配器

    支持 OpenAI Whisper、SiliconFlow、以及所有兼容 OpenAI /audio/transcriptions API 的提供商。
    """

    def get_supported_params(self) -> list:
        return ["model", "language", "response_format"]

    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("OpenAI STT 需要 API Key，请在模型配置中设置 api_key")

        base_url = (config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        custom_url = config.get("stt_url", "")
        custom_headers_str = config.get("stt_headers", "")

        model = config.get("stt_model") or config.get("model") or "whisper-1"
        lang = language or config.get("stt_language") or config.get("language") or "zh"

        url = _resolve_transcriptions_url(base_url, custom_url)

        headers = {"Authorization": f"Bearer {api_key}"}
        extra = self._parse_custom_headers(custom_headers_str)
        if extra:
            headers.update(extra)

        data = {
            "model": model,
            "language": lang,
            "response_format": "text",
        }

        _log.info("OpenAI STT: url=%s, model=%s, lang=%s", url, model, lang)
        with open(audio_file_path, "rb") as audio_file:
            files = {
                "file": (os.path.basename(audio_file_path), audio_file, "audio/mpeg"),
            }
            resp = http_requests.post(
                url,
                headers=headers,
                data=data,
                files=files,
                timeout=60,
                **model_proxy_request_kwargs(config.get("proxy_url", "")),
            )

        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI STT error: HTTP {resp.status_code} - {resp.text[:300]}")

        return resp.text.strip()
