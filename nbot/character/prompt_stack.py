"""
动态提示词栈

允许任意模块在任意阶段注册提示词注入项，
最终统一合成为本轮顶部 system/developer prompt。

核心原则：
- 动态注入只在本轮请求生效，不写入历史消息
- 按优先级排序合成
- 可调试、可观察
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

_log = logging.getLogger(__name__)

PromptRole = Literal["system", "developer"]
PromptScope = Literal["global", "session", "turn"]


@dataclass
class PromptInjection:
    """单条提示词注入项"""

    key: str
    content: str
    priority: int = 100
    role: PromptRole = "system"
    scope: PromptScope = "turn"
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "content": self.content[:200] + "..." if len(self.content) > 200 else self.content,
            "priority": self.priority,
            "role": self.role,
            "scope": self.scope,
            "enabled": self.enabled,
        }


class PromptStack:
    """动态提示词栈，收集并合成所有注入项"""

    # 推荐优先级常量
    PRIORITY_SAFETY = 10
    PRIORITY_BEHAVIOR = 20
    PRIORITY_CHARACTER_PROFILE = 30
    PRIORITY_CHARACTER_STATE = 40
    PRIORITY_CHARACTER_RELATIONSHIP = 50
    PRIORITY_CHARACTER_MEMORIES = 60
    PRIORITY_KNOWLEDGE_RAG = 70
    PRIORITY_TOOL_INSTRUCTIONS = 80
    PRIORITY_REACTION_PLAN = 90

    def __init__(self):
        self.items: List[PromptInjection] = []

    def add(
        self,
        key: str,
        content: str,
        priority: int = 100,
        role: str = "system",
        scope: str = "turn",
    ) -> None:
        """注册一条提示词注入项

        Args:
            key: 注入项标识，用于调试和去重
            content: 注入内容
            priority: 优先级，数值越小越靠前
            role: 消息角色 (system / developer)
            scope: 作用域 (global / session / turn)
        """
        if not content or not content.strip():
            return

        # 同 key 则替换
        for i, item in enumerate(self.items):
            if item.key == key:
                self.items[i] = PromptInjection(
                    key=key,
                    content=content.strip(),
                    priority=priority,
                    role=role,
                    scope=scope,
                )
                return

        self.items.append(PromptInjection(
            key=key,
            content=content.strip(),
            priority=priority,
            role=role,
            scope=scope,
        ))

    def remove(self, key: str) -> bool:
        """移除指定 key 的注入项"""
        before = len(self.items)
        self.items = [item for item in self.items if item.key != key]
        return len(self.items) < before

    def get(self, key: str) -> Optional[PromptInjection]:
        """获取指定 key 的注入项"""
        for item in self.items:
            if item.key == key:
                return item
        return None

    def render(self, base_prompt: str = "") -> str:
        """合成所有注入项为最终的 system prompt

        Args:
            base_prompt: 基础系统提示词（通常来自角色卡编译结果）

        Returns:
            合成后的完整系统提示词
        """
        parts = []

        if base_prompt and base_prompt.strip():
            parts.append(base_prompt.strip())

        for item in sorted(self.items, key=lambda x: x.priority):
            if item.enabled and item.content.strip():
                parts.append(f"## {item.key}\n{item.content.strip()}")

        return "\n\n".join(parts).strip()

    def render_debug(self) -> List[Dict[str, Any]]:
        """返回调试信息，展示本轮所有注入项"""
        return [
            item.to_dict()
            for item in sorted(self.items, key=lambda x: x.priority)
        ]

    def clear_scope(self, scope: str) -> int:
        """清除指定作用域的所有注入项，返回清除数量"""
        before = len(self.items)
        self.items = [item for item in self.items if item.scope != scope]
        return before - len(self.items)

    @property
    def keys(self) -> List[str]:
        """返回所有已注册的 key 列表"""
        return [item.key for item in self.items]


def split_system_prompt(messages: List[Dict[str, Any]]) -> tuple:
    """从消息列表中分离 system prompt 和历史消息

    Args:
        messages: 完整消息列表

    Returns:
        (system_prompt_text, history_messages) 元组
    """
    system_parts = []
    history = []

    for msg in messages:
        role = msg.get("role", "")
        if role == "system":
            content = msg.get("content", "")
            if content:
                system_parts.append(content)
        else:
            history.append(msg)

    system_prompt = "\n\n".join(system_parts).strip()
    return system_prompt, history
