"""
Chat blueprint — AI hockey stats chat with auth, topic guard, and abuse tracking.

Routes:
  POST /api/chat/message      — send a query, get an answer
  POST /api/chat/feedback/<id> — like/dislike an answer
  GET  /api/chat/history       — last N messages for current user
"""
import uuid
import logging
import os

from flask import Blueprint, g, jsonify, request
from app.auth.jwt_validator import require_auth, optional_auth
from app.constants import ANONYMOUS_USER_ID
from app.db import PredSession
from app.models.chat_message import ChatMessage
from app.models.chat_feedback import ChatFeedback
from app.services.chat_guard import is_hockey_question
from app.services.chat_violations import check_user_allowed, record_violation

logger = logging.getLogger(__name__)
chat_bp = Blueprint("chat", __name__)


@chat_bp.post("/api/chat/message")
@optional_auth
def send_message():
    """
    Process a chat query.
    1. Check if user is banned
    2. Topic guard — block off-topic questions
    3. Call hockey chat engine
    4. Log everything
    """
    data = request.get_json(silent=True) or {}
    query = (data.get("query") or "").strip()
    session_id = data.get("session_id") or str(uuid.uuid4())

    if not query:
        return jsonify({"error": "query is required"}), 400

    user_id = g.pred_user.id if g.pred_user else ANONYMOUS_USER_ID
    db = PredSession()

    from app.services.event_tracker import track
    track("chat", user_id=g.pred_user.id if g.pred_user else None, ip_address=request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip())

    # 1. Check if user is currently banned (admins are exempt)
    is_admin = g.pred_user and getattr(g.pred_user, 'is_admin', False)
    if not is_admin:
        status = check_user_allowed(user_id, db)
        if not status["allowed"]:
            return jsonify({"error": "CHAT_DISABLED", "message": status["message"]}), 403

    # 2. Topic guard (admins are exempt)
    if not is_admin and not is_hockey_question(query):
        violation = record_violation(user_id, query, db)
        # Log the off-topic attempt
        msg = ChatMessage(
            user_id=user_id,
            session_id=session_id,
            query=query,
            answer=violation["message"],
            tools_used=[],
            iterations=0,
            is_off_topic=True,
        )
        db.add(msg)
        db.commit()
        return jsonify({
            "message_id": msg.id,
            "answer": violation["message"],
            "is_off_topic": True,
            "tools_used": [],
        }), 200

    # 3. Run the hockey chat engine
    try:
        # Set DB env vars for MCP (common lib reads them at import time)
        _set_mcp_env()
        from hockey_blast_mcp.bedrock_chat import chat as hb_chat

        # Fetch last 10 non-off-topic messages for context, capped at ~8000 chars total
        recent = (
            db.query(ChatMessage)
            .filter_by(user_id=user_id, is_off_topic=False)
            .order_by(ChatMessage.created_at.desc())
            .limit(10)
            .all()
        )
        history = []
        char_budget = 8000
        for m in reversed(recent):
            turn_chars = len(m.query or "") + len(m.answer or "")
            if char_budget - turn_chars < 0:
                break
            history.append({"role": "user", "content": m.query})
            history.append({"role": "assistant", "content": m.answer})
            char_budget -= turn_chars

        result = hb_chat(query, history=history)
    except Exception as e:
        logger.error(f"Chat engine error: {e}", exc_info=True)
        return jsonify({"error": "Chat engine failed", "detail": str(e)}), 500

    # 4. Save the message
    msg = ChatMessage(
        user_id=user_id,
        session_id=session_id,
        query=query,
        answer=result["answer"],
        tools_used=result.get("tools_used", []),
        iterations=result.get("iterations", 0),
        is_off_topic=False,
    )
    db.add(msg)
    db.commit()

    return jsonify({
        "message_id": msg.id,
        "session_id": session_id,
        "answer": result["answer"],
        "tools_used": result.get("tools_used", []),
        "iterations": result.get("iterations", 0),
        "is_off_topic": False,
    })


@chat_bp.post("/api/chat/feedback/<int:message_id>")
@optional_auth
def submit_feedback(message_id: int):
    """Like or dislike a chat answer, with optional comment."""
    data = request.get_json(silent=True) or {}
    rating = data.get("rating", "").lower()
    comment = (data.get("comment") or "").strip() or None

    if rating not in ("like", "dislike"):
        return jsonify({"error": "rating must be 'like' or 'dislike'"}), 400

    user_id = g.pred_user.id if g.pred_user else ANONYMOUS_USER_ID
    db = PredSession()
    # Match message by id only (anonymous users share user_id=0 so don't filter by user)
    msg = db.query(ChatMessage).filter_by(id=message_id).first()
    if not msg:
        return jsonify({"error": "Message not found"}), 404

    # Upsert feedback
    existing = db.query(ChatFeedback).filter_by(
        message_id=message_id, user_id=user_id
    ).first()
    if existing:
        existing.rating = rating
        existing.comment = comment
    else:
        fb = ChatFeedback(
            message_id=message_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
        )
        db.add(fb)

    db.commit()
    return jsonify({"ok": True, "rating": rating})


@chat_bp.get("/api/chat/history")
@require_auth
def get_history():
    """Return last 50 chat messages for the current user."""
    db = PredSession()
    messages = (
        db.query(ChatMessage)
        .filter_by(user_id=g.pred_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify({"messages": [m.to_dict() for m in reversed(messages)]})


def _set_mcp_env():
    """Ensure MCP env vars are set before importing hockey_blast_mcp."""
    defaults = {
        "DB_HOST": "192.168.86.83",
        "DB_USER": "foxyclaw",
        "DB_PASSWORD": "foxyhockey2026",
        "DB_NAME": "hockey_blast",
        "DB_PORT": "5432",
        "AWS_REGION": "us-east-1",
        "BEDROCK_MODEL": "us.anthropic.claude-sonnet-4-6",
    }
    for k, v in defaults.items():
        os.environ.setdefault(k, v)
