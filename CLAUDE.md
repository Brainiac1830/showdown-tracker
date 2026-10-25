# Showdown deck tracker + match history website

## About the owner (read first)
- Olivier is a **beginner coder who works in Python**. Give **extra detailed, step-by-step instructions** (where to click in VS Code, exact terminal commands, what output to expect).
- Windows PC, VS Code, PowerShell terminal, Python 3.14. Use `python -m pip ...`. Plays Showdown in **Edge**.
- Code style: lots of plain-English comments, simple names, "Python equivalent" notes in JS.
- Sister project: `..\origins-tracker` (Origins TCG tracker + website). This one copies its style and **shares its Firebase project**.

## What it is
Showdown (https://play.showdown.game): browser poker + action cards, 1v1, first to 100 chips. The tracker reads the game's own network messages (no screen recognition).

## Files
- `tracker.py`: starts Edge with `--remote-debugging-port=9222` and its own profile (`browser-profile/`), connects with Playwright `connect_over_cdp`, listens to `/catchup` responses (game events) and `/moves` requests (my moves), saves deck messages (`/api/Decks/compact` = my decks) to `games/decks/`. Writes `games/<date>_<id>/raw.jsonl, log.txt, summary.json`. Auto-saves finished matches online (`SAVE_ONLINE`). `--replay FILE` re-runs a saved file; `replay_game()` rebuilds a Game.
- `game_state.py`: the Game class (all game logic). `overlay.py`: Pillow-drawn tkinter overlay (HDT style). `cards.py`: card list, deck files, `GENERATORS`, `max_copies`. `update_cards.py`: rebuilds `cards.json` + `docs/cards.js` from the game's `card-faces.catalog-*.js` script.
- `website.py`: Firestore REST save to `users/<uid>/showdown_matches/<gameId>` (+ `meta/lastChange.showdownMatches`), using `tracker_key.txt` (same key as Origins). `--upload-all` uploads old matches.
- `docs/`: the website (GitHub Pages from `/docs`): `index.html/home.js`, `match-history.*`, `database.js`, `firebase.js`, `common.js` (card bars), `cards.js` (generated).
- `.gitignore`: browser-profile/, games/, art/, tracker_key.txt. **Never commit or print tracker_key.txt.**

## Protocol facts (hard-won)
- `/catchup` answer: `{snapshot, batches:[{moveIndex, eventData: "<JSON list>"}], status:{gameId, viewerRole, status:{result, serverNow...}}}`. Snapshot has `initEventData` (start state: CreateCard for decks/hands, SetPlayerDeckClasses, SetGameLogItems).
- `AddGameLogItem` = game log (CardPlayed, Check, PhaseChanged, CardsTargeted, Showdown, Fold), with `P1HandCards/P2HandCards`, `ChipsAfter`. `EndHand` (hand result), `EndGame` (WinnerId) = match end. Status `result`: 3 waiting, 2 playing, 0 over.
- Card tracking by game card id: CreateCard/MoveCards/DestroyCard/UpdateCardVisibility. My draws = my deck card ids moving to `P1_Hand`. Opponent hidden cards get **new ids on every hand change** (can't follow one card).
- Generated cards: `AnimateCard` with `Info.animationId == "generatedCard"` on the card id = the lighter border, sent to **both** players (found 2026-10-25; matched every generated card in 10 matches). My own cards also have `Slots: [{"Type":"Generated"}]`. The class rule and "maybe" guesses were removed. Backcheck by copy limit (Rare 1, Common 2) stays. Opponent's held generated count = hand arrivals − deck draws.
- My deck = the saved deck whose 2 classes match the match (`pick_deck`).

## Testing
- `python tracker.py --replay games\<folder>\raw.jsonl --no-overlay` (regression check on real matches).
- Website: copy `docs` to a temp folder, replace `firebase.js`/`database.js` with stubs that return `website_record()`s, serve with `python -m http.server`, check in the browser pane.

## Status (2026-10-25)
- Website published (GitHub repo Brainiac1830/showdown-tracker, public, Pages from `/docs`); key copied; 7 matches uploaded. `python website.py --upload-all --replace` re-saves old matches after tracker logic changes.
- Rules question: unclear if Showdown's terms allow trackers (real money). Advised: check ToS / ask them, use in free matches until then, no cross-match opponent profiles in the overlay.
