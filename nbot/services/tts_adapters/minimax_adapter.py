"""MiniMax TTS 适配器"""
import base64
import json
import logging

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.tts_adapters.base import TTSAdapter

_log = logging.getLogger(__name__)

MINIMAX_VOICES = [
    {"id": "male-qn-qingse", "name": "青涩 (男)", "description": "中文男声 - 青涩少年"},
    {"id": "male-qn-jingying", "name": "精英 (男)", "description": "中文男声 - 精英干练"},
    {"id": "female-shaonv", "name": "少女 (女)", "description": "中文女声 - 少女感"},
    {"id": "female-chengshu", "name": "成熟 (女)", "description": "中文女声 - 成熟温柔"},
    {"id": "female-tianmei", "name": "甜美 (女)", "description": "中文女声 - 甜美可爱"},
    {"id": "audiobook_male_1", "name": "播音男", "description": "中文男声 - 播音朗读"},
    {"id": "audiobook_male_2", "name": "书卷男", "description": "中文男声 - 书卷气"},
    {"id": "audiobook_female_1", "name": "播音女", "description": "中文女声 - 播音朗读"},
    {"id": "audiobook_female_2", "name": "书卷女", "description": "中文女声 - 书卷气"},
]


def _resolve_t2a_url(base_url: str, custom_url: str = "") -> str:
    """解析 MiniMax /t2a_v2 端点地址。"""
    if custom_url:
        return custom_url

    base = (base_url or "").strip().rstrip("/")
    default_url = "https://api.minimaxi.com/v1/t2a_v2"
    if base.endswith("/t2a_v2"):
        return base
    if base:
        return f"{base}/t2a_v2"
    return default_url


class MiniMaxTTSAdapter(TTSAdapter):
    """MiniMax TTS 适配器

    API: POST /v1/t2a_v2
    认证: Authorization: Bearer <key>
    模型: speech-2.8-hd
    响应: JSON {data: {audio: <base64>}}
    """

    def get_supported_params(self) -> list:
        return ["model", "voice", "text", "format", "speed", "pitch", "volume"]

    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("MiniMax TTS 需要 API Key，请在模型配置中设置 api_key")

        model = config.get("tts_model") or config.get("model") or "speech-2.8-hd"
        voice = (config.get("tts_voice") or "male-qn-qingse").strip()
        if not voice or voice == "default":
            voice = "male-qn-qingse"
        fmt = config.get("tts_format") or "mp3"
        speed = float(config.get("tts_speed", 1.0))
        pitch = float(config.get("tts_pitch", 1.0))
        volume = float(config.get("tts_volume", 1.0))

        url = _resolve_t2a_url(config.get("base_url", ""), config.get("tts_url", ""))

        body = {
            "model": model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice,
                "speed": speed,
                "vol": volume,
                "pitch": pitch,
            },
            "audio_setting": {
                "audio_sample_rate": 32000,
                "bitrate": 128000,
                "format": fmt,
                "channel": 1,
            },
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        extra = self._parse_custom_headers(config.get("tts_headers", ""))
        if extra:
            headers.update(extra)

        _log.info("MiniMax TTS: url=%s, model=%s, voice=%s", url, model, voice)
        resp = http_requests.post(
            url,
            headers=headers,
            data=json.dumps(body).encode("utf-8"),
            timeout=60,
            **model_proxy_request_kwargs(config.get("proxy_url", "")),
        )

        if resp.status_code != 200:
            raise RuntimeError(f"MiniMax TTS error: HTTP {resp.status_code} - {resp.text[:300]}")

        content_type = resp.headers.get("Content-Type", "").lower()
        if "audio" in content_type or "octet-stream" in content_type:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return output_path

        try:
            resp_json = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"MiniMax TTS 未返回音频: content-type={content_type or 'unknown'}, body={resp.text[:200]}") from exc

        data = resp_json.get("data") or {}
        audio_b64 = data.get("audio") or data.get("audio_base64")
        if isinstance(audio_b64, str) and audio_b64:
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(audio_b64))
            return output_path

        extra_info = data.get("extra_info") or {}
        audio_url = extra_info.get("audio_url")
        if audio_url:
            audio_resp = http_requests.get(
                audio_url,
                timeout=60,
                **model_proxy_request_kwargs(config.get("proxy_url", "")),
            )
            with open(output_path, "wb") as f:
                f.write(audio_resp.content)
            return output_path

        base_resp = resp_json.get("base_resp") or {}
        status_code = base_resp.get("status_code", -1)
        status_msg = base_resp.get("status_msg", "")
        raise RuntimeError(
            f"MiniMax TTS 未返回音频: status_code={status_code}, status_msg={status_msg}, body={resp.text[:200]}"
        )
