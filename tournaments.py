# tournaments.py
# Automatic tournament detection, from the game's own tournament messages.
#
# When you open a tournament in the game, the page loads
#   GET /api/tournaments/public/<tournament id>
# The tracker saves it in games/tournaments/ (see tracker.py). It holds:
#   {"id", "name": "Daily Small Stakes ($10 GTD) BO3 #9", "status": "Started",
#    "deckType": "PerTournament",            <- decks are locked for the whole tournament
#    "participants": [{"userId", "username", ...}],
#    "stages": [{"bestOf": 3, "rounds": [{"matches": [
#        {"currentGameId": "<game id>", "p1": {"userId"}, "p2": {"userId"}, "status": "InProgress", ...}]}]}]}
#
# A match belongs to a tournament if:
#   1. its game id is a bracket match's currentGameId, or
#   2. its two players are the two players of an unfinished bracket match
#      (games 2 and 3 of a best-of-3 get new game ids; the bracket only shows the current one).
#
# (The participants also have "gameDeckJson", but the server leaves it empty while a
#  tournament is running, so decks still have to be scouted.)

import json
from pathlib import Path


class TournamentIndex:
    def __init__(self, folder=None):
        self.by_game = {}         # game id -> tournament info
        self.by_players = {}      # frozenset({"nous", "weedjones"}) -> tournament info
        self.tournaments = {}     # tournament id -> latest body (so an update replaces the old bracket)
        # Every game id ever seen in a bracket. The bracket only lists each match's CURRENT
        # game, so once a match moves on, its older game ids would be forgotten without this.
        self.known_file = Path(folder) / "known_games.json" if folder else None
        self.known = {}
        if self.known_file:
            try:
                self.known = json.loads(self.known_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self.known = {}
        if folder:
            for path in sorted(Path(folder).glob("tournaments_public_*.json")):
                try:
                    self.update(json.loads(path.read_text(encoding="utf-8")).get("body"))
                except (OSError, json.JSONDecodeError):
                    pass

    def update(self, body):
        """Read one tournament message (any game message is fine: only full brackets are used).
        Returns True if it was a tournament bracket."""
        if not isinstance(body, dict) or not body.get("stages") or not body.get("name"):
            return False
        self.tournaments[body.get("id") or body["name"]] = body
        self._rebuild()
        self.remember(self.by_game)
        return True

    def remember(self, games):
        """Add {game id: tournament info} to known_games.json (kept forever)."""
        new = {g: info for g, info in games.items() if self.known.get(g) != info}
        if not new:
            return
        self.known.update(new)
        if self.known_file:
            self.known_file.parent.mkdir(parents=True, exist_ok=True)
            self.known_file.write_text(json.dumps(self.known, indent=1), encoding="utf-8")

    def _rebuild(self):
        self.by_game, self.by_players = {}, {}
        for t in self.tournaments.values():
            info = {"id": t.get("id"), "name": " ".join(t["name"].split()), "status": t.get("status"),
                    "locked": t.get("deckType") == "PerTournament"}
            names = {p.get("userId"): (p.get("username") or "").lower() for p in t.get("participants") or []}
            for stage in t.get("stages") or []:
                for rnd in stage.get("rounds") or []:
                    for match in rnd.get("matches") or []:
                        if match.get("currentGameId"):
                            self.by_game[match["currentGameId"]] = info
                        players = frozenset(names.get((match.get(slot) or {}).get("userId")) for slot in ("p1", "p2"))
                        if match.get("completedAt") is None and len(players) == 2 and all(players) \
                                and t.get("status") != "Ended":
                            self.by_players[players] = info

    def lookup(self, game_id, player_names=()):
        """The tournament this match belongs to, or None.
        player_names: the two players' in-game names (if known yet)."""
        if game_id in self.by_game:
            return self.by_game[game_id]
        if game_id in self.known:
            return self.known[game_id]
        names = frozenset((n or "").lower() for n in player_names)
        if len(names) == 2 and all(names) and names in self.by_players:
            info = self.by_players[names]
            self.remember({game_id: info})       # e.g. game 2 of a best-of-3: remember it too
            return info
        return None
