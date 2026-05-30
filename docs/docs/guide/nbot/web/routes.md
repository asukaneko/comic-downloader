# routes - API 路由

## 概述

`nbot/web/routes/` 目录包含 Web 后台的所有 API 路由定义，共约 230 个接口，涵盖聊天、会话、角色、世界书、知识库、频道、AI 模型等全部功能模块。

## 路由结构

```
nbot/web/routes/
├── auth.py              # 认证登录
├── sessions.py          # 会话与消息管理
├── chat.py              # 聊天接口
├── characters.py        # 角色卡与运行时状态
├── world_book.py        # 世界书管理
├── personality.py       # 人格预设管理
├── knowledge.py         # 知识库
├── memory.py            # 记忆管理
├── ai_config.py         # AI 配置
├── ai_models.py         # AI 模型管理
├── channels.py          # 频道管理
├── gateway.py           # 网关管理
├── workflows.py         # 工作流
├── skills.py            # 技能管理
├── skills_storage.py    # 技能存储
├── tools.py             # 工具配置
├── task_center.py       # 任务中心
├── heartbeat.py         # 心跳管理
├── files.py             # 文件操作
├── workspace_private.py # 私有工作区
├── workspace_shared.py  # 共享工作区
├── workspace_misc.py    # 工作区杂项
├── voice.py             # 语音 TTS/STT
├── live2d.py            # Live2D
├── push.py              # 推送通知
├── public_sessions.py   # 公开会话
├── qq_overview.py       # QQ 概览
├── qrcode.py            # 二维码
├── api_keys.py          # API 密钥管理
├── config_legacy.py     # 旧版配置
├── config_transfer.py   # 配置导入导出
├── web_agent.py         # Web Agent
└── admin_misc.py        # 管理杂项（日志/统计/设置）
```

---

## 认证 (auth.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 主页面 |
| GET | `/dashboard` | 仪表盘页面 |
| POST | `/api/login` | 用户登录 |
| POST | `/api/verify-token` | 验证会话 Token |
| POST | `/api/logout` | 注销登录 |

---

## 会话管理 (sessions.py)

### 会话 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions` | 列出所有会话 |
| POST | `/api/sessions` | 创建新会话 |
| GET | `/api/sessions/<session_id>` | 获取会话详情 |
| PUT | `/api/sessions/<session_id>` | 更新会话 |
| DELETE | `/api/sessions/<session_id>` | 删除会话 |
| GET | `/api/sessions/<session_id>/debug` | 调试：查看会话详情 |
| POST | `/api/sessions/<session_id>/archive` | 归档会话 |
| POST | `/api/sessions/<session_id>/restore` | 恢复归档会话 |
| POST | `/api/sessions/<session_id>/fork` | 复制会话 |
| PUT | `/api/sessions/<session_id>/bind-character` | 绑定角色到会话 |

### 消息操作

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/<session_id>/messages` | 获取会话消息 |
| POST | `/api/sessions/<session_id>/messages` | 添加消息 |
| PUT | `/api/sessions/<session_id>/messages/<message_id>` | 更新消息（支持截断） |
| DELETE | `/api/sessions/<session_id>/messages/<message_id>` | 删除单条消息 |
| DELETE | `/api/sessions/<session_id>/messages` | 清空所有消息 |
| GET | `/api/sessions/<session_id>/message-favorites` | 获取收藏消息 |
| PUT | `/api/sessions/<session_id>/message-favorites` | 更新收藏消息 |

### AI 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/<session_id>/chat` | 发送消息给 AI |
| POST | `/api/sessions/<session_id>/regenerate` | 重新生成最后一条 AI 回复 |
| POST | `/api/stop` | 停止 AI 生成 |
| POST | `/api/sessions/<session_id>/compress` | 压缩上下文（摘要） |
| POST | `/api/sessions/<session_id>/ai-summary` | AI 生成会话摘要 |
| POST | `/api/sessions/<session_id>/restore-from-archive` | 从归档恢复消息 |

### 运行时时间线

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/<session_id>/runtime-timeline` | 获取运行时时间线 |
| POST | `/api/sessions/<session_id>/runtime-timeline` | 添加时间线条目 |

### 导入导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/<session_id>/export` | 导出单个会话 |
| GET | `/api/sessions/export` | 批量导出会话 |
| POST | `/api/sessions/import` | 导入会话 |

---

## 角色管理 (characters.py)

### 角色卡 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/characters` | 列出所有角色卡 |
| GET | `/api/characters/<character_id>` | 获取角色卡详情 |
| POST | `/api/characters` | 创建角色卡 |
| PUT | `/api/characters/<character_id>` | 更新角色卡 |
| DELETE | `/api/characters/<character_id>` | 删除角色卡 |

