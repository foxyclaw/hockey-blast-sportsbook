"""
Odds service — computes pick odds from team skill differential.

Skill values: 0 = elite, 100 = worst (lower is better).
Vig: 10% house edge applied to both sides.

Usage:
    from app.services.odds_service import compute_odds
    odds = compute_odds(home_avg_skill=64, visitor_avg_skill=73)
    # returns {"home_odds": 1.69, "visitor_odds": 1.97, "home_prob": 0.54, "visitor_prob": 0.46}
"""

VIG = 0.10  # House edge
MIN_PROB = 0.20
MAX_PROB = 0.80
DEFAULT_ODDS = 1.90  # Used when no skill data available (close to even with vig)


def compute_odds(home_avg_skill: float | None, visitor_avg_skill: float | None) -> dict:
    """
    Returns odds for home and visitor teams.

    Logic:
    - P(home wins) = 0.5 + (visitor_skill - home_skill) / 200
    - Clipped to [MIN_PROB, MAX_PROB]
    - With vig: payout = 1 / (prob * (1 + VIG))
    - Rounded to 2 decimal places
    """
    if home_avg_skill is None or visitor_avg_skill is None:
        return {
            "home_odds": DEFAULT_ODDS,
            "visitor_odds": DEFAULT_ODDS,
            "home_prob": 0.5,
            "visitor_prob": 0.5,
            "has_skill_data": False,
        }

    raw_home_prob = 0.5 + (float(visitor_avg_skill) - float(home_avg_skill)) / 200.0
    home_prob = max(MIN_PROB, min(MAX_PROB, raw_home_prob))
    visitor_prob = 1.0 - home_prob

    home_odds = round(1.0 / (home_prob * (1 + VIG)), 2)
    visitor_odds = round(1.0 / (visitor_prob * (1 + VIG)), 2)

    return {
        "home_odds": home_odds,
        "visitor_odds": visitor_odds,
        "home_prob": round(home_prob, 3),
        "visitor_prob": round(visitor_prob, 3),
        "has_skill_data": True,
    }


def get_pick_odds(
    picked_team_id: int,
    home_team_id: int,
    home_avg_skill: float | None,
    visitor_avg_skill: float | None,
) -> float:
    """Return the odds for a specific picked team."""
    odds = compute_odds(home_avg_skill, visitor_avg_skill)
    if picked_team_id == home_team_id:
        return odds["home_odds"]
    return odds["visitor_odds"]
