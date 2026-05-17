# file_gateway - 文件网关

## 概述

`file_gateway.py` 实现基于 HMAC 签名的安全文件交付系统。为 Web、QQ 等频道的文件访问提供有时效的签名 Token，避免直接暴露文件系统路径，同时支持跨频道统一的文件预览和下载。

## 设计思路

### 为什么需要文件网关

- **安全性**: AI 工具调用返回的文件路径不应直接暴露给前端或外部 API
- **时效性**: Token 有过期时间，防止链接被长期滥用
- **统一性**: Web 上传、QQ 图片、工作区文件统一通过网关访问
- **可追溯**: 每次访问都经过签名验证

### Token 结构

```
{base64(payload)}.{base64(hmac_sha256)}
```

Payload（JSON）包含：
- `path`: 文件绝对路径
- `filename`: 文件名
- `exp`: 过期时间戳

## 安全机制

### 路径白名单

只有以下目录中的文件才能通过网关访问：

- `data/workspaces/` — 工作区文件
- `data/workspace/`
- `data/web/` — Web 数据
- `data/cache/`, `cache/`, `nbot/cache/` — 缓存
- `static/files/` — 静态文件
- `static/uploads/` — 上传文件
- 工作区管理器的 `workspaces_dir` 和 `shared_workspace_dir`

::: warning 路径遍历防护
`is_allowed_file_path()` 使用 `os.path.commonpath()` 验证文件确实在白名单目录内，防止路径遍历攻击。
:::

### 签名密钥

密钥获取优先级：
1. 环境变量 `NBOT_FILE_GATEWAY_SECRET`
2. `data/web/file_gateway_secret.txt`（自动生成，48 字节随机字符串）
3. 回退到 Flask `secret_key`

### Token 过期

默认有效期 24 小时（`DEFAULT_EXPIRES_IN = 86400`），过期后验证失败返回 403。

## 核心 API

### sign_file_token()

为文件生成签名 Token，供 URL 使用。

```python
from nbot.web.file_gateway import sign_file_token

token = sign_file_token(
    server,
    "/data/workspaces/session_abc/report.pdf",
    filename="report.pdf",
    expires_in=3600,  # 1 小时后过期
)
# → "eyJwYXRoIjoi...(base64).abc123...(signature)"
```

### verify_file_token()

验证 Token 并返回文件信息。

```python
from nbot.web.file_gateway import verify_file_token

payload = verify_file_token(server, token)
# → {"path": "/abs/path/to/file", "filename": "report.pdf", "exp": 1716000000}
```

验证流程：
1. 分离 payload 和 signature
2. 验证 HMAC-SHA256 签名
3. 检查过期时间
4. 验证文件路径在白名单内
5. 确认文件存在

### build_file_gateway_urls()

生成完整的网关 URL 集合。

```python
from nbot.web.file_gateway import build_file_gateway_urls

urls = build_file_gateway_urls(
    server,
    "/data/workspaces/session_abc/image.png",
    filename="image.png",
    absolute=True,  # 生成绝对 URL
)

print(urls["url"])             # 内联访问 URL（?inline=1）
print(urls["download_url"])    # 下载 URL
print(urls["preview_url"])     # 预览 URL（/preview 端点）
print(urls["expires_at"])      # 过期时间戳
print(urls["token"])           # 原始 Token
```

返回的 URL 路由：

| 路由 | 说明 |
|------|------|
| `/api/files/gateway/{token}` | 文件下载（`Content-Disposition: attachment`） |
| `/api/files/gateway/{token}?inline=1` | 内联显示（浏览器中预览） |
| `/api/files/gateway/{token}/preview` | 结构化的预览信息（JSON） |

### build_file_metadata()

构建完整的文件元数据（给前端渲染文件卡片用）。

```python
from nbot.web.file_gateway import build_file_metadata

meta = build_file_metadata(server, "/path/to/file.png", filename="screenshot.png")

# 基本信息
print(meta["name"])       # "screenshot.png"
print(meta["type"])       # "image/png"
print(meta["size"])       # 123456
print(meta["extension"])  # ".png"

# 类型判断
print(meta["is_image"])   # True
print(meta["is_text"])    # False
print(meta["is_video"])   # False
print(meta["is_audio"])   # False

# 网关 URL
print(meta["url"])            # 内联 URL
print(meta["download_url"])   # 下载 URL
print(meta["preview_url"])    # 预览 URL

# 网关元信息
print(meta["gateway_token"])  # Token 字符串
print(meta["expires_at"])     # 过期时间戳
print(meta["expires_in"])     # 有效期（秒）
```

