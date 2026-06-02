import importlib
import os
import sys
import threading

from dotenv import load_dotenv

from nbot.logging_config import configure_ncatbot_log_file_name

# Skip ncatbot's GitHub proxy auto-detection during startup.
# None means "probe proxies"; empty string means "connect directly".
os.environ.setdefault("GITHUB_PROXY", "")
configure_ncatbot_log_file_name(sys.argv, os.environ)

from ncatbot.utils.config import config as ncatbot_config  # noqa: E402
from ncatbot.utils.logger import get_log  # noqa: E402


def _load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)
    else:
        load_dotenv()


_load_env_file()


def _apply_runtime_ncatbot_config():
    bot_uin = os.getenv("BOT_UIN")
    if bot_uin:
        ncatbot_config.set_bot_uin(bot_uin)

    root = os.getenv("ROOT")
    if root:
        ncatbot_config.set_root(root)

    ws_uri = os.getenv("WS_URI")
    if ws_uri:
        ncatbot_config.set_ws_uri(ws_uri)

    token = os.getenv("TOKEN")
    if token:
        ncatbot_config.set_token(token)

    webui_uri = os.getenv("WEBUI_URI")
    if webui_uri:
        ncatbot_config.set_webui_uri(webui_uri)


_apply_runtime_ncatbot_config()

_log = get_log()
_commands_module = None
web_server_instance = None
_pending_qq_bot = None
_web_server_started = threading.Event()


def _get_commands_module():
    global _commands_module
    if _commands_module is None:
        _commands_module = importlib.import_module("nbot.commands")
    return _commands_module


def _set_web_server_bot(bot):
    global web_server_instance, _pending_qq_bot
    _pending_qq_bot = bot
    if web_server_instance:
        web_server_instance.set_qq_bot(bot)
        _log.info("QQ Bot reference set in web server")


def _prepare_web_server(bot=None):
    global web_server_instance
    from nbot.web import create_web_app
    import logging

    werkzeug_log = logging.getLogger("werkzeug")
    werkzeug_log.setLevel(logging.ERROR)
    werkzeug_log.disabled = True

    app, socketio, web_server = create_web_app()
    web_server_instance = web_server

    if bot:
        _set_web_server_bot(bot)
    elif _pending_qq_bot:
        _set_web_server_bot(_pending_qq_bot)

    return app, socketio, web_server


def start_web_server(host="0.0.0.0", port=5000, bot=None, prepared=None):
    global web_server_instance
    try:
        _log.info(f"Starting Web Chat Server on {host}:{port}...")
        if prepared is None:
            app, socketio, web_server = _prepare_web_server(bot=bot)
        else:
            app, socketio, web_server = prepared
            web_server_instance = web_server
            if bot:
                _set_web_server_bot(bot)
            elif _pending_qq_bot:
                _set_web_server_bot(_pending_qq_bot)
        _web_server_started.set()
        socketio.run(
            app,
            host=host,
            port=port,
            debug=False,
            allow_unsafe_werkzeug=True,
            log_output=False,
        )
    except ImportError as e:
        _web_server_started.set()
        _log.error(f"Failed to import web module: {e}")
        _log.info(
            "Install flask and flask-socketio to enable web chat: pip install flask flask-socketio"
        )
    except Exception as e:
        _web_server_started.set()
        _log.error(f"Failed to start web server: {e}")


def run_bot():
    _log.info("Starting NekoBot QQ service...")
    commands = _get_commands_module()
    _set_web_server_bot(commands.bot)
    commands.bot.run(enable_webui_interaction=False)


def run_cli():
    """启动CLI模式"""
    _log.info("Starting NekoBot CLI mode...")
    try:
        from nbot.cli_cc_style import CCStyleCLI
        cli = CCStyleCLI()
        cli.run()
    except ImportError as e:
        _log.error(f"Failed to import CLI module: {e}")
        _log.info("Install rich to enable CLI: pip install rich")
        print("\n错误: 需要安装 rich 库")
        print("请运行: pip install rich")
    except Exception as e:
        _log.error(f"CLI error: {e}")
        print(f"\nCLI错误: {e}")


