# 命令手册

## 漫画相关

| 命令 | 说明 |
|------|------|
| `/jm <ID>` | 下载漫画 |
| `/jmrank <月排行/周排行>` | 获取排行榜 |
| `/jm_search <内容>` | 搜索漫画 |
| `/jm_tag <标签>` | 搜索漫画标签 |
| `/jm_clear` | 清除缓存 |
| `/jm_send_user <on\|off>` | 开启/关闭群聊用户私信发送漫画 (admin) |
| `/jm_send <on\|off>` | 开启/关闭发送漫画 (admin) |
| `/jm_pwd <on\|off>` | 开启/关闭密码加密，密码为漫画 ID (admin) |
| `/jm_email <邮箱> <on\|off>` | 配置邮箱并开启或关闭发送漫画到邮箱 |

## 收藏管理

| 命令 | 说明 |
|------|------|
| `/get_fav <用户名> <密码>` | 获取收藏夹（群聊请私聊） |
| `/add_fav <ID>` | 添加收藏 |
| `/del_fav <ID>` | 删除收藏 |
| `/list_fav` | 查看收藏列表 |

## 黑名单

| 命令 | 说明 |
|------|------|
| `/add_black_list` 或 `/abl <ID>` | 添加黑名单 |
| `/del_black_list` 或 `/dbl <ID>` | 删除黑名单 |
| `/list_black_list` 或 `/lbl` | 查看黑名单 |
| `/add_global_black_list` 或 `/agbl <ID>` | 添加全局黑名单 (admin) |
| `/del_global_black_list` 或 `/dgbl <ID>` | 删除全局黑名单 (admin) |

## AI 聊天

| 命令 | 说明 |
|------|------|
| `/set_prompt` 或 `/sp <提示词>` | 设定当前会话提示词（群聊仅 admin） |
| `/del_prompt` 或 `/dp` | 删除当前会话提示词（群聊仅 admin） |
| `/get_prompt` 或 `/gp` | 获取当前会话提示词（群聊仅 admin） |
| `/del_message` 或 `/dm` | 删除对话记录（仅群 admin） |
| `/show_chat` 或 `/sc` | 发送完整聊天记录（仅群 admin） |
| `/new` | 创建新的对话会话，清空当前对话历史 (admin) |
| `/model` | 查看当前模型 (admin) |
| `/model <编号>` | 切换到指定模型 (admin) |
| `/model list` | 列出所有可用模型 (admin) |
| `/character` | 查看/切换角色 (admin) |
| `/character list` | 列出角色 (admin) |
| `/character <编号\|id\|名称>` | 切换角色 (admin) |
| `/new_agent` | 创建新的 Agent 对话并切换到当前频道 (admin) |
| `/new_character` | 退出 Agent 模式并恢复为新的角色对话 (admin) |
| `/resume [编号\|会话ID\|名称]` | 从 Web 会话载入到当前频道 (admin) |
| `/push` | 将当前频道会话上传到 Web 会话 (admin) |

## AI 总结与主动聊天

| 命令 | 说明 |
|------|------|
| `/summary_today` | 总结今天与机器人的聊天内容 |
| `/summary_recent` 或 `/sr [数量]` | 总结最近若干条群聊消息 |
| `/summary_auto` | 开启或关闭每日自动总结群聊记录 (admin) |
| `/auto_reply [on\|off\|话痨程度0-1]` | 开启/关闭或设置群聊智能自动回复 (admin) |
| `/主动聊天 [1\|0]` | 开启/关闭主动聊天（AI 自行决定聊天频率） |
| `/heartbeat` | 查看当前会话心跳 |
| `/heartbeat on [分钟]` | 开启当前会话心跳 |
| `/heartbeat off` | 关闭当前会话心跳 |
| `/heartbeat run` | 立即执行一次心跳 |

## 娱乐功能

| 命令 | 说明 |
|------|------|
| `/random_image` 或 `/ri` | 随机图片 |
| `/random_emoticons` 或 `/re` | 随机表情包 |
| `/st <标签>` | 随机涩图（标签支持与或 `&` `\|`） |
| `/random_video` 或 `/rv` | 随机二次元视频 |
| `/random_dice` 或 `/rd` | 随机骰子 |
| `/random_rps` 或 `/rps` | 石头剪刀布 |
| `/music <音乐名/id>` | 发送音乐 |
| `/random_music` 或 `/rm` | 随机音乐 |
| `/generate_photo` 或 `/gf <描述> <大小>` | AI 生成图片 |
| `/识别人物` | 识别图片中的二次元人物 |

