"""Helpers for code update and restart workflows."""

from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

RUNTIME_PATHS = {
    ".env",
    "config.ini",
    "data",
    "logs",
    "cache",
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
}


@dataclass
class ZipUpdateResult:
    changed_files: int
    source_root: str


def _parse_version_tuple(version: str) -> tuple[int, ...]:
    version = (version or "").strip().lstrip("v")
    parts = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def read_version_from_disk(project_root: str | Path) -> str:
    """Read nbot/version.py without using the already-imported module cache."""
    version_path = Path(project_root) / "nbot" / "version.py"
    try:
        tree = ast.parse(version_path.read_text(encoding="utf-8"))
    except OSError:
        return "unknown"

    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        has_version_target = any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
        if not has_version_target:
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            return node.value.value
    return "unknown"


def _update_state_path(project_root: str | Path) -> Path:
    return Path(project_root) / "data" / "web" / "update_state.json"


def read_update_state(project_root: str | Path) -> dict:
    state_path = _update_state_path(project_root)
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_update_state(
    project_root: str | Path,
    installed_version: str,
    method: str = "",
    tag: str = "",
) -> Path:
    state_path = _update_state_path(project_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "installed_version": installed_version.strip().lstrip("v"),
        "method": method,
        "tag": tag,
        "updated_at": datetime.now().isoformat(),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state_path


def resolve_display_version(project_root: str | Path) -> dict:
    code_version = read_version_from_disk(project_root)
    state = read_update_state(project_root)
    installed_version = str(state.get("installed_version") or "").strip().lstrip("v")

    display_version = code_version
    installed_is_newer = (
        installed_version
        and _parse_version_tuple(installed_version) > _parse_version_tuple(code_version)
    )
    if installed_is_newer:
        display_version = installed_version

    return {
        "version": display_version,
        "code_version": code_version,
        "installed_version": installed_version,
        "update_method": state.get("method", ""),
        "update_tag": state.get("tag", ""),
        "updated_at": state.get("updated_at", ""),
    }


def _is_runtime_path(relative_path: Path) -> bool:
    parts = relative_path.parts
    return bool(parts and parts[0] in RUNTIME_PATHS)


def create_update_backup(project_root: str | Path, backup_dir: str | Path | None = None) -> Path:
    root = Path(project_root)
    if backup_dir is None:
        backup_root = root / "data" / "backups"
    else:
        backup_root = Path(backup_dir)
    backup_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_root / f"update-{timestamp}.zip"

    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(root)
            if _is_runtime_path(relative):
                continue
            zf.write(path, relative.as_posix())

    return backup_path


def _find_source_root(extract_dir: Path) -> Path:
    children = [child for child in extract_dir.iterdir() if child.is_dir()]
    if len(children) == 1 and (children[0] / "nbot").exists():
        return children[0]
    if (extract_dir / "nbot").exists():
        return extract_dir
    raise ValueError("更新包格式不正确：未找到 nbot 目录")


def apply_source_zip(zip_path: str | Path, project_root: str | Path) -> ZipUpdateResult:
    root = Path(project_root)
    archive = Path(zip_path)
    changed_files = 0

    with tempfile.TemporaryDirectory(prefix="nbot-update-") as tmp:
        extract_dir = Path(tmp)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

        source_root = _find_source_root(extract_dir)
        for src in source_root.rglob("*"):
            if not src.is_file():
                continue
            relative = src.relative_to(source_root)
            if _is_runtime_path(relative):
                continue

            dst = root / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            changed_files += 1

        return ZipUpdateResult(changed_files=changed_files, source_root=source_root.name)


def build_restart_launcher_command(
    project_root: str | Path,
    python_executable: str,
    current_pid: int,
    argv: list[str],
) -> list[str]:
    launcher = Path(project_root) / "tools" / "restart_launcher.py"
    return [
        python_executable,
        str(launcher),
        "--pid",
        str(current_pid),
        "--",
        python_executable,
        *argv,
    ]


def request_restart(project_root: str | Path, delay_seconds: float = 1.0) -> str:
    """Restart through a supervisor when available, otherwise via a detached launcher."""
    if os.getenv("NBOT_SUPERVISED") == "1":
        _exit_later(delay_seconds)
        return "supervisor"

    command = build_restart_launcher_command(
        project_root=project_root,
        python_executable=sys.executable,
        current_pid=os.getpid(),
        argv=sys.argv,
    )
    subprocess.Popen(
        command,
        cwd=str(project_root),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=os.name != "nt",
    )
    _exit_later(delay_seconds)
    return "launcher"


def _exit_later(delay_seconds: float) -> None:
    import threading
    import time

    def _exit_later() -> None:
        time.sleep(delay_seconds)
        os._exit(0)

    threading.Thread(target=_exit_later, daemon=True).start()
