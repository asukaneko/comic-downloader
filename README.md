<h2 style = "text-align:center;">基于NcatBot和jmcomic的本子下载和聊天的猫娘机器人</h2> 

---
>环境为 <u>___windows___</u>  
>强烈建议使用 ___小号___ 登录

```
目录结构：
.
│  bot.py
│  chat.py
│  config.ini
│  config.py
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
>bot.py 中 设置了 ___命令注册装饰器___ ，可以自行添加命令    
---
>命令列表：  
>___/jm xxxxxx 下载漫画  
/set_prompt 或 /sp 设置提示词  
/del_prompt 或 /dp 删除提示词  
//get_prompt 或 /gp 获取提示词
/agree   同意好友请求  
/restart   重启Bot  
/random_image 或 /ri 发送随机图片  
/random_words 或 /rw 发送随机一言  
/random_emoticons 或 /re 发送随机表情包
/st 标签名 发送随机涩图,标签支持与或(& |)  
/weather 城市名 或 /w 城市名 发送天气  
……  
/help 或 /h 查看帮助___

### 五、提示
+ 登录以后可在napcat\logs文件夹下找到webui的登录地址
+ 群聊使用 _/chat_ 命令或 _@机器人_ 即可聊天，私聊默认处理所有非命令消息为聊天 
+ _大模型默认使用硅基流动的，免费赠送15元_]()
+ 群聊想要ai处理图片，则先发图片，再回复自己的信息，回复内容仅包含@机器人

### 六、更多  

+ 支持图片识别，需去https://platform.moonshot.cn/console/account 获取api，免费赠送15元。填入config.ini中（第二个api）
+ 支持多群聊以及用户自定义提示词
+ 群聊支持用户感知，聊天支持时间感知
+ 支持保存对话记录
+ 快速添加命令
+ 配置要求低，轻量，占用内存小

