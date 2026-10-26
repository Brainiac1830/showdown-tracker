# tracker.py
# Showdown deck tracker (prototype).
#
# How it works, in plain English:
#   1. It starts Edge (or Chrome) with a "debugging port" turned on and its own
#      profile folder (browser-profile/). You log in to Showdown there once.
#   2. Python connects to that port with Playwright and listens to the game's
#      network messages (no screenshots, no picture recognition).
#   3. Every /catchup answer from the server goes to game_state.py, which works
#      out what happened. The overlay window shows it.
#   4. Each match gets a folder in games/ with:
#        raw.jsonl     every server answer, untouched (for fixing the tracker later)
#        log.txt       readable log ("azhh played Silver Bullet")
#        summary.json  the result and cards played, written at the end
#
# Run it:            python tracker.py
# Test on a file:    python tracker.py --replay C:\Users\Brainiac\Downloads\logs.json
# No overlay:        add --no-overlay

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from cards import load_saved_decks, read_deck_file
import profiles
import website
from browsers import find_browser
from tournaments import TournamentIndex
from game_state import Game

# ----------------------------- settings -----------------------------

HERE = Path(__file__).resolve().parent
GAME_URL = "https://play.showdown.game"
DEBUG_PORT = 9222                       # the port Python uses to talk to the browser
PROFILE_DIR = HERE / "browser-profile"  # the tracker's own browser profile (your Showdown login lives here)
SAVE_FOLDER = HERE / "games"
DECK_FILE = HERE / "deck.txt"
# Your decks, saved automatically when you open the game's deck screen
SAVED_DECKS_FILE = SAVE_FOLDER / "decks" / "Decks_compact.json"
# Everyone's shared player sightings, downloaded from the website (see website.py)
SHARED_FILE = SAVE_FOLDER / "shared_sightings.json"
# Tournament mode: the tournament you're in (set with the trophy button on the overlay)
TOURNAMENT_FILE = HERE / "tournament_mode.json"
# How often to download what other players shared (seconds)
SYNC_EVERY = 120
# The way matches are read and saved. RAISE THIS NUMBER when that changes (e.g. a new
# kind of data in the records): every PC then re-saves its old matches once, by itself,
# from their raw.jsonl, the next time the tracker starts. History:
#   1 = before 2026-10-25 evening
#   2 = hand log + deck list (Cards page), discarded cards, classes worked out from cards
#   3 = ranks + bot flag, hands ended by a card (Windfall), chips per hand measured after each hand
#   4 = stolen cards (Thought Police...) count in the victim's deck, not as the thief's plays
#   5 = cards discarded straight from the deck (Drought) count as seen
DATA_VERSION = 5
DATA_STATE_FILE = SAVE_FOLDER / "data_version.json"
SHOW_OVERLAY = True
# Save each finished match to your website by itself (needs tracker_key.txt, see website.py)
SAVE_ONLINE = True

# Which browser opens the game: see browsers.py. To choose one, put its full path in
# browser_path.txt next to this file, e.g.  C:\Program Files\Google\Chrome\Application\chrome.exe
BROWSER_FILE = HERE / "browser_path.txt"


# ----------------------------- saving -----------------------------

