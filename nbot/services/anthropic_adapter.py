"""
Anthropic Messages API 适配器 - 向后兼容垫片

实际实现已迁移至 nbot.core.protocols.anthropic_messages。
此文件保留原有函数签名以兼容旧代码。
"""

from nbot.core.protocols.anthropic_messages import AnthropicMessagesProtocol

_proto = AnthropicMessagesProtocol()


def convert_openai_messages_to_anthropic(messages):
    return _proto._convert_messages(messages)


def convert_openai_tools_to_anthropic(tools):
    return _proto._convert_tools(tools)


def build_anthropic_payload(model, messages, max_tokens=4096, **kwargs):
    return _proto.build_payload(model, messages, max_tokens=max_tokens, **kwargs)


def parse_anthropic_response(response_data):
    normalized = _proto.parse_response(response_data)
    return {
        "content": normalized.content,
        "thinking_content": normalized.thinking_content,
        "tool_calls": normalized.tool_calls or None,
        "finish_reason": normalized.finish_reason,
        "usage": normalized.usage,
    }


def parse_anthropic_stream_chunk(chunk_data):
    return _proto.parse_stream_chunk(chunk_data)


def get_anthropic_headers(api_key):
    return _proto.build_headers(api_key)
