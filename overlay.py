# overlay.py
# The deck tracker, drawn like the Origins overlay (Hearthstone Deck Tracker style).
# Two windows:
#   LEFT  = my deck (cards left in my deck, greyed out when all drawn)
#   RIGHT = the opponent: what they played this match, and below it the
#           LIKELY CARDS: what they played in earlier matches with the same classes
#           (a prediction, not their decklist; click its title to turn it off/on)
# When spectating, left = player 1 and right = player 2, both drawn like opponents.
#
# Tournament mode (trophy button, top of the left window): decks are locked in a
# tournament, so every card seen in a player's tournament matches IS in their deck.
# The right window then shows TOURNAMENT DECK: those cards, with copies left this match.
#
#   - Pillow draws each window as one picture, tkinter shows it.
#   - Cards are grouped by stage, each with its colour:
#       Universal = grey, Pre-flop = blue, Flop = yellow, River = red
#     and sorted by their chip score inside each group.
#   - Cards made during the match (generated) get a teal stripe and a ✦.
#   - Drag a window to move it (the place is remembered). The X closes the tracker.
#
# Like before, it has no loop of its own: tracker.py calls update_window() often.

import io
import json
import threading
import tkinter as tk
import urllib.request
from tkinter import ttk
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

from cards import STAGES, card_info

HERE = Path(__file__).resolve().parent
ART_FOLDER = HERE / "art"                        # card pictures are downloaded here once
SETTINGS_FILE = HERE / "overlay_settings.json"   # window places + prediction on/off

WIDTH = 260                      # overlay width in pixels
ROW = 26                         # height of one card row
SORT_HIGH_FIRST = False          # True = highest chip score at the top of each stage
STAGE_GAP = 4                    # extra space between stages (no titles: the colours show the stage)
MAX_PREDICTED = 15               # most "likely cards" rows to show

# ---------- colours (red, green, blue) ----------
BG = (18, 16, 28)
PANEL = (36, 32, 52)
PANEL_GONE = (26, 23, 38)
PANEL_GUESS = (24, 22, 36)       # background of predicted rows
TEXT = (255, 255, 255)
DIM = (120, 115, 140)
GOLD = (240, 190, 60)
GREEN = (70, 220, 140)
LOSS = (235, 80, 95)
OPP = (255, 120, 120)            # opponent header
GUESS = (190, 170, 255)          # lilac: the prediction's title
TOURNEY = (240, 190, 60)         # gold: tournament mode
GENERATED = (80, 220, 205)       # teal: cards made during the match
STAGE_COLOURS = {
    "Any": (150, 150, 165),      # Universal: grey
    "PreFlop": (70, 140, 240),   # Pre-flop: blue
    "Flop": (240, 195, 55),      # Flop: yellow
    "River": (235, 75, 85),      # River: red
}
DARK_TEXT = (20, 16, 30)

FONT_FILES = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]


def font(size):
    for f in FONT_FILES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


BIG, MID, SMALL = font(15), font(13), font(11)


# ---------- card art (downloaded in the background, kept in art/) ----------

_strips = {}            # card_id -> picture strip (or None if there's no art)
_downloading = set()
art_version = [0]       # goes up when a new picture is ready, so the overlay redraws


