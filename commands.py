from ncatbot.core import BotClient, GroupMessage, PrivateMessage
from ncatbot.utils.logger import get_log
from config import load_config
from chat import group_messages,user_messages # 导入 chat 函数
import jmcomic,requests,random,configparser,json,yaml
from jmcomic import *
import asyncio

_log = get_log()

if_tts = False #判断是否开启TTS

bot_id = load_config() # 加载配置,返回机器人qq号

bot = BotClient()

command_handlers = {}
group_imgs = {} # 用于存储图片信息

def register_command(*command,help_text = None): # 注册命令
    def decorator(func):
        command_handlers[command] = func
        if help_text is not None:
            func.help_text = help_text
        return func
    return decorator

def load_address(): # 加载配置文件，返回图片保存地址
    with open("option.yml", "r", encoding="utf-8") as f:
        conf = yaml.safe_load(f)
        after_photo_list = conf.get("plugins", {}).get("after_photo", [])
        if after_photo_list and isinstance(after_photo_list, list):
            pdf_dir = after_photo_list[0].get("kwargs", {}).get("pdf_dir", "./cache/pdf/")
        else:
            pdf_dir = "./cache/pdf/"
        if not pdf_dir.endswith(os.path.sep):
            pdf_dir += os.path.sep
        return pdf_dir

@register_command("测试")
async def handle_test(msg, is_group=True):
    if not msg.raw_message == "测试":
        return
    reply_text = "测试成功喵~\n输入 /help 查看帮助喵~"
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)

@register_command("/tts",help_text = "/tts -> 开启或关闭TTS")
async def handle_tts(msg, is_group=True):
    global if_tts
    if_tts = not if_tts
    text = "已开启TTS喵~" if if_tts else "已关闭TTS喵~"
    if is_group:
        await msg.reply(text=text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=text)

@register_command("/jmrank",help_text = "/jmrank 月排行/周排行 -> ")
async def handle_jmrank(msg, is_group=True):
    if is_group:
        await msg.reply(text="正在获取排行喵~")
    else:
        await bot.api.post_private_msg(msg.user_id, text="正在获取排行喵~")
    select = msg.raw_message[len("/jmrank"):].strip()

    # 创建客户端
    op = JmOption.default()
    cl = op.new_jm_client()

    page: JmCategoryPage = cl.categories_filter(
        page=1,
        time=JmMagicConstants.TIME_ALL,
        category=JmMagicConstants.CATEGORY_ALL,
        order_by=JmMagicConstants.ORDER_BY_LATEST,
    )

    if select == "月排行":
        page: JmCategoryPage = cl.month_ranking(1)
    elif select == "周排行":
        page: JmCategoryPage = cl.week_ranking(1)

    cache_dir = load_address()[:-4]
    cache_dir += "rank/"
    os.makedirs(cache_dir,exist_ok = True)

    name = time.time()
    for page in cl.categories_filter_gen(page=1,  # 起始页码
                                         # 下面是分类参数
                                         time=JmMagicConstants.TIME_WEEK,
                                         category=JmMagicConstants.CATEGORY_ALL,
                                         order_by=JmMagicConstants.ORDER_BY_VIEW,
                                         ):
        for aid, atitle in page:
            #content += f"ID: {aid}\n"
            with open(cache_dir + f"{select}_{name}.txt", "a", encoding="utf-8") as f:
                f.write(f"ID: {aid} Name: {atitle}\n\n")

    if is_group:
        await bot.api.post_group_file(msg.group_id, file=cache_dir + f"{select}_{name}.txt")
    else:
        await bot.api.upload_private_file(msg.user_id, cache_dir + f"{select}_{name}.txt", f"{select}_{name}.txt")

