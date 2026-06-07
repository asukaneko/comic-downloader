"""TTS 适配器注册表"""
from nbot.services.tts_adapters.openai_adapter import OpenAITTSAdapter
from nbot.services.tts_adapters.xiaomi_adapter import XiaomiTTSAdapter
from nbot.services.tts_adapters.doubao_adapter import DoubaoTTSAdapter

_openai = OpenAITTSAdapter()
_xiaomi = XiaomiTTSAdapter()
_doubao = DoubaoTTSAdapter()

_ADAPTERS = {
    "openai": _openai,
    "openai_compatible": _openai,
    "xiaomi": _xiaomi,
    "doubao": _doubao,
    "volcengine": _doubao,
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
    }
