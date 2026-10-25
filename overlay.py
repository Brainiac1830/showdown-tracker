# overlay.py
# The deck tracker window, drawn like the Origins overlay (Hearthstone Deck Tracker style):
#   - Pillow draws the whole panel as one picture, tkinter shows it.
#   - Cards are grouped by stage, each with its colour:
#       Universal = grey, Pre-flop = blue, Flop = yellow, River = red
#     and sorted by their chip score inside each group.
#   - Each row: score badge, card name, the card's art faded in, copies left.
#   - Cards made during the match (generated) get their own teal section with a ✦ mark.
#   - Drag to move. Click the X to close the tracker.
#
# Like before, it has no loop of its own: tracker.py calls update_window() often.

import io
import threading
import tkinter as tk
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageTk

from cards import STAGES, card_info

HERE = Path(__file__).resolve().parent
ART_FOLDER = HERE / "art"        # card pictures are downloaded here once

WIDTH = 260                      # overlay width in pixels
ROW = 26                         # height of one card row
SORT_HIGH_FIRST = False          # True = highest chip score at the top of each stage
STAGE_GAP = 4                    # extra space between stages (no titles: the colours show the stage)

# ---------- colours (red, green, blue) ----------
BG = (18, 16, 28)
PANEL = (36, 32, 52)
PANEL_GONE = (26, 23, 38)
TEXT = (255, 255, 255)
DIM = (120, 115, 140)
GOLD = (240, 190, 60)
GREEN = (70, 220, 140)
LOSS = (235, 80, 95)
OPP = (255, 120, 120)            # opponent header
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


