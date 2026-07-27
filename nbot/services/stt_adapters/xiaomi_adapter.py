"""小米 MiMo STT 适配器"""
import base64
import json
import logging
import os
import subprocess
import tempfile

import requests as http_requests

from nbot.core.model_proxy import model_proxy_request_kwargs
from nbot.services.stt_adapters.base import STTAdapter

_log = logging.getLogger(__name__)

XIAOMI_STT_BASE_URL = "https://api.xiaomimimo.com/v1"

# 小米 API 支持的格式
_XIAOMI_SUPPORTED_EXTS = {".wav", ".mp3"}

# 文件扩展名 -> MIME 类型映射
_MIME_MAP = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".webm": "audio/webm",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
}


def _ensure_wav_or_mp3(audio_file_path: str) -> str:
    """确保音频文件是 wav 或 mp3 格式，如果不是则用 ffmpeg 转换为 wav。

    返回可用的文件路径。如果进行了转换，返回临时文件路径（调用方需负责清理）；
    如果原始格式已兼容，直接返回原路径。
    """
    ext = os.path.splitext(audio_file_path)[1].lower()
    if ext in _XIAOMI_SUPPORTED_EXTS:
        return audio_file_path, None

    # 需要转换
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        ffmpeg_exe = "ffmpeg"

    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)

    _log.info("Converting %s -> wav for Xiaomi STT", ext)
    try:
        subprocess.run(
            [ffmpeg_exe, "-y", "-i", audio_file_path, "-ar", "16000", "-ac", "1", tmp_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=30,
        )
        return tmp_path, tmp_path
    except Exception as e:
        # 清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise RuntimeError(f"音频格式转换失败 (webm->wav): {e}") from e


def _build_audio_data_url(audio_file_path: str) -> str:
    """读取音频文件并构建 data URL 格式的 base64 字符串"""
    ext = os.path.splitext(audio_file_path)[1].lower()
    mime_type = _MIME_MAP.get(ext, "audio/mpeg")

    with open(audio_file_path, "rb") as f:
        audio_bytes = f.read()

    b64_str = base64.b64encode(audio_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{b64_str}"


class XiaomiSTTAdapter(STTAdapter):
    """小米 MiMo STT API 适配器

    API: POST /v1/chat/completions (JSON + base64 input_audio)
    认证: api-key 头
    模型: mimo-v2.5-asr
    音频格式: mp3、wav（base64 data URL，上限 10MB）
    """

    def get_supported_params(self) -> list:
        return ["model", "language"]

    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("小米 STT 需要 API Key，请在模型配置中设置 api_key")

        base_url = (config.get("base_url") or XIAOMI_STT_BASE_URL).rstrip("/")
        custom_url = config.get("stt_url", "")

        model = config.get("stt_model") or config.get("model") or "mimo-v2.5-asr"
        lang = language or config.get("stt_language") or config.get("language") or "auto"

        url = custom_url if custom_url else f"{base_url}/chat/completions"

        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }

        # 确保音频格式为 wav/mp3（小米 API 不支持 webm）
        usable_path, tmp_path = _ensure_wav_or_mp3(audio_file_path)
        try:
            audio_data_url = _build_audio_data_url(usable_path)

            body = {
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": audio_data_url,
                                },
                            }
                        ],
                    }
                ],
                "asr_options": {
                    "language": lang,
                },
            }

            _log.info("Xiaomi STT: url=%s, model=%s, lang=%s", url, model, lang)
            resp = http_requests.post(
                url,
                headers=headers,
                json=body,
                timeout=60,
                **model_proxy_request_kwargs(config.get("proxy_url", "")),
            )

            if resp.status_code != 200:
                raise RuntimeError(f"小米 STT error: HTTP {resp.status_code} - {resp.text[:300]}")

            # Response is chat completion format: choices[0].message.content
            try:
                resp_json = resp.json()
                choices = resp_json.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    text = message.get("content", "")
                    if text:
                        return text.strip()
                return resp.text.strip()
            except Exception as e:
                _log.error("Failed to parse Xiaomi STT response: %s", e)
                return resp.text.strip()
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
