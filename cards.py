# cards.py
# The card list (cards.json, made by update_cards.py) and reading deck files.

import base64
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The four stages, in the order the overlay shows them.
# The game calls Universal cards "Any".
STAGES = ["Any", "PreFlop", "Flop", "River"]
STAGE_NAMES = {"Any": "Universal", "PreFlop": "Pre-flop", "Flop": "Flop", "River": "River"}


def _load():
    try:
        with open(HERE / "cards.json", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print("cards.json is missing: run  python update_cards.py")
        return []


ALL_CARDS = _load()
BY_ID = {c["id"]: c for c in ALL_CARDS}
BY_NAME = {c["name"].lower(): c for c in ALL_CARDS}


# Cards that put new cards in their owner's hand, and what those cards can be.
# (From the card texts in cards.json. Used to guess which of the opponent's
#  plays were generated, since the game hides that mark on their cards.)
GENERATORS = {
    "salvaged_goods": lambda c: c["type"] == "Flop",            # "Get that many Flop action cards plus 1"
    "chain_reaction": lambda c: c["type"] == "PreFlop",         # "Get 3 random Preflop action cards"
    "eureka": lambda c: c["type"] == "River",                   # "get 3 random River action cards"
    "high_hand_bonus": lambda c: c["type"] == "River",          # "Get a random River action card"
    "wash_ashore": lambda c: c["type"] in ("Any", "River"),     # "Get a random Universal or River action card"
    "cinch": lambda c: "Backfire" in (c.get("text") or ""),     # "Get a random action card with Backfire"
    "comeback_chance": lambda c: c["id"] == "roulette",         # "Get a Roulette"
    "card_protector": lambda c: c["id"] == "card_protector",    # "If you win showdown, get Card Protector"
    "prototype": lambda c: c["id"] == "prototype",              # "If you win the pot, get Prototype"
    "spiraling_debt": lambda c: c["id"] == "spiraling_debt",    # "If you lose showdown, get Spiraling Debt"
    "all_in": lambda c: True,                                   # "Get a random action card"
}


def max_copies(card):
    """Most copies a deck can hold: Rare 1, Common 2.
    (Seen in all 9 decks on 2026-10-24: 92 Rares, all 1 copy; Commons 1 or 2.)
    So a 2nd Rare or a 3rd Common in one match must have been generated."""
    return 1 if card.get("rarity") == "Rare" else 2


def could_make(generator_id, card):
    """Could this generator card have made this card? (unknown generator = yes)"""
    rule = GENERATORS.get(generator_id)
    return True if rule is None else rule(card)


def find_card(text):
    """Find a card by its id ("salvaged_goods") or its name ("Salvaged Goods").
    Returns the card dict, or None."""
    if not text:
        return None
    return BY_ID.get(text) or BY_NAME.get(text.strip().lower())


def card_info(card_id, name=None):
    """The card for this id. If it's not in cards.json (a new card), a stand-in is
    made so the overlay can still show it."""
    return BY_ID.get(card_id) or find_card(name) or {
        "id": card_id, "name": name or card_id, "type": "Any", "chips": 0,
        "class": None, "art": None, "unknown": True}


def decode_deck_code(code):
    """The game stores decks as base64 text of {"c": [["card_id", copies], ...]}.
    Returns a Counter {card_id: copies}, or None if it isn't a deck code."""
    code = code.strip()
    code += "=" * (-len(code) % 4)   # base64 needs a length that's a multiple of 4
    try:
        data = json.loads(base64.b64decode(code))
        return Counter({card_id: int(n) for card_id, n in data["c"]})
    except Exception:
        return None


def load_saved_decks(path):
    """Your decks as the game sent them (saved by the tracker when you open the
    deck screen: games/decks/Decks_compact.json).
    Returns a list of {"name": "Theory Craft", "cards": Counter, "classes": {"Inventor", "Rebel"}}."""
    try:
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    decks = []
    for deck in saved.get("body") or []:
        cards = decode_deck_code(deck.get("compactData") or "")
        if cards:
            classes = {card_info(card_id).get("class") for card_id in cards} - {None}
            decks.append({"name": deck.get("name") or "Deck", "cards": cards, "classes": classes})
    return decks


def read_deck_file(path):
    """Read deck.txt. Returns (deck name, Counter {card_id: copies}, [names not found]).

    Lines can be:
        name: Theory Craft          the deck's name
        2 Silver Bullet             2 copies (name or id)
        Silver Bullet               1 copy
        code: eyJjIjpbWyJ...        a deck code (the game's own format)
    Empty lines and lines starting with # are skipped.
    """
    name, deck, unknown = None, Counter(), []
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return name, deck, unknown
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("name:"):
            name = line[5:].strip()
            continue
        if line.lower().startswith("code:"):
            deck.update(decode_deck_code(line[5:]) or Counter())
            continue
        first, _, rest = line.partition(" ")
        copies, text = (int(first), rest) if first.isdigit() and rest else (1, line)
        card = find_card(text)
        if card:
            deck[card["id"]] += copies
        else:
            unknown.append(text)
    return name, deck, unknown
