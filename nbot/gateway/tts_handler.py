"""Gateway TTS 处理器

负责在 Gateway 投递回复后，根据 TTS 开关状态生成语音并发送。
支持 QQ 频道（通过 OneBot API 发送语音消息）。
"""

import logging
from typing import Any

from nbot.services.tts import generate_tts_audio

_log = logging.getLogger(__name__)


class GatewayTTSHandler:
    """Gateway TTS 处理器

    检查 TTS 开关状态，生成语音并通过 QQ Bot API 发送。
    """

    def __init__(self, switch_manager, qq_bot=None):
        """
        Args:
            switch_manager: SwitchManager 实例，用于检查 TTS 开关状态
            qq_bot: QQ Bot 实例，用于发送语音消息
        """
        self._switch = switch_manager
        self._qq_bot = qq_bot

    def set_qq_bot(self, qq_bot) -> None:
        """设置 QQ Bot 实例（支持延迟注入）"""
        self._qq_bot = qq_bot

    async def handle_tts(
        self,
        *,
        channel_id: str,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """处理 TTS 语音生成和发送

        Args:
            channel_id: 频道标识（如 "qq"）
            conversation_id: 会话 ID
            content: 要转换为语音的文本内容
            metadata: 额外元数据
        """
        # 只处理 QQ 频道
        if channel_id != "qq":
            _log.debug("[TTS] 跳过非 QQ 频道 channel=%s", channel_id)
            return

        # 检查 TTS 开关状态
        if not self._is_tts_enabled(conversation_id):
            _log.debug("[TTS] TTS 未启用 conv=%s", conversation_id)
            return

        # 检查 QQ Bot 是否可用
        if not self._qq_bot:
            _log.warning("[TTS] QQ Bot 未初始化，无法发送语音")
            return

        # 生成语音
        audio_path = generate_tts_audio(content)
        if not audio_path:
            _log.warning("[TTS] 语音生成失败 conv=%s", conversation_id)
            return

        # 发送语音消息
        await self._send_voice(conversation_id, audio_path, metadata)

    def _is_tts_enabled(self, conversation_id: str) -> bool:
        """检查 TTS 是否启用"""
        try:
            return self._switch.get_switch_state('tts', conversation_id=conversation_id)
        except Exception:
            return False

    async def _send_voice(
        self,
        conversation_id: str,
        audio_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """发送语音消息到 QQ

        Args:
            conversation_id: 会话 ID（格式：qq:group:{group_id} 或 qq:private:{user_id}）
            audio_path: 音频文件路径
            metadata: 额外元数据
        """
        import os as _os

        try:
            from ncatbot.core.element import MessageChain, Record

            # 解析 conversation_id 获取目标
            parts = conversation_id.split(":")
            if len(parts) < 3:
                _log.warning("[TTS] 无效的 conversation_id: %s", conversation_id)
                return

            msg_type = parts[1]  # group 或 private
            target_id = parts[2]  # group_id 或 user_id

            # 确保使用绝对路径（OneBot 客户端需要绝对路径才能读取文件）
            abs_audio_path = _os.path.abspath(audio_path)
            if not _os.path.exists(abs_audio_path):
                _log.error("[TTS] 音频文件不存在 path=%s", abs_audio_path)
                return

            file_size = _os.path.getsize(abs_audio_path)
            _log.info("[TTS] 准备发送语音 path=%s size=%d", abs_audio_path, file_size)

            # 构建语音消息
            rtf = MessageChain([Record(abs_audio_path)])

            # 发送语音
            if msg_type == "group":
                await self._qq_bot.api.post_group_msg(group_id=target_id, rtf=rtf)
                _log.info("[TTS] 语音已发送到群 %s", target_id)
            elif msg_type == "private":
                await self._qq_bot.api.post_private_msg(user_id=target_id, rtf=rtf)
                _log.info("[TTS] 语音已发送到用户 %s", target_id)
            else:
                _log.warning("[TTS] 不支持的消息类型: %s", msg_type)

        except Exception as e:
            _log.error("[TTS] 发送语音失败 conv=%s error=%s", conversation_id, str(e))


def create_tts_handler(switch_manager, qq_bot=None) -> GatewayTTSHandler:
    """工厂函数：创建 TTS 处理器实例"""
    return GatewayTTSHandler(switch_manager, qq_bot)