def _download_art(card):
    try:
        ART_FOLDER.mkdir(exist_ok=True)
        request = urllib.request.Request(card["art"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as answer:
            (ART_FOLDER / f"{card['id']}.webp").write_bytes(answer.read())
    except Exception:
        pass
    _downloading.discard(card["id"])
    art_version[0] += 1


def art_strip(card):
    """A thin horizontal slice of the card art, used as the row background."""
    card_id = card["id"]
    if card_id in _strips:
        return _strips[card_id]
    path = ART_FOLDER / f"{card_id}.webp"
    if not path.exists():
        # Python note: a Thread runs a function in the background so the window doesn't freeze
        if card.get("art") and card_id not in _downloading:
            _downloading.add(card_id)
            threading.Thread(target=_download_art, args=(card,), daemon=True).start()
        return None
    try:
        picture = Image.open(io.BytesIO(path.read_bytes())).convert("RGB")
    except Exception:
        _strips[card_id] = None
        return None
    w, h = picture.size
    piece = picture.crop((int(w * 0.05), int(h * 0.30), int(w * 0.95), int(h * 0.50)))
    _strips[card_id] = piece.resize((140, ROW - 2))
    return _strips[card_id]


# ---------- drawing pieces ----------

def fit(d, text, fnt, width):
    """Shorten text with … until it fits in width pixels."""
    if d.textlength(text, font=fnt) <= width:
        return text
    while text and d.textlength(text + "…", font=fnt) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def sparkle(d, cx, cy, r, fill):
    """A 4-pointed star: the mark for generated cards."""
    k = r * 0.3
    d.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
               (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill=fill)


def score_text(chips):
    return f"+{chips}" if chips > 0 else str(chips)


def card_row(img, d, y, card, count_text, gone=False, generated=False, predicted=False):
    """One card row: stage stripe, score badge, name, faded art, count box.
    predicted = a "likely card" (prediction): darker, dashed stripe, % in the box."""
    colour = STAGE_COLOURS.get(card["type"], STAGE_COLOURS["Any"])
    d.rectangle([4, y, WIDTH - 4, y + ROW - 1], fill=PANEL_GUESS if predicted else (PANEL_GONE if gone else PANEL))

    # card art, faded in from the left (Hearthstone style)
    strip = art_strip(card)
    if strip is not None:
        darker = 4 if gone else (2 if predicted else 1)
        s = strip if darker == 1 else Image.eval(strip, lambda v: v // darker)
        mask = Image.linear_gradient("L").rotate(90).resize(s.size)    # dark on the left -> full on the right
        mask = Image.eval(mask, lambda v: min(255, int(v * 1.5)))
        img.paste(s, (WIDTH - 4 - 34 - s.size[0], y + 1), mask)

    # stage stripe on the left edge: teal for generated cards, dashed for predicted ones
    if predicted:
        for dash in range(y, y + ROW, 6):
            d.rectangle([4, dash, 7, min(dash + 2, y + ROW - 1)], fill=colour)
    else:
        d.rectangle([4, y, 7, y + ROW - 1], fill=GENERATED if generated else (colour if not gone else DIM))

    # chip score badge, in the stage colour (outlined only for predicted cards)
    badge = [12, y + 4, 40, y + ROW - 5]
    score = score_text(card.get("chips", 0))
    if predicted:
        d.rounded_rectangle(badge, radius=5, outline=colour, width=1)
        score_colour = colour
    else:
        d.rounded_rectangle(badge, radius=5, fill=colour if not gone else (55, 52, 70))
        score_colour = DARK_TEXT if not gone else DIM
    d.text(((badge[0] + badge[2]) / 2 - d.textlength(score, font=MID) / 2, y + 4), score,
           font=MID, fill=score_colour)

    # name with a dark outline so it's readable over the art
    x = 46
    if generated:
        sparkle(d, x + 5, y + ROW / 2, 6, GENERATED)
        x += 14
    name = fit(d, card["name"], MID, WIDTH - 42 - x)
    name_colour = DIM if gone else ((205, 200, 220) if predicted else TEXT)
    d.text((x, y + 4), name, font=MID, fill=name_colour, stroke_width=2, stroke_fill=(0, 0, 0))

    # count box on the right (copies left, times played, or % for a prediction)
    d.rectangle([WIDTH - 36, y + 3, WIDTH - 7, y + ROW - 4], fill=(14, 12, 22))
    box_font = SMALL if predicted else MID
    d.text((WIDTH - 21 - d.textlength(count_text, font=box_font) / 2, y + (6 if predicted else 4)),
           count_text, font=box_font, fill=GUESS if predicted else (GOLD if not gone else DIM))


def group_by_stage(counter):
    """{card_id: n} -> {stage: [(card, n), ...]} sorted by chip score, then name."""
    groups = {stage: [] for stage in STAGES}
    for card_id, n in counter.items():
        card = card_info(card_id)
        groups.setdefault(card["type"], []).append((card, n))
    for rows in groups.values():
        rows.sort(key=lambda cn: ((-1 if SORT_HIGH_FIRST else 1) * cn[0].get("chips", 0), cn[0]["name"]))
    return groups


TROPHY_ZONE = (WIDTH - 52, 0, WIDTH - 30, 26)     # where the trophy button is (left, top, right, bottom)


def trophy(d, x, y, colour):
    """A small trophy cup (the font has no emoji): cup, handles, stem, base."""
    d.pieslice([x, y - 4, x + 14, y + 10], 0, 180, fill=colour)       # the cup
    d.rectangle([x, y + 2, x + 14, y + 3], fill=colour)
    d.arc([x - 4, y + 1, x + 3, y + 8], 90, 270, fill=colour, width=2)       # handles
    d.arc([x + 11, y + 1, x + 18, y + 8], 270, 90, fill=colour, width=2)
    d.rectangle([x + 6, y + 10, x + 8, y + 13], fill=colour)           # stem
    d.rectangle([x + 3, y + 13, x + 11, y + 15], fill=colour)          # base


def title_bar(d, text, colour=TEXT, trophy_button=None):
    """Top bar with a title and the close X. trophy_button: None = no button,
    True / False = tournament mode on (gold) / off (grey)."""
    d.rectangle([0, 0, WIDTH, 26], fill=PANEL)
    room = WIDTH - (64 if trophy_button is not None else 40)
    d.text((8, 5), fit(d, text, BIG, room), font=BIG, fill=colour)
    if trophy_button is not None:
        trophy(d, TROPHY_ZONE[0] + 4, 7, TOURNEY if trophy_button else DIM)
    d.line([WIDTH - 20, 8, WIDTH - 10, 18], fill=DIM, width=2)
    d.line([WIDTH - 20, 18, WIDTH - 10, 8], fill=DIM, width=2)
    return 32


def tournament_banner(d, y, tournament):
    """Gold bar: TOURNAMENT · Sunday Cup"""
    if not tournament:
        return y
    d.rounded_rectangle([4, y, WIDTH - 4, y + 20], radius=4, fill=(60, 48, 20))
    d.text((10, y + 3), fit(d, f"TOURNAMENT · {tournament}", SMALL, WIDTH - 24), font=SMALL, fill=TOURNEY)
    return y + 26


def played_sections(img, d, y, counter):
    """Cards played, by stage. The count box shows how many times."""
    groups = group_by_stage(counter)
    for stage in STAGES:
        rows = groups.get(stage) or []
        if not rows:
            continue
        for card, n in rows:
            card_row(img, d, y, card, str(n))
            y += ROW + 2
        y += STAGE_GAP
    return y


def generated_section(img, d, y, counter):
    """Cards that were made during the match: teal stripe and a ✦, after the others."""
    groups = group_by_stage(counter)
    for stage in STAGES:
        for card, n in groups.get(stage) or []:
            card_row(img, d, y, card, str(n), generated=True)
            y += ROW + 2
    return y + 2


def result_banner(d, y, word, colour):
    d.rounded_rectangle([4, y, WIDTH - 4, y + 24], radius=5, fill=colour)
    d.text((WIDTH / 2 - d.textlength(word, font=BIG) / 2, y + 3), word, font=BIG, fill=DARK_TEXT)
    return y + 30


def short_date(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%d %b")


# ---------- LEFT window: my deck ----------

def render_my_side(game, tournament=None):
    img = Image.new("RGB", (WIDTH, 3000), BG)
    d = ImageDraw.Draw(img)
    y = title_bar(d, game.deck_name if game and game.deck_name else "Showdown tracker",
                  trophy_button=bool(tournament))
    y = tournament_banner(d, y, tournament)
    zones = {"tournament": TROPHY_ZONE}

    if game is None:
        d.text((8, y), "Waiting for a match...", font=SMALL, fill=DIM)
        return img.crop((0, 0, WIDTH, y + 22)), zones

    me, opp = game.me, game.opponent()
    left = " · ".join(x for x in (game.hand_number, game.stage) if x) or "Match found"
    d.text((8, y), left, font=SMALL, fill=DIM)
    if game.chips and me:
        right = f"{game.chips.get(me, '?')} – {game.chips.get(opp, '?')}   pot {game.chips.get('Pot', '?')}"
        d.text((WIDTH - 8 - d.textlength(right, font=SMALL), y), right, font=SMALL, fill=DIM)
    y += 18

    if game.ended:
        word = {"win": "VICTORY", "loss": "DEFEAT"}.get(game.result_word(), "MATCH OVER")
        y = result_banner(d, y, word, {"win": GREEN, "loss": LOSS}.get(game.result_word(), GOLD))
        y = online_status(d, y, game)

    if me and game.deck:
        total = sum(game.deck.values())
        # exact count from the game when we saw the match start, else from the list
        left_total = game.cards_in_deck(me) or sum(game.cards_left(c) for c in game.deck)
        d.text((8, y), f"IN DECK   {left_total}/{total}", font=MID, fill=GREEN)
        y += 20
        groups = group_by_stage(game.deck)
        for stage in STAGES:
            rows = groups.get(stage) or []
            for card, copies in rows:
                left_n = game.cards_left(card["id"])
                card_row(img, d, y, card, str(left_n), gone=left_n == 0)
                y += ROW + 2
            if rows:
                y += STAGE_GAP
        # cards I played that aren't in my deck list (deck list out of date?)
        extra = {c: n for c, n in game.played[me].items() if c not in game.deck}
        if extra:
            d.text((8, y), "Not in deck list", font=SMALL, fill=DIM)
            y = played_sections(img, d, y + 16, extra)
    elif me:
        d.text((8, y), "MY CARDS PLAYED", font=MID, fill=GREEN)
        y += 20
        if game.played[me]:
            y = played_sections(img, d, y, game.played[me])
        else:
            d.text((8, y), "nothing yet (open the deck screen once", font=SMALL, fill=DIM)
            d.text((8, y + 14), "so the tracker knows your decks)", font=SMALL, fill=DIM)
            y += 32
    # My own generated cards aren't shown (they'd make the panel too tall).
    return img.crop((0, 0, WIDTH, y + 6)), zones


def online_status(d, y, game):
    status = getattr(game, "online_status", "")     # "Saved to website ✓" (see tracker.py)
    if status:
        d.text((8, y), fit(d, status, SMALL, WIDTH - 16), font=SMALL,
               fill=GREEN if "✓" in status else (GOLD if "Saving" in status else LOSS))
        y += 16
    return y


# ---------- a player panel: the opponent (or either player when spectating) ----------

def render_player(game, pid, prediction, show_prediction, waiting_text="Opponent",
                  tournament=None, tdeck=None, trophy_button=False):
    """Returns (picture, click zones). Click zones: {"prediction": (top, bottom)},
    and {"tournament": (left, top, right, bottom)} when this window has the trophy button.
    tdeck = what's known of their tournament deck (profiles.tournament_deck)."""
    img = Image.new("RGB", (WIDTH, 3000), BG)
    d = ImageDraw.Draw(img)
    zones = {"tournament": TROPHY_ZONE} if trophy_button else {}
    trophy_state = bool(tournament) if trophy_button else None

    if game is None or pid is None:
        y = title_bar(d, waiting_text, OPP, trophy_state)
        y = tournament_banner(d, y, tournament)
        d.text((8, y), "Waiting for a match...", font=SMALL, fill=DIM)
        return img.crop((0, 0, WIDTH, y + 22)), zones

    y = title_bar(d, game.name(pid).upper(), OPP, trophy_state)
    y = tournament_banner(d, y, tournament)

    # classes (left) and hand / deck counts (right)
    classes = game.deck_classes.get(pid)
    d.text((8, y), " / ".join(classes) if classes else "", font=SMALL, fill=DIM)
    in_hand = game.cards_in_hand(pid) or (game.opp_hand_size if pid == game.opponent() else None)
    if in_hand is not None:
        in_deck = game.cards_in_deck(pid)
        hand = f"{in_hand} in hand" + (f" · {in_deck} in deck" if in_deck else "")
        x = WIDTH - 8 - d.textlength(hand, font=SMALL)
        d.text((x, y), hand, font=SMALL, fill=DIM)
        held = len(game.opp_pool) if pid == game.opponent() else 0    # generated cards they hold: "✦2"
        if held:
            count = str(held)
            x -= 10 + d.textlength(count, font=SMALL)
            sparkle(d, x, y + 6, 5, GENERATED)
            d.text((x + 7, y), count, font=SMALL, fill=GENERATED)
    y += 18

    if game.spectating:
        # chips, and the winner at the end
        d.text((8, y), f"Chips {game.chips.get(pid, '?')}", font=SMALL, fill=DIM)
        y += 16
        if game.ended:
            won = game.winner == pid
            y = result_banner(d, y, "WINNER" if won else "LOST", GREEN if won else LOSS)
            if pid == "P1":
                y = online_status(d, y, game)

    # ----- this match -----
    if game.played[pid]:
        y = played_sections(img, d, y + 2, game.played[pid])
    elif not game.generated[pid]:
        d.text((8, y + 2), "nothing played yet", font=SMALL, fill=DIM)
        y += 20
    y = generated_section(img, d, y, game.generated[pid])

    # ----- tournament deck: cards KNOWN to be in their deck (decks are locked) -----
    known = {}
    if tournament:
        y += 4
        if tdeck is None:
            d.text((8, y), f"TOURNAMENT DECK: not seen in {tournament} yet", font=SMALL, fill=DIM)
            y += 18
        else:
            known = tdeck["cards"]
            d.line([4, y, WIDTH - 4, y], fill=TOURNEY)
            d.text((8, y + 4), "TOURNAMENT DECK", font=MID, fill=TOURNEY)
            d.text((8, y + 22), f"{tdeck['known']}/30 cards known · from {tdeck['matches']} "
                                f"match{'es' if tdeck['matches'] != 1 else ''}", font=SMALL, fill=DIM)
            d.text((8, y + 36), "count = copies they still have this match", font=SMALL, fill=DIM)
            y += 54
            groups = group_by_stage(known)
            for stage in STAGES:
                rows = groups.get(stage) or []
                for card, copies in rows:
                    left_n = max(0, copies - game.played[pid][card["id"]])
                    card_row(img, d, y, card, str(left_n), gone=left_n == 0)
                    y += ROW + 2
                if rows:
                    y += STAGE_GAP

    # ----- likely cards (from earlier matches) -----
    y += 4
    top = y
    if not show_prediction:
        d.text((8, y), "Likely cards: hidden (click to show)", font=SMALL, fill=DIM)
        y += 18
    elif not classes:
        d.text((8, y), "LIKELY CARDS: waiting for their classes...", font=SMALL, fill=DIM)
        y += 18
    elif prediction is None:
        d.text((8, y), "LIKELY CARDS", font=SMALL, fill=GUESS)
        d.text((8, y + 14), f"No earlier matches vs {game.name(pid)}", font=SMALL, fill=DIM)
        d.text((8, y + 28), f"on {' / '.join(classes)}", font=SMALL, fill=DIM)
        y += 46
    else:
        n = prediction["matches"]
        d.line([4, y, WIDTH - 4, y], fill=GUESS)
        d.text((8, y + 4), "LIKELY CARDS", font=MID, fill=GUESS)
        hide = "hide"
        d.text((WIDTH - 8 - d.textlength(hide, font=SMALL), y + 6), hide, font=SMALL, fill=DIM)
        d.text((8, y + 22), f"NOT their decklist: played in {n} earlier", font=SMALL, fill=DIM)
        d.text((8, y + 36), f"match{'es' if n != 1 else ''} · last seen {short_date(prediction['lastSeen'])}",
               font=SMALL, fill=DIM)
        y += 54
        # Leave out cards they already played this match as often as ever before,
        # and cards already in the TOURNAMENT DECK above (those are certain)
        played_now = game.played[pid]
        rows = [c for c in prediction["cards"] if played_now[c["id"]] < c["most"] and c["id"] not in known]
        shown = rows[:MAX_PREDICTED]
        groups = {}
        for c in shown:
            groups.setdefault(card_info(c["id"])["type"], []).append(c)
        for stage in STAGES:
            stage_rows = sorted(groups.get(stage, []), key=lambda c: (-c["percent"], card_info(c["id"])["name"]))
            for c in stage_rows:
                card_row(img, d, y, card_info(c["id"]), f"{c['percent']}%", predicted=True)
                y += ROW + 2
            if stage_rows:
                y += STAGE_GAP
        if len(rows) > len(shown):
            d.text((8, y), f"+ {len(rows) - len(shown)} more seen less often", font=SMALL, fill=DIM)
            y += 16
        if not rows:
            already = "in the tournament deck or played already" if known else "played already"
            d.text((8, y), f"all of them {already}", font=SMALL, fill=DIM)
            y += 16
    zones["prediction"] = (top, top + 22)
    return img.crop((0, 0, WIDTH, y + 6)), zones


# ---------- the windows ----------

def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_settings(settings):
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=1), encoding="utf-8")
    except OSError:
        pass


class Panel:
    """One overlay window: shows a picture, drag to move, X closes everything."""

    def __init__(self, window, name, place, overlay):
        self.window, self.name, self.overlay = window, name, overlay
        window.title("Showdown tracker")
        window.overrideredirect(True)            # no Windows title bar
        window.attributes("-topmost", True)      # stay above the browser
        window.attributes("-alpha", 0.95)
        window.geometry(f"+{place[0]}+{place[1]}")
        self.label = tk.Label(window, bd=0, bg="#12101c")
        self.label.pack()
        self.label.bind("<ButtonPress-1>", self._press)
        self.label.bind("<B1-Motion>", self._move)
        self.label.bind("<ButtonRelease-1>", self._release)
        self.zones = {}

    def _press(self, event):
        self._start = (event.x_root, event.y_root)
        self._dx = event.x_root - self.window.winfo_x()
        self._dy = event.y_root - self.window.winfo_y()

    def _move(self, event):
        self.window.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def _release(self, event):
        moved = abs(event.x_root - self._start[0]) + abs(event.y_root - self._start[1])
        if moved >= 4:
            self.overlay.remember_place(self.name, self.window.winfo_x(), self.window.winfo_y())
        elif event.x > WIDTH - 28 and event.y < 26:
            self.overlay.quit()
        elif "tournament" in self.zones and self.zones["tournament"][0] <= event.x <= self.zones["tournament"][2] \
                and self.zones["tournament"][1] <= event.y <= self.zones["tournament"][3]:
            self.overlay.ask_tournament()
        elif "prediction" in self.zones and self.zones["prediction"][0] <= event.y <= self.zones["prediction"][1]:
            self.overlay.toggle_prediction()

    def draw(self, picture, zones):
        # Python note: keep a reference to the PhotoImage, or tkinter shows nothing
        self._photo = ImageTk.PhotoImage(picture)
        self.label.configure(image=self._photo)
        self.zones = zones


class Overlay:
    def __init__(self, on_quit, predict=None, recorder=None):
        """predict(name, classes, game_id) -> prediction or None (see profiles.py).
        recorder = tracker.py's Recorder, for tournament mode (can be None)."""
        self.on_quit = on_quit
        self.predict = predict or (lambda name, classes, game_id: None)
        self.recorder = recorder
        self._dialog = None
        self.closed = False
        self._shown = None
        self.settings = load_settings()
        self.settings.setdefault("prediction", True)

        root = tk.Tk()
        screen_width = root.winfo_screenwidth()
        self.root = root
        self.left = Panel(root, "left", self.settings.get("left", (20, 120)), self)
        self.right = Panel(tk.Toplevel(root), "right",
                           self.settings.get("right", (screen_width - WIDTH - 20, 120)), self)
        self.show(None)

    def remember_place(self, name, x, y):
        self.settings[name] = (x, y)
        save_settings(self.settings)

    def toggle_prediction(self):
        self.settings["prediction"] = not self.settings["prediction"]
        save_settings(self.settings)
        self._shown = None            # redraw now

    # ----- tournament mode -----

    def tournament(self):
        return self.recorder.tournament if self.recorder else None

    def ask_tournament(self):
        """A small window: pick or type the tournament name, Start / Stop / Cancel."""
        if self.recorder is None:
            return
        if self._dialog is not None and self._dialog.winfo_exists():
            self._dialog.lift()
            return
        win = tk.Toplevel(self.root)
        self._dialog = win
        win.title("Tournament mode")
        win.attributes("-topmost", True)
        win.configure(bg="#1b1d24", padx=14, pady=12)
        tk.Label(win, text="Tournament name", bg="#1b1d24", fg="white", font=("Segoe UI", 10)).pack(anchor="w")
        tk.Label(win, text="Decks are locked in a tournament: every match you play or watch\n"
                           "while this is on adds to the players' known tournament decks.",
                 justify="left", bg="#1b1d24", fg="#9a9cb8", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 8))
        # A list of earlier names (mine + shared), so everyone uses the same spelling
        names = self.recorder.tournament_names()
        box = ttk.Combobox(win, values=names, width=34)
        box.set(self.tournament() or (names[0] if names else ""))
        box.pack(fill="x")
        box.focus_set()
        buttons = tk.Frame(win, bg="#1b1d24")
        buttons.pack(fill="x", pady=(10, 0))

        def start(event=None):
            if box.get().strip():
                self.recorder.set_tournament(box.get())
                self._shown = None
                win.destroy()

        def stop():
            self.recorder.set_tournament(None)
            self._shown = None
            win.destroy()

        tk.Button(buttons, text="Start", command=start, bg="#fcbf1e", relief="flat", padx=12).pack(side="left")
        if self.tournament():
            tk.Button(buttons, text="Stop tournament mode", command=stop, relief="flat", padx=8).pack(side="left", padx=6)
        tk.Button(buttons, text="Cancel", command=win.destroy, relief="flat", padx=8).pack(side="right")
        box.bind("<Return>", start)
        win.geometry(f"+{self.root.winfo_x() + 20}+{self.root.winfo_y() + 40}")

    def quit(self):
        if not self.closed:
            self.closed = True
            self.root.destroy()
            self.on_quit()

    def update_window(self):
        """Let tkinter draw and handle clicks. Called often by tracker.py."""
        if not self.closed:
            self.root.update()

    def _prediction_for(self, game, pid):
        if game is None or pid is None or not self.settings["prediction"]:
            return None
        classes = game.deck_classes.get(pid)
        name = game.names.get(pid)
        return self.predict(name, classes, game.game_id) if name and classes else None

    def show(self, game):
        """Redraw if something changed (new event, a card picture finished downloading,
        or prediction turned on/off)."""
        if self.closed:
            return
        tournament = self.tournament()
        key = (id(game), game.version if game else None, art_version[0], self.settings["prediction"], tournament)
        if key == self._shown:
            return
        self._shown = key
        on = self.settings["prediction"]

        def tdeck(pid):
            name = game.names.get(pid) if game and pid else None
            return self.recorder.tournament_deck(name, game.game_id) if tournament and name else None

        if game is not None and game.spectating:
            self.left.draw(*render_player(game, "P1", self._prediction_for(game, "P1"), on,
                                          tournament=tournament, tdeck=tdeck("P1"), trophy_button=True))
            self.right.draw(*render_player(game, "P2", self._prediction_for(game, "P2"), on,
                                           tournament=tournament, tdeck=tdeck("P2")))
        else:
            opp = game.opponent() if game else None
            self.left.draw(*render_my_side(game, tournament))
            self.right.draw(*render_player(game, opp, self._prediction_for(game, opp), on,
                                           tournament=tournament, tdeck=tdeck(opp)))
