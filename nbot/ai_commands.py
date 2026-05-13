import asyncio
import json
import os
import time
from datetime import datetime

from nbot.services.chat_service import (
    delete_session_workspace,
    generate_today_summary,
    get_qq_session_id,
    group_messages,
    summarize_group_text,
    user_messages,
)


def register_ai_commands(
    *,
    register_command,
    bot,
    log,
    project_root,
    admin,
    read_secure_json,
    write_secure_json,
    workspace_available,
    switch,
    running,
    write_running,
    normalize_timestamp,
    heartbeat_core,
    normalize_file_path,
    load_address,
):
    """Register AI/session commands that are shared by QQ and Web history."""

    def web_data_dir():
        return os.path.join(project_root(), "data", "web")

    def resume_bindings_path():
        return os.path.join(web_data_dir(), "qq_web_session_bindings.json")

    def load_resume_bindings():
        path = resume_bindings_path()
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            log.warning(f"Load resume bindings failed: {e}")
        return {}

    def save_resume_bindings(bindings):
        os.makedirs(web_data_dir(), exist_ok=True)
        with open(resume_bindings_path(), "w", encoding="utf-8") as f:
            json.dump(bindings, f, ensure_ascii=False, indent=2)

    def save_qq_histories():
        os.makedirs("saved_message", exist_ok=True)
        with open("saved_message/user_messages.json", "w", encoding="utf-8") as f:
            json.dump(user_messages, f, ensure_ascii=False, indent=4)
        with open("saved_message/group_messages.json", "w", encoding="utf-8") as f:
            json.dump(group_messages, f, ensure_ascii=False, indent=4)

    async def reply_current_channel(msg, is_group, text):
        if is_group:
            await msg.reply(text=text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=text)

    def load_character_options():
        characters = []
        seen = set()

        def add_character(data):
            if not isinstance(data, dict):
                return
            name = str(data.get("name") or "").strip()
            character_id = str(data.get("id") or name).strip()
            if not name and not character_id:
                return
            key = character_id or name
            if key in seen:
                return
            seen.add(key)
            item = dict(data)
            item["id"] = character_id or name
            item["name"] = name or character_id
            characters.append(item)

        base_dir = project_root()

        try:
            from nbot.character.repository import ProfileRepository

            for profile in ProfileRepository(base_dir).list_all():
                add_character(profile.to_personality_dict())
        except Exception as e:
            log.warning(f"Load character profiles failed: {e}")

        for file_path in (
            os.path.join(base_dir, "resources", "prompts", "personality.json"),
            os.path.join(base_dir, "data", "web", "custom_personality_presets.json"),
        ):
            try:
                if not os.path.exists(file_path):
                    continue
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        add_character(item)
                elif isinstance(data, dict):
                    add_character(data)
            except Exception as e:
                log.warning(f"Load character file failed: {file_path}, {e}")

        return characters

    def compile_character_prompt(character):
        if character.get("systemPrompt"):
            return str(character.get("systemPrompt") or "")
        from nbot.character.compiler import compile_personality_prompt

        return compile_personality_prompt(character)

    def resolve_character_session(msg, is_group):
        if is_group and getattr(msg, "group_id", None):
            return "group", str(msg.group_id)
        if not is_group and getattr(msg, "user_id", None):
            return "user", str(msg.user_id)

        session_id = (
            getattr(msg, "session_id", None)
            or getattr(msg, "chat_id", None)
            or getattr(msg, "conversation_id", None)
        )
        if session_id:
            return "channel", str(session_id)

        if getattr(msg, "user_id", None):
            return "user", str(msg.user_id)
        return "", ""

    def get_session_prompt(scope, target_id, msg=None):
        if scope == "channel":
            session_id = getattr(msg, "session_id", None) or target_id
            server = getattr(msg, "server", None)
            session = None
            if server and hasattr(server, "sessions"):
                session = server.sessions.get(str(session_id))
            if session:
                prompt = session.get("system_prompt") or session.get("prompt") or ""
                if prompt:
                    return str(prompt)
                for item in session.get("messages", []):
                    if item.get("role") == "system":
                        return str(item.get("content") or "")

        prefix = "group" if scope == "group" else "user" if scope == "user" else "channel"
        prompt_file = os.path.join(
            project_root(),
            "resources",
            "prompts",
            prefix,
            f"{prefix}_{target_id}.txt",
        )
        try:
            if os.path.exists(prompt_file):
                with open(prompt_file, "r", encoding="utf-8") as f:
                    return f.read()
        except Exception as e:
            log.warning(f"Load session prompt failed: {e}")
        return ""

    def get_active_character():
        personality_file = os.path.join(project_root(), "resources", "prompts", "personality.json")
        try:
            if os.path.exists(personality_file):
                with open(personality_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as e:
            log.warning(f"Load active character failed: {e}")
        return {}

    def find_session_character(characters, scope, target_id, msg=None):
        current_prompt = get_session_prompt(scope, target_id, msg).strip()
        if current_prompt:
            for character in characters:
                try:
                    if compile_character_prompt(character).strip() == current_prompt:
                        return character
                except Exception:
                    continue
        return get_active_character()

    def find_character(characters, arg):
        if not arg:
            return None
        try:
            index = int(arg)
            if 1 <= index <= len(characters):
                return characters[index - 1]
        except ValueError:
            pass

        needle = arg.casefold()
        for character in characters:
            if needle in {
                str(character.get("id") or "").casefold(),
                str(character.get("name") or "").casefold(),
            }:
                return character

        matches = [
            c for c in characters
            if needle in str(c.get("id") or "").casefold()
            or needle in str(c.get("name") or "").casefold()
        ]
        return matches[0] if len(matches) == 1 else None

    def set_current_session_character(msg, is_group, character):
        base_dir = project_root()
        prompt = compile_character_prompt(dict(character))
        scope, target_id = resolve_character_session(msg, is_group)
        if not scope or not target_id:
            raise ValueError("无法识别当前会话")

        prefix = "group" if scope == "group" else "user" if scope == "user" else "channel"
        prompt_dir = os.path.join(base_dir, "resources", "prompts", prefix)
        prompt_file = os.path.join(prompt_dir, f"{prefix}_{target_id}.txt")

        os.makedirs(prompt_dir, exist_ok=True)
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

        if scope in {"group", "user"}:
            messages = group_messages if scope == "group" else user_messages
            messages[target_id] = [{"role": "system", "content": prompt}]
            save_qq_histories()

            if scope == "group":
                delete_session_workspace(
                    group_id=target_id,
                    group_user_id=str(getattr(msg, "user_id", "")),
                )
            else:
                delete_session_workspace(user_id=target_id)
        else:
            server = getattr(msg, "server", None)
            session_id = getattr(msg, "session_id", None) or target_id
            if server and hasattr(server, "sessions"):
                from nbot.core.session_store import WebSessionStore

                session_store = WebSessionStore(
                    server.sessions,
                    save_callback=lambda: server._save_data("sessions"),
                )
                session = session_store.get_session(str(session_id))
                if session is not None:
                    system_msg = {"role": "system", "content": prompt}
                    session["system_prompt"] = prompt
                    session["character_id"] = character.get("id") or character.get("name") or ""
                    session["sender_name"] = character.get("name") or "AI"
                    session["sender_avatar"] = character.get("avatar", "")
                    session["sender_portrait"] = character.get("portrait", "")
                    session_store.replace_messages(str(session_id), [system_msg])
                    session_store.set_session(str(session_id), session)
            if workspace_available:
                try:
                    from nbot.core.workspace import workspace_manager

                    workspace_manager.delete_workspace(str(session_id))
                except Exception as e:
                    log.debug(f"Delete channel workspace skipped: {e}")

        try:
            from nbot.core.prompt import prompt_manager

            prompt_manager._prompt_cache = {}
        except Exception:
            pass

    def current_qq_session_info(msg, is_group):
        if is_group:
            group_id = str(getattr(msg, "group_id", "") or "")
            user_id = str(getattr(msg, "user_id", "") or "")
            history_key = f"{group_id}_{user_id}" if group_id and user_id else group_id
            session_id = get_qq_session_id(group_id=group_id, group_user_id=user_id)
            return {
                "store": group_messages,
                "history_key": history_key,
                "session_id": session_id,
                "user_id": None,
                "group_id": group_id,
                "group_user_id": user_id,
                "label": f"群 {group_id} / 用户 {user_id}" if user_id else f"群 {group_id}",
            }

        user_id = str(getattr(msg, "user_id", "") or "")
        return {
            "store": user_messages,
            "history_key": user_id,
            "session_id": get_qq_session_id(user_id=user_id),
            "user_id": user_id,
            "group_id": None,
            "group_user_id": None,
            "label": f"私聊 {user_id}",
        }

    def copy_chat_messages(messages):
        return [dict(message) for message in messages or [] if isinstance(message, dict)]

    def session_system_prompt(session, messages):
        prompt = str((session or {}).get("system_prompt") or "")
        if prompt:
            return prompt
        for message in messages or []:
            if isinstance(message, dict) and message.get("role") == "system":
                return str(message.get("content") or "")
        return ""

    def session_matches_character(session, active):
        active_ids = {
            str((active or {}).get("id") or "").strip().casefold(),
            str((active or {}).get("name") or "").strip().casefold(),
        }
        active_ids.discard("")
        if not active_ids:
            return True
        session_ids = {
            str((session or {}).get("character_id") or "").strip().casefold(),
            str((session or {}).get("sender_name") or "").strip().casefold(),
        }
        session_ids.discard("")
        return bool(active_ids & session_ids)

    def load_web_sessions():
        from nbot.web.sessions_db import load_sessions as load_sessions_from_db

        sessions = load_sessions_from_db(web_data_dir())
        return sessions if isinstance(sessions, dict) else {}

    def save_web_sessions(sessions):
        from nbot.web.sessions_db import save_sessions as save_sessions_to_db

        save_sessions_to_db(web_data_dir(), sessions)

    def current_character(msg, is_group):
        characters = load_character_options()
        scope, target_id = resolve_character_session(msg, is_group)
        return find_session_character(characters, scope, target_id, msg)

    def candidate_resume_sessions(msg, is_group):
        active = current_character(msg, is_group)
        sessions = load_web_sessions()
        candidates = []
        for session_id, session in sessions.items():
            if not isinstance(session, dict):
                continue
            session_type = str(session.get("type") or "web").lower()
            if session_type.startswith("qq_") or session_type == "cli":
                continue
            if session.get("archived"):
                continue
            if not session_matches_character(session, active):
                continue
            messages = session.get("messages") if isinstance(session.get("messages"), list) else []
            candidates.append((session_id, session, len(messages)))

        candidates.sort(
            key=lambda item: str(item[1].get("updated_at") or item[1].get("created_at") or ""),
            reverse=True,
        )
        return candidates

    def find_resume_session(candidates, arg):
        arg = (arg or "").strip()
        if not arg:
            return None
        try:
            index = int(arg)
            if 1 <= index <= len(candidates):
                return candidates[index - 1]
        except ValueError:
            pass

        needle = arg.casefold()
        matches = []
        for item in candidates:
            session_id, session, _ = item
            name = str(session.get("name") or "")
            if needle == str(session_id).casefold() or needle == name.casefold():
                return item
            if needle in str(session_id).casefold() or needle in name.casefold():
                matches.append(item)
        return matches[0] if len(matches) == 1 else None

    def format_resume_session_list(candidates, active):
        active_name = (active or {}).get("name") or (active or {}).get("id") or "当前角色"
        lines = [f"可载入的 Web 会话（角色：{active_name}）："]
        if not candidates:
            lines.append("没有找到匹配当前角色的 Web 会话。")
            return "\n".join(lines)
        for index, (session_id, session, message_count) in enumerate(candidates[:20], 1):
            name = session.get("name") or session_id[:8]
            updated = session.get("updated_at") or session.get("created_at") or ""
            suffix = f" - {updated[:16]}" if updated else ""
            lines.append(f"{index}. {name} [{session_id[:8]}] {message_count} 条{suffix}")
        lines.append("")
        lines.append("用法：/resume <编号|会话ID|名称>")
        return "\n".join(lines)

    def extract_history_text_item(item):
        def parts_from_segments(segments):
            parts = []
            for seg in segments or []:
                seg_type = getattr(seg, "type", None)
                data = getattr(seg, "data", None)
                if isinstance(seg, dict):
                    seg_type = seg.get("type")
                    data = seg.get("data")
                data = data or {}
                if seg_type == "text":
                    parts.append(str(data.get("text") or ""))
                elif seg_type == "image":
                    parts.append("[图片]")
                elif seg_type:
                    parts.append(f"[{seg_type}]")
            return "".join(parts).strip()

        if isinstance(item, dict):
            message = item.get("message")
            if isinstance(message, list):
                text = parts_from_segments(message)
                if text:
                    return text
            return str(item.get("raw_message") or item.get("message") or item.get("content") or "").strip()

        message = getattr(item, "message", None)
        if isinstance(message, list):
            text = parts_from_segments(message)
            if text:
                return text
        return str(
            getattr(item, "raw_message", None)
            or getattr(item, "content", None)
            or ""
        ).strip()

    async def get_group_history_items(group_id, count):
        history = await bot.api.get_group_msg_history(
            group_id,
            message_seq=0,
            count=count,
            reverse_order=True,
        )
        if isinstance(history, list):
            return history
        if isinstance(history, dict):
            data = history.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("messages"), list):
                return data["messages"]
        return []

    def history_items_to_text(items):
        lines = []
        for item in items:
            user_id = None
            nickname = ""
            if isinstance(item, dict):
                user_id = item.get("user_id")
                sender = item.get("sender")
                if isinstance(sender, dict):
                    nickname = sender.get("nickname", "") or ""
            else:
                user_id = getattr(item, "user_id", None)
                sender = getattr(item, "sender", None)
                if sender is not None:
                    try:
                        nickname = sender.nickname
                    except Exception:
                        if isinstance(sender, dict):
                            nickname = sender.get("nickname", "") or ""
            text = extract_history_text_item(item)
            uid_str = str(user_id) if user_id is not None else ""
            name_part = nickname or uid_str
            lines.append(f"{name_part}: {text}" if name_part else text)
        return "\n".join(lines)

    async def get_group_today_summary_text(group_id):
        try:
            items = await get_group_history_items(group_id, 500)
        except Exception as e:
            log.error(f"获取群聊历史失败：{e}")
            return None
        if not items:
            return "今天群里还没有记录到消息喔~"

        today = datetime.now().date()
        filtered = []
        for item in items:
            t = item.get("time") if isinstance(item, dict) else getattr(item, "time", None)
            try:
                dt = datetime.fromtimestamp(int(t)) if t is not None else None
            except Exception:
                dt = None
            if dt is not None and dt.date() == today:
                filtered.append(item)
        if not filtered:
            return "今天群里还没有记录到消息喔~"
        return summarize_group_text(history_items_to_text(filtered))

    async def auto_summary_task():
        log.info("每日自动总结定时任务已启动")
        while True:
            try:
                now = datetime.now()
                if now.hour == 23 and now.minute == 55:
                    for group_id, switches in switch.group_switches.items():
                        if switches.get("summary_auto", False):
                            try:
                                summary = await get_group_today_summary_text(int(group_id))
                                if summary and "还没有记录到消息" not in summary:
                                    await bot.api.post_group_msg(
                                        group_id=int(group_id),
                                        text=f"【每日自动总结】\n{summary}",
                                    )
                            except Exception as e:
                                log.error(f"自动总结群 {group_id} 失败: {e}")
                    await asyncio.sleep(65)
                else:
                    await asyncio.sleep(30)
            except Exception as e:
                log.error(f"每日自动总结任务发生异常: {e}")
                await asyncio.sleep(60)

    async def auto_active_chat_task():
        log.info("主动聊天定时任务已启动")
        while True:
            try:
                now = datetime.now()
                if 8 <= now.hour < 24:
                    current_time = time.time()
                    for user_id, info in list(running.items()):
                        if not info.get("active", False):
                            continue
                        interval = float(info.get("interval", 1.0))
                        last_time = normalize_timestamp(info.get("last_time", 0))
                        if last_time == 0:
                            running[user_id]["last_time"] = current_time
                            write_running()
                            continue
                        if current_time - last_time >= 60 * 60 * interval:
                            try:
                                next_interval = await heartbeat_core.process_user(int(user_id), interval)
                                if next_interval is not None:
                                    running[user_id]["interval"] = next_interval
                                running[user_id]["last_time"] = current_time
                                write_running()
                            except Exception as e:
                                log.error(f"主动聊天用户 {user_id} 发送失败: {e}")
                await asyncio.sleep(60)
            except Exception as e:
                log.error(f"主动聊天定时任务发生异常: {e}")
                await asyncio.sleep(60)

    @register_command(
        "/summary_recent",
        "/sr",
        help_text="/summary_recent [数量] 或 /sr [数量] -> 总结最近若干条群聊消息",
        category="2",
    )
    async def handle_summary_recent(msg, is_group=True):
        if not is_group:
            await bot.api.post_private_msg(msg.user_id, text="请在群聊中使用该命令喔~")
            return

        raw = getattr(msg, "raw_message", "") or ""
        prefix = "/summary_recent" if raw.startswith("/summary_recent") else "/sr"
        arg = raw[len(prefix):].strip()
        try:
            count = int(arg) if arg else 100
        except ValueError:
            await msg.reply(text="格式错误喔，请输入 /summary_recent [数量] 或 /sr [数量]")
            return
        count = max(1, min(count, 500))

        try:
            items = await get_group_history_items(msg.group_id, count)
        except Exception as e:
            await msg.reply(text=f"获取群聊历史失败喔：{e}")
            return
        if not items:
            await msg.reply(text="没有获取到群聊历史消息喔~")
            return
        await msg.reply(text=summarize_group_text(history_items_to_text(items)))

    @register_command(
        "/summary_today",
        help_text="/summary_today -> 总结今天与机器人的聊天内容",
        category="2",
    )
    async def handle_summary_today(msg, is_group=True):
        if is_group:
            summary = await get_group_today_summary_text(msg.group_id)
            if summary:
                await msg.reply(text=summary)
        else:
            summary = generate_today_summary(user_id=msg.user_id)
            await bot.api.post_private_msg(msg.user_id, text=summary)

    @register_command(
        "/summary_auto",
        help_text="/summary_auto -> 开启或关闭每日自动总结群聊记录(admin)",
        category="2",
        admin_show=True,
    )
    async def handle_summary_auto(msg, is_group=True):
        if not is_group:
            await bot.api.post_private_msg(msg.user_id, text="请在群聊中使用该命令喔~")
            return
        if str(msg.user_id) not in admin:
            await msg.reply(text="你没有权限开启自动总结喔~")
            return

        state = switch.toggle_switch("summary_auto", group_id=str(msg.group_id))
        text = "已开启每日自动总结喔（将在每天23:55发送）" if state else "已关闭每日自动总结喔"
        await msg.reply(text=text)
        switch.save_switches()

    @register_command(
        "/auto_reply",
        help_text="/auto_reply [on|off|话痨程度0-1] -> 开启/关闭或设置群聊智能自动回复(admin)",
        category="2",
        admin_show=True,
    )
    async def handle_auto_reply(msg, is_group=True):
        if not is_group:
            await bot.api.post_private_msg(msg.user_id, text="请在群聊中使用该命令喔~")
            return
        if str(msg.user_id) not in admin:
            await msg.reply(text="你没有权限开启智能自动回复喔~")
            return
        group_id_str = str(msg.group_id)
        raw = (getattr(msg, "raw_message", "") or "")[len("/auto_reply"):].strip()
        level = None
        desired_state = None
        if raw:
            parts = raw.split()
            action = parts[0].lower()
            if action in {"on", "enable", "start", "开启", "打开"}:
                desired_state = True
                parts = parts[1:]
            elif action in {"off", "disable", "stop", "关闭", "关掉"}:
                desired_state = False
                parts = parts[1:]

            level_text = parts[0] if parts else None
            if level_text is None and desired_state is None:
                level_text = action

        if raw and level_text is not None:
            try:
                level = max(0.0, min(float(level_text), 1.0))
            except ValueError:
                await msg.reply(text="格式错误喔，请输入 on/off，或 0~1 之间的小数，例如 0.3 或 0.8")
                return
            switch.group_switches.setdefault(group_id_str, {})["auto_reply_level"] = level

            # 设置话痨程度时应保持自动回复开启，避免连续设置 level 反复切换开关。
            if desired_state is None:
                desired_state = True

        if desired_state is None:
            state = switch.toggle_switch("auto_reply", group_id=group_id_str)
        else:
            switch.set_switch_state("auto_reply", desired_state, group_id=group_id_str)
            state = desired_state

        if level is None:
            try:
                level = float(switch.group_switches.get(group_id_str, {}).get("auto_reply_level", 0.5))
            except Exception:
                level = 0.5
        text = ("已开启群聊智能自动回复喔~" if state else "已关闭群聊智能自动回复喔~") + f" 当前话痨程度：{level:.2f}"
        await msg.reply(text=text)
        switch.save_switches()

    @register_command(
        "/主动聊天",
        help_text="/主动聊天 [是否开启(1/0)] -> 开启/关闭主动聊天（AI将自行决定聊天频率）",
        category="2",
    )
    async def handle_active_chat(msg, is_group=True):
        if is_group:
            await msg.reply(text="只能私聊设置喔~")
            return

        try:
            raw = (getattr(msg, "raw_message", "") or "")[len("/主动聊天"):].strip()
            parts = raw.split() if raw else []
            user_id = str(msg.user_id)
            current = running.get(user_id, {})
            interval = float(current.get("interval", 1.0))
            active = bool(current.get("active", False))

            if not parts:
                active = not active
            elif len(parts) == 1:
                if parts[0] in ("0", "1"):
                    active = bool(int(parts[0]))
                else:
                    interval = float(parts[0])
                    active = True
            elif len(parts) >= 2:
                interval = float(parts[0])
                if parts[1] in ("0", "1"):
                    active = bool(int(parts[1]))

            running.setdefault(user_id, {})
            running[user_id]["interval"] = interval
            running[user_id]["active"] = active
            running[user_id]["state"] = False
            switch.set_switch_state("active_chat", active, user_id=user_id)

            if active:
                try:
                    recent = await bot.api.get_recent_contact(100)
                    for contact in recent.get("data", []):
                        latest = contact.get("lastestMsg", {})
                        if str(latest.get("user_id")) == user_id:
                            running[user_id]["last_time"] = normalize_timestamp(latest.get("time", 0))
                            break
                    running[user_id].setdefault("last_time", time.time())
                except Exception as e:
                    log.error(f"获取最近联系人失败: {e}")
                    running[user_id]["last_time"] = time.time()

            write_running()
            reply = f"设置成功喔，{'AI现在会自行决定什么时候找你聊天喔~' if active else '已关闭主动聊天喔~'}"
            await bot.api.post_private_msg(user_id, text=reply)
        except ValueError:
            await bot.api.post_private_msg(msg.user_id, text="格式错误喔，请输入 /主动聊天 [1/0]")

    @register_command(
        "/show_chat",
        "/sc",
        help_text="/show_chat 或 /sc -> 发送完整聊天记录(仅群admin)",
        category="2",
    )
    async def handle_show_chat(msg, is_group=True):
        if (str(msg.user_id) not in admin) and is_group:
            await msg.reply(text="你没有权限发送聊天记录喔~")
            return

        cache_dir = normalize_file_path(os.path.join(load_address(), "聊天记录.txt"))
        is_web = hasattr(msg, "send_file") and not hasattr(msg, "message_type")

        if is_group and not is_web:
            try:
                text = str(group_messages[str(msg.group_id)])
            except KeyError:
                text = "该群没有聊天记录喔~"
            with open(cache_dir, "w", encoding="utf-8") as f:
                f.write(text)
            await bot.api.post_group_file(msg.group_id, file=cache_dir)
        else:
            try:
                text = str(user_messages[str(msg.user_id)])
            except KeyError:
                text = "你没有聊天记录喔~"
            with open(cache_dir, "w", encoding="utf-8") as f:
                f.write(text)
            if is_web and hasattr(msg, "send_file"):
                await msg.send_file(cache_dir, "聊天记录.txt")
            else:
                await bot.api.upload_private_file(msg.user_id, file=cache_dir, name="聊天记录.txt")

        try:
            os.remove(cache_dir)
        except OSError:
            pass

    @register_command(
        "/set_prompt",
        "/sp",
        help_text="/set_prompt 或 /sp <提示词> -> 设定当前会话提示词(群聊仅admin)",
        category="2",
    )
    async def handle_set_prompt(msg, is_group=True):
        if (str(msg.user_id) not in admin) and is_group:
            await msg.reply(text="你没有权限喔~")
            return

        raw = getattr(msg, "raw_message", "") or ""
        if raw.startswith("/set_prompt"):
            prompt_content = raw[len("/set_prompt"):].strip()
        else:
            prompt_content = raw[len("/sp"):].strip()

        id_str = str(msg.group_id if is_group else msg.user_id)
        prefix = "group" if is_group else "user"
        os.makedirs(f"resources/prompts/{prefix}", exist_ok=True)
        with open(f"resources/prompts/{prefix}/{prefix}_{id_str}.txt", "w", encoding="utf-8") as file:
            file.write(prompt_content)

        messages = group_messages if is_group else user_messages
        messages[id_str] = [{"role": "system", "content": prompt_content}]
        save_qq_histories()

        reply_text = "群组提示词已更新，对话记录已清除喔~" if is_group else "个人提示词已更新，对话记录已清除喔~"
        await reply_current_channel(msg, is_group, reply_text)

    @register_command(
        "/del_prompt",
        "/dp",
        help_text="/del_prompt 或 /dp -> 删除当前会话提示词(群聊仅admin)",
        category="2",
    )
    async def handle_del_prompt(msg, is_group=True):
        if (str(msg.user_id) not in admin) and is_group:
            await msg.reply(text="你没有权限喔~")
            return

        id_str = str(msg.group_id if is_group else msg.user_id)
        prefix = "group" if is_group else "user"
        messages = group_messages if is_group else user_messages
        prompt_path = f"resources/prompts/{prefix}/{prefix}_{id_str}.txt"

        messages.pop(id_str, None)
        try:
            os.remove(prompt_path)
        except FileNotFoundError:
            await reply_current_channel(msg, is_group, "没有可以删除的提示词喔~")
            return

        try:
            from nbot.core.prompt import prompt_manager

            kwargs = {"group_id": id_str} if is_group else {"user_id": id_str}
            prompt = prompt_manager.load_base_prompt(**kwargs)
            messages[id_str] = [{"role": "system", "content": prompt}]
            save_qq_histories()
        except Exception as e:
            log.warning(f"Reload base prompt failed: {e}")

        await reply_current_channel(msg, is_group, "提示词已删除喔~")

    @register_command(
        "/get_prompt",
        "/gp",
        help_text="/get_prompt 或 /gp -> 获取当前会话提示词(群聊仅admin)",
        category="2",
    )
    async def handle_get_prompt(msg, is_group=True):
        if (str(msg.user_id) not in admin) and is_group:
            await msg.reply(text="你没有权限喔~")
            return

        id_str = str(msg.group_id if is_group else msg.user_id)
        prefix = "group" if is_group else "user"
        try:
            with open(f"resources/prompts/{prefix}/{prefix}_{id_str}.txt", "r", encoding="utf-8") as file:
                prompt = file.read()
        except FileNotFoundError:
            prompt = "没有找到提示词喔~"
        await reply_current_channel(msg, is_group, prompt)

    @register_command("/new", help_text="/new -> 创建新的对话会话 (清空当前对话历史)", category="2")
    async def handle_new_session(msg, is_group=True):
        if is_group:
            group_id = getattr(msg, "group_id", None)
            chat_id = getattr(msg, "chat_id", None)
            if group_id:
                gid = str(group_id)
                group_messages.pop(gid, None)
                save_qq_histories()
                delete_session_workspace(group_id=gid, group_user_id=str(msg.user_id))
            elif chat_id:
                session_id = getattr(msg, "session_id", None)
                server = getattr(msg, "server", None)
                if session_id and server and hasattr(server, "sessions"):
                    from nbot.core.session_store import WebSessionStore

                    session_store = WebSessionStore(
                        server.sessions,
                        save_callback=lambda: server._save_data("sessions"),
                    )
                    session = session_store.get_session(session_id)
                    if session:
                        system_msg = next(
                            (m for m in session.get("messages", []) if m.get("role") == "system"),
                            None,
                        )
                        session_store.replace_messages(session_id, [system_msg] if system_msg else [])
                        session["updated_at"] = datetime.now().isoformat()
                    delete_session_workspace(user_id=str(msg.user_id))
                else:
                    await msg.reply(text="当前平台不支持会话重置喔~")
                    return
            else:
                await msg.reply(text="当前平台不支持会话重置喔~")
                return
            await msg.reply(text="已创建新会话喔，之前的对话历史已清空")
            return

        user_id = str(msg.user_id)
        user_messages.pop(user_id, None)
        save_qq_histories()
        delete_session_workspace(user_id=user_id)
        await bot.api.post_private_msg(msg.user_id, text="已创建新会话喔，之前的对话历史已清空")

    @register_command(
        "/character",
        "/char",
        help_text="/character -> 查看/切换角色\n/character list -> 列出角色\n/character <编号|id|名称> -> 切换角色",
        category="2",
    )
    async def handle_character_switch(msg, is_group=True):
        raw = (getattr(msg, "raw_message", "") or "").strip()
        parts = raw.split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else ""

        characters = load_character_options()
        session_scope, session_target_id = resolve_character_session(msg, is_group)
        active = find_session_character(characters, session_scope, session_target_id, msg)
        active_id = str(active.get("id") or active.get("name") or "")
        active_name = str(active.get("name") or active_id or "未设置")

        if not characters:
            await reply_current_channel(msg, is_group, "还没有可切换的角色。请先在 Web 角色卡里创建或导入角色。")
            return

        if not arg or arg.lower() == "list":
            lines = [f"当前角色：{active_name}", "", "可用角色："]
            for i, character in enumerate(characters, 1):
                name = character.get("name") or character.get("id") or "未命名"
                character_id = character.get("id") or name
                marker = "（当前）" if str(character_id) == active_id or str(name) == active_name else ""
                desc = str(character.get("description") or "").strip()
                suffix = f" - {desc[:40]}" if desc else ""
                lines.append(f"{i}. {name} [{character_id}]{marker}{suffix}")
            lines.append("")
            lines.append("用法：/character <编号|id|名称>")
            await reply_current_channel(msg, is_group, "\n".join(lines))
            return

        target = find_character(characters, arg)
        if not target:
            await reply_current_channel(msg, is_group, f"没有找到角色：{arg}\n发送 /character list 查看可用角色。")
            return

        try:
            set_current_session_character(msg, is_group, target)
        except Exception as e:
            log.error(f"Switch character failed: {e}", exc_info=True)
            await reply_current_channel(msg, is_group, f"切换角色失败：{e}")
            return

        name = target.get("name") or target.get("id") or arg
        await reply_current_channel(
            msg,
            is_group,
            f"已切换当前会话角色：{name}\n当前会话历史已清空，提示词已更新。",
        )

    @register_command(
        "/model",
        help_text="/model -> 查看当前模型\n/model <编号> -> 切换到指定模型\n/model list -> 列出所有可用模型",
        category="2",
    )
    async def handle_model_switch(msg, is_group=True):
        data_dir = os.path.join("data", "web")
        models_file = os.path.join(data_dir, "ai_models.json")

        if not os.path.exists(models_file):
            await reply_current_channel(msg, is_group, "暂无可用模型配置，请先在 Web 控制台添加模型喔~")
            return

        try:
            models_data, was_plaintext = read_secure_json(models_file, data_dir, {})
            if was_plaintext:
                write_secure_json(models_file, data_dir, models_data)
            if not isinstance(models_data, dict):
                models_data = {}
        except Exception:
            await reply_current_channel(msg, is_group, "读取模型配置失败喔~")
            return

        all_models = models_data.get("models", [])
        active_id = models_data.get("active_model_id")
        chat_models = [
            m for m in all_models
            if m.get("purpose", "chat") == "chat" and m.get("enabled", True)
        ]

        if not chat_models:
            await reply_current_channel(msg, is_group, "暂无启用的对话模型，请先在 Web 控制台启用一个对话模型喔~")
            return

        raw = getattr(msg, "raw_message", "").strip()
        parts = raw.split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else ""

        if arg == "" or arg == "list":
            lines = ["可用对话模型"]
            for i, model in enumerate(chat_models, 1):
                marker = " (当前)" if model.get("id") == active_id else ""
                name = model.get("name", "未命名")
                model_name = model.get("model", "?")
                lines.append(f"{i}. {name} - `{model_name}`{marker}")
            lines.append("")
            lines.append("输入 /model <编号> 切换模型")
            await reply_current_channel(msg, is_group, "\n".join(lines))
            return

        try:
            idx = int(arg)
        except ValueError:
            idx = 0

        if 1 <= idx <= len(chat_models):
            target = chat_models[idx - 1]
            models_data["active_model_id"] = target.get("id")
            write_secure_json(models_file, data_dir, models_data)
            from nbot.services.ai import refresh_runtime_ai_config

            refresh_runtime_ai_config()
            await reply_current_channel(
                msg,
                is_group,
                f"已切换到模型: {target.get('name', '未命名')} (`{target.get('model', '?')}`)",
            )
            return

        current = next((m for m in chat_models if m.get("id") == active_id), None)
        if current:
            reply = (
                f"当前模型: {current.get('name', '未命名')}\n"
                f"模型: `{current.get('model', '?')}`\n"
                f"厂商: {current.get('provider', '?')}\n"
                f"上下文: {current.get('max_context_length', 100000):,} tokens\n\n"
                "输入 /model list 查看所有可用模型"
            )
        else:
            reply = "未找到当前模型信息喔~"
        await reply_current_channel(msg, is_group, reply)

    @register_command(
        "/resume",
        help_text="/resume [编号|会话ID|名称] -> 从当前角色的 Web 会话载入到当前频道",
        category="2",
    )
    async def handle_resume_session(msg, is_group=True):
        raw = (getattr(msg, "raw_message", "") or "").strip()
        parts = raw.split(maxsplit=1)
        arg = parts[1].strip() if len(parts) > 1 else ""
        active = current_character(msg, is_group)
        candidates = candidate_resume_sessions(msg, is_group)

        if not arg:
            await reply_current_channel(
                msg,
                is_group,
                format_resume_session_list(candidates, active),
            )
            return

        selected = find_resume_session(candidates, arg)
        if not selected:
            await reply_current_channel(
                msg,
                is_group,
                "没有找到匹配的 Web 会话。发送 /resume 查看当前角色可载入的会话。",
            )
            return

        web_session_id, web_session, _ = selected
        info = current_qq_session_info(msg, is_group)
        messages = copy_chat_messages(web_session.get("messages", []))
        system_prompt = session_system_prompt(web_session, messages)
        if system_prompt and not any(m.get("role") == "system" for m in messages):
            messages.insert(0, {"role": "system", "content": system_prompt})

        info["store"][info["history_key"]] = messages
        save_qq_histories()

        bindings = load_resume_bindings()
        bindings[info["session_id"]] = {
            "web_session_id": web_session_id,
            "web_session_name": web_session.get("name") or "",
            "loaded_at": datetime.now().isoformat(),
            "channel": info["label"],
            "character_id": web_session.get("character_id") or web_session.get("sender_name") or "",
        }
        save_resume_bindings(bindings)

        try:
            delete_session_workspace(
                user_id=info["user_id"],
                group_id=info["group_id"],
                group_user_id=info["group_user_id"],
            )
        except Exception:
            pass

        await reply_current_channel(
            msg,
            is_group,
            f"已从 Web 会话「{web_session.get('name') or web_session_id[:8]}」载入 {len(messages)} 条消息到当前频道。\n之后 /push 会回写到该 Web 会话。",
        )

    @register_command(
        "/push",
        help_text="/push -> 将当前频道会话上传到 /resume 绑定的 Web 会话",
        category="2",
    )
    async def handle_push_session(msg, is_group=True):
        info = current_qq_session_info(msg, is_group)
        bindings = load_resume_bindings()
        binding = bindings.get(info["session_id"])
        if not binding:
            await reply_current_channel(
                msg,
                is_group,
                "当前频道还没有绑定 Web 会话。请先发送 /resume 选择一个会话。",
            )
            return

        web_session_id = binding.get("web_session_id")
        sessions = load_web_sessions()
        web_session = sessions.get(web_session_id)
        if not isinstance(web_session, dict):
            await reply_current_channel(
                msg,
                is_group,
                "绑定的 Web 会话不存在了。请重新发送 /resume 选择会话。",
            )
            return

        current_messages = copy_chat_messages(info["store"].get(info["history_key"], []))
        if not current_messages:
            await reply_current_channel(msg, is_group, "当前频道没有可上传的会话内容。")
            return

        system_prompt = session_system_prompt(web_session, current_messages)
        if system_prompt and not any(m.get("role") == "system" for m in current_messages):
            current_messages.insert(0, {"role": "system", "content": system_prompt})

        web_session["messages"] = current_messages
        web_session["system_prompt"] = session_system_prompt(web_session, current_messages)
        web_session["updated_at"] = datetime.now().isoformat()
        web_session["last_message"] = next(
            (
                str(m.get("content") or "")[:100]
                for m in reversed(current_messages)
                if isinstance(m, dict) and m.get("role") != "system"
            ),
            "",
        )
        sessions[web_session_id] = web_session
        save_web_sessions(sessions)

        binding["pushed_at"] = web_session["updated_at"]
        bindings[info["session_id"]] = binding
        save_resume_bindings(bindings)

        await reply_current_channel(
            msg,
            is_group,
            f"已上传当前频道的 {len(current_messages)} 条消息到 Web 会话「{web_session.get('name') or web_session_id[:8]}」。",
        )