def run_cli_and_web(host="0.0.0.0", port=5000):
    """同时启动 CLI 和 Web"""
    _log.info("Starting NekoBot CLI and Web Dashboard...")

    # 准备 Web 服务器
    prepared = _prepare_web_server(bot=None)

    # 启动 Web 服务器线程
    web_thread = threading.Thread(
        target=start_web_server,
        args=(host, port, None, prepared),
        name="web-server",
        daemon=True,
    )
    web_thread.start()

    # 启动 CLI（在主线程）
    run_cli()


def run_bot_with_mcp(host="0.0.0.0", port=5000, no_web=False):
    """同时启动 Bot + MCP Server

    Bot 在后台线程运行，MCP Server 在主线程运行（stdio 模式）。
    适合 Claude Code / Cursor 等 AI Agent 连接。
    """
    _log.info("Starting NekoBot with MCP Server...")

    # 启动 QQ Bot 后台线程（如果配置了）
    if _has_qq_bot_config():
        _log.info("Starting QQ Bot in background thread...")
        bot_thread = threading.Thread(
            target=run_bot,
            name="qq-bot-main",
            daemon=True,
        )
        bot_thread.start()
    else:
        _log.info("No QQ bot config found, skipping QQ bot startup")

    # 启动 Web 服务器线程（除非禁用）
    if not no_web:
        try:
            prepared = _prepare_web_server(bot=None)
            web_thread = threading.Thread(
                target=start_web_server,
                args=(host, port, None, prepared),
                name="web-server",
                daemon=True,
            )
            web_thread.start()
            _log.info(f"Web Dashboard starting on {host}:{port}")
        except Exception as e:
            _log.warning(f"Web server failed to start: {e}")

    # 在主线程启动 MCP Server（stdio 模式）
    _load_mcp_config_and_run()


def run_mcp_only():
    """仅启动 MCP Server（不启动 QQ Bot 和 Web）

    适合 Claude Code / Cursor 等 AI Agent 连接，
    不依赖 QQ Bot 配置，不启动 Web Dashboard。
    """
    _log.info("Starting MCP Server only (no bot, no web)...")
    _load_mcp_config_and_run()


def _load_mcp_config_and_run():
    """加载 MCP 配置并启动 MCP Server"""
    from nbot.mcp.config import load_mcp_config

    config = load_mcp_config()
    transport = config.get("transport", "stdio")

    # 启动 MCP Server。MCPContext 会优先复用已存在的全局 Gateway；
    # mcp-only 模式下没有全局实例时，才会根据 config 创建一个共享同一数据目录的 Gateway。
    from nbot.mcp.server import create_mcp_server
    mcp = create_mcp_server(config)

    if transport == "streamable-http":
        host = config.get("server", {}).get("host", "127.0.0.1")
        port = config.get("server", {}).get("port", 5001)
        _log.info("Starting MCP Server (streamable-http) on %s:%s ...", host, port)
    else:
        _log.info("Starting MCP Server (stdio)...")

    mcp.run(transport=transport)


def run_mcp_connect(url: str):
    """连接远程 MCP Server 并启动交互式客户端"""
    import asyncio
    from nbot.mcp.client import run_mcp_connect as _run_connect
    _log.info("Connecting to remote MCP Server: %s", url)
    asyncio.run(_run_connect(url))


