<div align="center">
<h1 style = "text-align:center;">🚀可以下载本子下载和聊天的猫娘机器人</h1> 

![cover](https://img.picui.cn/free/2025/04/19/6803c76d2bbf9.png)

> _a bot for downloading comics and chatting with ai_  


</div>

---

### 开始之前
>环境为 <u>___windows___</u>  
>建议使用 __小号__ 登录  
>基于jmcomic和ncatbot开发

 + **相关文档** 

| jmcomic | [![](https://img.shields.io/badge/jmcomic-on_Github-blue)](https://github.com/hect0x7/JMComic-Crawler-Python) | [![](https://img.shields.io/badge/jmcomic-Readthedocs.io-orange)](https://jmcomic.readthedocs.io/zh-cn/latest/) |
|:-:|:-:|:-:|

| napcat |[![](https://img.shields.io/badge/napcat-on_Github-blue)](https://github.com/NapNeko/NapCatQQ) | [![](https://img.shields.io/badge/napcat-Github.IO-orange)](https://napneko.github.io)
 |:-:|:-:|:-:|

  | ncatbot  | [![](https://img.shields.io/badge/ncatbot-on_Github-blue)](https://github.com/liyihao1110/ncatbot) | [![](https://img.shields.io/badge/Python_Sdk-Ncatbot-8A2BE2)](https://docs.ncatbot.xyz/) |
  |:-:|:-:|:-:|




```
目录结构：
.
│  bot.py
│  chat.py
│  config.ini
│  config.py
│  commands.py
│  LICENSE
│  neko.txt
│  number.txt
│  option.yml
│  README.md
│  requirements.txt
│  urls.ini
│  
├─logs
│      
├─napcat
│  ├─...... 
│  └─......
├─plugins
│
├─prompts
│  ├─group
│  └─user
├─saved_images
│      
├─saved_message
│
└─cache
    ├─comic
    ├─saved_images
    ├─list
    ├─fav
    ├─pdf
    └─......
```        


### 一、安装依赖
```
pip install -r requirements.txt
```
### 二、更改配置
```
config.ini：修改账号、大模型api、图片保存等
option.yml: 修改漫画下载目录、下载方式等
urls.ini: 修改图片获取api地址, 如不修改则使用默认地址
```
### 三、运行
```
python bot.py
```
命令行会提示下载napcat，然后扫码登录即可

### 四、命令相关
>commands.py 中 设置了 ___命令注册装饰器___ ，可以自行添加命令    
---
>命令列表：  
>___/jm xxxxxx 下载漫画  
/search xxx 搜索漫画  
/get_fav 获取收藏夹  
/jmrank 获取排行榜  
/add_fav xxx 添加收藏夹
/set_prompt 或 /sp 设置提示词  
/del_prompt 或 /dp 删除提示词  
//get_prompt 或 /gp 获取提示词  
/agree   同意好友请求  
/restart   重启Bot  
/random_image 或 /ri 发送随机图片  
/random_emoticons 或 /re 发送随机表情包  
/st 标签名 发送随机涩图,标签支持与或(& |)  
/weather 城市名 或 /w 城市名 发送天气  
/help 或 /h 查看帮助___  
……  
### 五、提示
+ 登录以后可在napcat\logs文件夹下找到webui的登录地址
+ 群聊使用 _/chat_ 命令或 _@机器人_ 即可聊天，私聊默认处理所有非命令消息为聊天 
+ _大模型默认使用硅基流动的，新用户免费赠送15元_
+ 群聊想要ai处理图片，则先发图片，再回复自己的信息，回复内容必须要先@机器人
+ tts可以自己上传音色，详情看chat.py中注释
+ ___如果你发现没有正常配置napcat，则打开网址：127.0.0.1:6099，token默认为napcat，然后登录，在网络配置那里新建一个websocket服务端，端口为默认的3001，然后保存即可___

### 六、更多  

+ 支持图片识别，需去https://platform.moonshot.cn/console/account 获取api，免费赠送15元。填入config.ini中（第二个api）
+ 支持多群聊以及用户自定义提示词
+ 群聊支持用户感知，聊天支持时间感知
+ 支持保存对话记录
+ 快速添加命令
+ 配置要求低，轻量，占用内存小

