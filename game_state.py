# game_state.py
# Turns the Showdown server messages into "what has happened in this match".
#
# How the game talks to the server (found by reading a saved browser log):
#   - The page keeps asking  POST /api/game/view-streams/<id>/catchup
#     "what happened after move number X?"
#   - The answer looks like:
#       {"snapshot": null,
#        "batches": [ {"moveIndex": 72, "eventData": "<a JSON list as text>", ...}, ... ],
#        "status":  {"gameId": "...", "moveIndex": 72, "status": {"result": 2, ...}},
#        "cursor": 72}
#   - "eventData" is a list of events like {"Type": "PlayCardAnim", ...}.
#     The most useful one is "AddGameLogItem": the game's own log entry
#     (card played, check, fold, stage changed...). Each has a "Sequence" number.
#   - Your own moves are sent with  POST /api/game/<gameId>/moves
#       {"move": {"type": "PlayCard", "cardNames": ["Silver Bullet"], "playerId": "P1"}}
#
# Players are called "P1" and "P2" in the messages. We work out which one is you.
#
# This file has no browser or window code, so it can be tested on its own
# (see "python tracker.py --replay" in the README).

import json
import time
from datetime import datetime
from collections import Counter

from cards import GENERATORS, card_info, max_copies


def server_time_ms(text):
    """'2026-10-25T02:21:48.4878032+00:00' -> milliseconds since 1970 (None if unreadable).
    Python only reads 6 digits after the dot, so the 7th is cut off."""
    try:
        if "." not in text:
            return int(datetime.fromisoformat(text).timestamp() * 1000)
        main, _, rest = text.partition(".")
        count = 0                       # how many digits come right after the dot
        while count < len(rest) and rest[count].isdigit():
            count += 1
        digits, zone = rest[:count][:6], rest[count:] or "+00:00"
        return int(datetime.fromisoformat(f"{main}.{digits or '0'}{zone}").timestamp() * 1000)
    except ValueError:
        return None


def other_player(pid):
    return "P2" if pid == "P1" else "P1"


