"""群聊 @mention 跨角色对话处理器。

当一轮对话中所有角色发言完毕后，解析回复中的 @角色名，
触发被 @ 角色的额外对话。对话同步队列执行，每条完成后加入历史再处理下一条。
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

_log = logging.getLogger(__name__)

DEFAULT_MAX_MENTIONS = 5


def collect_mentions_from_round(
    round_responses: List[Dict[str, Any]],
    character_ids: List[str],
    character_profiles: Dict[str, Dict[str, Any]],
) -> List[str]:
    """从一轮回复中收集所有被 @ 的角色 ID。

    Args:
        round_responses: 本轮回复列表，每条含 {role, content, sender}
        character_ids: 群聊中所有有效角色 ID
        character_profiles: 角色档案字典 {id: profile_dict}

    Returns:
        有序去重的被 @ 角色 ID 列表，排除已发言的角色
    """
    from nbot.group.scheduler import SpeakerScheduler

    # 构建 sender_name -> character_id 的映射（大小写不敏感）
    name_to_id: dict[str, str] = {}
    for cid in character_ids:
        name_to_id[cid.lower()] = cid
        profile = character_profiles.get(cid, {})
        name = str(profile.get("name", "")).strip()
        if name:
            name_to_id[name.lower()] = cid

    # 第一轮：收集所有已发言角色
    already_spoken: set[str] = set()
    for msg in round_responses:
        sender = str(msg.get("sender", "")).strip()
        if sender:
            sender_cid = name_to_id.get(sender.lower(), sender)
            already_spoken.add(sender_cid)

    # 第二轮：解析 @mention，排除已发言角色
    mentions_ordered: List[str] = []
    seen: set[str] = set()

    for msg in round_responses:
        content = str(msg.get("content", "")).strip()
        if not content:
            continue

        parsed = SpeakerScheduler.parse_mentions(content, character_ids, character_profiles)
        for cid in parsed:
            if cid not in seen and cid not in already_spoken:
                seen.add(cid)
                mentions_ordered.append(cid)

    return mentions_ordered


def process_cross_talk(
    mentions: List[str],
    max_mentions: int,
    *,
    pipeline: Any,
    callbacks: Any,
    group_context: Dict[str, Any],
    base_metadata: Dict[str, Any],
    chat_request: Any,
    adapter: Any,
    stop_event: Any = None,
    tools: Any = None,
    max_context_chars: int = 100000,
    hook_runtime: Any = None,
    build_cross_talk_context: Optional[Callable[[str], Any]] = None,
    send_cross_talk_message: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> List[Dict[str, Any]]:
    """顺序处理 @mention 跨角色对话。

    为每个被 @ 的角色（最多 max_mentions 个）：
    1. 构建 PipelineContext，设置该角色为发言者
    2. 调用 pipeline.process() 获取回复
    3. 通过回调发送消息并保存历史
    4. 继续处理下一个

    被 @ 角色的 metadata 中设置 cross_talk_triggered = True，
    防止递归触发进一步的 @mention。

    Args:
        mentions: 被 @ 的角色 ID 列表（有序）
        max_mentions: 最多处理的 @mention 数量
        pipeline: AIPipeline 实例
        callbacks: PipelineCallbacks 实例
        group_context: 群聊上下文字典
        base_metadata: 原始轮次的 metadata 基础副本
        chat_request: 原始 ChatRequest
        adapter: 频道适配器
        stop_event: 可选的停止事件
        tools: 可选的工具列表
        max_context_chars: 上下文字符预算
        hook_runtime: 可选的 hook 运行时
        build_cross_talk_context: 可选回调，构建跨角色对话的上下文对象
            签名: (speaker_id: str) -> PipelineContext 或类似对象
        send_cross_talk_message: 可选回调，发送跨角色对话消息
            签名: (message_dict: {role, content, sender}) -> None

    Returns:
        跨角色对话产生的助手消息列表
    """
    from nbot.core.ai_pipeline import PipelineContext

    results: List[Dict[str, Any]] = []
    to_process = mentions[:max_mentions]

    if not to_process:
        return results

    _log.info("cross-talk: processing %d mentions: %s", len(to_process), to_process)

    profiles = group_context.get("character_profiles", {})
    group = group_context.get("group")

    for i, speaker_id in enumerate(to_process):
        _log.info("cross-talk [%d/%d]: triggering %s", i + 1, len(to_process), speaker_id)

        # 构建上下文
        if build_cross_talk_context:
            ctx = build_cross_talk_context(speaker_id)
        else:
            ctx = PipelineContext(
                chat_request=chat_request,
                adapter=adapter,
                stop_event=stop_event,
                metadata=dict(base_metadata),
            )
            ctx.metadata["group_speaker"] = speaker_id
            ctx.metadata["group_speaker_name"] = profiles.get(speaker_id, {}).get("name", speaker_id)
            if group:
                ctx.metadata["group_id"] = group.group_id

        # 标记为跨角色对话，防止递归
        if hasattr(ctx, "metadata"):
            ctx.metadata["cross_talk_triggered"] = True

        try:
            result = pipeline.process(
                ctx, callbacks,
                tools=tools,
                max_context_chars=max_context_chars,
                hook_runtime=hook_runtime,
                group_context=group_context,
            )

            if result and result.final_content:
                speaker_name = ctx.metadata.get("group_speaker_name", speaker_id) if hasattr(ctx, "metadata") else speaker_id
                assistant_msg = result.assistant_message or {
                    "role": "assistant",
                    "content": result.final_content,
                    "sender": speaker_name,
                }

                # 确保 sender 字段存在
                if "sender" not in assistant_msg:
                    assistant_msg["sender"] = speaker_name

                results.append(assistant_msg)

                # 通过回调发送消息（用于 QQ 等 send_response 为空操作的频道）
                if send_cross_talk_message:
                    try:
                        send_cross_talk_message(assistant_msg)
                    except Exception as send_err:
                        _log.error("cross-talk: send message failed for %s: %s", speaker_id, send_err)

        except Exception as e:
            _log.error("cross-talk: speaker %s failed: %s", speaker_id, e)
            continue

    _log.info("cross-talk: completed %d/%d responses", len(results), len(to_process))
    return results
