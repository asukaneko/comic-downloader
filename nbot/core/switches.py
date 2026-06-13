import json


class SwitchManager:
    """Manage switch state for groups, users, and canonical conversations."""

    def __init__(self):
        self.group_switches = {}
        self.user_switches = {}
        self.conversation_switches = {}
        self.switch_configs = {}
        self._init_default_switches()

    def _init_default_switches(self):
        self.switch_configs = {}

    def add_switch(self, switch_name: str, default_value: bool = False, description: str = ""):
        self.switch_configs[switch_name] = {
            "default": default_value,
            "description": description,
        }
        self.save_switches()

    @staticmethod
    def _scope_from_conversation_id(conversation_id: str | None) -> tuple[str | None, str | None]:
        if not conversation_id:
            return None, None

        parts = conversation_id.split(":")
        if len(parts) < 3 or parts[0] != "qq":
            return None, None

        scope_type = parts[1]
        scope_id = parts[2]
        if scope_type == "group" and scope_id:
            return scope_id, None
        if scope_type == "private" and scope_id:
            return None, scope_id
        return None, None

    def get_switch_state(
        self,
        switch_name: str,
        group_id: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ):
        if switch_name not in self.switch_configs:
            raise ValueError(f"Unknown switch type: {switch_name}")

        if conversation_id and conversation_id in self.conversation_switches:
            if switch_name in self.conversation_switches[conversation_id]:
                return self.conversation_switches[conversation_id][switch_name]

        fallback_group_id, fallback_user_id = self._scope_from_conversation_id(conversation_id)
        group_id = group_id or fallback_group_id
        user_id = user_id or fallback_user_id

        if user_id and user_id in self.user_switches:
            if switch_name in self.user_switches[user_id]:
                return self.user_switches[user_id][switch_name]

        if group_id and group_id in self.group_switches:
            if switch_name in self.group_switches[group_id]:
                return self.group_switches[group_id][switch_name]

        return self.switch_configs[switch_name]["default"]

    def set_switch_state(
        self,
        switch_name: str,
        state: bool,
        group_id: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ):
        if switch_name not in self.switch_configs:
            raise ValueError(f"Unknown switch type: {switch_name}")

        if conversation_id:
            self.conversation_switches.setdefault(conversation_id, {})[switch_name] = state
        elif user_id:
            self.user_switches.setdefault(user_id, {})[switch_name] = state
        elif group_id:
            self.group_switches.setdefault(group_id, {})[switch_name] = state
        else:
            raise ValueError("conversation_id, group_id, or user_id is required")
        self.save_switches()

    def toggle_switch(
        self,
        switch_name: str,
        group_id: str | None = None,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ):
        current_state = self.get_switch_state(switch_name, group_id, user_id, conversation_id)
        new_state = not current_state
        self.set_switch_state(switch_name, new_state, group_id, user_id, conversation_id)
        self.save_switches()
        return new_state

    def get_switch_info(self, switch_name: str):
        if switch_name not in self.switch_configs:
            return None
        return self.switch_configs[switch_name]

    def list_all_switches(self):
        return list(self.switch_configs.keys())

    def save_switches(self, file_path: str = "switches.json"):
        data = {
            "group_switches": self.group_switches,
            "user_switches": self.user_switches,
            "conversation_switches": self.conversation_switches,
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_switches(self, file_path: str = "switches.json"):
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                self.group_switches = data.get("group_switches", {})
                self.user_switches = data.get("user_switches", {})
                self.conversation_switches = data.get("conversation_switches", {})
        except FileNotFoundError:
            pass
