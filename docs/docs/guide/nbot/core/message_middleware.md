# message_middleware - 消息预处理中间件

## 概述

`message_middleware.py` 为所有频道提供统一的附件处理流水线：将附件解析为可访问的 URL，由 AI 生成文字描述，最后注入用户消息。

## 附件标准格式

```python
{
    "type": "image" | "video" | "audio" | "file",
    "url": "https://...",
    "source": "qq" | "telegram" | "feishu" | "web",
    "source_ref": "频道的引用 key",
    "mime_type": "image/png",
    "name": "文件名",
    # ...频道特定字段
}
```

## 核心组件

### AttachmentResolver - 频道附件解析注册表

按频道注册 handler，接收 attachment dict，返回可直接访问的 URL（http 或 data: URL）。

```python
AttachmentResolver.register("qq", _resolve_qq_attachment)
AttachmentResolver.resolve("qq", attachment)  # → data:image/png;base64,...
```

内置解析器：

| 频道 | 解析策略 |
|------|----------|
| qq / qq_private / qq_group | 三级策略：get_file → download_file → 直接 HTTP |
| telegram | getFile API → 下载 → data URL |
| feishu / feishu_ws | 获取 tenant token → API 下载 → data URL |
| web | 本地路径 base64 / 相对 URL 拼接 base_url |

**QQ 三级策略**：
1. `get_file_sync` - 获取 NapCat 本地缓存文件路径（最可靠）
2. `download_file_sync` - NapCat 内部下载器（带正确签名）
3. 直接 HTTP 下载（带浏览器请求头，校验非 HTML）

### MediaDescriber - AI 媒体描述注册表

按媒体类型注册描述函数。函数接收 URL，返回文字描述。

```python
MediaDescriber.register("image", describe_image)
MediaDescriber.describe("image", url)  # → "图片中有一只猫在晒太阳"
```

支持描述的附件类型：`image`, `video`, `audio`。描述失败的标识前缀（"链接失效"、"解析失败"）不会注入消息。

### MessagePreprocessor - 编排流水线

```python
MessagePreprocessor.process(chat_request, workspace_context=None)
```

完整流程：
1. 遍历 `chat_request.attachments`
2. 标准化附件类型
3. `AttachmentResolver.resolve()` 获取可访问 URL
4. 如果提供 `workspace_context`，保存到会话工作区并生成 data URL
5. `MediaDescriber.describe()` 生成 AI 文字描述
6. 将描述块和 `[类型N描述]: ...` 标签注入 `chat_request.content`
7. 已处理的附件从列表中移除

```python
# 处理后 content 格式：
# [图片1描述]: 一只橘猫在窗台上晒太阳
# [图片2描述]: 一杯咖啡放在木桌上
#
# 用户消息: 你看这张照片怎么样？
```

## 使用示例

```python
from nbot.core.message_middleware import MessagePreprocessor

# 直接处理 ChatRequest
MessagePreprocessor.process(chat_request, {
    "session_id": "sess_123",
    "session_type": "private"
})
```

## 设计原则

1. **可扩展** - 新频道注册 handler 即可，无需修改核心逻辑
2. **降级策略** - URL 兜底、失败跳过、错误前缀过滤
3. **工作区集成** - 附件自动保存到会话工作区，同一文件去重
4. **编排分离** - 解析/描述/注入三个阶段独立可替换