### is_allowed_file_path()

检查文件路径是否在白名单内。

```python
from nbot.web.file_gateway import is_allowed_file_path

if is_allowed_file_path(server, "/data/workspaces/abc/file.txt"):
    # 安全：文件在白名单目录中
    ...
```

### get_public_base_url()

获取服务器的公网基础 URL。

```python
from nbot.web.file_gateway import get_public_base_url

base_url = get_public_base_url(server)
# → "http://your-server.com:8080" 或 ""（无法获取时）
```

获取优先级：
1. 环境变量 `NBOT_PUBLIC_BASE_URL` / `WEB_PUBLIC_BASE_URL`
2. 服务器 settings 中的 `public_base_url`
3. Flask 请求的 `Origin` 头
4. Flask 请求的 `host_url`

## 路由注册

在 `files.py` 的 `register_file_routes()` 中调用 `register_file_gateway_routes()` 注册两个 Flask 路由：

```python
from nbot.web.file_gateway import register_file_gateway_routes

register_file_gateway_routes(app, server)
```

### GET `/api/files/gateway/<token>`

文件下载/内联路由。

- 默认 `Content-Disposition: attachment`（下载）
- `?inline=1` 时浏览器内联预览
- 自动检测 MIME 类型

### GET `/api/files/gateway/<token>/preview`

结构化预览端点，返回 JSON：

- **图片** (`.jpg`, `.png`, `.gif`, `.webp`, `.svg`): 返回 `type: "image"` + URL
- **Office 文档** (`.pdf`, `.docx`, `.xlsx`, `.pptx`): 返回 `type: "pdf"` 等 + `is_blob: true`
- **其他文件**: 调用 `FileParser.parse_file()` 提取文本内容返回

## 集成点

### Web 消息适配器

`message_adapter.py` 的 `send_file()` 使用 `build_file_metadata()` 生成文件卡片：

```python
file_meta = build_file_metadata(self.server, dest_path, filename=file_name)
file_info = self.channel_adapter.build_assistant_message(
    ...,
    metadata={"file": {**file_meta, "safe_name": safe_name}},
)
```

小图片（<5MB）自动内联 base64 预览，文本文件（<100KB）自动提取内容预览。

### 工作区工具

`tools.py` 的工作区文件操作（`read_file`, `send_file` 等）会通过 `build_file_gateway_urls()` 生成网关 URL 返回给 AI：

```python
gateway_urls = build_file_gateway_urls(
    server, file_path,
    filename=filename,
    absolute=True,
)
# 返回给 AI 的结果中包含 url / download_url / preview_url
```

### Web 进度报告

`WebProgressReporter.on_send_file()` 在 AI 发送文件时通过 Socket.IO 推送文件卡片到前端：

```python
def on_send_file(self, ctx, file_path, filename):
    file_meta = build_file_metadata(self.server, file_path, filename=filename)
    # 构建消息并通过 socketio.emit("new_message", ...) 推送
```

### Web 附件解析

`WebCallbacks.resolve_attachment_data()` 支持将网关 URL 和绝对路径还原为文件路径，供 AI Pipeline 使用：

```python
# 网关 URL → Token 验证 → 文件路径
if path_to_use.startswith("/api/files/gateway/"):
    token = extract_token(path_to_use)
    payload = verify_file_token(server, token)
    file_path = payload["path"]

# 绝对路径 → 白名单验证 → 文件路径
elif os.path.isabs(path_to_use):
    if is_allowed_file_path(server, path_to_use):
        file_path = path_to_use
```

## 前端集成

文件上传 API（`/api/sessions/<id>/upload`）返回的响应中，`url` / `download_url` / `preview_url` 已全部迁移为网关 URL：

```json
{
  "success": true,
  "filename": "photo.png",
  "path": "/abs/path/to/photo.png",
  "url": "/api/files/gateway/{token}?inline=1",
  "download_url": "/api/files/gateway/{token}",
  "preview_url": "/api/files/gateway/{token}/preview",
  "size": 123456
}
```

前端无需修改，直接使用返回的 URL 即可。