def _has_qq_bot_config():
    """检查是否配置了QQ机器人（ncatbot/napcat）"""
    bot_uin = os.getenv("BOT_UIN", "").strip()
    ws_uri = os.getenv("WS_URI", "").strip()
    
    # 如果环境变量没有配置，尝试从config.ini读取
    if not bot_uin or not ws_uri:
        try:
            import configparser
            config_parser = configparser.ConfigParser()
            config_parser.read("config.ini", encoding="utf-8")
            bot_uin = config_parser.get("BotConfig", "bot_uin", fallback="").strip()
            ws_uri = config_parser.get("BotConfig", "ws_uri", fallback="").strip()
        except Exception:
            pass
    
    # 检查配置是否有效（bot_uin是QQ号，ws_uri是websocket地址）
    has_bot_uin = bool(bot_uin and bot_uin not in ["", "0"])
    has_ws_uri = bool(ws_uri and ws_uri not in ["", "ws://", "ws://localhost"])
    
    return has_bot_uin and has_ws_uri


if __name__ == "__main__":
    import sys

    web_disabled = "--no-web" in sys.argv
    only_web = "--only-web" in sys.argv
    cli_mode = "--cli" in sys.argv
    cli_and_web = "--cli-and-web" in sys.argv
    mcp_mode = "--mcp" in sys.argv
    mcp_only = "--mcp-only" in sys.argv
    mcp_connect = "--mcp-connect" in sys.argv
    web_port = 5000
    web_host = "0.0.0.0"

    mcp_connect_url = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--web-port" and i + 1 < len(sys.argv):
            web_port = int(sys.argv[i + 1])
        if arg == "--web-host" and i + 1 < len(sys.argv):
            web_host = sys.argv[i + 1]
        if arg == "--mcp-connect" and i + 1 < len(sys.argv):
            mcp_connect_url = sys.argv[i + 1]

    if mcp_connect:
        # MCP 客户端模式 - 连接远程 MCP Server
        if not mcp_connect_url:
            # 从 config.ini 读取 connect_url
            try:
                import configparser
                cp = configparser.ConfigParser()
                cp.read("config.ini", encoding="utf-8")
                mcp_connect_url = cp.get("mcp", "connect_url", fallback="")
            except Exception:
                pass
        if not mcp_connect_url:
            print("错误: 请指定远程 MCP Server URL")
            print("用法: python bot.py --mcp-connect <url>")
            print("示例: python bot.py --mcp-connect http://127.0.0.1:5001/mcp")
            sys.exit(1)
        run_mcp_connect(mcp_connect_url)
    elif mcp_only:
        # 仅 MCP 模式 - 不启动 Bot 和 Web
        run_mcp_only()
    elif mcp_mode:
        # Bot + MCP 模式 - Bot 后台运行，MCP Server 主线程 stdio
        run_bot_with_mcp(host=web_host, port=web_port, no_web=web_disabled)
    elif cli_and_web:
        # CLI + Web 模式 - 同时启动命令行和 Web 界面
        run_cli_and_web(host=web_host, port=web_port)
    elif cli_mode:
        # CLI模式 - 启动命令行界面
        run_cli()
    elif web_disabled:
        _log.info("Starting NekoBot (Web disabled)...")
        run_bot()
    elif only_web:
        _log.info("Starting NekoBot Web Dashboard only (QQ disabled)...")
        prepared = _prepare_web_server(bot=None)
        start_web_server(host=web_host, port=web_port, bot=None, prepared=prepared)
    else:
        # 检查是否配置了QQ机器人
        if _has_qq_bot_config():
            _log.info("Starting NekoBot with Web Dashboard...")
            prepared = _prepare_web_server(bot=None)
            bot_thread = threading.Thread(
                target=run_bot,
                name="qq-bot-main",
                daemon=True,
            )
            bot_thread.start()
            start_web_server(host=web_host, port=web_port, bot=None, prepared=prepared)
        else:
            _log.info("No QQ bot config found, starting Web Dashboard only...")
            _log.info("To enable QQ bot, set BOT_UIN and WS_URI in .env or config.ini")
            prepared = _prepare_web_server(bot=None)
            start_web_server(host=web_host, port=web_port, bot=None, prepared=prepared)
