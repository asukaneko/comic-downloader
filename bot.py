import importlib
import logging
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


def _generate_self_signed_cert(cert_dir: str) -> tuple:
    """生成自签名 SSL 证书，返回 (cert_path, key_path)。

    如果证书已存在且未过期，则复用。
    """
    import datetime

    cert_path = os.path.join(cert_dir, "selfsigned_cert.pem")
    key_path = os.path.join(cert_dir, "selfsigned_key.pem")

    # 检查已有证书是否有效（未过期）
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import serialization

            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())
            if cert.not_valid_after_utc > datetime.datetime.now(datetime.timezone.utc):
                _log.info("Reusing existing self-signed certificate (not expired)")
                return cert_path, key_path
            else:
                _log.info("Existing self-signed certificate expired, regenerating...")
        except Exception:
            _log.info("Cannot read existing certificate, regenerating...")

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import ipaddress

        # 生成 RSA 私钥
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # 构建证书主体
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "NcatBot"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NcatBot Self-Signed"),
        ])

        # 构建 SAN（Subject Alternative Names）
        san_list = [
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            x509.IPAddress(ipaddress.IPv4Address("0.0.0.0")),
        ]
        # 尝试添加主机名
        try:
            san_list.append(x509.DNSName(os.uname().nodename))
        except Exception:
            pass

        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=3650))  # 10 年有效期
            .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )

        os.makedirs(cert_dir, exist_ok=True)

        # 写入证书
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # 写入私钥
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))

        _log.info(f"Self-signed certificate generated: {cert_path}")
        return cert_path, key_path

    except ImportError:
        _log.error("cryptography library not installed. Run: pip install cryptography")
        return None, None
    except Exception as e:
        _log.error(f"Failed to generate self-signed certificate: {e}")
        return None, None


def print_startup_banner(version: str, mode: str):
    """Rich 启动横幅，失败时回退到纯文本。"""
    try:
        import colorama
        colorama.just_fix_windows_console()

        import shutil
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.align import Align
        from rich.text import Text
        from rich import box
        import pyfiglet
        import platform

        console = Console()
        terminal_width = shutil.get_terminal_size((100, 30)).columns
        panel_width = min(terminal_width - 4, 88)

        # ASCII Logo
        logo = pyfiglet.figlet_format("NekoBot", font="slant")
        console.print(Align.center(Text(logo, style="bold cyan")))

        # 信息表格
        table = Table.grid(expand=True, padding=(0, 1))
        table.add_column(style="bold white", width=10)
        table.add_column(style="bold green", width=18)
        table.add_column(style="bold white", width=10)
        table.add_column(style="bold cyan", width=22)

        table.add_row("Version", f"v{version}", "Python", platform.python_version())
        table.add_row("OS", platform.system(), "Mode", mode)
        table.add_row("Status", "[bold green]Ready[/]", "Bot", "[dim]Waiting...[/]")

        panel = Panel(
            table,
            title="[bold white]NekoBot Startup[/bold white]",
            border_style="magenta",
            box=box.ROUNDED,
            padding=(1, 3),
            width=panel_width,
        )
        console.print(Align.center(panel))
        console.print()
    except Exception:
        _log.info("=" * 52)
        _log.info(f"  NekoBot v{version}")
        _log.info(f"  Mode: {mode}")
        _log.info("=" * 52)


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


def start_web_server(host="0.0.0.0", port=5000, bot=None, prepared=None, ssl_context=None):
    global web_server_instance
    try:
        proto = "https" if ssl_context else "http"
        _log.info(f"Starting Web Chat Server on {proto}://{host}:{port}...")
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
            ssl_context=ssl_context,
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


def run_cli_and_web(host="0.0.0.0", port=5000, ssl_context=None):
    """同时启动 CLI 和 Web"""
    _log.info("Starting NekoBot CLI and Web Dashboard...")

    # 准备 Web 服务器
    prepared = _prepare_web_server(bot=None)

    # 启动 Web 服务器线程
    web_thread = threading.Thread(
        target=start_web_server,
        args=(host, port, None, prepared, ssl_context),
        name="web-server",
        daemon=True,
    )
    web_thread.start()

    # 启动 CLI（在主线程）
    run_cli()


def run_bot_with_mcp(host="0.0.0.0", port=5000, no_web=False, ssl_context=None):
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
                args=(host, port, None, prepared, ssl_context),
                name="web-server",
                daemon=True,
            )
            web_thread.start()
            proto = "https" if ssl_context else "http"
            _log.info(f"Web Dashboard starting on {proto}://{host}:{port}")
        except Exception as e:
            _log.warning(f"Web server failed to start: {e}")

    # 在主线程启动 MCP Server（stdio 模式）
    _load_mcp_config_and_run()


