"""
Multi-protocol model adapter package.

Provides unified interface for different AI model API protocols:
- OpenAI Chat Completions (v1/chat/completions)
- OpenAI Responses (v1/responses)
- Anthropic Messages (/v1/messages)
"""

from nbot.core.protocols.base import (
    ModelProtocol,
    get_protocol,
    list_protocols,
    register_protocol,
)
from nbot.core.protocols.openai_chat import OpenAIChatProtocol
from nbot.core.protocols.openai_responses import OpenAIResponsesProtocol
from nbot.core.protocols.anthropic_messages import AnthropicMessagesProtocol

__all__ = [
    "ModelProtocol",
    "get_protocol",
    "register_protocol",
    "OpenAIChatProtocol",
    "OpenAIResponsesProtocol",
    "AnthropicMessagesProtocol",
]
