"""
Hook Action Executor

Executes hook actions after event matching.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from nbot.hooks.models import RuntimeEvent

_log = logging.getLogger(__name__)


@dataclass
class ActionResult:
    success: bool
    action_type: str
    detail: str = ""
    output: Any = None


class ActionExecutor:
    def __init__(self):
        self._handlers: dict[str, Callable] = {}
        self._register_builtins()

    def _register_builtins(self):
        self.register("prompt_inject", self._action_prompt_inject)
        self.register("state_delta", self._action_state_delta)
        self.register("relationship_delta", self._action_relationship_delta)
        self.register("memory_write", self._action_memory_write)
        self.register("log", self._action_log)
        self.register("message", self._action_message)
        self.register("workflow", self._action_workflow)
        self.register("world_book_add", self._action_world_book_add)

    def register(self, action_type: str, handler: Callable) -> None:
        self._handlers[action_type] = handler

    async def execute(self, action: dict[str, Any], event: RuntimeEvent, context: dict[str, Any]) -> ActionResult:
        action_type = action.get("type", "")
        handler = self._handlers.get(action_type)
        if not handler:
            _log.warning("[HookAction] unknown type: %s", action_type)
            return ActionResult(success=False, action_type=action_type, detail="Unknown type: " + action_type)
        try:
            result = handler(action, event, context)
            if hasattr(result, "__await__"):
                result = await result
            return result
        except Exception as e:
            _log.error("[HookAction] failed type=%s err=%s", action_type, e)
            return ActionResult(success=False, action_type=action_type, detail=str(e))

    async def execute_all(self, actions: list[dict[str, Any]], event: RuntimeEvent, context: dict[str, Any]) -> list[ActionResult]:
        results = []
        for action in actions:
            results.append(await self.execute(action, event, context))
        return results

    @staticmethod
    def _action_prompt_inject(action, event, ctx):
        prompt_stack = ctx.get("prompt_stack")
        if prompt_stack is None:
            return ActionResult(False, "prompt_inject", "PromptStack unavailable")
        key = action.get("key", "hook_" + event.id[:8])
        content = action.get("content", "")
        priority = action.get("priority", 55)
        scope = action.get("scope", "turn")
        if content:
            prompt_stack.add(key, content, priority=priority, scope=scope)
        return ActionResult(True, "prompt_inject", "inject " + key)

    @staticmethod
    def _action_state_delta(action, event, ctx):
        state = ctx.get("character_state")
        if state is None:
            return ActionResult(False, "state_delta", "State unavailable")
        # 兼容两种格式：
        #   文档格式: {"field": "energy", "delta": -5}
        #   代码格式: {"payload": {"energy": -5}}
        payload = action.get("payload", {})
        if not payload and "field" in action:
            payload = {action["field"]: action.get("delta", 0)}
        changes = {}
        for field_name, value in payload.items():
            if not hasattr(state, field_name):
                continue
            old = getattr(state, field_name)
            if field_name == "mood":
                setattr(state, field_name, str(value))
                changes[field_name] = str(old) + " -> " + str(value)
            elif field_name == "mood_intensity":
                new_val = max(0.0, min(1.0, float(old) + float(value)))
                setattr(state, field_name, new_val)
                changes[field_name] = str(old) + " -> " + str(new_val)
            elif field_name == "energy":
                new_val = max(0, min(100, int(old) + int(value)))
                setattr(state, field_name, new_val)
                changes[field_name] = str(old) + " -> " + str(new_val)
            else:
                setattr(state, field_name, value)
                changes[field_name] = str(old) + " -> " + str(value)
        return ActionResult(True, "state_delta", str(changes), changes)

    @staticmethod
    def _action_relationship_delta(action, event, ctx):
        relationship = ctx.get("relationship")
        if relationship is None:
            return ActionResult(False, "relationship_delta", "Relationship unavailable")
        # 兼容两种格式（同 state_delta）
        payload = action.get("payload", {})
        if not payload and "field" in action:
            payload = {action["field"]: action.get("delta", 0)}
        changes = {}
        valid = {"affection", "trust", "familiarity", "dependency", "security", "jealousy"}
        for field_name, delta in payload.items():
            if field_name not in valid or not hasattr(relationship, field_name):
                continue
            old = getattr(relationship, field_name)
            new_val = max(0, min(100, int(old) + int(delta)))
            setattr(relationship, field_name, new_val)
            changes[field_name] = str(old) + " -> " + str(new_val)
        return ActionResult(True, "relationship_delta", str(changes), changes)

    @staticmethod
    def _action_memory_write(action, event, ctx):
        title = action.get("title", "")
        content = action.get("content", "")
        category = action.get("category") or action.get("memory_category")
        # 兼容: 文档用 memory_type，代码用 mem_type
        mem_type = action.get("mem_type") or action.get("memory_type", "long")
        if not content:
            return ActionResult(False, "memory_write", "Empty content")
        if category:
            return ActionExecutor._action_structured_memory_write(action, event, content)

        memory_service = ctx.get("memory_service")
        if memory_service is None:
            return ActionResult(False, "memory_write", "Memory service unavailable")
        try:
            memory_service.save(
                character_id=event.character_id,
                target_id=event.user_id,
                title=title,
                content=content,
                summary=content[:100] if len(content) > 100 else content,
                mem_type=mem_type,
            )
            return ActionResult(True, "memory_write", "saved: " + title)
        except Exception as e:
            return ActionResult(False, "memory_write", str(e))

    @staticmethod
    def _action_structured_memory_write(action, event, content):
        try:
            from nbot.memory.fs import get_memory_fs, normalize_memory_category

            category = normalize_memory_category(
                action.get("category") or action.get("memory_category")
            )
            if not category:
                return ActionResult(False, "memory_write", "Unknown memory category")

            character_id = str(action.get("character_id") or event.character_id or "").strip()
            target_id = str(
                action.get("target_id")
                or action.get("user_id")
                or event.user_id
                or ""
            ).strip()
            conversation_id = str(
                action.get("conversation_id")
                or event.conversation_id
                or target_id
                or "general"
            ).strip()
            if not character_id:
                return ActionResult(False, "memory_write", "Missing character_id")
            # important_event 和 timeline 都是角色级，不需要 target_id
            if category not in ("important_event", "timeline") and not target_id:
                return ActionResult(False, "memory_write", "Missing target_id")

            title = str(action.get("title") or "").strip()
            summary = str(action.get("summary") or content[:100]).strip()
            try:
                importance = max(0.0, min(1.0, float(action.get("importance", 0.6))))
            except (TypeError, ValueError):
                importance = 0.6

            mfs = get_memory_fs()
            if category == "user_persona":
                path = mfs.path_user_persona(character_id, target_id)
                fallback_title = "用户人格记忆"
                default_append = True
            elif category == "character_persona":
                path = mfs.path_character_persona(character_id, target_id)
                fallback_title = "角色人格记忆"
                default_append = True
            elif category == "recent_digest":
                path = mfs.path_recent_digest(character_id, target_id)
                fallback_title = "近期对话压缩摘要"
                default_append = False
            elif category == "timeline":
                # 跨会话时间线：角色级（不需 target_id），追加
                path = mfs.path_timeline(character_id)
                fallback_title = "跨会话时间线条目"
                default_append = True
            else:
                path = mfs.path_important_events(character_id, conversation_id)
                fallback_title = "重要事件"
                default_append = True

            append = action.get("append")
            if append is None:
                append = default_append
            mfs.write(
                path,
                character_id=character_id,
                target_id=target_id,
                title=title or fallback_title,
                content=content,
                summary=summary,
                importance=importance,
                append=bool(append),
            )
            return ActionResult(True, "memory_write", f"saved {category}: {path}", {
                "category": category,
                "path": path,
            })
        except Exception as e:
            return ActionResult(False, "memory_write", str(e))

    @staticmethod
    def _action_log(action, event, ctx):
        level = action.get("level", "info")
        message = action.get("message", "")
        log_func = getattr(_log, level, _log.info)
        log_func("[HookAction:log] %s", message)
        return ActionResult(True, "log", message)

    @staticmethod
    def _action_message(action, event, ctx):
        content = action.get("content", "")
        if not content:
            return ActionResult(False, "message", "Empty content")
        hook_messages = ctx.setdefault("hook_messages", [])
        hook_messages.append(content)
        return ActionResult(True, "message", "marked: " + content[:50])

    @staticmethod
    async def _action_workflow(action, event, ctx):
        """Trigger a workflow execution.

        action structure:
        {
            "type": "workflow",
            "workflow": "wf_goodnight_event"
        }
        """
        # 兼容: 文档用 workflow_id，代码用 workflow
        workflow_name = action.get("workflow") or action.get("workflow_id", "")
        if not workflow_name:
            return ActionResult(False, "workflow", "No workflow name")
        try:
            from nbot.core.workflow import get_workflow_engine
            engine = get_workflow_engine()
            context = {"event": event.to_dict(), **ctx}
            instance = await engine.execute_workflow(workflow_name, context)
            status = getattr(instance, "status", "unknown")
            return ActionResult(
                status != "error", "workflow",
                "ran " + workflow_name + " status=" + str(status),
            )
        except Exception as e:
            return ActionResult(False, "workflow", str(e))

    @staticmethod
    def _action_world_book_add(action, event, ctx):
        """Add an entry to a world book.

        action structure:
        {
            "type": "world_book_add",
            "book_id": "wb_xxx",
            "name": "entry name",
            "content": "entry content",
            "keywords": ["kw1", "kw2"],
            "entry_type": "event",
            "priority": 80
        }
        """
        try:
            from nbot.character.storage.world_book_store import WorldBookStore
            store = WorldBookStore()
        except Exception:
            return ActionResult(False, "world_book_add", "WorldBookStore unavailable")

        book_id = action.get("book_id", "")
        if not book_id:
            return ActionResult(False, "world_book_add", "No book_id")

        entry_data = {
            "name": action.get("name", ""),
            "content": action.get("content", ""),
            "keywords": action.get("keywords", []),
            "entry_type": action.get("entry_type", "event"),
            "priority": action.get("priority", 50),
            "always_on": action.get("always_on", False),
            "tags": action.get("tags", []),
        }

        if not entry_data["content"]:
            return ActionResult(False, "world_book_add", "Empty content")

        try:
            entry = store.add_entry(book_id, entry_data)
            if entry:
                return ActionResult(True, "world_book_add", "added: " + entry.name)
            return ActionResult(False, "world_book_add", "Book not found: " + book_id)
        except Exception as e:
            return ActionResult(False, "world_book_add", str(e))
