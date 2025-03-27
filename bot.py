from ncatbot.core import BotClient, GroupMessage, PrivateMessage
from ncatbot.utils.logger import get_log
from config import load_config
from chat import chat,group_messages,user_messages # 导入 chat 函数
import re,jmcomic,os,sys,requests,random,configparser,json,yaml

_log = get_log()

bot_id = load_config() # 加载配置,返回机器人qq号

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
    reply_text = "测试成功喵~\n输入 /help 查看帮助喵~"
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

            with open("option.yml", "r", encoding="utf-8") as f:
                conf = yaml.safe_load(f)
                after_photo_list = conf.get("plugins", {}).get("after_photo", [])
                if after_photo_list and isinstance(after_photo_list, list):
                    pdf_dir = after_photo_list[0].get("kwargs", {}).get("pdf_dir", "./cache/pdf/")
                else:
                    pdf_dir = "./cache/pdf/"
                if not pdf_dir.endswith(os.path.sep):
                    pdf_dir += os.path.sep
                file_path = os.path.join(pdf_dir, f"{comic_id}.pdf")

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

@register_command("/set_prompt")
@register_command("/sp")
async def handle_set_prompt(msg, is_group=True):
    prompt_content = ""
    if msg.raw_message.startswith("/set_prompt"):
        prompt_content = msg.raw_message[len("/set_prompt"):].strip()
    elif msg.raw_message.startswith("/sp"):
        prompt_content = msg.raw_message[len("/sp"):].strip()
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


@register_command("/del_prompt")
@register_command("/dp")
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

@register_command("/get_prompt")
@register_command("/gp")
async def handle_get_prompt(msg, is_group=True):
    id_str = str(msg.group_id if is_group else msg.user_id)
    if is_group:
        try:
            with open(f"prompts/group/group_{id_str}.txt", "r", encoding="utf-8") as file:
                prompt = file.read()
                await msg.reply(text=prompt)
        except FileNotFoundError:
            await msg.reply(text="没有找到提示词喵~")
    else:
        try:
            with open(f"prompts/user/user_{id_str}.txt", "r", encoding="utf-8") as file:
                prompt = file.read()
                await bot.api.post_private_msg(msg.user_id, text=prompt)
        except FileNotFoundError:
            await bot.api.post_private_msg(msg.user_id, text="没有找到提示词喵~")


@register_command("/agree") # 同意好友请求
async def handle_agree(msg, is_group=True):
    if not is_group:
        await bot.api.set_friend_add_request(flag=msg.user_id, approve=True,remark=msg.user_id)
        await bot.api.post_private_msg(msg.user_id, text="已同意好友请求喵~")
    else:
        await bot.api.set_friend_add_request(flag=msg.user_id, approve=True,remark=msg.user_id)
        await msg.reply(text="已同意好友请求喵~")


@register_command("/restart")
async def handle_restart(msg, is_group=True):
    reply_text = "正在重启喵~"
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)
    # 重启逻辑
    os.execv(sys.executable, [sys.executable] + sys.argv)


@register_command("/random_image")
@register_command("/ri")
async def handle_random_image(msg, is_group=True):
    # 在urls.ini中获取图片的url列表
    config = configparser.ConfigParser()
    config.read('urls.ini')
    urls = json.loads(config['ri']['urls'])

    random_number = random.randint(0, len(urls)-1)
    image_path = urls[random_number]
    if is_group:
        await bot.api.post_group_file(msg.group_id, image=image_path)
    else:
        await bot.api.post_private_file(msg.user_id, image=image_path)

@register_command("/random_words")
@register_command("/rw")
async def handle_random_words(msg, is_group=True):
    words = requests.get("https://uapis.cn/api/say").text
    if is_group:
        await msg.reply(text=words)
    else:
        await bot.api.post_private_msg(msg.user_id, text=words)


@register_command("/weather")
@register_command("/w")
async def handle_weather(msg, is_group=True):
    location = None
    if msg.raw_message.startswith("/weather"):
        location = msg.raw_message[len("/weather"):].strip()
    elif msg.raw_message.startswith("/w"):
        location = msg.raw_message[len("/w"):].strip()
    if not location:
        reply_text = "格式错误喵~ 请输入 /weather 城市名"
    else:
        # 调用天气 API 获取数据
        res = requests.get(f"https://uapis.cn/api/weather?name={location}")
        weather = res.json().get("weather")
        weather_info = f"{location}的天气是 {weather} 喵~"
        reply_text = weather_info
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)

