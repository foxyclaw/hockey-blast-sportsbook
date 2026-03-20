"""
Fire-and-forget event tracker.

Usage (non-blocking, never raises):
    from app.services.event_tracker import track
    track("visit", user_id=g.pred_user.id if g.pred_user else None)

A background daemon thread drains the queue every 5s and writes to DB.
Zero impact on request latency.
"""
import logging
import queue
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_q: queue.Queue = queue.Queue(maxsize=10_000)
_started = False
_lock = threading.Lock()


def track(event_type: str, user_id: int | None = None, ip_address: str | None = None) -> None:
    """Enqueue an event. Never blocks, never raises."""
    try:
        _q.put_nowait({"event_type": event_type, "user_id": user_id, "ip_address": ip_address})
    except queue.Full:
        pass  # Drop silently — tracking is best-effort


def _drain(app) -> None:
    """Background thread: flush queue to DB every 5 seconds."""
    from app.db import PredSession
    from app.models.site_event import SiteEvent

    while True:
        try:
            batch = []
            try:
                while len(batch) < 500:
                    batch.append(_q.get_nowait())
            except queue.Empty:
                pass

            if batch:
                with app.app_context():
                    session = PredSession()
                    try:
                        now = datetime.now(timezone.utc)
                        session.bulk_insert_mappings(SiteEvent, [
                            {"event_type": e["event_type"], "user_id": e["user_id"], "ip_address": e.get("ip_address"), "created_at": now}
                            for e in batch
                        ])
                        session.commit()
                    except Exception as exc:
                        logger.warning("[tracker] DB flush failed: %s", exc)
                        session.rollback()
        except Exception:
            pass

        threading.Event().wait(5)  # sleep 5s


def start_tracker(app) -> None:
    """Start the background drain thread. Safe to call multiple times."""
    global _started
    with _lock:
        if _started:
            return
        t = threading.Thread(target=_drain, args=(app,), daemon=True, name="event-tracker")
        t.start()
        _started = True
        logger.info("[tracker] Event tracker started")
