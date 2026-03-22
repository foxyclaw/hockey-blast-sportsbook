#!/usr/bin/env python3
"""
triage_feedback.py — LLM-powered feedback triage for chat_feedback table.

Fetches unprocessed 'dislike' feedback, uses Claude to classify each item,
creates GitHub issues for actionable bugs/features, and stamps processed rows.

Usage:
    # Dry run (default — shows what would happen, no issues filed):
    python scripts/triage_feedback.py

    # Actually file issues:
    python scripts/triage_feedback.py --execute

Env vars required:
    PRED_DATABASE_URL   — PostgreSQL connection string (already in .env)
    GITHUB_TOKEN        — GitHub PAT with repo scope (already in .env)
    ANTHROPIC_API_KEY   — Anthropic API key (NOT in .env yet — add it!)
                          Get one at: https://console.anthropic.com/settings/keys
                          Then add to .env: ANTHROPIC_API_KEY=sk-ant-...
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import anthropic
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

GITHUB_REPO = "foxyclaw/hockey-blast-sportsbook"
GITHUB_API  = "https://api.github.com"
LLM_MODEL   = "claude-3-haiku-20240307"

CHAT_FEEDBACK_LABEL = {
    "name": "chat-feedback",
    "color": "FF6B6B",
    "description": "Automatically triaged from user chat feedback",
}

TRIAGE_PROMPT = """\
You are triaging user feedback on an AI hockey stats assistant.

User asked: {query}

AI response: {response}

User's dislike comment: {comment}

Classify this feedback:
- "bug": Clear data error or wrong answer (high confidence issue)
- "feature": Missing capability or enhancement request
- "question": User confusion, not a real bug
- "not_actionable": Vague, spam, or unclear
- "needs_review": Ambiguous — could be a real issue but unclear

Respond with JSON only (no markdown fences):
{{"category": "bug|feature|question|not_actionable|needs_review", "confidence": "high|medium|low", "issue_title": "short title if actionable, else null", "issue_body": "detailed description for GitHub issue if actionable, else null", "reasoning": "one sentence"}}
"""

# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def github_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def ensure_label(token: str, repo: str, label: dict, dry_run: bool) -> None:
    """Create the chat-feedback label on the repo if it doesn't already exist."""
    headers = github_headers(token)
    url = f"{GITHUB_API}/repos/{repo}/labels"

    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    existing = {lbl["name"] for lbl in resp.json()}

    if label["name"] not in existing:
        if dry_run:
            print(f"[dry-run] Would create GitHub label: {label['name']}")
        else:
            create_resp = requests.post(url, headers=headers, json=label, timeout=10)
            if create_resp.status_code == 201:
                print(f"✓ Created GitHub label: {label['name']}")
            elif create_resp.status_code == 422:
                pass  # Already exists — race condition, fine
            else:
                create_resp.raise_for_status()
    else:
        print(f"  GitHub label '{label['name']}' already exists.")


def create_github_issue(
    token: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    dry_run: bool,
) -> str | None:
    """Create a GitHub issue. Returns the issue URL, or None in dry-run mode."""
    if dry_run:
        print(f"  [dry-run] Would create issue: {title}")
        print(f"  [dry-run] Labels: {labels}")
        return None

    headers = github_headers(token)
    url = f"{GITHUB_API}/repos/{repo}/issues"
    payload = {"title": title, "body": body, "labels": labels}

    resp = requests.post(url, headers=headers, json=payload, timeout=15)
    resp.raise_for_status()
    issue_url = resp.json()["html_url"]
    print(f"  ✓ Created issue: {issue_url}")
    return issue_url


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_connection(database_url: str):
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)


def ensure_columns(conn) -> None:
    """Add triage columns to chat_feedback if they don't exist (idempotent)."""
    ddl_statements = [
        "ALTER TABLE chat_feedback ADD COLUMN IF NOT EXISTS github_issue_url TEXT NULL",
        "ALTER TABLE chat_feedback ADD COLUMN IF NOT EXISTS triaged_at TIMESTAMP WITH TIME ZONE NULL",
        "ALTER TABLE chat_feedback ADD COLUMN IF NOT EXISTS triage_flag TEXT NULL",
    ]
    with conn.cursor() as cur:
        for ddl in ddl_statements:
            cur.execute(ddl)
    conn.commit()
    print("  DB columns verified (github_issue_url, triaged_at, triage_flag).")


def fetch_unprocessed_dislikes(conn) -> list[dict]:
    """Return dislike feedback rows not yet triaged, joined with chat_messages."""
    sql = """
        SELECT
            cf.id            AS feedback_id,
            cf.message_id,
            cf.user_id,
            cf.comment,
            cf.created_at    AS feedback_created_at,
            cm.query,
            cm.response
        FROM chat_feedback cf
        LEFT JOIN chat_messages cm ON cm.id = cf.message_id
        WHERE cf.rating = 'dislike'
          AND cf.triaged_at IS NULL
        ORDER BY cf.created_at ASC
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def stamp_feedback(
    conn,
    feedback_id: int,
    triage_flag: str,
    github_issue_url: str | None,
    dry_run: bool,
) -> None:
    """Update a feedback row with triage results."""
    if dry_run:
        return

    sql = """
        UPDATE chat_feedback
        SET
            triaged_at       = %s,
            triage_flag      = %s,
            github_issue_url = %s
        WHERE id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (datetime.now(timezone.utc), triage_flag, github_issue_url, feedback_id))
    conn.commit()


# ---------------------------------------------------------------------------
# LLM triage
# ---------------------------------------------------------------------------

