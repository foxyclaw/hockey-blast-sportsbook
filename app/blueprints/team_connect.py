"""
Team Connect blueprint.

GET  /api/notifications               — user's notifications (last 20)
POST /api/notifications/<id>/read     — mark a notification as read
GET  /api/free-agents                 — list free agents / subs (public)
POST /api/sub-requests                — captain creates sub request
GET  /api/sub-requests                — list open sub requests
POST /api/sub-requests/<id>/respond   — respond to sub request
POST /api/sub-requests/<id>/confirm/<user_id> — captain confirms a sub
POST /api/sub-requests/<id>/cancel    — captain cancels request
POST /api/roster-invites              — captain invites a free agent
POST /api/roster-invites/<id>/respond — invitee accepts/declines
"""

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select, or_

from app.auth.jwt_validator import require_auth, optional_auth
from app.db import PredSession
from app.utils.response import error_response

team_connect_bp = Blueprint("team_connect", __name__)


# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────

@team_connect_bp.route("/api/notifications", methods=["GET"])
@require_auth
def get_notifications():
    """Return the current user's last 20 notifications."""
    from app.models.pred_notification import PredNotification

    session = PredSession()
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = (
        select(PredNotification)
        .where(
            PredNotification.user_id == g.pred_user.id,
            PredNotification.created_at >= cutoff,
        )
        .order_by(PredNotification.created_at.desc())
        .limit(20)
    )
    notifications = session.execute(stmt).scalars().all()
    return jsonify({
        "notifications": [n.to_dict() for n in notifications],
        "unread_count": sum(1 for n in notifications if not n.is_read),
    })


@team_connect_bp.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
@require_auth
def mark_notification_read(notif_id: int):
    """Mark a single notification as read."""
    from app.models.pred_notification import PredNotification

    session = PredSession()
    notif = session.execute(
        select(PredNotification).where(
            PredNotification.id == notif_id,
            PredNotification.user_id == g.pred_user.id,
        )
    ).scalar_one_or_none()

    if not notif:
        return error_response("NOT_FOUND", "Notification not found", 404)

    # Delete on read — notifications are nudges, not an inbox
    session.delete(notif)
    session.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# Free Agents
# ─────────────────────────────────────────────────────────────────────────────

@team_connect_bp.route("/api/free-agents", methods=["GET"])
@optional_auth
def list_free_agents():
    """
    Returns users who are free agents or willing to sub.
    Filters: location_id, level, sub_only (bool)
    """
    from app.models.pred_user_preferences import PredUserPreferences
    from app.models.pred_user import PredUser
    from app.models.pred_user_hb_claim import PredUserHbClaim

    pred_session = PredSession()
    sub_only = request.args.get("sub_only", "false").lower() == "true"
    location_id = request.args.get("location_id", type=int)
    level = request.args.get("level")

    stmt = (
        select(PredUser, PredUserPreferences)
        .join(PredUserPreferences, PredUserPreferences.user_id == PredUser.id)
        .where(PredUser.is_active == True)  # noqa: E712
    )
    if sub_only:
        stmt = stmt.where(PredUserPreferences.wants_to_sub == True)  # noqa: E712
    else:
        stmt = stmt.where(
            or_(
                PredUserPreferences.is_free_agent == True,  # noqa: E712
                PredUserPreferences.wants_to_sub == True,  # noqa: E712
            )
        )
    if level:
        stmt = stmt.where(PredUserPreferences.skill_level == level)

    rows = pred_session.execute(stmt).all()

    result = []
    for user, prefs in rows:
        # Filter by location if requested
        if location_id and location_id not in (prefs.interested_location_ids or []):
            continue

        # Get primary HB claim for stats
        claim = pred_session.execute(
            select(PredUserHbClaim).where(
                PredUserHbClaim.user_id == user.id,
                PredUserHbClaim.is_primary == True,  # noqa: E712
            )
        ).scalar_one_or_none()

        snapshot = claim.profile_snapshot if claim else {}

        entry = {
            "user_id": user.id,
            "display_name": user.display_name,
            "avatar_url": user.avatar_url,
            "skill_level": prefs.skill_level,
            "is_free_agent": prefs.is_free_agent,
            "wants_to_sub": prefs.wants_to_sub,
            "interested_location_ids": prefs.interested_location_ids or [],
            "hb_profile": {
                "orgs": snapshot.get("orgs", []),
                "first_date": snapshot.get("first_date"),
                "last_date": snapshot.get("last_date"),
                "skill_value": snapshot.get("skill_value"),
            } if snapshot else None,
        }
        result.append(entry)

    return jsonify({"free_agents": result, "total": len(result)})


