"""
角色运行时引擎

CharacterRuntime 是角色模拟的编排中心，负责：
- before_turn: 读取角色卡/状态/关系/记忆，分析信号，生成 ReactionPlan，编译提示词
- after_turn: 更新情绪/关系，写入事件，抽取记忆

不直接处理 HTTP / Socket / QQ，仅依赖统一请求对象和抽象存储接口。
"""

import logging
from typing import Any, Dict, List, Optional

from nbot.character.models import (
    CharacterIdentity,
    CharacterMemory,
    CharacterProfile,
    CharacterState,
    CharacterTurnContext,
    ReactionPlan,
    RelationshipState,
)

_log = logging.getLogger(__name__)


class CharacterRuntime:
    """角色运行时引擎，编排角色模拟的完整生命周期"""

    def __init__(
        self,
        profile_repo=None,
        state_repo=None,
        relationship_repo=None,
        memory_service=None,
        signal_analyzer=None,
        planner=None,
        prompt_builder=None,
        state_machine=None,
    ):
        self.profile_repo = profile_repo
        self.state_repo = state_repo
        self.relationship_repo = relationship_repo
        self.memory_service = memory_service
        self.signal_analyzer = signal_analyzer
        self.planner = planner
        self.prompt_builder = prompt_builder
        self.state_machine = state_machine

    def before_turn(self, chat_request, identity: CharacterIdentity) -> CharacterTurnContext:
        """每轮对话前的角色模拟编排

        Args:
            chat_request: 统一聊天请求
            identity: 角色身份标识

        Returns:
            CharacterTurnContext 包含本轮所有角色上下文
        """
        # 读取角色卡
        profile = self._get_profile(identity)

        # 读取或创建角色运行时状态
        state = self._get_or_create_state(identity, profile)

        # 读取或创建关系状态
        relationship = self._get_or_create_relationship(identity)

        # 检索相关记忆
        memories = self._search_memories(identity, chat_request)

        # 分析用户输入信号
        signals = self._analyze_signals(chat_request, state, relationship)

        # 生成反应计划
        plan = self._plan_reaction(
            profile, state, relationship, memories, signals, chat_request
        )

        # 编译提示词
        prompt_text = self._build_prompt(
            profile, state, relationship, memories, plan
        )

        return CharacterTurnContext(
            profile=profile,
            state=state,
            relationship=relationship,
            memories=memories,
            signals=signals,
            plan=plan,
            prompt_text=prompt_text,
        )

    def after_turn(self, chat_request, result, turn_context: CharacterTurnContext) -> None:
        """每轮对话后的状态更新

        Args:
            chat_request: 统一聊天请求
            result: PipelineResult
            turn_context: before_turn 返回的上下文
        """
        if not self.state_machine:
            return

        # 应用状态变化
        new_state, new_relationship = self.state_machine.apply(
            old_state=turn_context.state,
            old_relationship=turn_context.relationship,
            signals=turn_context.signals,
            plan=turn_context.plan,
            user_message=getattr(chat_request, "content", ""),
            assistant_message=getattr(result, "final_content", ""),
        )

        # 保存状态
        if self.state_repo and new_state:
            self.state_repo.save(new_state)

        if self.relationship_repo and new_relationship:
            self.relationship_repo.save(new_relationship)

        # 记忆抽取（如果配置了记忆服务）
        if self.memory_service:
            try:
                self.memory_service.extract_and_save_if_needed(
                    chat_request=chat_request,
                    result=result,
                    turn_context=turn_context,
                )
            except Exception as exc:
                _log.warning("[CharacterRuntime] 记忆抽取异常: %s", exc)

    def _get_profile(self, identity: CharacterIdentity) -> CharacterProfile:
        """获取角色卡"""
        if self.profile_repo:
            profile = self.profile_repo.get(identity.character_id)
            if profile:
                return profile
        return CharacterProfile(name=identity.character_id)

    def _get_or_create_state(
        self, identity: CharacterIdentity, profile: CharacterProfile
    ) -> CharacterState:
        """获取或创建角色运行时状态"""
        if self.state_repo:
            state = self.state_repo.get_or_create(
                identity.character_id,
                identity.scope_id,
                initial_state=profile.initial_state,
            )
            if state:
                return state
        return CharacterState(
            character_id=identity.character_id,
            scope_id=identity.scope_id,
        )

    def _get_or_create_relationship(self, identity: CharacterIdentity) -> RelationshipState:
        """获取或创建关系状态"""
        if self.relationship_repo:
            rel = self.relationship_repo.get_or_create(
                identity.character_id,
                identity.target_id,
            )
            if rel:
                return rel
        return RelationshipState(
            character_id=identity.character_id,
            target_id=identity.target_id,
        )

    def _search_memories(
        self, identity: CharacterIdentity, chat_request
    ) -> List[CharacterMemory]:
        """检索相关记忆"""
        if not self.memory_service:
            return []
        try:
            return self.memory_service.search(
                character_id=identity.character_id,
                target_id=identity.target_id,
                query=getattr(chat_request, "content", ""),
                limit=8,
            )
        except Exception:
            return []

    def _analyze_signals(self, chat_request, state, relationship):
        """分析用户输入信号"""
        if not self.signal_analyzer:
            return None
        try:
            return self.signal_analyzer.analyze(
                getattr(chat_request, "content", ""),
                state=state,
                relationship=relationship,
            )
        except Exception:
            return None

    def _plan_reaction(
        self, profile, state, relationship, memories, signals, chat_request
    ) -> ReactionPlan:
        """生成反应计划"""
        if not self.planner:
            return ReactionPlan()
        try:
            return self.planner.plan(
                profile=profile,
                state=state,
                relationship=relationship,
                memories=memories,
                signals=signals,
                user_message=getattr(chat_request, "content", ""),
            )
        except Exception:
            return ReactionPlan()

    def _build_prompt(self, profile, state, relationship, memories, plan) -> str:
        """编译提示词"""
        from nbot.character.prompt_builder import build_character_injections
        from nbot.character.prompt_stack import PromptStack

        stack = PromptStack()

        # 将状态/关系/记忆/计划注册到 PromptStack
        build_character_injections(
            stack,
            profile=profile,
            state=state,
            relationship=relationship,
            memories=memories,
            plan=plan,
        )

        # 合成最终提示词
        return stack.render()
