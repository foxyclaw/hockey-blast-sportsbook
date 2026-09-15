"""Human merges are destructive and irreversible (merge_humans rewrites
human_id across ~40 tables in the shared hockey_blast database and deletes the
secondary human). Since 2026-09-15 the sportsbook never merges on its own —
not when a user confirms several player profiles, not when an admin approves a
claim. Merges are done deliberately by an operator against the primary
database (Render). Set HB_HUMAN_MERGES_ENABLED=1 only to restore the old
behaviour on purpose.
"""

import logging
import os

_log = logging.getLogger(__name__)


def human_merges_enabled() -> bool:
    return os.environ.get("HB_HUMAN_MERGES_ENABLED", "0") == "1"


def log_skipped_merge(context: str, user_id: int, human_ids) -> None:
    _log.warning(
        "human merge DISABLED (%s): user_id=%s holds confirmed claims on humans %s; "
        "not merging — an operator must review and merge by hand",
        context,
        user_id,
        sorted(human_ids),
    )
