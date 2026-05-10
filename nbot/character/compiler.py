"""
角色提示词编译器

将 CharacterProfile 编译为系统提示词。
从 personality.py 中的 compile_personality_prompt() 迁移而来，
同时支持新的 CharacterProfile 数据模型和旧 personality dict 格式。
"""

from typing import Any, Dict, Optional

from nbot.character.models import CharacterProfile, CharacterState, RelationshipState


def compile_profile_prompt(
    profile: CharacterProfile,
    state: Optional[CharacterState] = None,
    relationship: Optional[RelationshipState] = None,
    session_context: Optional[Dict[str, Any]] = None,
    user_name: Optional[str] = None,
) -> str:
    """将 CharacterProfile 编译成系统提示词

    Args:
        profile: 角色卡数据
        state: 角色运行时状态（可选，不传则使用 profile.initial_state）
        relationship: 关系状态（可选）
        session_context: 会话上下文信息（可选）
        user_name: 当前用户名，用于替换 {{user}} 模板变量

    Returns:
        编译后的系统提示词
    """
    prompt = ""

    name = profile.name
    basic_info = profile.basic_info
    personality = profile.personality
    scenario = profile.scenario
    response_format = profile.response_format
    rules = profile.rules
    example_dialogues = profile.example_dialogues

    # 角色设定部分
    if name:
        prompt += f"【角色名称】{name}\n"
    if basic_info:
        prompt += f"【基本信息】\n{basic_info}\n"
    if personality:
        prompt += f"【性格特点】{personality}\n"
    if scenario:
        prompt += f"【背景设定】{scenario}\n"
    if response_format:
        prompt += f"【回复格式】{response_format}\n"
    if rules and len(rules) > 0:
        prompt += "【行为规则】\n"
        for i, rule in enumerate(rules, 1):
            if rule:
                prompt += f"{i}. {rule}\n"
    if example_dialogues:
        prompt += f"【示例对话】\n{example_dialogues}\n"

    # 会话上下文
    if session_context:
        prompt += "\n【当前会话上下文】\n"
        if "session_name" in session_context:
            prompt += f"会话名称: {session_context['session_name']}\n"
        if "current_time" in session_context:
            prompt += f"当前时间: {session_context['current_time']}\n"
        if "user_info" in session_context:
            prompt += f"用户信息: {session_context['user_info']}\n"
        if "recent_messages" in session_context:
            prompt += "近期对话:\n"
            for msg in session_context["recent_messages"]:
                prompt += f"  {msg}\n"

    # 角色运行时状态（优先使用传入的 state，否则回退到 profile.initial_state）
    state_data = None
    if state:
        state_data = {
            "mood": state.mood,
            "mood_intensity": state.mood_intensity,
            "energy": state.energy,
        }
    if state_data:
        prompt += "\n【角色当前状态】\n"
        if "mood" in state_data:
            prompt += f"心情: {state_data['mood']}\n"
        if "mood_intensity" in state_data:
            prompt += f"情绪强度: {state_data['mood_intensity']}\n"
        if "energy" in state_data:
            prompt += f"精力: {state_data['energy']}\n"
        # 多维度关系状态（初始值）
        has_rel = any(k in state_data for k in ["affection", "trust", "familiarity", "dependency", "security"])
        if has_rel:
            prompt += "\n与用户的初始关系：\n"
            if "affection" in state_data:
                prompt += f"  好感: {state_data['affection']}/100\n"
            if "trust" in state_data:
                prompt += f"  信任: {state_data['trust']}/100\n"
            if "familiarity" in state_data:
                prompt += f"  熟悉: {state_data['familiarity']}/100\n"
            if "dependency" in state_data:
                prompt += f"  依赖: {state_data['dependency']}/100\n"
            if "security" in state_data:
                prompt += f"  安全感: {state_data['security']}/100\n"

    # 关系状态
    if relationship:
        prompt += "\n【与用户的关系】\n"
        prompt += f"好感: {relationship.affection}/100\n"
        prompt += f"信任: {relationship.trust}/100\n"
        prompt += f"熟悉: {relationship.familiarity}/100\n"
        prompt += f"依赖: {relationship.dependency}/100\n"
        prompt += f"安全感: {relationship.security}/100\n"
        if relationship.jealousy > 0:
            prompt += f"嫉妒: {relationship.jealousy}/100\n"

    if prompt:
        prompt = f'你是角色 "{name or "未命名"}"。\n\n' + prompt
    else:
        prompt = "请定义你的角色设定。"

    # 替换模板变量
    if user_name:
        prompt = prompt.replace("{{user}}", user_name)
    if name:
        prompt = prompt.replace("{{char}}", name)

    return prompt


def compile_personality_prompt(
    personality_data: Dict[str, Any],
    session_context: Optional[Dict[str, Any]] = None,
    user_name: Optional[str] = None,
) -> str:
    """兼容旧 personality dict 格式的编译入口

    保持与 personality.py 中原 compile_personality_prompt() 完全一致的签名和行为，
    内部转换为 CharacterProfile 后调用 compile_profile_prompt()。

    Args:
        personality_data: 旧格式的角色卡字典
        session_context: 会话上下文信息
        user_name: 当前用户名

    Returns:
        编译后的系统提示词
    """
    profile = CharacterProfile.from_personality_dict(personality_data)
    return compile_profile_prompt(
        profile,
        session_context=session_context,
        user_name=user_name,
    )