## 下载功能

| 命令 | 说明 |
|------|------|
| `/dv <链接>` | 下载视频 |
| `/di <链接>` | 下载图片 |
| `/df <链接>` | 下载文件 |

## 轻小说

| 命令 | 说明 |
|------|------|
| `/findbook` 或 `/fb <书名>` | 搜索轻小说 |
| `/fa <作者>` | 搜索作者 |
| `/select <编号>` | 选择下载（先用 `/fb` 搜索） |
| `/info <书名>` | 获取轻小说信息 |
| `/random_novel` 或 `/rn` | 随机小说 |
| `/hotnovel <day\|month> [数量]` | 获取今日/本月热门轻小说（支持翻页） |
| `/novel_res <res值>` | 根据 res 编号下载轻小说 |
| `/set_wenku_cookie <Cookie>` | 更新文库 8 的 Cookie (admin) |

## MCP 服务管理

| 命令 | 说明 |
|------|------|
| `/mcp` | 查看 MCP 连接状态 (admin) |
| `/mcp list` | 列出 MCP 服务 (admin) |
| `/mcp tools <名称\|ID>` | 查看服务工具 (admin) |
| `/mcp add_http <名称> <URL>` | 添加 HTTP MCP 服务 (admin) |
| `/mcp add_stdio <名称> <command> [args_json]` | 添加 stdio MCP 服务 (admin) |
| `/mcp del <名称\|ID>` | 删除 MCP 服务 (admin) |
| `/mcp_connect <名称\|ID\|URL>` | 连接 MCP 服务 (admin) |
| `/mcp_disconnect <名称\|ID>` | 断开 MCP 服务 (admin) |

## 工作区

| 命令 | 说明 |
|------|------|
| `/workspace` 或 `/ws` | 查看当前会话工作区文件列表 |
| `/ws_send <文件名>` | 发送工作区中的文件 |

## MC 服务器

| 命令 | 说明 |
|------|------|
| `/mc <地址>` | 查询服务器 |
| `/mc_bind <地址>` | 绑定服务器 |
| `/mc_unbind` | 解绑服务器 |
| `/mc_show` | 查看绑定的服务器 |

## 定时任务

| 命令 | 说明 |
|------|------|
| `/remind <小时> <内容>` | 定时提醒 |
| `/premind <MM-DD> <HH:MM> <内容>` | 精确时间提醒 |
| `/task </bot.api.xxx> <时间> <循环>` | 定时任务 (admin) |
| `/list_tasks` 或 `/lt` | 查看任务 (admin) |
| `/cancel_tasks` 或 `/ct <名称>` | 取消任务 (admin) |

## 群聊管理

| 命令 | 说明 |
|------|------|
| `/at_all` | 识别@全体成员功能 (admin) |
| `/set_group_admin <QQ>` | 设置群管理员 (admin) |
| `/del_group_admin <QQ>` | 取消群管理员 (admin) |

## 系统管理

| 命令 | 说明 |
|------|------|
| `/restart` | 重启机器人 (admin) |
| `/shutdown` | 关闭机器人 (admin) |
| `/tts` | 开启或关闭 TTS (admin) |
| `/agree` | 同意好友请求 (admin) |
| `/smtp <host> <port> <user> <password> <tls> <from>` | 配置当前用户 SMTP 服务 |

## 管理员

| 命令 | 说明 |
|------|------|
| `/set_admin` 或 `/sa <QQ>` | 设置管理员 (root) |
| `/del_admin` 或 `/da <QQ>` | 删除管理员 (root) |
| `/get_admin` 或 `/ga` | 管理员列表 |
| `/myid` 或 `/id` | 获取你的用户 ID（用于添加管理员） |
| `/set_ids <昵称> <签名> <性别>` | 设置账号信息 (admin) |
| `/set_online_status <状态>` | 设置在线状态 (admin) |
| `/get_friends` | 获取好友列表 (admin) |
| `/set_qq_avatar <地址>` | 更改头像 (admin) |
| `/send_like <QQ> <次数>` | 发送点赞 (admin) |
| `/bot.api.函数名(参数=值)` | 自定义 API (admin) |

## 翻译与运势

| 命令 | 说明 |
|------|------|
| `/translate` 或 `/tr <文本>` | 翻译 |
| `/fortune` 或 `/jrrp` | 今日运势 |

## 帮助

| 命令 | 说明 |
|------|------|
| `/help` 或 `/h` | 查看帮助 |

---

::: tip
所有命令定义在 `nbot/commands.py` 中，使用 `@register_command` 装饰器注册。
:::
