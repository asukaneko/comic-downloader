"""OAuth 子系统：从 Android 端 LocalOAuthManager / LocalOAuthModels 移植。

支持 7 个 provider（Codex / Qwen / MiniMax / xAI / Anthropic / OpenCode Zen / OpenCode Go），
4 种登录模式（设备码 / PKCE / Qwen 凭证导入 / API Key）。

主要导出：
- OAuthManager: 核心 OAuth 管理器
- LocalOAuthProviders: provider spec 注册表
- 数据类: OAuthAccount / OAuthLoginSession / OAuthPollResult 等
"""

from nbot.core.oauth.models import (
    LocalOAuthModelTarget,
    OAuthAccount,
    OAuthLoginMode,
    OAuthLoginSession,
    OAuthPollConnected,
    OAuthPollFailed,
    OAuthPollPending,
    OAuthPollResult,
    OAuthProviderSpec,
    OAuthRuntimeCredential,
    OAuthTokenState,
)
from nbot.core.oauth.providers import LocalOAuthProviders
from nbot.core.oauth.manager import OAuthManager

# ---------------------------------------------------------------------------
# OAuthManager 单例访问器（参考 nbot.core.failover 的 init/get 模式）
# ---------------------------------------------------------------------------
_oauth_manager_instance = None


def init_oauth_manager(data_dir: str) -> "OAuthManager":
    """初始化全局 OAuthManager 单例（由 WebChatServer 启动时调用一次）。"""
    global _oauth_manager_instance
    if _oauth_manager_instance is None:
        _oauth_manager_instance = OAuthManager(data_dir)
    return _oauth_manager_instance


def get_oauth_manager() -> "OAuthManager":
    """获取全局 OAuthManager 单例。

    services/ai.py 在运行时通过此函数访问 OAuthManager，
    解析 oauth_account_id 对应的 access_token 注入到 HTTP 请求。
    """
    if _oauth_manager_instance is None:
        raise RuntimeError(
            "OAuthManager 未初始化，请先在 WebChatServer 启动时调用 init_oauth_manager(data_dir)"
        )
    return _oauth_manager_instance

__all__ = [
    "OAuthManager",
    "LocalOAuthProviders",
    "OAuthLoginMode",
    "OAuthProviderSpec",
    "LocalOAuthModelTarget",
    "OAuthLoginSession",
    "OAuthPollResult",
    "OAuthPollPending",
    "OAuthPollConnected",
    "OAuthPollFailed",
    "OAuthRuntimeCredential",
    "OAuthTokenState",
    "OAuthAccount",
    "init_oauth_manager",
    "get_oauth_manager",
]
