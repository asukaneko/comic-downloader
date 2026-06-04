from nbot.character.channel_context import ChannelRenderPolicy, ChannelRuntimeContext
from nbot.character.dispatcher import CharacterRuntimeContextDispatcher, build_scope_id


class FakeAdapter:
    channel_name = "qq"

    def build_runtime_context(self, chat_request):
        return ChannelRuntimeContext(
            channel="qq",
            conversation_id="qq:group:1000",
            scene="group",
            user_id="2000",
            group_id="1000",
        )

    def get_render_policy(self, context):
        return ChannelRenderPolicy()

    def select_character_id(self, context):
        return None

    def resolve_memory_scope(self, context):
        return "group_user"

    def render_result(self, result, context):
        return [{"type": "text", "content": result.text}]


def test_channel_enabled_false_overrides_global_true():
    dispatcher = CharacterRuntimeContextDispatcher(
        runtime=None,
        config={
            "character_runtime": {"default_enabled": True},
            "channels": {
                "qq": {"character_runtime": {"enabled": False}},
            },
        },
    )
    context = ChannelRuntimeContext(
        channel="qq",
        conversation_id="qq:group:1000",
        scene="group",
    )

    assert dispatcher.is_enabled(context) is False


def test_channel_enabled_true_overrides_global_false():
    dispatcher = CharacterRuntimeContextDispatcher(
        runtime=None,
        config={
            "character_runtime": {"default_enabled": False},
            "channels": {
                "qq": {"character_runtime": {"enabled": True}},
            },
        },
    )
    context = ChannelRuntimeContext(
        channel="qq",
        conversation_id="qq:group:1000",
        scene="group",
    )

    assert dispatcher.is_enabled(context) is True


def test_explicit_conversation_memory_scope_overrides_adapter_default():
    dispatcher = CharacterRuntimeContextDispatcher(
        runtime=None,
        config={
            "channels": {
                "qq": {"character_runtime": {"memory_scope": "conversation"}},
            },
        },
    )
    context = ChannelRuntimeContext(
        channel="qq",
        conversation_id="qq:group:1000",
        scene="group",
        user_id="2000",
        group_id="1000",
    )

    assert dispatcher.resolve_memory_scope(context, FakeAdapter()) == "conversation"


def test_configured_group_user_memory_scope_overrides_adapter_default():
    dispatcher = CharacterRuntimeContextDispatcher(
        runtime=None,
        config={
            "channels": {
                "qq": {"character_runtime": {"memory_scope": "group_user"}},
            },
        },
    )
    context = ChannelRuntimeContext(
        channel="qq",
        conversation_id="qq:group:1000",
        scene="group",
        user_id="2000",
        group_id="1000",
    )

    assert dispatcher.resolve_memory_scope(context, FakeAdapter()) == "group_user"


def test_build_scope_id_empty_conversation_uses_clean_unknown_value():
    context = ChannelRuntimeContext(channel="qq", conversation_id="", scene="private")

    assert build_scope_id(context, "conversation") == "qq:conversation:unknown_conversation"


def test_build_scope_id_group_user_empty_group_falls_back_to_conversation():
    context = ChannelRuntimeContext(
        channel="qq",
        conversation_id="qq:group:1000",
        scene="group",
        user_id="2000",
        group_id="",
    )

    assert build_scope_id(context, "group_user") == "qq:group:qq:group:1000:user:2000"