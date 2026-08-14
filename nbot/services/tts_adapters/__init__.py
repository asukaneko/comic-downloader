"""TTS 适配器注册表"""
from nbot.services.tts_adapters.doubao_adapter import DoubaoTTSAdapter
from nbot.services.tts_adapters.gemini_adapter import GeminiTTSAdapter
from nbot.services.tts_adapters.glm_adapter import GlmTTSAdapter
from nbot.services.tts_adapters.minimax_adapter import MiniMaxTTSAdapter
from nbot.services.tts_adapters.openai_adapter import OpenAITTSAdapter
from nbot.services.tts_adapters.qwen_adapter import QwenTTSAdapter
from nbot.services.tts_adapters.xiaomi_adapter import XiaomiTTSAdapter

_openai = OpenAITTSAdapter()
_xiaomi = XiaomiTTSAdapter()
_doubao = DoubaoTTSAdapter()
_gemini = GeminiTTSAdapter()
_glm = GlmTTSAdapter()
_minimax = MiniMaxTTSAdapter()
_qwen = QwenTTSAdapter()

_ADAPTERS = {
    "openai": _openai,
    "openai_compatible": _openai,
    "xiaomi": _xiaomi,
    "doubao": _doubao,
    "volcengine": _doubao,
    "gemini": _gemini,
    "google": _gemini,
    "google_gemini": _gemini,
    "glm": _glm,
    "zhipu": _glm,
    "bigmodel": _glm,
    "minimax": _minimax,
    "qwen": _qwen,
    "dashscope": _qwen,
    "tongyi": _qwen,
}

_default_adapter = _openai


def get_adapter(provider_type: str = ""):
    """根据 provider_type 获取对应的 TTS 适配器实例"""
    return _ADAPTERS.get(provider_type, _default_adapter)


def get_all_adapters() -> dict:
    """返回所有可用适配器信息"""
    return {
        "openai": {"name": "OpenAI 兼容", "instance": _openai},
        "xiaomi": {"name": "小米 MiMo", "instance": _xiaomi},
        "doubao": {"name": "豆包（火山引擎）", "instance": _doubao},
        "gemini": {"name": "Gemini 原生 TTS", "instance": _gemini},
        "glm": {"name": "智谱 GLM-TTS", "instance": _glm},
        "minimax": {"name": "MiniMax TTS", "instance": _minimax},
        "qwen": {"name": "通义千问 TTS", "instance": _qwen},
    }
