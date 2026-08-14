"""STT Adapter 基类"""
import logging
from abc import ABC, abstractmethod

_log = logging.getLogger(__name__)


class STTAdapter(ABC):
    """STT 适配器基类，定义统一的语音识别接口"""

    @abstractmethod
    def transcribe(self, audio_file_path: str, config: dict, language: str = None) -> str:
        """
        将音频文件转换为文字

        Args:
            audio_file_path: 音频文件路径
            config: 统一 STT 配置 dict
            language: 语言代码 (zh, en 等)，None则使用配置中的语言

        Returns:
            识别出的文字
        """

    def get_supported_params(self) -> list:
        """返回该适配器支持的额外参数列表"""
        return []

    @staticmethod
    def _parse_custom_headers(headers_str: str) -> dict:
        """解析自定义请求头 JSON 字符串"""
        import json
        if not headers_str:
            return {}
        try:
            return json.loads(headers_str)
        except json.JSONDecodeError:
            _log.warning("Failed to parse custom STT headers: %s", headers_str)
            return {}

    @staticmethod
    def _guess_media_type(filename: str) -> str:
        """根据文件扩展名推断音频 MIME 类型。"""
        import os
        ext = os.path.splitext(filename or "")[1].lower()
        return {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".webm": "audio/webm",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".aac": "audio/aac",
            ".flac": "audio/flac",
            ".pcm": "audio/pcm",
        }.get(ext, "audio/mpeg")