@register_command("/search",help_text = "/search -> 搜索漫画")
async def handle_search(msg, is_group=True):
    if is_group:
        await msg.reply(text="正在搜索喵~")
    else:
        await bot.api.post_private_msg(msg.user_id, text="正在搜索喵~")

    cache_dir = load_address()[:-4]
    cache_dir += "search/"
    os.makedirs(cache_dir,exist_ok = True)

    content = msg.raw_message[len("/search"):].strip()
    name = content + str(time.time()).replace(".", "")
    client = JmOption.default().new_jm_client()
    with open(cache_dir + f"{name}.txt", "w", encoding="utf-8") as f:
        f.write(f"搜索结果：{content}\n")
    for i in range(5):# 搜索5页，可以自己修改
        page: JmSearchPage = client.search_site(search_query=content, page=i+1)
        for album_id, title in page:
            with open(cache_dir + f"{name}.txt", "a", encoding="utf-8") as f:
                f.write(f"ID: {album_id} Name: {title}\n\n")
    if is_group:
        await bot.api.post_group_file(msg.group_id, file=cache_dir + f"{name}.txt")
    else:
        await bot.api.upload_private_file(msg.user_id, cache_dir + f"{name}.txt", f"{content}.txt")

    '''
    # 直接搜索禁漫车号
    page = client.search_site(search_query='427413')
    album: JmAlbumDetail = page.single_album
    print(album.tags)
    '''

@register_command("/jm",help_text = "/jm 漫画ID -> 下载漫画")
async def handle_jmcomic(msg, is_group=True):
    match = re.match(r'^/jm\s+(\d+)$', msg.raw_message)
    if match:
        comic_id = match.group(1)
        # 立即回复用户，不等待下载完成
        reply_text = f"已开始下载漫画ID：{comic_id}，下载完成后会自动通知喵~"
        if is_group:
            await msg.reply(text=reply_text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=reply_text)

        # 创建后台任务
        asyncio.create_task(download_and_send_comic(comic_id, msg, is_group))
    else:
        error_msg = "格式错误了喵~，请输入 /jm 后跟漫画ID"
        if not is_group:
            await bot.api.post_private_msg(msg.user_id, text=error_msg)

# 新增后台任务函数
async def download_and_send_comic(comic_id, msg, is_group):
    try:
        # 在线程池中执行阻塞操作
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda:
            jmcomic.download_album(
                comic_id,
                jmcomic.create_option_by_file('./option.yml')
            )
        )

        pdf_dir = load_address()
        file_path = os.path.join(pdf_dir, f"{comic_id}.pdf")

        # 检查文件是否真正生成
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF文件未生成：{file_path}")

        success_text = f"漫画 {comic_id} 下载完成喵~"
        if is_group:
            await bot.api.post_group_file(msg.group_id, file=file_path)
            await msg.reply(text=success_text)
        else:
            await bot.api.upload_private_file(msg.user_id, file_path, f"{comic_id}.pdf")
            await bot.api.post_private_msg(msg.user_id, text=success_text)

    except Exception as e:
        error_msg = f"下载失败喵~: {str(e)}"
        if is_group:
            await msg.reply(text=error_msg)
        else:
            await bot.api.post_private_msg(msg.user_id, text=error_msg)

@register_command("/set_prompt","/sp",help_text = "/set_prompt 或者 /sp 提示词 -> 设定提示词")
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


@register_command("/del_prompt","/dp",help_text = "/del_prompt 或者 /dp -> 删除提示词")
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
                await msg.reply(text="提示词已删除喵~本子娘回来了喵~")
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
                await bot.api.post_private_msg(msg.user_id, text="提示词已删除喵~本子娘回来了喵~")
            except FileNotFoundError:
                await bot.api.post_private_msg(msg.user_id, text="没有可以删除的提示词喵~")

@register_command("/get_prompt","/gp",help_text = "/get_prompt 或者 /gp -> 获取提示词")
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


@register_command("/agree","/agree -> 同意好友请求") # 同意好友请求
async def handle_agree(msg, is_group=True):
    if not is_group:
        await bot.api.set_friend_add_request(flag=msg.user_id, approve=True,remark=msg.user_id)
        await bot.api.post_private_msg(msg.user_id, text="已同意好友请求喵~")
    else:
        await bot.api.set_friend_add_request(flag=msg.user_id, approve=True,remark=msg.user_id)
        await msg.reply(text="已同意好友请求喵~")