### 运行时状态

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/characters/<character_id>/state` | 获取角色运行时状态 |
| PUT | `/api/characters/<character_id>/state` | 手动更新运行时状态 |
| GET | `/api/characters/<character_id>/relationships` | 获取角色与用户关系 |
| PUT | `/api/characters/<character_id>/relationships` | 手动更新关系状态 |
| GET | `/api/characters/<character_id>/debug/latest-turn` | 调试：最新一轮快照 |
| POST | `/api/characters/runtime/initialize` | 初始化角色运行时引擎 |
| GET | `/api/characters/runtime/status` | 获取角色运行时状态 |

### 记忆

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/characters/<character_id>/memories` | 列出角色记忆 |
| POST | `/api/characters/<character_id>/memories` | 手动添加记忆 |
| DELETE | `/api/characters/<character_id>/memories/<memory_id>` | 删除记忆 |

---

## 世界书 (world_book.py)

### 世界书 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/world-books` | 列出所有世界书 |
| POST | `/api/world-books` | 创建世界书 |
| GET | `/api/world-books/<book_id>` | 获取单个世界书 |
| PUT | `/api/world-books/<book_id>` | 更新世界书 |
| DELETE | `/api/world-books/<book_id>` | 删除世界书 |

### 条目 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/world-books/<book_id>/entries` | 列出条目 |
| POST | `/api/world-books/<book_id>/entries` | 添加条目 |
| PUT | `/api/world-books/<book_id>/entries/<entry_id>` | 更新条目 |
| DELETE | `/api/world-books/<book_id>/entries/<entry_id>` | 删除条目 |
| POST | `/api/world-books/<book_id>/entries/batch` | 批量添加条目 |

### AI 生成与测试

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/world-books/<book_id>/ai-generate` | AI 生成条目 |
| POST | `/api/world-books/test-match` | 测试关键词匹配（支持多源召回） |

### 导入导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/world-books/export/<book_id>` | 导出单个世界书 |
| POST | `/api/world-books/import` | 导入世界书 |
| GET | `/api/world-books/export-all` | 导出全部世界书 |
| POST | `/api/world-books/import-all` | 批量导入世界书 |

### 测试匹配接口

支持简单模式和多源模式：

```json
// POST /api/world-books/test-match
// 多源模式
{
  "message": "进去看看",
  "character_id": "风堇",
  "recent_messages": [
    {"role": "assistant", "content": "你们抵达了白塔门前。"}
  ],
  "scene": {"location": "白塔"}
}
```

返回包含 `trigger_sources`、`score` 等多源召回信息。

---

## 人格预设 (personality.py)

### 基础操作

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/personality` | 获取当前人格配置 |
| PUT | `/api/personality` | 更新人格配置 |
| GET | `/api/personality/presets` | 获取内置人格预设 |
| POST | `/api/personality/import` | 导入角色卡（ZIP/JSON） |

### 自定义预设

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/personality/custom-presets` | 获取自定义预设列表 |
| POST | `/api/personality/custom-presets` | 添加自定义预设 |
| PUT | `/api/personality/custom-presets/<preset_id>` | 更新自定义预设 |
| DELETE | `/api/personality/custom-presets/<preset_id>` | 删除自定义预设 |
| POST | `/api/personality/custom-presets/<preset_id>/upload-to-platform` | 上传预设到平台 |

### AI 生成

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/personality/ai-generate` | AI 生成角色卡 |
| POST | `/api/personality/ai-generate-state` | AI 生成初始状态值 |
| POST | `/api/personality/ai-generate-first-message` | AI 生成开场白 |
| POST | `/api/personality/generate-portrait` | AI 生成角色头像 |

### 头像管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/personality/portrait` | 上传角色头像 |
| DELETE | `/api/personality/portrait` | 删除角色头像 |
| POST | `/api/personality/clean-unused-portraits` | 清理未使用头像 |

