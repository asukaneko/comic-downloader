"""
NekoBot 角色运行时引擎

提供独立的角色模拟层，包括：
- 角色卡数据模型 (CharacterProfile)
- 角色提示词编译器 (Compiler)
- 动态提示词栈 (PromptStack)
- 角色运行时 (CharacterRuntime)
- 状态机与反应规划 (StateMachine, ReactionPlanner)
- 角色记忆服务 (CharacterMemoryService)

本模块不依赖 Flask / Socket.IO / QQ，仅依赖统一请求对象和抽象存储接口。
"""
