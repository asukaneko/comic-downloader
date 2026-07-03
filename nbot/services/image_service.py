"""
图片生成服务

封装图片生成 API 调用，支持 OpenAI 兼容 / SiliconFlow / 自定义协议。
供以下场景共用：
  1. 角色立绘生成（routes/personality.py）
  2. 角色对话中按需生图（core/ai_pipeline.py 后处理 _try_send_image）

配置来源（优先级从高到低）：
  1. 调用方传入的 image_gen_config 字典
  2. WebChatServer.active_models_by_purpose['image_generation'] 当前选中的模型
  3. data/web/ai_models.json 中 purpose == "image_generation" 的第一个启用模型
  4. 内置默认值
"""

import base64
import json
import logging
import os
import random
import re
import time
import uuid

import requests

_log = logging.getLogger(__name__)

# API 超时（秒），生图通常较慢
_API_TIMEOUT = 300

# 默认图片大小
_DEFAULT_SIZE = "1024x1024"

# 内联标签正则：匹配 [send_image: ...] 风格
SEND_IMAGE_TAG_PATTERN = re.compile(
    r"\[send_image\s*:\s*([^\]]+?)\s*\]",
    re.IGNORECASE,
)


def get_image_generation_config() -> dict | None:
    """从 ai_models.json 加载当前选中的图片生成模型配置。

    优先使用 WebChatServer 中 active_models_by_purpose['image_generation']
    标记的"当前选中"模型；找不到时回退到第一个启用的 image_generation 模型。

    Returns:
        配置字典，未找到返回 None。
    """
    try:
        from nbot.web.server import WebChatServer

        server = WebChatServer.get_instance()
        if server is not None:
            config = get_image_generation_config_from_server(server)
            if config:
                return config
    except Exception as exc:
        _log.debug("[ImageService] 从 server 读取图片生成配置失败，回退: %s", exc)

    try:
        from nbot.web.utils.config_loader import get_model_config_by_purpose

        return get_model_config_by_purpose("image_generation")
    except Exception as exc:
        _log.debug("[ImageService] 加载图片生成配置失败: %s", exc)
        return None


def get_image_generation_config_from_server(server) -> dict | None:
    """从 WebChatServer 的 active_models_by_purpose 中获取当前选中的图片生成模型配置。

    Args:
        server: WebChatServer 实例。

    Returns:
        标准化后的配置字典，未找到返回 None。
    """
    if server is None:
        return None

    active_id = (getattr(server, "active_models_by_purpose", {}) or {}).get(
        "image_generation"
    )
    if not active_id:
        return None

    for model in getattr(server, "ai_models", []) or []:
        if model.get("id") == active_id and model.get("enabled", True):
            return _build_image_generation_config(model)

    return None


def _build_image_generation_config(model: dict) -> dict:
    """将原始模型字典标准化为图片生成调用所需的配置。"""
    from nbot.web.utils.config_loader import resolve_runtime_api_key

    provider_type = model.get("provider_type", "openai_compatible")
    return {
        "api_key": resolve_runtime_api_key(model.get("api_key", ""), provider_type),
        "base_url": model.get("base_url", ""),
        "model": model.get("model", ""),
        "provider_type": provider_type,
        "provider": model.get("provider", "custom"),
        "append_base_url_path": model.get("append_base_url_path", True),
        "size": model.get("size", ""),
    }


def is_image_generation_enabled() -> bool:
    """检查是否配置了可用的图片生成模型。"""
    config = get_image_generation_config()
    if not config:
        return False
    return bool(config.get("api_key") and config.get("base_url") and config.get("model"))


def _is_volces_ark_provider(provider_type: str = "", base_url: str = "") -> bool:
    """判断 provider 是否为火山引擎 ark（豆包）图片生成服务。

    火山引擎对图片 size 有像素数下限（≥ 3,686,400，约 1920x1920），
    需要把过小的尺寸自动放大。
    """
    pt = (provider_type or "").strip().lower()
    if pt in ("volces", "ark", "doubao", "volcengine"):
        return True
    url = (base_url or "").lower()
    return "volces.com" in url or "ark.cn-beijing" in url