@register_command("/random_emoticons")
@register_command("/re")
async def handle_random_emoticons(msg, is_group=True):
    #在urls.ini中获取表情包的url列表
    config = configparser.ConfigParser()
    config.read('urls.ini')
    urls = json.loads(config['re']['urls'])

    random_number = random.randint(0, len(urls)-1)
    if is_group:
        await bot.api.post_group_file(msg.group_id,image=urls[random_number])
    else:
        await bot.api.post_private_file(msg.user_id, image=urls[random_number])

@register_command("/st")
async def handle_st(msg, is_group=True):
    tags = msg.raw_message[len("/st"):].strip()
    res = requests.get(f"https://api.lolicon.app/setu/v2?tag={tags}").json().get("data")[0].get("urls").get("original")
    if is_group:
        await bot.api.post_group_file(msg.group_id,image=res)
    else:
        await bot.api.post_private_file(msg.user_id, image=res)

@register_command("/help")
@register_command("/h")
async def handle_help(msg, is_group=True):
    help_text = ("欢迎使用喵~~\n"
                 "/jm xxxxxx 下载漫画\n"
                 "/set_prompt 或 /sp 设置提示词\n"
                 "/del_prompt 或 /dp 删除提示词\n"
                 "/get_prompt 或 /gp 获取提示词\n"
                 "/agree 同意好友请求\n"
                 "/restart 重启Bot\n"
                 "/random_image 或 /ri 发送随机图片\n"
                 "/random_words 或 /rw 发送随机一言\n"
                 "/weather 城市名 或 /w 城市名 发送天气\n"
                 "/random_emoticons 或 /re 发送随机表情包\n"
                 "/st 标签名 发送随机涩图,标签支持与或(& |)\n"
                 "/help 或 /h 查看帮助"
    )
    if is_group:
        await msg.reply(text=help_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=help_text)


@bot.group_event()
async def on_group_message(msg: GroupMessage):
    _log.info(msg)
    for command, handler in command_handlers.items():
        if msg.raw_message.startswith(command):
            await handler(msg, is_group=True)
            return
    if msg.raw_message.startswith("/chat"):
        content = chat(msg.raw_message, group_id=msg.group_id,group_user_id=msg.user_id)
        await msg.reply(text=content)

    if msg.message[0].get("type") == "at" and msg.message[0].get("data").get("qq") == bot_id:
    #如果是at机器人
        try:
            ori_content = msg.message[1].get("data").get("text") #避免@的消息为空
        except IndexError:
            ori_content = "有人@了你"
        content = chat(ori_content, group_id=msg.group_id,group_user_id=msg.user_id)
        await msg.reply(text=content)

    if msg.message[0].get("type") == "reply" and msg.message[1].get("type") == "at" and msg.message[1].get("data").get("qq") == bot_id:
        #如果是回复机器人的消息
        try:
            ori_content = msg.message[2].get("data").get("text")
        except IndexError:
            ori_content = "有人回复了你"
        content = chat(ori_content, group_id=msg.group_id,group_user_id=msg.user_id)
        await msg.reply(text=content)

    """
    if msg.message[0].get("type") == "image" and msg.raw_message.startswith("/chat"):
        url = msg.message[0].get("data").get("url")
        content = chat(url, group_id=msg.group_id,image=True)
        await msg.reply(text=content)
    """

@bot.private_event()
async def on_private_message(msg: PrivateMessage):
    _log.info(msg)
    for command, handler in command_handlers.items():
        if msg.raw_message.startswith(command):
            await handler(msg, is_group=False)
            return
    if msg.message[0].get("type") == "image":
        url = msg.message[0].get("data").get("url")
        content = chat(url, user_id=msg.user_id,image=True)
        await bot.api.post_private_msg(msg.user_id, text=content)
        return

    if msg.raw_message: # 检查消息是否为空,避免接受文件后的空消息被回复
        content = chat(msg.raw_message, user_id=msg.user_id)
        await bot.api.post_private_msg(msg.user_id, text=content)

if __name__ == "__main__":
    bot.run(reload=False)