def run_mcp_only():
    """仅启动 MCP Server（不启动 QQ Bot 和 Web）

    适合 Claude Code / Cursor 等 AI Agent 连接，
    不依赖 QQ Bot 配置，不启动 Web Dashboard。
    stdout 保留给 MCP JSON-RPC 协议，所有非协议输出重定向到 stderr。
    """
    import builtins
    import logging
    import sys

    # 1. 重定向所有 logging handler 到 stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.DEBUG)
    stderr_handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(stderr_handler)
    root.setLevel(logging.INFO)

    # 2. 重定向 print() 到 stderr（不影响 sys.stdout，MCP SDK 仍用它做协议通信）
    _original_print = builtins.print

    def _print_to_stderr(*args, **kwargs):
        kwargs.setdefault("file", sys.stderr)
        _original_print(*args, **kwargs)

    builtins.print = _print_to_stderr

    root.info("Starting MCP Server only (no bot, no web)...")
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
        logging.getLogger("bot").info("Starting MCP Server (streamable-http) on %s:%s ...", host, port)
    else:
        logging.getLogger("bot").info("Starting MCP Server (stdio)...")

    # 注册本机 MCP 服务到 Web 管理界面（两种模式都注册）
    _register_builtin_mcp_server(transport, config)

    mcp.run(transport=transport)


