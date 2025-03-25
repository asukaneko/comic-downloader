## 基于NapCat和jmcomic的本子下载和聊天的猫娘机器人

---
>环境为 <u>___windows___</u>  

一、安装依赖
```
pip install -r requirements.txt
```
二、更改配置
```
config.ini：修改账号、api等
option.yml: 修改下载目录、下载方式等
```
三、运行
```
python bot.py
```
会弹出下载napcat，然后扫码登录即可

>bot.py 中 设置了 ___命令注册装饰器___ ，可以自行添加命令