"""
统一的 Token 用量统计管理器。

提供线程安全的用量记录、历史查询、排行榜生成和费用估算。
"""

import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


# 模型定价 ($/M tokens)
_MODEL_PRICING = {
    "claude-opus-4-7": (15.0, 75.0),       # input $15/M, output $75/M
    "claude-opus-4-5": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-3.5-sonnet": (3.0, 15.0),
    "claude-3.5-haiku": (0.80, 4.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.0, 30.0),
    "deepseek-v3": (0.27, 1.10),
    "deepseek-r1": (0.55, 2.19),
}


def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """基于模型定价估算费用（美元）。"""
    input_price, output_price = _MODEL_PRICING.get(model, (1.0, 4.0))
    return (prompt_tokens / 1_000_000) * input_price + (completion_tokens / 1_000_000) * output_price


class TokenStatsManager:
    """线程安全的 Token 用量统计管理器。"""

    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._file_path = os.path.join(data_dir, "token_stats.json")
        self._lock = threading.Lock()
        self._stats: Dict[str, Any] = {
            "today": 0,
            "month": 0,
            "total": 0,
            "estimated_cost": 0.0,
            "history": [],
            "sessions": {},
            "models": {},
            "users": {},
            "records": [],
        }
        self._load()

    # ------------------------------------------------------------------
    # 加载 / 保存
    # ------------------------------------------------------------------

    def _load(self):
        """从磁盘加载统计数据，自动合并同日重复条目。"""
        os.makedirs(self._data_dir, exist_ok=True)
        if not os.path.exists(self._file_path):
            return

        try:
            with open(self._file_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            return

        with self._lock:
            # 合并同日重复条目
            raw_history = saved.get("history", [])
            self._stats["history"] = self._merge_history(raw_history)

            today_str = datetime.now().strftime("%Y-%m-%d")
            last_history_date = self._stats["history"][-1]["date"] if self._stats["history"] else ""

            # today 计数器：如果最后一条历史不是今天，说明跨天了，重置为 0
            if last_history_date != today_str:
                self._stats["today"] = 0
            else:
                self._stats["today"] = saved.get("today", 0)

            # month 同理：检查最后一条历史的月份
            current_month = datetime.now().strftime("%Y-%m")
            last_month = last_history_date[:7] if last_history_date else ""
            if last_month != current_month:
                self._stats["month"] = 0
            else:
                self._stats["month"] = saved.get("month", 0)

            self._stats["total"] = saved.get("total", 0)
            self._stats["estimated_cost"] = float(saved.get("estimated_cost", 0) or 0)
            self._stats["sessions"] = saved.get("sessions", {})
            self._stats["models"] = saved.get("models", {})
            self._stats["users"] = saved.get("users", {})
            records = saved.get("records", [])
            self._stats["records"] = records if isinstance(records, list) else []

    def _save(self):
        """持久化到磁盘（调用前需持有锁）。"""
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self._stats, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _merge_history(history: List[Dict]) -> List[Dict]:
        """将同日多条记录合并为一条，去重防重复。

        旧代码产生的重复条目特征：message_count=0 且 input==output（字符估算）。
        优先保留 message_count>0 的真实 API 记录。
        """
        merged: Dict[str, List[Dict]] = {}
        for entry in history:
            date = entry.get("date", "")
            if not date:
                continue
            if date not in merged:
                merged[date] = []
            merged[date].append(entry)

        result = []
        for date, entries in merged.items():
            # 优先选择 message_count > 0 的条目（真实 API 记录）
            real_entries = [e for e in entries if e.get("message_count", 0) > 0]
            if real_entries:
                # 合并所有真实条目
                combined = {
                    "date": date,
                    "input": sum(e.get("input", 0) for e in real_entries),
                    "output": sum(e.get("output", 0) for e in real_entries),
                    "total": sum(e.get("total", 0) for e in real_entries),
                    "message_count": sum(e.get("message_count", 0) for e in real_entries),
                    "cost": sum(float(e.get("cost", 0) or 0) for e in real_entries),
                }
            else:
                # 没有真实记录则取最大值合并
                combined = {
                    "date": date,
                    "input": max(e.get("input", 0) for e in entries),
                    "output": max(e.get("output", 0) for e in entries),
                    "total": max(e.get("total", 0) for e in entries),
                    "message_count": max(e.get("message_count", 0) for e in entries),
                    "cost": max(float(e.get("cost", 0) or 0) for e in entries),
                }
            result.append(combined)

        return sorted(result, key=lambda x: x["date"])

    @staticmethod
    def _filter_records(
        records: List[Dict],
        date_range: str,
        start_date: str = "",
        end_date: str = "",
    ) -> List[Dict]:
        if start_date or end_date:
            start = start_date or "0000-00-00"
            end = end_date or "9999-99-99"
            return [
                r for r in records
                if start <= (r.get("date") or "") <= end
            ]

        today_str = datetime.now().strftime("%Y-%m-%d")
        if date_range == "today":
            return [r for r in records if r.get("date") == today_str]
        if date_range == "7d":
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            return [r for r in records if (r.get("date") or "") >= cutoff]
        if date_range == "30d":
            cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            return [r for r in records if (r.get("date") or "") >= cutoff]
        return list(records)

    def get_records(
        self,
        date_range: str = "today",
        *,
        start_date: str = "",
        end_date: str = "",
    ) -> List[Dict[str, Any]]:
        """返回指定时间段内的全部明细记录。"""
        with self._lock:
            records = list(self._stats.get("records", []))

        filtered = self._filter_records(records, date_range, start_date, end_date)
        return sorted(filtered, key=lambda item: item.get("timestamp", ""))

    # ------------------------------------------------------------------
    # 记录用量
    # ------------------------------------------------------------------

    def record_usage(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        *,
        total_tokens: Optional[int] = None,
        model: str = "",
        session_id: str = "",
        channel_type: str = "web",
        user_id: str = "",
        source: str = "api",
        duration_ms: Optional[float] = None,
    ):
        """记录一次 AI 调用用量。"""
        try:
            prompt_tokens = max(0, int(prompt_tokens or 0))
            completion_tokens = max(0, int(completion_tokens or 0))
            total_tokens = max(
                0,
                int(
                    total_tokens
                    if total_tokens is not None
                    else prompt_tokens + completion_tokens
                ),
            )
        except (TypeError, ValueError):
            return

        if not total_tokens:
            return

        cost = _estimate_cost(model or "default", prompt_tokens, completion_tokens)
        today_str = datetime.now().strftime("%Y-%m-%d")
        current_month = datetime.now().strftime("%Y-%m")
        timestamp = datetime.now().isoformat(timespec="seconds")

        with self._lock:
            stats = self._stats

            # 跨天/跨月自动重置
            last_date = stats["history"][-1]["date"] if stats["history"] else ""
            if last_date and last_date != today_str:
                stats["today"] = 0
            if last_date and last_date[:7] != current_month:
                stats["month"] = 0
            # 顶层聚合
            stats["today"] = stats.get("today", 0) + total_tokens
            stats["month"] = stats.get("month", 0) + total_tokens
            stats["total"] = stats.get("total", 0) + total_tokens
            stats["estimated_cost"] = float(stats.get("estimated_cost", 0) or 0) + cost

            # 每日历史（查找或创建今天的条目）
            today_entry = None
            for entry in stats["history"]:
                if entry.get("date") == today_str:
                    today_entry = entry
                    break
            if today_entry:
                today_entry["input"] += prompt_tokens
                today_entry["output"] += completion_tokens
                today_entry["total"] += total_tokens
                today_entry["message_count"] = today_entry.get("message_count", 0) + 1
                today_entry["cost"] = (float(today_entry.get("cost", 0) or 0) + cost)
            else:
                stats["history"].append({
                    "date": today_str,
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": total_tokens,
                    "message_count": 1,
                    "cost": cost,
                })

            # 限制历史记录保留 90 天
            if len(stats["history"]) > 90:
                stats["history"] = sorted(stats["history"], key=lambda x: x["date"])[-90:]

            # 会话维度
            if session_id:
                sessions = stats.setdefault("sessions", {})
                if session_id not in sessions:
                    sessions[session_id] = {"input": 0, "output": 0, "total": 0,
                                             "type": channel_type, "message_count": 0}
                s = sessions[session_id]
                s["input"] += prompt_tokens
                s["output"] += completion_tokens
                s["total"] += total_tokens
                s["message_count"] = s.get("message_count", 0) + 1

            # 模型维度
            if model:
                models = stats.setdefault("models", {})
                if model not in models:
                    models[model] = {"input": 0, "output": 0, "total": 0, "message_count": 0, "cost": 0.0}
                m = models[model]
                m["input"] += prompt_tokens
                m["output"] += completion_tokens
                m["total"] += total_tokens
                m["message_count"] = m.get("message_count", 0) + 1
                m["cost"] = float(m.get("cost", 0) or 0) + cost

            # 用户维度
            if user_id:
                users = stats.setdefault("users", {})
                uid = str(user_id)
                if uid not in users:
                    users[uid] = {"input": 0, "output": 0, "total": 0, "message_count": 0}
                u = users[uid]
                u["input"] += prompt_tokens
                u["output"] += completion_tokens
                u["total"] += total_tokens
                u["message_count"] = u.get("message_count", 0) + 1

            record = {
                "id": str(uuid.uuid4()),
                "timestamp": timestamp,
                "date": today_str,
                "model": model or "unknown",
                "session_id": session_id,
                "channel_type": channel_type,
                "user_id": str(user_id or ""),
                "input": prompt_tokens,
                "output": completion_tokens,
                "total": total_tokens,
                "cost": round(cost, 6),
                "source": source or channel_type or "api",
            }
            if duration_ms is not None:
                try:
                    record["duration_ms"] = max(0.0, float(duration_ms))
                except (TypeError, ValueError):
                    pass

            records = stats.setdefault("records", [])
            records.append(record)
            if len(records) > 5000:
                stats["records"] = records[-5000:]

            self._save()

    # ------------------------------------------------------------------
    # 查询统计
    # ------------------------------------------------------------------

    def get_stats(
        self,
        date_range: str = "today",
        *,
        start_date: str = "",
        end_date: str = "",
    ) -> Dict[str, Any]:
        """返回指定时间范围的统计数据。"""
        with self._lock:
            stats = self._stats
            history = list(stats.get("history", []))
            records = list(stats.get("records", []))
            sessions = dict(stats.get("sessions", {}))
            models = dict(stats.get("models", {}))
            users = dict(stats.get("users", {}))

        today_str = datetime.now().strftime("%Y-%m-%d")
        has_custom_range = bool(start_date or end_date)
        records = self._filter_records(records, date_range, start_date, end_date)
        recent_records = sorted(
            records,
            key=lambda item: item.get("timestamp", ""),
            reverse=True,
        )[:100]

        if has_custom_range:
            start = start_date or "0000-00-00"
            end = end_date or "9999-99-99"
            history = [
                h for h in history
                if start <= (h.get("date") or "") <= end
            ]
        elif date_range == "today":
            history = [h for h in history if h.get("date") == today_str]
            # 如果今日无历史记录，使用 today 计数器兜底
            if not history:
                today_val = stats.get("today", 0)
                return {
                    "today": today_val,
                    "month": stats.get("month", 0),
                    "total": stats.get("total", 0),
                    "total_tokens": today_val,
                    "today_input": 0,
                    "today_output": 0,
                    "message_count": 0,
                    "avg_tokens_per_msg": 0,
                    "estimated_cost": f"{float(stats.get('estimated_cost', 0) or 0):.2f}",
                    "active_sessions": len(stats.get("sessions", {})),
                    "avg_response_time": "0",
                    "history": [],
                    "recent_records": recent_records,
                    "records": recent_records,
                    "range_start": today_str,
                    "range_end": today_str,
                    "sessions": sessions,
                    "models": models,
                    "users": users,
                }
        elif date_range == "7d":
            cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            history = [h for h in history if h.get("date", "") >= cutoff]
        elif date_range == "30d":
            cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            history = [h for h in history if h.get("date", "") >= cutoff]

        # 汇总
        total_input = sum(h.get("input", 0) for h in history)
        range_dates = [
            item.get("date")
            for item in [*history, *records]
            if item.get("date")
        ]
        range_start = min(range_dates) if range_dates else (start_date or today_str)
        range_end = max(range_dates) if range_dates else (end_date or today_str)

        total_input = sum(h.get("input", 0) for h in history)
        total_output = sum(h.get("output", 0) for h in history)
        total_tokens = sum(h.get("total", h.get("input", 0) + h.get("output", 0)) for h in history)
        message_count = sum(h.get("message_count", 0) for h in history)
        total_cost = sum(float(h.get("cost", 0) or 0) for h in history)
        durations = []
        for record in records:
            try:
                duration = float(record.get("duration_ms", 0) or 0)
            except (TypeError, ValueError):
                continue
            if duration > 0:
                durations.append(duration)
        avg_response_time = (
            f"{(sum(durations) / len(durations) / 1000):.1f}"
            if durations
            else "0"
        )
        active_session_ids = {
            r.get("session_id")
            for r in records
            if r.get("session_id")
        }
        active_sessions = len(active_session_ids) if active_session_ids else len(sessions)

        return {
            "today": stats.get("today", 0),
            "month": stats.get("month", 0),
            "total": stats.get("total", 0),
            "total_tokens": total_tokens,
            "today_input": total_input,
            "today_output": total_output,
            "message_count": message_count,
            "avg_tokens_per_msg": round(total_tokens / message_count) if message_count > 0 else 0,
            "estimated_cost": f"{total_cost:.2f}",
            "active_sessions": active_sessions,
            "avg_response_time": avg_response_time,
            "history": history,
            "recent_records": recent_records,
            "records": recent_records,
            "range_start": range_start,
            "range_end": range_end,
            "sessions": sessions,
            "models": models,
            "users": users,
        }

    # ------------------------------------------------------------------
    # 排行榜
    # ------------------------------------------------------------------

    def get_rankings(self, limit: int = 10) -> Dict[str, List[Dict]]:
        """返回会话 / 模型 / 用户排行榜。"""
        with self._lock:
            sessions = dict(self._stats.get("sessions", {}))
            models = dict(self._stats.get("models", {}))
            users = dict(self._stats.get("users", {}))

        def _build(items: Dict, name_key: str = None) -> List[Dict]:
            result = []
            for key, val in items.items():
                name = key if name_key is None else val.get(name_key, key)
                entry = {
                    "name": str(name)[:32],
                    "value": val.get("total", 0) if isinstance(val, dict) else val,
                }
                if isinstance(val, dict):
                    entry.update({
                        "input": val.get("input", 0),
                        "output": val.get("output", 0),
                        "message_count": val.get("message_count", 0),
                        "cost": float(val.get("cost", 0) or 0),
                        "type": val.get("type", ""),
                    })
                result.append(entry)
            result.sort(key=lambda x: x["value"], reverse=True)
            return result[:limit]

        return {
            "sessions": _build(sessions),
            "models": _build(models),
            "users": _build(users),
        }

    # ------------------------------------------------------------------
    # 重置
    # ------------------------------------------------------------------

    def reset_daily(self):
        """重置今日计数器（跨天后调用）。"""
        with self._lock:
            self._stats["today"] = 0
            self._save()

    def reset_monthly(self):
        """重置本月计数器（跨月后调用）。"""
        with self._lock:
            self._stats["month"] = 0
            self._save()

    @property
    def data(self) -> Dict[str, Any]:
        """返回原始数据副本。"""
        with self._lock:
            return dict(self._stats)


# ------------------------------------------------------------------
# 单例
# ------------------------------------------------------------------

_instance: Optional[TokenStatsManager] = None


def init_token_stats_manager(data_dir: str) -> TokenStatsManager:
    """初始化单例（服务启动时调用）。"""
    global _instance
    _instance = TokenStatsManager(data_dir)
    return _instance


def get_token_stats_manager() -> TokenStatsManager:
    """获取单例（已在别处初始化）。"""
    global _instance
    if _instance is None:
        raise RuntimeError("TokenStatsManager 未初始化，请先调用 init_token_stats_manager()")
    return _instance