@register_command("/restart","/restart -> 重启机器人")
async def handle_restart(msg, is_group=True):
    reply_text = "正在重启喵~"
    if is_group:
        await msg.reply(text=reply_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=reply_text)
    # 重启逻辑
    os.execv(sys.executable, [sys.executable] + sys.argv)

#------以下为调用api发送文件的命令，采用异步方式发送文件------
# 新增后台任务函数
async def async_send_file(send_method, target_id, file_type, url):
    try:
        # 处理可能的重定向
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(url, allow_redirects=True, timeout=10))
        final_url = response.url

        # 异步发送文件
        await send_method(target_id, **{file_type: final_url})
    except Exception as e:
        pass

# 修改通用处理函数
async def handle_generic_file(msg, is_group: bool, section: str, file_type: str, custom_url: str = None):
    """通用文件处理函数（修复版）"""
    # 立即回复用户
    initial_text = "正在获取喵~"
    if initial_text:
        if is_group:
            await msg.reply(text=initial_text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=initial_text)

    try:
        # 修复配置读取逻辑
        if section:  # 仅当需要读取配置文件时
            loop = asyncio.get_event_loop()
            # 正确读取配置的方式
            def read_config():
                cfg = configparser.ConfigParser()
                cfg.read('urls.ini')
                if not cfg.has_section(section):
                    raise Exception(f"配置文件中缺少 [{section}] 段落")
                return cfg

            config = await loop.run_in_executor(None, read_config)
            urls = json.loads(config.get(section, 'urls'))
            selected_url = random.choice(urls)
        else:  # 使用自定义URL
            selected_url = custom_url

        # 创建后台任务
        send_method = bot.api.post_group_file if is_group else bot.api.post_private_file
        target_id = msg.group_id if is_group else msg.user_id
        asyncio.create_task(
            async_send_file(send_method, target_id, file_type, selected_url)
        )

    except Exception as e:
        error_msg = f"配置错误喵~: {str(e)}" if '配置' in str(e) else f"获取失败喵~: {str(e)}"
        if is_group:
            await msg.reply(text=error_msg)
        else:
            await bot.api.post_private_msg(msg.user_id, text=error_msg)

# 修改现有命令
@register_command("/random_image","/ri",help_text = "/random_image 或者 /ri -> 随机图片")
async def handle_random_image(msg, is_group=True):
    await handle_generic_file(msg, is_group, 'ri', 'image')

@register_command("/random_emoticons","/re",help_text = "/random_emoticons 或者 /re -> 随机表情包")
async def handle_random_emoticons(msg, is_group=True):
    await handle_generic_file(msg, is_group, 're', 'image')

@register_command("/st",help_text = "/st 标签名 -> 发送随机涩图,标签支持与或(& |)")
async def handle_st(msg, is_group=True):
    tags = msg.raw_message[len("/st"):].strip()
    res = requests.get(f"https://api.lolicon.app/setu/v2?tag={tags}").json().get("data")[0].get("urls").get("original")
    await handle_generic_file(msg, is_group,"","",custom_url=res)  # 特殊处理API调用

@register_command("/random_video","/rv",help_text = "/random_video 或者 /rv -> 随机二次元视频")
async def handle_random_video(msg, is_group=True):
    await handle_generic_file(msg, is_group, 'rv', 'video')

#---------------------------------------------

@register_command("/random_dice","/rd",help_text = "/random_dice 或者 /rd -> 发送随机骰子")
async def handle_random_dice(msg, is_group=True):
    if is_group:
        await bot.api.post_group_msg(msg.group_id,dice=True)
    else:
        await bot.api.post_private_msg(msg.user_id,dice=True)

@register_command("/random_rps","/rps",help_text = "/random_rps 或者 /rps -> 发送随机石头剪刀布")
async def handle_random_rps(msg, is_group=True):
    if is_group:
        await bot.api.post_group_msg(msg.group_id,rps=True)
    else:
        await bot.api.post_private_msg(msg.user_id,rps=True)

