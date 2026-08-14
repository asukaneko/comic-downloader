"""通义千问 Qwen ASR (STT) 适配器"""
import base64
import json
import logging
import os

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.stt_adapters.base import STTAdapter

_log = logging.getLogger(__name__)


def _resolve_qwen_chat_url(base_url: str, custom_url: str = "") -> str:
    """解析 DashScope 兼容模式 chat/completions 端点地址。"""
    if custom_url:
        return custom_url

    base = (base_url or "").strip().rstrip("/")
    default_url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    if base.endswith("/chat/completions"):
        return base
    if base:
        return f"{base}/chat/completions"
    return default_url


class QwenSTTAdapter(STTAdapter):
    """通义千问 Qwen ASR 适配器

    API: POST /compatible-mode/v1/chat/completions
    认证: Authorization: Bearer <key>
    模型: qwen3-asr-flash
    请求: messages 含 input_audio（base64 data URL）
    响应: choices[0].message.content
    """

    def get_supported_params(self) -> list:
        return ["model", "language"]

    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("Qwen ASR 需要 API Key，请在模型配置中设置 api_key")

        model = config.get("stt_model") or config.get("model") or "qwen3-asr-flash"
        lang = language or config.get("stt_language") or config.get("language") or ""

        url = _resolve_qwen_chat_url(
            config.get("base_url", ""), config.get("stt_url", "")
        )

        with open(audio_file_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
        filename = os.path.basename(audio_file_path)
        mime_type = self._guess_media_type(filename)
        audio_format = os.path.splitext(filename)[1].lstrip(".").lower() or "wav"

        body = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": f"data:{mime_type};base64,{audio_b64}",
                                "format": audio_format,
                            },
                        }
                    ],
                }
            ],
            "stream": False,
        }
        if lang and lang != "auto":
            body["language"] = lang

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        extra = self._parse_custom_headers(config.get("stt_headers", ""))
        if extra:
            headers.update(extra)

        _log.info("Qwen ASR: url=%s, model=%s, lang=%s, size=%d", url, model, lang, os.path.getsize(audio_file_path))
        resp = http_requests.post(
            url,
            headers=headers,
            data=json.dumps(body).encode("utf-8"),
            timeout=60,
            **model_proxy_request_kwargs(config.get("proxy_url", "")),
        )

        if resp.status_code != 200:
            raise RuntimeError(f"Qwen ASR error: HTTP {resp.status_code} - {resp.text[:300]}")

        try:
            resp_json = resp.json()
        except ValueError:
            return resp.text.strip()

        choices = resp_json.get("choices") or []
        if choices:
            message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
            content = message.get("content", "")
            if content:
                return str(content).strip()
        return resp.text.strip()
