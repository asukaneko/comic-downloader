"""
Hook Action Executor

Executes hook actions after event matching.
"""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

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
        self._handlers: Dict[str, Callable] = {}
        self._register_builtins()

    def _register_builtins(self):
        self.register("prompt_inject", self._action_prompt_inject)
        self.register("state_delta", self._action_state_delta)
        self.register("relationship_delta", self._action_relationship_delta)
        self.register("memory_write", self._action_memory_write)
        self.register("log", self._action_log)
        self.register("message", self._action_message)

    def register(self, action_type: str, handler: Callable) -> None:
        self._handlers[action_type] = handler

    async def execute(self, action: Dict[str, Any], event: RuntimeEvent, context: Dict[str, Any]) -> ActionResult:
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

    async def execute_all(self, actions: List[Dict[str, Any]], event: RuntimeEvent, context: Dict[str, Any]) -> List[ActionResult]:
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
        payload = action.get("payload", {})
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
        payload = action.get("payload", {})
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
        memory_service = ctx.get("memory_service")
        if memory_service is None:
            return ActionResult(False, "memory_write", "Memory service unavailable")
        title = action.get("title", "")
        content = action.get("content", "")
        mem_type = action.get("mem_type", "long")
        if not content:
            return ActionResult(False, "memory_write", "Empty content")
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
