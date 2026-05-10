# -*- coding: utf-8 -*-
"""二维码生成 API - 基于 segno 轻量库"""

import base64
import io
import logging

from flask import Blueprint, jsonify, request

try:
    import segno
except ImportError:
    segno = None

_log = logging.getLogger(__name__)

qrcode_bp = Blueprint("qrcode", __name__, url_prefix="/api")


def register_qrcode_routes(app, server):
    """注册二维码路由到 Flask 应用"""
    app.register_blueprint(qrcode_bp)


@qrcode_bp.route("/qrcode/generate", methods=["POST"])
def generate_qrcode():
    """生成二维码并返回 base64 图片数据

    请求体:
        - data: 二维码内容（必填）
        - scale: 缩放比例，默认 10
        - dark: 深色颜色，默认 '#1a1a2e'
        - light: 浅色颜色，默认 '#f0f0f0'
        - kind: 输出格式，默认 'png'（支持 png/svg/eps）
        - border: 边框大小，默认 1

    响应:
        - success: bool
        - image: base64 编码的图片数据（data:image/png;base64,...）
        - error: 错误信息
    """
    if segno is None:
        return jsonify({"success": False, "error": "segno 库未安装，请执行 pip install segno"}), 503

    data = request.json or {}
    content = data.get("data", "").strip()

    if not content:
        return jsonify({"success": False, "error": "二维码内容不能为空"}), 400

    scale = max(1, min(40, int(data.get("scale", 10))))
    dark = data.get("dark", "#1a1a2e")
    light = data.get("light", "#f0f0f0")
    kind = data.get("kind", "png").lower()
    border = max(0, min(10, int(data.get("border", 1))))

    # 验证 kind
    if kind not in ("png", "svg", "eps"):
        kind = "png"

    try:
        qr = segno.make(content, error="h")

        if kind == "svg":
            out = io.StringIO()
            qr.save(out, kind="svg", scale=scale, dark=dark, light=light, border=border)
            svg_data = out.getvalue()
            out.close()
            b64 = base64.b64encode(svg_data.encode("utf-8")).decode("utf-8")
            return jsonify({
                "success": True,
                "image": f"data:image/svg+xml;base64,{b64}",
                "kind": "svg"
            })
        else:
            out = io.BytesIO()
            qr.save(out, kind=kind, scale=scale, dark=dark, light=light, border=border)
            img_data = out.getvalue()
            out.close()
            b64 = base64.b64encode(img_data).decode("utf-8")
            mime = "image/png" if kind == "png" else "application/postscript"
            return jsonify({
                "success": True,
                "image": f"data:{mime};base64,{b64}",
                "kind": kind
            })

    except Exception as e:
        _log.error("[QRCode] 生成失败: %s", e, exc_info=True)
        return jsonify({"success": False, "error": f"生成失败: {str(e)}"}), 500


@qrcode_bp.route("/qrcode/session/<session_id>", methods=["GET"])
def generate_session_qrcode(session_id):
    """为会话生成分享二维码

    自动生成包含会话链接的二维码
    """
    if segno is None:
        return jsonify({"success": False, "error": "segno 库未安装"}), 503

    if not session_id:
        return jsonify({"success": False, "error": "会话ID不能为空"}), 400

    try:
        # 构建会话分享链接
        host_url = request.headers.get("Origin", "")
        if not host_url:
            host_url = request.host_url.rstrip("/")
        share_url = f"{host_url}/chat?session={session_id}"

        qr = segno.make(share_url, error="h")
        out = io.BytesIO()
        qr.save(out, kind="png", scale=10, dark="#1a1a2e", light="#f0f0f0", border=1)
        img_data = out.getvalue()
        out.close()
        b64 = base64.b64encode(img_data).decode("utf-8")

        return jsonify({
            "success": True,
            "image": f"data:image/png;base64,{b64}",
            "url": share_url,
            "kind": "png"
        })

    except Exception as e:
        _log.error("[QRCode] 会话二维码生成失败: %s", e, exc_info=True)
        return jsonify({"success": False, "error": f"生成失败: {str(e)}"}), 500
