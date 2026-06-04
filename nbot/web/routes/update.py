"""版本更新相关路由"""

import logging
import os
import subprocess
import sys
from pathlib import Path

import requests
from flask import jsonify

from nbot.version import __version__

_log = logging.getLogger(__name__)

# 项目根目录
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])

# GitHub 仓库信息
_GITHUB_REPO = "asukaneko/nekobot"
_GITHUB_API_LATEST = f"https://api.github.com/repos/{_GITHUB_REPO}/releases/latest"
_GITHUB_API_TAGS = f"https://api.github.com/repos/{_GITHUB_REPO}/tags"
_REQUEST_TIMEOUT = 15


def _parse_version(v: str) -> tuple:
    """将版本号字符串解析为可比较的元组，去掉 v 前缀。"""
    v = v.strip().lstrip("v")
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def register_update_routes(app, server):

    @app.route("/api/system/version")
    def get_version():
        """返回当前版本号。"""
        return jsonify({"version": __version__})

    @app.route("/api/system/check-update")
    def check_update():
        """检查 GitHub Releases 是否有新版本。"""
        try:
            current = __version__
            current_tuple = _parse_version(current)

            # 获取最新 release
            resp = requests.get(
                _GITHUB_API_LATEST,
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=_REQUEST_TIMEOUT,
            )

            if resp.status_code == 404:
                # 没有 release，回退到 tags
                return _check_update_from_tags(current, current_tuple)

            resp.raise_for_status()
            data = resp.json()

            latest_tag = data.get("tag_name", "")
            latest_version = latest_tag.lstrip("v")
            latest_tuple = _parse_version(latest_version)

            has_update = latest_tuple > current_tuple

            return jsonify({
                "current_version": current,
                "latest_version": latest_version,
                "latest_tag": latest_tag,
                "has_update": has_update,
                "release_notes": data.get("body", ""),
                "release_url": data.get("html_url", ""),
                "published_at": data.get("published_at", ""),
            })

        except requests.RequestException as e:
            _log.warning(f"检查更新失败 (GitHub API 不可达): {e}")
            return jsonify({
                "current_version": __version__,
                "has_update": False,
                "error": f"无法连接 GitHub: {e}",
            })
        except Exception as e:
            _log.error(f"检查更新时发生错误: {e}", exc_info=True)
            return jsonify({
                "current_version": __version__,
                "has_update": False,
                "error": str(e),
            })

    def _check_update_from_tags(current: str, current_tuple: tuple):
        """当没有 release 时，通过 tags 检查更新。"""
        try:
            resp = requests.get(
                _GITHUB_API_TAGS,
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            tags = resp.json()

            if not tags:
                return jsonify({
                    "current_version": current,
                    "has_update": False,
                    "error": "未找到任何版本标签",
                })

            latest_tag = tags[0].get("name", "")
            latest_version = latest_tag.lstrip("v")
            latest_tuple = _parse_version(latest_version)
            has_update = latest_tuple > current_tuple

            return jsonify({
                "current_version": current,
                "latest_version": latest_version,
                "latest_tag": latest_tag,
                "has_update": has_update,
                "release_notes": "",
                "release_url": f"https://github.com/{_GITHUB_REPO}/releases/tag/{latest_tag}",
                "published_at": "",
            })
        except Exception as e:
            _log.warning(f"通过 tags 检查更新也失败: {e}")
            return jsonify({
                "current_version": current,
                "has_update": False,
                "error": f"检查更新失败: {e}",
            })

    @app.route("/api/system/do-update", methods=["POST"])
    def do_update():
        """执行 git pull 拉取最新代码。"""
        try:
            server.log_message("info", "开始执行版本更新...", important=True)

            # 执行 git pull
            result = subprocess.run(
                ["git", "pull", "origin", "master"],
                cwd=_PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                shell=False,
            )

            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            if result.returncode != 0:
                _log.error(f"git pull 失败: {stderr}")
                server.log_message("error", f"版本更新失败: {stderr}", important=True)
                return jsonify({
                    "success": False,
                    "error": stderr or "git pull 执行失败",
                    "stdout": stdout,
                }), 500

            # 检查是否有实际更新
            already_up_to_date = "Already up to date" in stdout or "已经是最新的" in stdout

            if already_up_to_date:
                server.log_message("info", "版本更新检查：代码已是最新")
                return jsonify({
                    "success": True,
                    "message": "代码已是最新版本",
                    "stdout": stdout,
                    "needs_restart": False,
                })

            # 尝试安装新依赖
            pip_result = None
            requirements_path = os.path.join(_PROJECT_ROOT, "requirements.txt")
            if os.path.exists(requirements_path):
                try:
                    pip_result = subprocess.run(
                        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-q"],
                        cwd=_PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=300,
                        shell=False,
                    )
                    if pip_result.returncode != 0:
                        _log.warning(f"pip install 警告: {pip_result.stderr}")
                except subprocess.TimeoutExpired:
                    _log.warning("pip install 超时，跳过依赖安装")
                except Exception as pip_e:
                    _log.warning(f"pip install 失败: {pip_e}")

            # 重新读取版本号
            new_version = __version__
            try:
                import importlib
                import nbot.version
                importlib.reload(nbot.version)
                new_version = nbot.version.__version__
            except Exception:
                pass

            server.log_message("info", f"版本更新完成，当前版本: {new_version}，请重启服务", important=True)

            return jsonify({
                "success": True,
                "message": "代码已更新，请重启服务以生效",
                "stdout": stdout,
                "new_version": new_version,
                "needs_restart": True,
            })

        except subprocess.TimeoutExpired:
            _log.error("git pull 超时")
            server.log_message("error", "版本更新超时", important=True)
            return jsonify({
                "success": False,
                "error": "git pull 执行超时（120秒）",
            }), 500
        except FileNotFoundError:
            _log.error("git 命令不可用")
            return jsonify({
                "success": False,
                "error": "系统未安装 git，请先安装 git 后再试",
            }), 500
        except Exception as e:
            _log.error(f"执行更新时发生错误: {e}", exc_info=True)
            server.log_message("error", f"版本更新异常: {e}", important=True)
            return jsonify({
                "success": False,
                "error": str(e),
            }), 500

    @app.route("/api/system/restart", methods=["POST"])
    def restart_service():
        """重启服务进程。"""
        try:
            server.log_message("info", "正在重启服务...", important=True)

            # 延迟重启，让响应先返回
            import threading

            def _do_restart():
                import time
                time.sleep(1)
                os.execv(sys.executable, [sys.executable] + sys.argv)

            threading.Thread(target=_do_restart, daemon=True).start()

            return jsonify({
                "success": True,
                "message": "服务正在重启...",
            })
        except Exception as e:
            _log.error(f"重启服务失败: {e}", exc_info=True)
            return jsonify({
                "success": False,
                "error": str(e),
            }), 500
