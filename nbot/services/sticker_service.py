"""
基于 nekos.best 的表情包服务

根据角色当前心情（mood）自动匹配对应的二次元表情包图片/GIF，
通过 nekos.best 免费 API 获取随机图片。

配置来源（优先级从高到低）：
  1. data/settings.json 中的 features.sticker / sticker_probability
  2. 环境变量 NBOT_STICKER_ENABLED / NBOT_STICKER_PROBABILITY
  3. 内置默认值
"""

import json
import logging
import os
import random

import requests

_log = logging.getLogger(__name__)

# nekos.best API 基地址
_NEKOS_BASE_URL = "https://nekos.best/api/v2"

# 中文心情 → nekos.best endpoint 映射表
_MOOD_TO_ENDPOINT: dict[str, str] = {
    # 积极情绪
    "开心": "happy",
    "快乐": "happy",
    "高兴": "happy",
    "幸福": "happy",
    "得意": "smile",
    "放松": "smile",
    "微笑": "smile",
    "笑": "laugh",
    "黏人": "happy",
    # 消极情绪
    "生气": "angry",
    "愤怒": "angry",
    "委屈": "cry",
    "伤心": "cry",
    "难过": "cry",
    "哭": "cry",
    "受伤": "cry",
    "沉默": "pout",
    "不安": "shocked",
    "害怕": "shocked",
    "紧张": "shocked",
    # 社交情绪
    "害羞": "blush",
    "脸红": "blush",
    "尴尬": "facepalm",
    "无语": "facepalm",
    # 中性/默认
    "平静": "smile",
    "期待": "smile",
    "感动": "blush",
    "依赖": "blush",
}

# 默认发送概率 (0.0 - 1.0)
_DEFAULT_PROBABILITY = 0.5

# API 请求超时（秒）
_REQUEST_TIMEOUT = 10


def _get_settings_path() -> str:
    """获取 settings.json 的路径"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "data", "web", "settings.json")


def _load_sticker_settings() -> dict:
    """从 settings.json 加载表情包配置，返回 {enabled, probability}"""
    settings_path = _get_settings_path()
    result = {
        "enabled": True,
        "probability": _DEFAULT_PROBABILITY,
    }

    # 从文件读取
    try:
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            features = data.get("features", {}) if isinstance(data, dict) else {}
            if isinstance(features, dict):
                enabled = features.get("sticker")
                if enabled is not None:
                    result["enabled"] = bool(enabled)
            prob = data.get("sticker_probability")
            if prob is not None:
                result["probability"] = max(0.0, min(1.0, float(prob) / 100.0))
    except Exception as e:
        _log.debug("[Sticker] 读取 settings.json 失败: %s", e)

    # 环境变量覆盖
    env_enabled = os.getenv("NBOT_STICKER_ENABLED", "").strip().lower()
    if env_enabled in ("0", "false", "no", "off", "disabled"):
        result["enabled"] = False
    elif env_enabled in ("1", "true", "yes", "on", "enabled"):
        result["enabled"] = True

    env_prob = os.getenv("NBOT_STICKER_PROBABILITY", "").strip()
    if env_prob:
        try:
            result["probability"] = max(0.0, min(1.0, float(env_prob)))
        except (ValueError, TypeError):
            pass

    return result


def is_sticker_enabled() -> bool:
    """判断表情包功能是否已启用（读取设置）"""
    return _load_sticker_settings()["enabled"]


def get_sticker_probability() -> float:
    """获取当前配置的发送概率 (0.0 - 1.0)"""
    return _load_sticker_settings()["probability"]


def get_sticker_for_mood(mood: str) -> dict | None:
    """根据角色心情获取一张随机表情包图片

    Args:
        mood: 角色当前心情中文标签，如「开心」「生气」「害羞」

    Returns:
        成功返回字典 {url, artist_name, source_url, anime_name}，失败返回 None
    """
    if not mood:
        return None

    # 映射到 nekos.best endpoint
    endpoint = _MOOD_TO_ENDPOINT.get(mood)
    if not endpoint:
        _log.debug("[Sticker] 未映射的心情标签: %s，使用默认 smile", mood)
        endpoint = "smile"

    return _fetch_random_sticker(endpoint)


def should_send_sticker(probability: float | None = None) -> bool:
    """判断本轮是否应该发送表情包

    Args:
        probability: 发送概率 (0.0-1.0)，None 则从设置中自动读取
    """
    if probability is None:
        probability = get_sticker_probability()
    return random.random() < probability


def _fetch_random_sticker(endpoint: str) -> dict | None:
    """从 nekos.best API 随机获取一张指定分类的图片

    Args:
        endpoint: nekos.best 的分类名，如 happy、angry、cry 等

    Returns:
        成功返回图片信息字典，失败返回 None
    """
    url = f"{_NEKOS_BASE_URL}/{endpoint}"

    try:
        resp = requests.get(url, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        if not results:
            _log.warning("[Sticker] API 返回空结果: endpoint=%s", endpoint)
            return None

        chosen = random.choice(results)
        image_url = chosen.get("url", "")

        if not image_url:
            _log.warning("[Sticker] 图片 URL 为空: endpoint=%s", endpoint)
            return None

        _log.info(
            "[Sticker] 获取成功: endpoint=%s anime=%s artist=%s",
            endpoint,
            chosen.get("anime_name", "unknown"),
            chosen.get("artist_name", "unknown"),
        )

        return {
            "url": image_url,
            "artist_name": chosen.get("artist_name", ""),
            "source_url": chosen.get("source_url", ""),
            "anime_name": chosen.get("anime_name", ""),
            "endpoint": endpoint,
        }

    except requests.exceptions.Timeout:
        _log.warning("[Sticker] API 请求超时: %s", url)
        return None
    except requests.exceptions.RequestException as e:
        _log.warning("[Sticker] API 请求失败: %s, error=%s", url, e)
        return None
    except Exception as e:
        _log.error("[Sticker] 未知错误: %s", e, exc_info=True)
        return None
