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

    def get_node(self, node_id: str) -> Optional[PlotNode]:
        """获取单个节点。"""
        return self._nodes.get(node_id)

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
        """获取最新节点中未选择的选项。

        只返回最新一个尚未做出选择的节点所关联的选项，
        避免把历史轮次中所有未选选项都暴露出来。
        """
        candidates = [
            n for n in self._nodes.values()
            if n.conversation_id == conversation_id
        ]
        if not candidates:
            return []
        candidates.sort(key=lambda n: n.created_at, reverse=True)

        # 找到最新的、尚未做出选择的节点
        for node in candidates:
            if not node.selected_choice_id:
                return [
                    c.to_dict()
                    for c in self._choices.values()
                    if c.node_id == node.id and not c.selected
                ]

        # 所有节点都已选择，返回空
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

    # -- Rollback --

    def rollback(self, node_id: str) -> bool:
        """回滚：移除指定节点及其所有后代节点、相关选择和边。

        不允许回滚不存在的节点。
        """
        if node_id not in self._nodes:
            _log.warning("[PlotGraphManager] rollback target not found: %s", node_id)
            return False

        # 收集要删除的节点（BFS 遍历后代）
        to_remove: set = {node_id}
        queue = [node_id]
        while queue:
            current_id = queue.pop(0)
            for edge in list(self._edges.values()):
                if edge.from_node_id == current_id:
                    child_id = edge.to_node_id
                    if child_id not in to_remove:
                        to_remove.add(child_id)
                        queue.append(child_id)

        # 收集要删除的边和选择
        edges_to_remove = {
            eid for eid, e in self._edges.items()
            if e.from_node_id in to_remove or e.to_node_id in to_remove
        }
        choices_to_remove = {
            cid for cid, c in self._choices.items()
            if c.node_id in to_remove
        }

        # 执行删除
        for nid in to_remove:
            del self._nodes[nid]
        for eid in edges_to_remove:
            del self._edges[eid]
        for cid in choices_to_remove:
            del self._choices[cid]

        self._save()
        _log.info(
            "[PlotGraphManager] rollback node=%s, removed %d nodes, "
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
