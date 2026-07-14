"""Player name formatting helpers."""


def format_player_name(first_name, middle_name=None, last_name=None) -> str:
    """
    Build a display name as "First Middle Last", skipping any empty parts.

    Including the middle name/initial disambiguates distinct people who share a
    first + last name (e.g. "Michael S Welch" vs "Michael J Welch"), matching how
    the stats side renders names.
    """
    parts = [p.strip() for p in (first_name, middle_name, last_name) if p and str(p).strip()]
    return " ".join(parts)
