from ncatbot.core import BotClient, GroupMessage, PrivateMessage
from ncatbot.utils.logger import get_log
from config import load_config
from chat import chat,group_messages,user_messages # 导入 chat 函数
import re, jmcomic, os

_log = get_log()

load_config() # 加载配置

bot = BotClient()

command_handlers = {}

def register_command(command):
    def decorator(func):
        command_handlers[command] = func
        return func
    return decorator

@register_command("测试")
async def handle_test(msg, is_group=True):
    if not msg.raw_message == "测试":
        return
    reply_text = "测试成功喵~\n/jm xxxxxx 下载漫画\n/set_prompt 设置提示词\n/del_prompt 删除提示词"
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)

@register_command("/set_prompt")
async def handle_set_prompt(msg, is_group=True):
    prompt_content = msg.raw_message[len("/set_prompt"):].strip()
    id_str = str(msg.group_id if is_group else msg.user_id)
    os.makedirs("prompts", exist_ok=True)

    prefix = "group" if is_group else "user"
    with open(f"prompts/{prefix}/{prefix}_{id_str}.txt", "w", encoding="utf-8") as file:
        file.write(prompt_content)

    messages = group_messages if is_group else user_messages
    if id_str in messages:
        del messages[id_str]
    messages[id_str] = [{"role": "system", "content": prompt_content}]

    reply_text = "群组提示词已更新，对话记录已清除喵~" if is_group else "个人提示词已更新，对话记录已清除喵~"
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)

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
            try:
                os.remove(f"prompts/group/group_{id_str}.txt")
                with open("neko.txt", "r", encoding="utf-8") as file:
                    prompt = file.read()
                    group_messages[id_str] = [{"role": "system", "content": prompt}]
                await msg.reply(text="提示词已删除喵~neko回来了喵~")
            except FileNotFoundError:
                await msg.reply(text="没有可以删除的提示词喵~")

    else:
        if id_str in user_messages:
            del user_messages[id_str]
            try:
                os.remove(f"prompts/user/user_{id_str}.txt")
                with open("neko.txt", "r", encoding="utf-8") as file:
                    prompt = file.read()
                    user_messages[id_str] = [{"role": "system", "content": prompt}]
                await bot.api.post_private_msg(msg.user_id, text="提示词已删除喵~neko回来了喵~")
            except FileNotFoundError:
                await bot.api.post_private_msg(msg.user_id, text="没有可以删除的提示词喵~")

@register_command("/agree") # 同意好友请求
async def handle_agree(msg, is_group=True):
    if not is_group:
        await bot.api.set_friend_add_request(flag=msg.user_id, approve=True,remark=msg.user_id)
        await bot.api.post_private_msg(msg.user_id, text="已同意好友请求喵~")
    else:
        await bot.api.set_friend_add_request(flag=msg.user_id, approve=True,remark=msg.user_id)
        await msg.reply(text="已同意好友请求喵~")




@bot.group_event()
async def on_group_message(msg: GroupMessage):
    _log.info(msg)
    for command, handler in command_handlers.items():
        if msg.raw_message.startswith(command):
            await handler(msg, is_group=True)
            return
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
    content = chat(msg.raw_message, user_id=msg.user_id)
    await bot.api.post_private_msg(msg.user_id, text=content)

if __name__ == "__main__":
    bot.run(reload=False)