# ranks.py
# Player ranks, as the game shows them (from GET /api/Leaderboards/rank-rules, 2026-10-26).
# The game sends each player's rank as a number at the start of a match (SetPlayerRank):
#    0-9 Bronze, 10-19 Silver, 20-29 Gold, 30-39 Diamond (stars = number - start), 40 Elite.
# Bots: their rank comes as the TEXT "0" (real players' ranks are numbers, even at Bronze 1).

RANKS = [            # (start number, name, colour for the overlay)
    (0, "Bronze", (190, 120, 80)),
    (10, "Silver", (190, 198, 205)),
    (20, "Gold", (215, 180, 70)),
    (30, "Diamond", (170, 130, 230)),
    (40, "Elite", (150, 220, 235)),
]
BOT_COLOUR = (235, 80, 95)


def is_bot(raw):
    """The rank exactly as the game sent it: the text "0" = a bot."""
    return isinstance(raw, str) and raw.strip() == "0"


def points(raw):
    """The rank as a number (None if unknown)."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def label(raw):
    """("Silver 4★", colour) / ("Elite", colour) / ("BOT", red) / (None, None) if unknown."""
    if is_bot(raw):
        return "BOT", BOT_COLOUR
    n = points(raw)
    if n is None:
        return None, None
    for start, name, colour in reversed(RANKS):
        if n >= start:
            return (name if name == "Elite" else f"{name} {n - start}★"), colour
    return None, None
