"""
nbot.world

WorldEngine — 群聊环境判定器与调度层。

职责：
  - 判断谁该说话（world_engine 策略）
  - 判断是否需要旁白
  - 判断剧情后果
  - 防止角色篡改世界设定
"""

from nbot.world.engine import WorldEngine, WorldEngineDecision, get_world_engine

__all__ = ["WorldEngine", "WorldEngineDecision", "get_world_engine"]
