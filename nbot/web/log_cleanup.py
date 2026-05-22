import logging
import os
import time
from typing import Any, Dict


_log = logging.getLogger(__name__)


DEFAULT_LOG_CLEANUP = {
    "enabled": False,
    "retention_days": 0,
    "max_size_mb": 0,
    "last_run": None,
    "last_deleted_count": 0,
    "last_freed_bytes": 0,
    "last_error": "",
}


def normalize_log_cleanup_settings(settings: Dict[str, Any]) -> Dict[str, Any]:
    cleanup = dict(DEFAULT_LOG_CLEANUP)
    if isinstance(settings.get("log_cleanup"), dict):
        cleanup.update(settings["log_cleanup"])

    cleanup["enabled"] = bool(cleanup.get("enabled"))
    cleanup["retention_days"] = _positive_int(cleanup.get("retention_days"))
    cleanup["max_size_mb"] = _positive_int(cleanup.get("max_size_mb"))
    cleanup["last_deleted_count"] = _positive_int(cleanup.get("last_deleted_count"))
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
        "freed_bytes": 0,
        "remaining_bytes": 0,
        "logs_dir": os.path.abspath(os.path.join(base_dir, "logs")),
        "error": "",
    }

    if not result["enabled"]:
        return result

    logs_dir = result["logs_dir"]
    if not os.path.isdir(logs_dir):
        return result

    try:
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
    except Exception as exc:
        result["success"] = False
        result["error"] = str(exc)
        _log.warning("Failed to cleanup logs directory: %s", exc, exc_info=True)

    return result


def _positive_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
