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
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

from cards import STAGES, card_info

HERE = Path(__file__).resolve().parent
ART_FOLDER = HERE / "art"                        # card pictures are downloaded here once
SETTINGS_FILE = HERE / "overlay_settings.json"   # window places + prediction on/off

WIDTH = 220                      # overlay width in pixels
ROW = 19                         # height of one card row
ROW_GAP = 1                      # space between two rows
BAR = 20                         # height of the top bar
SORT_HIGH_FIRST = False          # True = highest chip score at the top of each stage
STAGE_GAP = 3                    # extra space between stages (no titles: the colours show the stage)
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


BIG, MID, SMALL = font(12), font(11), font(9)


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
    _strips[card_id] = piece.resize((110, ROW - 2))
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
        img.paste(s, (WIDTH - 4 - 28 - s.size[0], y + 1), mask)

    # stage stripe on the left edge: teal for generated cards, dashed for predicted ones
    if predicted:
        for dash in range(y, y + ROW, 5):
            d.rectangle([4, dash, 6, min(dash + 2, y + ROW - 1)], fill=colour)
    else:
        d.rectangle([4, y, 6, y + ROW - 1], fill=GENERATED if generated else (colour if not gone else DIM))

    # chip score badge, in the stage colour (outlined only for predicted cards)
    badge = [9, y + 2, 33, y + ROW - 3]
    score = score_text(card.get("chips", 0))
    if predicted:
        d.rounded_rectangle(badge, radius=4, outline=colour, width=1)
        score_colour = colour
    else:
        d.rounded_rectangle(badge, radius=4, fill=colour if not gone else (55, 52, 70))
        score_colour = DARK_TEXT if not gone else DIM
    d.text(((badge[0] + badge[2]) / 2 - d.textlength(score, font=MID) / 2, y + 2), score,
           font=MID, fill=score_colour)

    # name with a dark outline so it's readable over the art
    x = 38
    if generated:
        sparkle(d, x + 4, y + ROW / 2, 5, GENERATED)
        x += 11
    name = fit(d, card["name"], MID, WIDTH - 34 - x)
    name_colour = DIM if gone else ((205, 200, 220) if predicted else TEXT)
    d.text((x, y + 2), name, font=MID, fill=name_colour, stroke_width=2, stroke_fill=(0, 0, 0))

    # count box on the right (copies left, times played, or % for a prediction)
    d.rectangle([WIDTH - 29, y + 2, WIDTH - 5, y + ROW - 3], fill=(14, 12, 22))
    box_font = SMALL if predicted else MID
    d.text((WIDTH - 17 - d.textlength(count_text, font=box_font) / 2, y + (4 if predicted else 2)),
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


TROPHY_ZONE = (WIDTH - 42, 0, WIDTH - 24, BAR)     # where the trophy button is (left, top, right, bottom)


def trophy(d, x, y, colour):
    """A small trophy cup (the font has no emoji): cup, handles, stem, base."""
    d.pieslice([x, y - 3, x + 10, y + 7], 0, 180, fill=colour)        # the cup
    d.rectangle([x, y + 1, x + 10, y + 2], fill=colour)
    d.arc([x - 3, y, x + 2, y + 6], 90, 270, fill=colour, width=1)      # handles
    d.arc([x + 8, y, x + 13, y + 6], 270, 90, fill=colour, width=1)
    d.rectangle([x + 4, y + 7, x + 6, y + 9], fill=colour)             # stem
    d.rectangle([x + 2, y + 9, x + 8, y + 11], fill=colour)            # base


def title_bar(d, text, colour=TEXT, trophy_button=None, tournament=None, right=None, right_colour=GREEN):
    """Top bar, one line: title, then the tournament in gold ("NOUS · Daily Small…"),
    an optional number on the right (e.g. 23/30), the trophy button and the close X.
    trophy_button: None = no button, True / False = tournament mode on (gold) / off (grey)."""
    d.rectangle([0, 0, WIDTH, BAR], fill=PANEL)
    end = WIDTH - (46 if trophy_button is not None else 26)        # room before the buttons
    if right:
        end -= d.textlength(right, font=MID) + 6
        d.text((end + 4, 4), right, font=MID, fill=right_colour)
    title = fit(d, text, BIG, end - 8)
    d.text((6, 3), title, font=BIG, fill=colour)
    if tournament:
        x = 6 + d.textlength(title, font=BIG) + 6
        if end - x > 30:
            d.text((x, 5), fit(d, "· " + tournament, SMALL, end - x), font=SMALL, fill=TOURNEY)
    if trophy_button is not None:
        trophy(d, TROPHY_ZONE[0] + 4, 6, TOURNEY if trophy_button else DIM)
    d.line([WIDTH - 15, 6, WIDTH - 8, 13], fill=DIM, width=2)          # close X
    d.line([WIDTH - 15, 13, WIDTH - 8, 6], fill=DIM, width=2)
    return BAR + 4


def section_title(d, y, left, colour, right="", right_colour=DIM):
    """One line: a coloured section name on the left, small grey info on the right."""
    d.line([4, y, WIDTH - 4, y], fill=colour)
    d.text((6, y + 3), left, font=MID, fill=colour)
    if right:
        x = 6 + d.textlength(left, font=MID) + 6
        d.text((x, y + 5), fit(d, right, SMALL, WIDTH - 6 - x), font=SMALL, fill=right_colour)
    return y + 19


def played_sections(img, d, y, counter):
    """Cards played, by stage. The count box shows how many times."""
    groups = group_by_stage(counter)
    for stage in STAGES:
        rows = groups.get(stage) or []
        if not rows:
            continue
        for card, n in rows:
            card_row(img, d, y, card, str(n))
            y += ROW + ROW_GAP
        y += STAGE_GAP
    return y


def generated_section(img, d, y, counter):
    """Cards that were made during the match: teal stripe and a ✦, after the others."""
    groups = group_by_stage(counter)
    for stage in STAGES:
        for card, n in groups.get(stage) or []:
            card_row(img, d, y, card, str(n), generated=True)
            y += ROW + ROW_GAP
    return y + 2


def result_banner(d, y, word, colour):
    d.rounded_rectangle([4, y, WIDTH - 4, y + 17], radius=4, fill=colour)
    d.text((WIDTH / 2 - d.textlength(word, font=BIG) / 2, y + 1), word, font=BIG, fill=DARK_TEXT)
    return y + 21


# ---------- LEFT window: my deck ----------

def render_my_side(game, tournament=None, trophy_on=None):
    """tournament = the match's tournament (shown in the opponent's bar);
    trophy_on = manual tournament mode (the button)."""
    trophy_on = bool(tournament) if trophy_on is None else trophy_on
    img = Image.new("RGB", (WIDTH, 3000), BG)
    d = ImageDraw.Draw(img)
    zones = {"tournament": TROPHY_ZONE}
    me = game.me if game else None

    # cards left in my deck (exact count from the game when we saw the match start)
    left_total = None
    if me and game.deck:
        left_total = game.cards_in_deck(me) or sum(game.cards_left(c) for c in game.deck)
    y = title_bar(d, game.deck_name if game and game.deck_name else "Showdown tracker",
                  trophy_button=trophy_on,
                  right=f"{left_total}/{sum(game.deck.values())}" if left_total is not None else None)

    if game is None:
        d.text((6, y), "Waiting for a match...", font=SMALL, fill=DIM)
        return img.crop((0, 0, WIDTH, y + 16)), zones

    if game.ended:
        word = {"win": "VICTORY", "loss": "DEFEAT"}.get(game.result_word(), "MATCH OVER")
        y = result_banner(d, y, word, {"win": GREEN, "loss": LOSS}.get(game.result_word(), GOLD))
        y = online_status(d, y, game)

    if me and game.deck:
        groups = group_by_stage(game.deck)
        for stage in STAGES:
            rows = groups.get(stage) or []
            for card, copies in rows:
                left_n = game.cards_left(card["id"])
                card_row(img, d, y, card, str(left_n), gone=left_n == 0)
                y += ROW + ROW_GAP
            if rows:
                y += STAGE_GAP
        # cards I played that aren't in my deck list (deck list out of date?)
        extra = {c: n for c, n in game.played[me].items() if c not in game.deck}
        if extra:
            d.text((6, y), "Not in deck list", font=SMALL, fill=DIM)
            y = played_sections(img, d, y + 13, extra)
    elif me:
        if game.played[me]:
            y = played_sections(img, d, y, game.played[me])
        d.text((6, y), "Open the game's deck screen once to load your decks", font=SMALL, fill=DIM)
        y += 14
    # My own generated cards aren't shown (they'd make the panel too tall).
    return img.crop((0, 0, WIDTH, y + 4)), zones


def online_status(d, y, game):
    status = getattr(game, "online_status", "")     # "Saved to website ✓" (see tracker.py)
    if status:
        d.text((6, y), fit(d, status, SMALL, WIDTH - 12), font=SMALL,
               fill=GREEN if "✓" in status else (GOLD if "Saving" in status else LOSS))
        y += 13
    return y


# ---------- a player panel: the opponent (or either player when spectating) ----------

def render_player(game, pid, prediction, show_prediction, waiting_text="Opponent",
                  tournament=None, tdeck=None, trophy_button=False, trophy_on=None, warning=None):
    """Returns (picture, click zones). Click zones: {"prediction": (top, bottom)},
    and {"tournament": (left, top, right, bottom)} when this window has the trophy button.
    tdeck = what's known of their tournament deck (profiles.tournament_deck)."""
    img = Image.new("RGB", (WIDTH, 3000), BG)
    d = ImageDraw.Draw(img)
    zones = {"tournament": TROPHY_ZONE} if trophy_button else {}
    trophy_state = (bool(tournament) if trophy_on is None else trophy_on) if trophy_button else None

    if game is None or pid is None:
        y = title_bar(d, waiting_text, OPP, trophy_state, tournament)
        d.text((6, y), "Waiting for a match...", font=SMALL, fill=DIM)
        return img.crop((0, 0, WIDTH, y + 16)), zones

    # Top bar: NAME · tournament, and WON / LOST when a watched match is over
    right = None
    if game.spectating and game.ended:
        right = "WON" if game.winner == pid else "LOST"
    y = title_bar(d, game.name(pid).upper(), OPP, trophy_state, tournament,
                  right=right, right_colour=GREEN if right == "WON" else LOSS)
    if game.spectating and game.ended and pid == "P1":
        y = online_status(d, y, game)

    # ----- this match -----
    known = {}
    if not tournament:
        # ----- this match: what they played (count = times) -----
        y = played_sections(img, d, y, game.played[pid])
    else:
        # ----- tournament: ONE list. Decks are locked, so every card played this match
        # is in their deck too: known deck + new cards from this match.
        # count = copies they still have this match (0 = grey)
        earlier = tdeck["cards"] if tdeck else {}
        played_now = game.seen(pid)          # played + discarded this match: both used up a copy
        known = {c: max(earlier.get(c, 0), played_now[c]) for c in set(earlier) | set(played_now)}
        n = tdeck["matches"] if tdeck else 0
        info = f"{sum(known.values())}/30 · " + (f"{n} earlier match{'es' if n != 1 else ''}" if n else "first time seen")
        y = section_title(d, y, "TOURNAMENT DECK", TOURNEY, info)
        groups = group_by_stage(known)
        for stage in STAGES:
            rows = groups.get(stage) or []
            for card, copies in rows:
                left_n = max(0, copies - played_now[card["id"]])
                card_row(img, d, y, card, str(left_n), gone=left_n == 0)
                y += ROW + ROW_GAP
            if rows:
                y += STAGE_GAP
    # generated cards (teal ✦): never part of the deck, so always after it
    y = generated_section(img, d, y, game.generated[pid])

    # ----- likely cards (from earlier matches): a guess, NOT their decklist -----
    y += 2
    top = y
    classes = game.deck_classes.get(pid)
    if not show_prediction:
        d.text((6, y), "Likely cards hidden (click to show)", font=SMALL, fill=DIM)
        y += 14
    elif not classes:
        pass
    elif prediction is None:
        y = section_title(d, y, "LIKELY", GUESS, "no earlier matches")
    else:
        n = prediction["matches"]
        y = section_title(d, y, "LIKELY", GUESS, f"not their deck · {n} match{'es' if n != 1 else ''}")
        d.text((WIDTH - 6 - d.textlength("hide", font=SMALL), top + 5), "hide", font=SMALL, fill=DIM)
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
                y += ROW + ROW_GAP
            if stage_rows:
                y += STAGE_GAP
        if len(rows) > len(shown):
            d.text((6, y), f"+ {len(rows) - len(shown)} more seen less often", font=SMALL, fill=DIM)
            y += 13
    zones["prediction"] = (top, top + 18)
    if warning:          # e.g. "not linked: no shared data" (no tracker_key.txt)
        d.text((6, y), fit(d, warning, SMALL, WIDTH - 12), font=SMALL, fill=LOSS)
        y += 13
    return img.crop((0, 0, WIDTH, y + 4)), zones


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
        elif event.x > WIDTH - 20 and event.y < BAR:
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

    def tournament(self, game=None):
        """The tournament to show: the match's own (detected, or set when it started),
        else the manual trophy name."""
        if game is not None and (game.tournament or game.tournament_auto):
            return game.tournament
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
        tournament = self.tournament(game)
        trophy_on = bool(self.tournament())      # the trophy shows the manual mode
        status = getattr(self.recorder, "shared_status", "") or ""
        warning = status if status.startswith(("not linked", "shared data: download failed")) else None
        key = (id(game), game.version if game else None, art_version[0], self.settings["prediction"], tournament,
               trophy_on, warning)
        if key == self._shown:
            return
        self._shown = key
        on = self.settings["prediction"]

        def tdeck(pid):
            name = game.names.get(pid) if game and pid else None
            return self.recorder.tournament_deck(name, game.game_id, tournament) if tournament and name else None

        if game is not None and game.spectating:
            self.left.draw(*render_player(game, "P1", self._prediction_for(game, "P1"), on,
                                          tournament=tournament, tdeck=tdeck("P1"), trophy_button=True,
                                          trophy_on=trophy_on))
            self.right.draw(*render_player(game, "P2", self._prediction_for(game, "P2"), on,
                                           tournament=tournament, tdeck=tdeck("P2"), warning=warning))
        else:
            opp = game.opponent() if game else None
            self.left.draw(*render_my_side(game, tournament, trophy_on))
            self.right.draw(*render_player(game, opp, self._prediction_for(game, opp), on,
                                           tournament=tournament, tdeck=tdeck(opp), warning=warning))
