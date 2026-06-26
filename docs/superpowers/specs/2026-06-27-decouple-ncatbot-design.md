# Ncatbot 解耦与 QQ Bot 官方频道接入设计

**Date**: 2026-06-27
**Status**: Draft — pending user review
**Author**: Brainstorming session output

## 1. 背景与目标

### 1.1 现状

NekoBot 当前通过 [ncatbot](https://github.com/liyihao1110/ncatbot) + [NapCatQQ](https://github.com/NapNeko/NapCatQQ) 接入 QQ。ncatbot 3.8.5 是基于 OneBot v11 协议（NapCat WebSocket）的 Python 框架，依赖第三方 QQ 客户端运行。

项目同时已实现 **`nbot/channels/qqbot.py`**（231 行 Channel Adapter）和 **`nbot/services/qqbot_service.py`**（689 行 WebSocket 客户端）——这是一套完全独立、基于 QQ 开放平台 OpenAPI v2 协议（app_id + app_secret 鉴权）、直连 `api.sgroup.qq.com` 的官方机器人实现。该实现已可用，但与现有命令系统（`nbot/commands.py`）未打通。

### 1.2 目标

1. 让 `commands.py` 中的 60+ 命令可以同时跑在 ncatbot 和 QQBot 两个后端上
2. 配置文件支持 `app_id` + `app_secret` 作为新主推方案，与 `bot_uin` + `ws_uri` 并存
3. 保留对老 ncatbot 用户的向后兼容
4. 消除 `commands.py` 中 ~100+ 处 `bot.api.*` 散落调用，将其抽象到 `BotBackend` 协议

### 1.3 非目标

- 不完全移除 ncatbot 依赖（保留为可选项）
- 不拆分 `commands.py` 4989 行单文件
- 不重写 QQ Bot 业务逻辑（保留 `qqbot_service.py` 现有实现）
- 不引入第三方 QQ Bot SDK（如 `botpy`），仍用 `requests` + `websocket-client`

## 2. 核心设计：BotBackend 抽象层

### 2.1 设计原则

- **Platform-neutral 命令系统**：`commands.py` 不再直接导入 ncatbot 类型
- **鸭子类型后端**：`BotBackend` 是 `Protocol`，ncatbot_backend 和 qqbot_backend 不需要显式继承
- **最小破坏面**：保留现有 ncatbot 事件循环机制和 BotAPI monkey-patch（消息持久化逻辑）
- **配置驱动**：根据环境变量自动选择后端

### 2.2 三个核心抽象

#### 2.2.1 `IncomingMessage`（入站消息数据类）

**新文件**：`nbot/commands_backend.py`

```python
@dataclass
class IncomingMessage:
    """统一入站消息格式 —— 替代 ncatbot 的 msg 对象"""
    scene: Scene               # GROUP | PRIVATE
    user_id: str
    text: str = ""
    group_id: str = ""
    sender_name: str = ""
    message_id: str = ""
    is_mentioned: bool = False
    raw_message: Any = None    # 原生对象（ncatbot GroupMessage / qqbot dict）
    backend_name: str = "unknown"
    metadata: dict = field(default_factory=dict)

    @property
    def is_group(self) -> bool: ...

    async def reply(self, text=None, *, image=None, voice=None, file=None) -> bool:
        """便捷回复，自动选择私聊/群聊路径"""
```

**关键点**：
- 替代 ncatbot 的 `GroupMessage`/`PrivateMessage` 对象访问模式（`msg.user_id`、`msg.group_id`、`msg.reply()`）
- `reply()` 是 async 方法（保留与 `msg.reply()` 的语义兼容），但内部走 `get_backend().send_*`
- `raw_message` 保留原生对象（备用，业务代码不应直接访问）

#### 2.2.2 `BotBackend` 协议

```python
@runtime_checkable
class BotBackend(Protocol):
    name: str
    is_running: bool

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def run_forever(self) -> None:        # 阻塞入口

    # 文本消息
    async def send_private_text(self, user_id: str, text: str) -> bool: ...
    async def send_group_text(self, group_id: str, text: str) -> bool: ...

    # 富媒体
    async def send_private_image(self, user_id: str, image_path: str) -> bool: ...
    async def send_group_image(self, group_id: str, image_path: str) -> bool: ...
    async def send_group_voice(self, group_id: str, voice_path: str) -> bool: ...
    async def send_group_file(self, group_id: str, file_path: str) -> bool: ...
    async def send_private_file(self, user_id: str, file_path: str) -> bool: ...

    # 引用回复
    async def reply_message(self, message_id: str, text: str, *,
                            is_group: bool = False,
                            target_id: str = "") -> bool: ...

    # 历史/文件
    async def get_group_msg_history(self, group_id: str, count: int = 20) -> list: ...
    async def get_file_sync(self, file_id: str) -> dict: ...
    async def download_file_sync(self, thread_count: int, headers: dict, url: str) -> bytes: ...

    # 账号管理
    async def set_qq_profile(self, **kwargs) -> bool: ...
    async def set_online_status(self, status: str) -> bool: ...
    async def set_qq_avatar(self, url: str) -> bool: ...
    async def send_like(self, user_id: str, times: int = 1) -> bool: ...
    async def set_group_admin(self, group_id: str, user_id: str, enable: bool) -> bool: ...
    async def set_friend_add_request(self, flag: str, approve: bool, remark: str = "") -> bool: ...

    # 透传
    async def call_raw_api(self, func_name: str, **params) -> Any: ...
```

**总方法数**：约 20 个。覆盖 commands.py 中所有 30+ 种 `bot.api.*` 调用 + ai_commands.py + heartbeat.py + message_middleware.py + tts_handler.py + server.py。

#### 2.2.3 全局后端注册

```python
_active_backend: Optional[BotBackend] = None

def set_backend(backend: BotBackend) -> None:
    global _active_backend
    _active_backend = backend

def get_backend() -> BotBackend:
    if _active_backend is None:
        raise RuntimeError("Bot backend not initialized. Call set_backend() first.")
    return _active_backend
```

**说明**：
- 全局单例，bot.py 启动时 `set_backend()` 一次
- 与现有全局 `bot` 风格一致，避免引入 contextvars
- 启动前调用 `get_backend()` 抛 `RuntimeError`（明确失败）

## 3. 后端实现

### 3.1 `NcatbotBackend`（包装现有 ncatbot BotClient）

**新文件**：`nbot/backends/ncatbot_backend.py`（约 350 行）

**核心职责**：
1. 包装 `BotClient()` 实例
2. 事件转换：把 `GroupMessage/PrivateMessage` → `IncomingMessage`
3. API 包装：把 `bot.api.post_*` → `backend.send_*`

**关键代码骨架**：

```python
class NcatbotBackend:
    name = "ncatbot"
    is_running = False

    def __init__(self):
        self.bot = BotClient()
        self._dispatch_callback = None

    def set_dispatcher(self, callback):
        self._dispatch_callback = callback

    async def start(self):
        from nbot.commands import handle_incoming_message
        self.bot.add_group_event_handler(self._wrap_group)
        self.bot.add_private_event_handler(self._wrap_private)
        self.is_running = True

    async def _wrap_group(self, msg: GroupMessage):
        incoming = self._to_incoming(msg, Scene.GROUP)
        if self._dispatch_callback:
            await self._dispatch_callback(incoming)

    async def _wrap_private(self, msg: PrivateMessage):
        incoming = self._to_incoming(msg, Scene.PRIVATE)
        if self._dispatch_callback:
            await self._dispatch_callback(incoming)

    def _to_incoming(self, msg, scene: Scene) -> IncomingMessage:
        return IncomingMessage(
            scene=scene,
            user_id=str(msg.user_id),
            group_id=str(msg.group_id) if scene == Scene.GROUP else "",
            text=msg.raw_message,
            sender_name=msg.sender.nickname if hasattr(msg, 'sender') else "",
            message_id=str(getattr(msg, 'message_id', '')),
            is_mentioned=self._detect_mention(msg),
            raw_message=msg,
            backend_name="ncatbot",
        )

    def _detect_mention(self, msg) -> bool:
        """检测消息是否 @机器人"""
        try:
            at_segments = [s for s in msg.message if s.get('type') == 'at']
            return any(s.get('data', {}).get('qq') == str(msg.self_id)
                       for s in at_segments)
        except Exception:
            return False

    async def run_forever(self):
        """ncatbot BotClient.run() 内部管理事件循环，阻塞"""
        self.bot.run(enable_webui_interaction=False)

    async def stop(self):
        self.is_running = False

    # ---- BotBackend 协议方法（包装 bot.api）----
    async def send_private_text(self, user_id, text):
        return await self.bot.api.post_private_msg(user_id=user_id, text=text)

    async def send_group_text(self, group_id, text):
        return await self.bot.api.post_group_msg(group_id=group_id, text=text)

    # ... 其他 18 个方法类似包装
    async def call_raw_api(self, func_name, **params):
        """透传 ncatbot 原生 API（用于 /bot 动态命令）"""
        method = getattr(self.bot.api, func_name)
        return await method(**params)
```

**保留事项**：
- `BotAPI`/`GroupMessage.reply`/`PrivateMessage.reply` 的 monkey-patch **原状保留**（消息持久化自动记录是业务逻辑）
- `BotClient` 事件循环不替换
- 现有 60+ 命令函数业务逻辑不修改

### 3.2 `QQBotBackend`（包装现有 QQBotService）

**新文件**：`nbot/backends/qqbot_backend.py`（约 250 行）

**核心职责**：
1. 包装 `QQBotWebSocketService` WebSocket 客户端
2. 事件转换：把 OpenAPI v2 dispatch event → `IncomingMessage`
3. 复用 `send_qqbot_message()` REST API

**关键代码骨架**：

```python
class QQBotBackend:
    name = "qqbot"
    is_running = False

    def __init__(self, app_id: str, app_secret: str,
                 sandbox: bool = False, api_base: str = ""):
        self._creds = {"app_id": app_id, "app_secret": app_secret,
                       "sandbox": sandbox, "api_base": api_base}
        self._ws_service = None
        self._dispatch_callback = None
        self._token = None
        self._api_base = api_base or (
            "https://sandbox.api.sgroup.qq.com" if sandbox
            else "https://api.sgroup.qq.com"
        )

    def set_dispatcher(self, callback):
        self._dispatch_callback = callback

    async def start(self):
        from nbot.services.qqbot_service import (
            get_app_access_token, get_gateway,
            QQBotWebSocketService
        )
        self._token = get_app_access_token(
            self._creds["app_id"], self._creds["app_secret"]
        )
        gateway_url = get_gateway(self._token)
        self._ws_service = QQBotWebSocketService(
            gateway_url, self._token, on_event=self._on_dispatch
        )
        self._ws_service.start()  # 启动独立线程
        self.is_running = True

    def _on_dispatch(self, raw_event: dict):
        """WebSocket 推来的事件 → IncomingMessage → 推给 dispatcher"""
        from nbot.channels.qqbot import QQBotChannelAdapter
        adapter = QQBotChannelAdapter(bot_appid=self._creds["app_id"])
        parsed = adapter.parse_event(raw_event)
        if parsed is None:
            return
        metadata = parsed.get("metadata", {})
        scene = Scene.GROUP if metadata.get("qqbot_scene") == "group" else Scene.PRIVATE
        incoming = IncomingMessage(
            scene=scene,
            user_id=parsed.get("user_id", ""),
            group_id=metadata.get("qqbot_group_openid", ""),
            text=parsed.get("content", ""),
            sender_name=parsed.get("sender", ""),
            message_id=parsed.get("message_id", ""),
            is_mentioned=metadata.get("is_mentioned", False),
            raw_message=raw_event,
            backend_name="qqbot",
            metadata=metadata,
        )
        if self._dispatch_callback:
            asyncio.create_task(self._dispatch_callback(incoming))

    async def run_forever(self):
        """WebSocket 主循环，阻塞"""
        if self._ws_service:
            self._ws_service.run_forever()

    async def stop(self):
        self.is_running = False
        if self._ws_service:
            self._ws_service.stop()

    # ---- BotBackend 协议方法 ----
    async def send_private_text(self, user_id, text):
        from nbot.services.qqbot_service import send_qqbot_message
        return send_qqbot_message(
            self._token, "private", user_id, text, api_base=self._api_base
        )

    async def send_group_text(self, group_id, text):
        from nbot.services.qqbot_service import send_qqbot_message
        return send_qqbot_message(
            self._token, "group", group_id, text, api_base=self._api_base
        )

    # ... 其他 18 个方法

    async def call_raw_api(self, func_name, **params):
        """QQBot 不支持原生透传，返回 None + warning"""
        _log.warning("QQBot backend does not support raw API call: %s", func_name)
        return None
```

**`qqbot_service.py` 改动**：
- `answer_qqbot_event()` 约 100 行拆分：
  - 事件分发部分（`parse_event` → `IncomingMessage`）迁到 `QQBotBackend._on_dispatch`
  - 业务处理（AIPipeline、命令匹配、Web session 创建）保留为 `nbot/services/qqbot_dispatch.py` 的 `handle_qqbot_incoming()`
- `QQBotWebSocketService` 新增 `on_event` 回调参数（替代现有 `_handle_dispatch` 内联逻辑）
- `QQBotMessageAdapter`/`QQBotBotMock` **保留**（ai_commands.py 还在用，标记 deprecated）

## 4. bot.py 启动协调

### 4.1 新文件 `nbot/bot_runner.py`

```python
import os
import logging
from typing import Optional

_log = logging.getLogger(__name__)

def detect_backend() -> Optional[str]:
    """根据环境变量决定使用哪个后端。优先级: ncatbot > qqbot > None"""
    bot_uin = os.getenv("BOT_UIN", "").strip()
    ws_uri = os.getenv("WS_URI", "").strip()
    qqbot_app_id = os.getenv("QQBOT_APP_ID", "").strip()
    qqbot_app_secret = os.getenv("QQBOT_APP_SECRET", "").strip()

    has_ncatbot = bool(bot_uin and ws_uri)
    has_qqbot = bool(qqbot_app_id and qqbot_app_secret)

    if has_ncatbot and has_qqbot:
        _log.warning("Both ncatbot and qqbot configured; ncatbot takes precedence")
    if has_ncatbot:
        return "ncatbot"
    if has_qqbot:
        return "qqbot"
    return None

def create_backend(backend_name: str):
    if backend_name == "ncatbot":
        from nbot.backends.ncatbot_backend import NcatbotBackend
        from nbot.commands import _apply_runtime_ncatbot_config
        _apply_runtime_ncatbot_config()
        return NcatbotBackend()
    if backend_name == "qqbot":
        from nbot.backends.qqbot_backend import QQBotBackend
        return QQBotBackend(
            app_id=os.getenv("QQBOT_APP_ID"),
            app_secret=os.getenv("QQBOT_APP_SECRET"),
            sandbox=os.getenv("QQBOT_SANDBOX", "").lower() == "true",
            api_base=os.getenv("QQBOT_API_BASE", ""),
        )
    raise ValueError(f"Unknown backend: {backend_name}")
```

### 4.2 `bot.py` 改动（约 30 行）

```python
# 删除: _apply_runtime_ncatbot_config() 的直接调用
# 删除: _has_qq_bot_config() 的 ncatbot 风格判断

def run_bot():
    from nbot.bot_runner import detect_backend, create_backend
    from nbot.commands_backend import set_backend

    backend_name = detect_backend()
    if backend_name is None:
        _log.warning("No QQ bot backend configured (need BOT_UIN+WS_URI or QQBOT_APP_ID+QQBOT_APP_SECRET)")
        return

    _log.info("Starting NekoBot with backend: %s", backend_name)
    backend = create_backend(backend_name)
    set_backend(backend)

    # 注入 dispatcher: IncomingMessage → commands.handle_incoming_message
    async def dispatcher(incoming: IncomingMessage):
        from nbot.commands import handle_incoming_message
        await handle_incoming_message(incoming)
    backend.set_dispatcher(dispatcher)

    # Web server 端通过 backend 推送消息（兼容 server.py:2010 等处）
    _set_web_server_bot(backend)

    # 阻塞运行
    asyncio.run(backend.run_forever())
```

**主入口 `__main__` 改动**：

```python
# bot.py:691-707 (default branch) —— 简化为:
else:
    backend_name = detect_backend()
    if backend_name:
        _log.info("Starting NekoBot with Web Dashboard (backend=%s)...", backend_name)
        prepared = _prepare_web_server(bot=None)
        bot_thread = threading.Thread(target=run_bot, name=f"bot-{backend_name}", daemon=True)
        bot_thread.start()
        start_web_server(host=web_host, port=web_port, bot=None, prepared=prepared, ssl_context=ssl_context)
    else:
        _log.info("No QQ bot config found, starting Web Dashboard only...")
```

## 5. 配置项

### 5.1 `.env.example` 改动（双轨并列）

```env
# ==================== Bot 后端配置（双轨并列）====================
# 优先级: 同时配置时 ncatbot 优先；只配 QQBOT_* 则走 QQ Bot 官方

# ---- 选项 A: ncatbot + NapCat (旧版,保留向后兼容) ----
BOT_UIN=你的QQ号
ROOT=管理员QQ号
WS_URI=ws://你的NapCat地址:端口
TOKEN=你的NapCat令牌（可选）

# ---- 选项 B: QQ Bot 官方机器人（推荐,无需 NapCat）----
QQBOT_APP_ID=你的AppID
QQBOT_APP_SECRET=你的AppSecret
# 可选
QQBOT_SANDBOX=false
QQBOT_API_BASE=
```

### 5.2 `config.ini` 改动

```ini
[BotConfig]
# 旧版 ncatbot 配置（保留向后兼容）
bot_uin =
root =
ws_uri = ws://localhost:3001
token =

# 新版 QQ Bot 官方机器人配置（推荐）
qqbot_app_id =
qqbot_app_secret =
qqbot_sandbox = false
qqbot_api_base =
```

**读取兼容**：保留 `configparser` 读取 `[BotConfig]` 段，运行时通过 `os.getenv` 优先，fallback 到 `config.ini`。

## 6. commands.py 改造

### 6.1 保持不变

- 文件结构（仍单文件 ~5000 行）
- 60+ 命令函数主体业务逻辑
- `_dispatch_message` 命令路由逻辑
- `BotAPI`/`GroupMessage.reply` monkey-patch

### 6.2 改动点

#### 6.2.1 事件入口（顶部）

```python
# 删除:
async def handle_group_message(msg: GroupMessage): ...
async def handle_private_message(msg: PrivateMessage): ...

# 替换为:
async def handle_incoming_message(incoming: IncomingMessage):
    """统一事件入口 —— 由 backend 注入的 dispatcher 调用"""
    await dispatch_message(incoming)

# 删除:
if not hasattr(bot, '_nbot_handlers_registered'):
    bot.add_group_event_handler(handle_group_message)
    bot.add_private_event_handler(handle_private_message)
    bot._nbot_handlers_registered = True
# (这一段移到 NcatbotBackend.start() 中)
```

#### 6.2.2 全局 bot 引用

```python
# 删除:
bot = BotClient()
heartbeat_core = HeartbeatCore(bot.api)

# 替换为:
from nbot.commands_backend import get_backend, set_backend
# backend 通过 bot.py 启动时 set_backend() 注入
# HeartbeatCore 改为内部通过 get_backend() 获取
```

#### 6.2.3 消息分发（`dispatch_message`）

```python
# 旧:
async def dispatch_message(msg, is_group: bool):
    user_id = msg.user_id
    group_id = msg.group_id if is_group else ""
    raw = msg.raw_message
    sender_name = msg.sender.nickname
    ...

# 新:
async def dispatch_message(incoming: IncomingMessage):
    user_id = incoming.user_id
    group_id = incoming.group_id if incoming.is_group else ""
    raw = incoming.text
    sender_name = incoming.sender_name
    ...
```

#### 6.2.4 `bot.api.*` 批量替换（约 100+ 处机械替换）

| 原代码 | 新代码 |
|--------|--------|
| `await bot.api.post_private_msg(user_id=..., text=...)` | `await get_backend().send_private_text(user_id, text)` |
| `await bot.api.post_group_msg(group_id=..., text=...)` | `await get_backend().send_group_text(group_id, text)` |
| `await bot.api.post_group_msg(group_id=..., rtf=MessageChain([Record(p)]))` | `await get_backend().send_group_voice(group_id, p)` |
| `await bot.api.post_group_file(group_id=..., file=...)` | `await get_backend().send_group_file(group_id, file)` |
| `await bot.api.upload_private_file(user_id=..., file=...)` | `await get_backend().send_private_file(user_id, file)` |
| `await bot.api.set_qq_profile(...)` | `await get_backend().set_qq_profile(...)` |
| `await bot.api.set_online_status(...)` | `await get_backend().set_online_status(...)` |
| `await bot.api.set_qq_avatar(...)` | `await get_backend().set_qq_avatar(...)` |
| `await bot.api.send_like(...)` | `await get_backend().send_like(...)` |
| `await bot.api.set_group_admin(...)` | `await get_backend().set_group_admin(...)` |
| `await bot.api.set_friend_add_request(...)` | `await get_backend().set_friend_add_request(...)` |
| `await bot.api.get_group_msg_history(...)` | `await get_backend().get_group_msg_history(...)` |
| `getattr(bot.api, func_name)(**params)` | `await get_backend().call_raw_api(func_name, **params)` |

| 原代码（msg 对象） | 新代码（incoming） |
|--------|--------|
| `msg.user_id` | `incoming.user_id` |
| `msg.group_id` | `incoming.group_id` |
| `msg.raw_message` | `incoming.text` |
| `msg.sender.nickname` | `incoming.sender_name` |
| `msg.message_id` | `incoming.message_id` |
| `msg.reply("text")` | `await incoming.reply("text")` |

### 6.3 `ai_commands.py` 改动

**`commands.py` 已删除全局 `bot` 引用**（见 §6.2.2），但 `ai_commands.py` 仍需要 backend 引用。

```python
# 旧 (ai_commands.py):
def register_ai_commands(bot=None, ...):
    self.bot = bot
    ...
    await self.bot.api.post_private_msg(...)

# 新 (ai_commands.py):
def register_ai_commands(backend=None, ...):
    self.backend = backend
    ...
    await self.backend.send_private_text(...)
```

**`commands.py` 全局状态约定**：
- `commands.py` **删除** `bot = BotClient()` 全局（由 §6.2.2）
- `commands.py` **不新增** `backend = None` 全局（命令函数统一通过 `get_backend()` 获取）
- `ai_commands.py` **保留** `self.backend` 实例属性（每个命令 handler 实例一个）
- `nbot/services/qqbot_service.py` 的 `_handle_qqbot_command` 中的 monkey-patch **保留**（`cmd_module.bot = adapter.bot`），仅用于兼容 ai_commands.py 内部的 `_bot_instance` 引用，**不影响** commands.py

### 6.4 `nbot/core/heartbeat.py` 改动

```python
# 旧 (line 37 - 疑似 bug):
from ncatbot.services.ai import ai_client
# 旧 (line 174):
await self.bot_api.post_private_msg(int(user_id), text=msg_text)

# 新:
from nbot.services.ai import ai_client   # 修正为 nbot
class HeartbeatCore:
    def __init__(self):
        # 移除 bot_api 参数,内部通过 get_backend() 获取
        pass
    async def send_to_user(self, user_id, text):
        backend = get_backend()
        await backend.send_private_text(str(user_id), text)
```

### 6.5 `nbot/services/tts.py` 改动

```python
# 旧 (line 80):
from ncatbot.core.element import MessageChain, Record
def tts(text):
    audio = synthesize(text)
    return MessageChain([Record(audio)])

# 新:
async def tts(text, target_id, is_group=True):
    audio = synthesize(text)
    backend = get_backend()
    if is_group:
        await backend.send_group_voice(target_id, audio)
    else:
        # QQBot 不支持私聊语音,降级为文本
        await backend.send_private_text(target_id, "[语音消息]")
```

### 6.6 `nbot/gateway/tts_handler.py` 改动

```python
# 旧 (line 97, 122-125):
from ncatbot.core.element import MessageChain, Record
await self._qq_bot.api.post_group_msg(group_id=target_id, rtf=MessageChain([Record(path)]))

# 新:
from nbot.commands_backend import get_backend
backend = get_backend()
await backend.send_group_voice(target_id, path)
```

### 6.7 `nbot/core/message_middleware.py` 改动

```python
# 旧 (line 460, 544):
await bot.api.get_file_sync(file_id)
await bot.api.download_file_sync(thread_count, headers, url)

# 新:
from nbot.commands_backend import get_backend
backend = get_backend()
await backend.get_file_sync(file_id)
await backend.download_file_sync(thread_count, headers, url)
```

### 6.8 `nbot/web/server.py` 改动

```python
# 旧 (line 2010, 2017, 2019):
if self.qq_bot and qq_id:
    await self.qq_bot.api.post_group_msg(group_id=qq_id, text=...)
    await self.qq_bot.api.post_private_msg(user_id=qq_id, text=...)

# 新:
from nbot.commands_backend import get_backend
backend = get_backend()
if backend and qq_id:
    await backend.send_group_text(qq_id, ...)
    await backend.send_private_text(qq_id, ...)
```

`_set_web_server_bot(backend)` 替换现有的 `_set_web_server_bot(bot)`（已存在于 bot.py:255-265）。

## 7. 数据流

### 7.1 启动时

```
bot.py main()
  └─ run_bot()
       ├─ detect_backend() → "ncatbot" | "qqbot" | None
       ├─ create_backend(name) → BotBackend instance
       ├─ set_backend(backend) [global]
       ├─ backend.set_dispatcher(dispatcher)
       │    └─ dispatcher(incoming) = handle_incoming_message
       ├─ _set_web_server_bot(backend) [for web push]
       └─ backend.run_forever() [blocking — 不外层包 asyncio.run]
              ├─ NcatbotBackend.run_forever() → self.bot.run()  (ncatbot 内部管理事件循环)
              └─ QQBotBackend.run_forever() → self._ws_service.run_forever()  (独立线程)
```

### 7.2 ncatbot 路径

```
NapCatQQ WebSocket
  → ncatbot.BotClient event loop
  → NcatbotBackend._wrap_group(msg: GroupMessage)
  → _to_incoming(msg, Scene.GROUP)
  → dispatcher(incoming)
  → commands.handle_incoming_message(incoming)
  → dispatch_message(incoming)
  → 60+ 命令函数 [通过 get_backend().send_* 发回]
  → NcatbotBackend.send_group_text(...)
  → self.bot.api.post_group_msg(...)
  → ncatbot → NapCatQQ WebSocket → QQ server
```

### 7.3 QQBot 路径

```
QQ OpenAPI WebSocket (api.sgroup.qq.com)
  → QQBotWebSocketService 收到 OP_DISPATCH
  → QQBotBackend._on_dispatch(raw_event)
  → QQBotChannelAdapter.parse_event(raw_event) → parsed dict
  → 转 IncomingMessage
  → dispatcher(incoming)
  → commands.handle_incoming_message(incoming)
  → dispatch_message(incoming)
  → 60+ 命令函数 [通过 get_backend().send_* 发回]
  → QQBotBackend.send_group_text(...)
  → send_qqbot_message(token, "group", group_id, text)
  → REST POST https://api.sgroup.qq.com/v2/groups/{group_openid}/messages
  → QQ server
```

## 8. 测试策略

### 8.1 单元测试

**新文件**：`tests/test_commands_backend.py`

```python
import asyncio
import pytest
from nbot.commands_backend import (
    IncomingMessage, Scene, set_backend, get_backend
)

class FakeBackend:
    name = "fake"
    sent = []
    is_running = True
    async def start(self): pass
    async def stop(self): pass
    async def run_forever(self): pass
    async def send_private_text(self, user_id, text):
        self.sent.append(("private", user_id, text)); return True
    async def send_group_text(self, group_id, text):
        self.sent.append(("group", group_id, text)); return True
    # ... 其他 17 个方法

def test_incoming_message_reply_uses_group_path():
    fb = FakeBackend(); set_backend(fb)
    inc = IncomingMessage(scene=Scene.GROUP, user_id="u1", group_id="g1", text="hi")
    asyncio.run(inc.reply("hello"))
    assert fb.sent == [("group", "g1", "hello")]

def test_incoming_message_reply_uses_private_path():
    fb = FakeBackend(); set_backend(fb)
    inc = IncomingMessage(scene=Scene.PRIVATE, user_id="u1", text="hi")
    asyncio.run(inc.reply("hello"))
    assert fb.sent == [("private", "u1", "hello")]

def test_get_backend_before_set_raises():
    from nbot import commands_backend
    commands_backend._active_backend = None
    with pytest.raises(RuntimeError):
        get_backend()
```

**新文件**：`tests/test_backend_ncatbot.py`（mock `BotClient`）

```python
def test_to_incoming_group_message():
    from nbot.backends.ncatbot_backend import NcatbotBackend
    from unittest.mock import MagicMock
    backend = NcatbotBackend.__new__(NcatbotBackend)  # skip __init__
    backend.bot = MagicMock()
    msg = MagicMock()
    msg.user_id = "123"; msg.group_id = "456"
    msg.raw_message = "hello"; msg.sender.nickname = "Alice"
    msg.message_id = "m1"; msg.self_id = "999"
    msg.message = []  # no at
    inc = backend._to_incoming(msg, Scene.GROUP)
    assert inc.user_id == "123"
    assert inc.group_id == "456"
    assert inc.text == "hello"
    assert inc.sender_name == "Alice"
    assert inc.scene == Scene.GROUP
    assert inc.is_mentioned == False
```

**新文件**：`tests/test_backend_qqbot.py`

```python
def test_on_dispatch_private_message():
    from nbot.backends.qqbot_backend import QQBotBackend
    from unittest.mock import MagicMock
    backend = QQBotBackend.__new__(QQBotBackend)
    backend._creds = {"app_id": "test_id"}
    backend._dispatch_callback = MagicMock()
    raw_event = {
        "t": "C2C_MESSAGE_CREATE",
        "d": {
            "id": "msg_1", "content": "hello",
            "author": {"user_openid": "u_openid_1", "username": "Alice"},
        }
    }
    backend._on_dispatch(raw_event)
    # 验证 dispatcher 被调用(IncomingMessage 包含正确字段)
```

### 8.2 集成测试（手动）

启动命令：
```bash
# ncatbot 模式
BOT_UIN=xxx WS_URI=ws://localhost:3001 python bot.py

# QQBot 模式
QQBOT_APP_ID=xxx QQBOT_APP_SECRET=xxx python bot.py

# 同时启动（ncatbot 优先）
BOT_UIN=xxx WS_URI=ws://localhost:3001 QQBOT_APP_ID=xxx QQBOT_APP_SECRET=xxx python bot.py
```

回归测试（每条命令至少跑通一次）：
- `/jmrank` `/jm_search` —— 漫画
- `/email` —— 邮箱
- `/roll` `/dice` —— 骰子
- `/emoji` —— 表情包
- `/setadmin` `/admin` —— 管理
- AI 对话（私聊 + 群 @）—— 核心
- TTS 语音消息

### 8.3 CI 检查

保留现有 CI：
1. `ruff check . --select E9,F63,F7,F82`
2. `python -m compileall -q bot.py nbot tools`
3. `python -m pip install -r requirements.txt`
4. `python -m pytest -q`

新增测试运行：
```bash
python -m pytest tests/test_commands_backend.py tests/test_backend_ncatbot.py tests/test_backend_qqbot.py -q
```

## 9. 错误处理 & 边界情况

| 场景 | 处理 |
|------|------|
| 两个后端都没配置 | `detect_backend()` 返回 `None`，`run_bot()` 警告并退出 QQ bot 线程 |
| 两个后端都配置了 | ncatbot 优先 + 警告日志 |
| `backend` 未启动时命令系统调用 `get_backend()` | 抛 `RuntimeError`，提示调用 `set_backend()` |
| QQBot token 过期 | 捕获 401 → 自动刷新 token → 重试一次（保留 `get_app_access_token` 逻辑） |
| ncatbot 断开重连 | 保留 ncatbot 自身重连机制，不在 BotBackend 层重试 |
| 消息发送失败 | 后端 `send_xxx` 返回 `False`，命令函数检查并打日志（不抛异常） |
| Web 端推送消息 | `_set_web_server_bot(backend)` 注入 backend，`self.qq_bot.api.*` → `backend.*` |
| `IncomingMessage.reply()` 时 backend 已 stop | `get_backend()` 返回的对象仍可用，`send_xxx` 会失败，由调用方处理 |
| `/bot` 动态 API 命令 | `getattr(bot.api, name)(**params)` → `await get_backend().call_raw_api(name, **params)` |
| QQBot `call_raw_api` | 不支持，返回 `None` + 警告日志 |
| ncatbot 用户的旧 `.env` 无 `QQBOT_*` 配置 | 完全兼容，行为不变 |
| QQBot 用户的 `.env` 无 `BOT_UIN`/`WS_URI` 配置 | 完全兼容，走 QQBot 路径 |

## 10. 实施步骤（高层概览，详细计划在 writing-plans 阶段产出）

按依赖关系排序，每步可独立验证：

1. **新增核心抽象层**：创建 `nbot/commands_backend.py`（`IncomingMessage` + `BotBackend` Protocol + 全局 getter/setter）
2. **新增 ncatbot 后端**：创建 `nbot/backends/__init__.py` + `nbot/backends/ncatbot_backend.py`
3. **新增 QQBot 后端**：创建 `nbot/backends/qqbot_backend.py`，重构 `qqbot_service.py` 的 `answer_qqbot_event()`
4. **新增启动协调**：创建 `nbot/bot_runner.py`，改造 `bot.py` 的 `run_bot()` 和主入口
5. **改造 commands.py 事件入口**：替换 `handle_group_message/handle_private_message` → `handle_incoming_message`
6. **改造 commands.py 全局 bot 引用**：删除 `bot = BotClient()`、`heartbeat_core = HeartbeatCore(bot.api)`
7. **改造 commands.py 消息分发**：替换 `dispatch_message(msg, is_group)` → `dispatch_message(incoming)`
8. **批量替换 commands.py 中 `bot.api.*` 调用**（约 100+ 处机械替换）
9. **批量替换 commands.py 中 `msg.xxx` 属性访问**（约 100+ 处机械替换）
10. **改造 `ai_commands.py`**：`register_ai_commands(bot=...)` → `register_ai_commands(backend=...)`
11. **改造 `nbot/core/heartbeat.py`**：修正 `ncatbot.services.ai` bug（`nbot.services.ai`），`bot_api` 参数 → `get_backend()`
12. **改造 `nbot/services/tts.py`**：删除 `MessageChain`/`Record` 依赖，调用 `backend.send_*_voice()`
13. **改造 `nbot/gateway/tts_handler.py`**：同上
14. **改造 `nbot/core/message_middleware.py`**：`bot.api.get_file_sync/download_file_sync` → `backend.*`
15. **改造 `nbot/web/server.py`**：`self.qq_bot.api.*` → `backend.*`
16. **更新 `.env.example`**：双轨并列模板
17. **更新 `config.ini`**：双轨并列字段
18. **新增测试**：`tests/test_commands_backend.py` + `tests/test_backend_ncatbot.py` + `tests/test_backend_qqbot.py`
19. **手动回归测试**：ncatbot 模式 + QQBot 模式分别跑通核心命令
20. **CI 验证**：`ruff check . && python -m compileall -q bot.py nbot tools && python -m pytest -q`

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `commands.py` 100+ 处替换引入回归 bug | 高 | 分批替换 + 每批跑回归测试 + 保留 monkey-patch 作为兜底 |
| `IncomingMessage` dataclass 字段不足覆盖所有命令用法 | 中 | 先 grep `msg.\w+` 列出所有属性,确保 dataclass 字段完整 |
| ncatbot `BotClient.run()` 与 `asyncio.run()` 冲突 | 高 | ncatbot backend 的 `run_forever` 直接调 `bot.run()`,**不**包 `asyncio.run`(避免双事件循环) |
| QQBot `run_forever` 与 `asyncio.run()` 冲突 | 中 | QQBot backend 的 `run_forever` 内部已用独立线程,直接调 `self._ws_service.run_forever()` |
| 老用户升级时命令行为变化 | 中 | monkey-patch 保留 + IncomingMessage.reply() 语义兼容 `msg.reply()` |
| `register_ai_commands` 全局 bot 引用破环 | 中 | 同时维护 `bot` 和 `_backend` 全局,monkey-patch 兼容 |
| `tts.py` 删除 `MessageChain` 后 QQBot 不支持私聊语音 | 低 | 降级为文本提示,不抛异常 |

## 12. 验收标准

1. ✅ `python bot.py` 在仅有 `BOT_UIN`+`WS_URI` 时正常运行（ncatbot 模式）
2. ✅ `python bot.py` 在仅有 `QQBOT_APP_ID`+`QQBOT_APP_SECRET` 时正常运行（QQBot 模式）
3. ✅ 60+ 命令在两种模式下行为一致
4. ✅ `tests/test_commands_backend.py` 全部通过
5. ✅ `ruff check .` 无新增警告
6. ✅ `python -m compileall -q bot.py nbot tools` 无错误
7. ✅ `python -m pytest -q` 全部通过
8. ✅ `nbot/commands.py` 不再有 `import ncatbot`（`ncatbot.core` / `ncatbot.core.element` / `ncatbot.utils.*`）
9. ✅ `nbot/services/tts.py` 不再有 `import ncatbot`
10. ✅ `nbot/gateway/tts_handler.py` 不再有 `import ncatbot`
11. ✅ `nbot/core/heartbeat.py` 不再有 `import ncatbot`
12. ✅ `nbot/core/message_middleware.py` 不再有 `from nbot.commands import bot` 直接使用 `bot.api.*`
13. ✅ `nbot/web/server.py` 不再有 `self.qq_bot.api.*`
14. ✅ `.env.example` 包含双轨配置项
15. ✅ `config.ini` 包含双轨配置段

## 13. 后续工作（不在本次范围）

- 完全移除 ncatbot 依赖（当所有用户都迁移到 QQBot 后）
- 拆分 `commands.py` 4989 行单文件
- 统一 `nbot/services/qqbot_service.py` 与 `nbot/backends/qqbot_backend.py` 的边界（消除重复的 WebSocket 管理）
- 用 `botpy` 官方 SDK 替换手写的 `requests` + `websocket-client`（如果官方 SDK 成熟）
- 引入 `contextvars` 替代全局 `get_backend()`（如未来需要多 backend 并存）
