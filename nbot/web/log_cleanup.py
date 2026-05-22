import logging
import json
import os
import time
from datetime import datetime
from typing import Any, Dict


_log = logging.getLogger(__name__)


DEFAULT_LOG_CLEANUP = {
    "enabled": False,
    "include_logs_dir": True,
    "include_system_logs": False,
    "include_token_stats": False,
    "retention_days": 0,
    "max_size_mb": 0,
    "last_run": None,
    "last_deleted_count": 0,
    "last_deleted_entries": 0,
    "last_freed_bytes": 0,
    "last_error": "",
}


def normalize_log_cleanup_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    cleanup = dict(DEFAULT_LOG_CLEANUP)
    if isinstance(settings.get("log_cleanup"), dict):
        cleanup.update(settings["log_cleanup"])

    cleanup["enabled"] = bool(cleanup.get("enabled"))
    cleanup["include_logs_dir"] = bool(cleanup.get("include_logs_dir", True))
    cleanup["include_system_logs"] = bool(cleanup.get("include_system_logs", False))
    cleanup["include_token_stats"] = bool(cleanup.get("include_token_stats", False))
    cleanup["retention_days"] = _positive_int(cleanup.get("retention_days"))
    cleanup["max_size_mb"] = _positive_int(cleanup.get("max_size_mb"))
    cleanup["last_deleted_count"] = _positive_int(cleanup.get("last_deleted_count"))
    cleanup["last_deleted_entries"] = _positive_int(cleanup.get("last_deleted_entries"))
    cleanup["last_freed_bytes"] = _positive_int(cleanup.get("last_freed_bytes"))
    cleanup["last_error"] = str(cleanup.get("last_error") or "")
    settings["log_cleanup"] = cleanup
    return cleanup


def cleanup_logs_dir(base_dir: str, config: Dict[str, Any]) -> Dict[str, Any]:
    config = normalize_log_cleanup_settings({"log_cleanup": config})
    result = {
        "success": True,
        "enabled": bool(config.get("enabled")),
        "deleted_count": 0,
        "deleted_entries": 0,
        "freed_bytes": 0,
        "remaining_bytes": 0,
        "logs_dir": os.path.abspath(os.path.join(base_dir, "logs")),
        "system_logs": None,
        "token_stats": None,
        "cleaned_targets": [],
        "error": "",
    }

    if not result["enabled"]:
        return result

    try:
        if config.get("include_logs_dir", True):
            _cleanup_logs_directory(result, config)
        data_dir = os.path.abspath(os.path.join(base_dir, "data", "web"))
        if config.get("include_system_logs", False):
            system_result = cleanup_system_logs_file(
                os.path.join(data_dir, "system_logs.json"), config
            )
            _merge_json_result(result, system_result, "system_logs")
        if config.get("include_token_stats", False):
            token_result = cleanup_token_stats_file(
                os.path.join(data_dir, "token_stats.json"), config
            )
            _merge_json_result(result, token_result, "token_stats")
    except Exception as exc:
        result["success"] = False
        result["error"] = str(exc)
        _log.warning("Failed to cleanup logs directory: %s", exc, exc_info=True)

    return result


def cleanup_system_logs_file(path: str, config: Dict[str, Any]) -> Dict[str, Any]:
    result = _json_result(path)
    data = _read_json(path, [])
    if not isinstance(data, list):
        return result

    original = list(data)
    entries = _prune_entries_by_date(
        original,
        config.get("retention_days", 0),
        date_getter=lambda item: _parse_datetime((item or {}).get("time")),
    )
    entries = _trim_entries_to_file_size(
        path,
        entries,
        config.get("max_size_mb", 0),
        date_getter=lambda item: _parse_datetime((item or {}).get("time")),
    )
    return _write_pruned_json(path, original, entries, result)


def cleanup_token_stats_file(path: str, config: Dict[str, Any]) -> Dict[str, Any]:
    result = _json_result(path)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        return result

    original_history = data.get("history") if isinstance(data.get("history"), list) else []
    original_records = data.get("records") if isinstance(data.get("records"), list) else []
    history = _prune_entries_by_date(
        original_history,
        config.get("retention_days", 0),
        date_getter=lambda item: _parse_date((item or {}).get("date")),
    )
    records = _prune_entries_by_date(
        original_records,
        config.get("retention_days", 0),
        date_getter=lambda item: _parse_date((item or {}).get("date")),
    )

    pruned = dict(data)
    pruned["history"] = history
    pruned["records"] = records
    _recalculate_token_totals(pruned)

    max_size_mb = config.get("max_size_mb", 0)
    if max_size_mb > 0:
        max_bytes = max_size_mb * 1024 * 1024
        while _json_size(pruned) > max_bytes and pruned.get("records"):
            pruned["records"] = sorted(
                pruned["records"], key=lambda item: item.get("timestamp") or item.get("date") or ""
            )[1:]
        while _json_size(pruned) > max_bytes and pruned.get("history"):
            pruned["history"] = sorted(pruned["history"], key=lambda item: item.get("date") or "")[1:]
        _recalculate_token_totals(pruned)

    removed = len(original_history) + len(original_records) - len(pruned.get("history", [])) - len(pruned.get("records", []))
    return _write_json_object(path, data, pruned, result, removed)


