"""
PredUserHbClaim — stores every hb_human_id a user has ever claimed as themselves.

Multiple rows allowed per user (different records across seasons/facilities).
Merging/deduplication is a nightly-job concern in hockey_blast, not here.
Two users can claim the same hb_human_id — we store both, flag for review later.

claim_status values:
    'confirmed'      — accepted (no conflict, or approved by admin)
    'pending_review' — conflict detected; awaiting admin review
    'rejected'       — admin rejected this claim
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import PredBase as Base


class PredUserHbClaim(Base):
    __tablename__ = "pred_user_hb_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    hb_human_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="self_reported"
    )  # 'self_reported' | 'email_match' | 'admin'
    is_primary: Mapped[bool] = mapped_column(default=False)
    # Snapshot of the human's profile at claim time — disaster recovery insurance.
    # If hockey_blast DB is rebuilt from scratch, IDs change but names/teams don't.
    # This snapshot lets us re-link by name even after a full DB rebuild.
    profile_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Admin review fields ──────────────────────────────────────────────────
    claim_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="confirmed"
    )  # 'confirmed' | 'pending_review' | 'rejected'
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pred_users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Merge tracking ───────────────────────────────────────────────────────
    # Set when this claim's hb_human_id has been merged into the primary human
    # on the hockey_blast side. NULL means the HB-side merge has not run yet.
    merged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Prevent exact duplicate claims (same user + same hb_human_id)
    __table_args__ = (
        UniqueConstraint("user_id", "hb_human_id", name="uq_user_hb_claim"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "hb_human_id": self.hb_human_id,
            "source": self.source,
            "is_primary": self.is_primary,
            "claim_status": self.claim_status,
            "admin_note": self.admin_note,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "claimed_at": self.claimed_at.isoformat() if self.claimed_at else None,
            "merged_at": self.merged_at.isoformat() if self.merged_at else None,
            "profile_snapshot": self.profile_snapshot,
        }
