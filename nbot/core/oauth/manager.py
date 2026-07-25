"""OAuth 管理器：核心 OAuth 流程实现（1:1 移植自 LocalOAuthManager.kt）。

负责：
- 启动 / 轮询 设备码登录（Codex / MiniMax / xAI）
- Anthropic PKCE 登录
- Qwen 凭证导入
- OpenCode API Key 登录
- 令牌自动刷新
- 模型列表拉取
- 运行时凭据解析（注入到 HTTP 请求 header）

数据存储：
- oauth_accounts.json 用 secure_store 的 Fernet 信封加密
- 内部 OAuthTokenState 以 JSON 字符串存到 encrypted_credentials 字段（外层信封已加密）
- ai_models.json 中 OAuth 模型带 oauth_account_id 字段
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

import requests

from nbot.core.oauth.models import (
    OAuthAccount,
    OAuthLoginSession,
    OAuthPollConnected,
    OAuthPollFailed,
    OAuthPollPending,
    OAuthPollResult,
    OAuthRuntimeCredential,
    OAuthTokenState,
)
from nbot.core.oauth.providers import LocalOAuthProviders
from nbot.web.secure_store import read_secure_json, write_secure_json

_log = logging.getLogger(__name__)

# HTTP 超时（秒）：与 Android 端 defaultClient 一致
_HTTP_TIMEOUT = (20, 30)


class OAuthManager:
    """OAuth 管理器（对应 Android LocalOAuthManager）"""

    # ===== 关键常量（companion object 行 839-877 1:1 移植） =====
    REFRESH_SKEW_MS = 120_000  # 令牌提前 2 分钟刷新

    # Codex / OpenAI
    CODEX_ISSUER = "https://auth.openai.com"
    CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
    CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"

    # Qwen
    QWEN_CLIENT_ID = "f0304373b74a44d2b584a3fb70ca9e56"
    QWEN_TOKEN_URL = "https://chat.qwen.ai/api/v1/oauth2/token"

    # MiniMax
    MINIMAX_CLIENT_ID = "78257093-7e40-4613-99e0-527b14b39113"
    MINIMAX_PORTAL = "https://api.minimax.io"
    MINIMAX_SCOPE = "group_id profile model.completion"
    MINIMAX_USER_CODE_GRANT = "urn:ietf:params:oauth:grant-type:user_code"

    # xAI
    XAI_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
    XAI_SCOPE = "openid profile email offline_access grok-cli:access api:access"
    XAI_DISCOVERY_URL = "https://auth.x.ai/.well-known/openid-configuration"
    XAI_DEVICE_CODE_URL = "https://auth.x.ai/oauth2/device/code"

    # Anthropic
    ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
    ANTHROPIC_REDIRECT_URI = "https://console.anthropic.com/oauth/code/callback"
    ANTHROPIC_SCOPE = "org:create_api_key user:profile user:inference"
    ANTHROPIC_TOKEN_ENDPOINTS = [
        "https://platform.claude.com/v1/oauth/token",
        "https://console.anthropic.com/v1/oauth/token",
    ]
    ANTHROPIC_OAUTH_BETAS = (
        "interleaved-thinking-2025-05-14,"
        "fine-grained-tool-streaming-2025-05-14,"
        "claude-code-20250219,oauth-2025-04-20"
    )

    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._accounts_file = os.path.join(data_dir, "oauth_accounts.json")
        # 按账号 id 维护刷新锁，避免并发刷新
        self._refresh_locks: dict[str, threading.Lock] = {}
        self._lock_guard = threading.Lock()

    # ------------------------------------------------------------------
    # 账号持久化
    # ------------------------------------------------------------------

    def list_accounts(self) -> list[OAuthAccount]:
        """列出所有已登录账号"""
        try:
            data, _was_plaintext = read_secure_json(
                self._accounts_file, self.data_dir, {"accounts": []}
            )
        except Exception:
            return []
        if not isinstance(data, dict):
            return []
        raw_accounts = data.get("accounts", []) or []
        return [OAuthAccount.from_dict(a) for a in raw_accounts if isinstance(a, dict)]

    def save_accounts(self, accounts: list[OAuthAccount]) -> None:
        """保存账号列表（用 Fernet 信封加密）"""
        data = {"accounts": [a.to_dict() for a in accounts]}
        write_secure_json(self._accounts_file, self.data_dir, data)

    def _get_account_by_id(self, account_id: str) -> Optional[OAuthAccount]:
        for acc in self.list_accounts():
            if acc.id == account_id:
                return acc
        return None

    def _upsert_account(self, account: OAuthAccount) -> None:
        accounts = self.list_accounts()
        for i, acc in enumerate(accounts):
            if acc.id == account.id:
                accounts[i] = account
                self.save_accounts(accounts)
                return
        accounts.append(account)
        self.save_accounts(accounts)

    def _update_account_status(self, account_id: str, status: str) -> None:
        accounts = self.list_accounts()
        for acc in accounts:
            if acc.id == account_id:
                acc.status = status
                acc.updated_at = _now_iso()
                self.save_accounts(accounts)
                return

    def _save_metadata(self, account: OAuthAccount, metadata: dict[str, Any]) -> None:
        account.metadata_json = dict(metadata)
        account.updated_at = _now_iso()
        self._upsert_account(account)

    # ------------------------------------------------------------------
    # 登录入口
    # ------------------------------------------------------------------

    def start_login(self, provider: str) -> OAuthLoginSession:
        """启动 OAuth 登录会话"""
        if provider == LocalOAuthProviders.CODEX:
            return self._start_codex_login()
        if provider == LocalOAuthProviders.MINIMAX:
            return self._start_minimax_login()
        if provider == LocalOAuthProviders.XAI:
            return self._start_xai_login()
        if provider == LocalOAuthProviders.ANTHROPIC:
            return self._start_anthropic_login()
        if provider == LocalOAuthProviders.QWEN:
            raise ValueError("Qwen OAuth 需要导入 Qwen CLI 的 oauth_creds.json")
        if provider in (LocalOAuthProviders.OPENCODE_ZEN, LocalOAuthProviders.OPENCODE_GO):
            raise ValueError("OpenCode 需要输入 API Key")
        raise ValueError(f"未知 OAuth 提供商: {provider}")

    def poll_login(self, session: OAuthLoginSession) -> OAuthPollResult:
        """轮询登录状态"""
        if int(time.time() * 1000) >= session.expires_at:
            return OAuthPollFailed("登录授权已过期，请重新开始")
        try:
            if session.provider == LocalOAuthProviders.CODEX:
                return self._poll_codex(session)
            if session.provider == LocalOAuthProviders.MINIMAX:
                return self._poll_minimax(session)
            if session.provider == LocalOAuthProviders.XAI:
                return self._poll_xai(session)
            return OAuthPollFailed("该提供商不使用设备码轮询")
        except Exception as e:
            return OAuthPollFailed(str(e) or "OAuth 登录失败")

    def submit_anthropic_code(
        self, session: OAuthLoginSession, code_input: str
    ) -> OAuthPollResult:
        """Anthropic PKCE 提交授权码"""
        if session.provider != LocalOAuthProviders.ANTHROPIC:
            return OAuthPollFailed("OAuth 会话类型不匹配")
        try:
            parts = code_input.strip().split("#", 1)
            code = parts[0].strip() if parts else ""
            if not code:
                raise ValueError("请输入 Anthropic 授权码")
            returned_state = parts[1] if len(parts) > 1 else ""
            expected_state = session.secret.get("state", "")
            if returned_state != expected_state:
                raise ValueError("OAuth state 不匹配，请重新登录")
            payload = {
                "grant_type": "authorization_code",
                "client_id": self.ANTHROPIC_CLIENT_ID,
                "code": code,
                "state": returned_state or expected_state,
                "redirect_uri": self.ANTHROPIC_REDIRECT_URI,
                "code_verifier": session.secret.get("code_verifier", ""),
            }
            response = self._post_json_with_fallback(
                self.ANTHROPIC_TOKEN_ENDPOINTS,
                payload,
                {"User-Agent": "axios/1.7.9"},
            )
            state = self._token_state_from_standard_response(
                response,
                client_id=self.ANTHROPIC_CLIENT_ID,
                token_endpoint=self.ANTHROPIC_TOKEN_ENDPOINTS[0],
            )
            return self._connected_result(LocalOAuthProviders.ANTHROPIC, state)
        except Exception as e:
            return OAuthPollFailed(str(e) or "Anthropic OAuth 登录失败")

    def import_qwen_credentials(self, raw_json: str) -> OAuthPollResult:
        """导入 Qwen CLI 的 oauth_creds.json"""
        try:
            root = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            if not isinstance(root, dict):
                raise ValueError("oauth_creds.json 不是有效 JSON 对象")
            access_token = (root.get("access_token") or "").strip() if isinstance(root.get("access_token"), str) else ""
            refresh_token = (root.get("refresh_token") or "").strip() if isinstance(root.get("refresh_token"), str) else ""
            if not access_token:
                raise ValueError("oauth_creds.json 缺少 access_token")
            if not refresh_token:
                raise ValueError("oauth_creds.json 缺少 refresh_token")
            expiry_date = root.get("expiry_date")
            if isinstance(expiry_date, str) and expiry_date.isdigit():
                expiry_date = int(expiry_date)
            resource_url = root.get("resource_url") or "portal.qwen.ai"
            state = OAuthTokenState(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expiry_date if isinstance(expiry_date, int) else None,
                token_endpoint=self.QWEN_TOKEN_URL,
                client_id=self.QWEN_CLIENT_ID,
                resource_url=resource_url,
            )
            return self._connected_result(LocalOAuthProviders.QWEN, state)
        except Exception as e:
            return OAuthPollFailed(str(e) or "导入 Qwen OAuth 凭证失败")

    def import_api_key(self, provider: str, api_key: str) -> OAuthPollResult:
        """OpenCode API Key 登录"""
        try:
            if provider not in (
                LocalOAuthProviders.OPENCODE_ZEN,
                LocalOAuthProviders.OPENCODE_GO,
            ):
                raise ValueError("该提供商不支持 API Key 登录")
            normalized = (api_key or "").strip()
            if not normalized:
                raise ValueError("请输入 OpenCode API Key")
            return self._connected_result(
                provider, OAuthTokenState(access_token=normalized)
            )
        except Exception as e:
            return OAuthPollFailed(str(e) or "OpenCode API Key 登录失败")

    # ------------------------------------------------------------------
    # 模型管理
    # ------------------------------------------------------------------

    def available_models(
        self, account_id: str, refresh: bool = False
    ) -> list[str]:
        """获取账号可用模型列表（带缓存）"""
        account = self._get_account_by_id(account_id)
        if account is None:
            raise ValueError("OAuth 账号不存在")
        spec = LocalOAuthProviders.get(account.provider)
        if spec is None:
            raise ValueError(f"未知 provider: {account.provider}")
        metadata = dict(account.metadata_json or {})
        cached = metadata.get("models") or []
        if cached and not refresh:
            return list(cached)
        state = self.resolve_token_state(account, force_refresh=False)
        fetched = self._fetch_provider_models(account.provider, state)
        models = self._merge_models(spec.models, fetched)
        metadata["models"] = models
        self._save_metadata(account, metadata)
        return models

    def selected_models(self, account_id: str, ai_models: list[dict]) -> list[str]:
        """从 ai_models 列表中读取 oauth_account_id == account_id 的模型"""
        result = []
        for m in ai_models or []:
            if m.get("oauth_account_id") == account_id:
                model_id = m.get("model", "")
                if model_id:
                    result.append(model_id)
        return result

    def sync_selected_models(
        self,
        account_id: str,
        selected: list[str],
        ai_models: list[dict],
    ) -> list[dict]:
        """同步选中模型到 ai_models 列表，返回更新后的 ai_models。

        调用方负责将返回值写回 server.ai_models 并持久化。
        """
        account = self._get_account_by_id(account_id)
        if account is None:
            raise ValueError("OAuth 账号不存在")

        selected_set = set(selected)
        # 现有 OAuth 模型（按 model_id 索引）
        existing: dict[str, dict] = {}
        for m in ai_models:
            if m.get("oauth_account_id") == account_id:
                existing[m.get("model", "")] = m

        # 删除未选中的 OAuth 模型
        new_ai_models = []
        for m in ai_models:
            if m.get("oauth_account_id") == account_id:
                if m.get("model", "") not in selected_set:
                    continue  # 跳过未选中
            new_ai_models.append(m)

        # 新增 / 更新选中的模型
        for index, model_id in enumerate(selected):
            if not model_id:
                continue
            target = LocalOAuthProviders.resolve_model_target(account.provider, model_id)
            stable_id = _stable_uuid(f"{account.id}:{model_id}")
            existing_entry = existing.get(model_id)
            if existing_entry:
                # 更新已有条目
                existing_entry["name"] = existing_entry.get("name") or f"{_provider_title(account.provider)} · {model_id}"
                existing_entry["protocol"] = target.protocol
                existing_entry["provider"] = account.provider
                existing_entry["api_key"] = f"oauth:{account.id}"
                existing_entry["base_url"] = target.base_url
                existing_entry["model"] = model_id
                existing_entry["max_tokens"] = target.max_tokens
                existing_entry["max_context_length"] = target.max_context_length
                existing_entry["oauth_account_id"] = account.id
                existing_entry["updated_at"] = _now_iso()
            else:
                # 新建条目
                new_entry = {
                    "id": stable_id,
                    "name": f"{_provider_title(account.provider)} · {model_id}",
                    "purpose": "chat",
                    "provider": account.provider,
                    "provider_type": target.protocol,
                    "api_key": f"oauth:{account.id}",
                    "base_url": target.base_url,
                    "append_base_url_path": True,
                    "model": model_id,
                    "enabled": True,
                    "supports_tools": True,
                    "supports_reasoning": True,
                    "supports_stream": True,
                    "temperature": 0.7,
                    "max_tokens": target.max_tokens,
                    "top_p": 0.9,
                    "system_prompt": "",
                    "timeout": 60,
                    "retry_count": 3,
                    "stream": True,
                    "enable_memory": True,
                    "max_context_length": target.max_context_length,
                    "priority": len(existing) + index,
                    "failover_timeout": 0,
                    "oauth_account_id": account.id,
                    "created_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
                new_ai_models.append(new_entry)

        return new_ai_models

    def delete_account(
        self, account_id: str, ai_models: list[dict]
    ) -> list[dict]:
        """删除账号 + 关联的 ai_models，返回更新后的 ai_models"""
        new_ai_models = [
            m for m in ai_models if m.get("oauth_account_id") != account_id
        ]
        accounts = [a for a in self.list_accounts() if a.id != account_id]
        self.save_accounts(accounts)
        return new_ai_models

    # ------------------------------------------------------------------
    # 运行时凭据解析
    # ------------------------------------------------------------------

    def resolve_credential(self, account_id: str) -> OAuthRuntimeCredential:
        """每次实际请求前解析账号，并在即将过期时刷新。

        返回的 header 覆盖协议默认 header，保证 MiniMax/Anthropic OAuth 使用 Bearer。
        """
        account = self._get_account_by_id(account_id)
        if account is None:
            raise ValueError("OAuth 账号已删除")
        state = self.resolve_token_state(account, force_refresh=False)

        if account.provider == LocalOAuthProviders.CODEX:
            account_id_header = _extract_jwt_string(
                state.access_token,
                "https://api.openai.com/auth",
                "chatgpt_account_id",
            )
            extra_headers = {
                "User-Agent": "codex_cli_rs/0.0.0 (Nekobot Python)",
                "originator": "codex_cli_rs",
            }
            if account_id_header:
                extra_headers["ChatGPT-Account-ID"] = account_id_header
            return OAuthRuntimeCredential(
                access_token=state.access_token,
                extra_headers=extra_headers,
            )

        if account.provider == LocalOAuthProviders.MINIMAX:
            return OAuthRuntimeCredential(
                access_token=state.access_token,
                extra_headers={"Authorization": f"Bearer {state.access_token}"},
                remove_headers={"x-api-key"},
            )

        if account.provider == LocalOAuthProviders.QWEN:
            user_agent = "QwenCode/0.10.3 (python; backend)"
            return OAuthRuntimeCredential(
                access_token=state.access_token,
                extra_headers={
                    "User-Agent": user_agent,
                    "X-Dashscope-CacheControl": "enable",
                    "X-Dashscope-UserAgent": user_agent,
                    "X-Dashscope-AuthType": "qwen-oauth",
                },
            )

        if account.provider == LocalOAuthProviders.ANTHROPIC:
            return OAuthRuntimeCredential(
                access_token=state.access_token,
                extra_headers={
                    "Authorization": f"Bearer {state.access_token}",
                    "anthropic-beta": self.ANTHROPIC_OAUTH_BETAS,
                    "User-Agent": "claude-code/2.1.74 (external, cli)",
                    "x-app": "cli",
                },
                remove_headers={"x-api-key"},
            )

        # OpenCode Zen / Go / 其他：直接用 access_token
        return OAuthRuntimeCredential(access_token=state.access_token)

    # ------------------------------------------------------------------
    # 令牌状态解析 + 自动刷新
    # ------------------------------------------------------------------

    def resolve_token_state(
        self, account: OAuthAccount, force_refresh: bool = False
    ) -> OAuthTokenState:
        """解析当前令牌状态，必要时刷新"""
        with self._lock_guard:
            lock = self._refresh_locks.setdefault(account.id, threading.Lock())
        with lock:
            latest = self._get_account_by_id(account.id) or account
            state = self._decode_state(latest)
            now_ms = int(time.time() * 1000)
            expiring = False
            if state.expires_at is not None:
                expiring = state.expires_at <= now_ms + self.REFRESH_SKEW_MS
            elif state.access_token:
                expiring = _jwt_expires_soon(state.access_token, self.REFRESH_SKEW_MS)
            if not force_refresh and not expiring:
                return state
            if not state.refresh_token:
                self._update_account_status(account.id, "reauth_required")
                raise ValueError(f"OAuth 登录已过期，请重新登录 {latest.label}")
            try:
                refreshed = self._refresh_token(latest.provider, state)
            except Exception:
                self._update_account_status(account.id, "reauth_required")
                raise
            latest.encrypted_credentials = json.dumps(refreshed.to_dict(), ensure_ascii=False)
            latest.status = "connected"
            latest.expires_at = refreshed.expires_at
            latest.updated_at = _now_iso()
            self._upsert_account(latest)
            return refreshed

    def _refresh_token(
        self, provider: str, state: OAuthTokenState
    ) -> OAuthTokenState:
        """按 provider 分支刷新令牌"""
        if provider == LocalOAuthProviders.CODEX:
            return self._refresh_standard_form(state, self.CODEX_TOKEN_URL, self.CODEX_CLIENT_ID)
        if provider == LocalOAuthProviders.QWEN:
            return self._refresh_standard_form(state, self.QWEN_TOKEN_URL, self.QWEN_CLIENT_ID)
        if provider == LocalOAuthProviders.XAI:
            return self._refresh_standard_form(state, state.token_endpoint, self.XAI_CLIENT_ID)
        if provider == LocalOAuthProviders.MINIMAX:
            form = {
                "grant_type": "refresh_token",
                "client_id": self.MINIMAX_CLIENT_ID,
                "refresh_token": state.refresh_token,
            }
            response = self._execute_json(
                requests.post(
                    f"{self.MINIMAX_PORTAL}/oauth/token",
                    data=form,
                    headers={"Accept": "application/json"},
                    timeout=_HTTP_TIMEOUT,
                )
            )
            if response.get("status") != "success":
                raise ValueError("MiniMax OAuth 刷新失败")
            raw_expiry = response.get("expired_in") or 900
            expires_at = (
                raw_expiry if raw_expiry > 1_000_000_000_000
                else int(time.time() * 1000) + raw_expiry * 1000
            )
            return OAuthTokenState(
                access_token=response.get("access_token", ""),
                refresh_token=response.get("refresh_token", "") or state.refresh_token,
                expires_at=expires_at,
                token_endpoint=f"{self.MINIMAX_PORTAL}/oauth/token",
                client_id=self.MINIMAX_CLIENT_ID,
                portal_base_url=self.MINIMAX_PORTAL,
                resource_url=response.get("resource_url", "") or state.resource_url,
            )
        if provider == LocalOAuthProviders.ANTHROPIC:
            payload = {
                "grant_type": "refresh_token",
                "refresh_token": state.refresh_token,
                "client_id": self.ANTHROPIC_CLIENT_ID,
            }
            response = self._post_json_with_fallback(
                self.ANTHROPIC_TOKEN_ENDPOINTS,
                payload,
                {"User-Agent": "axios/1.7.9"},
            )
            return self._token_state_from_standard_response(
                response,
                client_id=self.ANTHROPIC_CLIENT_ID,
                token_endpoint=self.ANTHROPIC_TOKEN_ENDPOINTS[0],
                previous_refresh_token=state.refresh_token,
            )
        raise ValueError("该 OAuth 提供商不支持刷新")

    def _refresh_standard_form(
        self, state: OAuthTokenState, endpoint: str, client_id: str
    ) -> OAuthTokenState:
        """标准 OAuth refresh_token 表单刷新"""
        if not endpoint.startswith("https://"):
            raise ValueError("OAuth token endpoint 不安全")
        form = {
            "grant_type": "refresh_token",
            "refresh_token": state.refresh_token,
            "client_id": client_id,
        }
        response = self._execute_json(
            requests.post(endpoint, data=form, timeout=_HTTP_TIMEOUT)
        )
        return self._token_state_from_standard_response(
            response,
            client_id=client_id,
            token_endpoint=endpoint,
            previous_refresh_token=state.refresh_token,
        )

    def _fetch_provider_models(
        self, provider: str, state: OAuthTokenState
    ) -> list[str]:
        """拉取远端模型列表"""
        spec = LocalOAuthProviders.get(provider)
        if spec is None:
            raise ValueError(f"未知 provider: {provider}")
        # Qwen / MiniMax / Anthropic 直接返回 spec.models
        if provider in (
            LocalOAuthProviders.QWEN,
            LocalOAuthProviders.MINIMAX,
            LocalOAuthProviders.ANTHROPIC,
        ):
            return list(spec.models)

        if provider == LocalOAuthProviders.CODEX:
            url = "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0"
            headers = {
                "Authorization": f"Bearer {state.access_token}",
                "User-Agent": "codex_cli_rs/0.0.0 (Nekobot Python)",
                "originator": "codex_cli_rs",
            }
            chatgpt_account_id = _extract_jwt_string(
                state.access_token,
                "https://api.openai.com/auth",
                "chatgpt_account_id",
            )
            if chatgpt_account_id:
                headers["ChatGPT-Account-Id"] = chatgpt_account_id
        else:
            url = f"{spec.base_url.rstrip('/')}/models"
            headers = {"Authorization": f"Bearer {state.access_token}"}

        response = self._execute_json(
            requests.get(url, headers=headers, timeout=_HTTP_TIMEOUT)
        )
        # 兼容 models / data 两种字段
        array = response.get("models") if isinstance(response.get("models"), list) else None
        if array is None:
            array = response.get("data") if isinstance(response.get("data"), list) else None
        if array is None:
            return []

        result = []
        for item in array:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                visibility = str(item.get("visibility", "")).lower()
                if visibility in ("hide", "hidden"):
                    continue
                slug = item.get("slug") or item.get("id")
                if slug:
                    result.append(str(slug))
        # 去重
        seen = set()
        deduped = []
        for m in result:
            if m in seen:
                continue
            seen.add(m)
            deduped.append(m)
        # OpenCode provider 过滤掉 gemini-*
        if provider in (LocalOAuthProviders.OPENCODE_ZEN, LocalOAuthProviders.OPENCODE_GO):
            deduped = [m for m in deduped if LocalOAuthProviders.supports_opencode_model(m)]
        return deduped

    # ------------------------------------------------------------------
    # 连接成功结果构造
    # ------------------------------------------------------------------

    def _connected_result(
        self, provider: str, state: OAuthTokenState
    ) -> OAuthPollConnected:
        if not state.access_token:
            raise ValueError("OAuth 响应缺少 access_token")
        spec = LocalOAuthProviders.get(provider)
        if spec is None:
            raise ValueError(f"未知 provider: {provider}")
        now_iso = _now_iso()
        # 优先从 id_token 提取 email，否则尝试从 access_token 提取
        email = _extract_jwt_string(state.id_token or state.access_token, "email")
        if not email:
            email = _extract_jwt_string(
                state.access_token, "https://api.openai.com/profile", "email"
            )
        metadata: dict[str, Any] = {}
        if email:
            metadata["email"] = email
        label = f"{spec.title} · {email}" if email else spec.title
        # OAuthTokenState 直接以 JSON 字符串存到 encrypted_credentials（外层信封已加密）
        account = OAuthAccount(
            id=str(uuid.uuid4()),
            provider=provider,
            label=label,
            encrypted_credentials=json.dumps(state.to_dict(), ensure_ascii=False),
            metadata_json=metadata,
            status="connected",
            expires_at=state.expires_at,
            created_at=now_iso,
            updated_at=now_iso,
        )
        self._upsert_account(account)
        # 拉取模型列表
        try:
            fetched = self._fetch_provider_models(provider, state)
        except Exception as e:
            _log.warning("fetch_provider_models failed for %s: %s", provider, e)
            fetched = []
        models = self._merge_models(spec.models, fetched)
        metadata["models"] = models
        self._save_metadata(account, metadata)
        # 重新读取账号（_save_metadata 已更新）
        updated = self._get_account_by_id(account.id) or account
        return OAuthPollConnected(account=updated, models=models)

    # ------------------------------------------------------------------
    # 各 provider 的 start / poll 实现
    # ------------------------------------------------------------------

    def _start_codex_login(self) -> OAuthLoginSession:
        body = {"client_id": self.CODEX_CLIENT_ID}
        response = self._execute_json(
            requests.post(
                f"{self.CODEX_ISSUER}/api/accounts/deviceauth/usercode",
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=_HTTP_TIMEOUT,
            )
        )
        user_code = response.get("user_code", "") or ""
        device_auth_id = response.get("device_auth_id", "") or ""
        if not user_code or not device_auth_id:
            raise ValueError("OpenAI 设备码响应缺少必要字段")
        interval = response.get("interval")
        if isinstance(interval, (int, float)) and interval >= 3:
            poll_interval = int(interval)
        else:
            poll_interval = 5
        return OAuthLoginSession(
            id=str(uuid.uuid4()),
            provider=LocalOAuthProviders.CODEX,
            verification_url=f"{self.CODEX_ISSUER}/codex/device",
            user_code=user_code,
            expires_at=int(time.time() * 1000) + 15 * 60 * 1000,
            poll_interval_seconds=poll_interval,
            secret={"device_auth_id": device_auth_id},
        )

    def _poll_codex(self, session: OAuthLoginSession) -> OAuthPollResult:
        body = {
            "device_auth_id": session.secret.get("device_auth_id", ""),
            "user_code": session.user_code,
        }
        resp = requests.post(
            f"{self.CODEX_ISSUER}/api/accounts/deviceauth/token",
            json=body,
            headers={"Content-Type": "application/json"},
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code in (403, 404):
            return OAuthPollPending()
        if not resp.ok:
            raise ValueError(
                f"OpenAI 登录轮询失败: HTTP {resp.status_code} {resp.text[:200]}"
            )
        code_response = resp.json() if resp.text else {}
        form = {
            "grant_type": "authorization_code",
            "code": code_response.get("authorization_code", ""),
            "redirect_uri": f"{self.CODEX_ISSUER}/deviceauth/callback",
            "client_id": self.CODEX_CLIENT_ID,
            "code_verifier": code_response.get("code_verifier", ""),
        }
        token_response = self._execute_json(
            requests.post(self.CODEX_TOKEN_URL, data=form, timeout=_HTTP_TIMEOUT)
        )
        state = self._token_state_from_standard_response(
            token_response,
            client_id=self.CODEX_CLIENT_ID,
            token_endpoint=self.CODEX_TOKEN_URL,
        )
        return self._connected_result(LocalOAuthProviders.CODEX, state)

    def _start_minimax_login(self) -> OAuthLoginSession:
        verifier = _random_url_safe(64)
        challenge = _sha256_url_safe(verifier)
        state = _random_url_safe(16)
        form = {
            "response_type": "code",
            "client_id": self.MINIMAX_CLIENT_ID,
            "scope": self.MINIMAX_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        response = self._execute_json(
            requests.post(
                f"{self.MINIMAX_PORTAL}/oauth/code",
                data=form,
                headers={
                    "Accept": "application/json",
                    "x-request-id": str(uuid.uuid4()),
                },
                timeout=_HTTP_TIMEOUT,
            )
        )
        if response.get("state") != state:
            raise ValueError("MiniMax OAuth state 不匹配")
        raw_expiry = response.get("expired_in") or 900
        if isinstance(raw_expiry, (int, float)) and raw_expiry > 1_000_000_000_000:
            expires_at = int(raw_expiry)
        else:
            expires_at = int(time.time() * 1000) + int(raw_expiry) * 1000
        interval_ms = response.get("interval") or 2000
        poll_interval = max(2, int(interval_ms) // 1000)
        return OAuthLoginSession(
            id=str(uuid.uuid4()),
            provider=LocalOAuthProviders.MINIMAX,
            verification_url=response.get("verification_uri", "") or "",
            user_code=response.get("user_code", "") or "",
            expires_at=expires_at,
            poll_interval_seconds=poll_interval,
            secret={"code_verifier": verifier},
        )

    def _poll_minimax(self, session: OAuthLoginSession) -> OAuthPollResult:
        form = {
            "grant_type": self.MINIMAX_USER_CODE_GRANT,
            "client_id": self.MINIMAX_CLIENT_ID,
            "user_code": session.user_code,
            "code_verifier": session.secret.get("code_verifier", ""),
        }
        response = self._execute_json(
            requests.post(
                f"{self.MINIMAX_PORTAL}/oauth/token",
                data=form,
                headers={"Accept": "application/json"},
                timeout=_HTTP_TIMEOUT,
            )
        )
        status = response.get("status", "")
        if status == "success":
            raw_expiry = response.get("expired_in") or 900
            if isinstance(raw_expiry, (int, float)) and raw_expiry > 1_000_000_000_000:
                expires_at = int(raw_expiry)
            else:
                expires_at = int(time.time() * 1000) + int(raw_expiry) * 1000
            state = OAuthTokenState(
                access_token=response.get("access_token", ""),
                refresh_token=response.get("refresh_token", ""),
                expires_at=expires_at,
                token_endpoint=f"{self.MINIMAX_PORTAL}/oauth/token",
                client_id=self.MINIMAX_CLIENT_ID,
                portal_base_url=self.MINIMAX_PORTAL,
                resource_url=response.get("resource_url", ""),
            )
            return self._connected_result(LocalOAuthProviders.MINIMAX, state)
        if status == "error":
            return OAuthPollFailed("MiniMax 拒绝了本次授权")
        return OAuthPollPending()

    def _start_xai_login(self) -> OAuthLoginSession:
        discovery = self._execute_json(
            requests.get(self.XAI_DISCOVERY_URL, timeout=_HTTP_TIMEOUT)
        )
        token_endpoint = discovery.get("token_endpoint", "") or ""
        parsed = urlparse(token_endpoint)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or (host != "x.ai" and not host.endswith(".x.ai")):
            raise ValueError("xAI 返回了不安全的 token endpoint")
        form = {"client_id": self.XAI_CLIENT_ID, "scope": self.XAI_SCOPE}
        response = self._execute_json(
            requests.post(
                self.XAI_DEVICE_CODE_URL,
                data=form,
                headers={"Accept": "application/json"},
                timeout=_HTTP_TIMEOUT,
            )
        )
        verification_url = (
            response.get("verification_uri_complete")
            or response.get("verification_uri")
            or ""
        )
        expires_in = response.get("expires_in") or 900
        interval = response.get("interval")
        poll_interval = max(1, int(interval)) if isinstance(interval, (int, float)) else 5
        return OAuthLoginSession(
            id=str(uuid.uuid4()),
            provider=LocalOAuthProviders.XAI,
            verification_url=verification_url,
            user_code=response.get("user_code", "") or "",
            expires_at=int(time.time() * 1000) + int(expires_in) * 1000,
            poll_interval_seconds=poll_interval,
            secret={
                "device_code": response.get("device_code", "") or "",
                "token_endpoint": token_endpoint,
            },
        )

    def _poll_xai(self, session: OAuthLoginSession) -> OAuthPollResult:
        form = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": self.XAI_CLIENT_ID,
            "device_code": session.secret.get("device_code", ""),
        }
        resp = requests.post(
            session.secret.get("token_endpoint", ""),
            data=form,
            headers={"Accept": "application/json"},
            timeout=_HTTP_TIMEOUT,
        )
        try:
            data = resp.json() if resp.text else {}
        except Exception:
            data = {}
        if not resp.ok:
            error = data.get("error", "")
            if error in ("authorization_pending", "slow_down"):
                return OAuthPollPending()
            msg = data.get("error_description") or f"xAI OAuth 失败: HTTP {resp.status_code} {resp.text[:200]}"
            return OAuthPollFailed(msg)
        state = self._token_state_from_standard_response(
            data,
            client_id=self.XAI_CLIENT_ID,
            token_endpoint=session.secret.get("token_endpoint", ""),
        )
        return self._connected_result(LocalOAuthProviders.XAI, state)

    def _start_anthropic_login(self) -> OAuthLoginSession:
        verifier = _random_url_safe(32)
        challenge = _sha256_url_safe(verifier)
        state = _random_url_safe(32)
        params = {
            "code": "true",
            "client_id": self.ANTHROPIC_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": self.ANTHROPIC_REDIRECT_URI,
            "scope": self.ANTHROPIC_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
        url = f"https://claude.ai/oauth/authorize?{urlencode(params)}"
        return OAuthLoginSession(
            id=str(uuid.uuid4()),
            provider=LocalOAuthProviders.ANTHROPIC,
            verification_url=url,
            expires_at=int(time.time() * 1000) + 15 * 60 * 1000,
            secret={"code_verifier": verifier, "state": state},
        )

    # ------------------------------------------------------------------
    # HTTP / JSON 辅助
    # ------------------------------------------------------------------

    def _execute_json(self, response: requests.Response) -> dict:
        """执行 requests 调用并解析 JSON，失败时抛出带 detail 的异常"""
        try:
            raw = response.text or ""
        except Exception:
            raw = ""
        if not response.ok:
            detail = ""
            try:
                obj = json.loads(raw) if raw else {}
                if isinstance(obj, dict):
                    detail = (
                        obj.get("error_description")
                        or obj.get("message")
                        or ""
                    )
                    if not detail and isinstance(obj.get("error"), dict):
                        detail = obj["error"].get("message", "") or ""
            except Exception:
                pass
            if not detail:
                detail = f"HTTP {response.status_code}: {raw[:300]}"
            raise ValueError(detail)
        try:
            return json.loads(raw) if raw else {}
        except Exception:
            return {}

    def _post_json_with_fallback(
        self, endpoints: list[str], payload: dict, headers: dict[str, str]
    ) -> dict:
        """多 endpoint 回退 POST JSON"""
        last_error: Optional[Exception] = None
        for endpoint in endpoints:
            try:
                resp = requests.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=_HTTP_TIMEOUT,
                )
                return self._execute_json(resp)
            except Exception as e:
                last_error = e
                continue
        raise last_error or RuntimeError("OAuth token exchange failed")

    def _token_state_from_standard_response(
        self,
        response: dict,
        client_id: str,
        token_endpoint: str,
        previous_refresh_token: str = "",
    ) -> OAuthTokenState:
        access_token = response.get("access_token", "") or ""
        if not access_token:
            raise ValueError("OAuth 响应缺少 access_token")
        expires_in = response.get("expires_in")
        if isinstance(expires_in, (int, float)) and expires_in > 0:
            expires_at = int(time.time() * 1000) + int(expires_in) * 1000
        else:
            expires_at = _jwt_expiry_millis(access_token)
        return OAuthTokenState(
            access_token=access_token,
            refresh_token=response.get("refresh_token", "") or previous_refresh_token,
            id_token=response.get("id_token", "") or "",
            expires_at=expires_at,
            token_endpoint=token_endpoint,
            client_id=client_id,
            resource_url=response.get("resource_url", "") or "",
        )

    def _decode_state(self, account: OAuthAccount) -> OAuthTokenState:
        """从账号的 encrypted_credentials 字段解析 OAuthTokenState"""
        raw = account.encrypted_credentials or "{}"
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            data = {}
        return OAuthTokenState.from_dict(data)

    @staticmethod
    def _merge_models(curated: list[str], fetched: list[str]) -> list[str]:
        """合并 fetched + curated，去重保持顺序"""
        seen = set()
        result = []
        for m in list(fetched) + list(curated):
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result


# ---------------------------------------------------------------------------
# 模块级辅助函数
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_title(provider_id: str) -> str:
    spec = LocalOAuthProviders.get(provider_id)
    return spec.title if spec else provider_id


def _stable_uuid(name: str) -> str:
    """基于 name 生成稳定的 UUID（对应 Android 的 UUID.nameUUIDFromBytes）"""
    md5 = hashlib.md5(name.encode("utf-8")).digest()
    # 设置 version 3 (name-based, MD5) 的标志位
    b = bytearray(md5)
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    import uuid as _uuid
    return str(_uuid.UUID(bytes=bytes(b)))


def _random_url_safe(size: int) -> str:
    """生成 url-safe 随机字符串"""
    return secrets.token_urlsafe(size)[:size].rstrip("=")


def _sha256_url_safe(value: str) -> str:
    """SHA-256 后做 url-safe base64 编码并去除 = 填充"""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _decode_jwt_payload(token: str) -> Optional[dict]:
    """解码 JWT 的 payload 部分（不验证签名）"""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    part = parts[1]
    # 补齐 base64 padding
    padding = "=" * (-len(part) % 4)
    try:
        decoded = base64.urlsafe_b64decode(part + padding)
        data = json.loads(decoded.decode("utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _extract_jwt_string(token: str, *keys: str) -> Optional[str]:
    """从 JWT payload 中按 path 取字符串值"""
    current: Any = _decode_jwt_payload(token)
    if current is None:
        return None
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
        if current is None:
            return None
    return current if isinstance(current, str) else None


def _jwt_expiry_millis(token: str) -> Optional[int]:
    """从 JWT 的 exp 字段获取过期毫秒时间戳"""
    payload = _decode_jwt_payload(token)
    if not payload:
        return None
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        return int(exp) * 1000
    return None


def _jwt_expires_soon(token: str, skew_ms: int) -> bool:
    """判断 JWT 是否即将过期"""
    exp = _jwt_expiry_millis(token)
    if exp is None:
        return False
    return exp <= int(time.time() * 1000) + skew_ms
