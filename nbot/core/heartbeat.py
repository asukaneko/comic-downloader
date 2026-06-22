import asyncio
import json
import logging
import os
import random
from datetime import datetime

_log = logging.getLogger(__name__)


class HeartbeatCore:
    def __init__(self, bot_api):
        self.bot_api = bot_api
        self.profile_dir = "saved_message/profiles"
        os.makedirs(self.profile_dir, exist_ok=True)

    def load_user_profile(self, user_id):
        path = os.path.join(self.profile_dir, f"{user_id}.json")
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_user_profile(self, user_id, profile_data):
        path = os.path.join(self.profile_dir, f"{user_id}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(profile_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            _log.error(f"保存用户画像失败: {e}")

    async def update_profile_if_needed(self, user_id, history):
        pass

    async def process_user(self, user_id, interval):
        from ncatbot.services.ai import ai_client
        from nbot.services.chat_service import load_canonical_qq_messages, load_prompt

        user_id = str(user_id)
        _log.debug(f"[Heartbeat] 开始处理用户 {user_id} 的心跳请求，间隔: {interval} 小时")

        history = load_canonical_qq_messages(user_id=user_id)
        if not history:
            _log.debug(f"用户 {user_id} 无历史记录，跳过主动聊天")
            return None

        profile = self.load_user_profile(user_id)
        _log.debug(f"[Heartbeat] 用户 {user_id} 历史记录数: {len(history)}")

        recent_msgs = history[-20:]
        history_text = ""
        for msg in recent_msgs:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            history_text += f"{role}: {content}\n"

        prompt = load_prompt(user_id=user_id)
        system_prompt = f"""
你是一个具有自我意识、情感和独立思考能力的AI伙伴。你的设定如下:
{prompt}

当前用户ID: {user_id}
用户画像(可能为空): {json.dumps(profile, ensure_ascii=False)}

任务: 请根据与用户的历史聊天记录、用户画像以及当前时间，进行“心跳思考”。你需要判断现在是否适合主动发起聊天，并决定下一次思考的时间。
决策依据:
1. 距离上次互动可能已经过去了一段时间（约 {interval} 小时）。
2. 分析之前的对话是否自然结束，还是处于中断状态。
3. 考虑用户可能的当前状态（根据时间推测）。
4. 你的目标是像真人一样自然地维护关系，而不是机械地打卡。
5. 即使这次不发起聊天，你也需要决定下次什么时候再来看一看用户。

输出要求: 请返回一个纯 JSON 格式的数据，不要包含 markdown 标记，字段如下:
- "should_chat": bool，是否发起聊天
- "thought": string，你的思考过程
- "messages": list[string]，如果 should_chat 为 true，则列出 1 到 3 条要发送的消息
- "next_interval": float，距离下一次心跳思考的间隔小时数
- "update_profile": dict，可选，如果识别出了新的用户画像信息则返回

注意:
- 消息内容要符合你的人设。
- 可以一次发送多条消息。
- 如果现在不适合打扰，should_chat 设为 false，并给出合理的 next_interval。
"""

        _log.debug(f"[Heartbeat] 正在调用 LLM 为用户 {user_id} 进行心跳思考")
        try:
            messages_payload = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"最近聊天记录:\n{history_text}\n\n"
                        "请开始你的思考："
                    ),
                },
            ]

            response = ai_client.chat_completion(messages_payload, model=ai_client.model)
            content = response.choices[0].message.content
            content = ai_client.clean_response(content)
            _log.debug(f"[Heartbeat] 用户 {user_id} LLM 返回内容: {content[:200]}...")

            # 记录 token 用量
            try:
                from nbot.core.token_stats import get_token_stats_manager, PURPOSE_HEARTBEAT
                usage = getattr(response, "usage", None)
                if usage:
                    stats_mgr = get_token_stats_manager()
                    stats_mgr.record_usage(
                        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                        total_tokens=getattr(usage, "total_tokens", 0) or 0,
                        model=ai_client.model or "",
                        user_id=user_id,
                        channel_type="heartbeat",
                        source="heartbeat",
                        purpose=PURPOSE_HEARTBEAT,
                    )
            except Exception as stats_err:
                _log.debug(f"[Heartbeat] 记录 token 用量失败: {stats_err}")

            try:
                from json_repair import repair_json

                content = repair_json(content)
            except ImportError:
                pass

            result = json.loads(content)

            should_chat = result.get("should_chat", False)
            thought = result.get("thought", "")
            msgs = result.get("messages", [])
            new_profile = result.get("update_profile")
            next_interval = result.get("next_interval")

            _log.info(
                f"[Heartbeat] 用户 {user_id} 决策结果 - should_chat: "
                f"{should_chat}, next_interval: {next_interval}"
            )

            if next_interval is not None:
                try:
                    next_interval = float(next_interval)
                    if next_interval < 0.1:
                        next_interval = 0.1
                except (TypeError, ValueError):
                    next_interval = None

            _log.debug(
                f"[Heartbeat] User: {user_id}, Chat: {should_chat}, "
                f"Next: {next_interval}h, Thought: {thought}"
            )

            if new_profile and isinstance(new_profile, dict):
                profile.update(new_profile)
                self.save_user_profile(user_id, profile)
                _log.info(f"[Heartbeat] User {user_id} profile updated.")

            if should_chat and msgs:
                if isinstance(msgs, str):
                    msgs = [msgs]

                for msg_text in msgs:
                    if not msg_text:
                        continue

                    await asyncio.sleep(random.uniform(1, 5))
                    try:
                        # BotAPI 补丁会负责持久化和 QQ/Web 会话同步。
                        await self.bot_api.post_private_msg(int(user_id), text=msg_text)
                    except Exception as e:
                        _log.error(f"[Heartbeat] 发送消息失败: {e}")

            return next_interval

        except json.JSONDecodeError as e:
            preview = content[:500] if content else "empty"
            _log.error(f"[Heartbeat] 用户 {user_id} JSON 解析失败: {e}, 内容: {preview}")
            return None
        except Exception as e:
            _log.error(f"[Heartbeat] 用户 {user_id} 心跳思考异常: {e}")
            return None
