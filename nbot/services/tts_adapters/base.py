"""TTS Adapter 基类"""
import logging
from abc import ABC, abstractmethod

_log = logging.getLogger(__name__)


class TTSAdapter(ABC):
    """TTS 适配器基类，定义统一的语音合成接口"""

    @abstractmethod
    def synthesize(self, text: str, config: dict, output_path: str) -> str:
        """
        合成语音并保存到文件

        Args:
            text: 要合成的文本
            config: 统一 TTS 配置 dict
            output_path: 输出文件路径
        Returns:
            输出文件路径
        """

    def get_default_body_template(self) -> str:
        """返回该适配器的默认请求体模板"""
        return ""

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
            _log.warning("Failed to parse custom TTS headers: %s", headers_str)
            return {}

    @staticmethod
    def _pcm_to_wav(pcm: bytes, sample_rate: int = 24000, channels: int = 1) -> bytes:
        """将裸 PCM 封装为 WAV；已是 RIFF/WAV 则原样返回。"""
        if pcm[:4] == b"RIFF":
            return pcm
        import struct
        byte_rate = sample_rate * channels * 2
        block_align = channels * 2
        header = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack(
            "<IHHIIHH", 16, 1, channels, sample_rate, byte_rate, block_align, 16
        ) + b"data" + struct.pack("<I", len(pcm))
        return header + pcm

    @staticmethod
    def _render_body(template: str, variables: dict) -> str:
        """渲染请求体模板，将 {{variable}} 替换为实际值"""
        import re
        def replace_var(match):
            var_name = match.group(1).strip()
            value = variables.get(var_name, match.group(0))
            if isinstance(value, (int, float)):
                return str(value)
            return str(value)
        return re.sub(r'\{\{(\w+)\}\}', replace_var, template)
