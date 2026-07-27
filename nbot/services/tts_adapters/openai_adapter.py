"""OpenAI 兼容 TTS 适配器"""
import logging

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.tts_adapters.base import TTSAdapter

_log = logging.getLogger(__name__)

_OPENAI_BODY_TEMPLATE = (
    '{"model":"{{model}}","voice":"{{voice}}","input":"{{text}}",'
    '"response_format":"{{response_format}}","speed":{{speed}}}'
)


def _resolve_speech_url(base_url: str, custom_url: str = "") -> str:
    """Resolve an OpenAI-compatible speech endpoint."""
    if custom_url:
        return custom_url

    url_base = (base_url or "https://api.openai.com/v1").rstrip("/")
    if url_base.endswith("/audio/speech"):
        return url_base
    if url_base.endswith("/v1"):
        return f"{url_base}/audio/speech"
    return f"{url_base}/v1/audio/speech"


def _is_audio_response(content_type: str) -> bool:
    lowered = (content_type or "").lower()
    return "audio" in lowered or "octet-stream" in lowered


def _write_audio_response(resp, output_path: str) -> None:
    content_type = resp.headers.get("Content-Type", "")
    if not _is_audio_response(content_type):
        raise RuntimeError(
            f"TTS API did not return audio: content-type={content_type or 'unknown'}, "
            f"body={resp.text[:200]}"
        )
    with open(output_path, "wb") as f:
        f.write(resp.content)


class OpenAITTSAdapter(TTSAdapter):
    """OpenAI 兼容 TTS API 适配器

    支持 OpenAI、SiliconFlow、以及所有兼容 OpenAI TTS API 的提供商。
    """

    def get_default_body_template(self) -> str:
        return _OPENAI_BODY_TEMPLATE

    def get_supported_params(self) -> list:
        return ["model", "voice", "text", "speed", "pitch", "volume", "response_format"]

    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        api_key = config.get("api_key", "")
        base_url = (config.get("base_url") or "https://api.openai.com/v1").rstrip("/")
        custom_url = config.get("tts_url", "")
        body_template = config.get("tts_body_template", "")
        custom_headers_str = config.get("tts_headers", "")

        model = config.get("tts_model") or "gpt-4o-mini-tts"
        voice = (config.get("tts_voice") or "alloy").strip()
        speed = config.get("tts_speed", 1.0)
        pitch = config.get("tts_pitch", 1.0)
        volume = config.get("tts_volume", 1.0)
        fmt = config.get("tts_format") or "mp3"

        variables = {
            "model": model, "voice": voice, "text": text,
            "speed": speed, "pitch": pitch, "volume": volume,
            "response_format": fmt,
        }

        if body_template:
            rendered_body = self._render_body(body_template, variables)
        else:
            import json
            body = {
                "model": model, "voice": voice, "input": text,
                "response_format": fmt, "speed": speed,
            }
            if pitch != 1.0:
                body["pitch"] = pitch
            if volume != 1.0:
                body["volume"] = volume
            rendered_body = json.dumps(body)

        url = _resolve_speech_url(base_url, custom_url)

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        extra = self._parse_custom_headers(custom_headers_str)
        if extra:
            headers.update(extra)

        _log.info("TTS synthesize: url=%s, model=%s, voice=%s", url, model, voice)
        proxy_kwargs = model_proxy_request_kwargs(config.get("proxy_url", ""))
        resp = http_requests.post(
            url,
            headers=headers,
            data=rendered_body.encode("utf-8"),
            timeout=60,
            **proxy_kwargs,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"TTS API error: HTTP {resp.status_code} - {resp.text[:300]}")

        content_type = resp.headers.get("Content-Type", "")
        if _is_audio_response(content_type):
            _write_audio_response(resp, output_path)
        else:
            try:
                resp_json = resp.json()
                audio_url = resp_json.get("audio_url") or resp_json.get("url")
                if audio_url:
                    audio_resp = http_requests.get(
                        audio_url, timeout=60, **proxy_kwargs
                    )
                    _write_audio_response(audio_resp, output_path)
                else:
                    raise RuntimeError(
                        f"TTS API did not return audio: content-type={content_type or 'unknown'}, "
                        f"body={resp.text[:200]}"
                    )
            except ValueError as exc:
                raise RuntimeError(
                    f"TTS API did not return audio: content-type={content_type or 'unknown'}, "
                    f"body={resp.text[:200]}"
                ) from exc

        return output_path
