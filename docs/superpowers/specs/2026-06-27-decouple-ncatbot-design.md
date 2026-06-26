# Ncatbot 解耦与 QQ Bot 官方频道接入设计

**Date**: 2026-06-27
**Status**: Draft — pending user review (rev. 2)
**Author**: Brainstorming session output

## 1. 背景与目标

### 1.1 现状

NekoBot 当前通过 [ncatbot](https://github.com/liyihao1110/ncatbot) + [NapCatQQ](https://github.com/NapNeko/NapCatQQ) 接入 QQ。ncatbot 3.8.5 是基于 OneBot v11 协议（NapCat WebSocket）的 Python 框架，依赖第三方 QQ 客户端运行。

项目同时已实现 **`nbot/channels/qqbot.py`**（231 行 Channel Adapter）和 **`nbot/services/qqbot_service.py`**（689 行 WebSocket 客户端）——这是一套完全独立、基于 QQ 开放平台 OpenAPI v2 协议（app_id + app_secret 鉴权）、直连 `api.sgroup.qq.com` 的官方机器人实现。该实现已可用，但与现有命令系统（`nbot/commands.py`）未打通。

### 1.2 目标

1. 让 `commands.py` 中的核心命令（文本类）可以同时跑在 ncatbot 和 QQBot 两个后端上
2. 配置文件支持 `app_id` + `app_secret` 作为新主推方案，与 `bot_uin` + `ws_uri` 并存
3. 保留对老 ncatbot 用户的向后兼容
4. 引入 `BotBackend` 多层 Protocol 抽象，分阶段消除 `commands.py` 中对 ncatbot 的硬依赖

### 1.3 非目标

- 不完全移除 ncatbot 依赖（保留为可选项）
- 不拆分 `commands.py` 4989 行单文件
- 不重写 QQ Bot 业务逻辑（保留 `qqbot_service.py` 现有实现）
- 不引入第三方 QQ Bot SDK（如 `botpy`），仍用 `requests` + `websocket-client`
- **第一阶段不追求所有命令两端能力一致**，只保证核心文本命令可路由

### 1.4 关键设计修正（rev. 2）

> 在 brainstorming review 后修正：
> 1. `BotBackend` 拆分为多层 Protocol（核心 / Media / NcatbotAdmin / RawApi）
> 2. `run_forever()` 改为同步方法（不 async），避免与 ncatbot BotClient 内部事件循环冲突
> 3. `IncomingMessage.reply()` 第一版只支持文本，富媒体走 backend 显式方法
> 4. QQBot WebSocket 线程回调使用 `asyncio.run_coroutine_threadsafe`，避免 `no running event loop`
> 5. 实施拆为 4 个渐进阶段，每阶段可独立交付

## 2. 核心设计：分层 Protocol + 能力检测

### 2.1 设计原则

- **Platform-neutral 命令系统**：`commands.py` 不直接导入 ncatbot 类型
- **分层 Protocol 而非万能接口**：核心 / 媒体 / 管理 / 透传各为独立 Protocol，避免 QQBotBackend 出现大量"假实现"
- **能力检测代替全方法实现**：命令侧用 `isinstance(backend, MediaBackend)` 或 `backend.supports("group_voice")` 判断能力
- **最小破坏面**：保留 ncatbot 事件循环、BotAPI monkey-patch、QQBot 现有 service 层
- **配置驱动**：根据环境变量自动选择后端

### 2.2 `IncomingMessage`（入站消息数据类）

**新文件**：`nbot/commands_backend.py`

```python
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

class Scene(str, Enum):
    GROUP = "group"
    PRIVATE = "private"


@dataclass
class IncomingMessage:
    """统一入站消息格式 —— 替代 ncatbot 的 msg 对象

    rev. 2 简化：第一版 reply() 只支持文本，富媒体走 backend 显式方法。
    """
    scene: Scene
    user_id: str
    text: str = ""
    group_id: str = ""
    sender_name: str = ""
    message_id: str = ""
    is_mentioned: bool = False
    raw_message: Any = None           # 原生对象(ncatbot GroupMessage / qqbot dict)
    backend_name: str = "unknown"
    metadata: dict = field(default_factory=dict)

    @property
    def is_group(self) -> bool:
        return self.scene == Scene.GROUP

    async def reply(self, text: str) -> bool:
        """便捷文本回复 —— 自动选择私聊/群聊路径

        rev. 2: 第一版只支持 text 富媒体请用 backend.send_group_image 等显式方法
        """
        from nbot.commands_backend import get_backend
        backend = get_backend()
        if self.is_group:
            return await backend.send_group_text(self.group_id, text)
        return await backend.send_private_text(self.user_id, text)
```

**关键约束**：
- `reply()` 只接受 `text` 参数
- `reply_image()` / `reply_voice()` / `reply_file()` 不在第一版提供，使用方显式调用 `backend.send_*_*()`

### 2.3 分层 Protocol 定义

```python
from typing import Protocol, runtime_checkable, Any


@runtime_checkable
class BotBackend(Protocol):
    """核心 BotBackend —— 所有后端必须实现

    rev. 2: run_forever() 是同步方法，由 backend 内部决定如何阻塞
            不外层包 asyncio.run()，避免与 ncatbot BotClient 内部事件循环冲突
    """
    name: str
    is_running: bool

    async def start(self) -> None:
        """异步初始化：建立连接、获取 token 等"""
        ...

    def run_forever(self) -> None:
        """同步阻塞入口：ncatbot 由 bot.run() 阻塞；QQBot 由 WebSocketApp.run_forever() 阻塞"""
        ...

    async def stop(self) -> None:
        """异步停止"""
        ...

    # ---- 核心文本能力（所有后端必须实现）----
    async def send_private_text(self, user_id: str, text: str) -> bool: ...
    async def send_group_text(self, group_id: str, text: str) -> bool: ...

    # ---- 能力检测（所有后端必须实现）----
    def supports(self, capability: str) -> bool: ...


@runtime_checkable
class MediaBackend(Protocol):
    """富媒体能力（可选）—— ncatbotBackend 实现，QQBotBackend 不实现"""
    async def send_private_image(self, user_id: str, image_path: str) -> bool: ...
    async def send_group_image(self, group_id: str, image_path: str) -> bool: ...
    async def send_group_voice(self, group_id: str, voice_path: str) -> bool: ...
    async def send_group_file(self, group_id: str, file_path: str) -> bool: ...
    async def send_private_file(self, user_id: str, file_path: str) -> bool: ...
    async def reply_message(self, message_id: str, text: str, *,
                            is_group: bool = False, target_id: str = "") -> bool: ...


@runtime_checkable
class NcatbotAdminBackend(Protocol):
    """ncatbot / OneBot 专属管理能力（ncatbotBackend 实现，QQBotBackend 不实现）

    rev. 2: 拆出独立 Protocol，避免 QQBotBackend 假实现
    """
    async def set_qq_profile(self, **kwargs) -> bool: ...
    async def set_online_status(self, status: str) -> bool: ...
    async def set_qq_avatar(self, url: str) -> bool: ...
    async def send_like(self, user_id: str, times: int = 1) -> bool: ...
    async def set_group_admin(self, group_id: str, user_id: str, enable: bool) -> bool: ...
    async def set_friend_add_request(self, flag: str, approve: bool, remark: str = "") -> bool: ...
    async def get_group_msg_history(self, group_id: str, count: int = 20) -> list: ...
    async def get_file_sync(self, file_id: str) -> dict: ...
    async def download_file_sync(self, thread_count: int, headers: dict, url: str) -> bytes: ...


@runtime_checkable
class RawApiBackend(Protocol):
    """透传原生 API（ncatbotBackend 实现，QQBotBackend 不实现）"""
    async def call_raw_api(self, func_name: str, **params) -> Any: ...


# 能力字符串常量（用于 supports()）
class Capability:
    GROUP_IMAGE = "group_image"
    GROUP_VOICE = "group_voice"
    GROUP_FILE = "group_file"
    PRIVATE_IMAGE = "private_image"
    PRIVATE_FILE = "private_file"
    REPLY_MESSAGE = "reply_message"
    SET_QQ_PROFILE = "set_qq_profile"
    SET_QQ_AVATAR = "set_qq_avatar"
    SEND_LIKE = "send_like"
    SET_GROUP_ADMIN = "set_group_admin"
    GET_GROUP_HISTORY = "get_group_history"
    FILE_DOWNLOAD = "file_download"
    RAW_API = "raw_api"
```

### 2.4 全局后端注册

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

### 2.5 命令侧能力判断模式

```python
# 命令函数内部模式 A：Protocol isinstance 判断（推荐）
from nbot.commands_backend import MediaBackend

async def cmd_send_image(incoming: IncomingMessage, image_path: str):
    backend = get_backend()
    if not isinstance(backend, MediaBackend):
        await incoming.reply("当前后端不支持发送图片")
        return
    if incoming.is_group:
        await backend.send_group_image(incoming.group_id, image_path)
    else:
        await backend.send_private_image(incoming.user_id, image_path)


# 命令函数内部模式 B：supports() 字符串判断
async def cmd_send_voice(incoming: IncomingMessage, voice_path: str):
    backend = get_backend()
    if not backend.supports(Capability.GROUP_VOICE):
        await incoming.reply("当前后端不支持语音消息")
        return
    await backend.send_group_voice(incoming.group_id, voice_path)
```

**两种模式选型建议**：
- 能力组合判断（≥2 个方法）→ `isinstance` 更类型安全
- 单能力开关 → `supports()` 更轻量
- 项目内统一一种风格（推荐 `isinstance`）

## 3. 后端实现

### 3.1 `NcatbotBackend`（包装现有 ncatbot BotClient）

**新文件**：`nbot/backends/ncatbot_backend.py`（约 350 行）

**目标实现 4 个 Protocol**：BotBackend + MediaBackend + NcatbotAdminBackend + RawApiBackend

**按阶段补全**：
- **阶段 1**：仅实现 `BotBackend` 核心（`start` / `run_forever` / `stop` / `send_*_text` / `supports`）
- **阶段 2**：补全 `NcatbotAdminBackend`（管理能力）+ `RawApiBackend`（`call_raw_api`）
- **阶段 3**：补全 `MediaBackend`（富媒体）
- 每个阶段未实现的方法保留为返回 `False` 的空实现，确保 isinstance 判断在该阶段不命中

```python
class NcatbotBackend:
    name = "ncatbot"
    is_running = False

    def __init__(self):
        from ncatbot.core import BotClient
        self.bot = BotClient()
        self._dispatch_callback = None

    def set_dispatcher(self, callback):
        self._dispatch_callback = callback

    # ---- BotBackend ----
    async def start(self):
        from nbot.commands import handle_incoming_message
        self.bot.add_group_event_handler(self._wrap_group)
        self.bot.add_private_event_handler(self._wrap_private)
        self.is_running = True

    def run_forever(self):
        """同步阻塞 —— ncatbot BotClient.run() 内部管理事件循环

        rev. 2: 不返回,直接阻塞。bot.py 不要外层包 asyncio.run()
        """
        self.bot.run(enable_webui_interaction=False)

    async def stop(self):
        self.is_running = False

    async def send_private_text(self, user_id, text):
        return await self.bot.api.post_private_msg(user_id=user_id, text=text)

    async def send_group_text(self, group_id, text):
        return await self.bot.api.post_group_msg(group_id=group_id, text=text)

    def supports(self, capability: str) -> bool:
        # ncatbot 实现所有能力
        return True

    # ---- MediaBackend ----
    async def send_group_image(self, group_id, image_path): ...
    async def send_private_image(self, user_id, image_path): ...
    async def send_group_voice(self, group_id, voice_path): ...
    async def send_group_file(self, group_id, file_path): ...
    async def send_private_file(self, user_id, file_path): ...
    async def reply_message(self, message_id, text, *, is_group=False, target_id=""): ...

    # ---- NcatbotAdminBackend ----
    async def set_qq_profile(self, **kwargs): ...
    async def set_online_status(self, status): ...
    # ... 其他 7 个方法

    # ---- RawApiBackend ----
    async def call_raw_api(self, func_name, **params):
        method = getattr(self.bot.api, func_name)
        return await method(**params)

    # ---- 事件转换 ----
    async def _wrap_group(self, msg):
        incoming = self._to_incoming(msg, Scene.GROUP)
        if self._dispatch_callback:
            await self._dispatch_callback(incoming)

    async def _wrap_private(self, msg):
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
```

**保留事项**：
- `BotAPI`/`GroupMessage.reply`/`PrivateMessage.reply` 的 monkey-patch **原状保留**（消息持久化业务逻辑）
- 60+ 命令函数业务逻辑不修改（只改 `bot.api.*` → `backend.*`）

### 3.2 `QQBotBackend`（包装现有 QQBotService）

**新文件**：`nbot/backends/qqbot_backend.py`（约 200 行）

**实现 1 个 Protocol**：仅 BotBackend（不实现 MediaBackend / NcatbotAdminBackend / RawApiBackend）

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
        self._loop = None   # rev. 2: 在 start() 中获取主 asyncio loop,供 run_coroutine_threadsafe 使用

    def set_dispatcher(self, callback):
        self._dispatch_callback = callback

    # ---- BotBackend ----
    async def start(self):
        from nbot.services.qqbot_service import (
            get_app_access_token, get_gateway, QQBotWebSocketService
        )
        # rev. 2: 关键修复 —— 在异步上下文中获取 event loop
        self._loop = asyncio.get_running_loop()

        self._token = get_app_access_token(
            self._creds["app_id"], self._creds["app_secret"]
        )
        gateway_url = get_gateway(self._token)
        self._ws_service = QQBotWebSocketService(
            gateway_url, self._token, on_event=self._on_dispatch_safe
        )
        self._ws_service.start()  # 启动独立线程
        self.is_running = True

    def run_forever(self):
        """同步阻塞 —— WebSocket 主循环

        rev. 2: 不返回,直接阻塞。bot.py 不要外层包 asyncio.run()
        """
        if self._ws_service:
            self._ws_service.run_forever()

    async def stop(self):
        self.is_running = False
        if self._ws_service:
            self._ws_service.stop()

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

    def supports(self, capability: str) -> bool:
        """rev. 2: QQBot 只支持核心文本能力"""
        return capability == "private_text" or capability == "group_text"

    # ---- 事件转换 ----
    def _on_dispatch_safe(self, raw_event: dict):
        """rev. 2: 关键修复 —— WebSocket 线程回调不能直接 asyncio.create_task()

        必须用 run_coroutine_threadsafe 把协程调度到主 event loop
        """
        if self._loop is None or self._dispatch_callback is None:
            return
        try:
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
            # rev. 2: 关键 —— 跨线程调度协程
            asyncio.run_coroutine_threadsafe(
                self._dispatch_callback(incoming),
                self._loop
            )
        except Exception as e:
            _log.exception("qqbot dispatch error: %s", e)
```

**关键修复**（rev. 2 核心）：
- `start()` 中通过 `asyncio.get_running_loop()` 捕获主 loop 引用
- 线程回调 `_on_dispatch_safe()` 使用 `asyncio.run_coroutine_threadsafe(coro, loop)` 跨线程调度
- 避免 `RuntimeError: no running event loop`

**`qqbot_service.py` 改动**：
- `answer_qqbot_event()` 约 100 行拆分：
  - 事件分发部分（`parse_event` → `IncomingMessage`）迁到 `QQBotBackend._on_dispatch_safe`
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

    # 注入 dispatcher
    async def dispatcher(incoming: IncomingMessage):
        from nbot.commands import handle_incoming_message
        await handle_incoming_message(incoming)
    backend.set_dispatcher(dispatcher)

    _set_web_server_bot(backend)

    # rev. 2: 异步 start() + 同步 run_forever() 分离
    # start() 必须在 async 上下文中(QQBotBackend 需要获取 event loop)
    asyncio.run(backend.start())
    # run_forever() 同步阻塞,不外层包 asyncio.run()
    backend.run_forever()
```

**关键修正（rev. 2）**：
- `asyncio.run(backend.start())` 启动后立即退出（start 只做连接初始化）
- `backend.run_forever()` 在主线程同步阻塞
- ncatbot 路径：`start()` 注册 event handler → `run_forever()` 调 `bot.run()` 阻塞
- QQBot 路径：`start()` 获取 token + 启动 WebSocket 线程 → `run_forever()` 阻塞 WebSocket 主循环

**主入口 `__main__` 改动**：

```python
# bot.py default branch —— 简化为:
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

## 5. 配置项（不变）

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

## 6. commands.py 改造（分 4 阶段）

### 6.1 阶段 1：文本消息链路（最优先）

**目标**：打通核心文本消息闭环，不动富媒体/管理/边缘功能。

**改动清单**：
1. `commands.py` 顶部：删除 `bot = BotClient()` 全局、删除 `heartbeat_core = HeartbeatCore(bot.api)`（仅在阶段 4 恢复）
2. `commands.py` 顶部：删除 `handle_group_message`/`handle_private_message`，新增 `handle_incoming_message`
3. `commands.py` 顶部：删除 `bot.add_group_event_handler/add_private_event_handler` 注册（移到 `NcatbotBackend.start()`）
4. `commands.py` 中 `dispatch_message(msg, is_group)` 签名改为 `dispatch_message(incoming)`，内部 `msg.user_id/group_id/raw_message/sender.nickname` → `incoming.user_id/group_id/text/sender_name`
5. `commands.py` 中 `msg.reply("text")` → `await incoming.reply("text")`（reply 简化为只支持文本）
6. `commands.py` 中**只替换** `await bot.api.post_private_msg(user_id=..., text=...)` → `await get_backend().send_private_text(user_id, text)` 和 `await bot.api.post_group_msg(group_id=..., text=...)` → `await get_backend().send_group_text(group_id, text)`（**这两类调用优先替换**）
7. 暂不替换：图片/语音/文件/管理类 `bot.api.*` 调用（保留 `await bot.api.post_group_file(...)` 等原状）

**涉及命令**：所有命令的"发文本消息"路径，包括 AI 对话、`/roll`、`/dice`、`/email` 等。

**新增文件**：
- `nbot/commands_backend.py`（核心抽象 + IncomingMessage + BotBackend Protocol + 全局 getter）
- `nbot/backends/__init__.py`
- `nbot/backends/ncatbot_backend.py`（仅实现 BotBackend 核心，MediaBackend 暂空实现或 return False）
- `nbot/backends/qqbot_backend.py`（仅实现 BotBackend 核心）
- `nbot/bot_runner.py`
- `tests/test_commands_backend.py`
- `tests/test_backend_ncatbot.py`
- `tests/test_backend_qqbot.py`

**bot.py 改造**：`run_bot()` 改用 `asyncio.run(backend.start()) + backend.run_forever()`。

**.env.example / config.ini 改造**：双轨并列配置项。

**阶段 1 验收**：
- ncatbot 模式：AI 对话私聊/群聊可用
- ncatbot 模式：`/roll` `/dice` `/email` 基础命令文本回复正常
- QQBot 模式：AI 对话私聊/群聊可用
- QQBot 模式：`/roll` `/dice` `/email` 基础命令文本回复正常
- ncatbot 老用户配置零修改

### 6.2 阶段 2：迁移 commands.py 主路径

**目标**：批量替换 commands.py 中所有 `bot.api.*` 文本类调用到 backend。

**改动清单**：
1. 替换 `await bot.api.post_*_msg(...)` 的所有剩余调用
2. 替换 `await bot.api.set_qq_profile/set_online_status/set_qq_avatar/send_like/set_group_admin/set_friend_add_request` → 通过 `isinstance(backend, NcatbotAdminBackend)` 判断后调用；QQBot 路径返回"不支持"提示
3. 替换 `await bot.api.get_group_msg_history(...)` → 同上 NcatbotAdminBackend 判断
4. 替换 `getattr(bot.api, func_name)(**params)` (`/bot` 动态命令) → `isinstance(backend, RawApiBackend)` 判断
5. `ai_commands.py`：`register_ai_commands(bot=bot, ...)` → `register_ai_commands(backend=..., ...)`，内部 `bot_instance.api.*` → `backend.*`

**涉及命令**：
- 完整覆盖 60+ 命令的文本路径
- 管理类命令（`/setadmin` `/ban` 等）在 QQBot 模式下提示"当前后端不支持"

**阶段 2 验收**：
- ncatbot 模式：60+ 命令文本路径行为完全一致（与重构前）
- QQBot 模式：文本命令 100% 可用，管理类命令明确提示"不支持"
- `commands.py` 中不再有 `bot.api.post_*_msg` 调用

### 6.3 阶段 3：富媒体与边缘能力

**目标**：处理图片/语音/文件/TTS/message_middleware/web 推送。

**改动清单**：
1. `nbot/services/tts.py`：删除 `from ncatbot.core.element import MessageChain, Record`，改为 `await backend.send_group_voice(group_id, path)`；QQBot 不支持私聊语音，降级为文本
2. `nbot/gateway/tts_handler.py`：同上
3. `nbot/core/message_middleware.py`：`bot.api.get_file_sync/download_file_sync` → `isinstance(backend, NcatbotAdminBackend)` 判断后调用
4. `nbot/web/server.py`：`self.qq_bot.api.*` → `backend.*`
5. commands.py 中 `bot.api.post_group_file/upload_private_file` → `isinstance(backend, MediaBackend)` 判断后调用
6. commands.py 中 `bot.api.post_group_msg(rtf=MessageChain([Record(...)]))` → `isinstance(backend, MediaBackend)` 判断后调用 `backend.send_group_voice(...)`

**涉及命令**：
- 漫画下载（图片发送）
- TTS 语音消息
- 文件传输（表情包等）

**阶段 3 验收**：
- ncatbot 模式：富媒体/文件/语音/TTS 全部正常
- QQBot 模式：富媒体命令明确提示"当前后端不支持"
- `tts.py` / `tts_handler.py` / `message_middleware.py` / `server.py` 中不再有 `bot.api.*` 调用

### 6.4 阶段 4：清理 ncatbot 残留依赖

**目标**：完全切断 commands.py 等核心模块对 ncatbot 的直接 import。

**改动清单**：
1. `nbot/core/heartbeat.py`：修正 `from ncatbot.services.ai import ai_client` → `from nbot.services.ai import ai_client`（疑似 bug）；`bot_api` 参数 → 内部 `get_backend()` 获取
2. `commands.py` 顶部：确认无 `import ncatbot` 残留
3. `ai_commands.py`：确认无 `import ncatbot` 残留
4. `nbot/commands_backend.py`、`nbot/backends/ncatbot_backend.py` 是**唯一**仍可 `import ncatbot` 的文件
5. 删除 `_apply_runtime_ncatbot_config` 中重复的 setter 调用（保留核心部分）
6. `requirements.txt`：`ncatbot == 3.8.5` 标注为可选（`ncatbot>=3.8.5; sys_platform == "win32"` 或保留但加注释）

**涉及文件**：
- `nbot/core/heartbeat.py`
- `nbot/commands.py`
- `nbot/ai_commands.py`
- `requirements.txt`

**阶段 4 验收**：
- `grep -r "import ncatbot" nbot/commands.py nbot/ai_commands.py nbot/core/ nbot/services/ nbot/web/ nbot/gateway/ nbot/channels/` 无结果（仅 `nbot/commands_backend.py` 和 `nbot/backends/ncatbot_backend.py` 可有 ncatbot 引用）
- `python -m compileall -q bot.py nbot tools` 通过
- `ruff check .` 无新增警告
- `python -m pytest -q` 全部通过

### 6.5 4 阶段总览

| 阶段 | 目标 | 工作量 | 风险 | 验收命令数 |
|------|------|-------|------|----------|
| 1 | 文本消息链路 | 中 | 中 | 5-10 个核心命令 |
| 2 | 主路径批量替换 | 大 | 中 | 60+ 命令文本路径 |
| 3 | 富媒体 + 边缘 | 中 | 中低 | 60+ 命令完整 |
| 4 | 清理残留 import | 小 | 低 | 全部清理 |

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
       ├─ asyncio.run(backend.start())  [rev. 2: 异步初始化]
       │    ├─ NcatbotBackend.start() → 注册 event handler
       │    └─ QQBotBackend.start() → 获取 token + 启动 WebSocket 线程 + 保存 self._loop
       └─ backend.run_forever()  [rev. 2: 同步阻塞,不外层包 asyncio.run]
              ├─ NcatbotBackend.run_forever() → self.bot.run()  (ncatbot 内部管理事件循环)
              └─ QQBotBackend.run_forever() → self._ws_service.run_forever()  (阻塞 WebSocket 主循环)
```

### 7.2 ncatbot 路径

```
NapCatQQ WebSocket
  → ncatbot.BotClient event loop
  → NcatbotBackend._wrap_group(msg: GroupMessage)
  → _to_incoming(msg, Scene.GROUP)
  → dispatcher(incoming)  [async, 同一 event loop]
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
  → QQBotWebSocketService 收到 OP_DISPATCH [独立线程]
  → QQBotBackend._on_dispatch_safe(raw_event) [rev. 2: 关键修复]
  → QQBotChannelAdapter.parse_event(raw_event) → parsed dict
  → 转 IncomingMessage
  → asyncio.run_coroutine_threadsafe(self._dispatch_callback(incoming), self._loop)  [rev. 2: 跨线程调度]
  → 主 event loop 中执行 dispatcher(incoming)
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
    IncomingMessage, Scene, set_backend, get_backend, Capability
)

class FakeBackend:
    """最小 BotBackend 实现,用于测试"""
    name = "fake"
    is_running = True

    async def start(self): pass
    def run_forever(self): pass
    async def stop(self): pass
    async def send_private_text(self, user_id, text):
        self.sent.append(("private", user_id, text)); return True
    async def send_group_text(self, group_id, text):
        self.sent.append(("group", group_id, text)); return True
    def supports(self, capability): return False  # 核心 fake 不支持富媒体

    def __init__(self):
        self.sent = []

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
    backend = NcatbotBackend.__new__(NcatbotBackend)
    backend.bot = MagicMock()
    msg = MagicMock()
    msg.user_id = "123"; msg.group_id = "456"
    msg.raw_message = "hello"; msg.sender.nickname = "Alice"
    msg.message_id = "m1"; msg.self_id = "999"
    msg.message = []
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
def test_on_dispatch_uses_run_coroutine_threadsafe():
    """rev. 2: 验证线程回调使用 run_coroutine_threadsafe,不直接 create_task"""
    from nbot.backends.qqbot_backend import QQBotBackend
    from unittest.mock import MagicMock, patch
    import asyncio
    backend = QQBotBackend.__new__(QQBotBackend)
    backend._creds = {"app_id": "test"}
    backend._loop = MagicMock()
    backend._dispatch_callback = MagicMock()
    with patch("asyncio.run_coroutine_threadsafe") as mock_rcts:
        backend._on_dispatch_safe({"t": "C2C_MESSAGE_CREATE", "d": {}})
        # 验证 run_coroutine_threadsafe 被调用
        assert mock_rcts.called
        # 验证传入 loop
        call_args = mock_rcts.call_args
        assert call_args[0][1] == backend._loop
```

### 8.2 集成测试（手动）

启动命令：
```bash
# ncatbot 模式
BOT_UIN=xxx WS_URI=ws://localhost:3001 python bot.py

# QQBot 模式
QQBOT_APP_ID=xxx QQBOT_APP_SECRET=xxx python bot.py
```

阶段 1 回归测试（每条至少跑通一次）：
- AI 对话（私聊）—— 核心
- AI 对话（群 @）—— 核心
- `/roll` `/dice` —— 基础工具
- `/email` —— 文本命令

阶段 2 回归测试（在阶段 1 基础上增加）：
- 60+ 命令的文本路径

阶段 3 回归测试（在阶段 2 基础上增加）：
- 漫画图片发送
- TTS 语音消息
- 文件传输

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
| QQBot token 过期 | 捕获 401 → 自动刷新 token → 重试一次 |
| ncatbot 断开重连 | 保留 ncatbot 自身重连机制 |
| 消息发送失败 | 后端 `send_xxx` 返回 `False`，命令函数检查并打日志 |
| Web 端推送消息 | `_set_web_server_bot(backend)` 注入 backend |
| QQBot 线程回调时主 loop 未启动 | 启动顺序保证：`start()` 必须在 `run_forever()` 之前；`_on_dispatch_safe` 中检查 `self._loop is None` 时直接 return |
| QQBot 接收事件时主 loop 已关闭 | `run_coroutine_threadsafe` 返回的 Future 失败，仅打日志不抛 |
| 命令调用 QQBot 不支持的能力 | `isinstance(backend, MediaBackend)` / `NcatbotAdminBackend` / `RawApiBackend` 判断失败时，命令回复"当前后端不支持" |
| ncatbot 用户的旧 `.env` 无 `QQBOT_*` 配置 | 完全兼容，行为不变 |
| QQBot 用户的 `.env` 无 `BOT_UIN`/`WS_URI` 配置 | 完全兼容，走 QQBot 路径 |

## 10. 实施步骤（按 4 阶段组织）

### 阶段 1：文本消息链路（最优先）

1. 新建 `nbot/commands_backend.py`（`IncomingMessage` + `BotBackend` Protocol + 全局 getter/setter + `Capability` 常量）
2. 新建 `nbot/backends/__init__.py` + `nbot/backends/ncatbot_backend.py`（仅实现 `BotBackend` 核心）
3. 新建 `nbot/backends/qqbot_backend.py`（仅实现 `BotBackend` 核心 + `_on_dispatch_safe` 修复）
4. 新建 `nbot/bot_runner.py`（`detect_backend` + `create_backend`）
5. 改造 `bot.py` 的 `run_bot()`（`asyncio.run(start()) + run_forever()`）
6. 改造 `commands.py` 事件入口（删除 `handle_group/private_message`，新增 `handle_incoming_message`）
7. 改造 `commands.py` 全局 `bot` 引用（删除 `bot = BotClient()`）
8. 改造 `commands.py` 中 `dispatch_message(msg, is_group)` → `dispatch_message(incoming)`
9. 替换 `commands.py` 中 `msg.user_id/group_id/raw_message/sender.nickname` → `incoming.*`（**仅这两个属性 + reply 调用**）
10. 替换 `commands.py` 中 `await bot.api.post_*_msg(user_id/group_id=..., text=...)` → `await get_backend().send_*_text(...)`（**仅这两类**）
11. 替换 `commands.py` 中 `msg.reply("text")` → `await incoming.reply("text")`
12. 更新 `.env.example`（双轨并列）
13. 更新 `config.ini`（双轨并列）
14. 新增 `tests/test_commands_backend.py` + `tests/test_backend_ncatbot.py` + `tests/test_backend_qqbot.py`
15. 手动回归测试（阶段 1 验收）

### 阶段 2：主路径批量替换

16. 替换 `commands.py` 中所有 `bot.api.post_*_msg` 剩余调用
17. 替换 `commands.py` 中 `bot.api.set_qq_profile/set_online_status/set_qq_avatar/send_like/set_group_admin/set_friend_add_request` → `isinstance(backend, NcatbotAdminBackend)` 判断
18. 替换 `commands.py` 中 `bot.api.get_group_msg_history` → `isinstance(backend, NcatbotAdminBackend)` 判断
19. 替换 `commands.py` 中 `getattr(bot.api, name)(**params)`（`/bot` 命令）→ `isinstance(backend, RawApiBackend)` 判断
20. 改造 `ai_commands.py`（`register_ai_commands(bot=bot)` → `register_ai_commands(backend=...)`）
21. 手动回归测试（阶段 2 验收）

### 阶段 3：富媒体与边缘

22. 改造 `nbot/services/tts.py`（删除 `MessageChain`/`Record`，调用 `backend.send_group_voice`）
23. 改造 `nbot/gateway/tts_handler.py`（同上）
24. 改造 `nbot/core/message_middleware.py`（`bot.api.get_file_sync/download_file_sync` → `isinstance(backend, NcatbotAdminBackend)`）
25. 改造 `nbot/web/server.py`（`self.qq_bot.api.*` → `backend.*`）
26. 改造 `commands.py` 中 `bot.api.post_group_file/upload_private_file` → `isinstance(backend, MediaBackend)` 判断
27. 改造 `commands.py` 中 `bot.api.post_group_msg(rtf=MessageChain([Record(...)]))` → `isinstance(backend, MediaBackend)` 判断
28. 手动回归测试（阶段 3 验收）

### 阶段 4：清理 ncatbot 残留

29. 修复 `nbot/core/heartbeat.py` 中 `from ncatbot.services.ai import ai_client` 笔误
30. 改造 `nbot/core/heartbeat.py` 中 `bot_api` 参数 → 内部 `get_backend()` 获取
31. 检查 `commands.py` / `ai_commands.py` 无 `import ncatbot` 残留
32. 更新 `requirements.txt`（`ncatbot` 标注为可选）
33. 完整 CI 验证（ruff / compileall / pytest）

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| `commands.py` 100+ 处替换引入回归 bug | 高 | 分 4 阶段 + 每阶段独立验证 + 保留 ncatbot monkey-patch 作为兜底 |
| QQBot `_on_dispatch_safe` 跨线程调度失败 | 高 | rev. 2 已修复：`asyncio.get_running_loop()` + `run_coroutine_threadsafe` |
| ncatbot `BotClient.run()` 与 `asyncio.run()` 冲突 | 高 | rev. 2 已修复：`start()` 异步 + `run_forever()` 同步分离 |
| `IncomingMessage` 字段不足覆盖所有命令用法 | 中 | 第一版只支持 reply(text)，富媒体走 backend 显式方法 |
| 老用户升级时命令行为变化 | 中 | monkey-patch 保留 + `IncomingMessage.reply(text)` 语义兼容 `msg.reply(text)` |
| `register_ai_commands` 全局 bot 引用破环 | 中 | 保留 ai_commands.py 内部 `self.backend`，monkey-patch 兼容 |
| `tts.py` 删除 `MessageChain` 后 QQBot 不支持私聊语音 | 低 | 降级为文本提示，不抛异常 |
| 阶段 1 验收只覆盖 5-10 个命令，老用户感知不强 | 低 | 阶段 1 文档明确告知后续阶段计划 |

## 12. 验收标准（按阶段）

### 阶段 1 验收标准

1. ✅ `python bot.py` 在仅有 `BOT_UIN`+`WS_URI` 时正常运行（ncatbot 模式）
2. ✅ `python bot.py` 在仅有 `QQBOT_APP_ID`+`QQBOT_APP_SECRET` 时正常运行（QQBot 模式）
3. ✅ ncatbot 模式：AI 对话私聊可用
4. ✅ ncatbot 模式：AI 对话群 @ 可用
5. ✅ ncatbot 模式：`/roll` `/dice` `/email` 文本回复正常
6. ✅ QQBot 模式：AI 对话私聊可用
7. ✅ QQBot 模式：AI 对话群 @ 可用
8. ✅ QQBot 模式：`/roll` `/dice` `/email` 文本回复正常
9. ✅ `tests/test_commands_backend.py` 全部通过
10. ✅ `tests/test_backend_ncatbot.py` 全部通过
11. ✅ `tests/test_backend_qqbot.py` 全部通过（验证 `run_coroutine_threadsafe` 调用）
12. ✅ `ruff check .` 无新增警告
13. ✅ `python -m compileall -q bot.py nbot tools` 无错误
14. ✅ ncatbot 老用户配置零修改（行为与重构前一致）
15. ✅ `commands.py` 中 `await bot.api.post_*_msg` 仅剩 `post_group_msg(rtf=...)` 形式（富媒体暂保留）

### 阶段 2 验收标准

16. ✅ ncatbot 模式：60+ 命令文本路径行为完全一致（与重构前）
17. ✅ QQBot 模式：文本命令 100% 可用
18. ✅ QQBot 模式：管理类命令明确提示"当前后端不支持"
19. ✅ `commands.py` 中不再有 `bot.api.post_*_msg` 调用
20. ✅ `ai_commands.py` 不再有 `from nbot.commands import bot` 后的 `bot.api.*` 调用

### 阶段 3 验收标准

21. ✅ ncatbot 模式：富媒体/文件/语音/TTS 全部正常
22. ✅ QQBot 模式：富媒体命令明确提示"当前后端不支持"
23. ✅ `tts.py` / `tts_handler.py` 不再有 `import ncatbot`
24. ✅ `message_middleware.py` / `server.py` 中不再有 `bot.api.*` 调用

### 阶段 4 验收标准

25. ✅ `grep -r "import ncatbot" nbot/commands.py nbot/ai_commands.py nbot/core/ nbot/services/ nbot/web/ nbot/gateway/ nbot/channels/` 无结果
26. ✅ 仅 `nbot/commands_backend.py` 和 `nbot/backends/ncatbot_backend.py` 可有 ncatbot 引用
27. ✅ `python -m compileall -q bot.py nbot tools` 通过
28. ✅ `ruff check .` 无新增警告
29. ✅ `python -m pytest -q` 全部通过
30. ✅ `.env.example` / `config.ini` 包含双轨配置项

## 13. 后续工作（不在本次范围）

- 完全移除 ncatbot 依赖（当所有用户都迁移到 QQBot 后）
- 拆分 `commands.py` 4989 行单文件
- 统一 `nbot/services/qqbot_service.py` 与 `nbot/backends/qqbot_backend.py` 的边界
- 用 `botpy` 官方 SDK 替换手写的 `requests` + `websocket-client`
- 引入 `contextvars` 替代全局 `get_backend()`
- 支持多 backend 并存（QQBot + Telegram + Feishu 同时运行）
