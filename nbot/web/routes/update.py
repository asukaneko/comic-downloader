"""Version update related routes."""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from flask import jsonify

from nbot.web.update_service import (
    apply_source_zip,
    create_update_backup,
    request_restart,
    resolve_display_version,
    write_update_state,
)

_log = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_GITHUB_REPO = "asukaneko/nekobot"
_GITHUB_API_LATEST = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
_GITHUB_API_TAGS = f"https://api.github.com/repos/{_GITHUB_REPO}/tags"
_GITHUB_ZIPBALL = f"https://github.com/{_GITHUB_REPO}/archive/refs/tags/{{tag}}.zip"
_REQUEST_TIMEOUT = 15


def _parse_version(v: str) -> tuple:
    v = v.strip().lstrip("v")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def _current_version() -> str:
    return resolve_display_version(_PROJECT_ROOT)["version"]


def _current_version_payload() -> dict:
    return resolve_display_version(_PROJECT_ROOT)


def _download_zip(url: str, target: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        with target.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 128):
                if chunk:
                    f.write(chunk)


def _latest_update_info() -> dict:
    resp = requests.get(
        _GITHUB_API_LATEST,
        headers={"Accept": "application/vnd.github.v3+json"},
        timeout=_REQUEST_TIMEOUT,
    )

    if resp.status_code != 404:
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        return {
            "latest_tag": tag,
            "latest_version": tag.lstrip("v"),
            "release_notes": data.get("body", ""),
            "release_url": data.get("html_url", ""),
            "published_at": data.get("published_at", ""),
            "zipball_url": data.get("zipball_url") or _GITHUB_ZIPBALL.format(tag=tag),
        }

    tags_resp = requests.get(
        _GITHUB_API_TAGS,
        headers={"Accept": "application/vnd.github.v3+json"},
        timeout=_REQUEST_TIMEOUT,
    )
    tags_resp.raise_for_status()
    tags = tags_resp.json()
    if not tags:
        raise RuntimeError("未找到任何版本标签")

    tag = tags[0].get("name", "")
    return {
        "latest_tag": tag,
        "latest_version": tag.lstrip("v"),
        "release_notes": "",
        "release_url": f"https://github.com/{_GITHUB_REPO}/releases/tag/{tag}",
        "published_at": "",
        "zipball_url": _GITHUB_ZIPBALL.format(tag=tag),
    }


def _install_requirements(server) -> str:
    requirements_path = _PROJECT_ROOT / "requirements.txt"
    if not requirements_path.exists():
        return ""

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        _log.warning("pip install timed out, skipping dependency update")
        return "pip install 超时，已跳过依赖安装"
    except Exception as exc:
        _log.warning("pip install failed: %s", exc)
        return f"pip install 失败：{exc}"

    if result.returncode != 0:
        warning = result.stderr.strip() or "pip install 执行失败"
        _log.warning("pip install warning: %s", warning)
        server.log_message("warning", f"依赖安装警告：{warning}", important=True)
        return warning
    return ""