def _cleanup_logs_directory(result: Dict[str, Any], config: Dict[str, Any]) -> None:
    logs_dir = result["logs_dir"]
    if not os.path.isdir(logs_dir):
        return

    files = _collect_log_files(logs_dir)
    retention_days = config.get("retention_days", 0)
    if retention_days > 0:
        cutoff = time.time() - retention_days * 86400
        for file_info in list(files):
            if file_info["mtime"] < cutoff and _delete_file(file_info):
                result["deleted_count"] += 1
                result["freed_bytes"] += file_info["size"]
                files.remove(file_info)

    max_size_mb = config.get("max_size_mb", 0)
    if max_size_mb > 0:
        max_bytes = max_size_mb * 1024 * 1024
        total_bytes = sum(item["size"] for item in files)
        for file_info in sorted(files, key=lambda item: item["mtime"]):
            if total_bytes <= max_bytes:
                break
            if _delete_file(file_info):
                result["deleted_count"] += 1
                result["freed_bytes"] += file_info["size"]
                total_bytes -= file_info["size"]

    result["remaining_bytes"] = _directory_size(logs_dir)
    result["cleaned_targets"].append("logs_dir")


def _merge_json_result(result: Dict[str, Any], target_result: Dict[str, Any], key: str) -> None:
    result[key] = target_result
    result["deleted_entries"] += target_result.get("deleted_entries", 0)
    result["freed_bytes"] += target_result.get("freed_bytes", 0)
    if target_result.get("changed"):
        result["cleaned_targets"].append(key)
    if not target_result.get("success", True):
        result["success"] = False
        result["error"] = target_result.get("error", "")


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _json_result(path: str) -> Dict[str, Any]:
    return {
        "success": True,
        "changed": False,
        "path": os.path.abspath(path),
        "deleted_entries": 0,
        "freed_bytes": 0,
        "remaining_bytes": os.path.getsize(path) if os.path.exists(path) else 0,
        "data": None,
        "error": "",
    }


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_pruned_json(path: str, original: list, entries: list, result: Dict[str, Any]) -> Dict[str, Any]:
    return _write_json_object(path, original, entries, result, len(original) - len(entries))


def _write_json_object(path: str, original: Any, pruned: Any, result: Dict[str, Any], removed: int) -> Dict[str, Any]:
    if removed <= 0:
        result["data"] = original
        return result
    before_size = os.path.getsize(path) if os.path.exists(path) else 0
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pruned, f, ensure_ascii=False, indent=2)
        after_size = os.path.getsize(path) if os.path.exists(path) else 0
        result.update(
            {
                "changed": True,
                "deleted_entries": removed,
                "freed_bytes": max(0, before_size - after_size),
                "remaining_bytes": after_size,
                "data": pruned,
            }
        )
    except Exception as exc:
        result["success"] = False
        result["error"] = str(exc)
        result["data"] = original
    return result


def _prune_entries_by_date(entries: list, retention_days: int, date_getter) -> list:
    if retention_days <= 0:
        return list(entries)
    cutoff_ts = time.time() - retention_days * 86400
    kept = []
    for entry in entries:
        entry_dt = date_getter(entry)
        if entry_dt is None or entry_dt.timestamp() >= cutoff_ts:
            kept.append(entry)
    return kept


def _trim_entries_to_file_size(path: str, entries: list, max_size_mb: int, date_getter) -> list:
    if max_size_mb <= 0:
        return list(entries)
    max_bytes = max_size_mb * 1024 * 1024
    trimmed = list(entries)
    while trimmed and _json_size(trimmed) > max_bytes:
        sorted_entries = sorted(
            trimmed,
            key=lambda item: (date_getter(item) or datetime.max).timestamp(),
        )
        oldest = sorted_entries[0]
        trimmed.remove(oldest)
    return trimmed


def _json_size(data: Any) -> int:
    return len(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))


def _parse_datetime(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    candidates = (text, text[:19], text[:10])
    for candidate in candidates:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_date(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _recalculate_token_totals(data: Dict[str, Any]) -> None:
    history = data.get("history") if isinstance(data.get("history"), list) else []
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    data["today"] = sum(int(item.get("total", 0) or 0) for item in history if item.get("date") == today)
    data["month"] = sum(int(item.get("total", 0) or 0) for item in history if str(item.get("date", "")).startswith(month))
    data["total"] = sum(int(item.get("total", 0) or 0) for item in history)
    data["estimated_cost"] = sum(float(item.get("cost", 0) or 0) for item in history)


def _collect_log_files(logs_dir: str):
    files = []
    for root, _, filenames in os.walk(logs_dir):
        for filename in filenames:
            path = os.path.abspath(os.path.join(root, filename))
            try:
                stat = os.stat(path)
            except OSError:
                continue
            files.append({"path": path, "mtime": stat.st_mtime, "size": stat.st_size})
    return files


def _delete_file(file_info: Dict[str, Any]) -> bool:
    try:
        os.remove(file_info["path"])
        return True
    except OSError as exc:
        _log.warning("Failed to delete log file %s: %s", file_info.get("path"), exc)
        return False


def _directory_size(logs_dir: str) -> int:
    total = 0
    for root, _, filenames in os.walk(logs_dir):
        for filename in filenames:
            path = os.path.join(root, filename)
            try:
                total += os.path.getsize(path)
            except OSError:
                continue
    return total