### 导入导出

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/personality/export` | 导出角色卡为 ZIP |
| GET | `/api/personality/export-all` | 导出全部自定义角色卡 |
| POST | `/api/personality/import-all` | 批量导入角色卡 |

---

## 知识库 (knowledge.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge` | 列出所有知识文档 |
| POST | `/api/knowledge` | 添加知识文档 |
| GET | `/api/knowledge/<doc_id>` | 获取单个文档 |
| PUT | `/api/knowledge/<doc_id>` | 更新文档内容 |
| DELETE | `/api/knowledge/<doc_id>` | 删除文档 |
| POST | `/api/knowledge/<doc_id>/index` | 重建单文档向量索引 |
| POST | `/api/knowledge/batch` | 批量导入文档 |
| POST | `/api/knowledge/batch-delete` | 批量删除文档 |
| GET | `/api/knowledge/stats` | 获取知识库统计 |
| POST | `/api/knowledge/search` | 搜索知识库 |
| POST | `/api/knowledge/rebuild` | 重建知识库向量索引 |
| GET | `/api/knowledge/export` | 导出全部文档 |

---

## 记忆管理 (memory.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memory` | 获取记忆（可按类型过滤） |
| POST | `/api/memory` | 添加记忆 |
| PUT | `/api/memory/<memory_id>` | 更新记忆 |
| DELETE | `/api/memory/<memory_id>` | 删除记忆 |
| DELETE | `/api/memory` | 清空所有记忆 |
| GET | `/api/memory/export` | 导出全部记忆 |
| POST | `/api/memory/batch-delete` | 批量删除记忆 |
| POST | `/api/memory/import` | 导入记忆 |

---

## AI 配置 (ai_config.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai-config` | 获取 AI 配置 |
| PUT | `/api/ai-config` | 更新 AI 配置 |
| POST | `/api/ai-config/test` | 测试 AI 配置连通性 |
| GET | `/api/ai-config/by-purpose/<purpose>` | 按用途获取模型配置 |
| GET | `/api/ai-config/all-purposes` | 获取所有用途的模型配置 |

---

## AI 模型管理 (ai_models.py)

### 模型 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai-models` | 列出所有 AI 模型配置 |
| POST | `/api/ai-models` | 创建模型配置 |
| PUT | `/api/ai-models/<model_id>` | 更新模型配置 |
| DELETE | `/api/ai-models/<model_id>` | 删除模型配置 |

### 模型操作

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/ai-models/<model_id>/apply` | 应用/激活模型 |
| POST | `/api/ai-models/<model_id>/toggle` | 切换启用状态 |
| POST | `/api/ai-models/<model_id>/clone` | 克隆模型配置 |
| POST | `/api/ai-models/<model_id>/test` | 测试模型配置 |
| POST | `/api/ai-models/<model_id>/set-purpose` | 设置模型用途 |

### 查询

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai-models/purposes` | 获取所有用途类型 |
| GET | `/api/ai-models/protocols` | 获取所有协议类型 |
| GET | `/api/ai-models/by-purpose/<purpose>` | 按用途筛选模型 |
| GET | `/api/ai-models/active-by-purpose` | 获取每个用途的活跃模型 |

### 故障转移

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ai-models/failover-status` | 获取故障转移队列状态 |
| POST | `/api/ai-models/failover-reset` | 重置故障转移状态 |
| GET | `/api/ai-models/failover-queue/<purpose>` | 获取指定用途的故障转移队列 |
| POST | `/api/ai-models/failover-reorder` | 批量更新模型优先级 |

---

## 频道管理 (channels.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/channels` | 列出所有频道 |
| POST | `/api/channels` | 创建频道 |
| PUT | `/api/channels/<channel_id>` | 更新频道 |
| DELETE | `/api/channels/<channel_id>` | 删除频道 |
| POST | `/api/channels/<channel_id>/toggle` | 切换启用状态 |
| GET | `/api/channels/presets` | 获取频道预设 |
| POST | `/api/channels/presets/<preset_id>` | 从预设创建频道 |

### 平台特定

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/channels/telegram/<channel_id>/webhook` | Telegram Webhook |
| POST | `/api/channels/telegram/<channel_id>/set-webhook` | 设置 Telegram Webhook URL |
| POST | `/api/channels/feishu/<channel_id>/webhook` | 飞书 Webhook |
| POST | `/api/channels/feishu-ws/<channel_id>/start` | 启动飞书 WebSocket |
| POST | `/api/channels/feishu-ws/<channel_id>/stop` | 停止飞书 WebSocket |
| GET | `/api/channels/feishu-ws/<channel_id>/status` | 飞书 WebSocket 状态 |

---

## 网关 (gateway.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/gateway/<channel_id>/webhook` | 统一 Webhook 入口 |
| GET | `/api/gateway/health` | 健康检查 |
| GET | `/api/gateway/stats` | 运行时统计 |
| GET | `/api/gateway/queue/status` | 队列状态 |
| POST | `/api/gateway/worker/start` | 启动后台 Worker |
| POST | `/api/gateway/worker/stop` | 停止后台 Worker |
| GET | `/api/gateway/events` | 查询事件日志 |
| GET | `/api/gateway/events/<trace_id>` | 查询事件链 |