def _run_git_update(server) -> dict | None:
    if not (_PROJECT_ROOT / ".git").exists():
        return None

    try:
        result = subprocess.run(
            ["git", "pull", "origin", "master"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
            shell=False,
        )
    except FileNotFoundError:
        return None

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        raise RuntimeError(stderr or "git pull 执行失败")

    already_up_to_date = "Already up to date" in stdout or "已经是最新" in stdout
    if already_up_to_date:
        server.log_message("info", "版本更新检查：代码已经是最新", important=True)
        return {
            "updated": False,
            "message": "代码已经是最新版本",
            "stdout": stdout,
            "method": "git",
        }

    return {
        "updated": True,
        "message": "代码已通过 git 更新",
        "stdout": stdout,
        "method": "git",
    }


def _run_zip_update(server) -> dict:
    info = _latest_update_info()
    zip_url = info.get("zipball_url")
    if not zip_url:
        raise RuntimeError("未找到可下载的更新包")

    backup_path = create_update_backup(_PROJECT_ROOT)
    server.log_message("info", f"已创建更新前备份：{backup_path}", important=True)

    with tempfile.TemporaryDirectory(prefix="nbot-update-download-") as tmp:
        archive = Path(tmp) / "source.zip"
        _download_zip(zip_url, archive)
        result = apply_source_zip(archive, _PROJECT_ROOT)

    return {
        "updated": result.changed_files > 0,
        "message": f"代码已通过 zip 更新，共覆盖 {result.changed_files} 个文件",
        "stdout": "",
        "method": "zip",
        "latest_version": info.get("latest_version", ""),
        "backup_path": str(backup_path),
    }


def register_update_routes(app, server):
    @app.route("/api/system/version")
    def get_version():
        return jsonify(_current_version_payload())

    @app.route("/api/system/check-update")
    def check_update():
        try:
            current = _current_version()
            info = _latest_update_info()
            latest_version = info.get("latest_version", "")
            has_update = _parse_version(latest_version) > _parse_version(current)

            return jsonify({
                "current_version": current,
                "latest_version": latest_version,
                "latest_tag": info.get("latest_tag", ""),
                "has_update": has_update,
                "release_notes": info.get("release_notes", ""),
                "release_url": info.get("release_url", ""),
                "published_at": info.get("published_at", ""),
                "can_zip_update": bool(info.get("zipball_url")),
            })
        except requests.RequestException as exc:
            _log.warning("检查更新失败，GitHub API 不可达: %s", exc)
            return jsonify({
                "current_version": _current_version(),
                "has_update": False,
                "error": f"无法连接 GitHub: {exc}",
            })
        except Exception as exc:
            _log.error("检查更新时发生错误: %s", exc, exc_info=True)
            return jsonify({
                "current_version": _current_version(),
                "has_update": False,
                "error": str(exc),
            })

    @app.route("/api/system/do-update", methods=["POST"])
    def do_update():
        try:
            server.log_message("info", "开始执行版本更新...", important=True)

            try:
                update_result = _run_git_update(server)
            except Exception as git_exc:
                _log.error("git 更新失败: %s", git_exc)
                server.log_message("error", f"git 更新失败：{git_exc}", important=True)
                raise

            if update_result is None:
                server.log_message("info", "git 不可用，切换到 GitHub zip 更新", important=True)
                update_result = _run_zip_update(server)

            if not update_result["updated"]:
                try:
                    info = _latest_update_info()
                    latest_version = info.get("latest_version", "")
                    if latest_version:
                        write_update_state(
                            _PROJECT_ROOT,
                            installed_version=latest_version,
                            method=update_result.get("method", ""),
                            tag=info.get("latest_tag", ""),
                        )
                except Exception as state_exc:
                    _log.warning("记录已安装版本失败: %s", state_exc)

                return jsonify({
                    "success": True,
                    "message": update_result["message"],
                    "stdout": update_result.get("stdout", ""),
                    "method": update_result.get("method", ""),
                    "new_version": _current_version(),
                    "needs_restart": False,
                })

            pip_warning = _install_requirements(server)
            installed_version = update_result.get("latest_version", "")
            installed_tag = ""
            if not installed_version:
                try:
                    info = _latest_update_info()
                    installed_version = info.get("latest_version", "")
                    installed_tag = info.get("latest_tag", "")
                except Exception as state_exc:
                    _log.warning("获取最新版本用于状态记录失败: %s", state_exc)
            else:
                installed_tag = f"v{installed_version}"
            if installed_version:
                write_update_state(
                    _PROJECT_ROOT,
                    installed_version=installed_version,
                    method=update_result.get("method", ""),
                    tag=installed_tag,
                )
            new_version = resolve_display_version(_PROJECT_ROOT)["version"]
            message = "代码已更新，请重启服务以生效"
            if pip_warning:
                message += f"；依赖安装提示：{pip_warning}"

            server.log_message(
                "info",
                f"版本更新完成，当前磁盘版本：{new_version}，请重启服务",
                important=True,
            )

            return jsonify({
                "success": True,
                "message": message,
                "stdout": update_result.get("stdout", ""),
                "method": update_result.get("method", ""),
                "new_version": new_version,
                "backup_path": update_result.get("backup_path", ""),
                "needs_restart": True,
            })
        except subprocess.TimeoutExpired:
            _log.error("git pull 超时")
            server.log_message("error", "版本更新超时", important=True)
            return jsonify({"success": False, "error": "git pull 执行超时（120 秒）"}), 500
        except Exception as exc:
            _log.error("执行更新时发生错误: %s", exc, exc_info=True)
            server.log_message("error", f"版本更新异常：{exc}", important=True)
            return jsonify({"success": False, "error": str(exc)}), 500

    @app.route("/api/system/restart", methods=["POST"])
    def restart_service():
        try:
            server.log_message("info", "正在重启服务...", important=True)
            method = request_restart(_PROJECT_ROOT)
            return jsonify({
                "success": True,
                "message": "服务正在重启...",
                "method": method,
            })
        except Exception as exc:
            _log.error("重启服务失败: %s", exc, exc_info=True)
            return jsonify({"success": False, "error": str(exc)}), 500
