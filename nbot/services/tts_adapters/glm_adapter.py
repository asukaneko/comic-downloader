"""智谱 GLM-TTS 适配器"""
import json
import logging

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.tts_adapters.base import TTSAdapter

_log = logging.getLogger(__name__)

GLM_VOICES = [
    {"id": "tongtong", "name": "彤彤", "description": "中文女声 - 温柔甜美"},
    {"id": "xiaoyuan", "name": "小元", "description": "中文女声 - 青春活力"},
    {"id": "hanhan", "name": "涵涵", "description": "中文女声 - 甜美亲切"},
    {"id": "zhiyu", "name": "知鱼", "description": "中文女声 - 知性大方"},
    {"id": "xiaobing", "name": "晓兵", "description": "中文男声 - 沉稳磁性"},
    {"id": "jiemo", "name": "介默", "description": "中文男声 - 温柔治愈"},
]


def _resolve_glm_speech_url(base_url: str, custom_url: str = "") -> str:
    """解析 GLM /audio/speech 端点地址。"""
    if custom_url:
        return custom_url

    base = (base_url or "").strip().rstrip("/")
    default_url = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
    if base.endswith("/audio/speech"):
        return base
    if base:
        return f"{base}/audio/speech"
    return default_url


class GlmTTSAdapter(TTSAdapter):
    """智谱 GLM-TTS 适配器

    API: POST /api/paas/v4/audio/speech
    认证: Authorization: Bearer <key>
    响应: 音频二进制（mp3/wav）
    """

    def get_supported_params(self) -> list:
        return ["model", "voice", "text", "format", "speed", "volume"]

    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("GLM-TTS 需要 API Key，请在模型配置中设置 api_key")

        model = config.get("tts_model") or config.get("model") or "glm-tts"
        voice = (config.get("tts_voice") or "tongtong").strip()
        if not voice or voice == "default":
            voice = "tongtong"
        fmt = config.get("tts_format") or "wav"
        speed = float(config.get("tts_speed", 1.0))
        volume = float(config.get("tts_volume", 1.0))

        url = _resolve_glm_speech_url(config.get("base_url", ""), config.get("tts_url", ""))

        body = {
            "model": model,
            "input": text,
            "voice": voice,
            "response_format": fmt,
            "speed": speed,
            "volume": volume,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        extra = self._parse_custom_headers(config.get("tts_headers", ""))
        if extra:
            headers.update(extra)

        _log.info("GLM TTS: url=%s, model=%s, voice=%s", url, model, voice)
        resp = http_requests.post(
            url,
            headers=headers,
            data=json.dumps(body).encode("utf-8"),
            timeout=60,
            **model_proxy_request_kwargs(config.get("proxy_url", "")),
        )

        if resp.status_code != 200:
            raise RuntimeError(f"GLM-TTS error: HTTP {resp.status_code} - {resp.text[:300]}")

        content_type = resp.headers.get("Content-Type", "").lower()
        if "audio" in content_type or "octet-stream" in content_type:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return output_path

        try:
            resp_json = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"GLM-TTS 未返回音频: content-type={content_type or 'unknown'}, body={resp.text[:200]}") from exc

        audio_b64 = (
            resp_json.get("audio")
            or (resp_json.get("data") or {}).get("audio")
            or (resp_json.get("output") or {}).get("audio")
        )
        if isinstance(audio_b64, str) and audio_b64:
            import base64
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(audio_b64))
            return output_path

        raise RuntimeError(f"GLM-TTS 未返回音频: {resp.text[:200]}")