def _resolve_size(size: str, provider_type: str = "", base_url: str = "") -> str:
    """处理火山引擎 ark 的 size 下限要求（≥ 3,686,400 像素）。

    此前实现误把判断逻辑写在 size 字符串里（"volces" in size.lower()），
    导致永远命中不到——size 只可能是 "1024x1024" 这种格式。
    修复后改为通过 provider_type / base_url 识别火山引擎。
    """
    if not _is_volces_ark_provider(provider_type, base_url):
        return size
    try:
        width, height = size.split("x")
        pixels = int(width) * int(height)
        if pixels < 3686400:
            return "1920x1920"
    except (ValueError, AttributeError):
        pass
    return size


def _extract_image_url(result: dict, provider_type: str) -> str | None:
    """从图片生成 API 响应中提取图片 URL 或 base64。

    支持的返回结构：
      - OpenAI 标准：{"data": [{"url": "..."} | {"b64_json": "..."}]}
      - 火山 ark：{"data": [{"url": "..."}]}
      - SiliconFlow：{"images": [{"url": "..."}]}
      - 自定义文本格式：{"choices": [{"message": {"content": "..."}}]}
        其中 content 可能是 markdown 图片、http URL 或 base64 data URI
    """
    data_list = result.get("data") or []
    if data_list:
        item = data_list[0] if isinstance(data_list[0], dict) else {}
        url = item.get("url") or item.get("b64_json")
        if url:
            return url

    choices = result.get("choices") or []
    if choices:
        content = (
            choices[0].get("message", {}).get("content", "")
            if isinstance(choices[0], dict)
            else ""
        )
        if content:
            md_match = re.search(r"!\[.*?\]\((https?://\S+)\)", content)
            if md_match:
                return md_match.group(1)
            content = content.strip()
            if content.startswith("http") or content.startswith("data:"):
                return content
            if content and len(content) > 100:
                return content

    images = result.get("images") or []
    if images and isinstance(images[0], dict):
        return images[0].get("url")

    return None


def call_image_generation(
    prompt: str,
    config: dict,
    *,
    size: str = "",
    extra_keywords: list[str] | None = None,
) -> str | None:
    """调用图片生成 API，返回图片 URL 或 base64 data URI。

    Args:
        prompt: 英文图片描述 prompt。
        config: 模型配置，至少含 api_key/base_url/model/provider_type。
        size: 图片尺寸，如 "1024x1024"，为空使用配置或默认。
        extra_keywords: 附加到 prompt 末尾的关键词列表。

    Returns:
        成功返回图片 URL/base64，失败返回 None。
    """
    if not config:
        _log.warning("[ImageService] 缺少图片生成配置")
        return None

    api_key = config.get("api_key", "")
    full_url = config.get("base_url", "")
    model = config.get("model", "dall-e-3")
    provider_type = config.get("provider_type", "openai_compatible")
    image_size = size or config.get("size", "") or _DEFAULT_SIZE

    if not api_key or not full_url:
        _log.warning("[ImageService] api_key 或 base_url 未配置")
        return None

    if not prompt or not prompt.strip():
        _log.warning("[ImageService] prompt 为空")
        return None

    image_size = _resolve_size(image_size, provider_type=provider_type, base_url=full_url)
    full_prompt = prompt.strip()
    if extra_keywords:
        full_prompt = f"{full_prompt}. {' '.join(extra_keywords)}"

    try:
        if provider_type in ("openai_compatible", "openai") or "openai" in full_url.lower():
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "prompt": full_prompt,
                "n": 1,
                "size": image_size,
            }
            response = requests.post(
                full_url, headers=headers, json=payload, timeout=_API_TIMEOUT
            )
            if response.status_code != 200:
                _log.error("[ImageService] API 错误 %d: %s", response.status_code, response.text[:300])
                return None
            result = response.json()
            return _extract_image_url(result, provider_type)

        if provider_type == "siliconflow" or "siliconflow" in full_url.lower():
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "prompt": full_prompt,
                "image_size": image_size,
                "batch_size": 1,
            }
            response = requests.post(
                full_url, headers=headers, json=payload, timeout=_API_TIMEOUT
            )
            if response.status_code != 200:
                _log.error("[ImageService] API 错误 %d: %s", response.status_code, response.text[:300])
                return None
            result = response.json()
            return _extract_image_url(result, provider_type)

        # 兜底：通用 OpenAI 格式
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "prompt": full_prompt,
            "n": 1,
            "size": image_size,
        }
        response = requests.post(
            full_url, headers=headers, json=payload, timeout=_API_TIMEOUT
        )
        if response.status_code != 200:
            _log.error("[ImageService] API 错误 %d: %s", response.status_code, response.text[:300])
            return None
        result = response.json()
        url_or_b64 = result.get("data", [{}])[0].get("url") or result.get("images", [{}])[0].get("url")
        return url_or_b64
    except requests.exceptions.Timeout:
        _log.warning("[ImageService] 图片生成请求超时")
        return None
    except Exception as exc:
        _log.error("[ImageService] 调用失败: %s", exc, exc_info=True)
        return None


