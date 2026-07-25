# oauth - 多服务商账号管理

## 概述

`nbot/core/oauth/` 是 NekoBot 的 OAuth 子系统，从 Android 端 `LocalOAuthManager` / `LocalOAuthModels` 1:1 移植。它让用户可以通过订阅账号登录（Codex / Qwen / MiniMax / xAI / Anthropic / OpenCode Zen / OpenCode Go）替代手动填写 API Key，运行时由 NekoBot 自动刷新令牌并把 `access_token` 注入到 AI 请求头。

核心约束：本模块位于 `nbot/core/`，严禁引入 `nbot/web/` 或 `nbot/channels/`。Web 路由 (`nbot/web/routes/oauth.py`) 与 AI 服务层 (`nbot/services/ai.py`) 通过 `get_oauth_manager()` 单例访问。

## 支持的服务商

| Provider ID | 名称 | 登录模式 | 协议 | 备注 |
|-------------|------|----------|------|------|
| `openai-codex` | Codex | 设备码 | `openai_responses` | 使用 ChatGPT 订阅登录 OpenAI Codex |
| `qwen-oauth` | Qwen (via Qwen CLI) | 凭证导入 | `openai_chat` | 导入 Qwen CLI 的 `oauth_creds.json` |
| `minimax-oauth` | MiniMax (OAuth) | 设备码 | `anthropic_messages` | 浏览器授权，无需 API Key |
| `xai-oauth` | xAI Grok OAuth | 设备码 | `openai_responses` | SuperGrok / X Premium+ 订阅 |
| `opencode-zen` | OpenCode Zen | API Key | `openai_chat` | |
| `opencode-go` | OpenCode Go | API Key | `openai_chat` | |
| `anthropic-oauth` | Anthropic | PKCE | `anthropic_messages` | PKCE 浏览器授权码流程 |

## 四种登录模式

`OAuthLoginMode` 枚举定义了所有支持的登录流程：

| 模式 | 说明 | 调用入口 |
|------|------|----------|
| `DEVICE_CODE` | 设备码授权：用户在浏览器输入 user_code 完成授权，客户端轮询 token 端点 | `start_login` + `poll_login` |
| `PKCE_CODE` | PKCE 浏览器授权：用户在浏览器完成授权后，将回调中的 code 提交回后端 | `start_login` + `submit_anthropic_code` |
| `QWEN_CREDENTIAL_IMPORT` | 凭证导入：直接导入 Qwen CLI 生成的 `oauth_creds.json` | `import_qwen_credentials` |
| `API_KEY` | API Key 录入：将传统 API Key 包装为 OAuth 账号统一管理 | `import_api_key` |

## 核心数据模型

### OAuthAccount

已登录账号实体，持久化到 `data/web/oauth_accounts.json`（外层 Fernet 信封加密）。

```python
@dataclass
class OAuthAccount:
    id: str                          # 账号 ID（基于 provider + 标识 stable_uuid）
    provider: str                    # provider id（如 "openai-codex"）
    label: str                       # 显示名称
    encrypted_credentials: str       # OAuthTokenState 的 JSON 字符串（外层信封已加密）
    metadata_json: dict[str, Any]    # 附加元数据
    status: str = "connected"        # connected / expired / failed
    expires_at: Optional[int]        # 过期时间（毫秒时间戳）
    created_at: str
    updated_at: str
```

### OAuthTokenState

令牌状态，序列化后存入 `OAuthAccount.encrypted_credentials`：

```python
@dataclass
class OAuthTokenState:
    access_token: str
    refresh_token: str
    id_token: str
    expires_at: Optional[int]        # 毫秒时间戳
    token_endpoint: str
    client_id: str
    portal_base_url: str
    resource_url: str
```

### OAuthRuntimeCredential

运行时凭据，由 `resolve_credential()` 返回，供 `ai.py` 注入到 HTTP 请求：

```python
@dataclass
class OAuthRuntimeCredential:
    access_token: str
    extra_headers: dict[str, str]    # 需要追加的请求头
    remove_headers: set[str]         # 需要移除的请求头
```

### OAuthPollResult

登录轮询结果，用类层级模拟 sealed interface：

- `OAuthPollPending`：用户尚未完成授权，继续轮询
- `OAuthPollConnected`：登录成功，返回 `OAuthAccount` 与可用模型列表
- `OAuthPollFailed`：登录失败，附带 `message`

## OAuthManager 关键方法

