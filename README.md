## 基于NapCat和jmcomic的本子下载和聊天的猫娘机器人

---
>环境为 <u>___windows___</u>  
>强烈建议用 ___小号___ 登录

一、安装依赖
```
pip install -r requirements.txt
```
二、更改配置
```
config.ini：修改账号、api等
option.yml: 修改下载目录、下载方式等
urls.ini: 修改api地址, 如不修改则使用默认地址
```
三、运行
```
python bot.py
```
命令行会提示下载napcat，然后扫码登录即可

四、其他
>bot.py 中 设置了 ___命令注册装饰器___ ，可以自行添加命令    
---
>命令列表：  
>___/jm xxxxxx 下载漫画  
/set_prompt 或 /sp 设置提示词  
/del_prompt 或 /dp 删除提示词  
/agree   同意好友请求  
/restart   重启Bot  
/random_image 或 /ri 发送随机图片  
/random_words 或 /rw 发送随机一言  
/weather 城市名 或 /w 城市名 发送天气  
……  
/help 或 /h 查看帮助___


群聊使用/chat命令或@机器人即可聊天，私聊默认处理所有非命令消息为聊天  

_大模型推荐使用硅基流动的，免费赠送15元_