def card_row(img, d, y, card, count_text, gone=False, generated=False):
    """One card row: stage stripe, score badge, name, faded art, count box."""
    colour = STAGE_COLOURS.get(card["type"], STAGE_COLOURS["Any"])
    d.rectangle([4, y, WIDTH - 4, y + ROW - 1], fill=PANEL_GONE if gone else PANEL)

    # card art, faded in from the left (Hearthstone style)
    strip = art_strip(card)
    if strip is not None:
        s = strip if not gone else Image.eval(strip, lambda v: v // 4)
        mask = Image.linear_gradient("L").rotate(90).resize(s.size)    # dark on the left -> full on the right
        mask = Image.eval(mask, lambda v: min(255, int(v * 1.5)))
        img.paste(s, (WIDTH - 4 - 26 - s.size[0], y + 1), mask)

    # stage stripe on the left edge (teal for generated cards)
    mark = GENERATED
    d.rectangle([4, y, 7, y + ROW - 1], fill=mark if generated else (colour if not gone else DIM))

    # chip score badge, in the stage colour
    badge = [12, y + 4, 40, y + ROW - 5]
    d.rounded_rectangle(badge, radius=5, fill=colour if not gone else (55, 52, 70))
    score = score_text(card.get("chips", 0))
    d.text(((badge[0] + badge[2]) / 2 - d.textlength(score, font=MID) / 2, y + 4), score,
           font=MID, fill=DARK_TEXT if not gone else DIM)

    # name with a dark outline so it's readable over the art
    x = 46
    if generated:
        sparkle(d, x + 5, y + ROW / 2, 6, mark)
        x += 14
    name = fit(d, card["name"], MID, WIDTH - 34 - x)
    d.text((x, y + 4), name, font=MID, fill=TEXT if not gone else DIM, stroke_width=2, stroke_fill=(0, 0, 0))

    # count box on the right
    d.rectangle([WIDTH - 28, y + 3, WIDTH - 7, y + ROW - 4], fill=(14, 12, 22))
    d.text((WIDTH - 17 - d.textlength(count_text, font=MID) / 2, y + 4), count_text, font=MID,
           fill=GOLD if not gone else DIM)


def group_by_stage(counter):
    """{card_id: n} -> {stage: [(card, n), ...]} sorted by chip score, then name."""
    groups = {stage: [] for stage in STAGES}
    for card_id, n in counter.items():
        card = card_info(card_id)
        groups.setdefault(card["type"], []).append((card, n))
    for rows in groups.values():
        rows.sort(key=lambda cn: ((-1 if SORT_HIGH_FIRST else 1) * cn[0].get("chips", 0), cn[0]["name"]))
    return groups


# ---------- the whole panel ----------

def render(game):
    """Draw everything for this Game. Returns a Pillow image."""
    # Work out the height first: draw on a tall canvas, then cut it to size.
    img = Image.new("RGB", (WIDTH, 3000), BG)
    d = ImageDraw.Draw(img)

    # Title bar
    title = (game.deck_name if game and game.deck_name else "Showdown tracker")
    d.rectangle([0, 0, WIDTH, 26], fill=PANEL)
    d.text((8, 5), fit(d, title, BIG, WIDTH - 40), font=BIG, fill=TEXT)
    d.line([WIDTH - 20, 8, WIDTH - 10, 18], fill=DIM, width=2)     # close button (an X)
    d.line([WIDTH - 20, 18, WIDTH - 10, 8], fill=DIM, width=2)
    y = 32

    if game is None:
        d.text((8, y), "Waiting for a match...", font=SMALL, fill=DIM)
        return img.crop((0, 0, WIDTH, y + 22))

    me, opp = game.me, game.opponent()

    # Hand, stage and chips
    left = " · ".join(x for x in (game.hand_number, game.stage) if x) or "Match found"
    d.text((8, y), left, font=SMALL, fill=DIM)
    if game.chips and me:
        right = f"{game.chips.get(me, '?')} – {game.chips.get(opp, '?')}   pot {game.chips.get('Pot', '?')}"
        d.text((WIDTH - 8 - d.textlength(right, font=SMALL), y), right, font=SMALL, fill=DIM)
    y += 18

    # Result banner at the end
    if game.ended:
        word = {"win": "VICTORY", "loss": "DEFEAT"}.get(game.result_word(), "MATCH OVER")
        colour = {"win": GREEN, "loss": LOSS}.get(game.result_word(), GOLD)
        d.rounded_rectangle([4, y, WIDTH - 4, y + 24], radius=5, fill=colour)
        d.text((WIDTH / 2 - d.textlength(word, font=BIG) / 2, y + 3), word, font=BIG, fill=DARK_TEXT)
        y += 30
        status = getattr(game, "online_status", "")     # "Saved to website ✓" (see tracker.py)
        if status:
            d.text((8, y), fit(d, status, SMALL, WIDTH - 16), font=SMALL,
                   fill=GREEN if "✓" in status else (GOLD if "Saving" in status else LOSS))
            y += 16

    # ----- my side -----
    if me:
        if game.deck:
            total = sum(game.deck.values())
            # exact count from the game when we saw the match start, else from the list
            left_total = game.cards_in_deck(me) or sum(game.cards_left(c) for c in game.deck)
            d.text((8, y), f"IN DECK   {left_total}/{total}", font=MID, fill=GREEN)
            y += 20
            groups = group_by_stage(game.deck)
            for stage in STAGES:
                rows = groups.get(stage) or []
                if not rows:
                    continue
                for card, copies in rows:
                    left_n = game.cards_left(card["id"])
                    card_row(img, d, y, card, str(left_n), gone=left_n == 0)
                    y += ROW + 2
                y += STAGE_GAP
            # cards I played that aren't in my deck list (deck list out of date?)
            extra = {c: n for c, n in game.played[me].items() if c not in game.deck}
            if extra:
                y = played_sections(img, d, y, extra, header="Not in deck list")
        else:
            d.text((8, y), "MY CARDS PLAYED", font=MID, fill=GREEN)
            y += 20
            if game.played[me]:
                y = played_sections(img, d, y, game.played[me])
            else:
                d.text((8, y), "nothing yet", font=SMALL, fill=DIM)
                y += 18
        # My own generated cards aren't shown (they'd make the panel too tall).
        # They're still in log.txt and summary.json.

    # ----- opponent -----
    if opp:
        y += 6
        d.rectangle([0, y, WIDTH, y + 24], fill=PANEL)
        d.text((8, y + 4), fit(d, game.name(opp).upper(), MID, 140), font=MID, fill=OPP)
        in_hand = game.cards_in_hand(opp) or game.opp_hand_size
        if in_hand is not None:
            in_deck = game.cards_in_deck(opp)
            hand = f"{in_hand} in hand" + (f" · {in_deck} in deck" if in_deck else "")
            x = WIDTH - 8 - d.textlength(hand, font=SMALL)
            d.text((x, y + 6), hand, font=SMALL, fill=DIM)
            # how many of the cards they hold were generated: "✦2"
            held = len(game.opp_pool)
            if held:
                count = str(held)
                x -= 10 + d.textlength(count, font=SMALL)
                sparkle(d, x, y + 12, 5, GENERATED)
                d.text((x + 7, y + 6), count, font=SMALL, fill=GENERATED)
        y += 26
        classes = game.deck_classes.get(opp)
        if classes:
            d.text((8, y), " / ".join(classes), font=SMALL, fill=DIM)
            y += 16
        if game.played[opp]:
            y = played_sections(img, d, y + 2, game.played[opp])
        elif not game.generated[opp]:
            d.text((8, y + 2), "nothing played yet", font=SMALL, fill=DIM)
            y += 20
        y = generated_section(img, d, y, game.generated[opp])

    return img.crop((0, 0, WIDTH, y + 6))


def played_sections(img, d, y, counter, header=None):
    """Cards played, by stage. The count box shows how many times."""
    if header:
        d.text((8, y), header, font=SMALL, fill=DIM)
        y += 16
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


# ---------- the window ----------

class Overlay:
    def __init__(self, on_quit):
        self.on_quit = on_quit
        self.closed = False
        self._shown = None

        self.root = tk.Tk()
        self.root.title("Showdown tracker")
        self.root.overrideredirect(True)          # no Windows title bar
        self.root.attributes("-topmost", True)    # stay above the browser
        self.root.attributes("-alpha", 0.95)
        self.root.geometry("+20+120")
        self.label = tk.Label(self.root, bd=0, bg="#12101c")
        self.label.pack()

        self.label.bind("<ButtonPress-1>", self._press)
        self.label.bind("<B1-Motion>", self._move)
        self.label.bind("<ButtonRelease-1>", self._release)
        self._draw(None)

    # Drag to move; a click (no drag) on the X closes
    def _press(self, event):
        self._start = (event.x_root, event.y_root)
        self._dx = event.x_root - self.root.winfo_x()
        self._dy = event.y_root - self.root.winfo_y()

    def _move(self, event):
        self.root.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def _release(self, event):
        moved = abs(event.x_root - self._start[0]) + abs(event.y_root - self._start[1])
        if moved < 4 and event.x > WIDTH - 28 and event.y < 26:
            self.quit()

    def quit(self):
        if not self.closed:
            self.closed = True
            self.root.destroy()
            self.on_quit()

    def update_window(self):
        """Let tkinter draw and handle clicks. Called often by tracker.py."""
        if not self.closed:
            self.root.update()

    def _draw(self, game):
        # Python note: keep a reference to the PhotoImage, or tkinter shows nothing
        self._photo = ImageTk.PhotoImage(render(game))
        self.label.configure(image=self._photo)

    def show(self, game):
        """Redraw if something changed (new event, or a card picture finished downloading)."""
        if self.closed:
            return
        key = (id(game), game.version if game else None, art_version[0])
        if key != self._shown:
            self._shown = key
            self._draw(game)
