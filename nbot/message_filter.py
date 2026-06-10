"""消息过滤器模块

按频道/会话/全局配置关键词或正则表达式，支持两种过滤模式：
- strip:  删除消息中的指定文字（不撤回整条消息）
- recall: 撤回整条匹配消息

配置存储在 resources/config/message_filter.json。

存储结构：
{
    "global": [...rules...],
    "channels": {
        "qq": [
            {"session_scope": "all", "session_id": "", ...rules...},
            {"session_scope": "specific", "session_id": "qq:group:123456", ...rules...}
        ],
        "web": [...]
    }
}
"""

import json
import logging
import os
import re
import uuid
from concurrent.futures import TimeoutError as FuturesTimeout
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

_log = logging.getLogger(__name__)

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources",
    "config",
)
_CONFIG_FILE = os.path.join(_CONFIG_DIR, "message_filter.json")

_REGEX_MATCH_TIMEOUT = 0.1
_regex_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="msg_filter_regex")

DEFAULT_STRIP_MARKER = "<||>"

_QQ_CHANNEL_ALIASES = {"qq", "qq_group", "qq_private"}


class MessageFilter:
    """消息过滤器：按频道/会话/全局配置关键词，支持文本删除和消息撤回"""

    def __init__(self) -> None:
        self.enabled: bool = True
        self.filters: dict[str, Any] = {
            "global": [],
            "channels": {},
        }
        self._compiled_regex: dict[str, re.Pattern] = {}
        self._last_mtime: float = 0.0
        self.load()

    # ------------------------------------------------------------------
    # 默认标记处理
    # ------------------------------------------------------------------

    @staticmethod
    def strip_default_markers(content: str) -> str:
        """剥离默认删除标记 <||>，保留所有内容。"""
        if not content or DEFAULT_STRIP_MARKER not in content:
            return content
        return content.replace(DEFAULT_STRIP_MARKER, "").strip()

    @staticmethod
    def normalize_channel(channel: str) -> str:
        value = (channel or "global").strip()
        if value in _QQ_CHANNEL_ALIASES:
            return "qq"
        return value or "global"

    @staticmethod
    def normalize_session_id(channel: str, session_id: str) -> str:
        value = (session_id or "").strip()
        if not value:
            return ""

        normalized_channel = MessageFilter.normalize_channel(channel)
        if normalized_channel == "qq":
            if value.startswith("qq_group_"):
                group_id = value[len("qq_group_"):].split("_", 1)[0]
                return f"qq:group:{group_id}" if group_id else ""
            if value.startswith("qq_private_"):
                user_id = value[len("qq_private_"):].split("_", 1)[0]
                return f"qq:private:{user_id}" if user_id else ""
            if value.startswith("qq_group:"):
                return "qq:group:" + value.split(":", 1)[1]
            if value.startswith("qq_private:"):
                return "qq:private:" + value.split(":", 1)[1]

        if normalized_channel == "web" and ":" not in value:
            return f"web:{value}"

        return value

    @staticmethod
    def normalize_session_scope(session_scope: str, session_id: str) -> str:
        scope = (session_scope or "all").strip()
        if scope == "specific" and not (session_id or "").strip():
            return "all"
        return scope if scope in {"all", "specific"} else "all"

    # ------------------------------------------------------------------
    # 自动重载
    # ------------------------------------------------------------------

    def reload_if_needed(self) -> None:
        """检查配置文件是否被外部修改，有变化则重新加载。"""
        try:
            mtime = os.path.getmtime(_CONFIG_FILE)
            if mtime > self._last_mtime:
                self.load()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 匹配
    # ------------------------------------------------------------------

    def match(
        self, content: str, channel: str = "", session_id: str = ""
    ) -> dict | None:
        matched = self.match_all(content, channel, session_id)
        return matched[0] if matched else None

    def match_all(
        self, content: str, channel: str = "", session_id: str = ""
    ) -> list[dict]:
        if not self.enabled or not content:
            return []

        self.reload_if_needed()
        channel = self.normalize_channel(channel)
        session_id = self.normalize_session_id(channel, session_id)
        text = content.strip()
        matched: list[dict] = []

        # 1. 频道级规则（session_scope=all）
        if channel:
            for rule in self.filters.get("channels", {}).get(channel, []):
                if rule.get("session_scope") == "all" and self._match_rule(text, rule):
                    matched.append(rule)

        # 2. 会话级规则（session_scope=specific，精确匹配）
        if channel and session_id:
            for rule in self.filters.get("channels", {}).get(channel, []):
                if (
                    rule.get("session_scope") == "specific"
                    and rule.get("session_id") == session_id
                    and self._match_rule(text, rule)
                ):
                    matched.append(rule)

        # 3. 全局规则（最后，优先级最低）
        for rule in self.filters.get("global", []):
            if self._match_rule(text, rule):
                matched.append(rule)

        return matched

    def strip_content(self, content: str, rules: list[dict]) -> str:
        result = content
        for rule in rules:
            if not rule.get("enabled", True):
                continue
            pattern = rule.get("pattern", "")
            if not pattern:
                continue
            rule_type = rule.get("type", "keyword")

            if rule_type == "regex":
                compiled = self._get_compiled_regex(rule.get("id", ""), pattern)
                if compiled:
                    result = compiled.sub("", result)
            else:
                result = re.sub(re.escape(pattern), "", result, flags=re.IGNORECASE)

        return result.strip()

    def filter_content(
        self, content: str, channel: str = "", session_id: str = ""
    ) -> dict[str, Any]:
        matched_rules = self.match_all(content, channel=channel, session_id=session_id)
        if not matched_rules:
            return {
                "content": content,
                "filtered": False,
                "blocked": False,
                "rules": [],
            }

        recall_rules = [r for r in matched_rules if r.get("action") == "recall"]
        if recall_rules:
            return {
                "content": "",
                "filtered": True,
                "blocked": True,
                "rules": matched_rules,
            }

        filtered_content = self.strip_content(content, matched_rules)
        return {
            "content": filtered_content,
            "filtered": filtered_content != content,
            "blocked": not filtered_content,
            "rules": matched_rules,
        }

    def filter_message(
        self,
        message: dict,
        channel: str = "",
        session_id: str = "",
    ) -> dict[str, Any]:
        if message.get("role") != "user":
            return {
                "message": message,
                "filtered": False,
                "blocked": False,
                "rules": [],
            }

        result = self.filter_content(
            str(message.get("content") or ""),
            channel=channel,
            session_id=session_id,
        )
        if result["blocked"]:
            message["filtered"] = True
            message["filter_blocked"] = True
            message["filter_rule_count"] = len(result["rules"])
        if result["filtered"] and not result["blocked"]:
            message["content"] = result["content"]
            message["filtered"] = True
            message["filter_rule_count"] = len(result["rules"])
        return {"message": message, **result}

    def _match_rule(self, text: str, rule: dict) -> bool:
        if not rule.get("enabled", True):
            return False
        pattern = rule.get("pattern", "")
        if not pattern:
            return False

        if rule.get("type") == "regex":
            compiled = self._get_compiled_regex(rule.get("id", ""), pattern)
            if compiled is None:
                return False
            try:
                future = _regex_pool.submit(compiled.search, text)
                return future.result(timeout=_REGEX_MATCH_TIMEOUT) is not None
            except FuturesTimeout:
                _log.warning("[消息过滤] 正则匹配超时（疑似 ReDoS）: %s", pattern)
                return False

        return pattern.lower() in text.lower()

    def _get_compiled_regex(self, rule_id: str, pattern: str) -> re.Pattern | None:
        if rule_id in self._compiled_regex:
            return self._compiled_regex[rule_id]
        try:
            compiled = re.compile(pattern, re.IGNORECASE | re.DOTALL)
            self._compiled_regex[rule_id] = compiled
            return compiled
        except re.error as e:
            _log.warning("[消息过滤] 正则编译失败: %s, error=%s", pattern, e)
            return None

    # ------------------------------------------------------------------
    # 规则管理
    # ------------------------------------------------------------------

    def add_rule(
        self,
        pattern: str,
        channel: str = "global",
        session_scope: str = "all",
        session_id: str = "",
        rule_type: str = "keyword",
        action: str = "strip",
        group_id: str | None = None,
    ) -> dict:
        if group_id:
            channel = "qq"
            session_scope = "specific"
            session_id = f"qq:group:{group_id}"
        channel = self.normalize_channel(channel)
        session_id = self.normalize_session_id(channel, session_id)
        session_scope = self.normalize_session_scope(session_scope, session_id)
        rule = {
            "id": f"rule_{uuid.uuid4().hex[:8]}",
            "pattern": pattern,
            "type": rule_type,
            "action": action,
            "session_scope": session_scope,
            "session_id": session_id,
            "enabled": True,
            "created_at": datetime.now().isoformat(),
        }

        if channel == "global":
            self.filters.setdefault("global", []).append(rule)
        else:
            self.filters.setdefault("channels", {}).setdefault(channel, []).append(rule)

        self.save()
        return rule

    def add_rule_to(
        self,
        channel: str,
        session_scope: str,
        session_id: str,
        rule: dict,
    ) -> None:
        """将已有规则添加到指定位置（用于移动规则）。"""
        channel = self.normalize_channel(channel)
        session_id = self.normalize_session_id(channel, session_id)
        session_scope = self.normalize_session_scope(session_scope, session_id)
        rule["session_scope"] = session_scope
        rule["session_id"] = session_id
        if channel == "global":
            self.filters.setdefault("global", []).append(rule)
        else:
            self.filters.setdefault("channels", {}).setdefault(channel, []).append(rule)

    def find_rule(
        self, rule_id: str, channel: str = "global", session_id: str = ""
    ) -> dict | None:
        """查找规则。"""
        channel = self.normalize_channel(channel)
        session_id = self.normalize_session_id(channel, session_id)
        if channel == "global":
            rules = self.filters.get("global", [])
        else:
            rules = self.filters.get("channels", {}).get(channel, [])

        for rule in rules:
            if rule.get("id") == rule_id:
                return rule

        # 全局搜索
        for rule in self.filters.get("global", []):
            if rule.get("id") == rule_id:
                return rule
        for ch_rules in self.filters.get("channels", {}).values():
            for rule in ch_rules:
                if rule.get("id") == rule_id:
                    return rule

        return None

    def remove_rule(
        self,
        rule_id: str,
        channel: str = "global",
        session_id: str = "",
        group_id: str | None = None,
    ) -> bool:
        if group_id:
            channel = "qq"
            session_id = f"qq:group:{group_id}"
        channel = self.normalize_channel(channel)
        session_id = self.normalize_session_id(channel, session_id)
        if channel == "global":
            rules = self.filters.get("global", [])
            before = len(rules)
            self.filters["global"] = [r for r in rules if r.get("id") != rule_id]
            removed = len(self.filters["global"]) < before
        else:
            rules = self.filters.get("channels", {}).get(channel, [])
            before = len(rules)
            self.filters["channels"][channel] = [
                r for r in rules if r.get("id") != rule_id
            ]
            removed = len(self.filters["channels"][channel]) < before
            if removed and not self.filters["channels"][channel]:
                del self.filters["channels"][channel]

        if removed:
            self._compiled_regex.pop(rule_id, None)
            self.save()
        return removed

    def list_rules(
        self, channel: str = "global", session_id: str = "", group_id: str | None = None
    ) -> list[dict]:
        if group_id:
            channel = "qq"
            session_id = f"qq:group:{group_id}"
        channel = self.normalize_channel(channel)
        session_id = self.normalize_session_id(channel, session_id)
        if channel == "global":
            return list(self.filters.get("global", []))

        result = []
        for rule in self.filters.get("channels", {}).get(channel, []):
            scope = rule.get("session_scope", "all")
            if scope == "all" or rule.get("session_id", "") == session_id:
                result.append(rule)
        return result

    def list_all_rules(self) -> dict[str, Any]:
        result: dict[str, Any] = {"global": list(self.filters.get("global", []))}
        for ch_name, rules in self.filters.get("channels", {}).items():
            result.setdefault("channels", {})[ch_name] = list(rules)
        return result

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.save()

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def load(self) -> None:
        if not os.path.exists(_CONFIG_FILE):
            return
        try:
            self._last_mtime = os.path.getmtime(_CONFIG_FILE)
            with open(_CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self.enabled = data.get("enabled", True)
            self.filters["global"] = data.get("global", [])
            # 兼容旧格式 groups → channels
            if "channels" in data:
                self.filters["channels"] = data["channels"]
            elif "groups" in data:
                self.filters["channels"] = data["groups"]
            else:
                self.filters["channels"] = {}
            self._compiled_regex.clear()
            ch_count = sum(len(v) for v in self.filters["channels"].values())
            _log.info(
                "[消息过滤] 已加载配置: 全局规则 %d 条, 频道规则 %d 条",
                len(self.filters["global"]),
                ch_count,
            )
        except Exception as e:
            _log.warning("[消息过滤] 加载配置失败: %s", e)

    def save(self) -> None:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        data = {
            "enabled": self.enabled,
            "global": self.filters.get("global", []),
            "channels": self.filters.get("channels", {}),
        }
        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.warning("[消息过滤] 保存配置失败: %s", e)


message_filter = MessageFilter()
