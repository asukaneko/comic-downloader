"""模型采样参数工具：停止字符串的归一化与请求注入。

模型配置中的 stop 字段允许字符串（按行分隔）或字符串列表，
协议层会按各家 API 翻译为 stop / stop_sequences / stopSequences。
"""

from typing import Any, Dict, List

MAX_STOP_SEQUENCES = 4
MAX_STOP_LENGTH = 64


def normalize_stop_strings(value: Any) -> List[str]:
    """把模型配置里的停止字符串归一化为字符串列表。"""
    if not value:
        return []

    candidates: List[str] = []
    if isinstance(value, str):
        candidates = _split_lines(value)
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, str):
                candidates.extend(_split_lines(item))

    stops: List[str] = []
    for candidate in candidates:
        text = candidate.strip()
        if not text or text in stops:
            continue
        stops.append(text[:MAX_STOP_LENGTH])
        if len(stops) >= MAX_STOP_SEQUENCES:
            break
    return stops


def stop_extra_body(config: Any) -> Dict[str, Any]:
    """从模型配置中提取 stop 并包装为协议层 extra_body。"""
    if not isinstance(config, dict):
        return {}
    stops = normalize_stop_strings(config.get("stop"))
    if not stops:
        return {}
    return {"stop": stops}


def _split_lines(text: str) -> List[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