# ─────────────────────────────────────────────────────────────────────────────
# Sub Requests
# ─────────────────────────────────────────────────────────────────────────────

@team_connect_bp.route("/api/sub-requests", methods=["POST"])
@require_auth
def create_sub_request():
    """Captain creates a sub request for a game."""
    from app.models.pred_sub_request import PredSubRequest
    from datetime import datetime

    data = request.get_json() or {}
    game_id = data.get("game_id")
    hb_team_id = data.get("hb_team_id")

    if not game_id or not hb_team_id:
        return error_response("INVALID_INPUT", "game_id and hb_team_id are required", 400)

    deadline = None
    if data.get("deadline"):
        try:
            deadline = datetime.fromisoformat(data["deadline"])
        except ValueError:
            return error_response("INVALID_INPUT", "Invalid deadline format", 400)

    session = PredSession()
    sub_req = PredSubRequest(
        game_id=int(game_id),
        hb_team_id=int(hb_team_id),
        captain_user_id=g.pred_user.id,
        goalies_needed=int(data.get("goalies_needed", 0)),
        skaters_needed=int(data.get("skaters_needed", 0)),
        message=data.get("message"),
        deadline=deadline,
        status="open",
    )
    session.add(sub_req)
    session.commit()
    session.refresh(sub_req)
    return jsonify({"sub_request": sub_req.to_dict()}), 201


@team_connect_bp.route("/api/sub-requests", methods=["GET"])
@optional_auth
def list_sub_requests():
    """List open sub requests."""
    from app.models.pred_sub_request import PredSubRequest

    session = PredSession()
    stmt = (
        select(PredSubRequest)
        .where(PredSubRequest.status == "open")
        .order_by(PredSubRequest.created_at.desc())
        .limit(50)
    )
    reqs = session.execute(stmt).scalars().all()
    return jsonify({"sub_requests": [r.to_dict() for r in reqs]})


@team_connect_bp.route("/api/sub-requests/<int:req_id>/respond", methods=["POST"])
@require_auth
def respond_to_sub_request(req_id: int):
    """A sub responds to a request (interested/declined)."""
    from app.models.pred_sub_request import PredSubRequest
    from app.models.pred_sub_response import PredSubResponse

    data = request.get_json() or {}
    status = data.get("status", "interested")
    if status not in ("interested", "declined"):
        return error_response("INVALID_INPUT", "status must be interested or declined", 400)

    session = PredSession()
    sub_req = session.execute(
        select(PredSubRequest).where(PredSubRequest.id == req_id)
    ).scalar_one_or_none()

    if not sub_req:
        return error_response("NOT_FOUND", "Sub request not found", 404)
    if sub_req.status != "open":
        return error_response("CONFLICT", "Sub request is not open", 409)

    # Upsert response
    existing = session.execute(
        select(PredSubResponse).where(
            PredSubResponse.request_id == req_id,
            PredSubResponse.user_id == g.pred_user.id,
        )
    ).scalar_one_or_none()

    if existing:
        existing.status = status
        resp = existing
    else:
        resp = PredSubResponse(
            request_id=req_id,
            user_id=g.pred_user.id,
            status=status,
        )
        session.add(resp)

    session.commit()
    session.refresh(resp)
    return jsonify({"response": resp.to_dict()})


