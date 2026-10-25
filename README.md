# Showdown tracker (prototype)

A deck tracker for **Showdown** (poker + action cards, https://play.showdown.game).

Unlike the Origins tracker, it does **not** use screenshots. It reads the game's own
network messages (the same ones you see in F12 > Network), so card names are exact.
The server never sends the opponent's hidden cards, so the tracker only knows what you can see.

## Files
| File | What it does |
|---|---|
| `tracker.py` | Starts Edge, listens to the game, saves the files. **Run this one.** |
| `game_state.py` | Works out what happened from the server messages. |
| `overlay.py` | The always-on-top deck tracker window. |
| `cards.py` | Loads the card list and `deck.txt`. |
| `cards.json` | All action cards: name, stage, chip score, class, art link. |
| `update_cards.py` | Rebuilds `cards.json` from the game. Run it when the game adds cards. |
| `deck.txt` | Your deck (optional). |
| `website.py` | Saves finished matches to the website. |
| `docs/` | The website (GitHub Pages). |
| `art/` | Card pictures, downloaded automatically the first time they're shown. |
| `games/` | One folder per match: `log.txt`, `summary.json`, `raw.jsonl`. |
| `browser-profile/` | The tracker's own Edge profile (your Showdown login). **Never share or commit it.** |

## First-time setup
1. In VS Code, open the terminal: menu **Terminal > New Terminal**.
2. Go to this folder:
   ```
   cd C:\Users\Brainiac\Documents\GitHub\showdown-tracker
   ```
3. Install Playwright (it was already installed on 2026-10-24, so this should say "Requirement already satisfied"):
   ```
   python -m pip install playwright
   ```
   You do **not** need `playwright install`: the tracker uses your own Edge.

## Every time you play
1. Run:
   ```
   python tracker.py
   ```
2. A **new Edge window** opens on Showdown. It uses its own profile, so the first time
   you have to **log in to Showdown** in that window. After that it remembers you.
   - Play in **this** window, not your normal Edge. The tracker can only see this one.
3. The overlay appears at the top left. Drag it where you like.

## The overlay
- Cards are grouped by stage, in this order and colour:
  **Universal** (grey), **Pre-flop** (blue), **Flop** (yellow), **River** (red).
- Inside a stage, cards are sorted by chip score, lowest first (set `SORT_HIGH_FIRST = True`
  at the top of `overlay.py` for highest first). The badge on the left shows the score.
- **My side**: your whole deck at the start of the match. A card is taken off when you
  **draw** it (greyed out at 0), and put back if it returns to your deck (e.g. Mulligan).
  "IN DECK 21/30" is the exact count from the game.

## Deck import (automatic)
1. With the tracker running, open the game's **deck screen** once (Change Deck / Deck Builder).
   The tracker saves your decks in `games\decks\Decks_compact.json` and prints
   `Your decks: Theory Craft, Mill, ...`. Do it again after you change a deck.
2. When a match starts, the tracker picks the deck with the same 2 classes as the match
   (e.g. Inventor / Rebel = Theory Craft). If two decks share classes, it picks the one that
   holds your starting hand and played cards.
3. `deck.txt` is only needed to force a different list: if it has cards, it's used instead.
- **Opponent**: their name, deck classes, cards in hand, and every card they've played.
- **✦ Generated** (teal, opponent only; your own generated cards are hidden to keep the panel short):
  cards made during the match by another card. The game hides that mark on the opponent's cards,
  so the tracker works it out:
  - a card from outside their 2 classes is **generated** (bright ✦)
  - cards that land in their hand without coming from their deck are counted: **✦2** next to
    "in hand" = they hold 2 generated cards
  - when they play a card one of those could be (e.g. a Flop card after Salvaged Goods), it's
    **maybe generated** (faded ✦). The generators and what they give are in `GENERATORS` in `cards.py`
  - **backcheck**: a deck holds at most 1 copy of a Rare and 2 of a Common. A 2nd Rare or 3rd Common
    is generated, and an earlier "maybe" copy is upgraded to generated
4. Play a match. The terminal prints the log as it happens, for example:
   ```
   [Hand 6 Flop] azhh: Check
   [Hand 6 Flop] Brainiac played Eye for an Eye
   ```
5. To stop: click **✕** on the overlay, or press **Ctrl+C** in the terminal.
   The Edge window stays open (close it yourself).

The match is saved in `games\<date>_<game id>\`:
- `log.txt`: the readable log
- `summary.json`: opponent, result, cards played by each side
- `raw.jsonl`: every server message, untouched. **Send me this one** when something looks wrong.

## Website (match history)
Site: https://brainiac1830.github.io/showdown-tracker/ (files in `docs\`).
It uses the **same Firebase project and Google sign-in as the Origins website**, so there's nothing
new to set up in Firebase. Showdown matches are kept apart in `users/<you>/showdown_matches`.

- **Home**: record, win rate, win rate per deck, per opponent class pair, opponent cards seen most.
- **Match History**: every match (search a player, filter by deck / result). Click a match for each
  hand's result, your starting hand, and the cards both of you played (stage colours, ✦ = generated).

### One-time setup
1. **Copy the tracker key.** Copy `tracker_key.txt` from
   `C:\Users\Brainiac\Documents\GitHub\origins-tracker\tracker-app\` into this folder
   (same Google account and database, so the same key works). Never commit or share it.
2. **Test the link** (reads only):
   ```
   python website.py
   ```
   Expected: `Linked ✓  (your email) - 0 Showdown matches online`
3. **Upload your earlier matches** (each one only once, finished matches only):
   ```
   python website.py --upload-all
   ```
4. **Put the site on GitHub** (VS Code):
   - Open this folder in VS Code. Left bar: **Source Control** > **Publish to GitHub** >
     choose **public** (GitHub Pages is free for public repositories) > name it `showdown-tracker`.
     Check the file list first: `games`, `browser-profile`, `art` and `tracker_key.txt` must NOT be in it.
   - On github.com, open the repository > **Settings** > **Pages** > Source: **Deploy from a branch**,
     Branch: **main**, folder: **/docs** > **Save**. About 1 minute later the site is live.

### Every match after that
When a match ends, the tracker saves it to the website by itself. The overlay shows
**Saved to website ✓** under VICTORY / DEFEAT. (Turn it off with `SAVE_ONLINE = False` in `tracker.py`.)

## Testing without playing
Replays a saved file through the same code:
```
python tracker.py --replay C:\Users\Brainiac\Downloads\logs.json
```
It works with a DevTools HAR export, `/catchup` answers pasted one per line, or a `raw.jsonl`
from `games\`. Add `--no-overlay` to only print the log.

## Settings (top of tracker.py)
- `BROWSER_PATH`: leave `None` to find Edge automatically, or put the full path to Chrome.
- `DEBUG_PORT`: 9222. Change it if another program uses that port.
- `SHOW_OVERLAY`: `False` to never show the window.

## What the game sends (learned from the 2026-10-24 test match)
- **End of match**: an `EndGame` event with the winner. Each poker hand ends with `EndHand`
  (who won, e.g. "Straight Flush vs Flush").
- **Snapshot** (when the page loads): starting hand, both players' deck classes
  (e.g. Rebel / Inventor) and the game log so far, so joining halfway works.
- The status `result` number is 3 before the start, 2 while playing, 0 after the end.
- **Your deck list is not in the match messages** (only "26 hidden cards"). The tracker saves the
  deck screen's messages in `games\decks\` so a deck import can be built from them later.
- `summary.json` is rewritten after every update, so it's kept even if you close the terminal.

## Still unknown
- **Fold** entries are logged as one line; their details aren't read yet.
- Draws during the match aren't listed separately.
- Whether the game shows us the "Generated" mark on the **opponent's** cards (the class rule is the backup).

## Safety
- `browser-profile/` and `games/` are in `.gitignore`. Don't remove those lines.
- While the tracker's Edge is open, programs on **your own PC** can control it through port 9222.
  Close that Edge window when you're done playing.
- Check Showdown's rules about trackers, since real money can be involved.
