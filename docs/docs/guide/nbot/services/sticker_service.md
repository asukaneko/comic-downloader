# sticker_service - AI 表情包服务

## 概述

表情包服务根据角色当前心情（mood）自动匹配对应的二次元表情包图片/GIF，通过 [nekos.best](https://nekos.best) 免费 API 获取随机图片。

```text
AI 回复生成
  → 读取角色当前 mood
  → 匹配 nekos.best endpoint（happy/cry/angry/blush 等）
  → 请求 nekos.best API 获取随机图片
  → 附加到回复消息中
```

## 架构

### 核心文件

| 文件 | 职责 |
|------|------|
| `nbot/services/sticker_service.py` | 表情包服务主模块，心情→endpoint 映射、API 请求、发送逻辑 |

### 配置来源（优先级从高到低）

| 优先级 | 来源 | 配置项 |
|--------|------|--------|
| 1 | `data/settings.json` | `features.sticker`（开关）、`features.sticker_probability`（概率） |
| 2 | 环境变量 | `NBOT_STICKER_ENABLED`、`NBOT_STICKER_PROBABILITY` |
| 3 | 内置默认值 | 默认关闭，概率 0.3 |

## 心情映射

表情包服务将角色的中文心情映射到 nekos.best 的 API endpoint：

### 积极情绪

| 心情 | endpoint | 说明 |
|------|----------|------|
| 开心、快乐、高兴、幸福、黏人 | `happy` | 开心类 |
| 得意、放松、微笑、平静、期待 | `smile` | 微笑类 |
| 笑 | `laugh` | 大笑 |

### 消极情绪

| 心情 | endpoint | 说明 |
|------|----------|------|
| 生气、愤怒 | `angry` | 生气 |
| 委屈、伤心、难过、哭、受伤 | `cry` | 哭泣 |
| 沉默 | `pout` | 噘嘴 |
| 不安、害怕、紧张 | `shocked` | 震惊 |

### 社交情绪

| 心情 | endpoint | 说明 |
|------|----------|------|
| 害羞、脸红、感动、依赖 | `blush` | 脸红 |
| 尴尬、无语 | `facepalm` | 扶额 |

::: tip 未匹配的心情
如果角色当前心情不在映射表中，服务会随机选择一个 endpoint。
:::

## 使用方式

### 自动发送

当 AI 角色回复消息时，如果表情包功能开启且命中概率，系统会自动附带一张匹配当前心情的表情包图片。

### Web 后台配置

在 Web 后台的 **功能开关** 页面，找到"表情包"开关：

- **开启/关闭** — 控制是否在回复中附带表情包
- **概率** — 0~1 之间的浮点数，控制每条回复附带表情包的概率（默认 0.3，即 30%）

### 环境变量配置

```bash
# 启用表情包功能
NBOT_STICKER_ENABLED=true

# 设置发送概率（0~1）
NBOT_STICKER_PROBABILITY=0.3
```

### settings.json 配置

```json
{
  "features": {
    "sticker": true,
    "sticker_probability": 0.3
  }
}
```

## API 说明

### nekos.best API

- **Base URL**: `https://nekos.best/api/v2`
- **Endpoint**: `/{category}`（如 `/happy`、`/cry`、`/angry`）
- **方法**: GET
- **返回**: JSON，包含图片 URL

```json
// GET https://nekos.best/api/v2/happy
{
  "results": [
    {
      "url": "https://nekos.best/api/v2/happy/xxx.png",
      "artist_name": "...",
      "source_url": "..."
    }
  ]
}
```

## 相关页面

- [ai - AI客户端](./ai.md) — AI 模型配置
- [character - 实时情感引擎](../character/index.md) — 角色心情系统
- [routes - API路由](../web/routes.md) — Web 后台功能开关 API