@register_command("/del_message","/dm",help_text = "/del_message 或者 /dm -> 删除对话记录")
async def handle_del_message(msg, is_group=True):
    if is_group:
        del group_messages[str(msg.group_id)]
        await msg.reply(text="主人要离我而去了吗？呜呜呜……好吧，那我们以后再见喵~")
    else:
        del user_messages[str(msg.user_id)]
        await bot.api.post_private_msg(msg.user_id, text="主人要离我而去了吗？呜呜呜……好吧，那我们以后再见喵~")


@register_command("/set_ids",help_text = "/set_ids 昵称 个性签名 性别 -> 设置账号信息")
async def handle_set(msg, is_group=True):
    """
            nickname: 昵称
            personal_note: 个性签名
            sex: 性别
            :return: 设置账号信息
    """
    msgs = msg.raw_message[len("/set_ids"):].split(" ")
    if len(msgs) < 3:
        text = "格式错误喵~ 请输入 /set 昵称 个性签名 性别"
        if is_group:
            await msg.reply(text=text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=text)
        return
    try:
        nickname = msgs[0]
        personal_note = msgs[1]
        sex = msgs[2]
        await bot.api.set_qq_profile(nickname=nickname, personal_note=personal_note, sex=sex)
        text = "设置成功喵~"
        if is_group:
            await msg.reply(text=text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=text)
    except Exception as e:
        text = "设置失败喵~"
        if is_group:
            await msg.reply(text=text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=text)

@register_command("/set_online_status",help_text = "/set_online_status 在线状态 -> 设置在线状态")
async def handle_set_online_status(msg, is_group=True):
    msgs = msg.raw_message[len("/set_online_status"):].split(" ")[0]
    await bot.api.set_online_status(msgs)
    text = "设置成功喵~"
    if is_group:
        await msg.reply(text=text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=text)

@register_command("/get_friends",help_text = "/get_friends -> 获取好友列表")
async def handle_get_friends(msg, is_group=True):
    friends = await bot.api.get_friend_list(False)
    if is_group:
        await msg.reply(text=friends)
    else:
        await bot.api.post_private_msg(msg.user_id, text=friends)

@register_command("/set_qq_avatar",help_text = "/set_qq_avatar 地址 -> 更改头像")
async def handle_set_qq_avatar(msg, is_group=True):
    msgs = msg.raw_message[len("/set_qq_avatar"):]
    await bot.api.set_qq_avatar(msgs)
    text = "设置成功喵~"
    if is_group:
        await msg.reply(text=text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=text)

@register_command("/send_like",help_text = "/send_like 目标QQ号 次数 -> 发送点赞")
async def handle_send_like(msg, is_group=True):
    msgs = msg.raw_message[len("/send_like"):].split(" ")
    if len(msgs) < 2:
        text = "格式错误喵~ 请输入 /send_like 目标QQ号 次数"
        if is_group:
            await msg.reply(text=text)
        else:
            await bot.api.post_private_msg(msg.user_id, text=text)
    target_qq = msgs[0]
    times = msgs[1]
    await bot.api.send_like(target_qq, times)
    text = "发送成功喵~"
    if is_group:
        await msg.reply(text=text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=text)

#将help命令放在最后
@register_command("/help","/h",help_text = "/help 或者 /h -> 查看帮助")
async def handle_help(msg, is_group=True):
    help_text = "欢迎使用喵~~\n"
    # 收集所有命令的帮助信息
    for cmd, handler in command_handlers.items():
        if hasattr(handler, 'help_text'):
            help_text += handler.help_text + "\n"
    if is_group:
        await msg.reply(text=help_text)
    else:
        await bot.api.post_private_msg(msg.user_id, text=help_text)

    system_help = ("[内置命令]\n"
                   "/cfg <plugin_name>.<cfg_name> <value> 更改插件配置\n"
                   "/plg 查看已安装插件\n"
                   "/sm <user_id> 设置管理员\n"
                   "/acs [-g] [ban]/[grant] <number> <path> 管理权限\n"
                   )
    if is_group:
        await msg.reply(text=system_help)
    else:
        await bot.api.post_private_msg(msg.user_id, text=system_help)