def save_image_to_uploads(
    image_url_or_b64: str,
    upload_dir: str,
    *,
    prefix: str = "image",
) -> str | None:
    """将图片（URL 或 base64）下载到本地 uploads 目录，返回公开路径。

    Args:
        image_url_or_b64: API 返回的图片 URL 或 data URI 或裸 base64。
        upload_dir: 绝对路径，如 /path/to/nbot/web/static/uploads/character_images。
        prefix: 文件名前缀。

    Returns:
        相对 URL（如 "/static/uploads/.../xxx.png"），失败返回 None。
    """
    if not image_url_or_b64:
        return None

    try:
        os.makedirs(upload_dir, exist_ok=True)

        filename = f"{prefix}_{int(time.time())}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(upload_dir, filename)

        if image_url_or_b64.startswith("data:"):
            image_bytes = base64.b64decode(image_url_or_b64.split(",", 1)[1])
            with open(filepath, "wb") as f:
                f.write(image_bytes)
        elif image_url_or_b64.startswith("http"):
            response = requests.get(image_url_or_b64, timeout=120)
            if response.status_code != 200:
                _log.error("[ImageService] 下载图片失败 %d", response.status_code)
                return None
            with open(filepath, "wb") as f:
                f.write(response.content)
        else:
            # 尝试当作裸 base64
            try:
                image_bytes = base64.b64decode(image_url_or_b64)
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
            except Exception:
                _log.error("[ImageService] 无法识别的图片数据格式")
                return None

        # 计算相对于 static 的 URL 路径
        upload_dir_norm = os.path.normpath(upload_dir)
        static_root = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "web", "static")
        )
        if upload_dir_norm.startswith(static_root):
            rel = os.path.relpath(upload_dir_norm, static_root)
            return f"/static/{rel.replace(os.sep, '/')}/{filename}"
        # 兜底：仅返回文件名（外层自行包装）
        return filename
    except Exception as exc:
        _log.error("[ImageService] 保存图片失败: %s", exc, exc_info=True)
        return None


# ----------------------------------------------------------------------------
# PromptStack 注入：向角色 system prompt 注册"主动发图"能力说明
# ----------------------------------------------------------------------------

# 注入项 key（与 nbot.character.prompt_stack._DYNAMIC_SECTION_KEYS 保持一致）
IMAGE_CAPABILITY_KEY = "character.image_capability"

# 注入项优先级：紧跟 character.runtime_state(40) 之后
IMAGE_CAPABILITY_PRIORITY = 42

# 注入项内容
IMAGE_CAPABILITY_CONTENT = (
    "\n【主动发图能力】\n"
    "你可以选择性地在回复中插入图片发送给用户。\n"
    "方法：在回复文本任意位置添加 [send_image: <英文画面描述>] 标签。\n"
    "规则：\n"
    "1. 仅在用户明确要求看图，或当前情境非常适合用画面表达时使用。\n"
    "2. prompt 使用英文画面描述（场景、风格、构图），不超过 60 词。\n"
    "3. 标签会从最终展示文本中移除，用户只会看到一张图片。\n"
    "4. 每轮最多 1 个标签，避免打扰用户。\n"
    "5. 切勿滥用——只有真正能增强表达时才发图。\n"
    "示例：用户说「想看你做饭的样子」→ 你可以回复 "
    "\"好呀~ [send_image: anime girl cooking in cozy kitchen, "
    "warm lighting, soft smile, upper body shot]\""
)