class Game:
    """Everything we know about one match.
    Cards are counted by their id (e.g. "salvaged_goods"); cards.py has the names."""

    def __init__(self, game_id, deck=None, deck_name=None, saved_decks=None):
        self.game_id = game_id
        self.started_at = time.time()
        self.played_at_ms = None          # when the match started, by the game server's clock
        self.deck = deck or Counter()     # my deck {card_id: copies} (can be empty)
        self.deck_name = deck_name
        # Decks from the game's deck screen. If deck.txt is empty, the right one
        # is picked by deck classes once the match starts (see pick_deck).
        self.saved_decks = saved_decks or []
        self.deck_from_file = bool(self.deck)

        # Following every action card by the game's own card id (one per physical card):
        self.card_loc = {}                # card id -> where it is now, e.g. "P1_ActionsDeck", "P1_Hand"
        self.card_def = {}                # card id -> which card it is ("symbiosis"), once revealed
        self.original = {}                # card id -> "P1"/"P2" for cards that started in a deck
        self._reading_snapshot = False

        self.me = None                    # "P1" or "P2" once we know
        self._me_is_guess = False         # True while "me" is only a guess from viewerRole
        self.names = {}                   # {"P1": "Brainiac", "P2": "azhh"}
        self._turn_player = None          # who the last TurnChanged was for (used for names)

        self.hand_number = None           # e.g. "Hand 6"
        self.stage = None                 # e.g. "Flop"
        self.chips = {}                   # {"P1": 54, "P2": 49, "Pot": 16}
        self.opp_hand_size = None         # how many cards the opponent holds

        # Cards played from the deck, per player: {"P1": Counter({card_id: times}), ...}
        self.played = {"P1": Counter(), "P2": Counter()}
        # Cards played that were made during the match by another card
        # (e.g. Salvaged Goods gives Flop cards). They're not part of the deck.
        self.generated = {"P1": Counter(), "P2": Counter()}
        # Card ids the game showed with the lighter "generated" border (AnimateCard "generatedCard")
        self.marked_generated = set()
        self.opp_pool = []                # generated cards the opponent holds: [[generator ids], ...]
        self.opp_generators_played = set()
        # Every play in order: [{"hand": 6, "stage": "Flop", "player": "P1", "card": "...", ...}]
        self.plays = []

        self.result_code = None           # status "result" number (3 waiting, 2 playing, 0 over)
        self.deck_classes = {}            # {"P1": ["Rebel", "Inventor"], "P2": [...]}
        self.starting_hand = []           # my action cards at the start (from the snapshot)
        self.starting_hand_done = False
        self.hand_results = []            # one entry per poker hand (from "EndHand")
        self._snapshot_read = False
        self.ended = False
        self.end_reason = None            # plain-English reason we think it ended
        self.winner = None                # "P1" / "P2" / None if unknown

        self.log_lines = []               # readable lines, also written to log.txt
        self.version = 0                  # goes up on every change (the overlay redraws then)

        self._seen_moves = set()          # batch moveIndex numbers already read
        self._seen_log = set()            # log "Sequence" numbers already read
        self._log_types_seen = set()      # to report new kinds of log entries once
        self._last_move = -1              # highest moveIndex read so far

    # ---------- small helpers ----------

    def name(self, pid):
        """Show a player id as a name: you, the opponent's name, or 'P1'."""
        if pid in (None, "None"):
            return "Game"
        if pid == self.me:
            return self.names.get(pid, "You")
        return self.names.get(pid, pid)

    def opponent(self):
        return other_player(self.me) if self.me else None

    def say(self, text):
        """Add a line to the readable log."""
        stamp = time.strftime("%H:%M:%S")
        self.log_lines.append(f"{stamp}  {text}")
        self.version += 1

    def set_me(self, pid, why):
        if pid in ("P1", "P2") and self.me is None:
            self.me = pid
            self.say(f"You are {pid} ({why})")

    # ---------- things coming from the browser ----------

    def feed_my_move(self, move):
        """One move you sent (from the /moves request)."""
        self.set_me(move.get("playerId"), "from a move you sent")

    def feed_catchup(self, body):
        """One /catchup answer from the server."""
        status = body.get("status") or {}
        inner = status.get("status") or {}

        # viewerRole 0 seems to mean P1 and 1 means P2. Only a fallback guess:
        # the hand cards in the log tell us for sure (see _read_log_item).
        role = status.get("viewerRole")
        if self.me is None and role in (0, 1):
            self.me = "P1" if role == 0 else "P2"
            self.say(f"You are probably {self.me} (viewerRole {role}, will confirm)")
            self._me_is_guess = True

        # The status "result" number: 3 before the match starts, 2 while playing,
        # 0 after the end (seen in the 2026-10-24 test match). We only keep it for
        # the summary: the real end signal is the "EndGame" event below.
        self.result_code = inner.get("result", getattr(self, "result_code", None))

        # The server's clock, e.g. "2026-10-25T02:21:48.4878032+00:00" (the first one we
        # see = when the match started). Used as the match date on the website.
        if self.played_at_ms is None and inner.get("serverNow"):
            self.played_at_ms = server_time_ms(inner["serverNow"])

        # A snapshot is the whole game so far (sent when the page loads).
        # It holds the starting hands, deck classes and the game log up to now.
        # Read it first, once per match.
        snap = body.get("snapshot")
        if isinstance(snap, dict) and not self._snapshot_read:
            self._snapshot_read = True
            self._reading_snapshot = True
            self._read_events(snap, "initEventData", is_newest=True)
            self._reading_snapshot = False

        # The batches are the new moves. Read them in move order.
        batches = sorted(body.get("batches") or [], key=lambda b: b.get("moveIndex", 0))
        for batch in batches:
            self._read_batch(batch)

    # ---------- reading the events ----------

    def _read_batch(self, batch):
        move = batch.get("moveIndex")
        if move in self._seen_moves:
            return  # the page asked twice for the same move
        self._seen_moves.add(move)
        is_newest = move is None or move >= self._last_move
        if move is not None:
            self._last_move = max(self._last_move, move)
        self._read_events(batch, "eventData", is_newest)

    def _read_events(self, batch, field, is_newest):
        """Read the event list stored as text in batch[field]."""
        move = batch.get("moveIndex")
        if batch.get("payloadEncoding", "identity") != "identity":
            self.say(f"!! move {move}: unknown encoding {batch.get('payloadEncoding')} (skipped)")
            return
        try:
            events = json.loads(batch.get(field) or "[]")
        except json.JSONDecodeError:
            self.say(f"!! move {move}: could not read {field}")
            return

        # Opponent bookkeeping for this update (see _count_opp_generated)
        opp = self.opponent()
        hand_before = self.cards_in_hand(opp) if opp else 0
        self._batch_left = 0              # opponent cards that left their hand
        self._batch_drawn = 0             # opponent cards drawn from their deck
        self._batch_generator = None      # generator card the opponent played in this update

        for event in events:
            kind = event.get("Type")
            data = event.get(kind) or {}

            if kind == "SetPlayerDeckClasses":
                # e.g. {"PlayerId": "P2", "DeckClasses": ["Protector", "Rebel"]}
                self.deck_classes[data.get("PlayerId")] = data.get("DeckClasses") or []

            elif kind == "SetGameLogItems":
                # The whole log so far (in the snapshot). Same entries as AddGameLogItem.
                for item in data.get("Items") or []:
                    self._read_log_item(item, is_newest)

            elif kind == "UpdateCardVisibility":
                # The game shows me which card an id is (e.g. right before I draw it)
                card_id = (data.get("Display") or {}).get("cardId")
                if card_id:
                    self.card_def[data.get("CardId")] = card_id

            elif kind == "MoveCards":
                info = data.get("Info") or {}
                self._cards_moved(info.get("CardIds") or [], info.get("LocId") or "", info.get("Settings"))

            elif kind == "AnimateCard":
                # The lighter border on generated cards: sent to BOTH players when the
                # card is shown, e.g. {"CardId": "...", "Info": {"animationId": "generatedCard"}}
                if (data.get("Info") or {}).get("animationId") == "generatedCard":
                    self.marked_generated.add(data.get("CardId"))

            elif kind == "DestroyCard":
                # The game sometimes replaces a card with a new id: the old id is gone
                cid = (data.get("Req") or {}).get("CardId")
                if cid in self.card_loc:
                    self.card_loc[cid] = "Destroyed"

            elif kind == "CreateCard":
                # In the snapshot, my starting hand is created with names;
                # the opponent's cards are created blank.
                req = data.get("Req") or {}
                loc = req.get("Loc") or ""
                cid = req.get("CardId")
                self.card_loc[cid] = loc
                if (req.get("Display") or {}).get("cardId"):
                    self.card_def[cid] = req["Display"]["cardId"]
                # Cards in a deck or hand at the very start are that player's deck cards
                if self._reading_snapshot and not req.get("IsPokerCard") and \
                        (loc.endswith("_ActionsDeck") or loc.endswith("_Hand")):
                    self.original[cid] = loc.split("_")[0]
                if loc.endswith("_Hand") and req.get("Name") and not self.starting_hand_done:
                    pid = loc.split("_")[0]
                    if self._me_is_guess and self.me != pid:
                        self.me = pid
                    self._me_is_guess = False
                    self.set_me(pid, "your starting hand is visible")
                    self.starting_hand.append(req["Name"])

            elif kind == "EndHand":
                info = data.get("Info") or {}
                winner = info.get("WinnerId")
                me, opp = self.me or "P1", other_player(self.me or "P1")
                result = {
                    "hand": self.hand_number,
                    "winner": winner,
                    "result": info.get("HandResult"),
                    "myHand": info.get(f"{me}CombinationName"),
                    "opponentHand": info.get(f"{opp}CombinationName"),
                }
                self.hand_results.append(result)
                who = self.name(winner) if winner in ("P1", "P2") else "Nobody"
                self.say(f"[{self.hand_number}] {who} wins the hand "
                         f"({result['myHand']} vs {result['opponentHand']})")

            elif kind == "EndGame":
                winner = data.get("WinnerId")
                if winner in ("P1", "P2"):
                    self.winner = winner
                if not self.ended:
                    self.end(data.get("ExtraText") or f"winner {winner}")

            elif kind == "TurnChanged":
                self._turn_player = data.get("PlayerId")
                if is_newest:
                    self.hand_number = data.get("TurnNumber") or self.hand_number

            elif kind == "AnimatePhase":
                info = data.get("Info") or {}
                if info.get("animationId") == "setPlayerNameString" and self._turn_player:
                    # Right after "TurnChanged P2", the game shows P2's name.
                    pid, text = self._turn_player, info.get("text")
                    if text and self.names.get(pid) != text:
                        self.names[pid] = text
                        self.say(f"{pid} is called {text}")

            elif kind == "AddGameLogItem":
                self._read_log_item(data.get("Item") or {}, is_newest)

        if opp and not self._reading_snapshot:
            self._count_opp_generated(opp, hand_before)

        # The starting hand comes all at once in the snapshot
        if self.starting_hand and not self.starting_hand_done:
            self.starting_hand_done = True
            self.say(f"Starting hand: {', '.join(self.starting_hand)}")
        self.pick_deck()
        self.version += 1

    def _cards_moved(self, ids, loc, settings):
        """Cards changed place. Log my draws and cards put back in my deck."""
        opp = self.opponent()
        for cid in ids:
            before = self.card_loc.get(cid, "")
            self.card_loc[cid] = loc
            if opp and before == f"{opp}_Hand" and loc != before:
                self._batch_left += 1
            if opp and before == f"{opp}_ActionsDeck" and loc == f"{opp}_Hand":
                self._batch_drawn += 1
            owner = self.original.get(cid)
            if owner is None or owner != self.me or self._reading_snapshot:
                continue
            name = card_info(self.card_def.get(cid))["name"] if cid in self.card_def else "a card"
            deck = f"{owner}_ActionsDeck"
            if before == deck and loc != deck:
                self.say(f"[{self.hand_number}] You drew {name}" if loc.endswith("_Hand")
                         else f"[{self.hand_number}] {name} left your deck ({loc.split('_')[-1]})")
            elif loc == deck and before != deck:
                self.say(f"[{self.hand_number}] {name} went back into your deck")

    def _count_opp_generated(self, opp, hand_before):
        """After each update: did cards arrive in the opponent's hand without
        coming from their deck? Those were generated.

            arrived = (hand now - hand before) + cards that left the hand
            generated = arrived - cards drawn from their deck

        The game gives their hidden cards new ids all the time, so we can't follow
        one card. We only keep a list ("pool") of the generated cards they hold,
        each with the generator that made it (to know what it can be)."""
        hand_now = self.cards_in_hand(opp)
        arrived = (hand_now - hand_before) + self._batch_left
        new = arrived - self._batch_drawn
        if new > 0:
            # Made by the generator they just played, or else by one they played
            # earlier (Prototype / Card Protector / Wash Ashore come back later).
            if self._batch_generator:
                source = [self._batch_generator]
            else:
                source = sorted(self.opp_generators_played) or ["unknown"]
            for _ in range(new):
                self.opp_pool.append(source)
            self.say(f"[{self.hand_number}] {self.name(opp)} got {new} generated card(s)"
                     f" ({', '.join(card_info(s)['name'] if s != 'unknown' else '?' for s in source)})")
        # They can't hold more generated cards than cards (some may have been discarded)
        while len(self.opp_pool) > hand_now:
            self.opp_pool.pop(0)

    def _backcheck_copies(self, pid, card_id):
        """A deck holds at most 1 copy of a Rare and 2 of a Common. If the player
        has played more than that, the extra copies were generated."""
        info = card_info(card_id)
        extra = self.played[pid][card_id] - max_copies(info)
        while extra > 0:
            self.played[pid][card_id] -= 1
            self.generated[pid][card_id] += 1
            extra -= 1
            # fix the most recent matching play in the list
            for play in reversed(self.plays):
                if play["player"] == pid and play["cardId"] == card_id and play["generated"] is not True:
                    play["generated"] = True
                    break
            self.say(f"Backcheck: {self.name(pid)} played more {info['name']} than a deck can hold "
                     f"({max_copies(info)}), so one was generated")
        if self.played[pid][card_id] <= 0:
            self.played[pid].pop(card_id, None)

    def deck_out(self, pid):
        """Counter {card_id: n} of my deck cards that are no longer in my deck
        (drawn, discarded...). Only cards we've seen the face of."""
        out = Counter()
        for cid, owner in self.original.items():
            if owner == pid and self.card_loc.get(cid) != f"{pid}_ActionsDeck" and cid in self.card_def:
                out[self.card_def[cid]] += 1
        return out

    def cards_in_deck(self, pid):
        """How many action cards are in this player's deck right now (exact count)."""
        return sum(1 for loc in self.card_loc.values() if loc == f"{pid}_ActionsDeck")

    def cards_in_hand(self, pid):
        """How many action cards this player holds right now."""
        return sum(1 for loc in self.card_loc.values() if loc == f"{pid}_Hand")

    def pick_deck(self):
        """Choose my deck from the saved decks: same 2 classes as this match,
        then the one that holds the most of my starting hand and played cards.
        (Like the Origins tracker picks by hero, then by starting hand.)"""
        if self.deck_from_file or not self.saved_decks or not self.me:
            return
        classes = set(self.deck_classes.get(self.me) or [])
        if not classes:
            return
        candidates = [d for d in self.saved_decks if d["classes"] == classes]
        if not candidates:
            return
        seen = Counter(card_info(None, name)["id"] for name in self.starting_hand)
        seen.update(self.played[self.me])

        def fits(deck):
            return sum(min(n, deck["cards"][card_id]) for card_id, n in seen.items())

        best = max(candidates, key=fits)
        if best["name"] != self.deck_name or not self.deck:
            self.deck, self.deck_name = best["cards"], best["name"]
            how = "classes" if len(candidates) == 1 else "classes + cards seen"
            self.say(f"Deck: {best['name']} (picked by {how}: {' / '.join(sorted(classes))})")

    def _read_log_item(self, item, is_newest):
        seq = item.get("Sequence")
        if seq in self._seen_log:
            return
        self._seen_log.add(seq)

        kind = item.get("Type")
        pid = item.get("PlayerId")
        hand = item.get("HandNumber")
        stage = item.get("StageDisplayName") or item.get("Stage")

        # Who am I? My own hand cards have names, the opponent's are blank.
        for p in ("P1", "P2"):
            cards = item.get(f"{p}HandCards") or []
            if any(c.get("Name") for c in cards):
                if self._me_is_guess and self.me != p:
                    self.say(f"Correction: you are {p}, not {self.me}")
                    self.me = p
                self._me_is_guess = False
                self.set_me(p, "your hand cards are visible")

        # Current state (only from the newest log entries)
        if is_newest:
            if stage and stage != "Unknown Stage":
                self.stage = stage
            self.chips = item.get("ChipsAfter") or self.chips
            if self.me:
                theirs = item.get(f"{self.opponent()}HandCards")
                if theirs is not None:
                    self.opp_hand_size = len(theirs)

        if kind not in self._log_types_seen:
            self._log_types_seen.add(kind)
            if kind not in ("Check", "CardPlayed", "PhaseChanged", "CardsTargeted", "Fold", "Showdown"):
                self.say(f"(new kind of log entry: {kind})")

        where = f"[Hand {hand} {stage}]"
        who = self.name(pid)

        if kind == "CardPlayed":
            for card in (item.get("CardPlayed") or {}).get("PlayedCards") or []:
                info = card_info(card.get("DefinitionId"), card.get("Name"))
                owner = pid if pid in ("P1", "P2") else card.get("OwnerId")
                made, why = self._is_generated(card, info, owner)
                if owner in self.played:
                    (self.generated if made else self.played)[owner][info["id"]] += 1
                if made and owner == self.opponent() and self.opp_pool:
                    self.opp_pool.pop(0)   # one less generated card in their hand
                if owner == self.me and len(self.saved_decks) > 1:
                    self.pick_deck()   # a played card can settle a tie between decks
                self.plays.append({"hand": hand, "stage": stage, "player": owner, "card": info["name"],
                                   "cardId": info["id"], "generated": made})
                extra = f"  (generated: {why})" if made else ""
                self.say(f"{where} {self.name(owner)} played {info['name']}{extra}")
                if owner in self.played:
                    self._backcheck_copies(owner, info["id"])
                # Remember the opponent's generator cards (their output arrives in this update or later)
                if owner == self.opponent() and info["id"] in GENERATORS:
                    self.opp_generators_played.add(info["id"])
                    self._batch_generator = info["id"]
        elif kind == "PhaseChanged":
            change = item.get("PhaseChanged") or {}
            old, new = change.get("FromStageDisplayName"), change.get("ToStageDisplayName")
            # "Flop" -> "Flop - option" shows as Flop -> Flop: not worth a line
            if new and new != old and new != "Unknown Stage":
                self.say(f"{where} -> {new}")
        elif kind in ("CardsTargeted", "Showdown"):
            pass  # targets are part of the card play; "EndHand" reports the showdown
        else:
            self.say(f"{where} {who}: {kind}")

    def _is_generated(self, card, info, owner):
        """Was this card made during the match (not from the deck)?
        Returns (True/False, reason).

        1. The lighter border: the game sends AnimateCard "generatedCard" for the
           card's id, to both players (found by Olivier on 2026-10-25). Checked on
           10 matches: it was right for every card, for both players.
        2. My own cards also carry a "Generated" slot that only I can see.
        (The copy-limit backcheck in _backcheck_copies is a last safety net.)
        """
        if card.get("LiveViewId") in self.marked_generated or card.get("ViewId") in self.marked_generated:
            return True, "lighter border"
        if any((slot or {}).get("Type") == "Generated" for slot in card.get("Slots") or []):
            return True, "marked by the game"
        return False, ""

    # ---------- end of match ----------

    def end(self, reason):
        self.ended = True
        self.end_reason = reason
        self.say(f"=== Match over: {reason} ===")

    def result_word(self):
        """'win' / 'loss' / 'unknown' from my point of view."""
        if not self.winner or not self.me:
            return "unknown"
        return "win" if self.winner == self.me else "loss"

    def cards_left(self, card_id):
        """How many copies of this card are still in my deck (not drawn yet).
        If we missed the start of the match (no card ids), count played cards instead."""
        if not self.me:
            return self.deck[card_id]
        if any(owner == self.me for owner in self.original.values()):
            gone = self.deck_out(self.me)
        else:
            gone = self.played[self.me]
        return max(0, self.deck[card_id] - gone[card_id])

    def summary(self):
        """Everything worth saving at the end, as a plain dict (saved as summary.json)."""
        opp = self.opponent()

        def by_name(counter):
            return {card_info(card_id)["name"]: n for card_id, n in counter.items()}

        return {
            "gameId": self.game_id,
            "startedAt": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.started_at)),
            "savedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
            "me": self.me,
            "myName": self.names.get(self.me) if self.me else None,
            "opponent": self.names.get(opp) if opp else None,
            "result": self.result_word(),
            "ended": self.ended,
            "endReason": self.end_reason,
            "lastHand": self.hand_number,
            "chips": self.chips,
            "myDeckClasses": self.deck_classes.get(self.me, []) if self.me else [],
            "opponentDeckClasses": self.deck_classes.get(opp, []) if opp else [],
            "startingHand": self.starting_hand,
            "hands": self.hand_results,
            "deckName": self.deck_name,
            "myCardsPlayed": by_name(self.played[self.me]) if self.me else {},
            "myGeneratedPlayed": by_name(self.generated[self.me]) if self.me else {},
            "opponentCardsPlayed": by_name(self.played[opp]) if opp else {},
            "opponentGeneratedPlayed": by_name(self.generated[opp]) if opp else {},
            "plays": [dict(p, playerName=self.name(p["player"])) for p in self.plays],
        }

    def website_record(self):
        """The match as it's saved on the website (website.py). Cards are ids,
        e.g. {"salvaged_goods": 2}; the website has the names and pictures."""
        opp = self.opponent()
        me = self.me
        return {
            "gameId": self.game_id,
            "playedAt": self.played_at_ms or int(self.started_at * 1000),
            "result": self.result_word(),               # win / loss / unknown
            "myName": self.names.get(me) or "",
            "opponent": self.names.get(opp) or "?",
            "deckName": self.deck_name or "",
            "myClasses": self.deck_classes.get(me, []),
            "opponentClasses": self.deck_classes.get(opp, []),
            "myChips": self.chips.get(me, 0),
            "opponentChips": self.chips.get(opp, 0),
            "hands": [{"hand": h["hand"] or "",
                       "won": "me" if h["winner"] == me else "opponent" if h["winner"] == opp else "split",
                       "myHand": h["myHand"] or "", "opponentHand": h["opponentHand"] or ""}
                      for h in self.hand_results],
            "startingHand": [card_info(None, name)["id"] for name in self.starting_hand],
            "myCards": dict(self.played[me]),
            "myGenerated": dict(self.generated[me]),
            "opponentCards": dict(self.played[opp]),
            "opponentGenerated": dict(self.generated[opp]),
        }
