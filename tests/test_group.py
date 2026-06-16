"""Group chat tests."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from nbot.channels.web import WebChannelAdapter
from nbot.core.ai_pipeline import PipelineContext, PipelineResult, _annotate_group_message_senders
from nbot.core.chat_models import ChatRequest
from nbot.group.cross_talk import collect_mentions_from_round, process_cross_talk
from nbot.group.manager import GroupManager
from nbot.group.models import GroupConfig, GroupConversation, InterCharacterRelation
from nbot.group.narrator import NarratorCharacter
from nbot.group.scheduler import SpeakerScheduler
from nbot.web.ai_service import trigger_ai_response_for_request


class TestGroupConfig:
    def test_defaults(self):
        cfg = GroupConfig()
        assert cfg.speaker_strategy == 'mention'
        assert cfg.max_chars_per_turn == 800
        assert cfg.auto_narrate is True

    def test_roundtrip(self):
        cfg = GroupConfig(speaker_strategy='round_robin', max_chars_per_turn=500)
        cfg2 = GroupConfig.from_dict(cfg.to_dict())
        assert cfg2.speaker_strategy == 'round_robin'


class TestInterCharacterRelation:
    def test_key_sorted(self):
        r = InterCharacterRelation(char_b='beta', char_a='alpha')
        assert r.relation_key == 'alpha::beta'

    def test_clamp(self):
        r = InterCharacterRelation(char_a='a', char_b='b')
        r.update('affection', 150)
        assert r.affection == 100.0
        r.update('affection', -200)
        assert r.affection == 0.0

    def test_history_limit(self):
        r = InterCharacterRelation(char_a='a', char_b='b')
        for i in range(60):
            r.update('trust', 1)
        assert len(r.to_dict()['history']) == 50


class TestGroupConversation:
    def test_auto_id(self):
        g = GroupConversation(name='test')
        assert g.group_id.startswith('gc_')

    def test_relations(self):
        g = GroupConversation(name='test')
        r = InterCharacterRelation(char_a='alice', char_b='bob', trust=50)
        g.set_relation(r)
        assert g.get_relation('bob', 'alice') is not None
        assert len(g.get_relation_matrix()) == 1

    def test_roundtrip(self):
        g = GroupConversation(name='t', character_ids=['a'], narrator_id='n')
        g.advance_turn()
        g2 = GroupConversation.from_dict(g.to_dict())
        assert g2.name == 't' and g2.turn_count == 1


class TestSpeakerScheduler:
    def test_round_robin(self):
        s = SpeakerScheduler()
        c = GroupConversation(name='t', character_ids=['a', 'b'])
        c.config.speaker_strategy = 'round_robin'
        assert s.decide_next_speaker(c, '', ['a', 'b']) == 'a'
        assert s.decide_next_speaker(c, '', ['a', 'b'], last_speaker='a') == 'b'

    def test_mention(self):
        s = SpeakerScheduler()
        c = GroupConversation(name='t', character_ids=['alice', 'bob'])
        assert s.decide_next_speaker(c, '@bob hi', ['alice', 'bob']) == 'bob'

    def test_random(self):
        s = SpeakerScheduler()
        c = GroupConversation(name='t', character_ids=['a', 'b', 'c', 'd'])
        c.config.speaker_strategy = 'random'
        results = {s.decide_next_speaker(c, '', ['a', 'b', 'c', 'd']) for _ in range(100)}
        assert len(results) > 1

    def test_empty(self):
        assert SpeakerScheduler().decide_next_speaker(GroupConversation(name='t'), '', []) == ''

    def test_prompt_build(self):
        s = SpeakerScheduler()
        c = GroupConversation(name='t', character_ids=['a'])
        profiles = {'a': {'name': 'Alice', 'description': 'brave'}}
        p = s.build_group_system_prompt(c, profiles, 'a')
        assert 'Alice' in p


class TestNarratorCharacter:
    def test_immediate_triggers(self):
        n = NarratorCharacter()
        n.enabled = True
        for t in ['scene_change', 'character_join', 'plot_node', 'manual']:
            assert n.should_narrate(t, 0) is True

    def test_disabled(self):
        n = NarratorCharacter()
        n.enabled = False
        assert n.should_narrate('scene_change', 0) is False

    def test_format(self):
        assert NarratorCharacter().format_narration('[旁白] test') == 'test'

    def test_scene_context(self):
        n = NarratorCharacter()
        ctx = n.build_scene_context(['A', 'B'], location='forest')
        assert 'forest' in ctx

    def test_recent_summary(self):
        n = NarratorCharacter()
        msgs = [{'role': 'alice', 'content': 'hello'}]
        summary = n.build_recent_summary(msgs)
        assert 'alice' in summary

    def test_recent_summary_empty(self):
        assert NarratorCharacter().build_recent_summary([]) == '暂无对话'


class TestGroupManager:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.fp = os.path.join(self.tmpdir, 'groups.json')
        self.mgr = GroupManager(file_path=self.fp)

    def test_crud(self):
        g = self.mgr.create_group('test', ['a', 'b'])
        assert g.name == 'test'
        assert self.mgr.get_group(g.group_id) is not None
        assert len(self.mgr.list_groups()) == 1
        self.mgr.update_group(g.group_id, name='new')
        assert self.mgr.get_group(g.group_id).name == 'new'
        assert self.mgr.delete_group(g.group_id) is True
        assert self.mgr.get_group(g.group_id) is None

    def test_characters(self):
        g = self.mgr.create_group('t', ['a'])
        self.mgr.add_character(g.group_id, 'b')
        assert 'b' in self.mgr.get_group(g.group_id).character_ids
        self.mgr.remove_character(g.group_id, 'a')
        assert 'a' not in self.mgr.get_group(g.group_id).character_ids

    def test_strategy(self):
        g = self.mgr.create_group('t', ['a'])
        assert self.mgr.set_speaker_strategy(g.group_id, 'round_robin') is True
        assert self.mgr.get_group(g.group_id).config.speaker_strategy == 'round_robin'
        assert self.mgr.set_speaker_strategy(g.group_id, 'bad') is False

    def test_bind(self):
        g = self.mgr.create_group('t', ['a'])
        self.mgr.bind_channel(g.group_id, 'qq:group:123')
        assert self.mgr.get_group_by_channel('qq:group:123') is not None
        self.mgr.unbind_channel('qq:group:123')
        assert self.mgr.get_group_by_channel('qq:group:123') is None

    def test_relation(self):
        g = self.mgr.create_group('t', ['a', 'b'])
        self.mgr.update_relation(g.group_id, 'a', 'b', 'trust', 10)
        r = self.mgr.get_group(g.group_id).get_relation('a', 'b')
        assert r.trust == 10.0

    def test_persistence(self):
        g = self.mgr.create_group('t', ['a'])
        mgr2 = GroupManager(file_path=self.fp)
        assert mgr2.get_group(g.group_id) is not None


class _ImmediateSocket:
    def start_background_task(self, target, *args, **kwargs):
        return target(*args, **kwargs)

    def emit(self, *_args, **_kwargs):
        return None

    def sleep(self, *_args, **_kwargs):
        return None


class _PipelineWebServer:
    def __init__(self):
        self.socketio = _ImmediateSocket()
        self.sessions = {
            "session-group": {
                "id": "session-group",
                "name": "Group Session",
                "group_id": "group-1",
                "messages": [],
            }
        }
        self.web_channel_adapter = WebChannelAdapter()
        self.stop_events = {}
        self.PROGRESS_CARD_AVAILABLE = False
        self.progress_card_manager = None
        self.ai_config = {"max_context_length": 100000, "supports_tools": False}
        self.active_model_id = None
        self.ai_models = []

    def _save_data(self, _name):
        return None

    def log_message(self, _level, _message):
        return None


def test_web_round_robin_group_runs_each_character_once(monkeypatch):
    server = _PipelineWebServer()
    group = GroupConversation(
        group_id="group-1",
        name="party",
        character_ids=["alice", "bob", "carol"],
        config=GroupConfig(speaker_strategy="round_robin", auto_narrate=False),
    )

    class FakeGroupManager:
        def get_group(self, group_id):
            return group if group_id == "group-1" else None

    monkeypatch.setattr(GroupManager, "_instance", FakeGroupManager())

    speakers = []

    def fake_process(self, ctx, callbacks, **kwargs):
        group_context = kwargs.get("group_context") or {}
        current_group = group_context.get("group")
        speakers.append(ctx.metadata.get("group_speaker") or current_group.active_speaker)
        return PipelineResult(
            final_content=f"reply from {speakers[-1]}",
            usage={},
            metadata=dict(ctx.metadata),
        )

    monkeypatch.setattr("nbot.web.ai_service.AIPipeline.process", fake_process)

    response = trigger_ai_response_for_request(
        server,
        ChatRequest.for_web("session-group", "hello", "tester"),
        adapter=server.web_channel_adapter,
    )

    assert response.error is None
    assert speakers == ["alice", "bob", "carol"]


def test_web_round_robin_speakers_see_previous_speaker_messages(monkeypatch):
    server = _PipelineWebServer()
    group = GroupConversation(
        group_id="group-1",
        name="party",
        character_ids=["alice", "bob", "carol"],
        config=GroupConfig(speaker_strategy="round_robin", auto_narrate=False),
    )
    server.sessions["session-group"]["messages"] = [
        {"role": "user", "content": "hello", "sender": "tester"}
    ]

    class FakeGroupManager:
        def get_group(self, group_id):
            return group if group_id == "group-1" else None

    monkeypatch.setattr(GroupManager, "_instance", FakeGroupManager())

    visible_assistant_senders = []

    def fake_process(self, ctx, callbacks, **kwargs):
        visible_assistant_senders.append([
            msg.get("sender")
            for msg in callbacks.load_messages(ctx)
            if msg.get("role") == "assistant"
        ])
        speaker = ctx.metadata.get("group_speaker")
        message = {
            "role": "assistant",
            "content": f"reply from {speaker}",
            "sender": speaker,
        }
        callbacks.save_assistant_message(ctx, message)
        return PipelineResult(
            final_content=message["content"],
            assistant_message=message,
            usage={},
            metadata=dict(ctx.metadata),
        )

    monkeypatch.setattr("nbot.web.ai_service.AIPipeline.process", fake_process)

    response = trigger_ai_response_for_request(
        server,
        ChatRequest.for_web("session-group", "hello", "tester"),
        adapter=server.web_channel_adapter,
    )

    assert response.error is None
    assert visible_assistant_senders == [
        [],
        ["alice"],
        ["alice", "bob"],
    ]


def test_group_history_includes_sender_names_for_model_context():
    messages = [
        {"role": "user", "content": "hello", "sender": "tester"},
        {"role": "assistant", "content": "hi", "sender": "alice"},
        {"role": "assistant", "content": "already", "sender": "AI"},
    ]

    annotated = _annotate_group_message_senders(messages)

    assert annotated[0]["content"] == "【tester】hello"
    assert annotated[1]["content"] == "【alice】hi"
    assert annotated[2]["content"] == "already"
    assert messages[1]["content"] == "hi"


# ============================================================================
# @mention 跨角色对话测试
# ============================================================================

_IDS = ["alice", "bob", "carol"]
_PROFILES = {
    "alice": {"name": "Alice"},
    "bob": {"name": "小明"},
    "carol": {"name": "Carol"},
}


class TestParseMentions:
    """SpeakerScheduler.parse_mentions 单元测试"""

    def test_basic_at_id(self):
        assert SpeakerScheduler.parse_mentions("你好 @bob", _IDS, _PROFILES) == ["bob"]

    def test_basic_at_name_cn(self):
        """中文角色名匹配"""
        assert SpeakerScheduler.parse_mentions("你好 @小明", _IDS, _PROFILES) == ["bob"]

    def test_multiple_mentions_order(self):
        """多个 @mention 保持出现顺序"""
        result = SpeakerScheduler.parse_mentions("@carol 先说，然后 @bob 和 @alice", _IDS, _PROFILES)
        assert result == ["carol", "bob", "alice"]

    def test_dedup(self):
        """重复 @mention 只返回一次"""
        assert SpeakerScheduler.parse_mentions("@alice @alice @alice", _IDS, _PROFILES) == ["alice"]

    def test_no_mentions(self):
        assert SpeakerScheduler.parse_mentions("没有at任何人", _IDS, _PROFILES) == []

    def test_unknown_mention(self):
        """@不存在的角色被忽略"""
        assert SpeakerScheduler.parse_mentions("@unknown 你好", _IDS, _PROFILES) == []

    def test_empty_text(self):
        assert SpeakerScheduler.parse_mentions("", _IDS, _PROFILES) == []

    def test_empty_ids(self):
        assert SpeakerScheduler.parse_mentions("@alice", [], _PROFILES) == []

    def test_none_text(self):
        assert SpeakerScheduler.parse_mentions(None, _IDS, _PROFILES) == []

    def test_case_insensitive_id(self):
        """大小写不敏感匹配 ID"""
        assert SpeakerScheduler.parse_mentions("@Alice 你好", _IDS, _PROFILES) == ["alice"]
        assert SpeakerScheduler.parse_mentions("@BOB 你好", _IDS, _PROFILES) == ["bob"]

    def test_mixed_id_and_name(self):
        """同时使用 ID 和中文名"""
        result = SpeakerScheduler.parse_mentions("@alice 和 @小明 你们好", _IDS, _PROFILES)
        assert result == ["alice", "bob"]

    def test_mention_in_sentence(self):
        """@mention 嵌在句子中间（有空格分隔）"""
        assert SpeakerScheduler.parse_mentions("我觉得 @alice 说得对", _IDS, _PROFILES) == ["alice"]

    def test_mention_embedded_in_chinese_no_space(self):
        """中文紧贴 @ 时不匹配（避免误判）"""
        assert SpeakerScheduler.parse_mentions("我觉得@alice说得对", _IDS, _PROFILES) == []

    def test_at_without_valid_match(self):
        """@ 后面跟的不是角色名"""
        assert SpeakerScheduler.parse_mentions("@hello world", _IDS, _PROFILES) == []

    def test_empty_profiles(self):
        """没有 profile 时只匹配 ID"""
        result = SpeakerScheduler.parse_mentions("@alice @小明", _IDS, {})
        assert result == ["alice"]  # 小明不在 profiles 中，无法匹配


class TestCollectMentionsFromRound:
    """collect_mentions_from_round 单元测试"""

    def test_basic(self):
        """alice 发言 @bob，bob 应被返回"""
        msgs = [{"role": "assistant", "content": "@Bob 你好", "sender": "Alice"}]
        assert collect_mentions_from_round(msgs, _IDS, _PROFILES) == ["bob"]

    def test_self_mention_filtered(self):
        """alice @自己，应被过滤"""
        msgs = [{"role": "assistant", "content": "@Alice 你觉得呢？", "sender": "Alice"}]
        assert collect_mentions_from_round(msgs, _IDS, _PROFILES) == []

    def test_self_mention_by_id_filtered(self):
        """sender 是 ID，@的是名字，也应被过滤"""
        msgs = [{"role": "assistant", "content": "@Alice 你好", "sender": "alice"}]
        assert collect_mentions_from_round(msgs, _IDS, _PROFILES) == []

    def test_multi_message_filter_spoken(self):
        """多条消息：alice 和 bob 都发言了，只有 carol 被 @ 且未发言"""
        msgs = [
            {"role": "assistant", "content": "@Bob 你好", "sender": "Alice"},
            {"role": "assistant", "content": "@Carol 你觉得呢？", "sender": "Bob"},
        ]
        # alice 和 bob 都已发言，carol 被 bob @ 但 carol 未发言
        # bob 被 alice @ 但 bob 已发言 → 过滤
        result = collect_mentions_from_round(msgs, _IDS, _PROFILES)
        assert result == ["carol"]

    def test_all_spoken(self):
        """所有被 @ 的角色都已发言"""
        msgs = [
            {"role": "assistant", "content": "@Bob 你好", "sender": "Alice"},
            {"role": "assistant", "content": "@Alice 你好", "sender": "Bob"},
        ]
        assert collect_mentions_from_round(msgs, _IDS, _PROFILES) == []

    def test_empty_content(self):
        """空内容被跳过"""
        msgs = [{"role": "assistant", "content": "", "sender": "Alice"}]
        assert collect_mentions_from_round(msgs, _IDS, _PROFILES) == []

    def test_no_mentions(self):
        """没有 @mention"""
        msgs = [{"role": "assistant", "content": "普通消息", "sender": "Alice"}]
        assert collect_mentions_from_round(msgs, _IDS, _PROFILES) == []

    def test_empty_responses(self):
        """空列表"""
        assert collect_mentions_from_round([], _IDS, _PROFILES) == []

    def test_dedup_across_messages(self):
        """多条消息都 @同一个角色，只返回一次"""
        msgs = [
            {"role": "assistant", "content": "@Carol 快来", "sender": "Alice"},
            {"role": "assistant", "content": "@Carol 你在吗", "sender": "Bob"},
        ]
        result = collect_mentions_from_round(msgs, _IDS, _PROFILES)
        assert result == ["carol"]

    def test_sender_with_chinese_name(self):
        """sender 是中文名"""
        msgs = [{"role": "assistant", "content": "@Carol 你好", "sender": "小明"}]
        result = collect_mentions_from_round(msgs, _IDS, _PROFILES)
        assert result == ["carol"]  # 小明 → bob，carol 未发言

    def test_unknown_sender(self):
        """sender 不在角色列表中（如用户消息）"""
        msgs = [{"role": "assistant", "content": "@Alice 你好", "sender": "user123"}]
        result = collect_mentions_from_round(msgs, _IDS, _PROFILES)
        assert result == ["alice"]  # user123 不是角色，alice 未发言


class TestProcessCrossTalk:
    """process_cross_talk 单元测试"""

    def _make_group(self):
        return GroupConversation(
            group_id="gc_test",
            name="test_group",
            character_ids=_IDS,
            config=GroupConfig(
                speaker_strategy="round_robin",
                auto_narrate=False,
                allow_character_cross_talk=True,
            ),
        )

    def _make_group_context(self, group):
        return {
            "group": group,
            "character_profiles": _PROFILES,
            "scheduler": SpeakerScheduler.instance(),
            "narrator": NarratorCharacter.instance(),
            "auto_narrate": False,
            "recent_messages": [],
        }

    def test_basic_cross_talk(self):
        """基本跨角色对话：@bob 触发 bob 回复"""
        group = self._make_group()
        gc = self._make_group_context(group)

        processed = []

        class FakePipeline:
            def process(self, ctx, callbacks, **kwargs):
                speaker = ctx.metadata.get("group_speaker", "")
                processed.append(speaker)
                # 验证 cross_talk_triggered 标记
                assert ctx.metadata.get("cross_talk_triggered") is True
                return PipelineResult(
                    final_content=f"reply from {speaker}",
                    assistant_message={"role": "assistant", "content": f"reply from {speaker}", "sender": speaker},
                    usage={},
                    metadata=dict(ctx.metadata),
                )

        results = process_cross_talk(
            ["bob"], 5,
            pipeline=FakePipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
        )

        assert processed == ["bob"]
        assert len(results) == 1
        assert results[0]["sender"] == "bob"

    def test_max_mentions_limit(self):
        """超过 max_mentions 的被截断"""
        group = self._make_group()
        gc = self._make_group_context(group)

        processed = []

        class FakePipeline:
            def process(self, ctx, callbacks, **kwargs):
                processed.append(ctx.metadata.get("group_speaker"))
                return PipelineResult(
                    final_content="ok",
                    usage={},
                    metadata=dict(ctx.metadata),
                )

        results = process_cross_talk(
            ["bob", "carol", "alice"], 2,  # max=2
            pipeline=FakePipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
        )

        assert len(processed) == 2
        assert len(results) == 2

    def test_empty_mentions(self):
        """空 mentions 列表直接返回"""
        results = process_cross_talk(
            [], 5,
            pipeline=None,
            callbacks=None,
            group_context={},
            base_metadata={},
            chat_request=None,
            adapter=None,
        )
        assert results == []

    def test_pipeline_exception_continues(self):
        """某个角色 pipeline 失败不影响后续角色"""
        group = self._make_group()
        gc = self._make_group_context(group)

        processed = []

        class FailOnBobPipeline:
            def process(self, ctx, callbacks, **kwargs):
                speaker = ctx.metadata.get("group_speaker")
                processed.append(speaker)
                if speaker == "bob":
                    raise RuntimeError("bob failed")
                return PipelineResult(
                    final_content=f"reply from {speaker}",
                    usage={},
                    metadata=dict(ctx.metadata),
                )

        results = process_cross_talk(
            ["bob", "carol"], 5,
            pipeline=FailOnBobPipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
        )

        assert processed == ["bob", "carol"]
        assert len(results) == 1  # bob 失败，carol 成功
        assert results[0]["sender"] == "Carol"  # 使用 profile name

    def test_cross_talk_triggered_flag_set(self):
        """验证 cross_talk_triggered 标记被正确设置"""
        group = self._make_group()
        gc = self._make_group_context(group)

        class CheckFlagPipeline:
            def process(self, ctx, callbacks, **kwargs):
                assert ctx.metadata["cross_talk_triggered"] is True
                assert ctx.metadata["group_speaker"] == "carol"
                return PipelineResult(final_content="ok", usage={}, metadata=dict(ctx.metadata))

        process_cross_talk(
            ["carol"], 5,
            pipeline=CheckFlagPipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={"some_key": "some_value"},
            chat_request=None,
            adapter=None,
        )

    def test_base_metadata_not_mutated(self):
        """base_metadata 不被修改（使用副本）"""
        group = self._make_group()
        gc = self._make_group_context(group)
        original_meta = {"key": "value"}

        class FakePipeline:
            def process(self, ctx, callbacks, **kwargs):
                return PipelineResult(final_content="ok", usage={}, metadata=dict(ctx.metadata))

        process_cross_talk(
            ["bob"], 5,
            pipeline=FakePipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata=dict(original_meta),
            chat_request=None,
            adapter=None,
        )

        assert original_meta == {"key": "value"}  # 未被修改

    def test_send_callback_called(self):
        """send_cross_talk_message 回调被调用"""
        group = self._make_group()
        gc = self._make_group_context(group)
        sent = []

        class FakePipeline:
            def process(self, ctx, callbacks, **kwargs):
                return PipelineResult(
                    final_content="hello",
                    assistant_message={"role": "assistant", "content": "hello", "sender": "bob"},
                    usage={},
                    metadata=dict(ctx.metadata),
                )

        process_cross_talk(
            ["bob"], 5,
            pipeline=FakePipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
            send_cross_talk_message=lambda msg: sent.append(msg),
        )

        assert len(sent) == 1
        assert sent[0]["sender"] == "bob"

    def test_send_callback_exception_does_not_break(self):
        """send 回调异常不影响后续处理"""
        group = self._make_group()
        gc = self._make_group_context(group)

        class FakePipeline:
            def process(self, ctx, callbacks, **kwargs):
                return PipelineResult(
                    final_content="ok",
                    assistant_message={"role": "assistant", "content": "ok", "sender": ctx.metadata.get("group_speaker")},
                    usage={},
                    metadata=dict(ctx.metadata),
                )

        def bad_send(msg):
            raise RuntimeError("send failed")

        results = process_cross_talk(
            ["bob", "carol"], 5,
            pipeline=FakePipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
            send_cross_talk_message=bad_send,
        )

        # 两个角色都应成功处理，send 异常被捕获
        assert len(results) == 2

    def test_empty_response_not_added(self):
        """空回复不加入结果"""
        group = self._make_group()
        gc = self._make_group_context(group)

        class EmptyPipeline:
            def process(self, ctx, callbacks, **kwargs):
                return PipelineResult(final_content="", usage={}, metadata=dict(ctx.metadata))

        results = process_cross_talk(
            ["bob"], 5,
            pipeline=EmptyPipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
        )

        assert results == []

    def test_none_response_not_added(self):
        """None 回复不加入结果"""
        group = self._make_group()
        gc = self._make_group_context(group)

        class NonePipeline:
            def process(self, ctx, callbacks, **kwargs):
                return PipelineResult(final_content=None, usage={}, metadata=dict(ctx.metadata))

        results = process_cross_talk(
            ["bob"], 5,
            pipeline=NonePipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
        )

        assert results == []

    def test_build_cross_talk_context_callback(self):
        """自定义 build_cross_talk_context 回调被使用"""
        group = self._make_group()
        gc = self._make_group_context(group)
        built = []

        def custom_builder(speaker_id):
            built.append(speaker_id)
            ctx = PipelineContext(
                chat_request=None,
                adapter=None,
                metadata={},
            )
            ctx.metadata["group_speaker"] = speaker_id
            ctx.metadata["group_speaker_name"] = speaker_id
            return ctx

        class FakePipeline:
            def process(self, ctx, callbacks, **kwargs):
                return PipelineResult(
                    final_content="ok",
                    usage={},
                    metadata=dict(ctx.metadata),
                )

        process_cross_talk(
            ["bob", "carol"], 5,
            pipeline=FakePipeline(),
            callbacks=None,
            group_context=gc,
            base_metadata={},
            chat_request=None,
            adapter=None,
            build_cross_talk_context=custom_builder,
        )

        assert built == ["bob", "carol"]


class TestGroupConfigCrossTalk:
    """GroupConfig 新字段测试"""

    def test_cross_talk_defaults(self):
        cfg = GroupConfig()
        assert cfg.cross_talk_max_mentions == 5
        assert cfg.round_robin_mode == "async"

    def test_cross_talk_roundtrip(self):
        cfg = GroupConfig(cross_talk_max_mentions=3, round_robin_mode="sequential")
        d = cfg.to_dict()
        assert d["cross_talk_max_mentions"] == 3
        assert d["round_robin_mode"] == "sequential"
        cfg2 = GroupConfig.from_dict(d)
        assert cfg2.cross_talk_max_mentions == 3
        assert cfg2.round_robin_mode == "sequential"

    def test_backward_compat(self):
        """旧数据没有新字段时使用默认值"""
        cfg = GroupConfig.from_dict({})
        assert cfg.cross_talk_max_mentions == 5
        assert cfg.round_robin_mode == "async"


class TestGroupPromptRules:
    """群聊提示词规则测试"""

    def test_mention_rules_in_prompt(self):
        """提示词包含 @mention 相关规则"""
        s = SpeakerScheduler()
        c = GroupConversation(name='t', character_ids=['a'])
        profiles = {'a': {'name': 'Alice'}}
        prompt = s.build_group_system_prompt(c, profiles, 'a')
        assert '@角色名' in prompt
        assert '严禁' in prompt or '代替其他角色' in prompt

    def test_strict_no_impersonate_rule(self):
        """提示词包含严禁代替其他角色发言的规则"""
        s = SpeakerScheduler()
        c = GroupConversation(name='t', character_ids=['a', 'b'])
        profiles = {'a': {'name': 'Alice'}, 'b': {'name': 'Bob'}}
        prompt = s.build_group_system_prompt(c, profiles, 'a')
        assert '严禁' in prompt
        assert '不能写出其他角色的台词' in prompt or '代替其他角色' in prompt
