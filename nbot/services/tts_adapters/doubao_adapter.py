"""豆包（火山引擎）TTS V3 适配器"""
import base64
import json
import logging
import uuid

import requests as http_requests

from nbot.services.tts_adapters.base import TTSAdapter

_log = logging.getLogger(__name__)

DOUBAO_VOICES = [
    {"id": "zh_female_shuangkuaisisi_moon_bigtts", "name": "爽快思思", "description": "中文女声 - 甜美活泼"},
    {"id": "zh_male_bvlazysheep", "name": "懒羊羊", "description": "中文男声 - 慵懒磁性"},
    {"id": "zh_male_ahu_conversation_wvae_bigtts", "name": "阿虎", "description": "中文男声 - 对话风格"},
    {"id": "zh_female_vv_uranus_bigtts", "name": "VV", "description": "中文女声 - 支持方言"},
    {"id": "zh_female_cancan_mars_bigtts", "name": "灿灿", "description": "中文女声 - 阳光活力"},
    {"id": "zh_male_chongchong_mars_bigtts", "name": "冲冲", "description": "中文男声 - 活力少年"},
    {"id": "zh_female_dandan_mars_bigtts", "name": "旦旦", "description": "中文女声 - 温柔知性"},
    {"id": "zh_male_dongbeihaoran_mars_bigtts", "name": "浩然", "description": "中文男声 - 东北方言"},
    {"id": "zh_female_gufeng_mars_bigtts", "name": "古风", "description": "中文女声 - 古典韵味"},
    {"id": "zh_male_haoyu_mars_bigtts", "name": "浩宇", "description": "中文男声 - 成熟稳重"},
    {"id": "zh_female_shuangkuang_mars_bigtts", "name": "爽快", "description": "中文女声 - 直爽大方"},
    {"id": "zh_male_tianyuan_mars_bigtts", "name": "田园", "description": "中文男声 - 温暖治愈"},
    {"id": "zh_female_wanwan_mars_bigtts", "name": "婉婉", "description": "中文女声 - 温柔甜美"},
    {"id": "zh_female_xinrui_mars_bigtts", "name": "心蕊", "description": "中文女声 - 知性优雅"},
    {"id": "zh_male_yunxi_mars_bigtts", "name": "云希", "description": "中文男声 - 清新少年"},
    {"id": "zh_female_yunxia_mars_bigtts", "name": "云霞", "description": "中文女声 - 温暖亲切"},
]

# HTTP Chunked endpoint (recommended, simplest)
_DOUBAO_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


class DoubaoTTSAdapter(TTSAdapter):
    """豆包（火山引擎）TTS V3 适配器

    API: POST https://openspeech.bytedance.com/api/v3/tts/unidirectional
    认证: X-Api-Key 头（新版控制台）
    响应: chunked JSON，每个 chunk 包含 base64 音频数据
    """

    def get_supported_params(self) -> list:
        return ["model", "voice", "text", "format", "speed", "pitch", "volume"]

    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        api_key = config.get("api_key", "")
        if not api_key:
            raise RuntimeError("豆包 TTS 需要 API Key，请在模型配置中设置 api_key")

        voice = (config.get("tts_voice") or "zh_female_shuangkuaisisi_moon_bigtts").strip()
        fmt = config.get("tts_format") or "mp3"
        speed = config.get("tts_speed", 0)
        volume = config.get("tts_volume", 0)
        resource_id = config.get("tts_resource_id") or "seed-tts-2.0"

        # Build request body
        body = {
            "user": {"uid": "neko_bot"},
            "req_params": {
                "text": text,
                "speaker": voice,
                "audio_params": {
                    "format": fmt,
                    "sample_rate": 24000,
                    "speech_rate": int(speed) if speed else 0,
                    "loudness_rate": int(volume) if volume else 0,
                },
                "additions": {
                    "disable_markdown_filter": True,
                    "disable_emoji_filter": True,
                    "explicit_language": "zh-cn",
                },
            },
        }

        headers = {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "Content-Type": "application/json",
        }

        url = config.get("tts_url") or _DOUBAO_TTS_URL

        _log.info("Doubao TTS: voice=%s, resource=%s", voice, resource_id)
        resp = http_requests.post(
            url,
            headers=headers,
            data=json.dumps(body).encode("utf-8"),
            timeout=60,
            stream=True,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"豆包 TTS error: HTTP {resp.status_code} - {resp.text[:300]}")

        # Collect base64 audio chunks from chunked JSON response
        audio_chunks = []
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            code = chunk.get("code", -1)
            data = chunk.get("data")

            # code=0 means audio chunk with data
            if code == 0 and data:
                audio_chunks.append(base64.b64decode(data))
            # code=20000000 means session finished
            elif code == 20000000:
                break
            # Non-zero error code (not finish signal)
            elif code != 0 and code != 20000000:
                msg = chunk.get("message", "")
                raise RuntimeError(f"豆包 TTS error: code={code}, message={msg}")

        if not audio_chunks:
            raise RuntimeError("豆包 TTS 未返回音频数据")

        with open(output_path, "wb") as f:
            for chunk in audio_chunks:
                f.write(chunk)

        return output_path
