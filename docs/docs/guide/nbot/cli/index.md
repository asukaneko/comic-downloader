# CLI - 终端命令行界面

## 概述

`nbot/cli/` 提供了一套基于 **Rich** 和 **prompt_toolkit** 的终端交互界面，支持多屏切换、实时刷新、键盘导航和会话管理。通过 `bot.py` 的 `--cli` 标志启动。

## 启动方式

| 命令 | 效果 |
|------|------|
| `python bot.py --cli` | 仅启动 CLI（无 QQ 机器人） |
| `python bot.py --cli-and-web` | CLI + Web 仪表盘同时运行 |
| `python bot.py --no-web` | QQ 机器人仅运行，无 CLI 无 Web |

## 模块结构

```
nbot/cli/
├── __init__.py      # 导出 CLIApp 及主要 Screen/Component
├── app.py           # CLIApp 主循环，键盘捕获，Live 渲染
├── screens.py       # 6 种屏幕：Main / Chat / Tools / Sessions / Config / Help
└── components.py    # UI 组件：Header / Footer / Sidebar / MessagePanel / InputBox 等
```

---

## 核心类

### `CLIApp` (`app.py:34`)

应用主类。管理屏幕注册与切换、键盘事件循环、以及 Rich `Live` 渲染器。

```python
class CLIApp:
    def __init__(self):
        # 注册 6 个屏幕 (main/chat/tools/sessions/config/help)
        # 自动进入主屏幕

    def switch_screen(self, screen_name: str) -> None:
        # 切换到指定屏幕并触发 update()

    def show_help(self) -> None:
        # 切换到帮助屏幕

    def run(self) -> None:
        # 主循环：每秒 refresh_rate 次刷新 + 键盘轮询
        # 使用 Live(screen=True) 进入备用屏幕缓冲区

    def quit(self) -> None:
        # 退出主循环并清理
```

**键盘捕获**：跨平台实现（Windows `msvcrt` / Unix `termios`），方向键、Tab、Enter、Backspace、Ctrl+C 等均映射为语义键名后传递给当前屏幕的 `handle_input()`。

### `BaseScreen` (`screens.py:37`)

屏幕抽象基类，所有屏幕继承自它。

```python
class BaseScreen(ABC):
    def build_layout(self) -> Layout:   # 子类实现布局
    def handle_input(self, key) -> bool:  # 子类实现输入处理，return False 退出
    def update(self):                     # 子类实现数据刷新
    def render(self) -> Layout:           # 调用 build_layout()
```

每个屏幕包含 `Header` / `Footer` 实例，以及自身独有的组件面板。

### 屏幕一览

| 屏幕 | 类 | 关键组件 | 说明 |
|------|-----|---------|------|
| 主屏幕 | `MainScreen` | `Sidebar` + 欢迎面板 | 菜单导航（聊天/会话/工具/配置/帮助/退出），显示系统信息 |
| 聊天 | `ChatScreen` | `MessagePanel` + `InputBox` + `Sidebar` | 消息收发、输入编辑（光标/退格/删除）、会话持久化 |
| 工具 | `ToolsScreen` | `ToolPanel` + `Sidebar` | 加载 `data/web/tools.json` 展示启用/禁用状态 |
| 会话 | `SessionsScreen` | `SessionPanel` + `Sidebar` | 加载 `data/web/sessions.json` 列表 |
| 配置 | `ConfigScreen` | `ConfigPanel` + `Sidebar` | 加载 AI 配置（通过 `read_secure_json` 加密读取）和系统设置 |
| 帮助 | `HelpScreen` | `HelpPanel` | 显示所有可用命令 |

---

## UI 组件 (`components.py`)

| 组件 | 类 | 用途 |
|------|-----|------|
| 消息 | `Message` | 数据类：role / content / timestamp / metadata |
| 标题栏 | `Header` | 顶部 Panel，显示标题、当前屏幕指示器（带颜色圆点）、时间 |
| 状态栏 | `Footer` | 底部 Panel，显示快捷键提示和状态文本 |
| 侧边栏 | `Sidebar` | 可导航的菜单列表，支持选中高亮、上下选择 |
| 消息面板 | `MessagePanel` | 显示最近 20 条消息，区分 user/assistant/system/tool 四种角色 |
| 输入框 | `InputBox` | 支持光标移动、字符插入/删除、占位文本 |
| 工具面板 | `ToolPanel` | 表格展示工具名称、描述、启用/禁用状态 |
| 会话面板 | `SessionPanel` | 表格展示会话 ID、名称、类型、消息数、更新时间 |
| 配置面板 | `ConfigPanel` | 分类 Tab + 表格，支持多类别切换 |
| 加载动画 | `LoadingSpinner` | Rich Progress + SpinnerColumn |
| 帮助面板 | `HelpPanel` | 命令列表表格 |

---

## 数据流

```
用户键盘 → CLIApp._get_key() → 语义键名 → current_screen.handle_input(key)
                                               │
                                     ┌─────────┼─────────┐
                                     ↓         ↓         ↓
                                 切换屏幕   发送消息   执行命令
                                               │
                                               ↓
                                        MessagePanel.add_message()
                                               │
                                               ↓
                                        _save_session() → sessions.json
```

聊天会话通过 `build_cli_session_id()` 生成 ID，消息写入 `data/web/sessions.json`（兼容 Web 会话格式），AI 回复当前为模拟占位，实际调用需接入 `nbot.core` 管线。

## 关键设计

- **Live 渲染**：使用 Rich 的 `Live` 模式 + 备用屏幕缓冲区（`screen=True`），退出后自动恢复终端原始状态。
- **跨平台键盘**：Windows 用 `msvcrt`，Unix 用 `termios` + `select`，保持统一语义键名接口。
- **模块化屏幕**：每个屏幕独立实现 `build_layout` / `handle_input` / `update`，新增屏幕只需注册到 `_init_screens()`。
- **组件解耦**：`components.py` 只负责渲染纯 Rich Panel，不持有应用引用；`screens.py` 持有 `CLIApp` 引用以触发切换。