---

## 工作流 (workflows.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workflows` | 列出所有工作流 |
| POST | `/api/workflows` | 创建工作流 |
| PUT | `/api/workflows/<workflow_id>` | 更新工作流 |
| DELETE | `/api/workflows/<workflow_id>` | 删除工作流 |
| POST | `/api/workflows/<workflow_id>/toggle` | 切换启用状态 |
| POST | `/api/workflows/<workflow_id>/execute` | 执行工作流 |

---

## 技能 (skills.py + skills_storage.py)

### 技能 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills` | 列出所有技能 |
| POST | `/api/skills` | 创建技能 |
| PUT | `/api/skills/<skill_id>` | 更新技能 |
| DELETE | `/api/skills/<skill_id>` | 删除技能 |
| POST | `/api/skills/<skill_id>/toggle` | 切换启用状态 |

### 技能存储

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/skills/storage` | 列出所有技能存储 |
| GET | `/api/skills/storage/<skill_name>` | 获取技能存储内容 |
| GET/POST | `/api/skills/storage/<skill_name>/skill-md` | 读写 skill.md |
| GET/POST | `/api/skills/storage/<skill_name>/reference-md` | 读写 reference.md |
| GET | `/api/skills/storage/<skill_name>/file/<file_name>` | 获取技能文件 |
| POST | `/api/skills/storage/<skill_name>/file/<file_name>` | 上传技能文件 |
| GET | `/api/skills/storage/<skill_name>/script/<script_name>` | 获取技能脚本 |
| POST | `/api/skills/storage/<skill_name>/script/<script_name>` | 上传技能脚本 |
| DELETE | `/api/skills/storage/<skill_name>` | 删除技能存储 |
| POST | `/api/skills/upload-folder` | 上传整个技能文件夹 |

---

## 工具 (tools.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tools` | 列出所有工具 |
| POST | `/api/tools` | 创建工具 |
| PUT | `/api/tools/<tool_id>` | 更新工具 |
| DELETE | `/api/tools/<tool_id>` | 删除工具 |
| POST | `/api/tools/<tool_id>/toggle` | 切换启用状态 |

---

## 任务中心 (task_center.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/task-center` | 列出所有任务 |
| POST | `/api/task-center` | 创建任务 |
| PUT | `/api/task-center/<task_id>` | 更新任务 |
| DELETE | `/api/task-center/<task_id>` | 删除任务 |
| POST | `/api/task-center/<task_id>/toggle` | 切换启用状态 |
| POST | `/api/task-center/<task_id>/run` | 手动执行任务 |

---

## 心跳 (heartbeat.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/heartbeat` | 获取心跳配置 |
| PUT | `/api/heartbeat` | 更新心跳配置 |
| POST | `/api/heartbeat/run` | 手动触发心跳 |
| GET | `/api/heartbeat/content` | 获取心跳内容 |
| PUT | `/api/heartbeat/content` | 保存心跳内容 |

---

## 文件与工作区 (files.py + workspace_*.py)

### 文件操作

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/upload` | 上传文件 |
| GET | `/static/files/<filename>` | 访问文件 |
| GET | `/api/files/<safe_name>/preview` | 预览文件 |

### 私有工作区

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sessions/<session_id>/workspace/files` | 列出工作区文件 |
| POST | `/api/sessions/<session_id>/workspace/upload` | 上传文件到工作区 |
| GET | `/api/sessions/<session_id>/workspace/files/<filename>` | 下载工作区文件 |
| DELETE | `/api/sessions/<session_id>/workspace/files/<filename>` | 删除工作区文件 |
| POST | `/api/sessions/<session_id>/workspace/folders` | 创建文件夹 |
| POST | `/api/sessions/<session_id>/workspace/files/<filename>/move` | 移动文件 |
| POST | `/api/sessions/<session_id>/workspace/files/<filename>/move-to-shared` | 移动到共享区 |
| GET | `/api/sessions/<session_id>/workspace/files/<filename>/preview` | 预览文件 |

### 共享工作区

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspace/shared/files` | 列出共享文件 |
| GET | `/api/workspace/shared/files/<filename>` | 获取共享文件 |
| DELETE | `/api/workspace/shared/files/<filename>` | 删除共享文件 |
| POST | `/api/workspace/shared/folders` | 创建共享文件夹 |
| POST | `/api/workspace/shared/files/<filename>/move` | 移动共享文件 |
| POST | `/api/workspace/shared/files/<filename>/move-to-private` | 移动到私有区 |

### 杂项

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/workspace/download` | 按路径下载文件 |
| POST | `/api/workspace/convert/pptx-to-pdf` | PPTX 转 PDF |