def triage_with_llm(client: anthropic.Anthropic, row: dict) -> dict:
    """Call Claude Haiku to classify a single feedback item. Returns parsed JSON."""
    query    = row.get("query") or "(no query recorded)"
    response = row.get("response") or "(no response recorded)"
    comment  = row.get("comment") or "(no comment)"

    prompt = TRIAGE_PROMPT.format(
        query=query[:2000],       # guard against huge responses
        response=response[:2000],
        comment=comment[:500],
    )

    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown fences if Claude adds them anyway
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    return json.loads(raw)


def decide_action(triage: dict) -> str:
    """Return 'file_issue', 'needs_review', or 'not_actionable'."""
    category   = triage.get("category", "not_actionable")
    confidence = triage.get("confidence", "low")

    if category in ("bug", "feature") and confidence in ("high", "medium"):
        return "file_issue"
    elif category == "needs_review" or confidence == "low":
        return "needs_review"
    else:
        return "not_actionable"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Triage chat feedback using Claude LLM")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Preview what would happen without filing issues (default)",
    )
    mode_group.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help="Actually file GitHub issues and stamp the DB",
    )
    args = parser.parse_args()
    dry_run = args.dry_run

    # Load environment
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(env_path)

    database_url    = os.environ.get("PRED_DATABASE_URL")
    github_token    = os.environ.get("GITHUB_TOKEN")
    anthropic_key   = os.environ.get("ANTHROPIC_API_KEY")

    missing = []
    if not database_url:
        missing.append("PRED_DATABASE_URL")
    if not github_token:
        missing.append("GITHUB_TOKEN")
    if not anthropic_key:
        missing.append("ANTHROPIC_API_KEY  ← not in .env yet! Add: ANTHROPIC_API_KEY=sk-ant-...")

    if missing:
        print("ERROR: Missing required environment variables:")
        for m in missing:
            print(f"  • {m}")
        sys.exit(1)

    mode_label = "DRY RUN (pass --execute to file real issues)" if dry_run else "EXECUTE MODE"
    print(f"\n=== Feedback Triage [{mode_label}] ===\n")

    # Init clients
    anthropic_client = anthropic.Anthropic(api_key=anthropic_key)
    conn = get_connection(database_url)

    try:
        # 1. Ensure triage columns exist
        print("Checking DB schema...")
        ensure_columns(conn)

        # 2. Ensure chat-feedback label exists on GitHub
        print("Checking GitHub labels...")
        ensure_label(github_token, GITHUB_REPO, CHAT_FEEDBACK_LABEL, dry_run)

        # 3. Fetch unprocessed dislikes
        print("\nFetching unprocessed dislike feedback...")
        rows = fetch_unprocessed_dislikes(conn)
        print(f"  Found {len(rows)} unprocessed dislike(s).\n")

        if not rows:
            print("Nothing to triage. Done.")
            return

        # 4. Triage each item
        counts = {"issue_filed": 0, "needs_review": 0, "not_actionable": 0}

        for row in rows:
            feedback_id = row["feedback_id"]
            comment     = row.get("comment") or "(no comment)"
            print(f"--- Feedback #{feedback_id} ---")
            print(f"  Comment: {comment[:120]}")

            try:
                triage = triage_with_llm(anthropic_client, row)
            except (json.JSONDecodeError, Exception) as e:
                print(f"  ✗ LLM error: {e} — flagging as needs_review")
                triage = {"category": "needs_review", "confidence": "low", "reasoning": f"LLM error: {e}"}

            category   = triage.get("category", "?")
            confidence = triage.get("confidence", "?")
            reasoning  = triage.get("reasoning", "")
            print(f"  Category: {category} ({confidence} confidence)")
            print(f"  Reasoning: {reasoning}")

            action = decide_action(triage)
            issue_url = None

            if action == "file_issue":
                issue_title = triage.get("issue_title") or f"Chat feedback #{feedback_id}"
                issue_body  = triage.get("issue_body") or "(no details)"

                gh_title = f"[Chat Feedback] {issue_title}"
                gh_body  = (
                    f"{issue_body}\n\n"
                    f"---\n"
                    f"**Original query:** {row.get('query') or '(none)'}\n"
                    f"**User comment:** {comment}\n"
                    f"**Feedback ID:** {feedback_id}"
                )
                gh_labels = [
                    "bug" if category == "bug" else "enhancement",
                    "chat-feedback",
                ]

                issue_url = create_github_issue(
                    github_token, GITHUB_REPO, gh_title, gh_body, gh_labels, dry_run
                )
                triage_flag = "issue_filed"
                counts["issue_filed"] += 1

            elif action == "needs_review":
                print(f"  ⚠ Flagged for manual review.")
                triage_flag = "needs_review"
                counts["needs_review"] += 1

            else:
                print(f"  - Not actionable.")
                triage_flag = "not_actionable"
                counts["not_actionable"] += 1

            # 5. Stamp the row
            stamp_feedback(conn, feedback_id, triage_flag, issue_url, dry_run)
            print()

        # 6. Summary
        total = len(rows)
        print("=" * 40)
        print(f"Processed: {total} feedback item{'s' if total != 1 else ''}")
        print(f"  ✓ Issues filed:   {counts['issue_filed']}")
        print(f"  ⚠ Needs review:  {counts['needs_review']}")
        print(f"  - Not actionable: {counts['not_actionable']}")
        if dry_run:
            print("\n[dry-run] No issues were actually filed. Pass --execute to commit.")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
