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
        world_book_store=None,
        hook_runtime=None,
    ):
        self.profile_repo = profile_repo
        self.state_repo = state_repo
        self.relationship_repo = relationship_repo
        self.memory_service = memory_service
        self.signal_analyzer = signal_analyzer
        self.planner = planner
        self.prompt_builder = prompt_builder
        self.state_machine = state_machine
        self._world_book_store = world_book_store
        self._hook_runtime = hook_runtime
        self._event_logger = None  # lazy init

    def _emit_hook(self, event_type: str, identity=None, payload=None, context=None):
        """Emit a hook event if hook_runtime is available. Non-blocking helper."""
        if not self._hook_runtime:
            return
        try:
            from nbot.hooks.models import RuntimeEvent
            event = RuntimeEvent(
                type=event_type,
                source="character_runtime",
                character_id=getattr(identity, "character_id", "") if identity else "",
                user_id=getattr(identity, "target_id", "") if identity else "",
                conversation_id=getattr(identity, "scope_id", "") if identity else "",
                payload=payload or {},
            )
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._hook_runtime.emit_event(event, context=context))
            else:
                loop.run_until_complete(self._hook_runtime.emit_event(event, context=context))
        except Exception as e:
            _log.debug("[CharacterRuntime] hook emit failed: %s", e)

    def before_turn(self, chat_request, identity: CharacterIdentity, recent_messages: list = None) -> CharacterTurnContext:
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
        relationship = self._get_or_create_relationship(identity, profile)

        _log.debug(
            "[CharacterRuntime] before_turn: character=%s target=%s "
            "profile.initial_state=%s state.mood=%s relationship=%s",
            identity.character_id,
            identity.target_id,
            profile.initial_state,
            state.mood if state else None,
            {
                "affection": relationship.affection if relationship else None,
                "trust": relationship.trust if relationship else None,
                "familiarity": relationship.familiarity if relationship else None,
                "dependency": relationship.dependency if relationship else None,
                "security": relationship.security if relationship else None,
            },
        )

        # 检索相关记忆
        memories = self._search_memories(identity, chat_request)
        self._emit_hook("character.after_memory_retrieve", identity, {
            "memory_count": len(memories),
        })

        # 分析用户输入信号
        signals = self._analyze_signals(chat_request, state, relationship)

        # 生成反应计划
        plan = self._plan_reaction(
            profile, state, relationship, memories, signals, chat_request
        )
        self._emit_hook("character.after_reaction_plan", identity, {
            "intent": plan.intent if plan else "",
            "tone": plan.tone if plan else "",
        })

        # 世界书关键词匹配（多源上下文召回）
        world_book_entries = self._match_world_books(identity, chat_request, state=state, recent_messages=recent_messages)
        self._emit_hook("character.after_world_book_match", identity, {
            "entry_count": len(world_book_entries) if world_book_entries else 0,
        })

        # 编译提示词
        prompt_text = self._build_prompt(
            profile, state, relationship, memories, plan,
            world_book_entries=world_book_entries,
        )

        self._emit_hook("character.before_turn.finished", identity, {
            "mood": state.mood if state else "",
            "affection": relationship.affection if relationship else 0,
            "trust": relationship.trust if relationship else 0,
        }, context={
            "mood": state.mood if state else "",
            "mood_intensity": state.mood_intensity if state else 0,
            "energy": state.energy if state else 0,
            "affection": relationship.affection if relationship else 0,
            "trust": relationship.trust if relationship else 0,
            "familiarity": relationship.familiarity if relationship else 0,
            "dependency": relationship.dependency if relationship else 0,
            "security": relationship.security if relationship else 0,
            "jealousy": relationship.jealousy if relationship else 0,
        })

        return CharacterTurnContext(
            profile=profile,
            state=state,
            relationship=relationship,
            memories=memories,
            signals=signals,
            plan=plan,
            prompt_text=prompt_text,
            world_book_entries=world_book_entries,
        )

    def after_turn(self, chat_request, result, turn_context: CharacterTurnContext) -> None:
        """每轮对话后的状态更新

        Args:
            chat_request: 统一聊天请求
            result: PipelineResult
            turn_context: before_turn 返回的上下文
        """
        if not self.state_machine:
            _log.warning("[CharacterRuntime] after_turn skipped: state_machine is None")
            return

        identity = CharacterIdentity(
            character_id=turn_context.profile.id if turn_context.profile else "",
            target_id=getattr(chat_request, "user_id", "") or "",
            scope_id=turn_context.state.scope_id if turn_context.state else "",
        )
        self._emit_hook("character.after_turn.started", identity)

        old_state = self._refresh_latest_state(turn_context.state)
        old_relationship = self._refresh_latest_relationship(turn_context.relationship)

        # 应用状态变化
        new_state, new_relationship = self.state_machine.apply(
            old_state=old_state,
            old_relationship=old_relationship,
            signals=turn_context.signals,
            plan=turn_context.plan,
            user_message=getattr(chat_request, "content", ""),
            assistant_message=getattr(result, "final_content", ""),
        )

        try:
            from nbot.character.auto_state import update_state_from_recent_turns

            new_state, new_relationship, auto_state_changed = update_state_from_recent_turns(
                profile=turn_context.profile,
                state=new_state,
                relationship=new_relationship,
                user_message=getattr(chat_request, "content", ""),
                assistant_message=getattr(result, "final_content", ""),
                metadata=getattr(chat_request, "metadata", {}) or {},
                conversation_id=getattr(chat_request, "conversation_id", "") or "",
                result_error=getattr(result, "error", None),
            )
            if auto_state_changed:
                _log.debug(
                    "[CharacterRuntime] auto state adjustment applied: mood=%s intensity=%s",
                    new_state.mood,
                    new_state.mood_intensity,
                )
        except Exception as exc:
            _log.warning("[CharacterRuntime] auto state adjustment failed: %s", exc, exc_info=True)

        _log.debug(
            "[CharacterRuntime] after_turn: old_rel=%s new_rel=%s state_repo=%s rel_repo=%s",
            {
                "affection": old_relationship.affection,
                "trust": old_relationship.trust,
                "familiarity": old_relationship.familiarity,
                "dependency": old_relationship.dependency,
                "security": old_relationship.security,
            },
            {
                "affection": new_relationship.affection,
                "trust": new_relationship.trust,
                "familiarity": new_relationship.familiarity,
                "dependency": new_relationship.dependency,
                "security": new_relationship.security,
            },
            self.state_repo is not None,
            self.relationship_repo is not None,
        )

        # 保存状态
        if self.state_repo and new_state:
            self.state_repo.save(new_state)

        if self.relationship_repo and new_relationship:
            self.relationship_repo.save(new_relationship)

        # Emit state/relationship change events
        if new_state and old_state:
            if new_state.mood != old_state.mood:
                self._emit_hook("state.changed", identity, {
                    "field": "mood", "old": old_state.mood, "new": new_state.mood,
                })
        if new_relationship and old_relationship:
            rel_changes = {}
            for field in ("affection", "trust", "familiarity", "dependency", "security", "jealousy"):
                old_val = getattr(old_relationship, field)
                new_val = getattr(new_relationship, field)
                if old_val != new_val:
                    rel_changes[field] = {"old": old_val, "new": new_val}
            if rel_changes:
                self._emit_hook("relationship.changed", identity, rel_changes)

        self._emit_hook("character.after_state_update", identity, {
            "mood": new_state.mood if new_state else "",
            "mood_intensity": new_state.mood_intensity if new_state else 0,
            "energy": new_state.energy if new_state else 0,
        }, context={
            "mood": new_state.mood if new_state else "",
            "mood_intensity": new_state.mood_intensity if new_state else 0,
            "energy": new_state.energy if new_state else 0,
            "affection": new_relationship.affection if new_relationship else 0,
            "trust": new_relationship.trust if new_relationship else 0,
            "familiarity": new_relationship.familiarity if new_relationship else 0,
            "dependency": new_relationship.dependency if new_relationship else 0,
            "security": new_relationship.security if new_relationship else 0,
            "jealousy": new_relationship.jealousy if new_relationship else 0,
        })

        # Web snapshot / timeline are written after after_turn from this context.
        # Keep them on the just-saved values instead of the before_turn baseline.
        if new_state:
            turn_context.state = new_state
        if new_relationship:
            turn_context.relationship = new_relationship

        # 记忆抽取（如果配置了记忆服务）
        if self.memory_service:
            try:
                self.memory_service.extract_and_save_if_needed(
                    chat_request=chat_request,
                    result=result,
                    turn_context=turn_context,
                )
                self._emit_hook("memory.after_extract", identity)
            except Exception as exc:
                _log.warning("[CharacterRuntime] 记忆抽取异常: %s", exc)

        self._emit_hook("character.after_turn.finished", identity, {
            "mood": new_state.mood if new_state else "",
            "affection": new_relationship.affection if new_relationship else 0,
        })

    def _refresh_latest_state(self, state: CharacterState) -> CharacterState:
        if not self.state_repo or not state:
            return state
        try:
            latest = self.state_repo.get(state.character_id, state.scope_id)
            return latest or state
        except Exception:
            return state

    def _refresh_latest_relationship(self, relationship: RelationshipState) -> RelationshipState:
        if not self.relationship_repo or not relationship:
            return relationship
        try:
            latest = self.relationship_repo.get(
                relationship.character_id,
                relationship.target_id,
            )
            return latest or relationship
        except Exception:
            return relationship

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

    def _get_or_create_relationship(self, identity: CharacterIdentity, profile: CharacterProfile) -> RelationshipState:
        """获取或创建关系状态"""
        if self.relationship_repo:
            rel = self.relationship_repo.get_or_create(
                identity.character_id,
                identity.target_id,
                initial_state=profile.initial_state,
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

    def _build_prompt(self, profile, state, relationship, memories, plan,
                      world_book_entries=None) -> str:
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

        # 注入世界书
        _log.debug("[WorldBook] _build_prompt: entries=%d", len(world_book_entries) if world_book_entries else 0)
        if world_book_entries:
            from nbot.character.world_book_injector import inject_world_book
            inject_world_book(stack, world_book_entries)

        # 合成最终提示词
        return stack.render()

    def _match_world_books(self, identity, chat_request, state=None, recent_messages: list = None) -> list:
        """匹配世界书关键词（多源上下文召回）"""
        if not self._world_book_store:
            _log.debug("[WorldBook] store is None, skipping")
            return []
        try:
            from nbot.character.world_book_matcher import (
                WorldBookRecallContext,
                match_entries_v2,
            )
            world_books = self._world_book_store.list_all()
            user_message = getattr(chat_request, "content", "")

            _log.debug(
                "[WorldBook] matching: books=%d char_id=%s msg=%r recent_msgs=%d scene=%s",
                len(world_books), identity.character_id,
                user_message[:60] if user_message else "",
                len(recent_messages) if recent_messages else 0,
                bool(state.scene) if state else False,
            )

            # 构建召回上下文
            scene = {}
            if state and hasattr(state, "scene"):
                scene = state.scene or {}

            recall_context = WorldBookRecallContext(
                latest_user_message=user_message,
                recent_messages=recent_messages or [],
                scene=scene,
                character_id=identity.character_id,
                target_id=getattr(identity, "target_id", ""),
                scope_id=getattr(identity, "scope_id", ""),
            )

            # V2 多源召回
            results = match_entries_v2(recall_context, world_books, identity.character_id)
            entries = [r.entry for r in results]

            _log.debug("[WorldBook] matched %d entries", len(entries))
            return entries
        except Exception as exc:
            _log.warning("[CharacterRuntime] world book match failed: %s", exc, exc_info=True)
            return []