| 方法 | 说明 |
|------|------|
| `list_accounts()` | 列出所有已登录账号 |
| `start_login(provider) -> OAuthLoginSession` | 启动设备码 / PKCE 登录流程 |
| `poll_login(session) -> OAuthPollResult` | 轮询设备码登录结果 |
| `submit_anthropic_code(session, code) -> OAuthPollResult` | 提交 Anthropic PKCE 授权码 |
| `import_qwen_credentials(raw_json) -> OAuthPollResult` | 导入 Qwen CLI 凭证 |
| `import_api_key(provider, api_key) -> OAuthPollResult` | API Key 录入 |
| `available_models(account_id, refresh=False)` | 返回账号可用模型列表（带缓存，可强制刷新） |
| `selected_models(account_id, ai_models)` | 返回已选中的模型列表 |
| `sync_selected_models(account_id, selected, ai_models)` | 同步选中模型到 `ai_models.json` |
| `delete_account(account_id, ai_models)` | 删除账号并清理关联模型配置 |
| `resolve_credential(account_id) -> OAuthRuntimeCredential` | 解析运行时凭据（含自动刷新） |
| `resolve_token_state(account, force_refresh=False)` | 解析令牌状态，必要时调用 `_refresh_token` |

## 令牌自动刷新

`OAuthManager` 在 `resolve_credential` / `resolve_token_state` 阶段自动检查令牌过期时间：

- `REFRESH_SKEW_MS = 120_000`：令牌提前 2 分钟刷新
- `_jwt_expires_soon(token, skew_ms)`：基于 JWT `exp` 字段判断
- `_refresh_token(provider, state)`：按 provider 调用对应 token 端点
- `_refresh_standard_form(state, endpoint, client_id)`：标准 `refresh_token` grant 刷新

刷新后的新令牌会写回 `OAuthAccount.encrypted_credentials`，整个过程对调用方透明。

## 单例与初始化

参考 `nbot.core.failover` 的 init/get 模式：

```python
from nbot.core.oauth import init_oauth_manager, get_oauth_manager

# 启动时调用一次（由 WebChatServer 初始化）
init_oauth_manager(data_dir="data/")

# 运行时访问（services/ai.py）
manager = get_oauth_manager()
credential = manager.resolve_credential(account_id)
```

未初始化时 `get_oauth_manager()` 会抛出 `RuntimeError`。

## 与 AI 服务层集成

`nbot/services/ai.py` 在每次发起 AI 请求前：

1. 检查模型配置是否带 `oauth_account_id`
2. 若有，调用 `get_oauth_manager().resolve_credential(account_id)` 获取凭据
3. 将 `access_token` 注入 `Authorization` 头（或 provider 自定义头）
4. 应用 `extra_headers` / `remove_headers`

故障转移（failover）模块同样支持 OAuth 账号绑定的模型：当某个 OAuth 账号令牌失效且无法刷新时，模型进入冷却，自动尝试下一个。

## 持久化与加密

- **存储文件**：`data/web/oauth_accounts.json`
- **加密方式**：`secure_store` 的 Fernet 信封加密（与 `ai_config.json` 同一密钥体系）
- **敏感字段**：`OAuthTokenState` 整体序列化为 JSON 字符串，存入 `OAuthAccount.encrypted_credentials` 字段；外层文件再次加密
- **API 响应**：`OAuthPollConnected.to_dict()` 显式 `pop("encrypted_credentials")`，避免敏感信息泄露到前端

## Web API 路由

`nbot/web/routes/oauth.py` 提供以下端点（前缀 `/api/oauth`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/providers` | 列出所有支持的 OAuth 服务商 |
| GET | `/accounts` | 列出已登录账号 |
| POST | `/login` | 启动登录流程（设备码 / PKCE） |
| GET | `/login/poll` | 轮询设备码登录结果 |
| POST | `/login/anthropic-code` | 提交 Anthropic PKCE 授权码 |
| POST | `/login/qwen-import` | 导入 Qwen CLI 凭证 |
| POST | `/login/api-key` | API Key 录入 |
| GET | `/accounts/<id>/models` | 获取账号可用模型 |
| PUT | `/accounts/<id>/models` | 同步选中模型 |
| DELETE | `/accounts/<id>` | 删除账号 |

## 设计原则

1. **核心隔离** - `nbot/core/oauth/` 不依赖 `nbot/web/`，仅通过 `secure_store` 共享加密能力
2. **令牌透明刷新** - 调用方无需关心过期时间，`resolve_credential` 自动处理
3. **加密双保险** - 文件级 Fernet 加密 + 字段级 JSON 序列化，密钥丢失即数据失效
4. **provider 可扩展** - 在 `LocalOAuthProviders.all` 列表中追加 `OAuthProviderSpec` 即可新增服务商
5. **与现有模型配置共存** - OAuth 账号通过 `oauth_account_id` 字段关联 `ai_models.json`，不破坏原有 API Key 模式
