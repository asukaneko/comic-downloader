"""小米 MiMo TTS 适配器"""
import logging
import requests as http_requests

from nbot.services.tts_adapters.base import TTSAdapter

_log = logging.getLogger(__name__)

XIAOMI_VOICES = [
    {"id": "mimo_default", "name": "MiMo默认", "description": "默认音色 - 冰糖/Mia"},
    {"id": "冰糖", "name": "冰糖", "description": "中文女声 - 温柔甜美"},
    {"id": "茉莉", "name": "茉莉", "description": "中文女声 - 清新自然"},
    {"id": "苏打", "name": "苏打", "description": "中文男声 - 阳光活力"},
    {"id": "白桦", "name": "白桦", "description": "中文男声 - 沉稳磁性"},
    {"id": "Mia", "name": "Mia", "description": "英文女声"},
    {"id": "Chloe", "name": "Chloe", "description": "英文女声"},
    {"id": "Milo", "name": "Milo", "description": "英文男声"},
    {"id": "Dean", "name": "Dean", "description": "英文男声"},
]


class XiaomiTTSAdapter(TTSAdapter):
    """小米 MiMo TTS API 适配器

    API: POST /v1/chat/completions
    认证: api-key 头
    请求体: chat completions 格式，目标文本在 assistant 消息中

    支持音色复刻 (voiceclone):
      - 当 tts_ref_audio 非空时，audio.voice 设为 base64 data URL
      - 当 tts_user 非空时，在 messages 中插入 user 消息控制合成风格
    """

    def get_supported_params(self) -> list:
        return ["model", "voice", "text", "format"]

    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        api_key = config.get("api_key", "")
        base_url = (config.get("base_url") or "https://api.xiaomimimo.com/v1").rstrip("/")
        custom_url = config.get("tts_url", "")

        model = config.get("tts_model") or "mimo-v2.5-tts"
        voice = (config.get("tts_voice") or "mimo_default").strip()
        fmt = config.get("tts_format") or "mp3"
        ref_audio = (config.get("tts_ref_audio") or "").strip()
        user_instruction = (config.get("tts_user") or "").strip()

        url = custom_url if custom_url else f"{base_url}/chat/completions"

        # 音色复刻：将参考音频 base64 data URL 作为 voice 值
        voice_value = ref_audio if ref_audio else voice

        messages = []
        # user 消息用于控制合成风格（音色复刻或通用风格指令）
        if user_instruction:
            messages.append({"role": "user", "content": user_instruction})
        messages.append({"role": "assistant", "content": text})

        body = {
            "model": model,
            "messages": messages,
            "audio": {
                "format": fmt,
                "voice": voice_value,
            },
        }

        headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
        }

        _log.info("Xiaomi TTS: url=%s, model=%s, voice=%s, has_ref_audio=%s, has_user=%s",
                  url, model, voice, bool(ref_audio), bool(user_instruction))
        resp = http_requests.post(url, headers=headers, json=body, timeout=60)

        if resp.status_code != 200:
            raise RuntimeError(f"Xiaomi TTS error: HTTP {resp.status_code} - {resp.text[:300]}")

        content_type = resp.headers.get("Content-Type", "")
        if "audio" in content_type or "octet-stream" in content_type:
            with open(output_path, "wb") as f:
                f.write(resp.content)
        else:
            try:
                resp_json = resp.json()
                choices = resp_json.get("choices", [])
                if choices:
                    message = choices[0].get("message", {})
                    audio_data = message.get("audio", {})
                    if isinstance(audio_data, dict):
                        audio_url = audio_data.get("url")
                        audio_b64 = audio_data.get("data")
                        if audio_url:
                            audio_resp = http_requests.get(audio_url, timeout=60)
                            with open(output_path, "wb") as f:
                                f.write(audio_resp.content)
                        elif audio_b64:
                            import base64
                            with open(output_path, "wb") as f:
                                f.write(base64.b64decode(audio_b64))
                        else:
                            with open(output_path, "wb") as f:
                                f.write(resp.content)
                    elif isinstance(audio_data, str):
                        import base64
                        with open(output_path, "wb") as f:
                            f.write(base64.b64decode(audio_data))
                    else:
                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                else:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
            except Exception as e:
                _log.error("Failed to parse Xiaomi TTS response: %s", e)
                with open(output_path, "wb") as f:
                    f.write(resp.content)

        return output_path
