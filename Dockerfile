# syntax=docker/dockerfile:1.6
# NekoBot 主项目镜像
# 入口: python bot.py (默认启动 QQ + Web)
# 端口: 5000 (Web 面板)
# 数据: /app/data (建议挂载 volume 持久化)

FROM python:3.11-slim AS base

# 系统依赖:
#   - ffmpeg: faster-whisper / imageio-ffmpeg 解码
#   - build-essential / pkg-config: 部分 Python 包编译回退
#   - git: ncatbot 启动时的 git 探测 (项目里已 set GITHUB_PROXY="")
#   - ca-certificates curl: HTTPS 与健康检查
#   - libffi-dev libssl-dev: cryptography 编译回退
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
        pkg-config \
        git \
        ca-certificates \
        curl \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 升级 pip 并先装依赖 (利用 layer 缓存, 代码变更不会重装)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 运行时数据目录 (建议外部挂载)
RUN mkdir -p /app/data
VOLUME ["/app/data"]

# Web 端口
EXPOSE 5000

# 健康检查: Web 服务是否响应
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/ || exit 1

# 默认以非 root 运行 (data 目录需可写, 这里简化用 root; 如需非 root 请自行 chown)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GITHUB_PROXY="" \
    TZ=Asia/Shanghai

# 默认启动完整模式 (QQ + Web)
# 可通过 docker run 覆盖参数, 例如 --only-web
CMD ["python", "bot.py"]
