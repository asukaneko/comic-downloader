"""STT 适配器注册表"""
from nbot.services.stt_adapters.openai_adapter import OpenAISTTAdapter
from nbot.services.stt_adapters.xiaomi_adapter import XiaomiSTTAdapter
from nbot.services.stt_adapters.local_adapter import LocalWhisperSTTAdapter

_openai = OpenAISTTAdapter()
_xiaomi = XiaomiSTTAdapter()
_local = LocalWhisperSTTAdapter()

_ADAPTERS = {
    "openai": _openai,
    "openai_compatible": _openai,
    "xiaomi": _xiaomi,
    "local": _local,
    "faster_whisper": _local,
}

_default_adapter = _openai


def get_adapter(provider_type: str = ""):
    """根据 provider_type 获取对应的 STT 适配器实例"""
    return _ADAPTERS.get(provider_type, _default_adapter)


def get_all_adapters() -> dict:
    """返回所有可用适配器信息"""
    return {
        "openai": {"name": "OpenAI 兼容", "instance": _openai},
        "xiaomi": {"name": "小米 MiMo", "instance": _xiaomi},
        "local": {"name": "本地 faster-whisper", "instance": _local},
    }
