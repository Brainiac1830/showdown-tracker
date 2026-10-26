# profiles.py
# Player profiles: what a player usually runs, worked out from earlier matches
# (matches you played against them, and matches you spectated).
#
# Every finished match is kept as  games/<folder>/record.json  (the same data the
# website gets, see Game.website_record()). Other players' trackers share what they
# saw too ("sightings", see website.py), downloaded into games/shared_sightings.json.
# From both together we answer:
#   "GPPoker on Rebel / Protector: in how many of those matches did he play each card?"
#
# IMPORTANT: this is NOT his decklist. We only ever see the cards a player PLAYS
# (about 10 of the 30 per match), so a card he always runs can still show 40-60%.
# Read the % as "how often he plays it", not "chance it's in his deck".

import json
from collections import Counter
from pathlib import Path

from cards import card_info, max_copies


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
                    "cards": record.get("opponentCards") or {},
                    "discarded": record.get("opponentDiscarded") or {}}]
    for p in players:
        # no name yet (left before the game showed it) = can't be used for anyone's profile
        if not p.get("name") or p.get("name") in ("?", "P1", "P2"):
            continue
        # unknown classes and almost nothing seen (left right away): not worth keeping
        if not p.get("classes") and sum((p.get("cards") or {}).values()) < 2:
            continue
        # every deck card SEEN from them: played + discarded (both are in their deck)
        seen = Counter(p.get("cards") or {}) + Counter(p.get("discarded") or {})
        yield {"name": p["name"], "classes": p.get("classes") or [], "cards": dict(seen),
               "playedAt": record.get("playedAt") or 0, "gameId": record.get("gameId"),
               "tournament": record.get("tournament") or ""}


def all_appearances(records, sightings=()):
    """My own matches + the shared sightings, each match counted once per player
    (I may have shared my own sighting too, or someone else watched the same match)."""
    found = {}
    for r in records:
        for a in appearances(r):
            found[(a["gameId"], a["name"].lower())] = a
    for s in sightings or ():
        key = (s.get("gameId"), (s.get("name") or "").lower())
        too_little = not s.get("classes") and sum((s.get("cards") or {}).values()) < 2
        if s.get("name") and key not in found and not too_little:
            found[key] = {"name": s["name"], "classes": s.get("classes") or [], "cards": s.get("cards") or {},
                          "playedAt": s.get("playedAt") or 0, "gameId": s.get("gameId"),
                          "tournament": s.get("tournament") or ""}
    return list(found.values())


def predict(records, name, classes, exclude_game=None, sightings=()):
    """What this player played before with these classes (my matches + shared sightings).
    Returns None if we've never seen them with these classes, else
      {"matches": 5, "lastSeen": <ms>, "cards": [{"id", "seen": 4, "percent": 80, "most": 2}, ...]}
    seen = in how many of those matches they played it, most = most copies in one match.
    Generated cards are left out: they're not part of the deck."""
    if not name:
        return None
    key = class_key(classes)
    found = [a for a in all_appearances(records, sightings) if a["gameId"] != exclude_game
             and a["name"].lower() == name.lower() and class_key(a["classes"]) == key]
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


# ---------- Tournaments: decks are locked, so every card seen is in the deck ----------

def tournament_key(name):
    """"Sunday  Cup " and "sunday cup" are the same tournament."""
    return " ".join((name or "").split()).lower()


def tournament_names(records, sightings=()):
    """Every tournament name seen (mine and shared), the most recent first."""
    newest = {}
    for a in all_appearances(records, sightings):
        key = tournament_key(a.get("tournament"))
        if key and (key not in newest or a["playedAt"] > newest[key][0]):
            newest[key] = (a["playedAt"], a["tournament"].strip())
    return [name for _, name in sorted(newest.values(), reverse=True)]


def tournament_deck(records, name, tournament, exclude_game=None, sightings=()):
    """The cards this player is KNOWN to have in their deck for this tournament:
    everything they played in that tournament (mine + shared), with the most
    copies seen in one match. Generated cards are not in "cards", so they never count.
    Returns None if they weren't seen in that tournament, else
      {"matches": 3, "classes": [...], "cards": {card_id: copies}, "known": 14, "lastSeen": ms}"""
    if not name or not tournament_key(tournament):
        return None
    found = [a for a in all_appearances(records, sightings)
             if a["gameId"] != exclude_game and a["name"].lower() == name.lower()
             and tournament_key(a.get("tournament")) == tournament_key(tournament)]
    if not found:
        return None
    cards = Counter()
    for a in found:
        for card_id, n in a["cards"].items():
            cards[card_id] = max(cards[card_id], n)
    for card_id in cards:              # never more copies than a deck can hold (Rare 1, Common 2)
        cards[card_id] = min(cards[card_id], max_copies(card_info(card_id)))
    newest = max(found, key=lambda a: a["playedAt"])
    return {"matches": len(found), "classes": newest["classes"], "cards": dict(cards),
            "known": sum(cards.values()), "lastSeen": newest["playedAt"]}


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


def load_shared(cache_file):
    """The shared sightings downloaded last time (works without internet)."""
    try:
        return list(json.loads(Path(cache_file).read_text(encoding="utf-8"))["sightings"].values())
    except (OSError, json.JSONDecodeError, KeyError):
        return []