def build_image_capability_injection(stack) -> bool:
    """向 PromptStack 注册"主动发图"能力说明。

    满足以下全部条件时注册成功：
      1. settings.json 中 features.image_generation 为 True；
      2. ai_models.json 中已配置 purpose == "image_generation" 的可用模型；
      3. 当前非 agent 会话模式（由调用方在调用前检查）。

    Args:
        stack: nbot.character.prompt_stack.PromptStack 实例。

    Returns:
        注入成功返回 True，跳过返回 False。
    """
    if not is_image_generation_feature_enabled():
        return False
    if not is_image_generation_enabled():
        return False

    stack.add(
        key=IMAGE_CAPABILITY_KEY,
        content=IMAGE_CAPABILITY_CONTENT,
        priority=IMAGE_CAPABILITY_PRIORITY,
        scope="turn",
    )
    return True


# ----------------------------------------------------------------------------
# 内联标签解析：用于从 LLM 回复中提取 [send_image: ...] 触发器
# ----------------------------------------------------------------------------


def extract_send_image_tags(content: str) -> tuple[str, list[str]]:
    """从 LLM 回复文本中提取 [send_image: <prompt>] 标签。

    Args:
        content: LLM 原始回复。

    Returns:
        (清理后的文本, prompt 列表)。所有标签会被从文本中移除，
        返回的列表保持原顺序、去重。
    """
    if not content:
        return content or "", []

    prompts: list[str] = []
    seen = set()

    def _replace(match: re.Match) -> str:
        prompt = match.group(1).strip()
        if prompt and prompt not in seen:
            seen.add(prompt)
            prompts.append(prompt)
        return ""

    cleaned = SEND_IMAGE_TAG_PATTERN.sub(_replace, content)
    # 顺手清理多余空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, prompts


def should_send_image_probability(probability: float | None = None) -> bool:
    """按概率判断本轮是否应该主动发送图片（与 sticker 同款随机门控）。"""
    if probability is None:
        probability = get_image_generation_probability()
    if probability <= 0:
        return False
    if probability >= 1:
        return True
    return random.random() < probability


# ----------------------------------------------------------------------------
# settings.json 读写（参照 sticker_service 的实现）
# ----------------------------------------------------------------------------

def _get_settings_path() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "data", "web", "settings.json")


def _load_image_generation_settings() -> dict:
    """从 settings.json 加载图片生成配置，返回 {enabled, probability, size}。"""
    settings_path = _get_settings_path()
    result = {
        "enabled": False,
        "probability": 0.0,
        "size": _DEFAULT_SIZE,
    }

    try:
        if os.path.exists(settings_path):
            with open(settings_path, encoding="utf-8") as f:
                data = json.loads(f.read())
            features = data.get("features", {}) if isinstance(data, dict) else {}
            if isinstance(features, dict):
                enabled = features.get("image_generation")
                if enabled is not None:
                    result["enabled"] = bool(enabled)
            image_cfg = data.get("image_generation", {}) if isinstance(data, dict) else {}
            if isinstance(image_cfg, dict):
                prob = image_cfg.get("probability")
                if prob is not None:
                    try:
                        result["probability"] = max(0.0, min(1.0, float(prob) / 100.0))
                    except (TypeError, ValueError):
                        pass
                size = image_cfg.get("size")
                if size:
                    result["size"] = str(size)
    except Exception as exc:
        _log.debug("[ImageService] 读取 settings.json 失败: %s", exc)

    return result


def is_image_generation_feature_enabled() -> bool:
    """检查 settings.json 中的 image_generation 功能开关。"""
    return _load_image_generation_settings()["enabled"]


def get_image_generation_probability() -> float:
    """获取 settings.json 配置的发送概率 (0.0-1.0)。"""
    return _load_image_generation_settings()["probability"]


def get_image_generation_size() -> str:
    """获取 settings.json 配置的默认图片尺寸。"""
    return _load_image_generation_settings()["size"]