---

## 语音 (voice.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/tts/synthesize` | 文字转语音 |
| GET | `/api/tts/audio/<filename>` | 获取 TTS 音频文件 |
| POST | `/api/stt/transcribe` | 语音转文字 (faster-whisper) |

---

## Live2D (live2d.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/live2d/random-talk` | 随机对话 |
| POST | `/api/live2d/menu-options` | 菜单选项回复 |
| POST | `/api/live2d/reset` | 重置对话历史 |
| GET | `/api/live2d/history` | 获取对话历史 |
| POST | `/api/live2d/comment` | 发送评论 |

---

## 推送通知 (push.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sw.js` | Service Worker |
| GET | `/manifest.webmanifest` | PWA Manifest |
| GET | `/api/push/public-key` | 获取 VAPID 公钥 |
| GET | `/api/push/status` | 推送状态 |
| POST | `/api/push/subscribe` | 订阅推送 |
| POST | `/api/push/unsubscribe` | 取消订阅 |
| POST | `/api/push/test` | 测试推送 |

---

## 公开会话 (public_sessions.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sessions/<session_id>/public` | 公开会话 |
| DELETE | `/api/sessions/<session_id>/public` | 取消公开 |
| GET | `/api/sessions/<session_id>/public/status` | 获取公开状态 |
| GET | `/public/<public_id>` | 查看公开会话页面 |
| GET | `/api/public/<public_id>` | 获取公开会话数据 |

---

## QQ 管理 (qq_overview.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/qq/users` | 列出 QQ 用户 |
| GET | `/api/qq/groups` | 列出 QQ 群组 |
| GET | `/api/qq/messages/<qq_type>/<qq_id>` | 获取 QQ 消息 |
| DELETE | `/api/qq/messages/<qq_type>/<qq_id>` | 删除 QQ 消息 |
| GET | `/api/qq/sessions` | 列出 QQ 会话 |
| POST | `/api/qq/sessions/<session_id>/sync` | 同步 QQ 会话 |
| POST | `/api/qq/sessions/<session_id>/send` | 发送 QQ 消息 |
| POST | `/api/qq/link-session` | 关联 QQ 会话 |

---

## 其他

### API 密钥 (api_keys.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/api-keys` | 列出 API 密钥 |
| GET | `/api/api-keys/<key_id>` | 获取单个密钥 |
| POST | `/api/api-keys` | 创建密钥 |
| PUT | `/api/api-keys/<key_id>` | 更新密钥 |
| DELETE | `/api/api-keys/<key_id>` | 删除密钥 |

### 二维码 (qrcode.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/qrcode/generate` | 生成二维码 |
| GET | `/qrcode/session/<session_id>` | 生成会话分享二维码 |

### Web Agent (web_agent.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/web-agent/tools` | 列出可用工具 |
| POST | `/api/web-agent/execute` | 执行工具 |
| POST | `/api/web-agent/chat` | 与 Web Agent 对话 |

### 配置迁移 (config_transfer.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/config-transfer/export` | 导出配置包 |
| POST | `/api/config-transfer/import` | 导入配置包 |

### 管理杂项 (admin_misc.py)

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/commands` | 获取命令目录 |
| GET | `/api/startup-status` | 获取启动状态 |
| GET | `/api/tokens` | Token 使用统计 |
| GET | `/api/tokens/rankings` | Token 使用排行 |
| GET | `/api/tokens/export` | 导出 Token 记录 |
| GET | `/api/logs` | 获取系统日志 |
| POST | `/api/logs` | 添加日志 |
| DELETE | `/api/logs` | 清空日志 |
| POST | `/api/logs/cleanup` | 清理日志文件 |
| GET | `/api/settings` | 获取系统设置 |
| PUT | `/api/settings` | 更新系统设置 |
| GET | `/api/stats` | 系统统计 |
| GET | `/api/stats/messages` | 消息统计（按时间段） |
| GET | `/api/stats/platforms` | 平台消息统计 |
| POST | `/api/system/reload-core` | 重载核心模块 |
| POST | `/api/system/reload-config` | 重载配置 |

---

## 统一响应格式

所有接口返回统一 JSON 格式：

```json
{
  "success": true,
  "data": {},
  "message": "操作成功"
}
```

错误响应：

```json
{
  "success": false,
  "error": "错误信息"
}
```
