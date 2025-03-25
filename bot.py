from ncatbot.core import BotClient, GroupMessage, PrivateMessage
from ncatbot.utils.config import config
from ncatbot.utils.logger import get_log
import re, jmcomic, os
import configparser

_log = get_log()

config_parser = configparser.ConfigParser()
config_parser.read('config.ini')

# 从配置文件中获取配置信息
bot_uin = config_parser.get('BotConfig', 'bot_uin')
root = config_parser.get('BotConfig', 'root')
ws_uri = config_parser.get('BotConfig', 'ws_uri', fallback="ws://localhost:3001")
token = config_parser.get('BotConfig', 'token', fallback="")

api_key = config_parser.get('ApiKey', 'api_key')
base_url = config_parser.get('ApiKey', 'base_url')
model = config_parser.get('ApiKey', 'model')

config.set_bot_uin(bot_uin)  # 设置 bot qq 号 (必填)
config.set_root(root)  # 设置 bot 超级管理员账号 (建议填写)
config.set_ws_uri(ws_uri)  # 设置 napcat websocket server 地址
config.set_token(token)  # 设置 token (napcat 服务器的 token)

MAX_HISTORY_LENGTH = 20 #最大上下文数量

bot = BotClient()

#不同用户，群聊设置不同的上下文
user_messages = {}
group_messages = {}


def load_prompt(user_id=None, group_id=None):
    prompt_file = None
    if user_id:
        user_id = str(user_id)
        prompt_file = f"prompts/user/user_{user_id}.txt"
    elif group_id:
        group_id = str(group_id)
        prompt_file = f"prompts/group/group_{group_id}.txt"

    try:
        with open(prompt_file, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        try:
            with open("neko.txt", "r", encoding="utf-8") as file:
                return file.read()
        except FileNotFoundError:
            return ""


def chat(content, user_id=None, group_id=None):
    from openai import OpenAI

    if user_id:
        user_id = str(user_id)
        if user_id not in user_messages:
            prompt = load_prompt(user_id=user_id)
            user_messages[user_id] = [{"role": "system", "content": prompt}]
        messages = user_messages[user_id]
    elif group_id:
        group_id = str(group_id)
        if group_id not in group_messages:
            prompt = load_prompt(group_id=group_id)
            group_messages[group_id] = [{"role": "system", "content": prompt}]
        messages = group_messages[group_id]
    else:
        messages = []

    messages.append({"role": "user", "content": content})

    if len(messages) > MAX_HISTORY_LENGTH:
        messages = messages[-MAX_HISTORY_LENGTH:]

    client = OpenAI(api_key=api_key,
                    base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=False
    )
    assistant_response = response.choices[0].message.content
    messages.append({"role": "assistant", "content": assistant_response})
    return assistant_response


# 命令处理器字典
command_handlers = {}


def register_command(command):
    """命令注册装饰器"""

    def decorator(func):
        command_handlers[command] = func
        return func

    return decorator


# 注册测试命令
@register_command("测试")
async def handle_test(msg, is_group=True):
    reply_text = "NcatBot 测试成功喵~\n/jm xxxxxx 下载漫画\n/set_prompt 设置提示词\n/del_prompt 删除提示词"
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)


# 注册设置提示词命令
@register_command("/set_prompt")
async def handle_set_prompt(msg, is_group=True):
    prompt_content = msg.raw_message[len("/set_prompt"):].strip()
    id_str = str(msg.group_id if is_group else msg.user_id)
    os.makedirs("prompts", exist_ok=True)

    # 保存提示词文件
    prefix = "group" if is_group else "user"
    with open(f"prompts/{prefix}/{prefix}_{id_str}.txt", "w", encoding="utf-8") as file:
        file.write(prompt_content)

    # 更新上下文
    messages = group_messages if is_group else user_messages
    if id_str in messages:
        del messages[id_str]
    messages[id_str] = [{"role": "system", "content": prompt_content}]

    reply_text = "群组提示词已更新，对话记录已清除喵~" if is_group else "个人提示词已更新，对话记录已清除喵~"
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)


# 注册JMComic命令
@register_command("/jm")
async def handle_jmcomic(msg, is_group=True):
    match = re.match(r'^/jm\s+(\d+)$', msg.raw_message)
    if match:
        comic_id = match.group(1)
        reply_text = f"成功获取漫画ID了喵~: {comic_id}"
        if is_group:
            await msg.reply(text=reply_text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=reply_text)

        try:
            option = jmcomic.create_option_by_file('./option.yml')
            jmcomic.download_album(comic_id, option)
            file_path = f"F:/cache/pdf/{comic_id}.pdf"

            if is_group:
                await bot.api.post_group_file(msg.group_id, file=file_path)
                await msg.reply(text="漫画下好了喵~")
            else:
                await bot.api.upload_private_file(msg.user_id, file_path, f"{comic_id}.pdf")
                await bot.api.post_private_msg(msg.user_id, text=f"漫画下好了喵~")
        except Exception as e:
            error_msg = f"出错了喵~: {e}"
            if is_group:
                await msg.reply(text=error_msg)
            else:
                await bot.api.post_private_msg(msg.user_id, text=error_msg)
    else:
        error_msg = "格式错误了喵~，请输入 /jm 后跟漫画ID"
        if is_group:
            pass
        else:
            await bot.api.post_private_msg(msg.user_id, text=error_msg)

@register_command("/del_prompt")
async def handle_del_prompt(msg, is_group=True):
    id_str = str(msg.group_id if is_group else msg.user_id)
    if is_group:
        if id_str in group_messages:
            del group_messages[id_str]
            os.remove(f"prompts/group/group_{id_str}.txt")
            with open("neko.txt", "r", encoding="utf-8") as file:
                prompt = file.read()
                group_messages[id_str] = [{"role": "system", "content": prompt}]
            await msg.reply(text="提示词已删除喵~neko回来了喵~")
    else:
        if id_str in user_messages:
            del user_messages[id_str]
            os.remove(f"prompts/user/user_{id_str}.txt")
            with open("neko.txt", "r", encoding="utf-8") as file:
                prompt = file.read()
                user_messages[id_str] = [{"role": "system", "content": prompt}]
            await bot.api.post_private_msg(msg.user_id, text="提示词已删除喵~neko回来了喵~")


@bot.group_event()
async def on_group_message(msg: GroupMessage):
    _log.info(msg)
    for command, handler in command_handlers.items():
        if msg.raw_message.startswith(command):
            await handler(msg, is_group=True)
            return
    # 群聊需要明确使用/chat命令
    if msg.raw_message.startswith("/chat"):
        content = chat(msg.raw_message, group_id=msg.group_id)
        await msg.reply(text=content)


@bot.private_event()
async def on_private_message(msg: PrivateMessage):
    _log.info(msg)
    for command, handler in command_handlers.items():
        if msg.raw_message.startswith(command):
            await handler(msg, is_group=False)
            return
    # 私聊默认处理所有非命令消息为聊天
    content = chat(msg.raw_message, user_id=msg.user_id)
    await bot.api.post_private_msg(msg.user_id, text=content)


if __name__ == "__main__":
    bot.run(reload=False)