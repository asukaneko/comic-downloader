import logging

from flask import jsonify, request

from nbot.plot.graph_manager import get_plot_graph_manager

_log = logging.getLogger(__name__)


def register_plot_routes(app, server):

    @app.route("/api/plot/toggle", methods=["POST"])
    def toggle_plot_mode():
        data = request.json or {}
        session_id = data.get("session_id", "")
        enabled = data.get("enabled", False)

        if not session_id:
            return jsonify({"error": "session_id is required"}), 400

        # Try to set plot_mode on the session
        sessions = getattr(server, "sessions", {})
        if session_id in sessions:
            sessions[session_id]["plot_mode"] = enabled
            try:
                server._save_data("sessions")
            except Exception:
                _log.debug("[PlotRoutes] failed to persist plot_mode", exc_info=True)

        _log.info(
            "[PlotRoutes] plot_mode toggled session=%s enabled=%s",
            session_id,
            enabled,
        )
        return jsonify({"session_id": session_id, "plot_mode": enabled})

    @app.route("/api/plot/<conversation_id>/graph")
    def get_plot_graph(conversation_id):
        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        graph = manager.get_graph(conversation_id)
        return jsonify(graph)

    @app.route("/api/plot/<conversation_id>/latest-choices")
    def get_latest_plot_choices(conversation_id):
        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        choices = manager.get_latest_choices(conversation_id)
        return jsonify({"choices": choices})

    @app.route("/api/plot/<conversation_id>/mermaid")
    def get_plot_mermaid(conversation_id):
        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        mermaid = manager.generate_mermaid(conversation_id)
        return jsonify({"mermaid": mermaid})

    @app.route("/api/plot/<conversation_id>/select", methods=["POST"])
    def select_plot_choice(conversation_id):
        data = request.json or {}
        choice_id = data.get("choice_id", "")

        if not choice_id:
            return jsonify({"error": "choice_id is required"}), 400

        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        success = manager.select_choice(choice_id)

        if not success:
            return jsonify({"error": "choice not found or already selected"}), 404

        _log.info(
            "[PlotRoutes] choice selected conversation=%s choice=%s",
            conversation_id,
            choice_id,
        )
        return jsonify({"success": True, "choice_id": choice_id})

    @app.route("/api/plot/<conversation_id>/rollback", methods=["POST"])
    def rollback_plot(conversation_id):
        data = request.json or {}
        node_id = data.get("node_id", "")

        if not node_id:
            return jsonify({"error": "node_id is required"}), 400

        data_dir = getattr(server, "data_dir", "data/web")
        manager = get_plot_graph_manager(data_dir=data_dir)
        success = manager.rollback(node_id)

        if not success:
            return jsonify({"error": "node not found"}), 404

        _log.info(
            "[PlotRoutes] rollback conversation=%s node=%s",
            conversation_id,
            node_id,
        )
        return jsonify({"success": True, "node_id": node_id})
