# secure_store - 加密安全存储

## 概述

`secure_store.py` 提供基于 Fernet 对称加密的敏感数据持久化方案。用于加密存储 AI 配置（API Key）、AI 模型配置以及登录令牌等不应以明文出现在磁盘上的数据。

底层依赖 `cryptography` 库的 `Fernet` 实现，使用 AES-128-CBC 加密 + HMAC-SHA256 认证。

## 加密密钥管理

```python
def _load_or_create_key(data_dir: str) -> bytes:
    env_key = os.getenv("NBOT_SECURE_STORE_KEY", "").strip()
    if env_key:
        return env_key.encode("utf-8")

    path = os.path.join(data_dir, "secrets", "secure_store.key")
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read().strip()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    key = Fernet.generate_key()
    with open(path, "wb") as f:
        f.write(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        _log.debug("Could not restrict secure store key permissions")
    return key
```

密钥来源优先级：

| 优先级 | 来源 | 示例 |
|--------|------|------|
| 最高 | 环境变量 `NBOT_SECURE_STORE_KEY` | 适用于 Docker/K8s 部署 |
| 默认 | `data/web/secrets/secure_store.key` | 本地部署自动生成 |

密钥文件存储在 `{data_dir}/secrets/secure_store.key` 中，首次访问时自动生成，权限限制为 0600（仅属主可读写）。密钥为 Fernet 标准 32 字节 URL-safe Base64 编码。

## 加密格式

写入磁盘的加密文件采用 JSON 信封格式：

```python
def write_secure_json(file_path: str, data_dir: str, data: Any) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    envelope = {
        "version": 1,
        "encrypted": True,
        "algorithm": "fernet",
        "payload": _fernet(data_dir).encrypt(payload).decode("utf-8"),
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(envelope, f, ensure_ascii=False, indent=2)
```

写入流程：
1. 将原始数据序列化为紧凑 JSON（无多余空格）
2. 使用 Fernet 加密 payload
3. 将 ciphertext Base64 编码后放入信封结构
4. 将信封写入文件

读取流程：

```python
def read_secure_json(file_path: str, data_dir: str, default: Any) -> tuple[Any, bool]:
    if not os.path.exists(file_path):
        return default, False

    with open(file_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if not _is_encrypted_envelope(raw):
        return raw, True  # 旧版明文，触发迁移

    plaintext = _fernet(data_dir).decrypt(raw["payload"].encode("utf-8"))
    return json.loads(plaintext.decode("utf-8")), False
```

返回值 `was_plaintext` 标记是否读取了旧版明文文件。调用方据此决定是否需要将数据重新以加密格式保存。

## 密封格式检测

```python
def _is_encrypted_envelope(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and data.get("encrypted") is True
        and data.get("algorithm") == "fernet"
        and isinstance(data.get("payload"), str)
    )
```

通过检查三个条件判断文件是否为加密信封：

1. 顶层是字典
2. `encrypted` 字段为 `true`
3. `algorithm` 为 `"fernet"`
4. `payload` 存在且为字符串

## 使用场景

`persistence.py` 中三个数据文件使用加密存储：

| 文件 | 内容 | 敏感数据 |
|------|------|----------|
| `ai_config.json` | AI 提供商配置 | API Key |
| `ai_models.json` | 多模型配置 | 各模型的 API Key |
| `login_tokens.json` | 登录令牌 | 哈希后的登录凭证 |

### AI 配置示例

```python
# 写入（encrypt on save）
write_secure_json(
    os.path.join(server.data_dir, "ai_config.json"),
    server.data_dir,
    server.ai_config,  # 包含 api_key 字段
)

# 读取（automatic decrypt）
saved_config, was_plaintext = read_secure_json(
    ai_config_file, server.data_dir, {}
)
if was_plaintext:
    write_secure_json(ai_config_file, server.data_dir, saved_config)
```

### 登录令牌示例

```python
loaded_tokens, was_plaintext = read_secure_json(
    login_tokens_file, server.data_dir, {}
)

# 旧格式 Token key 自动迁移为 SHA-256 hash
if len(key) != 64:
    migrated[server._hash_token(key)] = value
```

## 安全说明

- **密钥泄露**：如果 `secrets/secure_store.key` 泄露，攻击者可解密所有存储的敏感数据。生产环境应使用 `NBOT_SECURE_STORE_KEY` 环境变量传递密钥，并将密钥文件排除在备份和版本控制之外。
- **加密算法**：Fernet 是 `cryptography` 库提供的高级加密 API，使用 AES-128-CBC + PKCS7 填充 + HMAC-SHA256 认证，防篡改防重放。
- **明文升级**：`persistence.py` 加载数据时自动检测明文旧文件并升级为加密格式，迁移过程对用户透明。
- **权限保护**：自动生成的密钥文件设置 `0o600` 权限，防止同服务器其他用户读取（Windows 下静默忽略此设置）。
