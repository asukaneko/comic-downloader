"""OAuth 提供商配置（7 个 provider，1:1 移植自 LocalOAuthModels.kt）。

Provider 列表：
- CODEX        (openai-codex)    设备码   openai_responses
- QWEN         (qwen-oauth)      凭证导入 openai_chat
- MINIMAX      (minimax-oauth)   设备码   anthropic_messages
- XAI          (xai-oauth)       设备码   openai_responses
- OPENCODE_ZEN (opencode-zen)    API Key  openai_chat
- OPENCODE_GO  (opencode-go)     API Key  openai_chat
- ANTHROPIC    (anthropic-oauth) PKCE     anthropic_messages
"""

from __future__ import annotations

from typing import Optional

from nbot.core.oauth.models import (
    LocalOAuthModelTarget,
    OAuthLoginMode,
    OAuthProviderSpec,
)


class LocalOAuthProviders:
    """OAuth 提供商注册表（单例，对应 Android LocalOAuthProviders object）"""

    # Provider id 常量
    CODEX = "openai-codex"
    QWEN = "qwen-oauth"
    MINIMAX = "minimax-oauth"
    XAI = "xai-oauth"
    OPENCODE_ZEN = "opencode-zen"
    OPENCODE_GO = "opencode-go"
    ANTHROPIC = "anthropic-oauth"

    # 7 个 provider 完整 spec
    all: list[OAuthProviderSpec] = [
        OAuthProviderSpec(
            id=CODEX,
            title="Codex",
            subtitle="使用 ChatGPT 订阅登录 OpenAI Codex",
            login_mode=OAuthLoginMode.DEVICE_CODE,
            protocol="openai_responses",
            base_url="https://chatgpt.com/backend-api/codex",
            models=[
                "gpt-5.6-sol",
                "gpt-5.6-sol-pro",
                "gpt-5.6-terra",
                "gpt-5.6-terra-pro",
                "gpt-5.6-luna",
                "gpt-5.6-luna-pro",
                "gpt-5.5",
                "gpt-5.4-mini",
                "gpt-5.4",
                "gpt-5.3-codex",
                "gpt-5.3-codex-spark",
            ],
            default_context_length=272_000,
            default_max_tokens=128_000,
        ),
        OAuthProviderSpec(
            id=QWEN,
            title="Qwen (via Qwen CLI)",
            subtitle="导入 Qwen CLI 的 oauth_creds.json",
            login_mode=OAuthLoginMode.QWEN_CREDENTIAL_IMPORT,
            protocol="openai_chat",
            base_url="https://portal.qwen.ai/v1",
            models=["qwen3-coder-plus", "qwen3-coder"],
            default_context_length=1_000_000,
            default_max_tokens=65_536,
        ),
        OAuthProviderSpec(
            id=MINIMAX,
            title="MiniMax (OAuth)",
            subtitle="浏览器授权，无需 API Key",
            login_mode=OAuthLoginMode.DEVICE_CODE,
            protocol="anthropic_messages",
            base_url="https://api.minimax.io/anthropic",
            models=["MiniMax-M3", "MiniMax-M2.7", "MiniMax-M2.7-highspeed"],
            default_context_length=204_800,
            default_max_tokens=131_072,
        ),
        OAuthProviderSpec(
            id=XAI,
            title="xAI Grok OAuth (SuperGrok / Premium+)",
            subtitle="使用 SuperGrok 或 X Premium+ 订阅",
            login_mode=OAuthLoginMode.DEVICE_CODE,
            protocol="openai_responses",
            base_url="https://api.x.ai/v1",
            models=[
                "grok-build-0.1",
                "grok-4.5",
                "grok-4.3",
                "grok-composer-2.5-fast",
                "grok-4.20-0309-reasoning",
                "grok-4.20-0309-non-reasoning",
                "grok-4.20-multi-agent-0309",
            ],
            default_context_length=1_000_000,
            default_max_tokens=131_072,
        ),
        OAuthProviderSpec(
            id=OPENCODE_ZEN,
            title="OpenCode Zen",
            subtitle="使用 OpenCode API Key 登录",
            login_mode=OAuthLoginMode.API_KEY,
            protocol="openai_chat",
            base_url="https://opencode.ai/zen/v1",
            models=[
                "gpt-5.4",
                "gpt-5.3-codex",
                "claude-sonnet-4-6",
                "claude-haiku-4-5",
                "qwen3.6-plus",
                "grok-4.5",
                "deepseek-v4-flash",
                "minimax-m2.7",
                "glm-5",
                "kimi-k2.6",
                "big-pickle",
                "deepseek-v4-flash-free",
            ],
            default_context_length=200_000,
            default_max_tokens=65_536,
        ),
        OAuthProviderSpec(
            id=OPENCODE_GO,
            title="OpenCode Go",
            subtitle="使用 OpenCode Go 订阅的 API Key 登录",
            login_mode=OAuthLoginMode.API_KEY,
            protocol="openai_chat",
            base_url="https://opencode.ai/zen/go/v1",
            models=[
                "grok-4.5",
                "glm-5.2",
                "glm-5.1",
                "kimi-k3",
                "kimi-k2.7-code",
                "kimi-k2.6",
                "deepseek-v4-pro",
                "deepseek-v4-flash",
                "mimo-v2.5-pro",
                "mimo-v2.5",
                "minimax-m3",
                "minimax-m2.7",
                "minimax-m2.5",
                "qwen3.7-max",
                "qwen3.7-plus",
                "qwen3.6-plus",
            ],
            default_context_length=200_000,
            default_max_tokens=65_536,
        ),
        OAuthProviderSpec(
            id=ANTHROPIC,
            title="Anthropic OAuth: Required Extra Usage Credits to Use Subscription",
            subtitle="需要 Claude Max 与 Extra Usage Credits",
            login_mode=OAuthLoginMode.PKCE_CODE,
            protocol="anthropic_messages",
            base_url="https://api.anthropic.com",
            models=[
                "claude-fable-5",
                "claude-sonnet-5",
                "claude-opus-4-8",
                "claude-opus-4-7",
                "claude-opus-4-6",
                "claude-sonnet-4-6",
                "claude-opus-4-5-20251101",
                "claude-sonnet-4-5-20250929",
                "claude-haiku-4-5-20251001",
            ],
            default_context_length=1_000_000,
            default_max_tokens=128_000,
        ),
    ]

    @classmethod
    def get(cls, provider_id: str) -> Optional[OAuthProviderSpec]:
        """按 id 查找 provider spec"""
        for spec in cls.all:
            if spec.id == provider_id:
                return spec
        return None

    @classmethod
    def resolve_model_target(
        cls, provider: str, model_id: str
    ) -> LocalOAuthModelTarget:
        """解析单个模型在 OAuth provider 下的运行时定位。

        OpenCode Zen / Go 会根据模型名前缀切换 protocol / base_url / token 限制。
        """
        spec = cls.get(provider)
        if spec is None:
            raise ValueError(f"未知账号提供商: {provider}")

        # 非 OpenCode provider 直接返回 spec 默认值
        if provider != cls.OPENCODE_ZEN and provider != cls.OPENCODE_GO:
            return LocalOAuthModelTarget(
                protocol=spec.protocol,
                base_url=spec.base_url,
                max_context_length=spec.default_context_length,
                max_tokens=spec.default_max_tokens,
            )

        normalized = (model_id or "").lower()

        # OpenCode Go：minimax-*/qwen* → anthropic_messages，其他 → openai_chat
        if provider == cls.OPENCODE_GO:
            if normalized.startswith("minimax-") or normalized.startswith("qwen"):
                return LocalOAuthModelTarget(
                    protocol="anthropic_messages",
                    base_url="https://opencode.ai/zen/go",
                    max_context_length=200_000,
                    max_tokens=128_000,
                )
            return LocalOAuthModelTarget(
                protocol="openai_chat",
                base_url="https://opencode.ai/zen/go/v1",
                max_context_length=200_000,
                max_tokens=65_536,
            )

        # OpenCode Zen：按模型族切换
        if normalized.startswith("gpt-"):
            return LocalOAuthModelTarget(
                protocol="openai_responses",
                base_url="https://opencode.ai/zen/v1",
                max_context_length=272_000,
                max_tokens=128_000,
            )
        if normalized.startswith("claude-") or normalized.startswith("qwen"):
            return LocalOAuthModelTarget(
                protocol="anthropic_messages",
                base_url="https://opencode.ai/zen",
                max_context_length=200_000,
                max_tokens=128_000,
            )
        # 默认
        return LocalOAuthModelTarget(
            protocol="openai_chat",
            base_url="https://opencode.ai/zen/v1",
            max_context_length=131_072,
            max_tokens=65_536,
        )

    @classmethod
    def supports_opencode_model(cls, model_id: str) -> bool:
        """gemini-* 模型不在 OpenCode 列表内（大小写不敏感）"""
        return not (model_id or "").lower().startswith("gemini-")
