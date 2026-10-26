# Showdown tracker (prototype)

> **New here? Read [SETUP.md](SETUP.md)**: install in 10 minutes, then double-click `start.bat`.
> This README is the detailed notes for the person maintaining the tracker.

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
Two windows (drag each one where you like; the places are remembered in `overlay_settings.json`):
- **Left: my deck.** **Right: the opponent.** When you **spectate**, left = player 1 and right = player 2.
- **LIKELY CARDS** (right window, under what they played): the cards this player played in your
  **earlier matches with the same 2 classes** (played against them or watched).
  - It is **not their decklist**: % = in how many of those matches they played the card. We only
    see played cards (about 10 of 30 per match), so a card they always run can still show 40-60%.
  - Predicted rows are faded with a dashed stripe and the % in the box. Once they play the card,
    it moves up to the normal list.
  - **Click the LIKELY CARDS title to hide / show it.** Keep it hidden in real-money matches until
    Showdown confirms trackers are allowed (it's the kind of feature poker sites ban most).

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
  cards made during the match by another card. The game shows these with a **lighter border**,
  and sends that mark to both players, so the tracker reads it for the opponent's cards too.
  **✦2** next to "in hand" = they hold 2 generated cards. Safety net: a deck holds at most
  1 copy of a Rare and 2 of a Common, so a 2nd Rare or 3rd Common is always generated.
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

## Tournament mode
Decks are locked during a tournament, so every card a player plays in their tournament matches IS in
their deck. Scout your future opponents by watching their matches:
1. Click the **trophy** in the left overlay window (top bar) > type or pick the tournament name > **Start**.
   A gold **TOURNAMENT** banner shows on both windows. (The name list has earlier names, so everyone uses
   the same spelling; capital letters and extra spaces don't matter.)
2. Every match you **watch or play** while it's on is saved with that tournament name, and shared.
3. When you play someone from that tournament, the right window shows **TOURNAMENT DECK**: every card
   seen from them in that tournament (by you or anyone who shared it), with the copies they still have
   this match. LIKELY CARDS below it only guesses the rest.
4. Click the trophy again > **Stop tournament mode** when the tournament is over.
The website's **Tournaments** page lists each tournament's players with their known deck ("14/30 known").
**Automatic detection:** when you open a tournament in the game (e.g. to spectate a table), the game sends
its bracket. The tracker saves it in `games\tournaments\` and from then on recognises that tournament's
matches by itself (by game id, or by the two players for games 2 and 3 of a best-of-3), using the
**official name**, e.g. *Daily Small Stakes ($10 GTD) BO3 #9*. The banner then says **auto**. Only tournaments
with locked decks (`deckType: PerTournament`) count. The trophy name is only used when nothing is detected.
Every game id seen in a bracket is remembered in `games\tournaments\known_games.json`.

## Website (match history)
Site: https://brainiac1830.github.io/showdown-tracker/ (files in `docs\`).
**Anyone can sign in with Google.** Each person's match history is private; what their trackers
saw other players play is **shared** (Players page + overlay "likely cards").

- **Home**: record, win rate, win rate per deck, per opponent class pair, opponent cards seen most.
- **Match History**: every match (search a player, filter by deck / result; "Watched matches" = spectated).
- **Players**: everyone you played or watched + players others shared. Per class pair: likely cards with %.
- **Tournaments**: per tournament, each player's known deck (decks are locked in a tournament).
- **Cards**: win rate when a card was played. Toggles: **Per hand** (won that hand; + average chip swing)
  or **Per game** (won the match), and **My plays** or **Everyone** (opponents + watched matches too).
  Deck filter with automatic **versions**: keep the same deck name when you change a card; each different
  card list becomes v1, v2, v3... Rows with fewer than 20 hands/games are greyed out (not enough data).
  It shows what happened when a card was played, not proof the card caused it.
  Matches saved before 2026-10-25 get hand data with `python website.py --upload-all --replace`
  (their deck list is the current one, so old matches all count as the current version).
- **Tools**: create your tracker key, and steps for other players to get the tracker.

### Data (Firebase project "showdown-tracker")
- `users/<uid>/showdown_matches/<game id>`: your matches (only you can read them).
- `showdown_sightings/<game id>_<player>`: shared. One per player per match: name, classes, cards played.
  Everyone signed in can read them and add new ones; only the one who added one can change it.
  Your own deck is never shared by your tracker. Set `SHARE_PLAYERS = False` in `website.py` to stop sharing.
- Rules: `firestore.rules` (paste into Firebase > Firestore Database > Rules > Publish).

### One-time setup: the separate Firebase project
Until this is done, the site still uses the Origins Firebase project (sign-in limited to the Origins player list,
and sharing doesn't work yet).
1. Go to https://console.firebase.google.com > **Create a project** > name `showdown-tracker` >
   Google Analytics **off** > **Create**.
2. Left menu **Build > Authentication** > **Get started** > **Google** > **Enable** > pick your email
   as support email > **Save**. Then **Settings** tab > **Authorized domains** > **Add domain** >
   `brainiac1830.github.io`.
3. **Build > Firestore Database** > **Create database** > location: one close to you
   (e.g. `northamerica-northeast1 (Montréal)`) > **Start in production mode** > **Create**.
   Then the **Rules** tab: delete everything, paste all of `firestore.rules`, **Publish**.
4. **Project settings** (gear, top left) > **General** > **Your apps** > the **</>** (Web) button >
   nickname `showdown-site` > **Register app** (no Hosting). Copy the 7 values of `firebaseConfig`
   into `docs\firebase-config.js` (or paste them in the chat and ask Claude to do it).
5. Commit and push (VS Code Source Control). Wait 1 minute, open the site, **Ctrl+F5**, sign in.
6. **Tools** page > **Create key** > **Copy**, and replace everything in `tracker_key.txt` with it
   (the old key belongs to the Origins project).
7. Move your matches and share what you've seen:
   ```
   python website.py --upload-all
   ```
   Expected: one "saved ... - shared N player(s)" line per match, then `Linked ✓ ... N Showdown matches online`
   and `Shared player data: ...`.

### Leaving a match before the end
What you saw still counts. When the next match starts (or you close the tracker):
- a **watched** match is saved as "Watched · left early", and both players are shared;
- **your own** match isn't saved (no result, so your stats don't change), but your opponent is shared.
Their cards count for LIKELY CARDS and tournament decks. If you come back and the match finishes,
the full version replaces the partial one. `python website.py --upload-all` does the same for old folders.

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
- **Browser:** found by itself (`browsers.py`): any Chrome-type browser (Edge, Chrome, Brave, Vivaldi,
  Opera, Chromium), wherever it's installed. Firefox and Safari can't be used, but that doesn't matter: the
  tracker always opens its own window. If no Chrome-type browser exists at all, it downloads Playwright's own
  Chromium once (~150 MB). To pick one, put its full path in a file `browser_path.txt` next to `tracker.py`.
  `python browsers.py` shows which one will be used.
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
