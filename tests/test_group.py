"""Group chat tests."""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from nbot.channels.web import WebChannelAdapter
from nbot.core.ai_pipeline import PipelineResult, _annotate_group_message_senders
from nbot.core.chat_models import ChatRequest
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