@team_connect_bp.route("/api/sub-requests/<int:req_id>/confirm/<int:confirm_user_id>", methods=["POST"])
@require_auth
def confirm_sub(req_id: int, confirm_user_id: int):
    """Captain confirms a specific sub for the request."""
    from app.models.pred_sub_request import PredSubRequest
    from app.models.pred_sub_response import PredSubResponse

    session = PredSession()
    sub_req = session.execute(
        select(PredSubRequest).where(PredSubRequest.id == req_id)
    ).scalar_one_or_none()

    if not sub_req:
        return error_response("NOT_FOUND", "Sub request not found", 404)
    if sub_req.captain_user_id != g.pred_user.id:
        return error_response("FORBIDDEN", "Only the captain can confirm subs", 403)

    resp = session.execute(
        select(PredSubResponse).where(
            PredSubResponse.request_id == req_id,
            PredSubResponse.user_id == confirm_user_id,
        )
    ).scalar_one_or_none()

    if not resp:
        return error_response("NOT_FOUND", "Response not found", 404)

    resp.status = "confirmed"
    session.commit()
    return jsonify({"ok": True, "response": resp.to_dict()})


@team_connect_bp.route("/api/sub-requests/<int:req_id>/cancel", methods=["POST"])
@require_auth
def cancel_sub_request(req_id: int):
    """Captain cancels a sub request."""
    from app.models.pred_sub_request import PredSubRequest

    session = PredSession()
    sub_req = session.execute(
        select(PredSubRequest).where(PredSubRequest.id == req_id)
    ).scalar_one_or_none()

    if not sub_req:
        return error_response("NOT_FOUND", "Sub request not found", 404)
    if sub_req.captain_user_id != g.pred_user.id:
        return error_response("FORBIDDEN", "Only the captain can cancel this request", 403)

    sub_req.status = "cancelled"
    session.commit()
    return jsonify({"ok": True})


# ─────────────────────────────────────────────────────────────────────────────
# Roster Invites
# ─────────────────────────────────────────────────────────────────────────────

@team_connect_bp.route("/api/roster-invites", methods=["POST"])
@require_auth
def create_roster_invite():
    """Captain invites a free agent to their team."""
    from app.models.pred_roster_invite import PredRosterInvite
    from sqlalchemy.exc import IntegrityError

    data = request.get_json() or {}
    to_user_id = data.get("to_user_id")
    hb_team_id = data.get("hb_team_id")
    team_name = data.get("team_name", "")

    if not to_user_id or not hb_team_id or not team_name:
        return error_response("INVALID_INPUT", "to_user_id, hb_team_id, and team_name are required", 400)

    if int(to_user_id) == g.pred_user.id:
        return error_response("INVALID_INPUT", "Cannot invite yourself", 400)

    session = PredSession()
    invite = PredRosterInvite(
        from_user_id=g.pred_user.id,
        to_user_id=int(to_user_id),
        hb_team_id=int(hb_team_id),
        team_name=team_name,
        message=data.get("message"),
        status="pending",
    )
    session.add(invite)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return error_response("CONFLICT", "Invite already exists for this user/team", 409)

    session.refresh(invite)
    return jsonify({"invite": invite.to_dict()}), 201


@team_connect_bp.route("/api/roster-invites/<int:invite_id>/respond", methods=["POST"])
@require_auth
def respond_to_roster_invite(invite_id: int):
    """Invitee accepts or declines a roster invite."""
    from app.models.pred_roster_invite import PredRosterInvite

    data = request.get_json() or {}
    status = data.get("status")
    if status not in ("accepted", "declined"):
        return error_response("INVALID_INPUT", "status must be accepted or declined", 400)

    session = PredSession()
    invite = session.execute(
        select(PredRosterInvite).where(PredRosterInvite.id == invite_id)
    ).scalar_one_or_none()

    if not invite:
        return error_response("NOT_FOUND", "Invite not found", 404)
    if invite.to_user_id != g.pred_user.id:
        return error_response("FORBIDDEN", "This invite is not for you", 403)
    if invite.status != "pending":
        return error_response("CONFLICT", "Invite has already been responded to", 409)

    invite.status = status
    session.commit()
    return jsonify({"ok": True, "invite": invite.to_dict()})
