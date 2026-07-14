# Docker 部署

> 通过 Docker / Docker Compose 一键部署 NekoBot，镜像发布在 GitHub Container Registry (ghcr.io)

## 镜像信息

::: info
- **镜像仓库**：`ghcr.io/asukaneko/nekobot`
- **支持架构**：`linux/amd64`、`linux/arm64`
- **暴露端口**：`5000`（Web 后台）
- **数据卷**：`/app/data`（会话、角色卡、Web 配置等运行时数据）
:::

## 标签策略

| 标签 | 说明 | 更新时机 |
| --- | --- | --- |
| `latest` | 稳定版，跟随最新语义化 tag | 发布 `v*.*.*` 时滚动 |
| `v3.1.2` / `3.1.2` | 精确版本 | 发布对应 tag 时 |
| `3.1` / `3` | 主次版本 / 主版本 | 发布同主版本 tag 时滚动 |
| `nightly` | 跟随 master 的每日构建 | 每次 push master |
| `master` | 跟随 master 分支 | 每次 push master |
| `sha-<短哈希>` | 精确到某次提交 | 每次构建 |

生产环境建议使用精确版本号（如 `3.1.2`），便于回滚与可复现部署。

## 前置准备

::: warning
- 已安装 Docker 20.10+（或 Podman 等兼容运行时）
- 已准备好 `.env` 配置文件（参考 [快速开始](./quick-start.md#配置环境变量)）
- NapCatQQ 需独立部署（本镜像不内置），通过 `WS_URI` 连接
:::

## 快速运行

### 1. 准备配置

```bash
mkdir -p nekobot/data
cd nekobot
cp .env.example .env
# 编辑 .env 填入 WEB_PASSWORD、BOT_UIN、WS_URI 等
```

### 2. 拉取并运行

```bash
docker run -d \
  --name nekobot \
  --restart unless-stopped \
  -p 5000:5000 \
  -v "$(pwd)/data:/app/data" \
  -v "$(pwd)/.env:/app/.env:ro" \
  --env-file .env \
  ghcr.io/asukaneko/nekobot:3.1.2
```

启动后访问 `http://<服务器IP>:5000`，使用 `.env` 中的 `WEB_PASSWORD` 登录。

## Docker Compose

推荐使用 Compose 管理长期部署。新建 `docker-compose.yml`：

```yaml
services:
  nekobot:
    image: ghcr.io/asukaneko/nekobot:3.1.2
    container_name: nekobot
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    env_file:
      - .env
    # 如需自定义启动参数，覆盖 command
    # command: ["python", "bot.py", "--only-web"]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:5000/"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s
```

启动：

```bash
docker compose up -d
```

查看日志：

```bash
docker compose logs -f nekobot
```

## 启动模式

镜像默认入口为 `python bot.py`（QQ + Web 完整模式）。可通过覆盖 `command` 切换其他模式：

| 模式 | command |
| --- | --- |
| 仅 Web 后台 | `["python", "bot.py", "--only-web"]` |
| 仅 QQ（无 Web） | `["python", "bot.py", "--no-web"]` |
| CLI + Web | `["python", "bot.py", "--cli-and-web"]` |
| 自定义端口 | `["python", "bot.py", "--web-host", "0.0.0.0", "--web-port", "8080"]` |

::: tip
仅 Web 模式不连接 QQ，适合做 AI 对话演示或纯 Web 部署。
:::

## 数据持久化

::: danger
**必须挂载 `/app/data` 卷**，否则容器重建后会丢失全部会话、角色卡、记忆与 Web 配置。
:::

`/app/data` 包含的关键内容：

| 路径 | 说明 |
| --- | --- |
| `data/sessions.db` | 全局会话数据库（SQLite） |
| `data/character/` | 角色卡运行时数据 |
| `data/web/` | Web 面板核心数据（含加密的 AI 配置、登录令牌等） |
| `data/workspaces/` | 各会话工作空间 |
| `data/memories.json` | 全局记忆 |
| `data/world_books.json` | 世界书 |

建议同时挂载 `logs/` 便于排查问题。

## 升级

```bash
# 1. 备份数据
docker run --rm -v "$(pwd)/data:/data" -v "$(pwd):/backup" alpine \
  tar czf /backup/nekobot-data-$(date +%Y%m%d).tar.gz -C /data .

# 2. 更新镜像标签
docker compose pull
# 或指定新版本：编辑 docker-compose.yml 中的 image tag

# 3. 重启容器
docker compose up -d
```

::: warning
跨大版本升级前请先完整备份 `data/` 目录，并查阅 [更新日志](./changelog.md) 确认是否有破坏性变更。
:::

## 与 NapCatQQ 协同部署

完整方案通常需要两个容器：NekoBot + NapCatQQ。示例：

```yaml
services:
  napcat:
    image: mlikiowa/napcat-docker:latest
    container_name: napcat
    restart: unless-stopped
    ports:
      - "3001:3001"   # WebSocket
      - "6099:6099"   # WebUI
    volumes:
      - ./napcat/config:/app/napcat/config
      - ./napcat/data:/app/napcat/data
    # 在 napcat/config 中配置 WS 服务端点为 ws://0.0.0.0:3001

  nekobot:
    image: ghcr.io/asukaneko/nekobot:3.1.2
    container_name: nekobot
    restart: unless-stopped
    depends_on:
      - napcat
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
    env_file:
      - .env
    environment:
      - WS_URI=ws://napcat:3001   # 通过 Docker 网络访问 napcat 容器
```

::: tip
两个容器需在同一 Docker 网络中才能通过服务名互访。Compose 默认创建的网络已满足此条件。
:::

## 本地构建

如需自行构建（例如内网部署或自定义依赖）：

```bash
git clone https://github.com/asukaneko/nekobot.git
cd nekobot
docker build -t nekobot:local .
docker run -d -p 5000:5000 -v "$(pwd)/data:/app/data" --env-file .env nekobot:local
```

## 常见问题

### 容器启动后 Web 无法访问

- 检查端口映射：`docker port nekobot`
- 查看日志：`docker logs nekobot`
- 健康检查：`docker inspect --format='{{.State.Health.Status}}' nekobot`

### `.env` 修改后不生效

`.env` 以只读方式挂载时，修改后需重启容器：

```bash
docker restart nekobot
```

### 数据库被锁 / SQLite 报错

确保 `data/` 目录对容器内进程可读写。Linux 下若使用非 root 运行，需 `chown` 对应 UID。

### 想用 HTTPS

容器内默认 HTTP。HTTPS 建议通过反向代理（Nginx / Caddy / Traefik）终结，或将证书挂载到容器并在 `.env` 中配置 `HTTPS=true` 与证书路径。
