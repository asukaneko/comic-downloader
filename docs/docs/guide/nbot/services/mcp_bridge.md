# mcp_bridge - MCP 桥梁

## 概述

`mcp_bridge.py` 实现 MCP（Model Context Protocol）桥梁，管理多个 MCP Server 连接，将 MCP 工具自动转换为 AI 可调用的 OpenAI function calling 格式。

## 工具命名规则

MCP 工具转换后生成全局唯一名称，格式：

```
mcp__<server_id_short>__<tool_name>
```

- `server_id_short`：UUID 去除连字符后取前 8 位
- `tool_name`：MCP 原始工具名

## 全局单例

```python
from nbot.services.mcp_bridge import get_mcp_bridge

bridge = get_mcp_bridge()  # 线程安全的单例
```

## 连接管理

### 连接服务器

```python
# HTTP/Streamable HTTP 传输
result = bridge.run_async(bridge.connect_server(
    "uuid-xxx",
    {"transport": "streamable-http", "url": "http://localhost:8000/mcp"}
))

# Stdio 传输（本地进程）
result = bridge.run_async(bridge.connect_server(
    "uuid-yyy",
    {
        "transport": "stdio",
        "command": "python",
        "args": ["mcp_server.py"],
        "env": {"API_KEY": "xxx"}
    }
))
```

`connect_server()` 自动完成：断开旧连接→创建 `MCPRemoteClient`→调用 `client.connect()`→调用 `client.list_tools()` 缓存工具列表。

### 断开连接

```python
bridge.run_async(bridge.disconnect_server("uuid-xxx"))
bridge.run_async(bridge.disconnect_all())  # 断开所有
```

### 状态查询

```python
bridge.is_connected("uuid-xxx")  # bool
bridge.get_status()              # {server_id: {"connected": bool, "tool_count": int}}
```

## 工具转换

`mcp_tool_to_openai()` 将单个 MCP 工具定义转为 OpenAI function calling 格式：

```python
from nbot.services.mcp_bridge import mcp_tool_to_openai

openai_tool = mcp_tool_to_openai(mcp_tool_dict, server_id)
# {"type": "function", "function": {"name": "mcp__abc123__get_weather", "description": "...", "parameters": {...}}}
```

### 批量获取

```python
# 指定服务器
tools = bridge.get_openai_tool_definitions("uuid-xxx")

# 所有服务器合并
all_tools = bridge.get_all_openai_tools()

# 原始 MCP 格式
raw_tools = bridge.get_server_tools("uuid-xxx")
```

## 工具执行

```python
# 通过 server_id + tool_name
result = bridge.run_async(bridge.execute(
    "uuid-xxx", "get_weather", {"city": "Beijing"}
))

# 通过全局完整名称
result = bridge.run_async(bridge.execute_by_full_name(
    "mcp__abc123__get_weather", {"city": "Beijing"}
))
```

`execute_by_full_name()` 从全名解析出 `server_id_short`，自动匹配已连接的 server。

## 事件循环管理

`MCPBridge` 维护一个持久化的事件循环线程（`_ensure_loop()`），所有异步操作通过 `asyncio.run_coroutine_threadsafe()` 提交。`run_async()` 是同步包装器，供非异步代码调用。

## 工具注册集成

MCP 桥接的工具可通过 `bridge.get_all_openai_tools()` 注入到 AI 管道的工具列表中，与普通 function calling 工具共存。

```python
from nbot.services.mcp_bridge import get_mcp_bridge
from nbot.services.tools import get_enabled_tools

bridge = get_mcp_bridge()
mcp_tools = bridge.get_all_openai_tools()
all_tools = (get_enabled_tools() or []) + mcp_tools
```

## 相关页面

- [react - ReAct Agent](./react.md) — AI 工具调用模式
- [ai - AI 客户端](./ai.md) — 工具注入到 AI 管道