def _register_builtin_mcp_server(transport: str, config: dict):
    """将本机 MCP Server 注册为 Web 管理界面的内置服务

    写入 data/web/mcp_servers.json，标记 _builtin=True（不可删除，可关闭）。
    根据 transport 类型生成不同的连接配置。
    """
    import json
    import os
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parent
    data_dir = root / "data" / "web"
    config_path = data_dir / "mcp_servers.json"

    os.makedirs(data_dir, exist_ok=True)

    # 构建条目
    builtin_id = "_builtin_local_mcp"
    entry = {
        "id": builtin_id,
        "name": "本机 MCP 服务",
        "transport": transport,
        "enabled": True,
        "auto_connect": True,
        "_builtin": True,
        "connected": False,
        "tool_count": 0,
        "last_connected_at": None,
    }

    if transport == "streamable-http":
        host = config.get("server", {}).get("host", "127.0.0.1")
        port = config.get("server", {}).get("port", 5001)
        display_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
        entry["url"] = f"http://{display_host}:{port}/mcp"
        entry["description"] = f"Bot MCP Server（HTTP {display_host}:{port}）"
    else:
        # stdio 模式：用当前 Python 解释器 + bot.py --mcp
        entry["command"] = sys.executable
        entry["args"] = [str(root / "bot.py"), "--mcp-only"]
        entry["description"] = "Bot MCP Server（stdio 子进程）"

    # 读取现有配置
    configs = []
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                configs = data
        except Exception:
            pass

    existing = next((c for c in configs if c.get("id") == builtin_id), None)

    if existing:
        # 更新，保留 created_at
        entry["created_at"] = existing.get("created_at", "")
        existing.update(entry)
    else:
        from datetime import datetime
        entry["created_at"] = datetime.now().isoformat()
        configs.insert(0, entry)

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(configs, f, ensure_ascii=False, indent=2)
        _log.info("[MCP] 已注册本机 MCP 服务: %s", transport)
    except Exception as e:
        _log.warning("[MCP] 注册本机 MCP 服务失败: %s", e)


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
    port_from_cli = False
    ssl_cert_cli = ""
    ssl_key_cli = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--web-port" and i + 1 < len(sys.argv):
            web_port = int(sys.argv[i + 1])
            port_from_cli = True
        if arg == "--web-host" and i + 1 < len(sys.argv):
            web_host = sys.argv[i + 1]
        if arg == "--mcp-connect" and i + 1 < len(sys.argv):
            mcp_connect_url = sys.argv[i + 1]
        if arg == "--ssl-cert" and i + 1 < len(sys.argv):
            ssl_cert_cli = sys.argv[i + 1]
        if arg == "--ssl-key" and i + 1 < len(sys.argv):
            ssl_key_cli = sys.argv[i + 1]

    # 如果命令行未指定端口，尝试从 settings.json 读取
    ssl_context = None
    if not port_from_cli:
        try:
            import json as _json
            _settings_path = os.path.join("data", "web", "settings.json")
            if os.path.exists(_settings_path):
                with open(_settings_path, "r", encoding="utf-8") as _f:
                    _saved_settings = _json.load(_f)
                    _saved_port = _saved_settings.get("web_port")
                    if _saved_port and str(_saved_port).isdigit():
                        web_port = int(_saved_port)
                    # 读取 SSL 配置（命令行参数优先）
                    if not ssl_cert_cli and not ssl_key_cli and _saved_settings.get("ssl_enabled"):
                        if _saved_settings.get("ssl_self_signed"):
                            # 自签名模式
                            _cert, _key = _generate_self_signed_cert(os.path.join("data", "web", "ssl"))
                            if _cert and _key:
                                ssl_context = (_cert, _key)
                        else:
                            _cert = _saved_settings.get("ssl_certfile", "")
                            _key = _saved_settings.get("ssl_keyfile", "")
                            if _cert and _key and os.path.isfile(_cert) and os.path.isfile(_key):
                                ssl_context = (_cert, _key)
                                _log.info(f"SSL enabled from settings: cert={_cert}, key={_key}")
                            elif _cert or _key:
                                _log.warning("SSL certfile or keyfile not found, falling back to HTTP")
        except Exception:
            pass

    # 从 .env / config.ini 读取 HTTPS 配置（settings.json 未启用时）
    if not ssl_context and not ssl_cert_cli and not ssl_key_cli:
        _https_env = os.getenv("HTTPS", "").strip().lower()
        _cert_env = os.getenv("SSL_CERTFILE", "").strip()
        _key_env = os.getenv("SSL_KEYFILE", "").strip()
        _self_signed_env = os.getenv("SSL_SELF_SIGNED", "").strip().lower()

        # 如果 .env 没有，尝试 config.ini
        if not _https_env and not _cert_env:
            try:
                import configparser
                _cp = configparser.ConfigParser()
                _cp.read("config.ini", encoding="utf-8")
                _https_env = _cp.get("HTTPS", "enabled", fallback="").strip().lower()
                _cert_env = _cp.get("HTTPS", "certfile", fallback="").strip()
                _key_env = _cp.get("HTTPS", "keyfile", fallback="").strip()
                _self_signed_env = _cp.get("HTTPS", "self_signed", fallback="").strip().lower()
            except Exception:
                pass

        if _https_env in ("true", "1", "yes", "on"):
            if _self_signed_env in ("true", "1", "yes", "on"):
                _cert, _key = _generate_self_signed_cert(os.path.join("data", "web", "ssl"))
                if _cert and _key:
                    ssl_context = (_cert, _key)
            elif _cert_env and _key_env:
                if os.path.isfile(_cert_env) and os.path.isfile(_key_env):
                    ssl_context = (_cert_env, _key_env)
                    _log.info(f"SSL enabled from env/config: cert={_cert_env}, key={_key_env}")
                else:
                    _log.warning(f"SSL cert/key file not found: {_cert_env}, {_key_env}")
            else:
                # HTTPS=true 但没有指定证书，自动使用自签名
                _cert, _key = _generate_self_signed_cert(os.path.join("data", "web", "ssl"))
                if _cert and _key:
                    ssl_context = (_cert, _key)

    # 命令行 SSL 参数（优先级最高）
    if ssl_cert_cli and ssl_key_cli:
        if os.path.isfile(ssl_cert_cli) and os.path.isfile(ssl_key_cli):
            ssl_context = (ssl_cert_cli, ssl_key_cli)
            _log.info(f"SSL enabled from CLI: cert={ssl_cert_cli}, key={ssl_key_cli}")
        else:
            _log.warning(f"CLI SSL cert/key file not found: {ssl_cert_cli}, {ssl_key_cli}")

    # ── 启动横幅 ──
    from nbot.version import __version__

    if mcp_connect:
        _mode = "MCP Client"
    elif mcp_only:
        _mode = "MCP Server Only"
    elif mcp_mode:
        _mode = "QQ Bot + MCP Server" + (" + Web" if not web_disabled else "")
    elif cli_and_web:
        _mode = "CLI + Web Dashboard"
    elif cli_mode:
        _mode = "CLI Only"
    elif web_disabled:
        _mode = "QQ Bot Only"
    elif only_web:
        _mode = "Web Dashboard Only"
    else:
        _mode = "QQ Bot + Web Dashboard"

    # mcp_only 模式下不打印 banner，避免污染 stdout（JSON-RPC 协议通道）
    if not mcp_only:
        print_startup_banner(version=__version__, mode=_mode)

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
        run_bot_with_mcp(host=web_host, port=web_port, no_web=web_disabled, ssl_context=ssl_context)
    elif cli_and_web:
        # CLI + Web 模式 - 同时启动命令行和 Web 界面
        run_cli_and_web(host=web_host, port=web_port, ssl_context=ssl_context)
    elif cli_mode:
        # CLI模式 - 启动命令行界面
        run_cli()
    elif web_disabled:
        _log.info("Starting NekoBot (Web disabled)...")
        run_bot()
    elif only_web:
        _log.info("Starting NekoBot Web Dashboard only (QQ disabled)...")
        prepared = _prepare_web_server(bot=None)
        start_web_server(host=web_host, port=web_port, bot=None, prepared=prepared, ssl_context=ssl_context)
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
            start_web_server(host=web_host, port=web_port, bot=None, prepared=prepared, ssl_context=ssl_context)
        else:
            _log.info("No QQ bot config found, starting Web Dashboard only...")
            _log.info("To enable QQ bot, set BOT_UIN and WS_URI in .env or config.ini")
            prepared = _prepare_web_server(bot=None)
            start_web_server(host=web_host, port=web_port, bot=None, prepared=prepared, ssl_context=ssl_context)
