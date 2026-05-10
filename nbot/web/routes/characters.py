"""
角色管理 API 路由

提供角色列表、详情、状态、关系、记忆、调试等接口。
保留旧 /api/personality 接口不变，新增 /api/characters 系列接口。
"""

import json
import logging
import os
from typing import Any, Dict

from flask import g, jsonify, request

_log = logging.getLogger(__name__)


def _get_character_runtime(server):
    """获取 CharacterRuntime 实例"""
    return getattr(server, "character_runtime", None)


def _get_base_dir(server):
    """获取项目根目录"""
    return getattr(server, "base_dir", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _get_profile_initial_state(server, character_id: str) -> Dict[str, Any]:
    from nbot.character.repository import ProfileRepository

    profile = ProfileRepository(_get_base_dir(server)).get(character_id)
    return profile.initial_state if profile else {}


def register_character_routes(app, server):
    """注册角色管理 API 路由"""

    # ================================================================
    # 角色列表 / 详情 / 创建 / 更新 / 删除
    # ================================================================

    @app.route("/api/characters", methods=["GET"])
    def list_characters():
        """列出所有角色卡"""
        from nbot.character.repository import ProfileRepository
        repo = ProfileRepository(_get_base_dir(server))
        profiles = repo.list_all()
        return jsonify([p.to_personality_dict() for p in profiles])

    @app.route("/api/characters/<character_id>", methods=["GET"])
    def get_character(character_id):
        """获取角色卡详情"""
        from nbot.character.repository import ProfileRepository
        repo = ProfileRepository(_get_base_dir(server))
        profile = repo.get(character_id)
        if not profile:
            return jsonify({"success": False, "error": "角色不存在"}), 404
        return jsonify(profile.to_personality_dict())

    @app.route("/api/characters", methods=["POST"])
    def create_character():
        """创建角色卡"""
        data = request.json or {}
        from nbot.character.models import CharacterProfile
        from nbot.character.repository import ProfileRepository
        from nbot.character.compiler import compile_profile_prompt

        profile = CharacterProfile.from_personality_dict(data)
        if not profile.id:
            import uuid
            profile.id = str(uuid.uuid4())

        profile.system_prompt = compile_profile_prompt(profile)

        repo = ProfileRepository(_get_base_dir(server))
        repo.save(profile)
        return jsonify({"success": True, "character": profile.to_personality_dict()})

    @app.route("/api/characters/<character_id>", methods=["PUT"])
    def update_character(character_id):
        """更新角色卡"""
        data = request.json or {}
        from nbot.character.models import CharacterProfile
        from nbot.character.repository import ProfileRepository
        from nbot.character.compiler import compile_profile_prompt

        repo = ProfileRepository(_get_base_dir(server))
        existing = repo.get(character_id)
        if not existing:
            return jsonify({"success": False, "error": "角色不存在"}), 404

        profile = CharacterProfile.from_personality_dict(data)
        profile.id = character_id
        profile.system_prompt = compile_profile_prompt(profile)

        repo.save(profile)
        return jsonify({"success": True, "character": profile.to_personality_dict()})

    @app.route("/api/characters/<character_id>", methods=["DELETE"])
    def delete_character(character_id):
        """删除角色卡"""
        from nbot.character.repository import ProfileRepository
        repo = ProfileRepository(_get_base_dir(server))
        if repo.delete(character_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "角色不存在"}), 404

    # ================================================================
    # 角色状态
    # ================================================================

    @app.route("/api/characters/<character_id>/state", methods=["GET"])
    def get_character_state(character_id):
        """获取角色运行时状态"""
        scope_id = request.args.get("scope_id", "")
        if not scope_id:
            return jsonify({"success": False, "error": "缺少 scope_id 参数"}), 400

        from nbot.character.repository import CharacterStateRepository
        repo = CharacterStateRepository(_get_base_dir(server))
        state = repo.get(character_id, scope_id)
        if not state:
            return jsonify({"success": False, "error": "状态不存在"}), 404
        return jsonify(state.to_dict())

    @app.route("/api/characters/<character_id>/state", methods=["PUT"])
    def update_character_state(character_id):
        """手动更新角色运行时状态"""
        scope_id = request.args.get("scope_id", "")
        if not scope_id:
            return jsonify({"success": False, "error": "缺少 scope_id 参数"}), 400

        data = request.json or {}
        from nbot.character.models import CharacterState
        from nbot.character.repository import CharacterStateRepository

        repo = CharacterStateRepository(_get_base_dir(server))
        state = repo.get(character_id, scope_id)
        if not state:
            state = CharacterState(character_id=character_id, scope_id=scope_id)

        # 更新字段
        if "mood" in data:
            state.mood = data["mood"]
        if "mood_intensity" in data:
            state.mood_intensity = float(data["mood_intensity"])
        if "energy" in data:
            state.energy = int(data["energy"])

        repo.save(state)
        return jsonify({"success": True, "state": state.to_dict()})

    # ================================================================
    # 关系状态
    # ================================================================

    @app.route("/api/characters/<character_id>/relationships", methods=["GET"])
    def get_character_relationship(character_id):
        """获取角色与用户的关系状态"""
        target_id = request.args.get("target_id", "")
        if not target_id:
            return jsonify({"success": False, "error": "缺少 target_id 参数"}), 400

        from nbot.character.repository import RelationshipRepository
        repo = RelationshipRepository(_get_base_dir(server))
        rel = repo.get_or_create(
            character_id,
            target_id,
            initial_state=_get_profile_initial_state(server, character_id),
        )
        if not rel:
            return jsonify({"success": False, "error": "关系不存在"}), 404
        return jsonify(rel.to_dict())

    @app.route("/api/characters/<character_id>/relationships", methods=["PUT"])
    def update_character_relationship(character_id):
        """手动更新关系状态"""
        target_id = request.args.get("target_id", "")
        if not target_id:
            return jsonify({"success": False, "error": "缺少 target_id 参数"}), 400

        data = request.json or {}
        from nbot.character.models import RelationshipState
        from nbot.character.repository import RelationshipRepository

        repo = RelationshipRepository(_get_base_dir(server))
        rel = repo.get_or_create(
            character_id,
            target_id,
            initial_state=_get_profile_initial_state(server, character_id),
        )

        # 更新字段
        for field_name in ["affection", "trust", "familiarity", "dependency", "security", "jealousy"]:
            if field_name in data:
                value = int(data[field_name])
                value = max(0, min(100, value))
                setattr(rel, field_name, value)

        repo.save(rel)
        return jsonify({"success": True, "relationship": rel.to_dict()})

    # ================================================================
    # 记忆管理
    # ================================================================

    @app.route("/api/characters/<character_id>/memories", methods=["GET"])
    def list_character_memories(character_id):
        """列出角色的记忆"""
        target_id = request.args.get("target_id", "")
        from nbot.character.memory import PromptManagerMemoryAdapter
        adapter = PromptManagerMemoryAdapter()
        memories = adapter.search(
            character_id=character_id,
            target_id=target_id,
            limit=50,
        )
        return jsonify([m.to_dict() for m in memories])

    @app.route("/api/characters/<character_id>/memories", methods=["POST"])
    def add_character_memory(character_id):
        """手动添加角色记忆"""
        data = request.json or {}
        target_id = data.get("target_id", "")
        title = data.get("title", "")
        content = data.get("content", "")
        mem_type = data.get("type", "long")

        if not title or not content:
            return jsonify({"success": False, "error": "标题和内容不能为空"}), 400

        from nbot.character.memory import PromptManagerMemoryAdapter
        adapter = PromptManagerMemoryAdapter()
        if adapter.save(character_id, target_id, title, content, mem_type=mem_type):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "保存失败"}), 500

    @app.route("/api/characters/<character_id>/memories/<memory_id>", methods=["DELETE"])
    def delete_character_memory(character_id, memory_id):
        """删除角色记忆"""
        from nbot.character.memory import PromptManagerMemoryAdapter
        adapter = PromptManagerMemoryAdapter()
        if adapter.delete(memory_id):
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "删除失败"}), 500

    # ================================================================
    # 调试接口
    # ================================================================

    @app.route("/api/characters/<character_id>/debug/latest-turn", methods=["GET"])
    def get_character_debug_latest(character_id):
        """获取最近一轮的调试快照"""
        scope_id = request.args.get("scope_id", "")
        if not scope_id:
            return jsonify({"success": False, "error": "缺少 scope_id 参数"}), 400

        from nbot.character.events import CharacterEventLogger
        logger = CharacterEventLogger(_get_base_dir(server))
        snapshot = logger.get_latest_debug_snapshot(scope_id)
        if not snapshot:
            return jsonify({"success": False, "error": "暂无调试数据"}), 404
        return jsonify({"success": True, "snapshot": snapshot})

    # ================================================================
    # 角色运行时初始化接口
    # ================================================================

    @app.route("/api/characters/runtime/initialize", methods=["POST"])
    def initialize_character_runtime():
        """初始化角色运行时引擎"""
        try:
            from nbot.character.runtime import CharacterRuntime
            from nbot.character.repository import (
                ProfileRepository,
                CharacterStateRepository,
                RelationshipRepository,
            )
            from nbot.character.memory import PromptManagerMemoryAdapter
            from nbot.character.policies import SignalAnalyzer
            from nbot.character.planner import ReactionPlanner
            from nbot.character.state_machine import StateMachine

            base_dir = _get_base_dir(server)

            runtime = CharacterRuntime(
                profile_repo=ProfileRepository(base_dir),
                state_repo=CharacterStateRepository(base_dir),
                relationship_repo=RelationshipRepository(base_dir),
                memory_service=PromptManagerMemoryAdapter(),
                signal_analyzer=SignalAnalyzer(),
                planner=ReactionPlanner(),
                state_machine=StateMachine(),
            )

            server.character_runtime = runtime
            _log.info("[CharacterRuntime] 角色运行时引擎已初始化")

            return jsonify({"success": True, "message": "角色运行时引擎已初始化"})
        except Exception as e:
            _log.error("[CharacterRuntime] 初始化失败: %s", e)
            return jsonify({"success": False, "error": str(e)}), 500

    @app.route("/api/characters/runtime/status", methods=["GET"])
    def get_character_runtime_status():
        """获取角色运行时状态"""
        runtime = _get_character_runtime(server)
        if not runtime:
            return jsonify({"initialized": False})

        return jsonify({
            "initialized": True,
            "has_profile_repo": runtime.profile_repo is not None,
            "has_state_repo": runtime.state_repo is not None,
            "has_relationship_repo": runtime.relationship_repo is not None,
            "has_memory_service": runtime.memory_service is not None,
            "has_signal_analyzer": runtime.signal_analyzer is not None,
            "has_planner": runtime.planner is not None,
            "has_state_machine": runtime.state_machine is not None,
        })