class Recorder:
    """Keeps the current Game, and writes its files in games/<folder>/."""

    def __init__(self, folder_prefix="", echo=True, save_online=False):
        self.folder_prefix = folder_prefix
        self.echo = echo              # also print the readable log in the terminal
        self.save_online = save_online and website.is_linked()
        self.deck_name, self.deck, unknown = read_deck_file(DECK_FILE)
        if unknown:
            print(f"deck.txt: these cards weren't found in cards.json: {', '.join(unknown)}")
        self.saved_decks = []
        self.game = None
        self.reload_saved_decks()
        self.folder = None
        self._lines_written = 0
        # Earlier finished matches (games/*/record.json), for the "likely cards" prediction
        self.records = []
        self.shared = profiles.load_shared(SHARED_FILE)      # last download, works offline
        self._syncing = False
        # Shown in the overlay when something's wrong (no key = no shared data from others)
        self.shared_status = "shared: ..." if self.save_online else "not linked: no shared data"
        self.tournament = load_tournament_mode()        # the manual trophy name
        # Tournament brackets seen in the game: detect tournament matches by themselves
        self.tournament_index = TournamentIndex(SAVE_FOLDER / "tournaments")
        if not folder_prefix:
            backfill_records()
            self.records = profiles.load_records(SAVE_FOLDER)
            if self.save_online:
                self.sync_shared()
            self.resave_if_outdated()

    def predict(self, name, classes, game_id):
        """What this player played in earlier matches with these classes (see profiles.py)."""
        return profiles.predict(self.records, name, classes, exclude_game=game_id, sightings=self.shared)

    # ----- tournament mode (the overlay's trophy button calls these) -----

    def tournament_message(self, body):
        """A tournament message from the game: learn its bracket, and check the
        current match again (the bracket can arrive after the match started)."""
        if self.tournament_index.update(body) and self.game is not None:
            if self.game.detect_tournament(self.tournament_index):
                self._write_new_log_lines()
                self.save_summary(quiet=True)      # (rewrites record.json if the match is over)

    def set_tournament(self, name):
        """Turn tournament mode on (a name) or off (None). The match being played or
        watched right now counts too, if it isn't over yet."""
        name = " ".join((name or "").split())[:60] or None
        self.tournament = name
        save_tournament_mode(name)
        if self.game is not None and not self.game.ended and not self.game.tournament_auto:
            self.game.tournament = name     # (a detected tournament stays as it is)
            self.game.version += 1
        print(f"Tournament mode: {name}" if name else "Tournament mode: off")

    def tournament_names(self):
        return profiles.tournament_names(self.records, self.shared)

    def tournament_deck(self, name, game_id, tournament=None):
        """What's known of this player's deck in this tournament (None if nothing).
        tournament: the match's tournament (detected or manual); default = the trophy name."""
        tournament = tournament or self.tournament
        if not tournament:
            return None
        return profiles.tournament_deck(self.records, name, tournament, exclude_game=game_id,
                                        sightings=self.shared)

    def resave_if_outdated(self):
        """Matches saved by an older tracker (see DATA_VERSION): re-save them once, in the
        background, from their raw.jsonl. Online too if linked (your matches + what you shared).
        Only the matches that exist NOW: the one you're about to play isn't touched."""
        state = load_data_state()
        outdated = state.get("version", 1) < DATA_VERSION
        not_online = self.save_online and not state.get("online")
        existing = {raw.parent.name for raw in SAVE_FOLDER.glob("*/raw.jsonl")
                    if not raw.parent.name.startswith(("replay_", "test_"))}
        if not existing or not (outdated or not_online):
            if not existing:
                save_data_state(online=self.save_online)     # nothing to re-save
            return
        print(f"Updating your {len(existing)} saved matches to the newest format (in the background)...")

        def work():
            try:
                if self.save_online:
                    done = website.upload_all(replace=True, only=existing, quiet=True)
                    print(f"  ... done: {done} matches re-saved and shared again.")
                else:
                    for raw in SAVE_FOLDER.glob("*/raw.jsonl"):
                        if raw.parent.name in existing:
                            game = replay_game(raw)
                            if game is not None and (game.ended or game.anything_seen()):
                                save_record(raw.parent, game.website_record())
                    print("  ... done (on this PC only: no tracker_key.txt).")
                save_data_state(online=self.save_online)
                self.records = profiles.load_records(SAVE_FOLDER)     # predictions use the new data
                if self.game is not None:
                    self.game.version += 1
            except Exception as error:
                print(f"  ... couldn't update the old matches ({error}). It will try again next time.")
        threading.Thread(target=work, daemon=True).start()

    def sync_shared(self):
        """Download new shared sightings, in the background (one download at a time).
        Called at start, when a match starts or ends, and every few minutes."""
        if not self.save_online or self._syncing:
            return
        self._syncing = True

        def work():
            try:
                before = len(self.shared)
                self.shared = website.sync_sightings(SHARED_FILE)
                self.shared_status = f"shared: {len(self.shared)}"
                if len(self.shared) != before:
                    print(f"Shared player data: {len(self.shared)} sightings")
                    if self.game is not None:
                        self.game.version += 1      # redraw the prediction
            except Exception as error:
                self.shared_status = "shared data: download failed"
                print(f"(Couldn't download the shared player data: {error})")
            finally:
                self._syncing = False
        threading.Thread(target=work, daemon=True).start()

    def _start_game(self, game_id):
        self.finish()  # save the previous match if there was one
        self.game = Game(game_id, self.deck, self.deck_name, self.saved_decks)
        self.game.tournament = self.tournament
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.folder = SAVE_FOLDER / f"{self.folder_prefix}{stamp}_{game_id[:8]}"
        self.folder.mkdir(parents=True, exist_ok=True)
        self._lines_written = 0
        print(f"\nNew match {game_id}  ->  saving in {self.folder}")
        self.sync_shared()      # get what others shared since last time, before predictions are needed

    def _write_raw(self, kind, data):
        with open(self.folder / "raw.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "kind": kind, "data": data}) + "\n")

    def _write_new_log_lines(self):
        new = self.game.log_lines[self._lines_written:]
        if not new:
            return
        with open(self.folder / "log.txt", "a", encoding="utf-8") as f:
            for line in new:
                f.write(line + "\n")
                if self.echo:
                    print(line)
        self._lines_written = len(self.game.log_lines)

    def handle_catchup(self, body):
        game_id = (body.get("status") or {}).get("gameId")
        if not game_id:
            return
        if self.game is None or game_id != self.game.game_id:
            self._start_game(game_id)
        self._write_raw("catchup", body)
        was_ended = self.game.ended
        self.game.feed_catchup(body)
        self.game.detect_tournament(self.tournament_index)
        self._write_new_log_lines()
        # Saved after every update, so closing the terminal early still keeps it
        self.save_summary(quiet=was_ended or not self.game.ended)
        if self.game.ended and not was_ended and self.save_online:
            self.upload(self.game)

    def upload(self, game):
        """Save the finished match to the website, in the background
        (a web request can take a second; the overlay must not freeze)."""
        record = game.website_record()
        game.online_status = "Saving to website..."
        game.version += 1

        def work():
            try:
                # replace=True: if I left this match earlier and came back, the full
                # version replaces the partial one saved when I left
                website.save_match(record, replace=True)
                game.online_status = "Saved to website ✓"
                print(f"{game.online_status} ({website.share_sightings(record, replace=True)})")
            except Exception as error:
                game.online_status = f"Not saved online: {error}"
                print(game.online_status)
            game.version += 1     # the overlay redraws
            self.sync_shared()    # pick up what others shared meanwhile

        threading.Thread(target=work, daemon=True).start()

    def reload_saved_decks(self):
        """Read the decks the game sent (when you opened the deck screen)."""
        self.saved_decks = load_saved_decks(SAVED_DECKS_FILE)
        if self.saved_decks:
            print(f"Your decks: {', '.join(d['name'] for d in self.saved_decks)}")
        if self.game is not None:
            self.game.saved_decks = self.saved_decks
            self.game.pick_deck()

    def handle_my_move(self, game_id, move):
        if self.game is None or game_id != self.game.game_id:
            return  # the server answer for this game will start it
        self._write_raw("my_move", move)
        self.game.feed_my_move(move)
        self._write_new_log_lines()

    def save_summary(self, quiet=False):
        with open(self.folder / "summary.json", "w", encoding="utf-8") as f:
            json.dump(self.game.summary(), f, indent=2, ensure_ascii=False)
        if self.game.ended:
            # record.json = what the website gets; also what player profiles are built from
            record = self.game.website_record()
            save_record(self.folder, record)
            self.records = [r for r in self.records if r.get("gameId") != record["gameId"]] + [record]
        if not quiet:
            print(f"Saved {self.folder / 'summary.json'}  (result: {self.game.result_word()})")

    def finish(self, wait=False):
        """Save whatever we have (called when a new match starts and when quitting).
        A match left before the end still counts for what was seen:
          - watched match: saved online as "left early", both players shared
          - my own match: only the opponent is shared (no result, so my stats don't change)
        wait=True (quitting): upload now instead of in the background."""
        if self.game is None:
            return
        self._write_new_log_lines()
        self.save_summary()
        game = self.game
        if game.ended or not game.anything_seen():
            return
        record = game.website_record()          # has "leftEarly": True
        save_record(self.folder, record)          # local copy: counts for predictions
        self.records = [r for r in self.records if r.get("gameId") != record["gameId"]] + [record]
        print(f"Left before the end: {self.folder.name} kept for what was seen")
        if self.save_online:
            self.upload_left_early(record, wait)

    def upload_left_early(self, record, wait=False):
        def work():
            try:
                if record.get("spectated"):
                    website.save_match(record, replace=True)
                print(f"  (left early: {website.share_sightings(record, replace=True)})")
            except Exception as error:
                print(f"  (left early, not saved online: {error})")
        if wait:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()


def load_data_state():
    """{"version": 2, "online": true}: how the saved matches on this PC were last saved."""
    try:
        return json.loads(DATA_STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_data_state(online):
    SAVE_FOLDER.mkdir(parents=True, exist_ok=True)
    DATA_STATE_FILE.write_text(json.dumps({"version": DATA_VERSION, "online": bool(online)}), encoding="utf-8")


def load_tournament_mode():
    try:
        return json.loads(TOURNAMENT_FILE.read_text(encoding="utf-8")).get("name") or None
    except (OSError, json.JSONDecodeError):
        return None


def save_tournament_mode(name):
    TOURNAMENT_FILE.write_text(json.dumps({"name": name}), encoding="utf-8")


def save_record(folder, record):
    with open(Path(folder) / "record.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1, ensure_ascii=False)


def backfill_records():
    """Matches saved before record.json existed: rebuild it from raw.jsonl (once)."""
    for raw in sorted(SAVE_FOLDER.glob("*/raw.jsonl")):
        folder = raw.parent
        if folder.name.startswith(("replay_", "test_")) or (folder / "record.json").exists():
            continue
        game = replay_game(raw)
        # finished, or left early with cards seen (those still count for predictions)
        if game is not None and (game.ended or game.anything_seen()):
            save_record(folder, game.website_record())


def replay_game(raw_file):
    """Rebuild a Game from a saved raw.jsonl, without writing any files.
    (Used by  python website.py --upload-all.)"""
    deck_name, deck, unknown = read_deck_file(DECK_FILE)
    index = TournamentIndex(SAVE_FOLDER / "tournaments")
    game = None
    for kind, data in read_replay_file(raw_file):
        if kind == "catchup":
            game_id = (data.get("status") or {}).get("gameId")
            if game is None and game_id:
                game = Game(game_id, deck, deck_name, load_saved_decks(SAVED_DECKS_FILE))
            if game is not None and game_id == game.game_id:
                game.feed_catchup(data)
        elif game is not None:
            game.feed_my_move(data[1])
    if game is not None:
        game.detect_tournament(index)
        if not game.tournament_auto:
            # tournament mode was on when it was recorded: keep that name
            try:
                saved = json.loads((Path(raw_file).parent / "record.json").read_text(encoding="utf-8"))
                game.tournament = saved.get("tournament") or None
            except (OSError, json.JSONDecodeError):
                pass
    return game


def save_deck_message(url, body, folder_name="decks"):
    """Keep a game message: deck messages (deck screen, card list) in games/decks/,
    tournament messages in games/tournaments/. Newest copy per address."""
    folder = SAVE_FOLDER / folder_name
    folder.mkdir(parents=True, exist_ok=True)
    name = url.split("?")[0].split("/api/")[-1].replace("/", "_") or folder_name
    with open(folder / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump({"url": url.split("?")[0], "savedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "body": body}, f, indent=2, ensure_ascii=False)
    if folder_name == "decks":
        print(f"(saved deck message: {name})")


# Game messages that may say a match is part of a tournament. Saved (only when they
# mention "tournament") so the tracker can later learn to detect tournaments by itself.
TOURNAMENT_HINTS = ("tournament", "findmatch", "matchstatus", "getgamedetails", "lobbystatus")


# ----------------------------- live (browser) -----------------------------

def port_is_open(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def start_browser():
    """Start the browser with the debugging port, unless it's already running."""
    if port_is_open(DEBUG_PORT):
        print(f"A browser is already listening on port {DEBUG_PORT}, using it.")
        return
    browser = find_browser(BROWSER_FILE)
    if not browser:
        sys.exit("Could not find or download a browser to use. Put the full path of Edge, Chrome or Brave "
                 "in browser_path.txt (next to tracker.py) and try again.")
    PROFILE_DIR.mkdir(exist_ok=True)
    print(f"Starting {Path(browser).name} ...")
    subprocess.Popen([
        browser,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={PROFILE_DIR}",   # separate profile: needed for the port to work
        "--no-first-run",
        GAME_URL,
    ])


async def run_live(show_overlay):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        sys.exit("Playwright is missing. Run:  python -m pip install playwright")

    start_browser()
    recorder = Recorder(save_online=SAVE_ONLINE)
    if SAVE_ONLINE and not recorder.save_online:
        print("(Matches won't be saved to the website: no tracker_key.txt. See website.py.)")
    stop = asyncio.Event()

    # Python note: "async def" functions are run by asyncio; "await" waits
    # for something (like a network answer) without freezing the program.
    async def on_response(response):
        url = response.url
        if response.status != 200 or "showdown.game/api/" not in url:
            return
        is_catchup = "/catchup" in url
        is_deck = "deck" in url.lower()
        maybe_tournament = any(hint in url.lower() for hint in TOURNAMENT_HINTS)
        if not (is_catchup or is_deck or maybe_tournament):
            return
        try:
            body = await response.json()
        except Exception:
            return  # page changed before we could read it
        if is_catchup:
            recorder.handle_catchup(body)
        elif is_deck:
            save_deck_message(url, body)
            if url.split("?")[0].endswith("/Decks/compact"):
                recorder.reload_saved_decks()
        elif "tournament" in json.dumps(body).lower() or "tournament" in url.lower():
            save_deck_message(url, body, "tournaments")
            recorder.tournament_message(body)

    def on_request(request):
        # Your own moves:  POST https://prod.showdown.game/api/game/<gameId>/moves
        if request.method != "POST" or not request.url.endswith("/moves"):
            return
        try:
            move = (request.post_data_json or {}).get("move") or {}
        except Exception:
            return
        game_id = request.url.rstrip("/").split("/")[-2]
        recorder.handle_my_move(game_id, move)

    async with async_playwright() as pw:
        browser = None
        for attempt in range(40):  # wait up to ~20 s for the browser to start
            try:
                browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
                break
            except Exception:
                await asyncio.sleep(0.5)
        if browser is None:
            sys.exit(f"Could not connect to the browser on port {DEBUG_PORT}. "
                     "Close all Edge windows started by the tracker and try again.")

        browser.on("disconnected", lambda b: stop.set())
        for context in browser.contexts:
            context.on("response", on_response)
            context.on("request", on_request)
        print("Connected. Play a match in that browser window. (Ctrl+C or ✕ to stop)")

        overlay = None
        if show_overlay:
            from overlay import Overlay
            overlay = Overlay(on_quit=stop.set, predict=recorder.predict, recorder=recorder)

        next_sync = time.time() + SYNC_EVERY
        try:
            while not stop.is_set():
                if overlay:
                    overlay.show(recorder.game)
                    overlay.update_window()
                if time.time() > next_sync:      # what other players shared meanwhile
                    recorder.sync_shared()
                    next_sync = time.time() + SYNC_EVERY
                await asyncio.sleep(0.05)  # this pause is when browser messages get handled
        except KeyboardInterrupt:
            pass
        finally:
            recorder.finish(wait=True)     # quitting: upload a match left early before closing
            if overlay:
                overlay.quit()
        # We only disconnect: the browser window stays open.


# ----------------------------- replay (testing) -----------------------------

def read_replay_file(path):
    """Read a saved file and return a list of ("catchup", body) / ("my_move", (gameId, move)).

    Works with:
      - a DevTools HAR export (the whole Network tab)
      - one /catchup answer per line (copied from DevTools, any order)
      - a raw.jsonl written by this tracker
    """
    text = Path(path).read_text(encoding="utf-8")
    items = []

    try:
        whole = json.loads(text)       # works if the file is one JSON thing (HAR, or one answer)
    except json.JSONDecodeError:
        whole = None                   # several JSON lines

    if isinstance(whole, dict) and "log" in whole:
        entries = whole["log"]["entries"]
        entries.sort(key=lambda e: e.get("startedDateTime", ""))
        for e in entries:
            url, method = e["request"]["url"], e["request"]["method"]
            if method == "POST" and url.endswith("/moves"):
                post = (e["request"].get("postData") or {}).get("text") or "{}"
                items.append(("my_move", (url.split("/")[-2], json.loads(post).get("move") or {})))
            elif "/catchup" in url:
                body = (e["response"].get("content") or {}).get("text")
                if body:
                    items.append(("catchup", json.loads(body)))
        return items

    catchups = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        if "kind" in data and "data" in data:          # our own raw.jsonl
            if data["kind"] == "catchup":
                items.append(("catchup", data["data"]))
            elif data["kind"] == "my_move":
                items.append(("my_move", (None, data["data"])))
        else:
            catchups.append(data)
    # Lines copied from DevTools can be newest-first, so sort by move number.
    catchups.sort(key=lambda b: b.get("cursor") or 0)
    return items + [("catchup", b) for b in catchups]


def run_replay(path, show_overlay):
    recorder = Recorder(folder_prefix="replay_")
    recorder.records = profiles.load_records(SAVE_FOLDER)     # so the replay can show predictions
    for kind, data in read_replay_file(path):
        if kind == "catchup":
            recorder.handle_catchup(data)
        else:
            game_id, move = data
            recorder.handle_my_move(game_id or (recorder.game and recorder.game.game_id), move)
    recorder.finish()

    if recorder.game is None:
        print("No Showdown match found in that file.")
        return
    if show_overlay:
        from overlay import Overlay
        closed = []
        overlay = Overlay(on_quit=lambda: closed.append(True), predict=recorder.predict, recorder=recorder)
        print("Overlay open. Click ✕ on it to finish.")
        while not closed:
            overlay.show(recorder.game)
            overlay.update_window()
            time.sleep(0.05)


# ----------------------------- start -----------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Showdown deck tracker")
    parser.add_argument("--replay", help="read a saved log file instead of the live browser")
    parser.add_argument("--no-overlay", action="store_true", help="don't open the overlay window")
    args = parser.parse_args()
    show = SHOW_OVERLAY and not args.no_overlay

    if args.replay:
        run_replay(args.replay, show)
    else:
        try:
            asyncio.run(run_live(show))
        except KeyboardInterrupt:
            print("Stopped.")
