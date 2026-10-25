# profiles.py
# Player profiles: what a player usually runs, worked out from earlier matches
# (matches you played against them, and matches you spectated).
#
# Every finished match is kept as  games/<folder>/record.json  (the same data the
# website gets, see Game.website_record()). From those we answer:
#   "GPPoker on Rebel / Protector: in how many of those matches did he play each card?"
#
# IMPORTANT: this is NOT his decklist. We only ever see the cards a player PLAYS
# (about 10 of the 30 per match), so a card he always runs can still show 40-60%.
# Read the % as "how often he plays it", not "chance it's in his deck".

import json
from collections import Counter
from pathlib import Path


def class_key(classes):
    """["Rebel", "Protector"] -> "Protector / Rebel" (sorted, so the order doesn't matter)"""
    return " / ".join(sorted(classes or [])) or "?"


def appearances(record):
    """The players whose cards we saw in one saved match.
    My own matches: only the opponent. Spectated matches: both players.
    Each is {"name", "classes", "cards": {card_id: times}, "playedAt", "gameId"}."""
    if record.get("spectated"):
        players = record.get("players") or []
    else:
        players = [{"name": record.get("opponent"), "classes": record.get("opponentClasses"),
                    "cards": record.get("opponentCards") or {}}]
    for p in players:
        if p.get("name") and p.get("name") != "?":
            yield {"name": p["name"], "classes": p.get("classes") or [], "cards": p.get("cards") or {},
                   "playedAt": record.get("playedAt") or 0, "gameId": record.get("gameId")}


def predict(records, name, classes, exclude_game=None):
    """What this player played before with these classes.
    Returns None if we've never seen them with these classes, else
      {"matches": 5, "lastSeen": <ms>, "cards": [{"id", "seen": 4, "percent": 80, "most": 2}, ...]}
    seen = in how many of those matches they played it, most = most copies in one match.
    Generated cards are left out: they're not part of the deck."""
    if not name:
        return None
    key = class_key(classes)
    found = [a for r in records if r.get("gameId") != exclude_game for a in appearances(r)
             if a["name"].lower() == name.lower() and class_key(a["classes"]) == key]
    if not found:
        return None
    seen, most = Counter(), Counter()
    for a in found:
        for card_id, n in a["cards"].items():
            if n > 0:
                seen[card_id] += 1
                most[card_id] = max(most[card_id], n)
    cards = [{"id": c, "seen": k, "percent": round(100 * k / len(found)), "most": most[c]}
             for c, k in seen.items()]
    cards.sort(key=lambda c: (-c["seen"], c["id"]))
    return {"matches": len(found), "lastSeen": max(a["playedAt"] for a in found), "cards": cards}


def load_records(save_folder):
    """Every saved record.json in games/ (the tracker writes one when a match ends)."""
    records = []
    for path in sorted(Path(save_folder).glob("*/record.json")):
        if path.parent.name.startswith(("replay_", "test_")):
            continue
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    return records
