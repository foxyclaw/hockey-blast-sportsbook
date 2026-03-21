"""
Topic guard — fast pre-check before expensive tool calls.
One short Bedrock call, no tools. Returns is_hockey: bool.
"""
import os
import requests
import logging

logger = logging.getLogger(__name__)

BEARER = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL = os.getenv("BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-6")
BEDROCK_URL = f"https://bedrock-runtime.{REGION}.amazonaws.com/model/{MODEL}/invoke"

GUARD_PROMPT = """You are a topic classifier for a hockey statistics platform called Hockey Blast.
Users ask about players, teams, games, stats, scores, seasons, rinks, and leagues.

Answer YES if the question could plausibly be about:
- A person's name (they might be a hockey player)
- Hockey stats, scores, games, teams, seasons, rinks, leagues
- Anything sports or athlete related
- Short or ambiguous queries (single names, short phrases)

Answer NO ONLY if the question is CLEARLY about a completely unrelated topic like cooking recipes, political news, math homework, or non-sports entertainment.

When in doubt, answer YES.

Answer with ONLY the word YES or NO.

Question: {query}"""


def is_hockey_question(query: str) -> bool:
    """
    Returns True if the query is hockey-related, False otherwise.
    Uses a single fast Bedrock call with no tools.
    """
    if not BEARER:
        logger.warning("No Bedrock token configured, allowing all queries")
        return True

    try:
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 5,
            "messages": [{"role": "user", "content": GUARD_PROMPT.format(query=query)}],
        }
        resp = requests.post(
            BEDROCK_URL,
            headers={"Authorization": f"Bearer {BEARER}", "Content-Type": "application/json"},
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"].strip().upper()
        return text.startswith("YES")
    except Exception as e:
        logger.error(f"Topic guard failed: {e} — allowing query")
        return True  # Fail open: don't block on guard errors
