"""
Plot Graph Manager

故事图谱管理器，负责节点/选择/边的 CRUD、
JSON 持久化存储、Mermaid 可视化导出。
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from nbot.plot.models import PlotChoice, PlotEdge, PlotNode

_log = logging.getLogger(__name__)

_plot_graph_manager = None


class PlotGraphManager:
    """故事图谱管理器"""

    def __init__(self, data_dir: str = "data/web"):
        self._graphs_file = os.path.join(data_dir, "plot_graphs.json")
        self._nodes: Dict[str, PlotNode] = {}
        self._choices: Dict[str, PlotChoice] = {}
        self._edges: Dict[str, PlotEdge] = {}
        self._active: Dict[str, str] = {}  # conversation_id -> 当前激活节点
        self._load()

    # -- Node CRUD --

    def add_node(self, node: PlotNode) -> PlotNode:
        """添加故事节点并持久化。"""
        self._nodes[node.id] = node
        self._save()
        _log.info(
            "[PlotGraphManager] added node id=%s title=%s level=%s",
            node.id, node.title, node.level,
        )
        return node

    def set_node_messages(
        self,
        node_id: str,
        user_message: Optional[Dict[str, Any]] = None,
        assistant_message: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """为节点写入消息快照（用于会话内分支物化）。"""
        node = self._nodes.get(node_id)
        if node is None:
            return False
        if user_message is not None:
            node.user_message = user_message
        if assistant_message is not None:
            node.assistant_message = assistant_message
        self._save()
        return True

    def get_node(self, node_id: str) -> Optional[PlotNode]:
        """获取单个节点。"""
        return self._nodes.get(node_id)

    def update_assistant_audio(
        self,
        message_id: str,
        audio_url: str,
        conversation_id: str = "",
    ) -> bool:
        """把 TTS 音频 URL 写入"该助手消息所属节点"的快照。

        分支切换/回溯时 materialize_path 会从节点快照重建消息，若快照不含
        audio_url，TTS 会丢失。此方法让快照成为音频的单一真相来源。

        匹配两种 id：
        1) 快照中存储的真实消息 id（assistant_message.id == message_id）
        2) 物化兜底 id：pm_a_<node_id>（历史节点切换后再生成 TTS 的情况）
        """
        if not message_id:
            return False
        target = None
        # 1) 按快照存储的真实消息 id 匹配
        for node in self._nodes.values():
            if conversation_id and node.conversation_id != conversation_id:
                continue
            am = node.assistant_message or {}
            if am.get("id") and str(am.get("id")) == str(message_id):
                target = node
                break
        # 2) 物化兜底 id：pm_a_<node_id>
        if target is None and message_id.startswith("pm_a_"):
            target = self._nodes.get(message_id[len("pm_a_"):])
        if target is None:
            return False
        am = dict(target.assistant_message or {})
        am["audio_url"] = audio_url or ""
        am.setdefault("role", "assistant")
        target.assistant_message = am
        self._save()
        _log.info(
            "[PlotGraphManager] updated assistant audio node=%s msg=%s",
            target.id, message_id,
        )
        return True

    # -- Choice CRUD --

    def add_choice(self, choice: PlotChoice) -> PlotChoice:
        """添加分支选择并持久化。"""
        self._choices[choice.id] = choice
        self._save()
        _log.info(
            "[PlotChoiceManager] added choice id=%s node_id=%s level=%s",
            choice.id, choice.node_id, choice.level,
        )
        return choice

    def get_choice(self, choice_id: str) -> Optional[PlotChoice]:
        """获取单个选择。"""
        return self._choices.get(choice_id)

    # -- Edge CRUD --

    def add_edge(self, edge: PlotEdge) -> PlotEdge:
        """添加故事边并持久化。"""
        self._edges[edge.id] = edge
        self._save()
        return edge

    # -- Selection --

    def select_choice(self, choice_id: str) -> bool:
        """标记选择为已选中，并创建对应的边。

        要求：该选择关联的节点必须存在，且选择尚未被选中。
        """
        choice = self._choices.get(choice_id)
        if choice is None:
            _log.warning("[PlotGraphManager] choice not found: %s", choice_id)
            return False

        if choice.selected:
            _log.warning("[PlotGraphManager] choice already selected: %s", choice_id)
            return False

        # 获取来源节点
        from_node = self._nodes.get(choice.node_id)
        if from_node is None:
            _log.warning(
                "[PlotGraphManager] source node not found: %s", choice.node_id,
            )
            return False

        # 标记选择为已选中
        choice.selected = True

        # 更新来源节点的 selected_choice_id
        from_node.selected_choice_id = choice.id

        self._save()
        _log.info(
            "[PlotGraphManager] selected choice %s on node %s",
            choice.id, choice.node_id,
        )

        # 剧情桥接：记忆 + 世界书
        self._bridge_to_memory(choice)
        self._bridge_to_world_book(choice)

        return True

    def create_edge_for_choice(
        self, choice_id: str, to_node_id: str, label: str = "",
    ) -> Optional[PlotEdge]:
        """为已选中的选择创建边。"""
        choice = self._choices.get(choice_id)
        if choice is None:
            return None

        edge = PlotEdge(
            from_node_id=choice.node_id,
            to_node_id=to_node_id,
            choice_id=choice_id,
            label=label or choice.text,
        )
        return self.add_edge(edge)

    # -- Graph Query --

    def get_graph(self, conversation_id: str) -> Dict[str, Any]:
        """获取指定会话的完整故事图谱。

        Returns:
            dict: {"nodes": [...], "choices": [...], "edges": [...]}
        """
        nodes = [
            n.to_dict()
            for n in self._nodes.values()
            if n.conversation_id == conversation_id
        ]
        node_ids = {n["id"] for n in nodes}

        choices = [
            c.to_dict()
            for c in self._choices.values()
            if c.node_id in node_ids
        ]
        choice_ids = {c["id"] for c in choices}

        edges = [
            e.to_dict()
            for e in self._edges.values()
            if e.from_node_id in node_ids or e.to_node_id in node_ids
        ]

        return {
            "nodes": nodes,
            "choices": choices,
            "edges": edges,
        }

    def get_latest_node(self, conversation_id: str) -> Optional[PlotNode]:
        """获取会话的最新故事节点。"""
        candidates = [
            n for n in self._nodes.values()
            if n.conversation_id == conversation_id
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda n: n.created_at, reverse=True)
        return candidates[0]

    def get_latest_choices(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取"当前位置"节点的未选择选项。

        以激活节点（当前会话所在分支末端）为准，而非全局最新节点，
        这样切换/回溯分支后，选项会随当前分支一起更新。
        """
        candidates = [
            n for n in self._nodes.values()
            if n.conversation_id == conversation_id
        ]
        if not candidates:
            return []

        # 优先用激活节点；其名下若全已选，再回退到按时间找最新未选节点
        active_id = self.get_active_node_id(conversation_id)
        active = self._nodes.get(active_id) if active_id else None
        if active is not None:
            unsel = [
                c.to_dict()
                for c in self._choices.values()
                if c.node_id == active.id and not c.selected
            ]
            if unsel:
                return unsel
            # 激活节点已无未选选项 -> 该位置不再展示历史其他分支的选项
            return []

        candidates.sort(key=lambda n: n.created_at, reverse=True)
        for node in candidates:
            if not node.selected_choice_id:
                return [
                    c.to_dict()
                    for c in self._choices.values()
                    if c.node_id == node.id and not c.selected
                ]
        return []

    # -- Mermaid Visualization --

    def generate_mermaid(self, conversation_id: str) -> str:
        """生成 Mermaid graph TD 语法的故事图谱。

        节点样式：
        - 普通节点: A["title"]
        - important: B["title"]:::important
        - turning_point: C["title"]:::turning_point
        - ending: D["title"]:::ending

        边标签为选择文本。
        """
        graph = self.get_graph(conversation_id)
        nodes = graph["nodes"]
        choices = graph["choices"]
        edges = graph["edges"]

        if not nodes:
            return "graph TD\n    empty[暂无剧情节点]"

        # 构建 node_id -> 短标识的映射
        node_id_map: Dict[str, str] = {}
        for idx, node in enumerate(nodes):
            short_id = chr(65 + idx) if idx < 26 else f"N{idx}"
            node_id_map[node["id"]] = short_id

        # 构建 choice_id -> choice 的映射
        choice_map: Dict[str, Dict[str, Any]] = {
            c["id"]: c for c in choices
        }

        lines = ["graph TD"]

        # 先定义所有节点（带标题和可选 class）
        for node in nodes:
            short_id = node_id_map[node["id"]]
            title = node["title"]
            level = node.get("level", "normal")
            suffix = f":::{level}" if level in ("important", "turning_point", "ending") else ""
            lines.append(f'    {short_id}["{title}"]{suffix}')

        # 渲染边
        rendered_edges: set = set()
        for edge in edges:
            from_id = edge["from_node_id"]
            to_id = edge["to_node_id"]
            edge_key = f"{from_id}->{to_id}"

            if edge_key in rendered_edges:
                continue
            rendered_edges.add(edge_key)

            from_short = node_id_map.get(from_id)
            to_short = node_id_map.get(to_id)
            if not from_short or not to_short:
                continue

            label = edge.get("label", "")
            if not label:
                choice = choice_map.get(edge["choice_id"], {})
                label = choice.get("text", "")

            if label:
                lines.append(f'    {from_short} -->|"{label}"| {to_short}')
            else:
                lines.append(f"    {from_short} --> {to_short}")

        # classDef 声明
        used_levels = {n.get("level", "normal") for n in nodes}
        level_styles = {
            "important": "fill:#ff9,stroke:#333,stroke-width:2px",
            "turning_point": "fill:#f9f,stroke:#333,stroke-width:2px",
            "ending": "fill:#9ff,stroke:#333,stroke-width:2px",
        }
        for level, style in level_styles.items():
            if level in used_levels:
                lines.append(f"    classDef {level} {style}")

        return "\n".join(lines)


    # -- Bridges --

    def _bridge_to_memory(self, choice: Any) -> None:
        """将选择写入记忆（非阻塞，失败不影响主流程）"""
        try:
            from nbot.plot.memory_bridge import PlotMemoryBridge
            # 从 choice 的 metadata 获取上下文
            meta = getattr(choice, 'metadata', {}) or {}
            conversation_id = meta.get('conversation_id', '')
            character_id = meta.get('character_id', '')
            user_id = meta.get('user_id', '')
            memory_service = meta.get('memory_service')
            if memory_service:
                PlotMemoryBridge.instance().on_choice_selected(
                    choice, conversation_id, character_id, user_id, memory_service,
                )
        except Exception as e:
            _log.debug("bridge to memory failed: %s", e)

    def _bridge_to_world_book(self, choice: Any) -> None:
        """转折点写入世界书（非阻塞）"""
        level = getattr(choice, 'level', 'normal')
        if level != 'turning_point':
            return
        try:
            from nbot.plot.world_book_bridge import PlotWorldBookBridge
            meta = getattr(choice, 'metadata', {}) or {}
            conversation_id = meta.get('conversation_id', '')
            character_id = meta.get('character_id', '')
            book_id = meta.get('world_book_id', '')
            world_book_store = meta.get('world_book_store')
            if world_book_store and book_id:
                PlotWorldBookBridge.instance().on_turning_point(
                    choice, conversation_id, character_id, book_id, world_book_store,
                )
        except Exception as e:
            _log.debug("bridge to world book failed: %s", e)

    # -- Branch & Timeline --

    def save_branch(self, conversation_id: str, branch_name: str) -> Optional[str]:
        """从当前节点创建分支快照，返回分支 ID"""
        graph = self.get_graph(conversation_id)
        nodes = graph.get("nodes", [])
        if not nodes:
            return None

        # 找到当前最新节点（最后创建的）
        latest = max(nodes, key=lambda n: n.get("created_at", ""))
        branch_id = f"br_{latest['id']}_{branch_name}"

        _log.info("branch saved: %s from node %s", branch_id, latest["id"])
        return branch_id

    def get_timeline(self, conversation_id: str) -> list[dict]:
        """按时间线返回路径节点（从根到当前）"""
        graph = self.get_graph(conversation_id)
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        choices = graph.get("choices", [])

        if not nodes:
            return []

        # 构建 parent -> child 映射
        child_map: dict[str, str] = {}
        for edge in edges:
            child_map[edge["from_node_id"]] = edge["to_node_id"]

        # 找根节点（没有被任何 edge 指向的）
        child_set = set(child_map.values())
        root_candidates = [n for n in nodes if n["id"] not in child_set]
        if not root_candidates:
            root_candidates = [nodes[0]]

        # 从根节点沿 selected_choice 路径走
        path = []
        current = root_candidates[0]
        visited = set()
        while current and current["id"] not in visited:
            visited.add(current["id"])
            path.append(current)
            # 找 selected_choice 对应的边
            sel_choice_id = current.get("selected_choice_id", "")
            if sel_choice_id:
                next_node_id = child_map.get(current["id"])
                if next_node_id:
                    current = next(
                        (n for n in nodes if n["id"] == next_node_id), None,
                    )
                else:
                    break
            else:
                break

        return path

    # -- In-session Branching (会话内分支) --

    def _build_parent_map(self, conversation_id: str):
        """返回 (nodes_by_id, parent_of, child_map)。

        父子关系：优先 edges / parent_node_id，孤儿按 created_at 串联，
        与前端 buildPlotChildMap 保持一致，保证单根连贯。
        """
        nodes = [
            n for n in self._nodes.values()
            if n.conversation_id == conversation_id
        ]
        nodes.sort(key=lambda n: n.created_at or "")
        by_id = {n.id: n for n in nodes}
        parent_of: Dict[str, str] = {}
        for n in nodes:
            if n.parent_node_id and n.parent_node_id in by_id:
                parent_of[n.id] = n.parent_node_id
        for e in self._edges.values():
            if e.from_node_id in by_id and e.to_node_id in by_id:
                parent_of.setdefault(e.to_node_id, e.from_node_id)
        prev = None
        for n in nodes:
            if n.id not in parent_of and prev is not None:
                parent_of[n.id] = prev.id
            prev = n
        child_map: Dict[str, list] = {}
        for child, parent in parent_of.items():
            child_map.setdefault(parent, []).append(child)
        return by_id, parent_of, child_map

    def get_active_node_id(self, conversation_id: str) -> str:
        """返回会话当前激活节点 id（单一真相来源）。

        若未显式设置，回退为最新创建的节点。
        """
        active = self._active.get(conversation_id, "")
        if active and active in self._nodes:
            return active
        latest = self.get_latest_node(conversation_id)
        return latest.id if latest else ""

    def set_active_node(self, conversation_id: str, node_id: str) -> bool:
        """设置会话当前激活节点并持久化。"""
        if node_id and node_id not in self._nodes:
            return False
        self._active[conversation_id] = node_id
        self._save()
        return True

    def get_children(self, conversation_id: str, node_id: str) -> List[PlotNode]:
        """返回某节点的直接子节点（按创建时间排序）。"""
        _, _, child_map = self._build_parent_map(conversation_id)
        children = [
            self._nodes[cid] for cid in child_map.get(node_id, [])
            if cid in self._nodes
        ]
        children.sort(key=lambda n: n.created_at or "")
        return children

    def path_to_node(self, conversation_id: str, node_id: str) -> List[PlotNode]:
        """返回从根到指定节点的节点路径（含该节点）。"""
        by_id, parent_of, _ = self._build_parent_map(conversation_id)
        if node_id not in by_id:
            return []
        path: List[PlotNode] = []
        cur = node_id
        guard = set()
        while cur and cur in by_id and cur not in guard:
            guard.add(cur)
            path.append(by_id[cur])
            cur = parent_of.get(cur, "")
        path.reverse()
        return path

    def materialize_path(
        self,
        conversation_id: str,
        node_id: str,
        system_prompt: str = "",
    ) -> List[Dict[str, Any]]:
        """物化从根到 node_id 的完整消息列表。

        缺少消息快照的历史节点用 title/summary 兜底，保证不报错。
        """
        path = self.path_to_node(conversation_id, node_id)
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for node in path:
            um = dict(node.user_message or {})
            am = dict(node.assistant_message or {})
            if um.get("content"):
                # 为物化消息赋稳定 id（基于节点），保证切换/回溯后编辑、
                # 重新生成、运行时时间线仍能正确引用。
                um.setdefault("id", f"pm_u_{node.id}")
                um.setdefault("role", "user")
                messages.append(um)
            if am.get("content"):
                am.setdefault("id", f"pm_a_{node.id}")
                am.setdefault("role", "assistant")
                messages.append(am)
            elif not node.assistant_message:
                # 历史节点兜底：用 summary/title 重建一条 assistant 消息
                fallback = node.summary or node.title or ""
                if fallback:
                    messages.append({
                        "role": "assistant",
                        "content": fallback,
                        "id": f"pm_a_{node.id}",
                    })
        return messages

    def branch_from(
        self,
        choice_id: str,
        new_node: PlotNode,
    ) -> Optional[PlotNode]:
        """从某选择创建一条新分支：

        允许同一父节点存在多个分支（每个已选 choice 一条边）。
        标记 choice 为已选、设置新节点父指针、建边。
        """
        choice = self._choices.get(choice_id)
        if choice is None:
            _log.warning("[PlotGraphManager] branch_from: choice not found %s", choice_id)
            return None
        parent_id = choice.node_id
        if parent_id not in self._nodes:
            _log.warning("[PlotGraphManager] branch_from: parent node missing %s", parent_id)
            return None
        new_node.parent_node_id = parent_id
        self._nodes[new_node.id] = new_node
        choice.selected = True
        # 不覆盖父节点已有的 selected_choice_id（保留首选主线语义）
        if not self._nodes[parent_id].selected_choice_id:
            self._nodes[parent_id].selected_choice_id = choice.id
        edge = PlotEdge(
            from_node_id=parent_id,
            to_node_id=new_node.id,
            choice_id=choice_id,
            label=choice.text,
        )
        self._edges[edge.id] = edge
        self._save()
        _log.info(
            "[PlotGraphManager] branched node %s from choice %s (parent %s)",
            new_node.id, choice_id, parent_id,
        )
        return new_node

    # -- Rollback --

    def rollback(self, node_id: str, conversation_id: str = "") -> bool:
        """回溯到指定节点：保留该节点，移除其所有后代节点、相关选择和边。

        回溯后该节点成为分支末端：清除其 selected_choice_id 并把它名下
        已选择的 choice 复位为未选，便于重新从此节点分支。
        不允许回溯不存在的节点。
        """
        if node_id not in self._nodes:
            _log.warning("[PlotGraphManager] rollback target not found: %s", node_id)
            return False

        # 收集要删除的后代节点（BFS，不含目标节点本身）
        to_remove: set = set()
        queue = [node_id]
        seen = {node_id}
        while queue:
            current_id = queue.pop(0)
            for edge in list(self._edges.values()):
                if edge.from_node_id == current_id:
                    child_id = edge.to_node_id
                    if child_id not in seen:
                        seen.add(child_id)
                        to_remove.add(child_id)
                        queue.append(child_id)

        # 删除：连接到被删后代的边、被删后代名下的选择；
        # 以及从目标节点出发指向被删后代的边。
        edges_to_remove = {
            eid for eid, e in self._edges.items()
            if e.from_node_id in to_remove or e.to_node_id in to_remove
        }
        choices_to_remove = {
            cid for cid, c in self._choices.items()
            if c.node_id in to_remove
        }

        for nid in to_remove:
            self._nodes.pop(nid, None)
        for eid in edges_to_remove:
            self._edges.pop(eid, None)
        for cid in choices_to_remove:
            self._choices.pop(cid, None)

        # 目标节点复位为分支末端
        target = self._nodes.get(node_id)
        if target:
            target.selected_choice_id = ""
        for c in self._choices.values():
            if c.node_id == node_id:
                c.selected = False

        # 激活节点指向回溯目标
        if conversation_id:
            self._active[conversation_id] = node_id

        self._save()
        _log.info(
            "[PlotGraphManager] rollback to node=%s, removed %d descendants, "
            "%d edges, %d choices",
            node_id, len(to_remove), len(edges_to_remove),
            len(choices_to_remove),
        )
        return True

    # -- Persistence --

    def _save(self):
        """将图谱数据写入 JSON 文件。"""
        data = {
            "nodes": {nid: n.to_dict() for nid, n in self._nodes.items()},
            "choices": {cid: c.to_dict() for cid, c in self._choices.items()},
            "edges": {eid: e.to_dict() for eid, e in self._edges.items()},
            "active": dict(self._active),
        }
        try:
            os.makedirs(os.path.dirname(self._graphs_file), exist_ok=True)
            with open(self._graphs_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.error("[PlotGraphManager] save failed: %s", e)

    def _load(self):
        """从 JSON 文件加载图谱数据。"""
        if not os.path.exists(self._graphs_file):
            return

        try:
            with open(self._graphs_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for nid, ndata in data.get("nodes", {}).items():
                self._nodes[nid] = PlotNode.from_dict(ndata)
            for cid, cdata in data.get("choices", {}).items():
                self._choices[cid] = PlotChoice.from_dict(cdata)
            for eid, edata in data.get("edges", {}).items():
                self._edges[eid] = PlotEdge.from_dict(edata)
            active = data.get("active", {})
            if isinstance(active, dict):
                self._active = {str(k): str(v) for k, v in active.items()}

            _log.info(
                "[PlotGraphManager] loaded %d nodes, %d choices, %d edges",
                len(self._nodes), len(self._choices), len(self._edges),
            )
        except Exception as e:
            _log.error("[PlotGraphManager] load failed: %s", e)


def get_plot_graph_manager(data_dir: str = "data/web") -> PlotGraphManager:
    """获取 PlotGraphManager 单例。"""
    global _plot_graph_manager
    if _plot_graph_manager is None:
        _plot_graph_manager = PlotGraphManager(data_dir=data_dir)
    return _plot_graph_manager
